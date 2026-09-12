from pathlib import Path

path = Path('generate_brief.py')
source = path.read_text()

start_markers = ["prompt='''", 'prompt = \'\'\'', 'prompt="""', 'prompt = """']
start = next((source.find(marker) for marker in start_markers if source.find(marker) >= 0), -1)
if start < 0:
    raise RuntimeError('The OpenAI prompt was not found. No changes were made.')

# Keep the exact assignment prefix used by the deployed generator.
quote = "'''" if "'''" in source[start:start+20] else '"""'
content_start = source.find(quote, start) + 3
payload_markers = [quote + '+payload', quote + ' + payload']
end = next((source.find(marker, content_start) for marker in payload_markers if source.find(marker, content_start) >= 0), -1)
if end < 0:
    raise RuntimeError('The end of the OpenAI prompt was not found. No changes were made.')

prompt = '''Return only a valid JSON array containing every supplied story exactly once and every original key. Preserve URL, source, published, image, category, image_credit, and image_source exactly when those keys are present. Never invent facts. Never return markdown.

AUDIENCE AND STYLE
Write for an intelligent non-specialist reader, such as a busy physician, executive, educator, or professional. Use clear language and short sentences, but preserve the important substance. Aim for concise, information-dense journalism rather than simplified or generic wording.

SUMMARY
For every story, write exactly two clear sentences totaling about 38-58 words.
The first sentence must explain the specific event, ruling, policy, dispute, discovery, company action, conflict development, sports result, or other reported outcome. Include enough detail that the reader understands what actually happened without opening the article.
The second sentence should add the most important context, consequence, limitation, or next step.
Do not merely restate the headline. Do not write vague phrases such as major development, key ruling, significant decision, political consequences, important legal protections, or controversial issue unless the sentence immediately explains the specific substance.
If the supplied article text does not identify a critical detail, say what remains unclear rather than guessing.

WHY IT MATTERS
why_it_matters is required for every story. Write one information-dense sentence of about 16-28 words explaining the concrete consequence or stakes of this specific event.
Do not use broad statements that could fit almost any article, such as court rulings shape laws, the economy affects everyone, technology is changing rapidly, or the conflict could increase tensions.
Explain who or what may be affected and how, while staying within the facts supplied.

PERSPECTIVES
Perspectives are required whenever a story is even mildly controversial or involves politics, policy, courts, elections, war, diplomacy, policing, public health, economics, education, labor, corporate power, technology risks, rights, fairness, or competing public priorities.
perspective_one and perspective_two must each be one distinct, good-faith argument of about 18-32 words.
Explain the actual point of disagreement and what each side believes is at stake. Do not write empty placeholders such as supporters say this protects rights, critics say the court overstepped, supporters approve, or critics disagree.
Where possible, anchor each perspective to the specific legal principle, policy tradeoff, economic consequence, institutional concern, public-interest goal, or practical risk described in the supplied article.
Do not create false balance around established facts. Leave both perspective fields blank only for clearly noncontroversial stories such as routine sports results, rescues, or straightforward discoveries.

UNCERTAINTY AND CONFIDENCE
uncertain is optional. Use one short sentence only when a meaningful fact, consequence, attribution, or next step remains unresolved. Otherwise return an empty string.
confidence must be Confirmed, Developing, Disputed, or Reported.

QUALITY CHECK
Before returning the JSON, verify for every story:
1. A reader can identify what specifically happened.
2. why_it_matters explains a consequence unique to that story.
3. Any perspectives describe a substantive disagreement rather than generic approval and opposition.
4. No unsupported detail was added.
5. Every original story and required key is present.

Stories: '''

updated = source[:content_start] + prompt + source[end:]
compile(updated, 'generate_brief.py', 'exec')
path.write_text(updated)
print('Upgraded summary depth, Why It Matters specificity, and perspective substance. Python syntax validated.')
