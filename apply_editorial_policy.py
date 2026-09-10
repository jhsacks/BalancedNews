from pathlib import Path
import re

PATH = Path('generate_brief.py')
source = PATH.read_text()

START_MARKERS = [
    "chosen=[]; counts={}",
    "chosen = []\ncounts = {}",
]
END_MARKERS = [
    "selected_urls=",
    "selected_urls =",
    "# Links must also be genuinely different events",
    "more = {category: []",
    "more={c:[]",
]

start = next((source.find(marker) for marker in START_MARKERS if source.find(marker) >= 0), -1)
if start < 0:
    raise RuntimeError('Could not find the story-selection start. No file was changed.')
end_candidates = [source.find(marker, start) for marker in END_MARKERS if source.find(marker, start) >= 0]
if not end_candidates:
    raise RuntimeError('Could not find the story-selection end. No file was changed.')
end = min(end_candidates)

# Determine the ranked candidate list and duplicate predicate already used by the current generator.
ranked_name = 'representatives' if re.search(r'\brepresentatives\s*=', source[:start]) else 'ranked'
if re.search(r'def\s+same_event\s*\(', source):
    duplicate_expression = 'any(same_event(story, selected) for selected in chosen)'
elif re.search(r'def\s+same_story\s*\(', source):
    duplicate_expression = 'any(same_story(story, selected) for selected in chosen)'
else:
    duplicate_expression = 'duplicate(story, chosen)'

policy = f'''chosen=[]
counts={{}}
source_counts={{}}
team_counts={{}}

TEAM_PATTERNS={{
 'atlanta hawks': r'\\b(?:atlanta\\s+)?hawks\\b',
 'atlanta braves': r'\\b(?:atlanta\\s+)?braves\\b',
 'atlanta falcons': r'\\b(?:atlanta\\s+)?falcons\\b',
 'atlanta united': r'\\batlanta\\s+united\\b',
 'georgia bulldogs': r'\\b(?:georgia\\s+bulldogs|uga|bulldogs)\\b',
 'indiana hoosiers': r'\\b(?:indiana\\s+hoosiers|hoosiers)\\b',
 'wisconsin badgers': r'\\b(?:wisconsin\\s+badgers|badgers)\\b'
}}

def story_team(story):
 text=(story.get('headline','')+' '+story.get('summary','')).lower()
 for team,pattern in TEAM_PATTERNS.items():
  if re.search(pattern,text):return team
 return ''

def source_allowed(story, category_pass=False):
 # A first category story is never blocked by source diversity.
 if category_pass:return True
 return source_counts.get(story.get('source',''),0)<CFG.get('max_featured_per_source',2)

def team_allowed(story):
 team=story_team(story)
 return not team or team_counts.get(team,0)<CFG.get('max_featured_per_team',1)

def add_story(story):
 chosen.append(story)
 category=story.get('category','')
 source_name=story.get('source','')
 team=story_team(story)
 counts[category]=counts.get(category,0)+1
 source_counts[source_name]=source_counts.get(source_name,0)+1
 if team:team_counts[team]=team_counts.get(team,0)+1

# Each category is curated independently. Sports, Good News, and every other section do not compete for one shared quota.
for category in CFG['category_order']:
 category_candidates=[story for story in {ranked_name} if story.get('category')==category]
 category_target=CFG.get('category_targets',{{}}).get(category,CFG.get('default_category_target',1))
 category_max=CFG.get('category_limits',{{}}).get(category,CFG.get('max_per_category',2))
 target=max(1,min(category_target,category_max))
 for story in category_candidates:
  if counts.get(category,0)>=target:break
  if repeated_good(story) if 'repeated_good' in globals() else repeated_good_news(story) if 'repeated_good_news' in globals() else False:continue
  if {duplicate_expression}:continue
  if not team_allowed(story):continue
  if not source_allowed(story,category_pass=(counts.get(category,0)==0)):continue
  add_story(story)

# Large-news-day expansion is category-local. A quiet Sports section cannot suppress major World or U.S. coverage.
for category in CFG['category_order']:
 category_candidates=[story for story in {ranked_name} if story.get('category')==category]
 category_max=CFG.get('category_limits',{{}}).get(category,CFG.get('max_per_category',2))
 for story in category_candidates:
  if counts.get(category,0)>=category_max:break
  if repeated_good(story) if 'repeated_good' in globals() else repeated_good_news(story) if 'repeated_good_news' in globals() else False:continue
  if {duplicate_expression}:continue
  if not team_allowed(story) or not source_allowed(story):continue
  add_story(story)

'''

updated = source[:start] + policy + source[end:]
compile(updated, 'generate_brief.py', 'exec')
PATH.write_text(updated)
print('Applied independent category selection, event deduplication, one-story-per-team, and source diversity.')
