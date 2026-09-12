import os, re, json, html as hm, io
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

import feedparser, requests
from bs4 import BeautifulSoup
from PIL import Image, ImageStat
from topic_images import topic_image

ROOT = Path(__file__).parent
CFG = json.loads((ROOT / 'config.json').read_text())
DATA = ROOT / 'data/briefings'
DATA.mkdir(parents=True, exist_ok=True)
TZ = ZoneInfo(CFG['timezone'])
now = datetime.now(TZ)
edition = os.getenv('BRIEF_EDITION') or ('AM' if now.hour < 12 else 'PM')
HEADERS = {'User-Agent': 'Mozilla/5.0'}


def clean(value):
    return re.sub(r'\s+', ' ', BeautifulSoup(hm.unescape(value or ''), 'html.parser').get_text(' ', strip=True)).strip()


def pdate(entry):
    raw = entry.get('published', '') or entry.get('updated', '') or entry.get('created', '')
    try:
        value = parsedate_to_datetime(raw)
        return (value.replace(tzinfo=TZ) if value.tzinfo is None else value).astimezone(TZ), raw
    except Exception:
        return None, raw


def url_date(url):
    match = re.search(r'/(20\d{2})/(0?[1-9]|1[0-2])(?:/(0?[1-9]|[12]\d|3[01]))?/', urlparse(url or '').path)
    if not match:
        return None
    try:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3) or 1), tzinfo=TZ)
    except ValueError:
        return None


def fresh(url, published, category):
    cutoff = now - timedelta(days=4) if category == 'Good News' else now - timedelta(hours=36 if edition == 'AM' else 18)
    dated = url_date(url)
    if dated and dated < now - timedelta(days=CFG.get('max_article_age_days', 14)):
        return False
    return bool(published and published >= cutoff)


def valid_image(url):
    if not url or any(part in url.lower() for part in ('gstatic', 'googleusercontent', 'logo', 'icon', 'favicon', 'placeholder', 'avatar')):
        return False
    try:
        response = requests.get(url, timeout=8, headers=HEADERS)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content)).convert('RGB')
        width, height = image.size
        if len(response.content) < 9000 or width < 300 or height < 150 or width / height > 3.8 or width / height < .58:
            return False
        small = image.resize((64, 64))
        colors = small.quantize(colors=32).getcolors() or []
        stats = ImageStat.Stat(small)
        return len(colors) > 5 and not (sum(stats.mean) / 3 > 225 and sum(stats.stddev) / 3 < 42)
    except Exception:
        return False


def find_image(entry, url):
    candidates = []
    for key in ('media_content', 'media_thumbnail'):
        candidates += [item.get('url', '') for item in entry.get(key, []) if isinstance(item, dict)]
    for field in ('summary', 'description', 'content'):
        value = entry.get(field, '')
        if isinstance(value, list):
            value = ' '.join(str(item.get('value', '')) for item in value if isinstance(item, dict))
        candidates += [urljoin(url, tag.get('src', '')) for tag in BeautifulSoup(str(value), 'html.parser').find_all('img')]
    try:
        response = requests.get(url, timeout=10, headers=HEADERS, allow_redirects=True)
        soup = BeautifulSoup(response.text, 'html.parser')
        for tag in (soup.find('meta', property='og:image'), soup.find('meta', property='og:image:url'), soup.find('meta', attrs={'name': 'twitter:image'})):
            if tag:
                candidates.append(urljoin(response.url, tag.get('content', '')))
        candidates += [urljoin(response.url, tag.get('src', '')) for tag in soup.select('article img, main img')[:10]]
    except Exception:
        pass
    return next((candidate for candidate in dict.fromkeys(candidates) if valid_image(candidate)), '')


def tokens(text):
    stop = {'the','and','for','with','from','that','this','into','after','before','over','about','says','latest','update','news','report','reports','announces','announce','today','live','analysis','why','how','what'}
    return {word for word in re.findall(r'[a-z0-9]+', text.lower()) if len(word) > 2 and word not in stop}


def headline_key(text):
    return ' '.join(sorted(tokens(text)))


def same_story(first, second):
    first_tokens = tokens(first.get('headline', ''))
    second_tokens = tokens(second.get('headline', ''))
    if not first_tokens or not second_tokens:
        return False
    overlap = first_tokens & second_tokens
    containment = len(overlap) / max(1, min(len(first_tokens), len(second_tokens)))
    union = len(overlap) / max(1, len(first_tokens | second_tokens))
    sequence = SequenceMatcher(None, headline_key(first.get('headline', '')), headline_key(second.get('headline', ''))).ratio()
    if containment >= .55 or union >= .42 or sequence >= .72:
        return True
    first_summary = tokens(first.get('summary', '')[:260])
    second_summary = tokens(second.get('summary', '')[:260])
    summary_overlap = len(first_summary & second_summary) / max(1, min(len(first_summary), len(second_summary))) if first_summary and second_summary else 0
    return containment >= .38 and summary_overlap >= .48


def duplicate(story, selected):
    return any(same_story(story, other) for other in selected)


def score(story):
    text = (story['headline'] + ' ' + story['summary']).lower()
    return 2 + sum(3 for keyword in CFG['importance_keywords'] if keyword in text) + 7 * any(keyword in text for keyword in CFG['sports_keywords'])


def cap(category):
    return CFG.get('category_limits', {}).get(category, CFG['max_per_category'])


old_good = []
history = now - timedelta(days=CFG.get('good_news_history_days', 14))
for path in DATA.glob('*.json'):
    try:
        briefing = json.loads(path.read_text())
        generated = datetime.fromisoformat(briefing['generated_at'])
        if generated >= history:
            old_good += [story for story in briefing.get('stories', []) if story.get('category') == 'Good News']
    except Exception:
        pass


def repeated_good(story):
    return story['category'] == 'Good News' and any(story.get('url') == old.get('url') or same_story(story, old) for old in old_good)


def load_feed(feed):
    try:
        response = requests.get(feed['url'], headers=HEADERS, timeout=10)
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
    except Exception as error:
        print(f"Feed skipped: {feed['name']}: {error}")
        return []
    loaded = []
    for entry in parsed.entries[:CFG.get('entries_per_feed', 30)]:
        published, raw = pdate(entry)
        url = entry.get('link', '')
        headline = clean(entry.get('title', ''))
        summary = clean(entry.get('summary', ''))[:900]
        if not url or not headline or not fresh(url, published, feed['category']):
            continue
        story = {'headline': headline, 'summary': summary, 'why_it_matters': '', 'url': url, 'source': feed['name'], 'published': raw, 'category': feed['category'], 'confidence': 'Reported', 'image': '', 'perspective_one': '', 'perspective_two': '', 'uncertain': '', '_entry': entry}
        story['_score'] = score(story)
        loaded.append(story)
    return loaded


items = []
with ThreadPoolExecutor(max_workers=CFG.get('feed_workers', 8)) as pool:
    futures = [pool.submit(load_feed, feed) for feed in CFG['feeds']]
    for future in as_completed(futures):
        items.extend(future.result())

ranked = sorted(items, key=lambda story: (story['_score'], story['published']), reverse=True)
chosen, counts, source_counts, team_counts = [], {}, {}, {}
TEAM_PATTERNS = {
    'atlanta hawks': r'\b(?:atlanta\s+)?hawks\b',
    'atlanta braves': r'\b(?:atlanta\s+)?braves\b',
    'atlanta falcons': r'\b(?:atlanta\s+)?falcons\b',
    'atlanta united': r'\batlanta\s+united\b',
    'georgia bulldogs': r'\b(?:georgia\s+bulldogs|uga|bulldogs)\b',
    'indiana hoosiers': r'\b(?:indiana\s+hoosiers|hoosiers)\b',
    'wisconsin badgers': r'\b(?:wisconsin\s+badgers|badgers)\b'
}


def story_team(story):
    text = (story.get('headline', '') + ' ' + story.get('summary', '')).lower()
    for team, pattern in TEAM_PATTERNS.items():
        if re.search(pattern, text):
            return team
    return ''


def source_allowed(story, category_pass=False):
    return True if category_pass else source_counts.get(story.get('source', ''), 0) < CFG.get('max_featured_per_source', 2)


def team_allowed(story):
    team = story_team(story)
    return not team or team_counts.get(team, 0) < CFG.get('max_featured_per_team', 1)


def add_story(story):
    chosen.append(story)
    category = story.get('category', '')
    source_name = story.get('source', '')
    team = story_team(story)
    counts[category] = counts.get(category, 0) + 1
    source_counts[source_name] = source_counts.get(source_name, 0) + 1
    if team:
        team_counts[team] = team_counts.get(team, 0) + 1


for category in CFG['category_order']:
    candidates = [story for story in ranked if story.get('category') == category]
    target = max(1, min(CFG.get('category_targets', {}).get(category, CFG.get('default_category_target', 1)), cap(category)))
    for story in candidates:
        if counts.get(category, 0) >= target:
            break
        if repeated_good(story) or duplicate(story, chosen) or not team_allowed(story) or not source_allowed(story, counts.get(category, 0) == 0):
            continue
        add_story(story)

for category in CFG['category_order']:
    candidates = [story for story in ranked if story.get('category') == category]
    for story in candidates:
        if counts.get(category, 0) >= cap(category):
            break
        if repeated_good(story) or duplicate(story, chosen) or not team_allowed(story) or not source_allowed(story):
            continue
        add_story(story)

selected_urls = {story['url'] for story in chosen}
more = {category: [] for category in CFG['category_order']}
for story in ranked:
    if story['url'] in selected_urls or repeated_good(story) or len(more[story['category']]) >= CFG['more_links_per_category'] or duplicate(story, chosen + more[story['category']]):
        continue
    more[story['category']].append({'headline': story['headline'], 'url': story['url'], 'source': story['source'], 'summary': story['summary']})


def attach_image(story):
    entry = story.pop('_entry')
    story['image'] = find_image(entry, story['url'])
    story['image_credit'] = ''
    story['image_source'] = ''
    if not story['image']:
        fallback = topic_image(story['headline'], story['category'], HEADERS)
        if fallback:
            story['image'] = fallback['url']
            story['image_credit'] = fallback['credit']
            story['image_source'] = fallback['source']
    return story


with ThreadPoolExecutor(max_workers=CFG.get('image_workers', 6)) as pool:
    chosen = list(pool.map(attach_image, chosen))

key = os.getenv('OPENAI_API_KEY', '').strip()
if key and chosen:
    try:
        from openai import OpenAI
        payload = json.dumps([{key: value for key, value in story.items() if not key.startswith('_')} for story in chosen])
        prompt = '''Return only a valid JSON array containing every supplied story exactly once and every original key. Preserve URL, source, published, image, category, image_credit, and image_source exactly. Never invent facts. Never return markdown.

Write for an intelligent non-specialist: a busy physician, executive, educator, or professional. Keep the prose accessible and concise, but give the reader enough substance to understand the actual issue. Do not write at a childlike level.

SUMMARY
Write exactly two information-dense sentences, usually 35-60 words total. The first sentence must identify the specific event, ruling, policy, dispute, announcement, discovery, market move, or conflict development. The second sentence should add the most important context, consequence, affected group, or next step.

A reader must understand what actually happened without opening the article. Do not merely paraphrase the headline. Do not omit the subject of a court case, the content of a policy, the nature of a conflict development, the purpose of a technology, or the substance of a business decision.

Avoid generic phrases such as major development, key ruling, significant decision, political consequences, legal protections, sparked debate, supporters praised, and critics pushed back unless followed by the specific issue.

WHY IT MATTERS
why_it_matters is required for every story. Write one information-dense sentence of roughly 18-32 words. Explain the practical consequence unique to this story, including who or what could be affected. Avoid statements that could apply to almost any story.

PERSPECTIVES
For any story involving politics, public policy, courts, elections, war, diplomacy, economics, regulation, healthcare policy, education, labor, business power, technology governance, rights, public spending, fairness, or competing public priorities, perspective_one and perspective_two are required.

Each perspective should be one substantive sentence, usually 22-45 words. Explain the actual tradeoff or disagreement. State what each side believes is at stake, what outcome each side values, or what risk each side fears. Do not use empty labels such as supporters think this protects rights or critics think this goes too far.

When the underlying disagreement is not supported by the supplied story, leave both perspective fields blank rather than inventing a debate. Do not create false balance around established facts.

UNCERTAINTY AND CONFIDENCE
uncertain is optional. Use one short sentence only when a meaningful fact, consequence, attribution, or next step remains unresolved. Otherwise return an empty string. confidence must be Confirmed, Developing, Disputed, or Reported.

QUALITY CHECK
Before returning JSON, verify that each summary names the actual issue under discussion, each why_it_matters is specific to that story, and each perspective teaches the reader something substantive about the disagreement. Preserve every story and every required key.

Stories: ''' + payload
        text = OpenAI(api_key=key).responses.create(model=os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'), input=prompt).output_text.strip().removeprefix('```json').removesuffix('```').strip()
        result = json.loads(text)
        if isinstance(result, list) and len(result) == len(chosen):
            for story in result:
                story.setdefault('perspective_one', '')
                story.setdefault('perspective_two', '')
                story.setdefault('uncertain', '')
            chosen = result
    except Exception as error:
        print('AI refinement skipped:', error)

for story in chosen:
    story.pop('_score', None)

output = {'generated_at': now.isoformat(), 'edition': edition, 'stories': chosen, 'more_stories': more}
filename = f"{now:%Y-%m-%d}_{edition}.json"
(DATA / filename).write_text(json.dumps(output, indent=2))
print(filename, len(chosen))
