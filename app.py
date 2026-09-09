import json, html
from pathlib import Path
from datetime import datetime, timedelta
import streamlit as st

ROOT = Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text())
DATA = ROOT / "data/briefings"
QR = ROOT / "assets/zelle_qr.png"

st.set_page_config(page_title=CFG["title"], page_icon="📰", layout="wide")
st.markdown("""
<style>
.block-container{max-width:1240px;padding-top:1rem}.hero{background:linear-gradient(110deg,#123B5D,#0F766E);color:#fff;padding:12px 20px;border-radius:14px;display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}.hero h1{font-size:1.95rem;line-height:1;margin:0}.hero p{font-size:.96rem;margin:0;opacity:.95}.edition{font-size:.86rem;color:#61717a;margin:6px 2px 10px}.support{background:#FFF8E8;border:1px solid #F1D58A;border-radius:12px;padding:10px 14px;margin:10px 0 16px}.card{background:#fff;border:1px solid #E1E8EC;border-radius:16px;overflow:hidden;margin-bottom:16px}.card img{width:100%;height:155px;object-fit:cover}.body{padding:16px}.eye{font-size:.72rem;font-weight:800;color:#0F766E;text-transform:uppercase}.card h3{margin:7px 0}.sum,.why,.ctx-line{line-height:1.62;font-size:1rem;letter-spacing:.01em}.why{margin-top:10px}.ctx{background:#EFF8F6;border-left:4px solid #0F766E;padding:10px 12px;margin-top:11px;border-radius:0 8px 8px 0}.ctx-title{font-weight:800;color:#0B5F59;margin-bottom:5px}.src{font-size:.8rem;color:#718096;margin-top:10px}.btn{display:inline-block;background:#0F766E;color:#fff!important;padding:7px 11px;border-radius:8px;text-decoration:none;margin-top:9px}.empty{border:1px dashed #B8C7CC;border-radius:16px;padding:18px;text-align:center;color:#60717A;background:#FAFCFC}.cricket{font-size:7rem;line-height:1.05}.more{background:#F7F9FA;border-radius:12px;padding:10px 14px;margin:-4px 0 18px}.more li{margin:6px 0}
</style>""", unsafe_allow_html=True)

def esc(x): return html.escape(str(x or ""))

def story_card(s):
    image = f"<img src='{esc(s.get('image'))}'>" if s.get("image") else ""
    why = f"<div class='why'><b>Why it matters:</b> {esc(s.get('why_it_matters'))}</div>" if s.get("why_it_matters") else ""
    views = []
    if s.get("perspective_one"): views.append(f"<div class='ctx-line'><b>One perspective:</b> {esc(s['perspective_one'])}</div>")
    if s.get("perspective_two"): views.append(f"<div class='ctx-line'><b>Another perspective:</b> {esc(s['perspective_two'])}</div>")
    if s.get("uncertain"): views.append(f"<div class='ctx-line'><b>Still unclear:</b> {esc(s['uncertain'])}</div>")
    perspectives = "<div class='ctx'><div class='ctx-title'>Where perspectives differ</div>" + "".join(views) + "</div>" if views else ""
    return f"<div class='card'>{image}<div class='body'><div class='eye'>{esc(s.get('category'))} · {esc(s.get('confidence'))}</div><h3>{esc(s.get('headline'))}</h3><div class='sum'>{esc(s.get('summary'))}</div>{why}{perspectives}<div class='src'>{esc(s.get('source'))} · {esc(s.get('published'))}</div><a class='btn' href='{esc(s.get('url'))}'>Read source article</a></div></div>"

briefings = []
for path in DATA.glob("*.json"):
    try:
        item = json.loads(path.read_text())
        generated = datetime.fromisoformat(item["generated_at"])
        if datetime.now(generated.tzinfo) - generated <= timedelta(days=CFG.get("archive_days", 8)): briefings.append(item)
    except Exception: pass
briefings.sort(key=lambda x: x["generated_at"], reverse=True)
if not briefings:
    st.warning("No briefings are available yet. Run the briefing workflow once."); st.stop()
with st.sidebar:
    st.title("🗓️ Briefing Archive")
    labels = [f"{datetime.fromisoformat(b['generated_at']).strftime('%A, %b %d')} · {b['edition']}" for b in briefings]
    selected = st.radio("Edition", range(len(briefings)), format_func=lambda i: labels[i], label_visibility="collapsed")
    st.divider(); st.link_button("Support via Venmo", "https://venmo.com/u/jhsacks", use_container_width=True)
    if QR.exists(): st.image(str(QR), caption="Zelle: scan the QR code", use_container_width=True)
brief = briefings[selected]; generated = datetime.fromisoformat(brief["generated_at"])
stories = brief.get("stories", []); more = brief.get("more_stories", {})
st.markdown(f"<div class='hero'><h1>{esc(CFG['title'])}</h1><p>{esc(CFG['tagline'])}</p></div><div class='edition'>{generated.strftime('%A, %B %d, %Y')} · <b>{brief['edition']} edition</b></div>", unsafe_allow_html=True)
st.markdown("<div class='support'><b>I hope you like this site!</b> It is reader-supported. <a href='https://venmo.com/u/jhsacks'>Support via Venmo</a></div>", unsafe_allow_html=True)
for category in CFG["category_order"]:
    st.header(category)
    group = [s for s in stories if s.get("category") == category]
    if not group:
        st.markdown("<div class='empty'><div class='cricket'>🦗</div><b>Quiet in this section.</b><br>No fresh story cleared the quality bar for this edition.</div>", unsafe_allow_html=True)
    else:
        columns = st.columns(2)
        for index, story in enumerate(group):
            with columns[index % 2]: st.markdown(story_card(story), unsafe_allow_html=True)
    links = more.get(category, [])
    if links:
        st.markdown("<div class='more'><b>More worth a look</b><ul>" + "".join(f"<li><a href='{esc(x['url'])}'>{esc(x['headline'])}</a> <span class='src'>· {esc(x.get('source'))}</span></li>" for x in links) + "</ul></div>", unsafe_allow_html=True)
