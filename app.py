import json,html
from pathlib import Path
from datetime import datetime,timedelta
import streamlit as st
R=Path(__file__).parent;C=json.loads((R/'config.json').read_text());D=R/'data/briefings';Q=R/'assets/zelle_qr.png'
st.set_page_config(page_title=C['title'],page_icon='📰',layout='wide')
st.markdown('''<style>.block-container{max-width:1240px}.hero{background:linear-gradient(135deg,#123B5D,#0F766E);color:white;padding:28px;border-radius:20px}.support{background:#FFF8E8;border:1px solid #F1D58A;border-radius:16px;padding:16px;margin:18px 0}.rail{background:#102F46;color:white;padding:14px 18px;border-radius:15px}.rail a{color:#D7F0ED!important}.card{background:white;border:1px solid #E1E8EC;border-radius:17px;overflow:hidden;margin-bottom:18px}.card img{width:100%;height:145px;object-fit:cover}.body{padding:17px}.eye{font-size:.72rem;font-weight:800;color:#0F766E;text-transform:uppercase}.card h3{margin:7px 0}.sum{line-height:1.65;font-size:1.02rem;letter-spacing:.01em;max-width:68ch}.why{margin-top:11px;line-height:1.6}.ctx{background:#EFF8F6;border-left:4px solid #0F766E;padding:10px;margin-top:10px}.src{font-size:.8rem;color:#718096;margin-top:10px}.btn{display:inline-block;background:#0F766E;color:white!important;padding:8px 12px;border-radius:8px;text-decoration:none;margin-top:9px}</style>''',unsafe_allow_html=True)
def e(x):return html.escape(str(x or ''))
def card(s):
 img=f"<img src='{e(s.get('image'))}'>" if s.get('image') else '';why=f"<div class='why'><b>Why it matters:</b> {e(s.get('why_it_matters'))}</div>" if s.get('why_it_matters') else '';bits=[]
 for k,l in [('perspective_one','One view'),('perspective_two','Another view'),('uncertain','Still uncertain')]:
  if s.get(k):bits.append(f'<b>{l}:</b> {e(s[k])}')
 ctx="<div class='ctx'>"+'<br><br>'.join(bits)+"</div>" if bits else ''
 return f"<div class='card'>{img}<div class='body'><div class='eye'>{e(s.get('category'))} · {e(s.get('confidence'))}</div><h3>{e(s.get('headline'))}</h3><div class='sum'>{e(s.get('summary'))}</div>{why}{ctx}<div class='src'>{e(s.get('source'))} · {e(s.get('published'))}</div><a class='btn' href='{e(s.get('url'))}'>Read source article</a></div></div>"
B=[]
for p in D.glob('*.json'):
 try:
  b=json.loads(p.read_text());d=datetime.fromisoformat(b['generated_at'])
  if datetime.now(d.tzinfo)-d<=timedelta(days=C.get('archive_days',8)):B.append(b)
 except:pass
B=sorted(B,key=lambda x:x['generated_at'],reverse=True)
with st.sidebar:
 st.title('🗓️ Briefing Archive'); labels=[f"{datetime.fromisoformat(b['generated_at']).strftime('%A, %b %d')} · {b['edition']}" for b in B];i=st.radio('Edition',range(len(B)),format_func=lambda x:labels[x],label_visibility='collapsed');st.divider();st.link_button('Support via Venmo','https://venmo.com/u/jhsacks',use_container_width=True)
 if Q.exists():st.image(str(Q),caption='Zelle: scan the QR code',use_container_width=True)
b=B[i];d=datetime.fromisoformat(b['generated_at']);S=b['stories'];st.markdown(f"<div class='hero'><h1>{e(C['title'])}</h1><p>{e(C['tagline'])}</p></div><p>{d.strftime('%A, %B %d, %Y')} · <b>{b['edition']} edition</b></p>",unsafe_allow_html=True)
st.markdown("<div class='support'><b>I hope you like this site!</b><br>But it is not free to run. Feel free to throw me a few bucks every month or so to keep it going!<br><a href='https://venmo.com/u/jhsacks'>Support via Venmo</a></div>",unsafe_allow_html=True)
st.markdown("<div class='rail'><b>Top stories</b><ol>"+''.join(f"<li><a href='{e(s['url'])}'>{e(s['headline'])}</a></li>" for s in S[:5])+"</ol></div>",unsafe_allow_html=True)
seen=set()
for cat in C['category_order']+[s.get('category') for s in S]:
 if not cat or cat in seen:continue
 G=[s for s in S if s.get('category')==cat]
 if not G:continue
 seen.add(cat);st.header(cat);cols=st.columns(2)
 for n,s in enumerate(G):
  with cols[n%2]:st.markdown(card(s),unsafe_allow_html=True)
