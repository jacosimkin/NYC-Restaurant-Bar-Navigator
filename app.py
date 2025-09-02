# app.py
# NYC Restaurant & Bar Navigator – Split Hero + Gated Business Plan Template

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
        --text:#F5FAFF;
        --muted:#C4D0DB;
        --brand:#0ea5e9;     /* cyan */
        --violet:#7c3aed;    /* violet */
        --stroke:rgba(148,163,184,.32);
        --card:rgba(255,255,255,.08);
        --glass:rgba(13,20,35,.72);
      }
      .stApp {
        color: var(--text);
        background: radial-gradient(900px 480px at 15% -10%, rgba(124,58,237,.22), transparent 50%),
                    radial-gradient(1100px 560px at 120% 0%, rgba(14,165,233,.22), transparent 55%),
                    var(--bg);
      }
      .block-container{padding-top:1.0rem; max-width:1150px;}
      p, li { line-height: 1.55; }

      /* Top nav */
      .topnav{
        position: sticky; top: 0; z-index: 50;
        backdrop-filter: saturate(180%) blur(10px);
        background: linear-gradient(180deg, rgba(11,18,32,.95), rgba(11,18,32,.65));
        border-bottom:1px solid var(--stroke);
        padding:.75rem 0 .65rem 0; margin-bottom:.8rem;
      }
      .brand{font-weight:800;font-size:1.06rem; letter-spacing:.2px}
      .navright a{
        text-decoration:none; color:var(--text); opacity:.96; margin-left:16px; font-size:1rem;
        padding:6px 8px; border-radius:10px;
      }
      .navright a:hover{ background: rgba(255,255,255,.06); }
      .navright a.active{ color:#E2F3FF; background: rgba(14,165,233,.18); border:1px solid rgba(14,165,233,.45); }

      /* Split hero */
      .hero{
        border:1px solid var(--stroke); border-radius:22px;
        background: linear-gradient(135deg, rgba(14,165,233,.22), rgba(124,58,237,.20)), var(--glass);
        padding: 22px; box-shadow: 0 22px 44px rgba(2,8,23,.45);
      }
      .pill{
        display:inline-flex; gap:8px; align-items:center;
        padding:7px 11px; border-radius:999px;
        background:rgba(14,165,233,.22); border:1px solid rgba(14,165,233,.50);
        color:var(--text); font-size:.84rem; margin-bottom:10px; font-weight:600;
      }
      .headline{ font-size:2.15rem; line-height:1.08; margin:.2rem 0 .55rem 0; font-weight:900; }
      .sub{ color:var(--muted); font-size:1.05rem; margin:0 0 .6rem 0; }
      .cta{
        display:inline-block; padding:13px 18px; border-radius:12px;
        background:linear-gradient(135deg, var(--brand), #22d3ee);
        color:#06131f; font-weight:800; text-decoration:none; font-size:1rem;
        border:1px solid rgba(255,255,255,.22); box-shadow:0 12px 34px rgba(14,165,233,.45);
      }
      .btn-secondary{
        display:inline-block; padding:12px 16px; border-radius:12px;
        background:rgba(255,255,255,.08); border:1px solid var(--stroke); color:var(--text);
        text-decoration:none; font-weight:700;
      }

      .card{ border:1px solid var(--stroke); background:var(--card); border-radius:16px; padding:16px; height:100%; }
      .sec-grid{display:grid; grid-template-columns: repeat(3,1fr); gap:16px;}
      .pricing{display:grid; grid-template-columns:repeat(3,1fr); gap:16px;}
      .section-title{ font-size:1.45rem; font-weight:900; margin:.8rem 0 .5rem 0; }
      .divider{ height:1px; background:var(--stroke); margin:20px 0; }
      .badge{
        display:inline-flex; align-items:center; gap:8px;
        border:1px solid var(--stroke); padding:7px 11px; border-radius:999px;
        margin-right:8px; margin-bottom:8px; font-size:.95rem; font-weight:600;
      }
      .footer{margin: 24px 0 30px 0; color:var(--muted); font-size:.95rem}

      /* Hide default sidebar */
      [data-testid="collapsedControl"], [data-testid="stSidebar"] { display:none; }
      /* Inputs: readable labels */
      label, .stTextInput label, .stSelectbox label, .stTextArea label { font-weight:700; color:#ECF3FF; }
      /* Honeypot hide */
      label[for="honeypot"], input#honeypot {position:absolute;left:-10000px;width:1px;height:1px;overflow:hidden;}

      @media(max-width:980px){
        .sec-grid, .pricing { grid-template-columns: 1fr; }
        .headline{font-size:1.85rem;}
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

# ------------------------------- CONTENT -------------------------------------

def business_plan_template_md() -> str:
    """Simple, clean template the user can download after signup."""
    return f"""# NYC Restaurant & Bar – Business Plan Template

**Owner:**  
**Concept Name:**  
**Neighborhood / Borough:**  

---

## 1) Concept & Vision
- Cuisine / Beverage focus:
- Service model (full service, quick service, bar & lounge, café, bakery):
- Seating & capacity:
- Competitive edge / differentiation:

## 2) Market & Location
- Target customer:
- Foot traffic / demand drivers:
- Nearby competitors & price points:
- Seasonal considerations:

## 3) Operations
- Hours of operation:
- Staffing plan (roles & headcount):
- Supplier strategy (food, beverage):
- Technology stack (POS, reservation, delivery, back-office):

## 4) Compliance & Permits (NYC)
- DOH Food Service Establishment Permit
- FDNY hood & suppression (if grease cooking)
- DOB filings / CO (if build-out or occupancy change)
- SLA on-premise license (if serving alcohol) + Community Board
- DOT Outdoor Dining (if sidewalk/roadway seating)

> Tip: Use our AI Navigator to generate a personalized permit roadmap with timelines and links.

## 5) Menu & Pricing
- Sample menu highlights:
- Cost of goods targets:
- Pricing strategy:

## 6) Marketing & Launch
- Brand / story:
- Opening plan (soft launch vs grand opening):
- Partnerships / PR / influencers:
- Loyalty & retention plan:

## 7) Financials (Year 1)
- Startup budget (build-out, equipment, working capital):
- Revenue projections (by daypart / channel):
- Key assumptions (check average, turns, occupancy):
- Breakeven analysis:

## 8) Risks & Mitigations
- Top 3 risks:
- Mitigation plans:

## 9) Milestones & Timeline
- Lease signed:
- Build-out start / inspections:
- Hiring:
- Opening day target:

---

*Generated by {APP_NAME}. This is an editable template; adapt to your concept.*
"""

# ------------------------------- UI UTILS ------------------------------------

def top_nav(active:str):
    st.markdown(f"""
    <div class="topnav">
      <div style="display:flex;align-items:center;justify-content:space-between;">
        <div class="brand">🍽️ {APP_NAME}</div>
        <div class="navright">
          <a href="?page=landing" class="{ 'active' if active=='landing' else ''}">Landing</a>
          <a href="?page=about" class="{ 'active' if active=='about' else ''}">About</a>
          <a href="#lead-form">Join Waitlist</a>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ------------------------------- PAGES ---------------------------------------

def landing_page():
    # Split hero: left copy, right form card
    st.markdown('<a name="top"></a>', unsafe_allow_html=True)
    with st.container():
        st.markdown('<section class="hero">', unsafe_allow_html=True)
        col_left, col_right = st.columns([6,5], gap="large")
        with col_left:
            st.markdown("""
                <div class="pill">NYC Restaurants & Bars · Early Access ✨</div>
                <h1 class="headline">Open your spot without opening a law book.</h1>
                <p class="sub">AI that turns NYC permits into a personalized, step-by-step roadmap — with official links and timelines.</p>
                <div style="display:flex;gap:12px;margin-top:10px;flex-wrap:wrap;">
                    <a class="cta" href="#lead-form">Get My Roadmap</a>
                    <a class="btn-secondary" href="?page=about">Learn more</a>
                </div>
            """, unsafe_allow_html=True)
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            st.markdown(
                "<span style='color:#dbeafe;font-weight:700'>Designed in NYC</span> · Backed by DOH · FDNY · DOB · SLA · DOT citations",
                unsafe_allow_html=True,
            )
        with col_right:
            st.markdown('<a name="lead-form"></a>', unsafe_allow_html=True)
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown("**Join the NYC launch list**  \nTell us about your concept.")
            if "visit_ts" not in st.session_state: st.session_state.visit_ts=time.time()
            with st.form("waitlist", clear_on_submit=False):
                name = st.text_input("First & Last Name*").strip()
                email = st.text_input("Email*").strip()
                business = st.selectbox("Business Type*", ["Restaurant","Bar","Cafe","Bakery"])
                borough = st.selectbox("Borough*", ["Manhattan","Brooklyn","Queens","Bronx","Staten Island"])
                alcohol = st.selectbox("Will you serve alcohol?*", ["Yes","No"])
                timeframe = st.selectbox("Estimated opening*", ["Now","1–3 months","3–6 months","Exploring"])
                notes = st.text_area("Notes (optional)", height=70, placeholder="Concept, size, unique angle…")
                hp = st.text_input(" ", key="honeypot", label_visibility="hidden")
                ok = st.checkbox("I agree to be contacted about early access and product updates.", value=True)
                submit = st.form_submit_button("Get My Roadmap ✉️")
            if submit:
                errs=[]
                if not name: errs.append("Full name is required.")
                if not valid_email(email): errs.append("Please enter a valid email.")
                if not ok: errs.append("Please agree to be contacted about early access.")
                if hp: errs.append("Submission flagged. Please try again.")
                if time.time()-st.session_state.visit_ts < 3: errs.append("Form submitted too quickly. Please try again.")
                if errs:
                    for e in errs: st.error(e)
                else:
                    record = {
                        "full_name": name, "email": email.lower(), "phone":"",
                        "business_type": business, "borough": borough,
                        "alcohol": alcohol.lower(), "outdoor_seating": "",
                        "launch_timeframe": timeframe, "role": "Owner/Operator",
                        "notes": notes, "source_page": "landing",
                    }
                    is_new = persist_to_csv(record)
                    post_webhook(record); push_google_sheet(record)
                    st.session_state.signed_up = True
                    if is_new:
                        st.success("You're on the list! Your business plan template is ready below.")
                        st.balloons()
                    else:
                        st.info("You're already on the list. Your template is ready below.")
            # Gated download appears beneath the form card
            if st.session_state.get("signed_up"):
                st.markdown("<hr/>", unsafe_allow_html=True)
                st.markdown("**Download: Restaurant/Bar Business Plan Template (Markdown)**")
                tpl = business_plan_template_md().encode("utf-8")
                st.download_button(
                    "Download Template (.md)",
                    data=tpl,
                    file_name="NYC_Restaurant_Business_Plan_Template.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)  # end card
        st.markdown("</section>", unsafe_allow_html=True)

    # Trust band
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    c1,c2,c3 = st.columns(3)
    with c1: st.markdown("**🔒 Privacy-first**  \nWe only use your info for updates.")
    with c2: st.markdown("**🏙️ NYC-specific**  \nBuilt for DOH, FDNY, DOB, SLA, DOT.")
    with c3: st.markdown("**⚡ AI-native**  \nClear guidance with citations — not generic checklists.")

    # Resource teasers (Toast-style)
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Starter resources</div>', unsafe_allow_html=True)
    res1, res2, res3 = st.columns(3)
    with res1:
        st.markdown("**Liquor License: Community Board Prep**")
        st.caption("Checklist for SLA notices, timelines, and typical pitfalls.")
    with res2:
        st.markdown("**Health Dept. Pre-Inspection Tips**")
        st.caption("Common DOH findings and how to avoid them.")
    with res3:
        st.markdown("**Outdoor Dining Rules (DOT)**")
        st.caption("Clear path requirements, barriers, hours.")

    # Pricing preview
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Simple pricing (coming soon)</div>', unsafe_allow_html=True)
    grid = st.columns(3)
    with grid[0]: st.markdown("**Free**  \nChecklist preview • Links & citations")
    with grid[1]: st.markdown("**Pro ($49/mo)**  \nFull roadmap • Doc checklists • Reminders • PDF export")
    with grid[2]: st.markdown("**Premium ($199/project)**  \nForm autofill • Optional human review • Priority support")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    faq()
    footer()

def about_page():
    st.markdown("""
    <div class="section-title">Why this exists</div>
    <div class="card">
      <b>Our mission</b> is simple: make opening a restaurant or bar in NYC clear, fast, and fair.<br><br>
      <b>The problem:</b> A maze of agencies, portals, forms, inspections, and unwritten rules (DOH, FDNY, DOB, SLA, DOT). 
      Most operators burn weeks and thousands on avoidable confusion.<br><br>
      <b>Our solution:</b> An AI guide that asks plain-English questions about your concept and location, then generates a personalized permit roadmap with documents, fees, timelines, and source links — like a <i>TurboTax for permits</i>.
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">What you’ll get at launch</div>', unsafe_allow_html=True)
    c1,c2,c3 = st.columns(3)
    with c1: st.markdown("✅ Tailored permit checklist (restaurants & bars)")
    with c2: st.markdown("🧾 Required documents + prep templates")
    with c3: st.markdown("⏱️ Estimated fees & timelines")

    st.markdown('<div class="section-title">What’s next</div>', unsafe_allow_html=True)
    c4,c5,c6 = st.columns(3)
    with c4: st.markdown("🖊️ Autofill common forms")
    with c5: st.markdown("🔔 Reminders for deadlines & renewals")
    with c6: st.markdown("👩‍⚖️ Optional human review (vetted partners)")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Join the NYC launch list</div>', unsafe_allow_html=True)
    st.caption("Sign up to unlock the Business Plan Template and early access.")

    if "visit_ts_about" not in st.session_state: st.session_state.visit_ts_about=time.time()
    with st.form("about_form", clear_on_submit=False):
        name = st.text_input("First & Last Name*", key="an").strip()
        email = st.text_input("Email*", key="ae").strip()
        business = st.selectbox("Business Type*", ["Restaurant","Bar","Cafe","Bakery"], key="ab")
        timeframe = st.selectbox("Estimated opening*", ["Now","1–3 months","3–6 months","Exploring"], key="at")
        hp = st.text_input(" ", key="ahp", label_visibility="hidden")
        ok = st.checkbox("I agree to be contacted about early access and product updates.", value=True, key="ap")
        submit = st.form_submit_button("Get My Roadmap ✉️")
    if submit:
        errs=[]
        if not name: errs.append("Full name is required.")
        if not valid_email(email): errs.append("Please enter a valid email.")
        if not ok: errs.append("Please agree to be contacted about early access.")
        if hp: errs.append("Submission flagged. Please try again.")
        if time.time()-st.session_state.visit_ts_about < 3: errs.append("Form submitted too quickly. Please try again.")
        if errs:
            for e in errs: st.error(e)
        else:
            record = {
                "full_name": name, "email": email.lower(), "phone":"",
                "business_type": business, "borough": "",
                "alcohol": "", "outdoor_seating": "",
                "launch_timeframe": timeframe, "role": "Owner/Operator",
                "notes": "", "source_page": "about",
            }
            is_new = persist_to_csv(record)
            post_webhook(record); push_google_sheet(record)
            st.session_state.signed_up = True
            if is_new:
                st.success("You're on the list! Your business plan template is ready below.")
                st.balloons()
            else:
                st.info("You're already on the list. Your template is ready below.")

    if st.session_state.get("signed_up"):
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        st.markdown("**Download: Restaurant/Bar Business Plan Template (Markdown)**")
        tpl = business_plan_template_md().encode("utf-8")
        st.download_button(
            "Download Template (.md)",
            data=tpl,
            file_name="NYC_Restaurant_Business_Plan_Template.md",
            mime="text/markdown",
            use_container_width=True,
        )

    footer()

# ------------------------------- SHARED SECTIONS ------------------------------

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

# ------------------------------- ROUTER --------------------------------------

def main():
    st.set_page_config(page_title=f"{APP_NAME} · Early Access", page_icon="🍽️", layout="wide")
    inject_css()

    qs = st.query_params
    page = qs.get("page", ["landing"])[0] if isinstance(qs.get("page"), list) else qs.get("page","landing")
    if page not in ("landing","about"): page = "landing"

    # top nav
    st.markdown(f"""
    <div class="topnav">
      <div style="display:flex;align-items:center;justify-content:space-between;">
        <div class="brand">🍽️ {APP_NAME}</div>
        <div class="navright">
          <a href="?page=landing" class="{ 'active' if page=='landing' else ''}">Landing</a>
          <a href="?page=about" class="{ 'active' if page=='about' else ''}">About</a>
          <a href="#lead-form">Join Waitlist</a>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    landing_page() if page=="landing" else about_page()

if __name__ == "__main__":
    main()
