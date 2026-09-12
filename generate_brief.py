import os, re, json, html as hm, io
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse
import feedparser, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
from PIL import Image, ImageStat
from topic_images import topic_image

ROOT=Path(__file__).parent; CFG=json.loads((ROOT/'config.json').read_text()); DATA=ROOT/'data/briefings'; DATA.mkdir(parents=True,exist_ok=True)
TZ=ZoneInfo(CFG['timezone']); now=datetime.now(TZ); edition=os.getenv('BRIEF_EDITION') or ('AM' if now.hour<12 else 'PM'); HEADERS={'User-Agent':'Mozilla/5.0'}
def clean(v): return re.sub(r'\s+',' ',BeautifulSoup(hm.unescape(v or ''),'html.parser').get_text(' ',strip=True)).strip()
def pdate(e):
 raw=e.get('published','') or e.get('updated','') or e.get('created','')
 try:
  d=parsedate_to_datetime(raw); return (d.replace(tzinfo=TZ) if d.tzinfo is None else d).astimezone(TZ),raw
 except Exception:return None,raw
def url_date(u):
 m=re.search(r'/(20\d{2})/(0?[1-9]|1[0-2])(?:/(0?[1-9]|[12]\d|3[01]))?/',urlparse(u or '').path)
 if not m:return None
 try:return datetime(int(m.group(1)),int(m.group(2)),int(m.group(3) or 1),tzinfo=TZ)
 except ValueError:return None
def fresh(u,d,category):
 cutoff=now-timedelta(days=4) if category=='Good News' else now-timedelta(hours=36 if edition=='AM' else 18)
 dated=url_date(u)
 if dated and dated < now-timedelta(days=CFG.get('max_article_age_days',14)):return False
 return bool(d and d>=cutoff)
def valid_image(u):
 if not u or any(x in u.lower() for x in ('gstatic','googleusercontent','logo','icon','favicon','placeholder','avatar')):return False
 try:
  r=requests.get(u,timeout=8,headers=HEADERS); r.raise_for_status(); im=Image.open(io.BytesIO(r.content)).convert('RGB'); w,h=im.size
  if len(r.content)<9000 or w<300 or h<150 or w/h>3.8 or w/h<.58:return False
  q=im.resize((64,64)).quantize(colors=32); stat=ImageStat.Stat(im.resize((64,64)))
  return len(q.getcolors() or [])>5 and not(sum(stat.mean)/3>225 and sum(stat.stddev)/3<42)
 except Exception:return False
def find_image(e,u):
 c=[]
 for k in ('media_content','media_thumbnail'):c += [x.get('url','') for x in e.get(k,[]) if isinstance(x,dict)]
 for field in ('summary','description','content'):
  v=e.get(field,''); v=' '.join(str(x.get('value','')) for x in v if isinstance(x,dict)) if isinstance(v,list) else str(v)
  c += [urljoin(u,t.get('src','')) for t in BeautifulSoup(v,'html.parser').find_all('img')]
 try:
  r=requests.get(u,timeout=10,headers=HEADERS,allow_redirects=True); soup=BeautifulSoup(r.text,'html.parser')
  for t in (soup.find('meta',property='og:image'),soup.find('meta',property='og:image:url'),soup.find('meta',attrs={'name':'twitter:image'})):
   if t:c.append(urljoin(r.url,t.get('content','')))
  c += [urljoin(r.url,t.get('src','')) for t in soup.select('article img, main img')[:10]]
 except Exception:pass
 return next((x for x in dict.fromkeys(c) if valid_image(x)),'')
def tokens(text):
 stop={'the','and','for','with','from','that','this','into','after','before','over','about','says','latest','update','news','report','reports','announces','announce','today','live','analysis','why','how','what'}
 return {x for x in re.findall(r'[a-z0-9]+',text.lower()) if len(x)>2 and x not in stop}
def headline_key(text):
 return ' '.join(sorted(tokens(text)))
def same_story(a,b):
 ah=a.get('headline','');bh=b.get('headline','')
 at=tokens(ah);bt=tokens(bh)
 if not at or not bt:return False
 containment=len(at&bt)/max(1,min(len(at),len(bt)))
 union=len(at&bt)/max(1,len(at|bt))
 seq=SequenceMatcher(None,headline_key(ah),headline_key(bh)).ratio()
 # Same event when headlines substantially share the same people/teams, action, and object.
 if containment>=.55 or union>=.42 or seq>=.72:return True
 # Use summaries only as a supporting signal, never by themselves.
 ast=tokens(a.get('summary','')[:260]);bst=tokens(b.get('summary','')[:260])
 summary_overlap=len(ast&bst)/max(1,min(len(ast),len(bst))) if ast and bst else 0
 return containment>=.38 and summary_overlap>=.48
def duplicate(x,selected):return any(same_story(x,y) for y in selected)
def score(x):
 text=(x['headline']+' '+x['summary']).lower(); return 2+sum(3 for k in CFG['importance_keywords'] if k in text)+7*any(k in text for k in CFG['sports_keywords'])
def cap(cat):return CFG.get('category_limits',{}).get(cat,CFG['max_per_category'])

old_good=[]; history=now-timedelta(days=CFG.get('good_news_history_days',14))
for p in DATA.glob('*.json'):
 try:
  b=json.loads(p.read_text()); d=datetime.fromisoformat(b['generated_at'])
  if d>=history:old_good += [s for s in b.get('stories',[]) if s.get('category')=='Good News']
 except Exception:pass
def repeated_good(x):return x['category']=='Good News' and any(x.get('url')==y.get('url') or same_story(x,y) for y in old_good)
items=[]
def load_feed(feed):
 try:
  response=requests.get(feed['url'],headers=HEADERS,timeout=10)
  response.raise_for_status()
  parsed=feedparser.parse(response.content)
 except Exception as e:
  print(f"Feed skipped: {feed['name']}: {e}")
  return []
 loaded=[]
 for entry in parsed.entries[:CFG.get('entries_per_feed',30)]:
  d,raw=pdate(entry);u=entry.get('link','');h=clean(entry.get('title',''));sm=clean(entry.get('summary',''))[:900]
  if not u or not h or not fresh(u,d,feed['category']):continue
  x={'headline':h,'summary':sm,'why_it_matters':'','url':u,'source':feed['name'],'published':raw,'category':feed['category'],'confidence':'Reported','image':'','perspective_one':'','perspective_two':'','uncertain':'','_entry':entry}
  x['_score']=score(x);loaded.append(x)
 return loaded
with ThreadPoolExecutor(max_workers=CFG.get('feed_workers',8)) as pool:
 futures=[pool.submit(load_feed,feed) for feed in CFG['feeds']]
 for future in as_completed(futures):items.extend(future.result())
ranked=sorted(items,key=lambda x:(x['_score'],x['published']),reverse=True); chosen=[]
counts={}
source_counts={}
team_counts={}

TEAM_PATTERNS={
 'atlanta hawks': r'\b(?:atlanta\s+)?hawks\b',
 'atlanta braves': r'\b(?:atlanta\s+)?braves\b',
 'atlanta falcons': r'\b(?:atlanta\s+)?falcons\b',
 'atlanta united': r'\batlanta\s+united\b',
 'georgia bulldogs': r'\b(?:georgia\s+bulldogs|uga|bulldogs)\b',
 'indiana hoosiers': r'\b(?:indiana\s+hoosiers|hoosiers)\b',
 'wisconsin badgers': r'\b(?:wisconsin\s+badgers|badgers)\b'
}

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
 category_candidates=[story for story in ranked if story.get('category')==category]
 category_target=CFG.get('category_targets',{}).get(category,CFG.get('default_category_target',1))
 category_max=CFG.get('category_limits',{}).get(category,CFG.get('max_per_category',2))
 target=max(1,min(category_target,category_max))
 for story in category_candidates:
  if counts.get(category,0)>=target:break
  if repeated_good(story) if 'repeated_good' in globals() else repeated_good_news(story) if 'repeated_good_news' in globals() else False:continue
  if any(same_story(story, selected) for selected in chosen):continue
  if not team_allowed(story):continue
  if not source_allowed(story,category_pass=(counts.get(category,0)==0)):continue
  add_story(story)

# Large-news-day expansion is category-local. A quiet Sports section cannot suppress major World or U.S. coverage.
for category in CFG['category_order']:
 category_candidates=[story for story in ranked if story.get('category')==category]
 category_max=CFG.get('category_limits',{}).get(category,CFG.get('max_per_category',2))
 for story in category_candidates:
  if counts.get(category,0)>=category_max:break
  if repeated_good(story) if 'repeated_good' in globals() else repeated_good_news(story) if 'repeated_good_news' in globals() else False:continue
  if any(same_story(story, selected) for selected in chosen):continue
  if not team_allowed(story) or not source_allowed(story):continue
  add_story(story)

selected_urls={x['url'] for x in chosen}; more={c:[] for c in CFG['category_order']}
for x in ranked:
 if x['url'] in selected_urls or repeated_good(x) or len(more[x['category']])>=CFG['more_links_per_category'] or duplicate(x,chosen+more[x['category']]):continue
 more[x['category']].append({'headline':x['headline'],'url':x['url'],'source':x['source'],'summary':x['summary']})
def attach_image(story):
 entry=story.pop('_entry');story['image']=find_image(entry,story['url']);story['image_credit']='';story['image_source']=''
 if not story['image']:
  fallback=topic_image(story['headline'],story['category'],HEADERS)
  if fallback:
   story['image']=fallback['url'];story['image_credit']=fallback['credit'];story['image_source']=fallback['source']
 return story
with ThreadPoolExecutor(max_workers=CFG.get('image_workers',6)) as pool:
 chosen=list(pool.map(attach_image,chosen))
key=os.getenv('OPENAI_API_KEY','').strip()
if key and chosen:
 try:
  from openai import OpenAI
  payload=json.dumps([{k:v for k,v in x.items() if not k.startswith('_')} for x in chosen])
  prompt='''Return only a valid JSON array containing every supplied story exactly once and every original key. Preserve URL, source, published, image, category, image_credit, and image_source exactly when those keys are present. Never invent facts. Never return markdown.

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

Stories: '''+payload
  text=OpenAI(api_key=key).responses.create(model=os.getenv('OPENAI_MODEL','gpt-4.1-mini'),input=prompt).output_text.strip().removeprefix('```json').removesuffix('```').strip(); result=json.loads(text)
  if isinstance(result,list) and len(result)==len(chosen):chosen=result
 except Exception as e:print('AI refinement skipped:',e)
for x in chosen:x.pop('_score',None)
out={'generated_at':now.isoformat(),'edition':edition,'stories':chosen,'more_stories':more}; name=f"{now:%Y-%m-%d}_{edition}.json";(DATA/name).write_text(json.dumps(out,indent=2));print(name,len(chosen))
