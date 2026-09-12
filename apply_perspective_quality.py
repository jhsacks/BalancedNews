from pathlib import Path
import re

path = Path('generate_brief.py')
source = path.read_text()

# Replace the active OpenAI prompt without depending on line formatting.
pattern = re.compile(r"prompt\s*=\s*'''[\s\S]*?Stories:\s*'''\s*\+\s*payload")
replacement = '''prompt = r\'\'\'Return only a valid JSON array containing every supplied story exactly once and every original key. Preserve URL, source, published, image, category, image_credit, and image_source exactly when present. Never invent facts and never return markdown.

Write for an intelligent non-specialist: a busy physician, executive, educator, or professional. Use clear language, but preserve the substance that makes the story worth knowing.

SUMMARY
Write exactly two concise, information-dense sentences totaling 35-55 words. The first sentence must explain the specific event, decision, dispute, finding, policy, transaction, or outcome. The second sentence must add the most important context, mechanism, consequence, or unresolved issue. A reader must understand what actually happened without opening the article. Never substitute generic phrases such as "a key position," "a major development," "an important ruling," "political consequences," or "legal protections" for the specific issue reported.

WHY IT MATTERS
why_it_matters is required for every story. Write one concrete sentence of 15-28 words explaining the practical consequence for law, policy, markets, health, technology, international relations, institutions, communities, or daily life. It must be specific to this story. Avoid statements that could fit almost any article, such as "court rulings shape laws," "the economy affects everyone," or "technology is changing rapidly."

PERSPECTIVES
For any story involving politics, policy, courts, war, diplomacy, policing, public health, economics, education, labor, corporate power, technology risk, rights, fairness, or competing public priorities, perspective_one and perspective_two are required. Each must be one substantive sentence of 18-32 words. Explain the actual disagreement and what each side believes is at stake. Do not merely say supporters approve, critics object, the court protected rights, or the court overstepped. Do not create false balance around established facts. Leave both fields blank only for clearly noncontroversial stories such as routine scores, rescues, weather facts, or straightforward discoveries.

UNCERTAINTY AND CONFIDENCE
uncertain is optional and should be blank unless an important fact remains unresolved. confidence must be Confirmed, Developing, Disputed, or Reported.

Before returning the JSON, verify that every summary identifies the specific subject of the story, every why_it_matters states a story-specific consequence, and every controversial story contains two meaningful perspectives. Stories: \'\'\' + payload'''

updated, count = pattern.subn(replacement, source, count=1)
if count != 1:
    raise RuntimeError('The active briefing prompt was not found. No file was changed.')

# Strengthen validation so a generic AI response cannot silently publish without perspectives.
validation_anchor = "if isinstance(result,list) and len(result)==len(chosen):chosen=result"
validation_replacement = '''if not isinstance(result,list) or len(result)!=len(chosen):
   raise ValueError('AI returned the wrong number of stories')
  perspective_categories={'U.S. Politics','Conflicts & Security','Middle East Affairs','Business & Economy','Society & Culture'}
  for story in result:
   story.setdefault('perspective_one','');story.setdefault('perspective_two','');story.setdefault('uncertain','')
   if not str(story.get('why_it_matters','')).strip():raise ValueError('AI omitted Why It Matters')
   if story.get('category') in perspective_categories and (not str(story.get('perspective_one','')).strip() or not str(story.get('perspective_two','')).strip()):
    raise ValueError(f"AI omitted perspectives for {story.get('category')}")
  chosen=result'''
if validation_anchor in updated:
    updated = updated.replace(validation_anchor, validation_replacement, 1)

compile(updated, 'generate_brief.py', 'exec')
path.write_text(updated)
print('Applied higher-substance briefing prompt and perspective validation.')
