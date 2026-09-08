import os,re,json,html as htmlmod
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
import feedparser,requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).parent; CFG=json.loads((ROOT/'config.json').read_text()); DATA=ROOT/'data/briefings'; DATA.mkdir(parents=True,exist_ok=True)
TZ=ZoneInfo(CFG['timezone']); now=datetime.now(TZ); edition=os.getenv('BRIEF_EDITION') or ('AM' if now.hour<12 else 'PM')
previous_urls=set()
for p in sorted(DATA.glob('*.json'),reverse=True)[:3]:
 try: previous_urls.update(x.get('url','') for x in json.loads(p.read_text()).get('stories',[]))
 except: pass

def clean(v):
 return re.sub(r'\s+',' ',BeautifulSoup(htmlmod.unescape(v or ''),'html.parser').get_text(' ',strip=True)).strip()
def pub_dt(e):
 raw=e.get('published','') or e.get('updated','')
 try:
  d=parsedate_to_datetime(raw)
  if d.tzinfo is None: d=d.replace(tzinfo=TZ)
  return d.astimezone(TZ),raw
 except: return now,raw
def get_image(e,url):
 for k in ('media_content','media_thumbnail'):
  v=e.get(k,[])
  if v and v[0].get('url'): return v[0]['url']
 try:
  r=requests.get(url,timeout=5,headers={'User-Agent':'Mozilla/5.0 BalancedBrief/2.0'})
  if r.ok:
   s=BeautifulSoup(r.text,'html.parser'); t=s.find('meta',property='og:image') or s.find('meta',attrs={'name':'twitter:image'})
   if t: return t.get('content','')
 except: pass
 return ''
def relevance(x):
 t=(x['headline']+' '+x['summary']).lower(); n=0
 n+=sum(3 for k in CFG['importance_keywords'] if k in t)
 n+=7 if any(k in t for k in CFG['sports_keywords']) else 0
 n+=2 if x['category'] in ('U.S. Government & Politics','International Affairs','Conflicts & Security','Israel / Palestinian Territories','Healthcare & Medicine') else 0
 n-=6 if any(k in t for k in ('celebrity','royal family','fashion','recipe','quiz','lottery')) else 0
 return n
cutoff=now-timedelta(hours=28 if edition=='AM' else 12)
items=[]
for feed in CFG['feeds']:
 d=feedparser.parse(feed['url'])
 for e in d.entries[:35]:
  url=e.get('link',''); headline=clean(e.get('title','')); summary=clean(e.get('summary',''))[:800]; dt,raw=pub_dt(e)
  if not url or not headline or dt<cutoff: continue
  if edition=='PM' and url in previous_urls: continue
  x={'headline':headline,'summary':summary,'url':url,'source':feed['name'],'published':raw,'category':feed['category'],'confidence':'Reported','image':'','perspective_one':'','perspective_two':'','uncertain':''}
  x['_score']=relevance(x); x['_entry']=e; items.append(x)
seen=set(); counts={}; chosen=[]
for x in sorted(items,key=lambda z:(z['_score'],z['published']),reverse=True):
 key=re.sub('[^a-z0-9]','',x['headline'].lower())[:90]
 if key in seen or x['_score']<2 or counts.get(x['category'],0)>=CFG['max_per_category']: continue
 seen.add(key); counts[x['category']]=counts.get(x['category'],0)+1; chosen.append(x)
 if len(chosen)>=CFG['max_stories']: break
for x in chosen: x['image']=get_image(x.pop('_entry'),x['url'])
key=os.getenv('OPENAI_API_KEY','').strip()
if key and chosen:
 try:
  from openai import OpenAI
  client=OpenAI(api_key=key)
  payload=json.dumps([{k:v for k,v in x.items() if k!='_score'} for x in chosen],ensure_ascii=False)
  rules='''You edit a moderate, evidence-weighted executive briefing. Return JSON only, using the same array and keys. Preserve URL, source, published, image, and category exactly. Do not invent, infer, or embellish facts. Keep only consequential stories and rank the most consequential first.

HEADLINE: Rewrite each headline in calm, precise, non-sensational language.

SUMMARY: Write a useful central account of 3 to 5 complete sentences, approximately 90 to 150 words when the supplied material supports that length. Start with the established event, then explain why it matters and the relevant context. Attribute allegations, disputed claims, forecasts, and partisan interpretations. If the supplied source material is too thin for a responsible longer summary, remain shorter rather than adding unsupported detail.

BALANCE: For genuinely controversial stories, fill perspective_one with 2 to 3 sentences presenting the strongest materially relevant argument or interpretation from one side, and perspective_two with 2 to 3 sentences presenting the strongest competing argument or interpretation. Fill uncertain with 1 to 2 sentences identifying unresolved facts or limitations. Do not manufacture false balance, treat unsupported claims as facts, or legitimize dehumanizing claims. Distinguish governments, parties, armed organizations, institutions, civilians, and populations. For Israel and Palestinian coverage, never treat one actor as speaking for all Israelis or all Palestinians.

SOURCE LINK: The preserved URL is the article button shown to the reader. Favor a straight-news, fact-centered article already present in the supplied candidates, rather than an opinion or analysis item. Do not label an outlet politically and do not claim ideological neutrality.

CONFIDENCE: Use Confirmed, Developing, Disputed, or Reported. Add Understanding the Story only when supplied facts support a genuinely useful explainer. Add Worth Watching only for a consequential emerging development. Stories: '''
  res=client.responses.create(model=os.getenv('OPENAI_MODEL','gpt-4.1-mini'),input=rules+payload)
  text=res.output_text.strip().removeprefix('```json').removesuffix('```').strip(); chosen=json.loads(text)
 except Exception as ex: print('AI refinement skipped:',ex)
for x in chosen: x.pop('_score',None)
out={'generated_at':now.isoformat(),'edition':edition,'stories':chosen}; name=f"{now.strftime('%Y-%m-%d')}_{edition}.json"; (DATA/name).write_text(json.dumps(out,indent=2,ensure_ascii=False)); print(name,len(chosen))
