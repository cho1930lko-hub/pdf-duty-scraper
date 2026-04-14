import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta, date
import json
import io
import base64
import re

# ── Optional imports ──────────────────────────────────────────────────────────
try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

try:
    from PIL import Image
    import fitz  # PyMuPDF
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# ── IST timezone ──────────────────────────────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(IST)

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ड्यूटी रोस्टर | 1930",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ══════════════════════════════════════════════════════════════════════════════
#  CSS — पुराना design same + नए elements
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;500;600;700;900&family=Rajdhani:wght@500;600;700&family=Space+Mono:wght@400;700&display=swap');

:root {
  --navy-deep:    #060d1f;
  --navy-mid:     #0d1b3e;
  --navy-light:   #1a2d5a;
  --navy-glow:    #1e3a7a;
  --accent-blue:  #2E75B6;
  --accent-cyan:  #00d4ff;
  --accent-gold:  #ffd700;
  --accent-green: #22c55e;
  --accent-red:   #ef4444;
  --accent-orange:#f97316;
  --accent-purple:#a855f7;
  --glass-bg:     rgba(255,255,255,0.04);
  --glass-border: rgba(255,255,255,0.10);
  --text-primary: #e8f0ff;
  --text-muted:   #7a92b8;
}

html, body, [class*="css"] {
    font-family: 'Noto Sans Devanagari', sans-serif;
    background: var(--navy-deep) !important;
    color: var(--text-primary) !important;
}
.stApp {
    background: linear-gradient(135deg, #060d1f 0%, #0a1628 40%, #060d1f 100%) !important;
    min-height: 100vh;
}
.main .block-container {
    padding: 1.5rem 2rem 3rem 2rem !important;
    max-width: 1400px !important;
}

/* ══ LOGIN CARD ══ */
.login-wrap {
    max-width: 420px;
    margin: 60px auto 0 auto;
    background: linear-gradient(135deg, rgba(13,27,62,0.98), rgba(26,45,90,0.90));
    border: 1px solid rgba(0,212,255,0.2);
    border-radius: 24px;
    padding: 44px 36px 16px;
    text-align: center;
    box-shadow: 0 0 60px rgba(46,117,182,0.25), inset 0 1px 0 rgba(255,255,255,0.06);
}
.login-icon  { font-size: 3rem; margin-bottom: 10px; display: block; }
.login-title { font-size: 1.4rem; font-weight: 800; color: var(--text-primary); margin-bottom: 4px;
               font-family: 'Rajdhani', sans-serif; letter-spacing: 1px; }
.login-sub   { font-size: 0.78rem; color: var(--text-muted); margin-bottom: 0px;
               letter-spacing: 2px; text-transform: uppercase; }

/* ══ MAGIC HEADER ══ */
.magic-header-wrap {
    position: relative; margin-bottom: 32px;
    border-radius: 20px; padding: 3px; overflow: visible;
}
.magic-header-wrap::before {
    content: ''; position: absolute; inset: -2px; border-radius: 22px;
    background: conic-gradient(from var(--angle,0deg),#ff0080,#ff6b00,#ffd700,#00ff88,#00cfff,#7f5fff,#ff0080);
    animation: spin-border 5s linear infinite; z-index: 0;
}
.magic-header-wrap::after {
    content: ''; position: absolute; inset: -20px; border-radius: 32px;
    background: conic-gradient(from 0deg,#ff008055,#00cfff55,#7f5fff55,#ff008055);
    animation: spin-border 5s linear infinite; filter: blur(24px); z-index: -1; opacity: 0.7;
}
@keyframes spin-border { 0%{transform:rotate(0deg)} 100%{transform:rotate(360deg)} }
.magic-header-inner {
    position: relative; z-index: 1;
    background: linear-gradient(135deg, #0d1b3e 0%, #132448 30%, #1a2d5a 60%, #0d1b3e 100%);
    border-radius: 18px; padding: 28px 36px 24px; text-align: center; overflow: hidden;
}
.magic-header-inner::after {
    content: ''; position: absolute; top:-50%; left:-50%; width:200%; height:200%;
    background: linear-gradient(105deg,transparent 40%,rgba(255,255,255,0.04) 50%,transparent 60%);
    animation: sweep 6s ease-in-out infinite; pointer-events: none;
}
@keyframes sweep { 0%{transform:translateX(-100%)} 50%,100%{transform:translateX(100%)} }
.magic-header-inner h1 {
    font-family: 'Rajdhani','Noto Sans Devanagari',sans-serif;
    font-size: 2.2rem; font-weight: 700; margin: 0 0 8px 0;
    background: linear-gradient(90deg,#fff 0%,#a8d4ff 20%,#ffd700 40%,#ffffff 60%,#a8d4ff 80%,#ffd700 100%);
    background-size: 300% auto; -webkit-background-clip: text;
    -webkit-text-fill-color: transparent; background-clip: text;
    animation: shimmer-text 4s linear infinite; letter-spacing: 1.5px; position: relative; z-index:1;
}
@keyframes shimmer-text { 0%{background-position:300% center} 100%{background-position:-300% center} }
.magic-header-inner .subtitle {
    font-size: 0.88rem; color: var(--text-muted); letter-spacing: 3px;
    text-transform: uppercase; font-weight: 600; position: relative; z-index:1;
}
.header-badge {
    display: inline-block; background: rgba(0,212,255,0.12);
    border: 1px solid rgba(0,212,255,0.3); border-radius: 20px;
    padding: 4px 14px; font-size: 0.72rem; color: #00d4ff;
    letter-spacing: 2px; text-transform: uppercase; margin-top: 10px; position:relative; z-index:1;
}
.particle { position:absolute; border-radius:50%; animation:float-up 4s ease-in infinite; opacity:0; z-index:2; }
.p1{width:5px;height:5px;background:#00cfff;left:8%;animation-delay:0s}
.p2{width:3px;height:3px;background:#ff0080;left:22%;animation-delay:1s}
.p3{width:6px;height:6px;background:#ffd700;left:48%;animation-delay:2s}
.p4{width:4px;height:4px;background:#00ff88;left:72%;animation-delay:0.5s}
.p5{width:5px;height:5px;background:#7f5fff;left:90%;animation-delay:1.5s}
.p6{width:3px;height:3px;background:#ff6b00;left:35%;animation-delay:2.5s}
@keyframes float-up {
    0%{opacity:0;transform:translateY(40px) scale(0)} 20%{opacity:1}
    80%{opacity:0.6} 100%{opacity:0;transform:translateY(-30px) scale(1.5)}
}

/* ══ METRIC CARDS ══ */
.metric-card {
    background:var(--glass-bg); backdrop-filter:blur(12px); border:1px solid var(--glass-border);
    border-radius:16px; padding:20px 16px; text-align:center; position:relative;
    overflow:hidden; transition:transform 0.25s,box-shadow 0.25s; cursor:default;
}
.metric-card::before { content:''; position:absolute; top:0;left:0;right:0; height:3px; border-radius:16px 16px 0 0; }
.metric-card:hover { transform:translateY(-5px); }
.metric-card .val { font-family:'Rajdhani',monospace; font-size:3rem; font-weight:700; line-height:1; margin-bottom:6px; }
.metric-card .lbl { font-size:0.78rem; color:var(--text-muted); font-weight:600; letter-spacing:0.5px; }
.metric-card .icon { font-size:1.4rem; margin-bottom:8px; display:block; }
.card-blue{box-shadow:0 4px 30px rgba(46,117,182,0.2);border-color:rgba(46,117,182,0.35)}
.card-blue .val{color:#60a5fa} .card-blue::before{background:linear-gradient(90deg,#2E75B6,#60a5fa)}
.card-gold{box-shadow:0 4px 30px rgba(255,215,0,0.2);border-color:rgba(255,215,0,0.35)}
.card-gold .val{color:#ffd700} .card-gold::before{background:linear-gradient(90deg,#b8860b,#ffd700)}
.card-green{box-shadow:0 4px 30px rgba(34,197,94,0.2);border-color:rgba(34,197,94,0.35)}
.card-green .val{color:#4ade80} .card-green::before{background:linear-gradient(90deg,#16a34a,#4ade80)}
.card-cyan{box-shadow:0 4px 30px rgba(0,212,255,0.2);border-color:rgba(0,212,255,0.35)}
.card-cyan .val{color:#00d4ff} .card-cyan::before{background:linear-gradient(90deg,#0ea5e9,#00d4ff)}
.card-orange{box-shadow:0 4px 30px rgba(249,115,22,0.2);border-color:rgba(249,115,22,0.35)}
.card-orange .val{color:#fb923c} .card-orange::before{background:linear-gradient(90deg,#ea580c,#fb923c)}
.card-purple{box-shadow:0 4px 30px rgba(168,85,247,0.2);border-color:rgba(168,85,247,0.35)}
.card-purple .val{color:#c084fc} .card-purple::before{background:linear-gradient(90deg,#9333ea,#c084fc)}
.card-red{box-shadow:0 4px 30px rgba(239,68,68,0.2);border-color:rgba(239,68,68,0.35)}
.card-red .val{color:#f87171} .card-red::before{background:linear-gradient(90deg,#dc2626,#f87171)}

/* ══ SHIFT BADGES & CARDS ══ */
.shift-badge { display:inline-block; padding:4px 14px; border-radius:20px;
               font-size:0.78rem; font-weight:700; border:1px solid transparent; }
.s1{background:rgba(255,192,0,0.15);color:#ffd700;border-color:rgba(255,192,0,0.4)}
.s2{background:rgba(34,197,94,0.15);color:#4ade80;border-color:rgba(34,197,94,0.4)}
.s3{background:rgba(96,165,250,0.15);color:#60a5fa;border-color:rgba(96,165,250,0.4)}
.shift-card { background:var(--glass-bg); border:1px solid var(--glass-border);
    border-radius:16px; padding:18px 16px 12px; text-align:center;
    transition:transform 0.2s; margin-bottom:12px; }
.shift-card:hover{transform:translateY(-3px)}
.shift-card .count{font-family:'Rajdhani',monospace;font-size:2.8rem;font-weight:700;line-height:1}
.shift-card .unit{font-size:0.72rem;color:var(--text-muted);font-weight:600}
.sc-s1{border-top:3px solid #ffd700;box-shadow:0 4px 20px rgba(255,215,0,0.12)} .sc-s1 .count{color:#ffd700}
.sc-s2{border-top:3px solid #4ade80;box-shadow:0 4px 20px rgba(74,222,128,0.12)} .sc-s2 .count{color:#4ade80}
.sc-s3{border-top:3px solid #60a5fa;box-shadow:0 4px 20px rgba(96,165,250,0.12)} .sc-s3 .count{color:#60a5fa}

/* ══ SECTION TITLE ══ */
.section-title {
    font-family:'Rajdhani','Noto Sans Devanagari',sans-serif; font-size:1.05rem; font-weight:700;
    color:var(--text-primary); letter-spacing:1px; padding:10px 16px; margin:24px 0 14px 0;
    background:var(--glass-bg); border:1px solid var(--glass-border);
    border-left:4px solid var(--accent-blue); border-radius:0 10px 10px 0;
    display:flex; align-items:center; gap:8px;
}

/* ══ NEW STAFF ALERT ══ */
@keyframes blink-alert {
    0%,100%{box-shadow:0 0 20px rgba(255,215,0,0.6);border-color:rgba(255,215,0,0.8)}
    50%{box-shadow:0 0 40px rgba(255,215,0,0.2);border-color:rgba(255,215,0,0.3)}
}
.new-staff-alert {
    background:rgba(255,215,0,0.08); border:2px solid rgba(255,215,0,0.6);
    border-radius:14px; padding:14px 20px; margin:8px 0;
    animation: blink-alert 1.5s ease-in-out infinite;
    display:flex; align-items:center; gap:12px;
}
.new-staff-alert .alert-icon {font-size:1.5rem;}
.new-staff-alert .alert-text {color:#ffd700; font-weight:700; font-size:0.9rem;}

/* ══ PDF UPLOAD ZONE ══ */
.upload-zone {
    background:var(--glass-bg); border:2px dashed var(--glass-border);
    border-radius:16px; padding:20px; text-align:center;
    transition:border-color 0.2s, background 0.2s;
}
.upload-zone:hover { border-color:rgba(0,212,255,0.4); background:rgba(0,212,255,0.04); }
.upload-label { font-size:0.8rem; color:var(--text-muted); margin-top:8px; letter-spacing:0.5px; }

/* ══ AI SECTION ══ */
.ai-card {
    background:linear-gradient(135deg,rgba(168,85,247,0.08),rgba(46,117,182,0.08));
    border:1px solid rgba(168,85,247,0.3); border-radius:16px; padding:20px;
    margin-bottom:12px;
}
.ai-response {
    background:rgba(0,0,0,0.3); border:1px solid rgba(168,85,247,0.2);
    border-radius:12px; padding:16px; margin-top:12px;
    font-size:0.88rem; line-height:1.8; color:var(--text-primary);
    white-space:pre-wrap;
}

/* ══ STREAMLIT OVERRIDES ══ */
.stTabs [data-baseweb="tab-list"] {
    background:var(--glass-bg)!important; border:1px solid var(--glass-border)!important;
    border-radius:12px!important; padding:4px!important; gap:4px!important;
}
.stTabs [data-baseweb="tab"] {
    background:transparent!important; border-radius:8px!important;
    color:var(--text-muted)!important; font-weight:600!important;
    font-size:0.82rem!important; padding:8px 16px!important;
    transition:all 0.2s!important; border:none!important;
}
.stTabs [aria-selected="true"] {
    background:linear-gradient(135deg,var(--navy-glow),var(--accent-blue))!important; color:white!important;
}
[data-testid="stDataFrame"] { border:1px solid var(--glass-border)!important; border-radius:12px!important; overflow:hidden!important; }

.stTextInput>div>div>input,
div[data-testid="stTextInput"] input {
    background:#0d1b3e!important; background-color:#0d1b3e!important;
    border:1px solid rgba(255,255,255,0.12)!important; border-radius:10px!important;
    color:#e8f0ff!important; caret-color:#00d4ff!important;
    font-family:'Noto Sans Devanagari',sans-serif!important;
    transition:border-color 0.2s,box-shadow 0.2s!important;
}
.stTextInput>div>div>input:focus,
div[data-testid="stTextInput"] input:focus {
    border-color:var(--accent-blue)!important;
    box-shadow:0 0 0 3px rgba(46,117,182,0.2)!important; outline:none!important;
}
.stTextInput>div>div>input::placeholder,
div[data-testid="stTextInput"] input::placeholder { color:#4a6080!important; opacity:1!important; }
.stTextInput label, .stTextInput label p,
div[data-testid="stTextInput"] label,
div[data-testid="stTextInput"] label p {
    color:#a0b8d8!important; font-weight:600!important; font-size:0.85rem!important;
}
input[type="password"] {
    background:#0d1b3e!important; background-color:#0d1b3e!important;
    color:#e8f0ff!important; border:1px solid rgba(255,255,255,0.12)!important;
    border-radius:10px!important; caret-color:#00d4ff!important;
}
input[type="password"]::placeholder { color:#4a6080!important; opacity:1!important; }
.stSelectbox>div>div { background:#0d1b3e!important; border:1px solid rgba(255,255,255,0.12)!important; border-radius:10px!important; color:var(--text-primary)!important; }
.stTextArea textarea {
    background:#0d1b3e!important; border:1px solid rgba(255,255,255,0.12)!important;
    border-radius:10px!important; color:var(--text-primary)!important;
}
.stButton>button {
    background:linear-gradient(135deg,var(--navy-mid),var(--accent-blue))!important;
    color:white!important; font-weight:700!important; font-size:0.9rem!important;
    border-radius:10px!important; border:1px solid rgba(46,117,182,0.5)!important;
    padding:10px 22px!important; transition:all 0.25s!important;
}
.stButton>button:hover {
    background:linear-gradient(135deg,var(--accent-blue),#1a4d8a)!important;
    transform:translateY(-2px)!important; box-shadow:0 6px 20px rgba(46,117,182,0.4)!important;
}
.stDownloadButton>button {
    background:linear-gradient(135deg,#16a34a,#15803d)!important; color:white!important;
    font-weight:700!important; font-size:0.82rem!important; border-radius:8px!important;
    border:1px solid rgba(34,197,94,0.4)!important; transition:all 0.2s!important;
}
.stDownloadButton>button:hover { transform:translateY(-2px)!important; box-shadow:0 6px 18px rgba(22,163,74,0.4)!important; }
.stAlert{border-radius:10px!important; border-left:4px solid!important;}
[data-testid="stInfoMessage"]{background:rgba(46,117,182,0.1)!important; border-color:var(--accent-blue)!important;}
[data-testid="stSuccessMessage"]{background:rgba(34,197,94,0.1)!important; border-color:var(--accent-green)!important;}
[data-testid="stWarningMessage"]{background:rgba(249,115,22,0.1)!important; border-color:var(--accent-orange)!important;}
.stSpinner>div{border-top-color:var(--accent-cyan)!important;}
hr{border-color:var(--glass-border)!important; margin:20px 0!important;}
.stCaption{color:var(--text-muted)!important; font-size:0.78rem!important;}

/* Clock */
.clock-box{background:linear-gradient(135deg,var(--navy-deep),var(--navy-mid)); border-radius:14px; padding:18px 16px; text-align:center; border:1px solid rgba(0,212,255,0.2); box-shadow:0 0 30px rgba(0,212,255,0.12); margin-top:8px; position:relative; overflow:hidden;}
.clock-label{font-size:0.65rem;color:var(--text-muted);letter-spacing:2px;text-transform:uppercase;margin-bottom:6px}
.clock-date{font-size:1rem;font-weight:700;color:var(--accent-gold);margin-bottom:6px}
.clock-time{font-size:2rem;font-weight:700;color:var(--accent-cyan);font-family:'Space Mono',monospace;letter-spacing:3px;text-shadow:0 0 20px rgba(0,212,255,0.5)}
.clock-city{font-size:0.65rem;color:var(--text-muted);margin-top:6px;letter-spacing:1.5px}
.footer{text-align:center;color:var(--text-muted);font-size:0.75rem;padding:16px;border-top:1px solid var(--glass-border);margin-top:32px;letter-spacing:0.5px;}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:var(--navy-deep)}
::-webkit-scrollbar-thumb{background:var(--navy-glow);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--accent-blue)}
@keyframes pulse-dot{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.4;transform:scale(1.5)}}
.live-dot{display:inline-block;width:8px;height:8px;background:#22c55e;border-radius:50%;animation:pulse-dot 1.5s ease-in-out infinite;box-shadow:0 0 6px #22c55e;margin-right:6px;vertical-align:middle;}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  PASSWORD
# ══════════════════════════════════════════════════════════════════════════════
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.markdown("""
        <div class="login-wrap">
            <span class="login-icon">🔐</span>
            <div class="login-title">साइबर क्राइम 1930</div>
            <div class="login-sub">ड्यूटी रोस्टर प्रणाली</div>
        </div>
        """, unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            pwd = st.text_input("पासवर्ड दर्ज करें", type="password", key="pwd_input", placeholder="••••••••")
            if st.button("🔓 लॉगिन करें", use_container_width=True, key="login_btn"):
                if pwd == st.secrets["passwords"]["app_password"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("❌ गलत पासवर्ड! दोबारा कोशिश करें।")
        return False
    return True

if not check_password():
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
SHEET_ID = "1TSq6eMn3jbFNqZuMjIpll09NWqO3XOEOmUCBs-0CATk"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SHIFT_NAMES = ["Shift1", "Shift2", "Shift3"]
HINDI_MONTHS = {1:"जनवरी",2:"फ़रवरी",3:"मार्च",4:"अप्रैल",5:"मई",6:"जून",
                7:"जुलाई",8:"अगस्त",9:"सितम्बर",10:"अक्टूबर",11:"नवम्बर",12:"दिसम्बर"}

# ══════════════════════════════════════════════════════════════════════════════
#  GOOGLE SHEETS HELPERS
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_resource(show_spinner=False)
def get_client():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

def get_or_create_worksheet(sh, title, rows=10000, cols=20):
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=rows, cols=cols)
        return ws

@st.cache_data(ttl=60, show_spinner=False)
def load_all_data(sheet_id):
    client = get_client()
    sh = client.open_by_key(sheet_id)

    # Master_Data
    try:
        master_df = pd.DataFrame(sh.worksheet("Master_Data").get_all_records())
    except:
        master_df = pd.DataFrame(columns=["Mobile_No","Employee_Name","Designation","STATUS"])

    # Shift sheets
    shift_dfs = {}
    for s in SHIFT_NAMES:
        try:
            shift_dfs[s] = pd.DataFrame(sh.worksheet(s).get_all_records())
        except:
            shift_dfs[s] = pd.DataFrame(columns=["Mobile_No","Employee_Name","Designation","Shift_Date"])

    # Audit_Log
    try:
        audit_df = pd.DataFrame(sh.worksheet("Audit_Log").get_all_records())
    except:
        audit_df = pd.DataFrame(columns=["Date","Shift","Mobile_No","Employee_Name","Designation","Action","Remarks"])

    # Avkaash
    try:
        avkaash_df = pd.DataFrame(sh.worksheet("Avkaash").get_all_records())
    except:
        avkaash_df = pd.DataFrame(columns=["Mobile_No","Designation","Name","Leave_From","Leave_To","Leave_Reason","Sd_Days","Status"])

    return master_df, shift_dfs, audit_df, avkaash_df

def setup_sheets():
    """पहली बार sheets और headers बनाएं"""
    client = get_client()
    sh = client.open_by_key(SHEET_ID)

    # Master_Data
    ws = get_or_create_worksheet(sh, "Master_Data")
    if not ws.get_all_values():
        ws.append_row(["Mobile_No","Employee_Name","Designation","STATUS"])

    # Shift sheets
    for s in SHIFT_NAMES:
        ws = get_or_create_worksheet(sh, s)
        if not ws.get_all_values():
            ws.append_row(["Mobile_No","Employee_Name","Designation","Shift_Date"])

    # Audit_Log
    ws = get_or_create_worksheet(sh, "Audit_Log")
    if not ws.get_all_values():
        ws.append_row(["Date","Shift","Mobile_No","Employee_Name","Designation","Action","Remarks"])

    # Avkaash
    ws = get_or_create_worksheet(sh, "Avkaash")
    if not ws.get_all_values():
        ws.append_row(["Mobile_No","Designation","Name","Leave_From","Leave_To","Leave_Reason","Sd_Days","Status"])

def format_sheets():
    """Sheets को color-code करें"""
    try:
        client = get_client()
        sh = client.open_by_key(SHEET_ID)

        # Master_Data — Navy Blue header
        ws = sh.worksheet("Master_Data")
        ws.format("A1:D1", {
            "backgroundColor": {"red": 0.024, "green": 0.106, "blue": 0.247},
            "textFormat": {"bold": True, "foregroundColor": {"red": 0.91, "green": 0.94, blue: 1.0}},
        })

        # Shift1 — Gold header
        ws = sh.worksheet("Shift1")
        ws.format("A1:D1", {
            "backgroundColor": {"red": 1.0, "green": 0.84, "blue": 0.0},
            "textFormat": {"bold": True},
        })

        # Shift2 — Green header
        ws = sh.worksheet("Shift2")
        ws.format("A1:D1", {
            "backgroundColor": {"red": 0.13, "green": 0.77, "blue": 0.37},
            "textFormat": {"bold": True},
        })

        # Shift3 — Blue header
        ws = sh.worksheet("Shift3")
        ws.format("A1:D1", {
            "backgroundColor": {"red": 0.38, "green": 0.65, "blue": 0.98},
            "textFormat": {"bold": True},
        })
    except Exception as e:
        pass  # Formatting optional, don't fail

# ══════════════════════════════════════════════════════════════════════════════
#  PDF OCR HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def pdf_to_images_base64(pdf_bytes):
    """Scanned PDF → base64 images list (Groq vision के लिए)"""
    images_b64 = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_num in range(min(len(doc), 5)):  # max 5 pages
            page = doc[page_num]
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            images_b64.append(b64)
        doc.close()
    except Exception as e:
        st.error(f"PDF image convert error: {e}")
    return images_b64

def extract_text_pdfplumber(pdf_bytes):
    """Text-based PDF से text निकालें"""
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
    except Exception as e:
        pass
    return text.strip()

def parse_pdf_with_groq(pdf_bytes, shift_name, shift_date_str):
    """
    Groq से PDF parse करके staff list निकालें
    Returns: list of dicts [{Mobile_No, Employee_Name, Designation}]
    """
    if not GROQ_AVAILABLE:
        return [], "Groq library install नहीं है"

    groq_client = Groq(api_key=st.secrets["groq"]["api_key"])

    # पहले text निकालने की कोशिश
    text_content = ""
    if PDF_AVAILABLE:
        text_content = extract_text_pdfplumber(pdf_bytes)

    if text_content and len(text_content) > 100:
        # Text-based PDF
        prompt = f"""यह एक duty roster PDF का text है।
इसमें से सभी कर्मचारियों की जानकारी निकालो।

PDF Text:
{text_content[:3000]}

JSON format में return करो, कोई extra text नहीं:
{{
  "shift_date": "DD-MM-YYYY या empty",
  "staff": [
    {{"Mobile_No": "10 digit number", "Employee_Name": "नाम", "Designation": "पद"}},
    ...
  ]
}}

Rules:
- Mobile_No: 10 अंकों का नंबर, नहीं मिले तो "" 
- Employee_Name: पूरा नाम
- Designation: पद/रैंक जैसे SI, HC, Constable, ASI आदि
- अगर mobile नहीं है तो भी नाम और पद जोड़ो
"""
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.1,
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r'```json|```', '', raw).strip()
            data = json.loads(raw)
            return data.get("staff", []), None
        except Exception as e:
            return [], f"Text parse error: {e}"

    else:
        # Scanned PDF — Vision API
        if not OCR_AVAILABLE:
            return [], "PyMuPDF install नहीं है (pip install PyMuPDF)"

        images_b64 = pdf_to_images_base64(pdf_bytes)
        if not images_b64:
            return [], "PDF से images नहीं बन सकीं"

        all_staff = []
        for idx, img_b64 in enumerate(images_b64[:3]):  # max 3 pages
            prompt = f"""यह {shift_name} duty roster की scanned image है।

इसमें से सभी कर्मचारियों की जानकारी निकालो।

JSON format में return करो ONLY, कोई extra text नहीं:
{{
  "staff": [
    {{"Mobile_No": "10 digit mobile number", "Employee_Name": "पूरा नाम", "Designation": "पद/रैंक"}},
    ...
  ]
}}

Rules:
- Mobile_No: 10 अंकों का नंबर ढूंढो, नहीं मिले तो ""
- Employee_Name: जो नाम लिखा हो
- Designation: SI, HC, Constable, ASI, Inspector आदि
- सभी visible कर्मचारी शामिल करो"""

            try:
                response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                            {"type": "text", "text": prompt}
                        ]
                    }],
                    max_tokens=2000,
                    temperature=0.1,
                )
                raw = response.choices[0].message.content.strip()
                raw = re.sub(r'```json|```', '', raw).strip()
                data = json.loads(raw)
                all_staff.extend(data.get("staff", []))
            except Exception as e:
                # Try text-only fallback
                try:
                    response = groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "user", "content": f"Page {idx+1} parse करो: {prompt}"}],
                        max_tokens=500,
                        temperature=0.1,
                    )
                except:
                    pass

        # Duplicates हटाएं
        seen = set()
        unique_staff = []
        for s in all_staff:
            key = str(s.get("Mobile_No","")) + str(s.get("Employee_Name",""))
            if key not in seen:
                seen.add(key)
                unique_staff.append(s)

        return unique_staff, None

# ══════════════════════════════════════════════════════════════════════════════
#  SHEET WRITERS
# ══════════════════════════════════════════════════════════════════════════════
def update_shift_sheet(shift_name, staff_list, date_str):
    """
    Shift sheet update करो + Master_Data में नए कर्मचारी add करो
    Returns: new_staff_list (नए कर्मचारी जो Master में नहीं थे)
    """
    client = get_client()
    sh = client.open_by_key(SHEET_ID)
    now_str = now_ist().strftime("%d-%m-%Y %H:%M")

    # Shift sheet clear + नया data
    ws_shift = sh.worksheet(shift_name)
    ws_shift.clear()
    ws_shift.append_row(["Mobile_No", "Employee_Name", "Designation", "Shift_Date"])

    rows = []
    for s in staff_list:
        mob = str(s.get("Mobile_No", "")).strip()
        name = str(s.get("Employee_Name", "")).strip()
        desig = str(s.get("Designation", "")).strip()
        if name:
            rows.append([mob, name, desig, date_str])

    if rows:
        ws_shift.append_rows(rows)

    # Master_Data check
    ws_master = sh.worksheet("Master_Data")
    master_records = ws_master.get_all_records()
    existing_mobiles = {str(r.get("Mobile_No","")).strip() for r in master_records if str(r.get("Mobile_No","")).strip()}

    new_staff = []
    audit_rows = []

    for s in staff_list:
        mob = str(s.get("Mobile_No", "")).strip()
        name = str(s.get("Employee_Name", "")).strip()
        desig = str(s.get("Designation", "")).strip()

        if not name:
            continue

        # Audit log entry
        audit_rows.append([date_str, shift_name, mob, name, desig, "Loaded", f"PDF से लोड"])

        # नया mobile → Master में add
        if mob and mob not in existing_mobiles and len(mob) == 10:
            ws_master.append_row([mob, name, desig, 1])
            existing_mobiles.add(mob)
            new_staff.append({"Mobile_No": mob, "Employee_Name": name, "Designation": desig})

    # Audit log update
    ws_audit = get_or_create_worksheet(sh, "Audit_Log")
    if audit_rows:
        ws_audit.append_rows(audit_rows)

    load_all_data.clear()
    return new_staff


def load_historical_pdf(shift_name, staff_list, date_str):
    """पुरानी duty सीधे Audit_Log में डालो (Shift sheet नहीं बदलेगी)"""
    client = get_client()
    sh = client.open_by_key(SHEET_ID)
    ws_audit = get_or_create_worksheet(sh, "Audit_Log")

    audit_rows = []
    for s in staff_list:
        mob = str(s.get("Mobile_No", "")).strip()
        name = str(s.get("Employee_Name", "")).strip()
        desig = str(s.get("Designation", "")).strip()
        if name:
            audit_rows.append([date_str, shift_name, mob, name, desig, "Historical", "पुराना record"])

    if audit_rows:
        ws_audit.append_rows(audit_rows)

    load_all_data.clear()
    return len(audit_rows)


def add_leave(mob, name, desig, leave_from, leave_to, reason, sd_days):
    client = get_client()
    sh = client.open_by_key(SHEET_ID)
    ws = get_or_create_worksheet(sh, "Avkaash")
    today = now_ist().date()
    try:
        from_d = datetime.strptime(leave_from, "%d-%m-%Y").date()
        to_d = datetime.strptime(leave_to, "%d-%m-%Y").date()
        status = "Active" if from_d <= today <= to_d else ("Upcoming" if today < from_d else "Expired")
    except:
        status = "Active"
    ws.append_row([mob, desig, name, leave_from, leave_to, reason, sd_days, status])
    load_all_data.clear()


def add_employee_manual(mob, name, desig, status=1):
    client = get_client()
    sh = client.open_by_key(SHEET_ID)
    ws = sh.worksheet("Master_Data")
    ws.append_row([mob, name, desig, status])
    load_all_data.clear()


# ══════════════════════════════════════════════════════════════════════════════
#  AI HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def ai_pattern_analysis(audit_df):
    """Audit_Log से pattern analysis"""
    if not GROQ_AVAILABLE or audit_df.empty:
        return "डेटा उपलब्ध नहीं है।"

    groq_client = Groq(api_key=st.secrets["groq"]["api_key"])

    # Summary बनाओ
    if "Shift" in audit_df.columns and "Employee_Name" in audit_df.columns:
        shift_counts = audit_df.groupby(["Employee_Name","Shift"]).size().reset_index(name="count")
        summary = shift_counts.head(50).to_string(index=False)
    else:
        summary = "Audit data available but columns missing"

    prompt = f"""यह एक पुलिस duty roster का audit data है।
इस data को देखकर pattern analysis करो:

{summary}

Hindi में बताओ:
1. किस कर्मचारी की कितनी duty किस shift में लगी
2. कोई shift bias है? (किसी को हमेशा एक ही shift?)
3. Fair rotation है या नहीं?
4. सुझाव: अगली duty कैसी होनी चाहिए?

संक्षिप्त और स्पष्ट रखो।"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {e}"


def ai_virtual_duty_suggest(audit_df, master_df):
    """Virtual duty suggestion — sheet में नहीं जाएगा"""
    if not GROQ_AVAILABLE:
        return "Groq available नहीं है।"

    groq_client = Groq(api_key=st.secrets["groq"]["api_key"])

    staff_list = master_df[master_df.get("STATUS", 1) == 1]["Employee_Name"].tolist() if not master_df.empty else []

    if "Employee_Name" in audit_df.columns and "Shift" in audit_df.columns:
        recent = audit_df.tail(30).to_string(index=False)
    else:
        recent = "No recent data"

    prompt = f"""Based on this duty history, suggest virtual duty assignment for next rotation.
DO NOT assign same shift repeatedly to same person.

Recent history:
{recent}

Available staff: {', '.join(staff_list[:20])}

Output in Hindi — suggest who should go in Shift1/Shift2/Shift3.
यह preview only है, sheet में नहीं जाएगा।
Format:
🟡 Shift1: [names]
🟢 Shift2: [names]  
🔵 Shift3: [names]"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.4,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {e}"


def ai_employee_search(mob, master_df, shift_dfs, audit_df, avkaash_df):
    """Mobile number से complete employee card"""
    mob = str(mob).strip()

    # Master से basic info
    emp_row = None
    if not master_df.empty and "Mobile_No" in master_df.columns:
        res = master_df[master_df["Mobile_No"].astype(str).str.strip() == mob]
        if not res.empty:
            emp_row = res.iloc[0]

    if emp_row is None:
        return None, "कर्मचारी नहीं मिला"

    name = str(emp_row.get("Employee_Name", "—"))
    desig = str(emp_row.get("Designation", "—"))
    status = int(emp_row.get("STATUS", 1))

    # Current shift
    current_shift = "—"
    for s_name, s_df in shift_dfs.items():
        if not s_df.empty and "Mobile_No" in s_df.columns:
            found = s_df[s_df["Mobile_No"].astype(str).str.strip() == mob]
            if not found.empty:
                current_shift = s_name
                break

    # 2 months history from audit
    history = []
    if not audit_df.empty and "Mobile_No" in audit_df.columns:
        emp_audit = audit_df[audit_df["Mobile_No"].astype(str).str.strip() == mob]
        history = emp_audit[["Date","Shift","Action"]].tail(20).values.tolist() if not emp_audit.empty else []

    # Leave records
    leaves = []
    if not avkaash_df.empty and "Mobile_No" in avkaash_df.columns:
        emp_leave = avkaash_df[avkaash_df["Mobile_No"].astype(str).str.strip() == mob]
        leaves = emp_leave[["Leave_From","Leave_To","Leave_Reason","Status"]].values.tolist() if not emp_leave.empty else []

    return {
        "name": name, "designation": desig, "mobile": mob,
        "status": status, "current_shift": current_shift,
        "history": history, "leaves": leaves
    }, None


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITY
# ══════════════════════════════════════════════════════════════════════════════
def df_to_excel_bytes(df, sheet_name="Sheet1"):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()

def get_active_leave_mobiles(avkaash_df):
    today = now_ist().date()
    active = set()
    if avkaash_df.empty or "Mobile_No" not in avkaash_df.columns:
        return active
    for _, row in avkaash_df.iterrows():
        try:
            f = pd.to_datetime(row.get("Leave_From",""), dayfirst=True).date()
            t = pd.to_datetime(row.get("Leave_To",""), dayfirst=True).date()
            if f <= today <= t:
                active.add(str(row.get("Mobile_No","")).strip())
        except:
            pass
    return active

# ══════════════════════════════════════════════════════════════════════════════
#  HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div class="magic-header-wrap"><div class="magic-header-inner">
  <div class="particle p1"></div><div class="particle p2"></div>
  <div class="particle p3"></div><div class="particle p4"></div>
  <div class="particle p5"></div><div class="particle p6"></div>
  <h1>🚨 साइबर क्राइम हेल्पलाइन 1930</h1>
  <div class="subtitle">✦ ड्यूटी रोस्टर प्रबंधन प्रणाली ✦</div>
  <div class="header-badge"><span class="live-dot"></span>LIVE SYSTEM • ACTIVE</div>
</div></div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### ⚙️ सेटिंग्स")
    st.markdown("---")
    now = now_ist()
    st.markdown(f"""<div class="clock-box">
      <div class="clock-label">📍 भारतीय मानक समय (IST)</div>
      <div class="clock-date">📅 {now.day} {HINDI_MONTHS[now.month]} {now.year}</div>
      <div class="clock-time">{now.strftime("%I:%M %p")}</div>
      <div class="clock-city">लखनऊ • प्रयागराज • भारत</div>
    </div>""", unsafe_allow_html=True)
    st.markdown("---")
    if st.button("🔧 Sheets Setup करें", use_container_width=True):
        with st.spinner("Setup हो रहा है..."):
            try:
                setup_sheets()
                st.success("✅ सभी sheets तैयार!")
            except Exception as e:
                st.error(f"Error: {e}")
    if st.button("🔃 Cache रिफ्रेश", use_container_width=True):
        load_all_data.clear()
        st.rerun()
    st.markdown("---")
    st.caption(f"Sheet ID: ...{SHEET_ID[-8:]}")
    st.caption(f"Groq: {'✅' if GROQ_AVAILABLE else '❌'}")
    st.caption(f"PDF: {'✅' if PDF_AVAILABLE else '❌'}")
    st.caption(f"OCR: {'✅' if OCR_AVAILABLE else '❌'}")

# ══════════════════════════════════════════════════════════════════════════════
#  LOAD DATA
# ══════════════════════════════════════════════════════════════════════════════
with st.spinner("डेटा लोड हो रहा है..."):
    try:
        master_df, shift_dfs, audit_df, avkaash_df = load_all_data(SHEET_ID)
    except Exception as e:
        st.error(f"❌ Sheet connect नहीं हुई: {e}")
        st.info("Sidebar में 'Sheets Setup करें' बटन दबाएं।")
        st.stop()

today_str = now_ist().strftime("%d-%m-%Y")
active_leave_mobs = get_active_leave_mobiles(avkaash_df)

# ══════════════════════════════════════════════════════════════════════════════
#  METRIC CARDS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">📊 सारांश डैशबोर्ड</div>', unsafe_allow_html=True)

total_master = len(master_df)
s1_count = len(shift_dfs.get("Shift1", pd.DataFrame()))
s2_count = len(shift_dfs.get("Shift2", pd.DataFrame()))
s3_count = len(shift_dfs.get("Shift3", pd.DataFrame()))
leave_count = len(active_leave_mobs)

c1,c2,c3,c4,c5 = st.columns(5)
for col,icon,val,lbl,cls in [
    (c1,"👥",total_master,"कुल कर्मचारी","card-blue"),
    (c2,"🟡",s1_count,"Shift 1","card-gold"),
    (c3,"🟢",s2_count,"Shift 2","card-green"),
    (c4,"🔵",s3_count,"Shift 3","card-cyan"),
    (c5,"🌴",leave_count,"अवकाश पर","card-orange"),
]:
    with col:
        st.markdown(f'<div class="metric-card {cls}"><span class="icon">{icon}</span><div class="val">{val}</div><div class="lbl">{lbl}</div></div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  NEW STAFF ALERTS (blinking)
# ══════════════════════════════════════════════════════════════════════════════
if "new_staff_alerts" in st.session_state and st.session_state["new_staff_alerts"]:
    st.markdown('<div class="section-title">🔔 नए कर्मचारी जोड़े गए</div>', unsafe_allow_html=True)
    for ns in st.session_state["new_staff_alerts"]:
        st.markdown(f"""
        <div class="new-staff-alert">
            <span class="alert-icon">⚠️</span>
            <span class="alert-text">नया कर्मचारी जोड़ा गया: {ns['Employee_Name']} | {ns['Designation']} | 📱 {ns['Mobile_No']}</span>
        </div>""", unsafe_allow_html=True)
    if st.button("✅ Alerts dismiss करें"):
        st.session_state["new_staff_alerts"] = []
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
#  PDF UPLOAD SECTION
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">📥 PDF Upload — तीनों Shifts</div>', unsafe_allow_html=True)

pdf_date_input = st.date_input(
    "📅 PDF की तारीख चुनें",
    value=now_ist().date(),
    key="pdf_date"
)
pdf_date_str = pdf_date_input.strftime("%d-%m-%Y")

# Historical mode toggle
is_historical = st.checkbox(
    "📚 Historical Mode (पुराना data — सिर्फ Audit_Log में जाएगा, Shift sheet नहीं बदलेगी)",
    value=False,
    key="historical_mode"
)

pu1, pu2, pu3 = st.columns(3)
upload_configs = [
    (pu1, "Shift1", "🟡", "sc-s1", "s1"),
    (pu2, "Shift2", "🟢", "sc-s2", "s2"),
    (pu3, "Shift3", "🔵", "sc-s3", "s3"),
]

for col, shift_name, emoji, card_cls, badge_cls in upload_configs:
    with col:
        st.markdown(f'<div class="shift-card {card_cls}"><span class="shift-badge {badge_cls}">{emoji} {shift_name}</span></div>', unsafe_allow_html=True)
        uploaded = st.file_uploader(
            f"{shift_name} PDF",
            type=["pdf"],
            key=f"upload_{shift_name}",
            label_visibility="collapsed"
        )
        if uploaded is not None:
            st.caption(f"📎 {uploaded.name}")
            if st.button(f"🚀 {shift_name} Process करें", key=f"process_{shift_name}", use_container_width=True):
                with st.spinner(f"{shift_name} parse हो रहा है... (Groq AI)"):
                    pdf_bytes = uploaded.read()
                    staff_list, err = parse_pdf_with_groq(pdf_bytes, shift_name, pdf_date_str)
                    if err:
                        st.error(f"❌ Error: {err}")
                    elif not staff_list:
                        st.warning(f"⚠️ {shift_name}: कोई कर्मचारी नहीं मिला")
                    else:
                        if is_historical:
                            count = load_historical_pdf(shift_name, staff_list, pdf_date_str)
                            st.success(f"📚 {shift_name}: {count} records Audit_Log में")
                        else:
                            new_staff = update_shift_sheet(shift_name, staff_list, pdf_date_str)
                            st.success(f"✅ {shift_name}: {len(staff_list)} कर्मचारी load")
                            if new_staff:
                                if "new_staff_alerts" not in st.session_state:
                                    st.session_state["new_staff_alerts"] = []
                                st.session_state["new_staff_alerts"].extend(new_staff)
                        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
#  CURRENT DATE DUTY — तीनों shifts side by side
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(f'<div class="section-title">📋 वर्तमान ड्यूटी — {today_str}</div>', unsafe_allow_html=True)

duty_cols = st.columns(3)
shift_styles = [
    ("🟡 Shift 1", "sc-s1", "s1", "#ffd700"),
    ("🟢 Shift 2", "sc-s2", "s2", "#4ade80"),
    ("🔵 Shift 3", "sc-s3", "s3", "#60a5fa"),
]

for idx, (s_label, card_cls, badge_cls, color) in enumerate(shift_styles):
    s_name = SHIFT_NAMES[idx]
    s_df = shift_dfs.get(s_name, pd.DataFrame())
    with duty_cols[idx]:
        count = len(s_df)
        st.markdown(f"""
        <div class="shift-card {card_cls}">
            <span class="shift-badge {badge_cls}">{s_label}</span>
            <div class="count">{count}</div>
            <div class="unit">कर्मचारी</div>
        </div>""", unsafe_allow_html=True)
        if not s_df.empty:
            disp_cols = [c for c in ["Employee_Name","Designation","Mobile_No"] if c in s_df.columns]
            rename_map = {"Employee_Name":"नाम","Designation":"पद","Mobile_No":"मोबाइल"}
            st.dataframe(
                s_df[disp_cols].rename(columns=rename_map),
                use_container_width=True, hide_index=True, height=280
            )
            st.download_button(
                label=f"⬇️ {s_name} Excel",
                data=df_to_excel_bytes(s_df, s_name),
                file_name=f"{s_name}_{today_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key=f"dl_{s_name}"
            )
        else:
            st.info(f"अभी कोई data नहीं\nPDF upload करें ↑")

# ══════════════════════════════════════════════════════════════════════════════
#  TABS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🤖 AI Analysis",
    "🔍 कर्मचारी खोज",
    "👥 Master Data",
    "🌴 अवकाश",
    "📜 Audit Log",
    "➕ कर्मचारी जोड़ें"
])

# ─── TAB 1: AI Analysis ───────────────────────────────────────────────────────
with tab1:
    st.markdown('<div class="section-title">🤖 AI Duty Analysis (Groq llama-3.3-70b)</div>', unsafe_allow_html=True)

    ai_c1, ai_c2 = st.columns(2)

    with ai_c1:
        st.markdown('<div class="ai-card">', unsafe_allow_html=True)
        st.markdown("**📊 Pattern Analysis**")
        st.caption("पिछले duty patterns देखकर bias और fairness check करे")
        if st.button("🔍 Pattern Analyze करें", use_container_width=True, key="btn_pattern"):
            with st.spinner("AI analysis कर रहा है..."):
                result = ai_pattern_analysis(audit_df)
                st.session_state["pattern_result"] = result
        if "pattern_result" in st.session_state:
            st.markdown(f'<div class="ai-response">{st.session_state["pattern_result"]}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with ai_c2:
        st.markdown('<div class="ai-card">', unsafe_allow_html=True)
        st.markdown("**🎯 Virtual Duty Suggestion**")
        st.caption("AI suggest करेगा — सिर्फ preview, sheet में नहीं जाएगा")
        if st.button("✨ Virtual Duty Suggest", use_container_width=True, key="btn_virtual"):
            with st.spinner("AI duty suggest कर रहा है..."):
                result = ai_virtual_duty_suggest(audit_df, master_df)
                st.session_state["virtual_result"] = result
        if "virtual_result" in st.session_state:
            st.markdown(f'<div class="ai-response">{st.session_state["virtual_result"]}</div>', unsafe_allow_html=True)
            st.caption("⚠️ यह सिर्फ AI suggestion है — sheet में कोई बदलाव नहीं हुआ")
        st.markdown('</div>', unsafe_allow_html=True)

# ─── TAB 2: Employee Search ───────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="section-title">🔍 मोबाइल नंबर से कर्मचारी खोजें</div>', unsafe_allow_html=True)

    sc1, sc2 = st.columns([3, 1])
    with sc1:
        search_mobile = st.text_input("📱 मोबाइल नंबर", placeholder="10 अंकों का नंबर...", key="mob_search", max_chars=10)
    with sc2:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        search_btn = st.button("🔍 खोजें", use_container_width=True, key="mob_search_btn")

    if search_btn or (search_mobile and len(search_mobile.strip()) == 10):
        mob_q = search_mobile.strip()
        if mob_q.isdigit() and len(mob_q) == 10:
            emp_data, err = ai_employee_search(mob_q, master_df, shift_dfs, audit_df, avkaash_df)
            if err:
                st.markdown(f"""
                <div style="background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.3);
                    border-radius:14px;padding:20px;margin-top:12px;text-align:center;">
                    <div style="font-size:2rem;">🔍</div>
                    <div style="color:#f87171;font-weight:700;">मोबाइल नं. {mob_q} से कोई कर्मचारी नहीं मिला</div>
                </div>""", unsafe_allow_html=True)
            else:
                # Status
                if mob_q in active_leave_mobs:
                    ds,sc_color = "🌴 अवकाश पर","#f97316"
                    glow,bc = "rgba(249,115,22,0.15)","rgba(249,115,22,0.4)"
                elif emp_data["current_shift"] != "—":
                    ds,sc_color = f"🟢 {emp_data['current_shift']}","#22c55e"
                    glow,bc = "rgba(34,197,94,0.15)","rgba(34,197,94,0.4)"
                elif emp_data["status"] == 0:
                    ds,sc_color = "🔴 निष्क्रिय","#ef4444"
                    glow,bc = "rgba(239,68,68,0.15)","rgba(239,68,68,0.4)"
                else:
                    ds,sc_color = "⏳ Unassigned","#a855f7"
                    glow,bc = "rgba(168,85,247,0.15)","rgba(168,85,247,0.4)"

                # History table
                hist_html = ""
                if emp_data["history"]:
                    rows_html = "".join([f"<tr><td style='padding:4px 8px;color:#a0b8d8'>{h[0]}</td><td style='padding:4px 8px;color:#60a5fa'>{h[1]}</td><td style='padding:4px 8px;color:#4ade80'>{h[2]}</td></tr>" for h in emp_data["history"][-10:]])
                    hist_html = f"""<div style="margin-top:16px;">
                        <div style="font-size:0.78rem;color:#7a92b8;margin-bottom:6px;">📅 पिछली 10 duties:</div>
                        <table style="width:100%;border-collapse:collapse;font-size:0.8rem;">
                            <tr style="background:rgba(255,255,255,0.05)">
                                <th style="padding:4px 8px;text-align:left;color:#7a92b8">तारीख</th>
                                <th style="padding:4px 8px;text-align:left;color:#7a92b8">Shift</th>
                                <th style="padding:4px 8px;text-align:left;color:#7a92b8">Action</th>
                            </tr>
                            {rows_html}
                        </table></div>"""

                # Leave html
                leave_html = ""
                if emp_data["leaves"]:
                    leave_rows = "".join([f"<div style='font-size:0.82rem;color:#fb923c;padding:4px 0'>{l[0]} → {l[1]} | {l[2]} | {l[3]}</div>" for l in emp_data["leaves"]])
                    leave_html = f"""<div style="background:rgba(249,115,22,0.1);border:1px solid rgba(249,115,22,0.25);border-radius:10px;padding:10px 16px;margin-top:14px;">
                        <div style="font-size:0.78rem;color:#7a92b8;margin-bottom:6px;">🌴 अवकाश इतिहास:</div>
                        {leave_rows}</div>"""

                st.markdown(f"""
                <div style="background:linear-gradient(135deg,rgba(13,27,62,0.97),rgba(26,45,90,0.82));
                    border:1px solid {bc};border-left:5px solid {sc_color};border-radius:20px;
                    padding:28px 32px;margin-top:16px;box-shadow:0 8px 40px {glow};">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;">
                        <div>
                            <div style="font-size:1.6rem;font-weight:800;color:#e8f0ff;margin-bottom:6px;font-family:'Rajdhani',sans-serif;">
                                👤 {emp_data['name']}
                            </div>
                            <div style="font-size:0.85rem;color:#7a92b8;margin-bottom:3px;">🏷️ {emp_data['designation']}</div>
                            <div style="font-size:0.85rem;color:#7a92b8;">📱 {emp_data['mobile']}</div>
                        </div>
                        <div style="background:rgba(0,0,0,0.4);border:1px solid {bc};border-radius:16px;padding:16px 28px;text-align:center;">
                            <div style="font-size:1.05rem;font-weight:700;color:{sc_color};margin-bottom:6px;">{ds}</div>
                        </div>
                    </div>
                    {hist_html}
                    {leave_html}
                </div>""", unsafe_allow_html=True)
        else:
            st.warning("⚠️ 10 अंकों का सही नंबर दर्ज करें")

# ─── TAB 3: Master Data ───────────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="section-title">👥 Master Data — सम्पूर्ण कर्मचारी सूची</div>', unsafe_allow_html=True)
    if master_df.empty:
        st.info("Master Data खाली है। PDF upload करें या नीचे manually जोड़ें।")
    else:
        ms1, ms2 = st.columns([2,1])
        with ms1:
            m_search = st.text_input("🔍 नाम / मोबाइल खोजें", placeholder="खोजें...", key="master_search")
        with ms2:
            m_status = st.selectbox("स्थिति", ["सभी","Active (1)","Inactive (0)"], key="master_status")

        disp = master_df.copy()
        if m_search:
            mask = disp.get("Employee_Name", pd.Series()).astype(str).str.contains(m_search, case=False, na=False)
            if "Mobile_No" in disp.columns:
                mask |= disp["Mobile_No"].astype(str).str.contains(m_search, na=False)
            disp = disp[mask]
        if m_status == "Active (1)" and "STATUS" in disp.columns:
            disp = disp[pd.to_numeric(disp["STATUS"], errors="coerce") == 1]
        elif m_status == "Inactive (0)" and "STATUS" in disp.columns:
            disp = disp[pd.to_numeric(disp["STATUS"], errors="coerce") == 0]

        st.dataframe(disp, use_container_width=True, hide_index=True, height=380)
        md1, _ = st.columns([1,3])
        with md1:
            st.download_button("⬇️ Master Data Excel",
                data=df_to_excel_bytes(disp, "Master_Data"),
                file_name=f"Master_Data_{today_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
        st.caption(f"कुल: {len(disp)} कर्मचारी")

# ─── TAB 4: Avkaash ───────────────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="section-title">🌴 अवकाश प्रबंधन</div>', unsafe_allow_html=True)

    if not avkaash_df.empty:
        st.dataframe(avkaash_df, use_container_width=True, hide_index=True, height=280)
        av1, _ = st.columns([1,3])
        with av1:
            st.download_button("⬇️ अवकाश Excel",
                data=df_to_excel_bytes(avkaash_df, "Avkaash"),
                file_name=f"Avkaash_{today_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
    else:
        st.info("कोई अवकाश record नहीं है।")

    st.markdown("---")
    st.markdown("**नया अवकाश जोड़ें**")
    lc1, lc2, lc3 = st.columns(3)
    with lc1:
        l_mob = st.text_input("मोबाइल नं. *", key="l_mob", max_chars=10)
        l_name = st.text_input("नाम", key="l_name")
    with lc2:
        l_desig = st.text_input("पद", key="l_desig")
        l_from = st.date_input("छुट्टी से", key="l_from", value=now_ist().date())
    with lc3:
        l_to = st.date_input("छुट्टी तक", key="l_to", value=now_ist().date())
        l_sd = st.number_input("SD Days", value=0, min_value=0, key="l_sd")
    l_reason = st.text_input("कारण", key="l_reason")

    if st.button("✅ अवकाश दर्ज करें", key="save_leave"):
        if l_mob and l_name:
            try:
                add_leave(
                    l_mob, l_name, l_desig,
                    l_from.strftime("%d-%m-%Y"),
                    l_to.strftime("%d-%m-%Y"),
                    l_reason, l_sd
                )
                st.success("✅ अवकाश दर्ज हो गया!")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.warning("मोबाइल नं. और नाम ज़रूरी है।")

# ─── TAB 5: Audit Log ─────────────────────────────────────────────────────────
with tab5:
    st.markdown('<div class="section-title">📜 Audit Log — सम्पूर्ण इतिहास</div>', unsafe_allow_html=True)

    if audit_df.empty:
        st.info("अभी कोई audit record नहीं है। PDF upload करने पर यहाँ entries आएंगी।")
    else:
        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            date_filter = st.text_input("तारीख फ़िल्टर (DD-MM-YYYY)", placeholder="जैसे: 15-03-2025", key="audit_date")
        with ac2:
            shift_filter = st.selectbox("Shift", ["सभी"] + SHIFT_NAMES, key="audit_shift")
        with ac3:
            action_filter = st.selectbox("Action", ["सभी","Loaded","Historical","Added"], key="audit_action")

        a_df = audit_df.copy()
        if date_filter and "Date" in a_df.columns:
            a_df = a_df[a_df["Date"].str.contains(date_filter, na=False)]
        if shift_filter != "सभी" and "Shift" in a_df.columns:
            a_df = a_df[a_df["Shift"] == shift_filter]
        if action_filter != "सभी" and "Action" in a_df.columns:
            a_df = a_df[a_df["Action"] == action_filter]

        a_sorted = a_df.sort_values("Date", ascending=False) if "Date" in a_df.columns else a_df
        st.dataframe(a_sorted, use_container_width=True, hide_index=True, height=380)

        al1, _ = st.columns([1,3])
        with al1:
            st.download_button("⬇️ Audit Log Excel",
                data=df_to_excel_bytes(a_sorted, "Audit_Log"),
                file_name=f"Audit_Log_{today_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
        st.caption(f"कुल records: {len(a_df)}")

# ─── TAB 6: Add Employee ──────────────────────────────────────────────────────
with tab6:
    st.markdown('<div class="section-title">➕ नया कर्मचारी जोड़ें (Manual)</div>', unsafe_allow_html=True)

    ec1, ec2 = st.columns(2)
    with ec1:
        e_mob = st.text_input("मोबाइल नं. *", key="e_mob", max_chars=10)
        e_name = st.text_input("नाम *", key="e_name")
    with ec2:
        e_desig = st.text_input("पद / Designation", key="e_desig")
        e_status = st.selectbox("स्थिति", [1,0], format_func=lambda x: "सक्रिय (Active)" if x==1 else "निष्क्रिय (Inactive)", key="e_status")

    if st.button("💾 कर्मचारी सहेजें", key="save_employee"):
        if e_mob and e_name:
            try:
                add_employee_manual(e_mob, e_name, e_desig, e_status)
                st.success(f"✅ {e_name} Master_Data में जोड़ा गया!")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.warning("मोबाइल नं. और नाम ज़रूरी है।")

    st.markdown("---")
    st.markdown('<div class="section-title">📚 JSON से Bulk Import</div>', unsafe_allow_html=True)
    st.caption("अपनी staff list JSON paste करें")
    sample_json = '''[
  {"Mobile_No": "9876543210", "Employee_Name": "राम कुमार", "Designation": "SI"},
  {"Mobile_No": "9876543211", "Employee_Name": "श्याम लाल", "Designation": "HC"}
]'''
    bulk_json = st.text_area("JSON Staff List", value="", height=150, placeholder=sample_json, key="bulk_json")

    if st.button("📥 Bulk Import करें", key="bulk_import"):
        if bulk_json.strip():
            try:
                staff_list = json.loads(bulk_json)
                client = get_client()
                sh = client.open_by_key(SHEET_ID)
                ws = sh.worksheet("Master_Data")
                existing = {str(r.get("Mobile_No","")).strip() for r in ws.get_all_records()}
                added = 0
                for s in staff_list:
                    mob = str(s.get("Mobile_No","")).strip()
                    name = str(s.get("Employee_Name","")).strip()
                    desig = str(s.get("Designation","")).strip()
                    if name and mob not in existing:
                        ws.append_row([mob, name, desig, 1])
                        existing.add(mob)
                        added += 1
                load_all_data.clear()
                st.success(f"✅ {added} नए कर्मचारी import हुए!")
                st.rerun()
            except json.JSONDecodeError:
                st.error("❌ JSON format गलत है। ऊपर sample देखें।")
            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.warning("JSON paste करें।")

# ══════════════════════════════════════════════════════════════════════════════
#  FOOTER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(f"""
<div class="footer">
  🚨 साइबर क्राइम हेल्पलाइन <strong>1930</strong> &nbsp;|&nbsp;
  ड्यूटी रोस्टर प्रणाली &nbsp;|&nbsp;
  <span class="live-dot"></span>
  {now_ist().strftime('%d-%m-%Y %H:%M')} IST
</div>
""", unsafe_allow_html=True)
