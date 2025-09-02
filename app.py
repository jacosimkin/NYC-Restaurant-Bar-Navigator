# app.py
# NYC Restaurant & Bar Navigator – Modern Landing (Streamlit)

from __future__ import annotations

import os, re, json, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

import pandas as pd
import streamlit as st

# Optional deps
try:
    import requests  # for webhook
except Exception:
    requests = None

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
except Exception:
    gspread = None
    ServiceAccountCredentials = None

APP_NAME = "NYC Restaurant & Bar Navigator"
DATA_DIR = Path("data"); DATA_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = DATA_DIR / "waitlist.csv"

# --------------------------- THEME + GLOBAL CSS -------------------------------

def inject_css():
    st.markdown("""
    <style>
      :root{
        --bg:#0b1220;
        --bg-2:#0e1626;
        --panel:#0f192c;
        --text:#f8fafc;
        --muted:#9aa6b2;
        --brand:#0ea5e9;
        --brand-2:#7c3aed;
        --ok:#22c55e;
        --card:rgba(255,255,255,.04);
        --stroke:rgba(148,163,184,.18);
        --glass:rgba(13,20,35,.55);
      }
      .stApp { background: radial-gradient(1000px 500px at 20% -10%, rgba(124,58,237,.15), transparent 50%),
                           radial-gradient(1200px 600px at 120% 0%, rgba(14,165,233,.15), transparent 50%),
                           var(--bg); }
      .block-container{padding-top:1.2rem; max-width:1100px;}
      /* Top nav */
      .topnav{
        position: sticky; top: 0; z-index: 50;
        backdrop-filter: saturate(180%) blur(8px);
        background: linear-gradient(180deg, rgba(11,18,32,.9), rgba(11,18,32,.6));
        border-bottom:1px solid var(--stroke);
        padding: .7rem 0 .6rem 0; margin-bottom: .6rem;
      }
      .brand{font-weight:700;font-size:1.05rem; letter-spacing:.2px}
      .navright a{
        text-decoration:none; color:var(--text); opacity:.85; margin-left:14px; font-size:.95rem;
      }
      .navright a.active{color:var(--brand); opacity:1; font-weight:600}
      /* Hero */
      .hero{
        position:relative; overflow:hidden;
        border:1px solid var(--stroke); border-radius:22px;
        background: linear-gradient(135deg, rgba(14,165,233,.16), rgba(124,58,237,.14)) , var(--glass);
        padding: 26px 26px 22px 26px; box-shadow: 0 20px 40px rgba(2,8,23,.35);
      }
      .pill{
        display:inline-flex; gap:8px; align-items:center;
        padding:6px 10px; border-radius:999px;
        background:rgba(14,165,233,.18); border:1px solid rgba(14,165,233,.35);
        color:var(--text); font-size:.82rem; margin-bottom:8px;
      }
      .headline{font-size:2.2rem; line-height:1.05; margin:.1rem 0 .5rem 0; font-weight:800;}
      .sub{color:var(--muted); margin:0 0 .4rem 0}
      .cta{
        display:inline-block; padding:12px 16px; border-radius:12px;
        background:linear-gradient(135deg, var(--brand), #22d3ee);
        color:#06121f; font-weight:700; text-decoration:none;
        border:1px solid rgba(255,255,255,.18); box-shadow:0 10px 30px rgba(14,165,233,.35);
      }
      .sec-grid{display:grid; grid-template-columns: repeat(3,1fr); gap:16px;}
      .card{
        border:1px solid var(--stroke); background:var(--card);
        border-radius:16px; padding:16px; height:100%;
      }
      .muted{ color:var(--muted); }
      .badge{
        display:inline-flex; align-items:center; gap:8px;
        border:1px solid var(--stroke); padding:6px 10px; border-radius:999px;
        margin-right:8px; margin-bottom:8px; font-size:.9rem;
      }
      .section-title{ font-size:1.35rem; font-weight:800; margin:.6rem 0 .4rem 0; }
      .divider{ height:1px; background:var(--stroke); margin:18px 0; }
      .pricing{display:grid; grid-template-columns:repeat(3,1fr); gap:16px;}
      .kicker{color:#a5b4fc; font-weight:700; font-size:.9rem; letter-spacing:.06em;}
      .footer{margin: 22px 0 30px 0; color:var(--muted); font-size:.9rem}
      /* Buttons */
      .btn-secondary{
        display:inline-block; padding:10px 14px; border-radius:12px;
        background:rgba(255,255,255,.04); border:1px solid var(--stroke); color:var(--text);
        text-decoration:none;
      }
      /* Hide default sidebar toggle */
      [data-testid="collapsedControl"], [data-testid="stSidebar"] { display:none; }
      /* Honeypot hide */
      label[for="honeypot"], input#honeypot {position:absolute;left:-10000px;width:1px;height:1px;overflow:hidden;}
      @media(max-width:900px){
        .sec-grid, .pricing { grid-template-columns: 1fr; }
        .headline{font-size:1.8rem;}
      }
    </style>
    """, unsafe_allow_html=True)

# --------------------------- STORAGE & INTEGRATIONS ---------------------------

EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
def valid_email(email:str)->bool: return bool(email and EMAIL_RE.match(email))

def load_existing()->pd.DataFrame:
    if CSV_PATH.exists():
        try: return pd.read_csv(CSV_PATH)
        except Exception: return pd.DataFrame()
    return pd.DataFrame()

def persist_to_csv(record:Dict[str,Any])->bool:
    df=load_existing(); email=record.get("email","").strip().lower()
    if "email" in df.columns and email in df["email"].astype(str).str.lower().tolist():
        return False
    row=pd.DataFrame([{**record,"created_utc":datetime.now(timezone.utc).isoformat()}])
    out=pd.concat([df,row], ignore_index=True); out.to_csv(CSV_PATH, index=False); return True

def post_webhook(record:Dict[str,Any])->None:
    if not requests or os.getenv("USE_WEBHOOK","false").lower()!="true": return
    url=os.getenv("WEBHOOK_URL","").strip(); 
    if not url: return
    try: requests.post(url, json=record, timeout=10)
    except Exception: pass

def push_google_sheet(record:Dict[str,Any])->None:
    if not gspread or not ServiceAccountCredentials: return
    if os.getenv("USE_GOOGLE_SHEETS","false").lower()!="true": return
    try:
        creds_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"); creds_path=os.getenv("GOOGLE_CREDENTIALS_FILE")
        scope=["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
        if creds_json:
            info=json.loads(creds_json); creds=ServiceAccountCredentials.from_json_keyfile_dict(info, scope)
        elif creds_path and Path(creds_path).exists():
            creds=ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        else: return
        client=gspread.authorize(creds)
        sh=client.open_by_key(os.getenv("GOOGLE_SHEET_ID",""))
        try: ws=sh.worksheet("Waitlist")
        except gspread.WorksheetNotFound:
            ws=sh.add_worksheet(title="Waitlist", rows=1000, cols=20)
            ws.append_row(["created_utc","full_name","email","phone","business_type","borough",
                           "alcohol","outdoor_seating","launch_timeframe","role","notes","source_page"])
        ws.append_row([
            datetime.now(timezone.utc).isoformat(),
            record.get("full_name",""), record.get("email",""), record.get("phone",""),
            record.get("business_type",""), record.get("borough",""),
            record.get("alcohol",""), record.get("outdoor_seating",""),
            record.get("launch_timeframe",""), record.get("role",""),
            record.get("notes",""), record.get("source_page","landing")
        ])
    except Exception: pass

# ------------------------------- UI UTILITIES --------------------------------

def top_nav(active:str):
    st.markdown(f"""
    <div class="topnav">
      <div style="display:flex;align-items:center;justify-content:space-between;">
        <div class="brand">🍽️ {APP_NAME}</div>
        <div class="navright">
          <a href="?page=landing" class="{ 'active' if active=='landing' else ''}">Landing</a>
          <a href="?page=about" class="{ 'active' if active=='about' else ''}">About</a>
          <a href="#lead-form" class="">Join Waitlist</a>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

def hero():
    st.markdown("""
    <section class="hero">
      <div class="pill">NYC Restaurants & Bars · Early Access ✨</div>
      <h1 class="headline">Open your spot without opening a law book.</h1>
      <p class="sub">AI that turns NYC permits into a personalized, step-by-step roadmap — with official links and timelines.</p>
      <div style="display:flex;gap:10px;margin-top:8px;">
        <a class="cta" href="#lead-form">Request Early Access</a>
        <a class="btn-secondary" href="?page=about">Learn more</a>
      </div>
    </section>
    """, unsafe_allow_html=True)

def trust_band():
    st.markdown("""
    <div class="sec-grid" style="margin-top:12px;">
      <div class="card"><b>🔒 Privacy-first</b><br><span class="muted">We only use your info for updates.</span></div>
      <div class="card"><b>🏙️ NYC-specific</b><br><span class="muted">Built for DOH, FDNY, DOB, SLA, DOT.</span></div>
      <div class="card"><b>⚡ AI-native</b><br><span class="muted">Clear guidance with citations — not generic checklists.</span></div>
    </div>
    """, unsafe_allow_html=True)

def how_it_works():
    st.markdown('<div class="section-title">How it works</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="sec-grid">
      <div class="card"><b>1) Onboard</b><br><span class="muted">Describe your concept, location, and plans.</span></div>
      <div class="card"><b>2) AI chat</b><br><span class="muted">We ask smart follow-ups (alcohol, outdoor seating, build-out).</span></div>
      <div class="card"><b>3) Roadmap</b><br><span class="muted">Get permits, documents, fees, timelines, and official links.</span></div>
    </div>
    """, unsafe_allow_html=True)

def audience():
    st.markdown('<div class="section-title">Who is it for?</div>', unsafe_allow_html=True)
    st.markdown("""
      <div class="card">
        <span class="badge">🍝 Restaurant</span>
        <span class="badge">🍸 Bar</span>
        <span class="badge">☕ Cafe</span>
        <span class="badge">🥐 Bakery</span>
        <div class="muted" style="margin-top:6px;">From first-timers to seasoned operators.</div>
      </div>
    """, unsafe_allow_html=True)

def pricing():
    st.markdown('<div class="section-title">Simple pricing (coming soon)</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="pricing">
      <div class="card"><b>Free</b><br><span class="muted">Checklist preview • Links & citations</span></div>
      <div class="card"><b>Pro <span class="muted">($49/mo)</span></b><br><span class="muted">Full roadmap • Doc checklists • Reminders • PDF export</span></div>
      <div class="card"><b>Premium <span class="muted">($199/project)</span></b><br><span class="muted">Form autofill • Optional human review • Priority support</span></div>
    </div>
    """, unsafe_allow_html=True)

def faq():
    st.markdown('<div class="section-title">FAQ</div>', unsafe_allow_html=True)
    with st.expander("Is this legal advice?"):
        st.write("No. We provide educational guidance with citations to official NYC sources. For complex cases, we can refer you to licensed professionals.")
    with st.expander("Which agencies do you cover?"):
        st.write("We start with DOH, FDNY, DOB, SLA, and DOT for restaurants and bars in NYC.")
    with st.expander("When are you launching?"):
        st.write("We’re inviting early testers soon. Join the waitlist to get an invite.")
    with st.expander("How do you use my data?"):
        st.write("Strictly for contacting you about early access and updates. You can request deletion anytime.")

def footer():
    st.markdown(f"<div class='divider'></div><div class='footer'>© {datetime.now().year} {APP_NAME} · This is not legal advice.</div>", unsafe_allow_html=True)

# ------------------------------- PAGES ---------------------------------------

def landing_page():
    hero(); trust_band()
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    how_it_works(); audience()
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    pricing()
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    st.markdown('<a name="lead-form"></a>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Join the NYC launch list</div>', unsafe_allow_html=True)
    st.caption("Tell us about your concept. We’ll notify you as we open access.")

    if "visit_ts" not in st.session_state: st.session_state.visit_ts=time.time()

    with st.form("waitlist", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Full Name*").strip()
            email = st.text_input("Email*").strip()
            phone = st.text_input("Phone (optional)").strip()
            role = st.selectbox("Your role*", ["Owner","General Manager","Consultant","Other"])
        with c2:
            business = st.selectbox("Business Type*", ["Restaurant","Bar","Cafe","Bakery"])
            borough = st.selectbox("Borough*", ["Manhattan","Brooklyn","Queens","Bronx","Staten Island"])
            alcohol = st.selectbox("Will you serve alcohol?*", ["Yes","No"])
            outdoor = st.selectbox("Outdoor seating planned?*", ["Yes","No"])
        timeframe = st.selectbox("Target launch timeframe*", ["Now","1–3 months","3–6 months","Exploring"])
        notes = st.text_area("Anything else? (optional)", height=80)
        # Honeypot + consent
        hp = st.text_input(" ", key="honeypot", label_visibility="hidden")
        ok = st.checkbox("I agree to be contacted about early access and product updates.", value=True)
        submit = st.form_submit_button("Request Early Access ✉️")

    if submit:
        errs: List[str] = []
        if not name: errs.append("Full name is required.")
        if not valid_email(email): errs.append("Please enter a valid email.")
        if not ok: errs.append("Please agree to be contacted about early access.")
        if hp: errs.append("Submission flagged. Please try again.")
        if time.time()-st.session_state.visit_ts < 3: errs.append("Form submitted too quickly. Please try again.")
        if errs:
            for e in errs: st.error(e)
            return

        record = {
            "full_name": name, "email": email.lower(), "phone": phone,
            "business_type": business, "borough": borough,
            "alcohol": alcohol.lower(), "outdoor_seating": outdoor.lower(),
            "launch_timeframe": timeframe, "role": role, "notes": notes,
            "source_page": "landing",
        }
        is_new = persist_to_csv(record)
        post_webhook(record); push_google_sheet(record)

        if is_new:
            st.success("You're on the list! We’ll email you as we open access in NYC.")
            st.balloons()
        else:
            st.info("Looks like you’ve already signed up with this email. We’ll keep you posted!")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    faq(); footer()

def about_page():
    st.markdown("""
    <div class="kicker">ABOUT</div>
    <div class="section-title" style="margin-top:.2rem;">Why this exists</div>
    <div class="card">
      <b>Our mission</b> is simple: make opening a restaurant or bar in NYC clear, fast, and fair.<br><br>
      <b>The problem:</b> You face a maze of agencies, portals, forms, inspections, and unwritten rules (DOH, FDNY, DOB, SLA, DOT). 
      Most operators burn weeks and thousands on avoidable confusion.<br><br>
      <b>Our solution:</b> An AI guide that asks plain-English questions about your concept and location, then generates a personalized permit roadmap with documents, fees, timelines, and source links — like a <i>TurboTax for permits</i>.
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">What you’ll get at launch</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="sec-grid">
      <div class="card">✅ Tailored permit checklist (restaurants & bars)</div>
      <div class="card">🧾 Required documents + prep templates</div>
      <div class="card">⏱️ Estimated fees & timelines</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">What’s next</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="sec-grid">
      <div class="card">🖊️ Autofill common forms</div>
      <div class="card">🔔 Reminders for deadlines & renewals</div>
      <div class="card">👩‍⚖️ Optional human review (vetted partners)</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Responsible AI</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="card">
      We prioritize transparency: every recommendation links to official NYC sources. 
      This tool provides educational guidance and is <b>not legal advice</b>.
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Join the NYC launch list</div>', unsafe_allow_html=True)
    st.caption("Tell us about your concept. We’ll notify you as we open access.")

    if "visit_ts_about" not in st.session_state: st.session_state.visit_ts_about=time.time()
    with st.form("about_form", clear_on_submit=False):
        c1,c2 = st.columns(2)
        with c1:
            name = st.text_input("Full Name*", key="an").strip()
            email = st.text_input("Email*", key="ae").strip()
            role = st.selectbox("Your role*", ["Owner","General Manager","Consultant","Other"], key="ar")
        with c2:
            business = st.selectbox("Business Type*", ["Restaurant","Bar","Cafe","Bakery"], key="ab")
            timeframe = st.selectbox("Target launch timeframe*", ["Now","1–3 months","3–6 months","Exploring"], key="at")
        hp = st.text_input(" ", key="ahp", label_visibility="hidden")
        ok = st.checkbox("I agree to be contacted about early access and product updates.", value=True, key="ap")
        submit = st.form_submit_button("Request Early Access ✉️")

    if submit:
        errs=[]
        if not name: errs.append("Full name is required.")
        if not valid_email(email): errs.append("Please enter a valid email.")
        if not ok: errs.append("Please agree to be contacted about early access.")
        if hp: errs.append("Submission flagged. Please try again.")
        if time.time()-st.session_state.visit_ts_about < 3: errs.append("Form submitted too quickly. Please try again.")
        if errs:
            for e in errs: st.error(e)
            return
        record = {
            "full_name": name, "email": email.lower(), "role": role,
            "business_type": business, "launch_timeframe": timeframe,
            "notes":"", "borough":"", "alcohol":"", "outdoor_seating":"", "source_page":"about"
        }
        is_new = persist_to_csv(record); post_webhook(record); push_google_sheet(record)
        if is_new: st.success("You're on the list! We’ll email you as we open access in NYC."); st.balloons()
        else: st.info("Looks like you’ve already signed up with this email. We’ll keep you posted!")

    footer()

# ------------------------------- ROUTER --------------------------------------

def main():
    st.set_page_config(page_title=f"{APP_NAME} · Early Access", page_icon="🍽️", layout="wide")
    inject_css()

    # Basic querystring nav
    qs = st.query_params
    page = qs.get("page", ["landing"])[0] if isinstance(qs.get("page"), list) else qs.get("page","landing")
    if page not in ("landing","about"): page = "landing"

    top_nav(page)

    if page == "landing":
        landing_page()
    else:
        about_page()

if __name__ == "__main__":
    main()
