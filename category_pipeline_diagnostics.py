import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import feedparser
import requests

ROOT = Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text())
DATA = ROOT / "data/briefings"
TZ = ZoneInfo(CFG.get("timezone", "America/New_York"))
NOW = datetime.now(TZ)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BalancedBriefDiagnostics/1.0)"}


def parsed_date(entry):
    raw = entry.get("published", "") or entry.get("updated", "") or entry.get("created", "")
    try:
        value = parsedate_to_datetime(raw)
        if value.tzinfo is None:
            value = value.replace(tzinfo=TZ)
        return value.astimezone(TZ)
    except Exception:
        return None


def lookback(category):
    if category == "Good News":
        return timedelta(days=CFG.get("good_news_lookback_days", 7))
    return timedelta(hours=max(CFG.get("am_lookback_hours", 36), CFG.get("pm_lookback_hours", 18)))


def latest_briefing():
    briefings = []
    for path in DATA.glob("*.json"):
        try:
            payload = json.loads(path.read_text())
            briefings.append((datetime.fromisoformat(payload["generated_at"]), path, payload))
        except Exception:
            pass
    return max(briefings, key=lambda item: item[0]) if briefings else None


feed_rows = []
category_stats = defaultdict(lambda: {"feeds": 0, "reachable": 0, "entries": 0, "fresh": 0, "feed_errors": []})
for feed in CFG.get("feeds", []):
    category = feed.get("category", "Uncategorized")
    stats = category_stats[category]
    stats["feeds"] += 1
    try:
        response = requests.get(feed["url"], headers=HEADERS, timeout=15)
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        entries = parsed.entries[: CFG.get("entries_per_feed", 40)]
        fresh = sum(1 for entry in entries if (parsed_date(entry) and parsed_date(entry) >= NOW - lookback(category)))
        stats["reachable"] += 1
        stats["entries"] += len(entries)
        stats["fresh"] += fresh
        feed_rows.append({"name": feed.get("name", ""), "category": category, "status": response.status_code, "entries": len(entries), "fresh": fresh, "error": ""})
    except Exception as error:
        message = str(error)[:220]
        stats["feed_errors"].append(f"{feed.get('name','')}: {message}")
        feed_rows.append({"name": feed.get("name", ""), "category": category, "status": "error", "entries": 0, "fresh": 0, "error": message})

latest = latest_briefing()
selected_counts = Counter()
more_counts = Counter()
latest_name = "none"
if latest:
    _, path, payload = latest
    latest_name = path.name
    selected_counts.update(story.get("category", "Uncategorized") for story in payload.get("stories", []))
    for category, links in payload.get("more_stories", {}).items():
        more_counts[category] += len(links or [])

report = {
    "checked_at": NOW.isoformat(),
    "latest_briefing": latest_name,
    "categories": {},
    "feeds": feed_rows,
}
print("\nCATEGORY PIPELINE DIAGNOSTICS")
print(f"Latest briefing: {latest_name}")
print("Category | Feeds OK/Total | Entries | Fresh | Selected | More links | Diagnosis")
for category in CFG.get("category_order", sorted(category_stats)):
    stats = category_stats[category]
    selected = selected_counts[category]
    more = more_counts[category]
    if stats["reachable"] == 0:
        diagnosis = "FEED FAILURE: no configured feed was reachable"
    elif stats["fresh"] == 0:
        diagnosis = "SOURCE/FRESHNESS: reachable feeds returned no fresh entries"
    elif selected == 0 and more == 0:
        diagnosis = "GENERATOR FILTERING: fresh candidates existed but none reached output"
    elif selected == 0:
        diagnosis = "SELECTION: candidates reached links but no featured card"
    else:
        diagnosis = "OK"
    report["categories"][category] = {**stats, "selected": selected, "more_links": more, "diagnosis": diagnosis}
    print(f"{category} | {stats['reachable']}/{stats['feeds']} | {stats['entries']} | {stats['fresh']} | {selected} | {more} | {diagnosis}")

out = DATA / "category_pipeline_diagnostics.json"
out.write_text(json.dumps(report, indent=2))
print(f"\nWrote {out}")
