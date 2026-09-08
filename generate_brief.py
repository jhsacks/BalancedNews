import os,re,json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import feedparser,requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).parent; CFG=json.loads((ROOT/'config.json').read_text()); DATA=ROOT/'data/briefings'; DATA.mkdir(parents=True,exist_ok=True)
now=datetime.now(ZoneInfo(CFG['timezone'])); edition=os.getenv('BRIEF_EDITION') or ('AM' if now.hour<12 else 'PM')
def clean(x): return re.sub(r'<[^>]+>','',x or '').replace('&amp;','&').strip()
def image_for(url):
    try:
        r=requests.get(url,timeout=5,headers={'User-Agent':'Mozilla/5.0'}); s=BeautifulSoup(r.text,'html.parser')
        t=s.find('meta',property='og:image') or s.find('meta',attrs={'name':'twitter:image'})
        return t.get('content','') if t else ''
    except: return ''
def score(x):
    t=(x['headline']+' '+x['summary']).lower(); n=sum(2 for k in CFG['major_keywords'] if k.lower() in t)
    n+=5 if any(k.lower() in t for k in CFG['sports_keywords']) else 0
    n+=2 if x['category'] in ('International Affairs','Healthcare & Medicine','Markets & Economy') else 0
    n-=3 if any(k in t for k in ('celebrity','royal','fashion','recipe','quiz')) else 0
    return n
items=[]
for f in CFG['feeds']:
    d=feedparser.parse(f['url'])
    for e in d.entries[:35]:
        x={'headline':clean(e.get('title','')),'summary':clean(e.get('summary',''))[:700],'url':e.get('link',''),'source':f['name'],'published':e.get('published','') or e.get('updated',''),'category':f['category'],'confidence':'Reported','image':'','perspective_one':'','perspective_two':''}
        if x['headline'] and x['url']: x['_score']=score(x); items.append(x)
seen=set(); stories=[]
for x in sorted(items,key=lambda v:v['_score'],reverse=True):
    key=re.sub('[^a-z0-9]','',x['headline'].lower())[:80]
    if key in seen or x['_score']<1: continue
    seen.add(key); x['image']=image_for(x['url']); stories.append(x)
    if len(stories)>=CFG['max_stories']: break
key=os.getenv('OPENAI_API_KEY','').strip()
if key and stories:
    try:
        from openai import OpenAI
        client=OpenAI(api_key=key); raw=json.dumps([{k:v for k,v in x.items() if k!='_score'} for x in stories])
        prompt='Return JSON only, same array and keys. Calm factual headlines and summaries. Never add facts. Preserve URL, source, published, image, category. For genuinely controversial stories add concise perspective_one and perspective_two without false balance; otherwise blank. Confidence: Reported, Developing, or Disputed. Input:\n'+raw
        text=client.responses.create(model=os.getenv('OPENAI_MODEL','gpt-4.1-mini'),input=prompt).output_text.strip().removeprefix('```json').removesuffix('```').strip(); stories=json.loads(text)
    except Exception as e: print('AI refinement skipped:',e)
for x in stories: x.pop('_score',None)
out={'generated_at':now.isoformat(),'edition':edition,'stories':stories}; name=f"{now.strftime('%Y-%m-%d')}_{edition}.json"; (DATA/name).write_text(json.dumps(out,indent=2)); print(name,len(stories))
