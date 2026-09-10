import io
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageStat

BAD_PARTS=("gstatic","googleusercontent","logo","icon","favicon","placeholder","avatar","sprite","tracking","pixel")

def _candidates(entry,url,headers):
    found=[]
    for key in ("media_content","media_thumbnail"):
        found += [x.get("url","") for x in entry.get(key,[]) if isinstance(x,dict)]
    for x in entry.get("enclosures",[]):
        if isinstance(x,dict): found.append(x.get("href","") or x.get("url",""))
    for field in ("summary","description","content"):
        value=entry.get(field,"")
        if isinstance(value,list): value=" ".join(str(x.get("value","")) for x in value if isinstance(x,dict))
        soup=BeautifulSoup(str(value),"html.parser")
        found += [urljoin(url,t.get("src","") or t.get("data-src","") or t.get("data-lazy-src","")) for t in soup.find_all("img")]
    try:
        r=requests.get(url,headers=headers,timeout=10,allow_redirects=True)
        soup=BeautifulSoup(r.text,"html.parser")
        selectors=[
            ('meta',{'property':'og:image'}),('meta',{'property':'og:image:url'}),
            ('meta',{'property':'og:image:secure_url'}),('meta',{'name':'twitter:image'}),
            ('meta',{'name':'twitter:image:src'})]
        for name,attrs in selectors:
            tag=soup.find(name,attrs=attrs)
            if tag: found.append(urljoin(r.url,tag.get("content","")))
        for tag in soup.select("article img, main img, figure img, [class*='hero'] img, [class*='lead'] img")[:20]:
            found.append(urljoin(r.url,tag.get("src","") or tag.get("data-src","") or tag.get("data-lazy-src","")))
    except Exception: pass
    return list(dict.fromkeys(x for x in found if x))

def _valid(url,headers):
    if not url or any(x in url.lower() for x in BAD_PARTS): return False
    try:
        r=requests.get(url,headers=headers,timeout=8)
        r.raise_for_status()
        im=Image.open(io.BytesIO(r.content)).convert("RGB")
        w,h=im.size
        if len(r.content)<6500 or w<260 or h<130 or w/h>4.2 or w/h<.52: return False
        small=im.resize((64,64)); colors=len(small.quantize(colors=32).getcolors() or [])
        stat=ImageStat.Stat(small)
        return colors>5 and not(sum(stat.mean)/3>230 and sum(stat.stddev)/3<35)
    except Exception: return False

def best_image(entry,url,headers):
    return next((x for x in _candidates(entry,url,headers) if _valid(x,headers)),"")
