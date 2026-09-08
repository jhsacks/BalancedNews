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
def blocked_image(url):
 if not url: return True
 low=url.lower()
 blocked_hosts=('news.google.com','googleusercontent.com','gstatic.com','google.com')
 blocked_words=('logo','icon','favicon','sprite','branding','placeholder','default-image')
 return any(h in low for h in blocked_hosts) or any(w in low for w in blocked_words)

def extract_publisher_url(entry, feed_url):
 """Return the publisher article URL when an aggregator exposes one."""
 candidates=[]
 source=entry.get('source') or {}
 if isinstance(source,dict) and source.get('href'): candidates.append(source.get('href'))
 for link in entry.get('links',[]):
  href=link.get('href','') if isinstance(link,dict) else ''
  if href: candidates.append(href)
 candidates.append(entry.get('link',''))
 # First accept any already-direct article URL.
 for url in candidates:
  if url and 'news.google.com' not in url and not url.rstrip('/').endswith(('.com','.org','.net','.gov','.edu')):
   return url
 # For Google News, inspect the landing page for a non-Google canonical/article link.
 google_url=entry.get('link','')
 if google_url and 'news.google.com' in google_url:
  try:
   r=requests.get(google_url,timeout=10,headers={'User-Agent':'Mozilla/5.0'},allow_redirects=True)
   if r.url and 'news.google.com' not in r.url: return r.url
   soup=BeautifulSoup(r.text,'html.parser')
   selectors=[('link',{'rel':'canonical'}),('meta',{'property':'og:url'}),('a',{})]
   for tag,attrs in selectors:
    for node in soup.find_all(tag,attrs=attrs):
     url=node.get('href') or node.get('content') or ''
     if url.startswith('http') and all(h not in url.lower() for h in ('google.com','gstatic.com','googleusercontent.com')):
      return url
  except Exception:
   pass
 return ''

def get_image(entry,url):
 """Use a real publisher image only; never use Google or branding art."""
 for key in ('media_content','media_thumbnail'):
  values=entry.get(key,[])
  for value in values:
   candidate=value.get('url','')
   if not blocked_image(candidate): return candidate
 try:
  r=requests.get(url,timeout=10,headers={'User-Agent':'Mozilla/5.0 BalancedBrief/3.0'},allow_redirects=True)
  if not r.ok: return ''
  soup=BeautifulSoup(r.text,'html.parser')
  for tag in [soup.find('meta',property='og:image'),soup.find('meta',attrs={'name':'twitter:image'}),soup.find('meta',attrs={'name':'twitter:image:src'})]:
   candidate=tag.get('content','') if tag else ''
   if not blocked_image(candidate): return candidate
  # Last article-page fallback: first substantial content image, not a site logo.
  for img in soup.find_all('img'):
   candidate=img.get('src') or img.get('data-src') or img.get('data-lazy-src') or ''
   if candidate.startswith('//'): candidate='https:'+candidate
   if candidate.startswith('/'):
    from urllib.parse import urljoin
    candidate=urljoin(r.url,candidate)
   width=str(img.get('width','')); height=str(img.get('height',''))
   alt=(img.get('alt') or '').lower()
   if candidate.startswith('http') and not blocked_image(candidate) and 'logo' not in alt:
    if (width.isdigit() and int(width)>=300) or not width:
     return candidate
 except Exception:
  pass
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
  url=extract_publisher_url(e,feed['url']) or e.get('link',''); headline=clean(e.get('title','')); summary=clean(e.get('summary',''))[:800]; dt,raw=pub_dt(e)
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
with_real_images=[]
for x in chosen:
 entry=x.pop('_entry')
 x['image']=get_image(entry,x['url'])
 if x['image'] and not blocked_image(x['image']):
  if x['source'].startswith('Google News:'):
   src=entry.get('source') or {}
   if isinstance(src,dict) and src.get('title'): x['source']=src['title']
  with_real_images.append(x)
chosen=with_real_images
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
