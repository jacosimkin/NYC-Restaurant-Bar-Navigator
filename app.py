# app.py
# NYC Restaurant & Bar Navigator – Landing + About (Streamlit)

from __future__ import annotations

import os
import re
import json
import time
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
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = DATA_DIR / "waitlist.csv"

# ──────────────────────────────────────────────────────────────────────────────
# Styling
# ──────────────────────────────────────────────────────────────────────────────

def inject_global_css() -> None:
    st.markdown(
        """
        <style>
            .block-container {padding-top: 2rem !important; max-width: 1100px !important;}
            body {
                background-image: radial-gradient(rgba(255,255,255,0.06) 1px, transparent 1px);
                background-size: 18px 18px;
            }
            .hero {
                background: linear-gradient(180deg, rgba(14,165,233,0.12), rgba(14,165,233,0.02));
                border: 1px solid rgba(148,163,184,0.25);
                border-radius: 18px; padding: 28px; margin-bottom: 18px;
            }
            .pill {display:inline-block;padding:6px 10px;border-radius:999px;
                   background:rgba(14,165,233,0.15);border:1px solid rgba(14,165,233,0.35);
                   font-size:0.8rem;margin-bottom:8px;}
            .card {border:1px solid rgba(148,163,184,0.25);background:rgba(255,255,255,0.02);
                   border-radius:16px;padding:18px;height:100%;}
            .muted { color: #94A3B8; } .small { font-size: 0.9rem; } .tiny { font-size: 0.8rem; }
            .badge {display:inline-block;border:1px solid rgba(148,163,184,0.35);
                   padding:4px 10px;border-radius:999px;margin:4px;font-size:0.85rem;}
            .footer {margin-top:26px;color:#94A3B8;font-size:0.85rem;}
            label[for="honeypot"], input#honeypot {position:absolute;left:-10000px;width:1px;height:1px;}
        </style>
        """,
        unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)

def valid_email(email: str) -> bool:
    return bool(email and EMAIL_RE.match(email))

def load_existing() -> pd.DataFrame:
    if CSV_PATH.exists():
        try:
            return pd.read_csv(CSV_PATH)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def persist_to_csv(record: Dict[str, Any]) -> bool:
    df = load_existing()
    email = record.get("email", "").strip().lower()
    ts = datetime.now(timezone.utc).isoformat()
    if "email" in df.columns and email in df["email"].astype(str).str.lower().tolist():
        return False
    row = pd.DataFrame([{**record, "created_utc": ts}])
    out = pd.concat([df, row], ignore_index=True)
    out.to_csv(CSV_PATH, index=False)
    return True

def post_webhook(record: Dict[str, Any]) -> None:
    if not requests or os.getenv("USE_WEBHOOK", "false").lower() != "true":
        return
    url = os.getenv("WEBHOOK_URL", "").strip()
    if not url: return
    try: requests.post(url, json=record, timeout=10)
    except Exception: pass

def push_google_sheet(record: Dict[str, Any]) -> None:
    if not gspread or not ServiceAccountCredentials: return
    if os.getenv("USE_GOOGLE_SHEETS", "false").lower() != "true": return
    try:
        creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        creds_path = os.getenv("GOOGLE_CREDENTIALS_FILE")
        if creds_json:
            info = json.loads(creds_json)
            scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scope)
        elif creds_path and Path(creds_path).exists():
            scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        else: return
        client = gspread.authorize(creds)
        sh = client.open_by_key(os.getenv("GOOGLE_SHEET_ID", ""))
        try: ws = sh.worksheet("Waitlist")
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title="Waitlist", rows=1000, cols=20)
            ws.append_row(["created_utc","full_name","email","phone","business_type",
                           "borough","alcohol","outdoor_seating","launch_timeframe","role","notes"])
        ws.append_row([datetime.now(timezone.utc).isoformat(),
                       record.get("full_name",""),record.get("email",""),record.get("phone",""),
                       record.get("business_type",""),record.get("borough",""),
                       record.get("alcohol",""),record.get("outdoor_seating",""),
                       record.get("launch_timeframe",""),record.get("role",""),record.get("notes","")])
    except Exception: pass

# ──────────────────────────────────────────────────────────────────────────────
# UI Components
# ──────────────────────────────────────────────────────────────────────────────

def top_nav() -> str:
    with st.sidebar:
        st.markdown(f"### {APP_NAME}")
        page = st.radio("Navigate", ["Landing", "About"], index=0)
        st.markdown("---")
        return page

def hero_section() -> None:
    st.markdown(
        """
        <div class="hero">
            <div class="pill">NYC Restaurants & Bars · Early Access</div>
            <h1>Open your spot without opening a law book.</h1>
            <p class="muted">An AI guide that turns NYC permits into a clear, step-by-step roadmap.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

def trust_row() -> None:
    c1,c2,c3=st.columns(3)
    c1.markdown("**🔒 Privacy-first**  \nWe only use your info for updates.")
    c2.markdown("**🏙️ NYC-specific**  \nBuilt for DOH, FDNY, DOB, SLA, DOT.")
    c3.markdown("**⚡ Fast**  \nNo fluff, just clarity.")

def how_it_works() -> None:
    st.subheader("How it works")
    c1,c2,c3=st.columns(3)
    c1.markdown("**1) Onboard**  \nTell us your concept + location.")
    c2.markdown("**2) Chat**  \nAI asks smart follow-ups.")
    c3.markdown("**3) Roadmap**  \nGet permits, docs, timelines.")

def who_is_it_for() -> None:
    st.subheader("Who is it for?")
    st.markdown('<div class="card"><span class="badge">🍝 Restaurant</span><span class="badge">🍸 Bar</span><span class="badge">☕ Cafe</span></div>', unsafe_allow_html=True)

def pricing_teaser() -> None:
    st.subheader("Pricing (coming soon)")
    c1,c2,c3=st.columns(3)
    c1.markdown("**Free**  \nChecklist preview")
    c2.markdown("**Pro ($49/mo)**  \nFull roadmap + reminders")
    c3.markdown("**Premium ($199/project)**  \nForm autofill + review")

def faq_section() -> None:
    st.subheader("FAQ")
    with st.expander("Is this legal advice?"): st.write("No, we provide guidance with citations. Not legal advice.")
    with st.expander("Which agencies?"): st.write("DOH, FDNY, DOB, SLA, DOT.")
    with st.expander("When launch?"): st.write("Inviting early testers soon.")
    with st.expander("Data use?"): st.write("Only to contact you about this product.")

def footer() -> None:
    st.markdown(f"<div class='footer'>© {datetime.now().year} {APP_NAME}. Not legal advice.</div>", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# Pages
# ──────────────────────────────────────────────────────────────────────────────

def landing_page() -> None:
    hero_section(); trust_row(); st.divider(); how_it_works(); who_is_it_for(); st.divider(); pricing_teaser(); st.divider()
    st.subheader("Join the NYC launch list")

    if "visit_ts" not in st.session_state: st.session_state.visit_ts=time.time()
    with st.form("waitlist", clear_on_submit=False):
        name=st.text_input("Full Name*").strip()
        email=st.text_input("Email*").strip()
        business=st.selectbox("Business Type*",["Restaurant","Bar","Cafe","Bakery"])
        borough=st.selectbox("Borough*",["Manhattan","Brooklyn","Queens","Bronx","Staten Island"])
        alcohol=st.selectbox("Serve alcohol?",["Yes","No"])
        outdoor=st.selectbox("Outdoor seating?",["Yes","No"])
        role=st.selectbox("Role*",["Owner","Manager","Consultant","Other"])
        timeframe=st.selectbox("Launch timeframe*",["Now","1–3 mo","3–6 mo","Exploring"])
        notes=st.text_area("Notes (optional)")
        honeypot=st.text_input(" ",key="honeypot",label_visibility="hidden")
        ok=st.checkbox("I agree to be contacted.",value=True)
        submit=st.form_submit_button("Request Early Access ✉️")

    if submit:
        errs=[]
        if not name: errs.append("Name required")
        if not valid_email(email): errs.append("Invalid email")
        if not ok: errs.append("Consent required")
        if honeypot: errs.append("Spam detected")
        if time.time()-st.session_state.visit_ts<3: errs.append("Too quick; try again")

        if errs: [st.error(e) for e in errs]; return
        record={"full_name":name,"email":email.lower(),"business_type":business,"borough":borough,
                "alcohol":alcohol,"outdoor_seating":outdoor,"role":role,"launch_timeframe":timeframe,"notes":notes}
        is_new=persist_to_csv(record); post_webhook(record); push_google_sheet(record)
        if is_new: st.success("You're on the list!"); st.balloons()
        else: st.info("Already signed up with this email.")

    st.divider(); faq_section(); footer()

def about_page() -> None:
    st.subheader("About")
    st.markdown("Our mission: make opening a restaurant or bar in NYC clear, fast, and fair.")
    st.markdown("Problem: Fragmented agencies, costly expeditors, delays.")
    st.markdown("Solution: AI guide that asks you plain-English questions, then generates a personalized permit roadmap with docs, fees, timelines, and links.")
    st.markdown("Next: autofill forms, reminders, human review, expansion beyond NYC.")
    st.divider()
    st.subheader("Join the launch list")
    if "visit_ts_about" not in st.session_state: st.session_state.visit_ts_about=time.time()
    with st.form("about_form"):
        name=st.text_input("Full Name*",key="an").strip()
        email=st.text_input("Email*",key="ae").strip()
        role=st.selectbox("Role*",["Owner","Manager","Consultant","Other"],key="ar")
        business=st.selectbox("Business*",["Restaurant","Bar","Cafe","Bakery"],key="ab")
        timeframe=st.selectbox("Launch timeframe*",["Now","1–3 mo","3–6 mo","Exploring"],key="at")
        hp=st.text_input(" ",key="ahp",label_visibility="hidden")
        ok=st.checkbox("I agree to be contacted.",value=True,key="ap")
        submit=st.form_submit_button("Request Early Access ✉️")
    if submit:
        errs=[]
        if not name: errs.append("Name required")
        if not valid_email(email): errs.append("Invalid email")
        if not ok: errs.append("Consent required")
        if hp: errs.append("Spam detected")
        if time.time()-st.session_state.visit_ts_about<3: errs.append("Too quick; try again")
        if errs: [st.error(e) for e in errs]; return
        record={"full_name":name,"email":email.lower(),"role":role,"business_type":business,
                "launch_timeframe":timeframe,"notes":"","borough":"","alcohol":"","outdoor_seating":""}
        is_new=persist_to_csv(record); post_webhook(record); push_google_sheet(record)
        if is_new: st.success("You're on the list!"); st.balloons()
        else: st.info("Already signed up with this email.")
    footer()

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title=f"{APP_NAME} · Early Access", page_icon="🍽️", layout="wide")
    inject_global_css()
    page=top_nav()
    if page=="Landing": landing_page()
    else: about_page()

if __name__=="__main__":
    main()
