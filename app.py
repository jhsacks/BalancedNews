import json,html
from pathlib import Path
from datetime import datetime,timedelta
import streamlit as st
ROOT=Path(__file__).parent; CFG=json.loads((ROOT/'config.json').read_text()); DATA=ROOT/'data/briefings'
st.set_page_config(page_title=CFG['title'],page_icon='📰',layout='wide',initial_sidebar_state='expanded')
st.markdown('''<style>.block-container{max-width:1240px;padding-top:1.1rem}.hero{background:linear-gradient(135deg,#123B5D,#0F766E);color:white;padding:34px;border-radius:24px}.hero h1{font-size:3rem;margin:0}.hero p{font-size:1.08rem;color:#D7F0ED;margin:.35rem 0 0}.meta{color:#667085;margin:18px 0}.lead,.card,.snapshot{background:#fff;border:1px solid #E1E8EC;border-radius:20px;overflow:hidden;box-shadow:0 6px 20px #18364a12;margin-bottom:22px}.lead img{width:100%;height:430px;object-fit:cover}.card img{width:100%;height:225px;object-fit:cover}.body{padding:21px}.lead .body{padding:27px}.eyebrow{font-size:.73rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:#0F766E}.lead h2{font-size:2.2rem;line-height:1.12;margin:.45rem 0}.card h3{font-size:1.28rem;line-height:1.22;margin:.45rem 0}.summary{line-height:1.58;color:#34495E}.context{background:#EFF8F6;border-left:4px solid #0F766E;padding:13px;margin:14px 0;border-radius:8px}.source{font-size:.8rem;color:#718096;margin-top:12px}.btn{display:inline-block;background:#0F766E;color:#fff!important;text-decoration:none;padding:9px 14px;border-radius:10px;font-weight:750;margin-top:10px}.section{margin:30px 0 13px}.snapgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.snap{background:#102F46;color:white;padding:15px;border-radius:14px}.snap b{color:#A7F3D0}@media(max-width:700px){.hero h1{font-size:2.1rem}.lead img{height:245px}.lead h2{font-size:1.65rem}.snapgrid{grid-template-columns:1fr}}</style>''',unsafe_allow_html=True)
def esc(x): return html.escape(str(x or ''))
def load():
 out=[]
 for p in DATA.glob('*.json'):
  try:
   d=json.loads(p.read_text()); dt=datetime.fromisoformat(d['generated_at'])
   if datetime.now(dt.tzinfo)-dt<=timedelta(days=CFG.get('archive_days',8)): out.append(d)
  except: pass
 return sorted(out,key=lambda d:d['generated_at'],reverse=True)
def card(s,lead=False):
 img=f"<img src='{esc(s.get('image'))}' alt='{esc(s.get('headline'))}'>" if s.get('image') else ''
 ctx=''
 if any(s.get(k) for k in ('perspective_one','perspective_two','uncertain')):
  ctx=f"<div class='context'><b>Balanced context</b><br>{esc(s.get('perspective_one'))}{'<br><br>'+esc(s.get('perspective_two')) if s.get('perspective_two') else ''}{'<br><br><b>Still uncertain:</b> '+esc(s.get('uncertain')) if s.get('uncertain') else ''}</div>"
 tag='h2' if lead else 'h3'; cls='lead' if lead else 'card'
 return f"<article class='{cls}'>{img}<div class='body'><div class='eyebrow'>{esc(s.get('category'))} · {esc(s.get('confidence','Reported'))}</div><{tag}>{esc(s.get('headline'))}</{tag}><div class='summary'>{esc(s.get('summary'))}</div>{ctx}<div class='source'>{esc(s.get('source'))} · {esc(s.get('published'))}</div><a class='btn' href='{esc(s.get('url'))}' target='_blank'>Read original reporting</a></div></article>"
briefs=load()
if not briefs: st.error('No live editions yet. Run Generate dated news brief in GitHub Actions.'); st.stop()
with st.sidebar:
 st.title('🗓️ Briefing Archive'); st.caption('The latest edition appears first.')
 labels=[]
 for b in briefs:
  d=datetime.fromisoformat(b['generated_at']); labels.append(f"{d.strftime('%A, %b %d')} · {b['edition']}")
 pick=st.radio('Edition',range(len(briefs)),format_func=lambda i:labels[i],label_visibility='collapsed')
 st.divider(); st.caption('AM and PM editions remain available for the previous week.')
b=briefs[pick]; d=datetime.fromisoformat(b['generated_at']); stories=b.get('stories',[])
st.markdown(f"<div class='hero'><h1>{esc(CFG['title'])}</h1><p>{esc(CFG['tagline'])}</p></div><div class='meta'>{d.strftime('%A, %B %d, %Y')} · <b>{b['edition']} edition</b> · Updated {d.strftime('%I:%M %p')}</div>",unsafe_allow_html=True)
if pick: st.info('You are viewing an archived edition. Select the first sidebar item for the newest brief.')
if not stories: st.warning('No stories met the importance threshold for this edition.'); st.stop()
st.markdown(card(stories[0],True),unsafe_allow_html=True)
if len(stories)>1:
 st.markdown("<h2 class='section'>Top stories</h2>",unsafe_allow_html=True); cols=st.columns(2)
 for i,s in enumerate(stories[1:5]):
  with cols[i%2]: st.markdown(card(s),unsafe_allow_html=True)
remaining=stories[5:]
order=['U.S. Government & Politics','Major U.S. News','International Affairs','Conflicts & Security','Israel / Palestinian Territories','Healthcare & Medicine','Science & Discovery','AI & Technology','Markets & Economy','Sports','Positive Developments','Understanding the Story','Worth Watching']
for cat in order:
 group=[s for s in remaining if s.get('category')==cat]
 if not group: continue
 st.markdown(f"<h2 class='section'>{esc(cat)}</h2>",unsafe_allow_html=True); cols=st.columns(2)
 for i,s in enumerate(group):
  with cols[i%2]: st.markdown(card(s),unsafe_allow_html=True)
st.divider(); st.caption('Selected for significance, not category quotas. Source inclusion does not imply endorsement. Developing and disputed claims are labeled.')
