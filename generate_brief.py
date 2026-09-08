import os,re,json,html as hm,io
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
import feedparser,requests
from bs4 import BeautifulSoup
from PIL import Image,ImageStat
ROOT=Path(__file__).parent; CFG=json.loads((ROOT/'config.json').read_text()); DATA=ROOT/'data/briefings'; DATA.mkdir(parents=True,exist_ok=True)
TZ=ZoneInfo(CFG['timezone']); now=datetime.now(TZ); edition=os.getenv('BRIEF_EDITION') or ('AM' if now.hour<12 else 'PM')
def clean(v): return re.sub(r'\s+',' ',BeautifulSoup(hm.unescape(v or ''),'html.parser').get_text(' ',strip=True)).strip()
def pdate(e):
 raw=e.get('published','') or e.get('updated','')
 try:
  d=parsedate_to_datetime(raw); return (d.replace(tzinfo=TZ) if d.tzinfo is None else d).astimezone(TZ),raw
 except:return now,raw
def bad_url(u):
 low=(u or '').lower(); return not u or any(x in low for x in ('google.com','gstatic.com','googleusercontent.com','logo','icon','favicon','sprite','branding','placeholder','avatar','profile'))
def good_image(u):
 if bad_url(u): return False
 try:
  r=requests.get(u,timeout=8,headers={'User-Agent':'Mozilla/5.0'}); im=Image.open(io.BytesIO(r.content)).convert('RGB'); w,h=im.size
  if not r.ok or len(r.content)<12000 or w<320 or h<160 or w/h>3.4 or w/h<.65:return False
  q=im.resize((64,64)).quantize(colors=32); colors=len(q.getcolors() or []); stat=ImageStat.Stat(im.resize((64,64)))
  return colors>5 and not (sum(stat.mean)/3>220 and sum(stat.stddev)/3<48)
 except:return False
def image(e,u):
 candidates=[]
 for k in ('media_content','media_thumbnail'):
  candidates += [x.get('url','') for x in e.get(k,[])]
 try:
  r=requests.get(u,timeout=8,headers={'User-Agent':'Mozilla/5.0'},allow_redirects=True); soup=BeautifulSoup(r.text,'html.parser')
  for t in (soup.find('meta',property='og:image'),soup.find('meta',attrs={'name':'twitter:image'})):
   if t:candidates.append(t.get('content',''))
 except:pass
 return next((x for x in candidates if good_image(x)),'')
def score(x):
 t=(x['headline']+' '+x['summary']).lower(); return sum(3 for k in CFG['importance_keywords'] if k in t)+7*any(k in t for k in CFG['sports_keywords'])+2
cut=now-timedelta(hours=30 if edition=='AM' else 14); items=[]
for f in CFG['feeds']:
 d=feedparser.parse(f['url'])
 for e in d.entries[:30]:
  dt,raw=pdate(e); u=e.get('link',''); h=clean(e.get('title','')); sm=clean(e.get('summary',''))[:900]
  if not u or not h or dt<cut:continue
  x={'headline':h,'summary':sm,'why_it_matters':'','url':u,'source':f['name'],'published':raw,'category':f['category'],'confidence':'Reported','image':'','perspective_one':'','perspective_two':'','uncertain':'','_entry':e}; x['_score']=score(x); items.append(x)
ranked=sorted(items,key=lambda x:(x['_score'],x['published']),reverse=True); chosen=[]; seen=set(); counts={}
for cat in CFG['category_order']:
 for x in ranked:
  k=re.sub('[^a-z0-9]','',x['headline'].lower())[:90]
  if x['category']==cat and k not in seen: seen.add(k);chosen.append(x);counts[cat]=1;break
for x in ranked:
 k=re.sub('[^a-z0-9]','',x['headline'].lower())[:90]
 if k in seen or x['_score']<2 or counts.get(x['category'],0)>=CFG['max_per_category']:continue
 seen.add(k);chosen.append(x);counts[x['category']]=counts.get(x['category'],0)+1
 if len(chosen)>=CFG['max_stories']:break
for x in chosen:x['image']=image(x.pop('_entry'),x['url'])
key=os.getenv('OPENAI_API_KEY','').strip()
if key and chosen:
 try:
  from openai import OpenAI
  raw=json.dumps([{k:v for k,v in x.items() if not k.startswith('_')} for x in chosen])
  prompt='''Return JSON only as one flat array. Keep every supplied story exactly once. Preserve URL, source, published, image, and category EXACTLY. Never rename categories or create Top Stories. Never invent facts. Clean each headline. For EVERY story, write summary as exactly 2 concise sentences totaling 45-75 words and why_it_matters as exactly 1 sentence under 28 words. Only for materially controversial stories, write perspective_one and perspective_two as one sentence each under 30 words, and uncertain as one sentence under 25 words. Otherwise leave those three blank. Do not manufacture false balance. Distinguish governments, organizations, civilians, and populations. Confidence must be Confirmed, Developing, Disputed, or Reported. Stories: '''+raw
  txt=OpenAI(api_key=key).responses.create(model=os.getenv('OPENAI_MODEL','gpt-4.1-mini'),input=prompt).output_text.strip().removeprefix('```json').removesuffix('```').strip(); chosen=json.loads(txt)
 except Exception as e:print('AI refinement skipped:',e)
for x in chosen:x.pop('_score',None)
out={'generated_at':now.isoformat(),'edition':edition,'stories':chosen}; name=f"{now:%Y-%m-%d}_{edition}.json";(DATA/name).write_text(json.dumps(out,indent=2));print(name,len(chosen))
