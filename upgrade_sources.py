import json
from pathlib import Path

CONFIG = Path('config.json')
config = json.loads(CONFIG.read_text())

feeds = [
    # General / national coverage
    {"name":"Associated Press U.S.","url":"https://news.google.com/rss/search?q=source%3AAP+US+politics+national+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen","category":"U.S. News"},
    {"name":"Associated Press World","url":"https://news.google.com/rss/search?q=source%3AAP+world+international+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen","category":"World News"},
    {"name":"USA Today U.S.","url":"https://news.google.com/rss/search?q=source%3AUSA+Today+US+national+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen","category":"U.S. News"},
    {"name":"USA Today Politics","url":"https://news.google.com/rss/search?q=source%3AUSA+Today+politics+Congress+White+House+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen","category":"U.S. Politics"},

    # Society, culture, health, education
    {"name":"PBS NewsHour Society","url":"https://news.google.com/rss/search?q=source%3APBS+NewsHour+education+housing+workforce+society+when%3A3d&hl=en-US&gl=US&ceid=US%3Aen","category":"Society & Culture"},
    {"name":"USA Today Society","url":"https://news.google.com/rss/search?q=source%3AUSA+Today+education+parenting+housing+workplace+society+when%3A3d&hl=en-US&gl=US&ceid=US%3Aen","category":"Society & Culture"},
    {"name":"U.S. News Society","url":"https://news.google.com/rss/search?q=source%3AUS+News+education+health+workforce+society+when%3A3d&hl=en-US&gl=US&ceid=US%3Aen","category":"Society & Culture"},
    {"name":"U.S. News Health","url":"https://www.usnews.com/rss/health","category":"Health & Medicine"},

    # Middle East: Israeli, Gulf/Arab, and international-wire coverage
    {"name":"Times of Israel","url":"https://www.timesofisrael.com/israel-and-the-region/feed/","category":"Middle East Affairs"},
    {"name":"The National Middle East","url":"https://news.google.com/rss/search?q=source%3AThe+National+Middle+East+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen","category":"Middle East Affairs"},
    {"name":"Arab News Middle East","url":"https://news.google.com/rss/search?q=source%3AArab+News+Middle+East+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen","category":"Middle East Affairs"},
    {"name":"Reuters Middle East","url":"https://news.google.com/rss/search?q=source%3AReuters+Middle+East+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen","category":"Middle East Affairs"},

    # Sports variety
    {"name":"ESPN NFL","url":"https://www.espn.com/espn/rss/nfl/news","category":"Sports"},
    {"name":"ESPN MLB","url":"https://www.espn.com/espn/rss/mlb/news","category":"Sports"},
    {"name":"CBS Sports NFL","url":"https://news.google.com/rss/search?q=source%3ACBS+Sports+NFL+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen","category":"Sports"},
    {"name":"CBS Sports MLB","url":"https://news.google.com/rss/search?q=source%3ACBS+Sports+MLB+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen","category":"Sports"},
    {"name":"Yahoo Sports NFL","url":"https://news.google.com/rss/search?q=source%3AYahoo+Sports+NFL+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen","category":"Sports"},
    {"name":"Yahoo Sports MLB","url":"https://news.google.com/rss/search?q=source%3AYahoo+Sports+MLB+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen","category":"Sports"},
    {"name":"NFL Opening Week","url":"https://news.google.com/rss/search?q=NFL+opening+week+kickoff+scores+injuries+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen","category":"Sports"},
    {"name":"Braves Playoff Race","url":"https://news.google.com/rss/search?q=Atlanta+Braves+playoff+race+wild+card+standings+when%3A2d&hl=en-US&gl=US&ceid=US%3Aen","category":"Sports"},

    # Positive reporting pool
    {"name":"Associated Press Good News","url":"https://news.google.com/rss/search?q=source%3AAP+rescue+recovery+breakthrough+community+when%3A7d&hl=en-US&gl=US&ceid=US%3Aen","category":"Good News"},
    {"name":"USA Today Good News","url":"https://news.google.com/rss/search?q=source%3AUSA+Today+rescue+community+breakthrough+success+when%3A7d&hl=en-US&gl=US&ceid=US%3Aen","category":"Good News"}
]

existing = {(f.get('name'), f.get('category')) for f in config.get('feeds', [])}
added = []
for feed in feeds:
    key = (feed['name'], feed['category'])
    if key not in existing:
        config.setdefault('feeds', []).append(feed)
        existing.add(key)
        added.append(feed['name'])

# Preserve current settings while strengthening only settings the working generator already understands.
sports_keywords = set(config.get('sports_keywords', []))
sports_keywords.discard('atlanta hawks')
sports_keywords.update({
    'nfl opening week','nfl kickoff','season opener','playoff race','wild card',
    'clinched','elimination game','super bowl','world series','college football playoff','championship'
})
config['sports_keywords'] = sorted(sports_keywords)
config.setdefault('category_limits', {})['Sports'] = 2
config['category_limits']['Good News'] = 1
config.setdefault('source_expansion', {})['version'] = '2026-09-10'
config['source_expansion']['excluded'] = ['Al Jazeera']
config['source_expansion']['notes'] = 'Israeli, Gulf/Arab, international-wire, society, general, and sports source expansion.'

CONFIG.write_text(json.dumps(config, indent=2) + '\n')
print(f'Added {len(added)} new feeds.')
for name in added:
    print(f'  + {name}')
print(f'Total feeds now: {len(config.get("feeds", []))}')
