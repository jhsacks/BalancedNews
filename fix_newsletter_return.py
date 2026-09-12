from pathlib import Path

path = Path('newsletter.py')
source = path.read_text()
lines = source.splitlines()

# The deployed file has a top-level `return sent`, which prevents app.py from importing newsletter.py.
changed = False
for index, line in enumerate(lines):
    if line.strip() == 'return sent' and not line.startswith((' ', '\t')):
        # `return sent` belongs inside send_newsletter(). Four spaces keeps it inside the function
        # and outside the subscriber loop when paired with the preceding top-level print line.
        lines[index] = '    return sent'
        changed = True

if not changed:
    raise RuntimeError("No top-level 'return sent' was found. No changes were made.")

updated = '\n'.join(lines) + '\n'
compile(updated, 'newsletter.py', 'exec')
path.write_text(updated)
print("Fixed newsletter.py and verified Python syntax.")
