from pathlib import Path

path = Path('generate_brief.py')
source = path.read_text()

history_start = source.find('old_good = []')
history_end = source.find('\n\ndef load_feed', history_start)
if history_start < 0 or history_end < 0:
    raise RuntimeError('Could not find the existing Good News history block. No changes were made.')

history_block = '''recent_briefings = []
for path in DATA.glob('*.json'):
    try:
        briefing = json.loads(path.read_text())
        generated = datetime.fromisoformat(briefing['generated_at'])
        recent_briefings.append((generated, briefing))
    except Exception:
        pass

# Compare candidates with the four most recent completed editions.
recent_briefings.sort(key=lambda item: item[0], reverse=True)
recent_featured = []
for _, briefing in recent_briefings[:4]:
    recent_featured.extend(briefing.get('stories', []))


def repeated_recent(story):
    return any(
        story.get('url') == previous.get('url')
        or same_story(story, previous)
        for previous in recent_featured
    )
'''
source = source[:history_start] + history_block + source[history_end:]

selection_start = source.find("for category in CFG['category_order']:", source.find('def add_story'))
selection_end = source.find('\nselected_urls =', selection_start)
if selection_start < 0 or selection_end < 0:
    raise RuntimeError('Could not find the existing selection loops. No changes were made.')

selection_block = '''for category in CFG['category_order']:
    candidates = [story for story in ranked if story.get('category') == category]

    # Baseline: one distinct recent story per category when one is available.
    for story in candidates:
        if counts.get(category, 0) >= 1:
            break
        if repeated_recent(story) or duplicate(story, chosen):
            continue
        if not team_allowed(story):
            continue
        if not source_allowed(story, category_pass=True):
            continue
        add_story(story)

# Additional cards must be both distinct and significant.
# Fewer stories are preferable to filler or repeated coverage.
extra_story_min_score = CFG.get('extra_story_min_score', 5)
for category in CFG['category_order']:
    candidates = [story for story in ranked if story.get('category') == category]
    for story in candidates:
        if len(chosen) >= CFG.get('max_stories', 16):
            break
        if counts.get(category, 0) >= cap(category):
            break
        if story.get('_score', 0) < extra_story_min_score:
            continue
        if repeated_recent(story) or duplicate(story, chosen):
            continue
        if not team_allowed(story) or not source_allowed(story):
            continue
        add_story(story)
'''
source = source[:selection_start] + selection_block + source[selection_end:]

source = source.replace(
    "story['url'] in selected_urls or repeated_good(story) or",
    "story['url'] in selected_urls or repeated_recent(story) or",
    1,
)

if 'repeated_good(' in source:
    raise RuntimeError('A repeated_good reference remains. No changes were written.')

compile(source, 'generate_brief.py', 'exec')
path.write_text(source)
print('Applied four-edition repeat filtering and quality-first minimums.')
