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
from image_engine import best_image

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
 return best_image(e,u,HEADERS)
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
def repeated_good(x):return x['category']=='Good News' and any(x.get('url')==y.get('url') or similar(x,y) for y in old_good)
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
ranked=sorted(items,key=lambda x:(x['_score'],x['published']),reverse=True); chosen=[]; counts={}
for cat in CFG['category_order']:
 for x in ranked:
  if x['category']==cat and not repeated_good(x) and not duplicate(x,chosen):chosen.append(x);counts[cat]=1;break
for x in ranked:
 if len(chosen)>=CFG['max_stories']:break
 if counts.get(x['category'],0)>=cap(x['category']) or repeated_good(x) or duplicate(x,chosen):continue
 chosen.append(x);counts[x['category']]=counts.get(x['category'],0)+1
selected_urls={x['url'] for x in chosen}; more={c:[] for c in CFG['category_order']}
for x in ranked:
 if x['url'] in selected_urls or repeated_good(x) or len(more[x['category']])>=CFG['more_links_per_category'] or duplicate(x,chosen+more[x['category']]):continue
 more[x['category']].append({'headline':x['headline'],'url':x['url'],'source':x['source'],'summary':x['summary']})
def attach_image(story):
 entry=story.pop('_entry');story['image']=find_image(entry,story['url']);return story
with ThreadPoolExecutor(max_workers=CFG.get('image_workers',6)) as pool:
 chosen=list(pool.map(attach_image,chosen))
key=os.getenv('OPENAI_API_KEY','').strip()
if key and chosen:
 try:
  from openai import OpenAI
  payload=json.dumps([{k:v for k,v in x.items() if not k.startswith('_')} for x in chosen])
  prompt='''Return only a JSON array with every supplied story exactly once. Preserve URL, source, published, image, and category exactly. Write for readers with dyslexia: common words, active voice, one idea per sentence. Summary must be exactly two short sentences totaling 24-40 words. why_it_matters must be one sentence under 18 words. For anything remotely controversial, including politics, policy, courts, war, diplomacy, policing, identity, religion, health policy, economic policy, climate, education, labor, corporate power, technology risks, or fairness, perspective_one and perspective_two are REQUIRED. Each is one distinct good-faith view in 10-20 plain words. Do not create false balance about established facts. For clearly noncontroversial stories, leave both blank. uncertain is one short sentence only when a key fact is unresolved. confidence is Confirmed, Developing, Disputed, or Reported. Include every key for every story. Stories: '''+payload
  text=OpenAI(api_key=key).responses.create(model=os.getenv('OPENAI_MODEL','gpt-4.1-mini'),input=prompt).output_text.strip().removeprefix('```json').removesuffix('```').strip(); result=json.loads(text)
  if isinstance(result,list) and len(result)==len(chosen):chosen=result
 except Exception as e:print('AI refinement skipped:',e)
for x in chosen:x.pop('_score',None)
out={'generated_at':now.isoformat(),'edition':edition,'stories':chosen,'more_stories':more}; name=f"{now:%Y-%m-%d}_{edition}.json";(DATA/name).write_text(json.dumps(out,indent=2));print(name,len(chosen))
