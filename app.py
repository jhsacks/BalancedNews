import json,html
from pathlib import Path
from datetime import datetime,timedelta
import streamlit as st
R=Path(__file__).parent; C=json.loads((R/'config.json').read_text()); D=R/'data/briefings'; Q=R/'assets/zelle_qr.png'; CR=R/'assets/crickets.png'
st.set_page_config(page_title=C['title'],page_icon='📰',layout='wide')
st.markdown('''<style>
.block-container{max-width:1240px;padding-top:1.3rem}.hero{background:linear-gradient(110deg,#123B5D,#0F766E);color:white;padding:13px 22px;border-radius:15px;display:flex;align-items:baseline;gap:18px;flex-wrap:wrap}.hero h1{font-size:2rem;line-height:1;margin:0}.hero p{font-size:.98rem;margin:0;opacity:.94}.edition{font-size:.88rem;color:#52616b;margin:7px 2px 12px}.support{background:#FFF8E8;border:1px solid #F1D58A;border-radius:14px;padding:12px 15px;margin:12px 0}.card{background:white;border:1px solid #E1E8EC;border-radius:16px;overflow:hidden;margin-bottom:16px}.card img{width:100%;height:145px;object-fit:cover}.body{padding:16px}.eye{font-size:.72rem;font-weight:800;color:#0F766E;text-transform:uppercase}.card h3{margin:7px 0}.sum,.why,.ctx-line{line-height:1.62;font-size:1rem;letter-spacing:.01em}.why{margin-top:10px}.ctx{background:#EFF8F6;border-left:4px solid #0F766E;padding:10px 12px;margin-top:11px;border-radius:0 8px 8px 0}.ctx-title{font-weight:800;color:#0B5F59;margin-bottom:5px}.src{font-size:.8rem;color:#718096;margin-top:10px}.btn{display:inline-block;background:#0F766E;color:white!important;padding:7px 11px;border-radius:8px;text-decoration:none;margin-top:9px}.empty{border:1px dashed #B8C7CC;border-radius:16px;padding:14px;text-align:center;color:#60717A;background:#FAFCFC}.empty img{height:120px;max-width:100%;object-fit:contain}.more{background:#F7F9FA;border-radius:12px;padding:10px 14px;margin:-4px 0 18px}.more b{color:#123B5D}.more li{margin:6px 0}
</style>''',unsafe_allow_html=True)
def e(x):return html.escape(str(x or ''))
def card(s):
 img=f"<img src='{e(s.get('image'))}'>" if s.get('image') else ''
 why=f"<div class='why'><b>Why it matters:</b> {e(s.get('why_it_matters'))}</div>" if s.get('why_it_matters') else ''
 views=[]
 if s.get('perspective_one'):views.append(f"<div class='ctx-line'><b>One perspective:</b> {e(s['perspective_one'])}</div>")
 if s.get('perspective_two'):views.append(f"<div class='ctx-line'><b>Another perspective:</b> {e(s['perspective_two'])}</div>")
 if s.get('uncertain'):views.append(f"<div class='ctx-line'><b>Still unclear:</b> {e(s['uncertain'])}</div>")
 ctx="<div class='ctx'><div class='ctx-title'>Where perspectives differ</div>"+''.join(views)+"</div>" if views else ''
 return f"<div class='card'>{img}<div class='body'><div class='eye'>{e(s.get('category'))} · {e(s.get('confidence'))}</div><h3>{e(s.get('headline'))}</h3><div class='sum'>{e(s.get('summary'))}</div>{why}{ctx}<div class='src'>{e(s.get('source'))} · {e(s.get('published'))}</div><a class='btn' href='{e(s.get('url'))}'>Read source article</a></div></div>"
B=[]
for p in D.glob('*.json'):
 try:
  b=json.loads(p.read_text());d=datetime.fromisoformat(b['generated_at'])
  if datetime.now(d.tzinfo)-d<=timedelta(days=C.get('archive_days',8)):B.append(b)
 except Exception:pass
B=sorted(B,key=lambda x:x['generated_at'],reverse=True)
if not B:st.warning('No briefings are available yet. Run the briefing workflow once.');st.stop()
with st.sidebar:
 st.title('🗓️ Briefing Archive');labels=[f"{datetime.fromisoformat(b['generated_at']).strftime('%A, %b %d')} · {b['edition']}" for b in B];i=st.radio('Edition',range(len(B)),format_func=lambda x:labels[x],label_visibility='collapsed');st.divider();st.link_button('Support via Venmo','https://venmo.com/u/jhsacks',use_container_width=True)
 if Q.exists():st.image(str(Q),caption='Zelle: scan the QR code',use_container_width=True)
b=B[i];d=datetime.fromisoformat(b['generated_at']);S=b.get('stories',[]);M=b.get('more_stories',{})
st.markdown(f"<div class='hero'><h1>{e(C['title'])}</h1><p>{e(C['tagline'])}</p></div><div class='edition'>{d.strftime('%A, %B %d, %Y')} · <b>{b['edition']} edition</b></div>",unsafe_allow_html=True)
st.markdown("<div class='support'><b>I hope you like this site!</b> It is reader-supported. <a href='https://venmo.com/u/jhsacks'>Support via Venmo</a></div>",unsafe_allow_html=True)
for cat in C['category_order']:
 st.header(cat);G=[s for s in S if s.get('category')==cat]
 if not G:
  img=f"<img src='{CR.as_posix()}'>" if CR.exists() else '🦗'
  st.markdown(f"<div class='empty'>{img}<div><b>Quiet in this section.</b><br>No fresh story cleared the quality bar for this edition.</div></div>",unsafe_allow_html=True)
 else:
  cols=st.columns(2)
  for n,s in enumerate(G):
   with cols[n%2]:st.markdown(card(s),unsafe_allow_html=True)
 links=M.get(cat,[])
 if links:
  st.markdown("<div class='more'><b>More worth a look</b><ul>"+''.join(f"<li><a href='{e(x['url'])}'>{e(x['headline'])}</a> <span class='src'>· {e(x.get('source'))}</span></li>" for x in links)+"</ul></div>",unsafe_allow_html=True)
