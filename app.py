import json, html
from pathlib import Path
from datetime import datetime
import streamlit as st
ROOT=Path(__file__).parent; CFG=json.loads((ROOT/'config.json').read_text()); DATA=ROOT/'data/briefings'
st.set_page_config(page_title=CFG['title'],page_icon='📰',layout='wide')
st.markdown('''<style>.block-container{max-width:1180px;padding-top:1.4rem}.hero{background:linear-gradient(135deg,#123B5D,#0E7490);color:white;padding:28px 30px;border-radius:22px;margin-bottom:20px}.hero h1{margin:0;font-size:2.35rem}.hero p{margin:6px 0 0;color:#D9F0F4}.story{background:white;border:1px solid #E3E8EE;border-radius:18px;overflow:hidden;margin-bottom:22px;box-shadow:0 4px 14px rgba(20,33,61,.06)}.story img{width:100%;height:260px;object-fit:cover}.story-body{padding:20px}.eyebrow{font-size:.76rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#0E7490}.story h3{font-size:1.35rem;line-height:1.22;margin:8px 0;color:#14213D}.summary{font-size:1rem;line-height:1.55;color:#344054}.balance{background:#F1F7F8;border-left:4px solid #0E7490;padding:12px 14px;margin:13px 0;border-radius:8px}.source{font-size:.82rem;color:#667085}.button{display:inline-block;background:#0E7490;color:white!important;text-decoration:none;padding:9px 14px;border-radius:10px;font-weight:700;margin-top:10px}.section{margin:28px 0 12px}</style>''',unsafe_allow_html=True)
briefs=[]
for p in DATA.glob('*.json'):
    try: briefs.append(json.loads(p.read_text()))
    except: pass
briefs=sorted(briefs,key=lambda x:x.get('generated_at',''),reverse=True)
if not briefs: st.error('No briefing files yet. Run the GitHub Action.'); st.stop()
with st.sidebar:
    st.title('Archive'); st.caption('Latest first. Select any previous AM or PM edition.')
    labels=[]
    for b in briefs:
        d=datetime.fromisoformat(b['generated_at']); labels.append(f"{d.strftime('%A, %b %d')} · {b['edition']}")
    chosen=st.radio('Edition',range(len(briefs)),format_func=lambda i:labels[i],label_visibility='collapsed')
b=briefs[chosen]; d=datetime.fromisoformat(b['generated_at'])
st.markdown(f"<div class='hero'><h1>📰 {html.escape(CFG['title'])}</h1><p>{html.escape(CFG['tagline'])}</p></div>",unsafe_allow_html=True)
st.caption(f"{d.strftime('%A, %B %d, %Y')} · {b['edition']} edition · Updated {d.strftime('%I:%M %p %Z')}")
if chosen: st.info('Archived edition. Choose the first sidebar item for the latest brief.')
stories=b.get('stories',[]); cats=[]
for s in stories:
    if s['category'] not in cats: cats.append(s['category'])
for cat in cats:
    st.markdown(f"<h2 class='section'>{html.escape(cat)}</h2>",unsafe_allow_html=True); cols=st.columns(2)
    for i,s in enumerate([x for x in stories if x['category']==cat]):
        with cols[i%2]:
            image=f"<img src='{html.escape(s.get('image',''))}' alt='News image'>" if s.get('image') else ''
            balance=''
            if s.get('perspective_one') or s.get('perspective_two'):
                balance=f"<div class='balance'><b>Balanced context</b><br>{html.escape(s.get('perspective_one',''))}<br><br>{html.escape(s.get('perspective_two',''))}</div>"
            st.markdown(f"<div class='story'>{image}<div class='story-body'><div class='eyebrow'>{html.escape(cat)} · {html.escape(s.get('confidence','Reported'))}</div><h3>{html.escape(s['headline'])}</h3><div class='summary'>{html.escape(s.get('summary',''))}</div>{balance}<div class='source'>{html.escape(s.get('source',''))} · {html.escape(s.get('published',''))}</div><a class='button' href='{html.escape(s['url'])}' target='_blank'>Read original reporting</a></div></div>",unsafe_allow_html=True)
st.divider(); st.caption('Selected for significance, not category quotas. Source inclusion does not imply endorsement.')
