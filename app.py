import json, html
from pathlib import Path
from datetime import datetime
import streamlit as st
ROOT=Path(__file__).parent; DATA=ROOT/'data/briefings'
st.set_page_config(page_title='The Balanced Brief',page_icon='📰',layout='wide',initial_sidebar_state='expanded')
st.markdown('''<style>
.block-container{max-width:1220px;padding-top:1.2rem}.hero{background:linear-gradient(135deg,#123B5D,#0F766E);color:#fff;padding:34px;border-radius:24px;margin-bottom:18px}.hero h1{font-size:2.9rem;margin:0}.hero p{font-size:1.08rem;color:#D7F0ED;margin:.35rem 0 0}.edition{color:#607080;margin-bottom:1.3rem}.lead{background:#fff;border-radius:22px;overflow:hidden;box-shadow:0 8px 26px #18364a16;margin-bottom:25px}.lead img{width:100%;height:410px;object-fit:cover}.leadbody{padding:26px}.lead h2{font-size:2.15rem;line-height:1.12;margin:.4rem 0}.card{background:#fff;border:1px solid #DFE7EB;border-radius:18px;overflow:hidden;margin-bottom:22px;box-shadow:0 4px 16px #18364a0d}.card img{width:100%;height:235px;object-fit:cover}.body{padding:19px}.eyebrow{font-size:.73rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:#0F766E}.card h3{font-size:1.3rem;line-height:1.2;margin:.45rem 0}.summary{line-height:1.55;color:#34495E}.context{background:#EFF8F6;border-left:4px solid #0F766E;padding:12px;margin:14px 0;border-radius:8px}.source{font-size:.8rem;color:#718096;margin-top:12px}.btn{display:inline-block;background:#0F766E;color:white!important;text-decoration:none;padding:9px 14px;border-radius:10px;font-weight:750;margin-top:10px}.section{margin:30px 0 13px}.pill{display:inline-block;background:#E8F3F1;color:#0F5E57;border-radius:999px;padding:5px 10px;font-size:.77rem;font-weight:700;margin-right:6px}.ticker{background:#102F46;color:white;padding:13px 18px;border-radius:14px;margin:10px 0 22px}.ticker b{color:#A7F3D0}@media(max-width:700px){.hero h1{font-size:2.1rem}.lead img{height:245px}.lead h2{font-size:1.65rem}}
</style>''',unsafe_allow_html=True)
def load():
 out=[]
 for p in DATA.glob('*.json'):
  try: out.append(json.loads(p.read_text()))
  except: pass
 return sorted(out,key=lambda x:x.get('generated_at',''),reverse=True)
def esc(x): return html.escape(str(x or ''))
def image(s,lead=False): return f"<img src='{esc(s.get('image'))}' alt='{esc(s.get('headline'))}'>" if s.get('image') else ''
def context(s):
 p1=s.get('perspective_one',''); p2=s.get('perspective_two',''); uncertain=s.get('uncertain','')
 if not any([p1,p2,uncertain]): return ''
 return f"<div class='context'><b>Balanced context</b><br>{esc(p1)}{'<br><br>'+esc(p2) if p2 else ''}{'<br><br><b>Still uncertain:</b> '+esc(uncertain) if uncertain else ''}</div>"
def story_card(s,lead=False):
 cls='lead' if lead else 'card'; bcls='leadbody' if lead else 'body'; tag='h2' if lead else 'h3'
 return f"<article class='{cls}'>{image(s,lead)}<div class='{bcls}'><div class='eyebrow'>{esc(s.get('category'))} · {esc(s.get('confidence','Reported'))}</div><{tag}>{esc(s.get('headline'))}</{tag}><div class='summary'>{esc(s.get('summary'))}</div>{context(s)}<div class='source'>{esc(s.get('source'))} · {esc(s.get('published'))}</div><a class='btn' href='{esc(s.get('url'))}' target='_blank'>Read original reporting</a></div></article>"
briefs=load()
if not briefs: st.error('No editions yet. Run the GitHub Action.'); st.stop()
with st.sidebar:
 st.title('🗓️ Briefing Archive'); st.caption('Latest first. Earlier AM and PM editions remain available.')
 labels=[]
 for b in briefs:
  d=datetime.fromisoformat(b['generated_at']); labels.append(f"{d.strftime('%A, %b %d')} · {b['edition']}")
 pick=st.radio('edition',range(len(briefs)),format_func=lambda i:labels[i],label_visibility='collapsed')
 st.divider(); st.caption('Choose any edition you missed. The current brief always remains first.')
b=briefs[pick]; d=datetime.fromisoformat(b['generated_at']); stories=b.get('stories',[])
st.markdown("<div class='hero'><h1>The Balanced Brief</h1><p>Important news. Clear context. No outrage bait.</p></div>",unsafe_allow_html=True)
st.markdown(f"<div class='edition'>{d.strftime('%A, %B %d, %Y')} · <b>{b['edition']} edition</b> · Updated {d.strftime('%I:%M %p')}</div>",unsafe_allow_html=True)
if pick: st.info('Archived edition. Select the first sidebar item to return to the latest briefing.')
if not stories: st.warning('No stories met the importance threshold for this edition.'); st.stop()
lead=stories[0]; st.markdown(story_card(lead,True),unsafe_allow_html=True)
top=stories[1:5]
if top:
 st.subheader('Top stories')
 cols=st.columns(2)
 for i,s in enumerate(top):
  with cols[i%2]: st.markdown(story_card(s),unsafe_allow_html=True)
used={id(x) for x in [lead]+top}; remaining=[x for x in stories if id(x) not in used]
order=['U.S. Government & Politics','Major U.S. News','International Affairs','Conflicts & Security','Israel / Palestinian Territories','Healthcare & Medicine','Science & Discovery','AI & Technology','Markets & Economy','Sports','Positive Developments','Understanding the Story','Worth Watching']
for cat in order:
 group=[s for s in remaining if s.get('category')==cat]
 if not group: continue
 st.markdown(f"<h2 class='section'>{esc(cat)}</h2>",unsafe_allow_html=True)
 cols=st.columns(2)
 for i,s in enumerate(group):
  with cols[i%2]: st.markdown(story_card(s),unsafe_allow_html=True)
st.divider(); st.caption('Stories are selected for significance, not category quotas. Source inclusion does not imply endorsement. Developing and disputed claims are labeled.')
