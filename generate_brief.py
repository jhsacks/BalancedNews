import os, re, json, html as hm, io
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse
import feedparser, requests
from bs4 import BeautifulSoup
from PIL import Image, ImageStat

ROOT=Path(__file__).parent
CFG=json.loads((ROOT/'config.json').read_text())
DATA=ROOT/'data/briefings'; DATA.mkdir(parents=True,exist_ok=True)
TZ=ZoneInfo(CFG['timezone']); now=datetime.now(TZ)
edition=os.getenv('BRIEF_EDITION') or ('AM' if now.hour<12 else 'PM')
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; BalancedBrief/1.0)'}

def clean(v): return re.sub(r'\s+',' ',BeautifulSoup(hm.unescape(v or ''),'html.parser').get_text(' ',strip=True)).strip()

def pdate(e):
 raw=e.get('published','') or e.get('updated','') or e.get('created','')
 try:
  d=parsedate_to_datetime(raw)
  return (d.replace(tzinfo=TZ) if d.tzinfo is None else d).astimezone(TZ),raw
 except Exception: return None,raw

def date_in_url(u):
 path=urlparse(u or '').path
 m=re.search(r'/(20\d{2})/(0?[1-9]|1[0-2])(?:/(0?[1-9]|[12]\d|3[01]))?/',path)
 if not m:return None
 try:return datetime(int(m.group(1)),int(m.group(2)),int(m.group(3) or 1),tzinfo=TZ)
 except ValueError:return None

def is_fresh(u,feed_date):
 limit=now-timedelta(days=CFG.get('max_article_age_days',14))
 url_date=date_in_url(u)
 if url_date and url_date<limit:return False
 return bool(feed_date and feed_date>=now-timedelta(hours=36 if edition=='AM' else 18))

def bad_url(u):
 low=(u or '').lower()
 return not u or any(x in low for x in ('gstatic.com','googleusercontent.com','logo','icon','favicon','sprite','branding','placeholder','avatar','profile'))

def good_image(u):
 if bad_url(u):return False
 try:
  r=requests.get(u,timeout=8,headers=HEADERS); r.raise_for_status()
  im=Image.open(io.BytesIO(r.content)).convert('RGB'); w,h=im.size
  if len(r.content)<9000 or w<300 or h<150 or w/h>3.8 or w/h<.58:return False
  q=im.resize((64,64)).quantize(colors=32); colors=len(q.getcolors() or [])
  stat=ImageStat.Stat(im.resize((64,64)))
  return colors>5 and not (sum(stat.mean)/3>225 and sum(stat.stddev)/3<42)
 except Exception:return False

def image(e,u):
 candidates=[]
 for k in ('media_content','media_thumbnail'):
  candidates += [x.get('url','') for x in e.get(k,[]) if isinstance(x,dict)]
 for enclosure in e.get('enclosures',[]):
  if isinstance(enclosure,dict) and str(enclosure.get('type','')).startswith('image'):
   candidates.append(enclosure.get('href','') or enclosure.get('url',''))
 for field in ('summary','description','content'):
  value=e.get(field,'')
  if isinstance(value,list):value=' '.join(str(x.get('value','')) for x in value if isinstance(x,dict))
  soup=BeautifulSoup(str(value),'html.parser')
  candidates += [urljoin(u,t.get('src','')) for t in soup.find_all('img')]
 try:
  r=requests.get(u,timeout=10,headers=HEADERS,allow_redirects=True)
  soup=BeautifulSoup(r.text,'html.parser')
  for t in (soup.find('meta',property='og:image'),soup.find('meta',property='og:image:url'),soup.find('meta',attrs={'name':'twitter:image'}),soup.find('meta',attrs={'name':'twitter:image:src'})):
   if t:candidates.append(urljoin(r.url,t.get('content','')))
  candidates += [urljoin(r.url,t.get('src','')) for t in soup.select('article img, main img')[:10]]
 except Exception:pass
 for candidate in dict.fromkeys(x for x in candidates if x):
  if good_image(candidate):return candidate
 return ''

def words(text):
 stop={'the','a','an','and','or','of','to','in','on','for','with','from','at','by','is','are','was','were','as','after','before','over','about','new','says','say','latest','update'}
 return {w for w in re.findall(r'[a-z0-9]+',text.lower()) if len(w)>2 and w not in stop}

def redundant(x,selected):
 a=words(x['headline']+' '+x.get('summary','')[:180])
 for y in selected:
  b=words(y['headline']+' '+y.get('summary','')[:180])
  overlap=len(a&b)/max(1,min(len(a),len(b)))
  if overlap>=.52:return True
 return False

def score(x):
 t=(x['headline']+' '+x['summary']).lower()
 return 2+sum(3 for k in CFG['importance_keywords'] if k in t)+7*any(k in t for k in CFG['sports_keywords'])

def limit(cat):return CFG.get('category_limits',{}).get(cat,CFG['max_per_category'])

items=[]
for f in CFG['feeds']:
 d=feedparser.parse(f['url'])
 for e in d.entries[:35]:
  dt,raw=pdate(e); u=e.get('link',''); h=clean(e.get('title','')); sm=clean(e.get('summary',''))[:800]
  if not u or not h or not is_fresh(u,dt):continue
  x={'headline':h,'summary':sm,'why_it_matters':'','url':u,'source':f['name'],'published':raw,'category':f['category'],'confidence':'Reported','image':'','perspective_one':'','perspective_two':'','uncertain':'','_entry':e}
  x['_score']=score(x); items.append(x)
ranked=sorted(items,key=lambda x:(x['_score'],x['published']),reverse=True)
chosen=[]; counts={}
# Guarantee breadth first, but never force a weak or duplicate article.
for cat in CFG['category_order']:
 for x in ranked:
  if x['category']==cat and counts.get(cat,0)<limit(cat) and not redundant(x,chosen):
   chosen.append(x); counts[cat]=1; break
for x in ranked:
 if len(chosen)>=CFG['max_stories']:break
 if counts.get(x['category'],0)>=limit(x['category']) or redundant(x,chosen):continue
 chosen.append(x); counts[x['category']]=counts.get(x['category'],0)+1
chosen_ids={x['url'] for x in chosen}
more={cat:[] for cat in CFG['category_order']}
for x in ranked:
 if x['url'] in chosen_ids or len(more.get(x['category'],[]))>=CFG.get('more_links_per_category',3):continue
 if redundant(x,chosen+more.get(x['category'],[])):continue
 more.setdefault(x['category'],[]).append({'headline':x['headline'],'url':x['url'],'source':x['source']})
for x in chosen:x['image']=image(x.pop('_entry'),x['url'])
key=os.getenv('OPENAI_API_KEY','').strip()
if key and chosen:
 try:
  from openai import OpenAI
  raw=json.dumps([{k:v for k,v in x.items() if not k.startswith('_')} for x in chosen])
  prompt='''Return JSON only as one flat array. Keep every supplied story exactly once and preserve URL, source, published, image, and category exactly. Never invent facts.
For every story, write a two-sentence summary of 24-40 words and one Why It Matters sentence under 18 words. Use short, common words, active voice, and one idea per sentence for readers with dyslexia.
Treat a story as controversial whenever reasonable people may disagree about policy, politics, courts, war, diplomacy, policing, identity, religion, public health, economics, climate, education, labor, corporate power, technology risks, or fairness. For every such story, ALWAYS fill perspective_one and perspective_two. Each must be one distinct, good-faith perspective in 10-20 plain words. Do not label parties as good or bad and do not create false balance about established facts. For noncontroversial stories, leave both blank. Use uncertain only if an important fact is unresolved. Confidence must be Confirmed, Developing, Disputed, or Reported. Return all keys for every story. Stories: '''+raw
  txt=OpenAI(api_key=key).responses.create(model=os.getenv('OPENAI_MODEL','gpt-4.1-mini'),input=prompt).output_text.strip().removeprefix('```json').removesuffix('```').strip()
  ai=json.loads(txt)
  if isinstance(ai,list) and len(ai)==len(chosen):chosen=ai
 except Exception as e:print('AI refinement skipped:',e)
for x in chosen:
 x.pop('_score',None); x.pop('_entry',None)
out={'generated_at':now.isoformat(),'edition':edition,'stories':chosen,'more_stories':more}
name=f"{now:%Y-%m-%d}_{edition}.json";(DATA/name).write_text(json.dumps(out,indent=2));print(name,len(chosen))
