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
  d=parsedate_to_datetime(raw); return (d.replace(tzinfo=TZ) if d.tzinfo is None else d).astimezone(TZ),raw
 except Exception:return None,raw
def url_date(u):
 m=re.search(r'/(20\d{2})/(0?[1-9]|1[0-2])(?:/(0?[1-9]|[12]\d|3[01]))?/',urlparse(u or '').path)
 if not m:return None
 try:return datetime(int(m.group(1)),int(m.group(2)),int(m.group(3) or 1),tzinfo=TZ)
 except ValueError:return None
def fresh(u,d,category):
 days=CFG.get('good_news_lookback_days',7) if category=='Good News' else None
 cutoff=now-timedelta(days=days) if days else now-timedelta(hours=CFG.get('am_lookback_hours',30) if edition=='AM' else CFG.get('pm_lookback_hours',18))
 dated=url_date(u)
 if dated and dated<now-timedelta(days=CFG.get('max_article_age_days',14)):return False
 return bool(d and d>=cutoff)
def valid_image(u):
 if not u or any(x in u.lower() for x in ('gstatic','googleusercontent','logo','icon','favicon','placeholder','avatar','sprite')):return False
 try:
  r=requests.get(u,timeout=8,headers=HEADERS);r.raise_for_status();im=Image.open(io.BytesIO(r.content)).convert('RGB');w,h=im.size
  if len(r.content)<7000 or w<280 or h<140 or w/h>4.0 or w/h<.55:return False
  q=im.resize((64,64)).quantize(colors=32);stat=ImageStat.Stat(im.resize((64,64)))
  return len(q.getcolors() or [])>5 and not(sum(stat.mean)/3>228 and sum(stat.stddev)/3<38)
 except Exception:return False
def find_image(e,u):
 c=[]
 for k in ('media_content','media_thumbnail'):
  c += [x.get('url','') for x in e.get(k,[]) if isinstance(x,dict)]
 for x in e.get('enclosures',[]):
  if isinstance(x,dict):c.append(x.get('href','') or x.get('url',''))
 for field in ('summary','description','content'):
  v=e.get(field,'');v=' '.join(str(x.get('value','')) for x in v if isinstance(x,dict)) if isinstance(v,list) else str(v)
  soup=BeautifulSoup(v,'html.parser');c += [urljoin(u,t.get('src','')) for t in soup.find_all('img')]
 try:
  r=requests.get(u,timeout=10,headers=HEADERS,allow_redirects=True);soup=BeautifulSoup(r.text,'html.parser')
  for t in (soup.find('meta',property='og:image'),soup.find('meta',property='og:image:url'),soup.find('meta',attrs={'name':'twitter:image'}),soup.find('meta',attrs={'name':'twitter:image:src'})):
   if t:c.append(urljoin(r.url,t.get('content','')))
  c += [urljoin(r.url,t.get('src','')) for t in soup.select('article img, main img, figure img')[:15]]
 except Exception:pass
 return next((x for x in dict.fromkeys(c) if valid_image(x)),'')
def tokens(text):
 stop={'the','and','for','with','from','that','this','into','after','before','over','about','says','latest','update','news','report','reports','announces','announce'}
 return {x for x in re.findall(r'[a-z0-9]+',text.lower()) if len(x)>2 and x not in stop}
def similar(a,b,threshold=.44):
 x=tokens(a.get('headline','')+' '+a.get('summary','')[:220]);y=tokens(b.get('headline','')+' '+b.get('summary','')[:220])
 return bool(x and y and len(x&y)/max(1,min(len(x),len(y)))>=threshold)
def duplicate(x,selected):return any(similar(x,y) for y in selected)
def score(x):
 text=(x['headline']+' '+x['summary']).lower()
 value=2+sum(3 for k in CFG['importance_keywords'] if k in text)+7*any(k in text for k in CFG['sports_keywords'])
 if x.get('image'):value+=1
 return value
def cap(cat):return CFG.get('category_limits',{}).get(cat,CFG['max_per_category'])

def prior_stories():
 found=[]
 for p in DATA.glob('*.json'):
  try:
   b=json.loads(p.read_text());d=datetime.fromisoformat(b['generated_at'])
   if now-d<=timedelta(days=CFG.get('cross_edition_history_days',2)):found+=b.get('stories',[])
  except Exception:pass
 return found
history=prior_stories();old_good=[x for x in history if x.get('category')=='Good News']
def repeated_good(x):return x['category']=='Good News' and any(x.get('url')==y.get('url') or similar(x,y,.50) for y in old_good)
def repeated_recent(x):
 if edition!='PM':return False
 return any(x.get('url')==y.get('url') or similar(x,y,.50) for y in history)

items=[]
for feed in CFG['feeds']:
 parsed=feedparser.parse(feed['url'])
 for entry in parsed.entries[:45]:
  d,raw=pdate(entry);u=entry.get('link','');h=clean(entry.get('title',''));sm=clean(entry.get('summary',''))[:900]
  if not u or not h or not fresh(u,d,feed['category']):continue
  x={'headline':h,'summary':sm,'why_it_matters':'','url':u,'source':feed['name'],'published':raw,'category':feed['category'],'confidence':'Reported','image':'','perspective_one':'','perspective_two':'','uncertain':'','_entry':entry}
  x['_score']=score(x);items.append(x)
ranked=sorted(items,key=lambda x:(x['_score'],x['published']),reverse=True)
chosen=[];counts={}
# Breadth first: select one fresh story per category whenever a qualifying candidate exists.
for cat in CFG['category_order']:
 candidates=[x for x in ranked if x['category']==cat and not repeated_good(x) and not duplicate(x,chosen)]
 fresh_candidates=[x for x in candidates if not repeated_recent(x)]
 pool=fresh_candidates or candidates
 if pool:chosen.append(pool[0]);counts[cat]=1
# Then fill remaining featured slots, respecting caps and strong duplicate suppression.
for x in ranked:
 if len(chosen)>=CFG['max_stories']:break
 if counts.get(x['category'],0)>=cap(x['category']) or repeated_good(x) or repeated_recent(x) or duplicate(x,chosen):continue
 chosen.append(x);counts[x['category']]=counts.get(x['category'],0)+1
# Extra distinct stories become links, never duplicate cards.
selected_urls={x['url'] for x in chosen};more={c:[] for c in CFG['category_order']}
for x in ranked:
 if x['url'] in selected_urls or repeated_good(x) or repeated_recent(x) or len(more[x['category']])>=CFG['more_links_per_category'] or duplicate(x,chosen+more[x['category']]):continue
 more[x['category']].append({'headline':x['headline'],'url':x['url'],'source':x['source'],'summary':x['summary']})
if not any(x.get('category')=='Good News' for x in chosen):raise RuntimeError('No fresh, non-repeated Good News story was found; previous briefing preserved.')
for x in chosen:x['image']=find_image(x.pop('_entry'),x['url'])
key=os.getenv('OPENAI_API_KEY','').strip()
if not key:raise RuntimeError('OPENAI_API_KEY missing; previous briefing preserved.')
from openai import OpenAI
payload=json.dumps([{k:v for k,v in x.items() if not k.startswith('_')} for x in chosen])
prompt='''Return only a valid JSON array containing every supplied story exactly once and every original key. Preserve URL, source, published, image, and category exactly. Never invent facts or return markdown.
For EVERY story, summary is exactly two short plain-language sentences totaling 24-40 words. why_it_matters is REQUIRED and is one clear sentence under 18 words. Use common words, active voice, and one idea per sentence.
Perspectives are REQUIRED for any story that is even mildly controversial or involves politics, policy, courts, war, diplomacy, policing, public health, economics, education, labor, corporate power, technology risks, rights, fairness, or competing public priorities. For such stories, perspective_one and perspective_two each state a distinct good-faith argument in one plain sentence of 10-20 words. Explain the disagreement, not political teams. Do not create false balance about established facts. Leave perspectives blank only for clearly noncontroversial stories such as routine sports results, rescues, or straightforward discoveries. uncertain is optional and should be blank unless a key fact is unresolved. confidence is Confirmed, Developing, Disputed, or Reported. Stories: '''+payload
try:
 text=OpenAI(api_key=key).responses.create(model=os.getenv('OPENAI_MODEL','gpt-4.1-mini'),input=prompt).output_text.strip().removeprefix('```json').removesuffix('```').strip();result=json.loads(text)
 if not isinstance(result,list) or len(result)!=len(chosen):raise ValueError('AI returned wrong story count')
 required={'headline','summary','why_it_matters','url','source','published','category','confidence','image'}
 for story in result:
  story.setdefault('perspective_one','');story.setdefault('perspective_two','');story.setdefault('uncertain','')
  missing=required-set(story)
  if missing:raise ValueError(f'missing required fields: {sorted(missing)}')
  if not str(story['why_it_matters']).strip():raise ValueError('missing Why It Matters')
 chosen=result
except Exception as e:raise RuntimeError(f'AI enrichment failed; previous briefing preserved: {e}') from e
for x in chosen:x.pop('_score',None)
out={'generated_at':now.isoformat(),'edition':edition,'stories':chosen,'more_stories':more}
name=f"{now:%Y-%m-%d}_{edition}.json";(DATA/name).write_text(json.dumps(out,indent=2));print(name,len(chosen))
