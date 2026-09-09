import os, re, html, requests
from urllib.parse import quote

VENMO_URL = "https://venmo.com/u/jhsacks"
SITE_URL = os.getenv("NEWSLETTER_BASE_URL", "https://balancedbrief.streamlit.app/").rstrip("/") + "/"

def _secret(name, secrets=None):
    if secrets is not None:
        try:
            value = secrets.get(name, "")
            if value:
                return str(value)
        except Exception:
            pass
    return os.getenv(name, "")

def valid_email(value):
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", (value or "").strip()))

def subscribe(email, preference, secrets=None):
    email = (email or "").strip().lower()
    if not valid_email(email): return False, "Please enter a valid email address."
    if preference not in {"AM", "PM", "BOTH"}: return False, "Please select an edition."
    url = _secret("SUPABASE_URL", secrets).rstrip("/"); key = _secret("SUPABASE_ANON_KEY", secrets)
    if not url or not key: return False, "Email signup is not configured yet."
    try:
        response = requests.post(f"{url}/rest/v1/rpc/subscribe_newsletter", headers={"apikey":key,"Authorization":f"Bearer {key}","Content-Type":"application/json"}, json={"p_email":email,"p_preference":preference}, timeout=12)
    except requests.RequestException:
        return False, "Signup could not connect. Please try again."
    if response.ok: return True, "You're subscribed. Your edition choice has been saved."
    return False, f"Signup failed ({response.status_code}): {response.text}"

def unsubscribe(token, secrets=None):
    if not token: return False
    url = _secret("SUPABASE_URL", secrets).rstrip("/"); key = _secret("SUPABASE_ANON_KEY", secrets)
    if not url or not key: return False
    try:
        return requests.post(f"{url}/rest/v1/rpc/unsubscribe_newsletter", headers={"apikey":key,"Authorization":f"Bearer {key}","Content-Type":"application/json"}, json={"p_token":token}, timeout=12).ok
    except requests.RequestException:
        return False

def _story_html(story):
    e=lambda x:html.escape(str(x or ""))
    image=f'<img src="{e(story.get("image"))}" alt="" style="width:100%;max-height:260px;object-fit:cover;display:block">' if story.get("image") else ""
    why=f'<p style="line-height:1.6"><strong>Why it matters:</strong> {e(story.get("why_it_matters"))}</p>'
    views=[]
    if story.get("perspective_one"): views.append(f'<p><strong>One perspective:</strong> {e(story["perspective_one"])}</p>')
    if story.get("perspective_two"): views.append(f'<p><strong>Another perspective:</strong> {e(story["perspective_two"])}</p>')
    perspectives=('<div style="padding:12px;background:#eff8f6;border-left:4px solid #0f766e"><strong>Where perspectives differ</strong>'+''.join(views)+'</div>') if views else ""
    return f'<div style="border:1px solid #dfe7eb;border-radius:12px;margin-bottom:18px;overflow:hidden">{image}<div style="padding:16px"><div style="font-size:12px;color:#0f766e;font-weight:700">{e(story.get("category"))}</div><h2>{e(story.get("headline"))}</h2><p style="line-height:1.6">{e(story.get("summary"))}</p>{why}{perspectives}<p><a href="{e(story.get("url"))}" style="color:#0f766e;font-weight:700">Read source article</a></p></div></div>'

def email_html(briefing, token):
    stories=briefing.get("stories",[]); sections=[]
    for category in dict.fromkeys(s.get("category") for s in stories if s.get("category")):
        sections.append(f'<h1>{html.escape(category)}</h1>'+''.join(_story_html(s) for s in stories if s.get("category")==category))
    unsubscribe_url=f"{SITE_URL}?unsubscribe={quote(str(token))}"
    return f'<!doctype html><html><body style="background:#f4f7f8;font-family:Arial,sans-serif;color:#182536"><div style="max-width:720px;margin:auto;padding:18px"><div style="background:#123b5d;color:white;padding:16px 20px;border-radius:14px"><div style="font-size:29px;font-weight:800">The Balanced Brief</div><div>Important news. Clear context. No outrage bait.</div></div>{"".join(sections)}<div style="padding:18px;background:#fff8e8;border:1px solid #f1d58a;border-radius:12px"><strong>Enjoying The Balanced Brief?</strong><br><a href="{VENMO_URL}">Support via Venmo</a></div><p style="font-size:12px;color:#718096">You received this because you subscribed. <a href="{unsubscribe_url}">Unsubscribe</a>.</p></div></body></html>'

def send_newsletter(briefing):
    supabase=_secret("SUPABASE_URL").rstrip("/"); service_key=_secret("SUPABASE_SERVICE_ROLE_KEY"); resend_key=_secret("RESEND_API_KEY"); from_email=_secret("NEWSLETTER_FROM_EMAIL")
    if not all((supabase,service_key,resend_key,from_email)):
        raise RuntimeError("Newsletter secrets are not configured in the workflow environment.")
    edition=str(briefing.get("edition","")).upper()
    response=requests.get(f"{supabase}/rest/v1/newsletter_subscribers",headers={"apikey":service_key,"Authorization":f"Bearer {service_key}"},params={"select":"email,preference,unsubscribe_token","active":"eq.true","or":f"(preference.eq.{edition},preference.eq.BOTH)"},timeout=15)
    print("STATUS:", response.status_code)
print("BODY:", response.text)

response.raise_for_status()
subscribers=response.json()
sent=0
    for subscriber in subscribers:
        mail=requests.post("https://api.resend.com/emails",headers={"Authorization":f"Bearer {resend_key}","Content-Type":"application/json"},json={"from":from_email,"to":[subscriber["email"]],"subject":f"The Balanced Brief · {edition} Edition","html":email_html(briefing,subscriber["unsubscribe_token"])},timeout=20)
        if not mail.ok: raise RuntimeError(f"Resend failed ({mail.status_code}): {mail.text}")
        sent+=1
    print(f"Newsletter emails sent: {sent}")
    return sent
