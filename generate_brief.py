import os
import re
import io
import json
import html as hm
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

import feedparser
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageStat

ROOT = Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text())
DATA = ROOT / "data/briefings"
DATA.mkdir(parents=True, exist_ok=True)
TZ = ZoneInfo(CFG["timezone"])
now = datetime.now(TZ)
edition = os.getenv("BRIEF_EDITION") or ("AM" if now.hour < 12 else "PM")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BalancedBrief/1.0)"}


def clean(value):
    return re.sub(
        r"\s+",
        " ",
        BeautifulSoup(hm.unescape(value or ""), "html.parser").get_text(" ", strip=True),
    ).strip()


def parse_date(entry):
    raw = entry.get("published", "") or entry.get("updated", "") or entry.get("created", "")
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TZ)
        return parsed.astimezone(TZ), raw
    except Exception:
        return None, raw


def date_in_url(url):
    match = re.search(
        r"/(20\d{2})/(0?[1-9]|1[0-2])(?:/(0?[1-9]|[12]\d|3[01]))?/",
        urlparse(url or "").path,
    )
    if not match:
        return None
    try:
        return datetime(
            int(match.group(1)), int(match.group(2)), int(match.group(3) or 1), tzinfo=TZ
        )
    except ValueError:
        return None


def is_fresh(url, published, category):
    if category == "Good News":
        cutoff = now - timedelta(days=CFG.get("good_news_lookback_days", 7))
    else:
        hours = CFG.get("am_lookback_hours", 30) if edition == "AM" else CFG.get("pm_lookback_hours", 18)
        cutoff = now - timedelta(hours=hours)
    dated_url = date_in_url(url)
    if dated_url and dated_url < now - timedelta(days=CFG.get("max_article_age_days", 14)):
        return False
    return bool(published and published >= cutoff)


def valid_image(url):
    if not url or any(
        token in url.lower()
        for token in ("gstatic", "googleusercontent", "logo", "icon", "favicon", "placeholder", "avatar", "sprite")
    ):
        return False
    try:
        response = requests.get(url, timeout=7, headers=HEADERS)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        width, height = image.size
        if len(response.content) < 7000 or width < 280 or height < 140 or width / height > 4.0 or width / height < 0.55:
            return False
        small = image.resize((64, 64))
        colors = len(small.quantize(colors=32).getcolors() or [])
        stats = ImageStat.Stat(small)
        return colors > 5 and not (sum(stats.mean) / 3 > 228 and sum(stats.stddev) / 3 < 38)
    except Exception:
        return False


def find_image(entry, article_url):
    candidates = []
    for key in ("media_content", "media_thumbnail"):
        candidates.extend(
            item.get("url", "") for item in entry.get(key, []) if isinstance(item, dict)
        )
    for enclosure in entry.get("enclosures", []):
        if isinstance(enclosure, dict):
            candidates.append(enclosure.get("href", "") or enclosure.get("url", ""))
    for field in ("summary", "description", "content"):
        value = entry.get(field, "")
        if isinstance(value, list):
            value = " ".join(str(item.get("value", "")) for item in value if isinstance(item, dict))
        soup = BeautifulSoup(str(value), "html.parser")
        candidates.extend(urljoin(article_url, tag.get("src", "")) for tag in soup.find_all("img"))
    try:
        response = requests.get(article_url, timeout=9, headers=HEADERS, allow_redirects=True)
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in (
            soup.find("meta", property="og:image"),
            soup.find("meta", property="og:image:url"),
            soup.find("meta", attrs={"name": "twitter:image"}),
            soup.find("meta", attrs={"name": "twitter:image:src"}),
        ):
            if tag:
                candidates.append(urljoin(response.url, tag.get("content", "")))
        candidates.extend(
            urljoin(response.url, tag.get("src", ""))
            for tag in soup.select("article img, main img, figure img")[:15]
        )
    except Exception:
        pass
    return next((url for url in dict.fromkeys(candidates) if valid_image(url)), "")


STOP_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "after", "before",
    "over", "about", "says", "latest", "update", "news", "report", "reports", "today",
    "live", "analysis", "why", "how", "what", "could", "would", "will", "new", "amid",
}


def normalized_words(text):
    text = clean(text).lower()
    text = re.sub(r"\s+[-|:]\s+[^-|:]{2,50}$", "", text)
    return [word for word in re.findall(r"[a-z0-9]+", text) if len(word) > 2 and word not in STOP_WORDS]


def same_event(first, second):
    first_words = set(normalized_words(first.get("headline", "")))
    second_words = set(normalized_words(second.get("headline", "")))
    if not first_words or not second_words:
        return False
    shared = first_words & second_words
    containment = len(shared) / max(1, min(len(first_words), len(second_words)))
    jaccard = len(shared) / max(1, len(first_words | second_words))
    first_key = " ".join(sorted(first_words))
    second_key = " ".join(sorted(second_words))
    sequence = SequenceMatcher(None, first_key, second_key).ratio()
    if containment >= 0.52 or jaccard >= 0.39 or sequence >= 0.69:
        return True
    first_summary = set(normalized_words(first.get("summary", "")[:300]))
    second_summary = set(normalized_words(second.get("summary", "")[:300]))
    summary_overlap = (
        len(first_summary & second_summary) / max(1, min(len(first_summary), len(second_summary)))
        if first_summary and second_summary
        else 0
    )
    return len(shared) >= 2 and containment >= 0.34 and summary_overlap >= 0.44


def cluster_events(ranked_articles):
    clusters = []
    for article in ranked_articles:
        matching_cluster = next(
            (cluster for cluster in clusters if same_event(article, cluster[0])), None
        )
        if matching_cluster is None:
            clusters.append([article])
        else:
            matching_cluster.append(article)
    return clusters


def score(story):
    text = (story["headline"] + " " + story["summary"]).lower()
    return (
        2
        + sum(3 for keyword in CFG["importance_keywords"] if keyword in text)
        + 7 * any(keyword in text for keyword in CFG["sports_keywords"])
    )


def category_cap(category):
    return CFG.get("category_limits", {}).get(category, CFG["max_per_category"])


def load_feed(feed):
    try:
        response = requests.get(feed["url"], headers=HEADERS, timeout=10)
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
    except Exception as error:
        print(f"Feed skipped: {feed['name']}: {error}")
        return []
    loaded = []
    for entry in parsed.entries[: CFG.get("entries_per_feed", 30)]:
        published, raw = parse_date(entry)
        url = entry.get("link", "")
        headline = clean(entry.get("title", ""))
        summary = clean(entry.get("summary", ""))[:900]
        if not url or not headline or not is_fresh(url, published, feed["category"]):
            continue
        story = {
            "headline": headline,
            "summary": summary,
            "why_it_matters": "",
            "url": url,
            "source": feed["name"],
            "published": raw,
            "category": feed["category"],
            "confidence": "Reported",
            "image": "",
            "perspective_one": "",
            "perspective_two": "",
            "uncertain": "",
            "_entry": entry,
        }
        story["_score"] = score(story)
        loaded.append(story)
    return loaded


articles = []
with ThreadPoolExecutor(max_workers=CFG.get("feed_workers", 8)) as executor:
    futures = [executor.submit(load_feed, feed) for feed in CFG["feeds"]]
    for future in as_completed(futures):
        articles.extend(future.result())

ranked_articles = sorted(
    articles, key=lambda story: (story["_score"], story["published"]), reverse=True
)
clusters = cluster_events(ranked_articles)
representatives = [cluster[0] for cluster in clusters]
print(f"Clustered {len(articles)} articles into {len(representatives)} distinct events")

# Avoid repeating Good News recently.
old_good = []
history_cutoff = now - timedelta(days=CFG.get("good_news_history_days", 14))
for path in DATA.glob("*.json"):
    try:
        old = json.loads(path.read_text())
        if datetime.fromisoformat(old["generated_at"]) >= history_cutoff:
            old_good.extend(
                story for story in old.get("stories", []) if story.get("category") == "Good News"
            )
    except Exception:
        pass


def repeated_good_news(story):
    return story["category"] == "Good News" and any(
        story.get("url") == old.get("url") or same_event(story, old) for old in old_good
    )


chosen = []
counts = {}
# First pass guarantees breadth: one distinct event per category whenever available.
for category in CFG["category_order"]:
    candidate = next(
        (
            story
            for story in representatives
            if story["category"] == category
            and not repeated_good_news(story)
            and not any(same_event(story, selected) for selected in chosen)
        ),
        None,
    )
    if candidate:
        chosen.append(candidate)
        counts[category] = 1

# Second pass adds only important, distinct events until the overall target is reached.
for story in representatives:
    if len(chosen) >= CFG["max_stories"]:
        break
    if counts.get(story["category"], 0) >= category_cap(story["category"]):
        continue
    if repeated_good_news(story) or any(same_event(story, selected) for selected in chosen):
        continue
    chosen.append(story)
    counts[story["category"]] = counts.get(story["category"], 0) + 1

# Links must also be genuinely different events, never alternate coverage of a card.
more = {category: [] for category in CFG["category_order"]}
for story in representatives:
    category = story["category"]
    if story in chosen or repeated_good_news(story):
        continue
    if len(more[category]) >= CFG["more_links_per_category"]:
        continue
    if any(same_event(story, selected) for selected in chosen):
        continue
    if any(same_event(story, link) for link in more[category]):
        continue
    more[category].append(
        {
            "headline": story["headline"],
            "url": story["url"],
            "source": story["source"],
            "summary": story["summary"],
        }
    )

if not any(story.get("category") == "Good News" for story in chosen):
    print("WARNING: No fresh Good News story found.")


def attach_image(story):
    entry = story.pop("_entry")
    story["image"] = find_image(entry, story["url"])
    return story


with ThreadPoolExecutor(max_workers=CFG.get("image_workers", 6)) as executor:
    chosen = list(executor.map(attach_image, chosen))

key = os.getenv("OPENAI_API_KEY", "").strip()
if not key:
    raise RuntimeError("OPENAI_API_KEY missing; previous briefing preserved.")

from openai import OpenAI

payload = json.dumps([{k: v for k, v in story.items() if not k.startswith("_")} for story in chosen])
prompt = '''Return only a valid JSON array with every supplied story exactly once and every original key. Preserve URL, source, published, image, and category exactly. Never invent facts or return markdown.
For every story, summary is exactly two short plain-language sentences totaling 24-40 words. why_it_matters is required and is one clear sentence under 18 words. Use common words, active voice, and one idea per sentence.
Perspectives are required whenever a story is even mildly controversial or involves politics, policy, courts, war, diplomacy, policing, public health, economics, education, labor, corporate power, technology risks, rights, fairness, or competing public priorities. For such stories, perspective_one and perspective_two each state a distinct good-faith argument in one plain sentence of 10-20 words. Explain the actual disagreement, not political teams. Do not create false balance about established facts. Leave perspectives blank only for clearly noncontroversial stories such as routine sports results, rescues, or straightforward discoveries. uncertain is optional and blank unless an important fact remains unresolved. confidence is Confirmed, Developing, Disputed, or Reported. Stories: ''' + payload

try:
    text = (
        OpenAI(api_key=key)
        .responses.create(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), input=prompt)
        .output_text.strip()
        .removeprefix("```json")
        .removesuffix("```")
        .strip()
    )
    result = json.loads(text)
    if not isinstance(result, list) or len(result) != len(chosen):
        raise ValueError("AI returned the wrong story count")
    required = {
        "headline", "summary", "why_it_matters", "url", "source", "published",
        "category", "confidence", "image",
    }
    for story in result:
        story.setdefault("perspective_one", "")
        story.setdefault("perspective_two", "")
        story.setdefault("uncertain", "")
        missing = required - set(story)
        if missing:
            raise ValueError(f"AI response missing required fields: {sorted(missing)}")
        if not str(story["why_it_matters"]).strip():
            raise ValueError("AI response omitted Why It Matters")
    chosen = result
except Exception as error:
    raise RuntimeError(f"AI enrichment failed; previous briefing preserved: {error}") from error

for story in chosen:
    story.pop("_score", None)

output = {
    "generated_at": now.isoformat(),
    "edition": edition,
    "stories": chosen,
    "more_stories": more,
}
filename = f"{now:%Y-%m-%d}_{edition}.json"
(DATA / filename).write_text(json.dumps(output, indent=2))
print(filename, len(chosen))
