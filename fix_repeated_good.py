from pathlib import Path

path = Path('generate_brief.py')
source = path.read_text()
old = "def repeated_good(x):return x['category']=='Good News' and any(x.get('url')==y.get('url') or similar(x,y) for y in old_good)"
new = "def repeated_good(x):return x['category']=='Good News' and any(x.get('url')==y.get('url') or same_story(x,y) for y in old_good)"
if old not in source:
    raise RuntimeError('Expected repeated_good line was not found. No changes made.')
updated = source.replace(old, new, 1)
compile(updated, 'generate_brief.py', 'exec')
path.write_text(updated)
print('Fixed repeated_good: similar() replaced with existing same_story().')
