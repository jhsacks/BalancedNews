import re
import html
import requests

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
STOP = {"the","and","for","with","from","that","this","after","before","over","about","says","news","today","live","analysis","why","how","what","could","would","will","new","amid","report","reports"}

def _plain(value):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(str(value or "")))).strip()

def _queries(headline, category):
    words=[w for w in re.findall(r"[A-Za-z0-9]+", headline) if len(w)>2 and w.lower() not in STOP]
    proper=[w for w in re.findall(r"\b(?:[A-Z][A-Za-z0-9]+|[A-Z]{2,})\b", headline) if w.lower() not in STOP]
    queries=[]
    if proper: queries.append(" ".join(proper[:6]))
    if words: queries.append(" ".join(words[:7]))
    category_fallbacks={
      "U.S. Politics":"United States Capitol White House",
      "U.S. News":"United States news",
      "World News":"world international",
      "Conflicts & Security":"military diplomacy",
      "Middle East Affairs":"Middle East diplomacy",
      "Health & Medicine":"medicine hospital research",
      "AI & Technology":"artificial intelligence technology",
      "Business & Economy":"stock market economy",
      "Society & Culture":"education society culture",
      "Sports":"sports stadium",
      "Good News":"community volunteers success"
    }
    if category in category_fallbacks:queries.append(category_fallbacks[category])
    return list(dict.fromkeys(q for q in queries if q))

def _search(query, headers):
    params={
      "action":"query","generator":"search","gsrsearch":f"filetype:bitmap {query}",
      "gsrnamespace":6,"gsrlimit":8,"prop":"imageinfo",
      "iiprop":"url|extmetadata","iiurlwidth":1200,"format":"json","origin":"*"
    }
    response=requests.get(COMMONS_API,params=params,headers=headers,timeout=12)
    response.raise_for_status()
    pages=list(response.json().get("query",{}).get("pages",{}).values())
    for page in pages:
        info=(page.get("imageinfo") or [{}])[0]
        url=info.get("thumburl") or info.get("url")
        if not url:continue
        meta=info.get("extmetadata",{})
        license_name=_plain(meta.get("LicenseShortName",{}).get("value",""))
        artist=_plain(meta.get("Artist",{}).get("value",""))
        source=info.get("descriptionurl","")
        return {"url":url,"credit":f"Wikimedia Commons{(' · '+artist) if artist else ''}{(' · '+license_name) if license_name else ''}","source":source,"query":query}
    return None

def topic_image(headline, category, headers):
    for query in _queries(headline,category):
        try:
            result=_search(query,headers)
            if result:return result
        except Exception as error:
            print(f"Topic image search skipped for {query}: {error}")
    return None
