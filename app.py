import json, html
from pathlib import Path
from datetime import datetime, timedelta
import streamlit as st

ROOT = Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text())
DATA = ROOT / "data/briefings"

st.set_page_config(page_title=CFG["title"], page_icon="📰", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
.block-container{max-width:1240px;padding-top:1.1rem}
.hero{background:linear-gradient(135deg,#123B5D,#0F766E);color:white;padding:30px 34px;border-radius:22px}
.hero h1{font-size:2.65rem;margin:0}.hero p{font-size:1.04rem;color:#D7F0ED;margin:.35rem 0 0}
.meta{color:#667085;margin:17px 0 22px}
.card{background:#fff;border:1px solid #E1E8EC;border-radius:18px;overflow:hidden;box-shadow:0 5px 18px #18364a10;margin-bottom:20px}
.card img{width:100%;height:145px;object-fit:cover;display:block}
.body{padding:18px}.eyebrow{font-size:.72rem;font-weight:800;letter-spacing:.085em;text-transform:uppercase;color:#0F766E}
.card h3{font-size:1.25rem;line-height:1.23;margin:.45rem 0}.summary{line-height:1.56;color:#34495E}
.context{background:#EFF8F6;border-left:4px solid #0F766E;padding:12px;margin:13px 0;border-radius:8px}
.source{font-size:.8rem;color:#718096;margin-top:11px}.btn{display:inline-block;background:#0F766E;color:#fff!important;text-decoration:none;padding:8px 13px;border-radius:9px;font-weight:750;margin-top:10px}
.section{margin:27px 0 12px}.notice{background:#EEF4F7;border-radius:12px;padding:12px 14px;color:#526577;margin-bottom:18px}
@media(max-width:700px){.hero h1{font-size:2rem}.card img{height:125px}}
</style>
""", unsafe_allow_html=True)

def esc(value): return html.escape(str(value or ""))

def load_briefs():
    briefs=[]
    for path in DATA.glob("*.json"):
        try:
            item=json.loads(path.read_text())
            dt=datetime.fromisoformat(item["generated_at"])
            if datetime.now(dt.tzinfo)-dt <= timedelta(days=CFG.get("archive_days",8)):
                briefs.append(item)
        except Exception:
            pass
    return sorted(briefs,key=lambda x:x["generated_at"],reverse=True)

def story_card(story):
    image=f"<img src='{esc(story['image'])}' alt='{esc(story['headline'])}'>"
    context=""
    if any(story.get(k) for k in ("perspective_one","perspective_two","uncertain")):
        context=("<div class='context'><b>Balanced context</b><br>"+esc(story.get("perspective_one"))+
                 ("<br><br>"+esc(story.get("perspective_two")) if story.get("perspective_two") else "")+
                 ("<br><br><b>Still uncertain:</b> "+esc(story.get("uncertain")) if story.get("uncertain") else "")+"</div>")
    return f"""<article class='card'>{image}<div class='body'><div class='eyebrow'>{esc(story.get('category'))} · {esc(story.get('confidence','Reported'))}</div><h3>{esc(story.get('headline'))}</h3><div class='summary'>{esc(story.get('summary'))}</div>{context}<div class='source'>{esc(story.get('source'))} · {esc(story.get('published'))}</div><a class='btn' href='{esc(story.get('url'))}' target='_blank'>Read source article</a></div></article>"""

briefs=load_briefs()
if not briefs:
    st.error("No live editions yet. Run Generate dated news brief in GitHub Actions.")
    st.stop()

with st.sidebar:
    st.title("🗓️ Briefing Archive")
    st.caption("The newest edition appears first.")
    labels=[]
    for brief in briefs:
        dt=datetime.fromisoformat(brief["generated_at"])
        labels.append(f"{dt.strftime('%A, %b %d')} · {brief['edition']}")
    selected=st.radio("Edition",range(len(briefs)),format_func=lambda i:labels[i],label_visibility="collapsed")
    st.divider()
    st.caption("AM and PM editions remain available for the prior week.")

brief=briefs[selected]
dt=datetime.fromisoformat(brief["generated_at"])
stories=[s for s in brief.get("stories",[]) if s.get("image")]
st.markdown(f"<div class='hero'><h1>{esc(CFG['title'])}</h1><p>{esc(CFG['tagline'])}</p></div><div class='meta'>{dt.strftime('%A, %B %d, %Y')} · <b>{brief['edition']} edition</b> · Updated {dt.strftime('%I:%M %p')}</div>",unsafe_allow_html=True)
if selected:
    st.info("Archived edition. Select the first sidebar item for the newest brief.")
if not stories:
    st.warning("No stories with verified article images met the importance threshold for this edition.")
    st.stop()

order=["U.S. Government & Politics","Major U.S. News","International Affairs","Conflicts & Security","Israel / Palestinian Territories","Healthcare & Medicine","Science & Discovery","AI & Technology","Markets & Economy","Sports","Positive Developments","Understanding the Story","Worth Watching"]
# Top stories are equally weighted. No arbitrary hero.
st.markdown("<h2 class='section'>Top stories</h2>",unsafe_allow_html=True)
cols=st.columns(2)
for i,story in enumerate(stories[:6]):
    with cols[i%2]: st.markdown(story_card(story),unsafe_allow_html=True)
remaining=stories[6:]
for category in order:
    group=[s for s in remaining if s.get("category")==category]
    if not group: continue
    st.markdown(f"<h2 class='section'>{esc(category)}</h2>",unsafe_allow_html=True)
    cols=st.columns(2)
    for i,story in enumerate(group):
        with cols[i%2]: st.markdown(story_card(story),unsafe_allow_html=True)
st.divider()
st.caption("Only stories with a real article image are displayed. Stories are selected for significance, not category quotas. Source inclusion does not imply endorsement.")
