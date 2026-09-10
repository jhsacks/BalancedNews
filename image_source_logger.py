import json, csv
from pathlib import Path
from datetime import datetime

DATA=Path('data/briefings')
OUT=DATA/'image_source_log.csv'
rows=[]
for f in DATA.glob('*.json'):
    try:
        d=json.loads(f.read_text())
        for s in d.get('stories',[]):
            source=s.get('source','')
            image=bool(str(s.get('image','')).strip())
            method='none'
            if s.get('image_source')=='AI-generated fallback':
                method='ai'
            elif image:
                method='article'
            rows.append([d.get('generated_at',''),d.get('edition',''),source,s.get('category',''),method,s.get('headline','')])
    except: pass
OUT.parent.mkdir(parents=True,exist_ok=True)
with open(OUT,'w',newline='',encoding='utf-8') as fp:
    w=csv.writer(fp)
    w.writerow(['generated_at','edition','source','category','image_method','headline'])
    w.writerows(rows)
print(f'Wrote {len(rows)} rows to {OUT}')
