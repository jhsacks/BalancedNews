import os, re, html, requests
from urllib.parse import quote

VENMO_URL = "https://venmo.com/u/jhsacks"
SITE_URL = os.getenv("NEWSLETTER_BASE_URL", "https://balancednews.streamlit.app/").rstrip("/") + "/"


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
    if not valid_email(email):
        return False, "Please enter a valid email address."
    if preference not in {"AM", "PM", "BOTH"}:
        return False, "Please select an edition."
    url = _secret("SUPABASE_URL", secrets).rstrip("/")
    key = _secret("SUPABASE_ANON_KEY", secrets)
    if not url or not key:
        return False, "Email signup is not configured yet."
    response = requests.post(
        f"{url}/rest/v1/rpc/subscribe_newsletter",
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"p_email": email, "p_preference": preference}, timeout=12,
    )
    if response.ok:
        return True, "You're subscribed. Your edition choice has been saved."
    return False, f"Signup failed ({response.status_code}): {response.text}"


def unsubscribe(token, secrets=None):
    if not token:
        return False
    url = _secret("SUPABASE_URL", secrets).rstrip("/")
    key = _secret("SUPABASE_ANON_KEY", secrets)
    if not url or not key:
        return False
    response = requests.post(
        f"{url}/rest/v1/rpc/unsubscribe_newsletter",
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"p_token": token}, timeout=12,
    )
    return response.ok


def _story_html(story):
    e = lambda x: html.escape(str(x or ""))
    image = f'<img src="{e(story.get("image"))}" alt="" style="width:100%;max-height:260px;object-fit:cover;border-radius:12px 12px 0 0;display:block">' if story.get("image") else ""
    why = f'<p style="margin:10px 0 0"><strong>Why it matters:</strong> {e(story.get("why_it_matters"))}</p>' if story.get("why_it_matters") else ""
    views = []
    if story.get("perspective_one"):
        views.append(f'<p style="margin:6px 0"><strong>One perspective:</strong> {e(story["perspective_one"])}</p>')
    if story.get("perspective_two"):
        views.append(f'<p style="margin:6px 0"><strong>Another perspective:</strong> {e(story["perspective_two"])}</p>')
    perspective = ('<div style="margin-top:12px;padding:11px 13px;background:#eff8f6;border-left:4px solid #0f766e"><strong style="color:#165f5a">Where perspectives differ</strong>' + ''.join(views) + '</div>') if views else ""
    return f'''<div style="border:1px solid #dfe7eb;border-radius:12px;margin:0 0 18px;overflow:hidden;background:#fff">{image}<div style="padding:16px"><div style="font-size:12px;font-weight:700;color:#0f766e;text-transform:uppercase">{e(story.get('category'))} · {e(story.get('confidence'))}</div><h2 style="font-size:22px;line-height:1.25;margin:7px 0 10px;color:#142235">{e(story.get('headline'))}</h2><p style="line-height:1.6;margin:0">{e(story.get('summary'))}</p>{why}{perspective}<p style="margin:12px 0 0"><a href="{e(story.get('url'))}" style="color:#0f766e;font-weight:700">Read source article</a></p></div></div>'''


def email_html(briefing, unsubscribe_token):
    edition = briefing.get("edition", "")
    sections = []
    stories = briefing.get("stories", [])
    for category in dict.fromkeys(s.get("category") for s in stories if s.get("category")):
        cards = ''.join(_story_html(s) for s in stories if s.get("category") == category)
        sections.append(f'<h1 style="font-size:26px;color:#142235;margin:28px 0 12px">{html.escape(category)}</h1>{cards}')
    unsubscribe_url = f"{SITE_URL}?unsubscribe={quote(str(unsubscribe_token))}"
    return f'''<!doctype html><html><body style="margin:0;background:#f4f7f8;font-family:Arial,sans-serif;color:#182536"><div style="max-width:720px;margin:auto;padding:18px"><div style="background:linear-gradient(110deg,#123b5d,#0f766e);color:white;padding:16px 20px;border-radius:14px"><div style="font-size:29px;font-weight:800">The Balanced Brief</div><div style="margin-top:4px">Important news. Clear context. No outrage bait.</div></div><p style="color:#60717a">{html.escape(edition)} edition</p>{''.join(sections)}<div style="margin-top:28px;padding:18px;background:#fff8e8;border:1px solid #f1d58a;border-radius:12px"><strong>Enjoying The Balanced Brief?</strong><br><a href="{VENMO_URL}" style="color:#0f766e;font-weight:700">Support via Venmo</a></div><p style="font-size:12px;color:#718096;line-height:1.5">You received this because you subscribed on The Balanced Brief. <a href="{unsubscribe_url}">Unsubscribe</a>.</p></div></body></html>'''


def send_newsletter(briefing):
    supabase = _secret("SUPABASE_URL").rstrip("/")
    service_key = _secret("SUPABASE_SERVICE_ROLE_KEY")
    resend_key = _secret("RESEND_API_KEY")
    from_email = _secret("NEWSLETTER_FROM_EMAIL")
    if not all((supabase, service_key, resend_key, from_email)):
        print("Newsletter delivery skipped: email secrets are not configured.")
        return 0
    edition = str(briefing.get("edition", "")).upper()
    headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
    response = requests.get(
        f"{supabase}/rest/v1/newsletter_subscribers",
        headers=headers,
        params={"select": "email,preference,unsubscribe_token", "active": "eq.true", "or": f"(preference.eq.{edition},preference.eq.BOTH)"}, timeout=15,
    )
    response.raise_for_status()
    subscribers = response.json()
    sent = 0
    for subscriber in subscribers:
        mail = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
            json={"from": from_email, "to": [subscriber["email"]], "subject": f"The Balanced Brief · {edition} Edition", "html": email_html(briefing, subscriber["unsubscribe_token"])}, timeout=20,
        )
        if mail.ok:
            sent += 1
        else:
            print("Newsletter send failed:", mail.status_code, mail.text[:300])
    print("Newsletter emails sent:", sent)
    return sent
