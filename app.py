import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta, date
import json
import io
import base64
import re
import time
import html as _html

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
    from openai import OpenAI as _OpenAI
    DEEPSEEK_AVAILABLE = True
except ImportError:
    DEEPSEEK_AVAILABLE = False

try:
    from PIL import Image
    import fitz
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# ══════════════════════════════════════════════════════════════════════════════
#  UNIFIED AI CALLER
# ══════════════════════════════════════════════════════════════════════════════
def ai_call(messages, max_tokens=1000, temperature=0.1):
    if DEEPSEEK_AVAILABLE:
        try:
            ds_key = st.secrets.get("deepseek", {}).get("api_key", "")
            if ds_key:
                ds_client = _OpenAI(api_key=ds_key, base_url="https://api.deepseek.com")
                resp = ds_client.chat.completions.create(
                    model="deepseek-chat", messages=messages,
                    max_tokens=max_tokens, temperature=temperature)
                return resp.choices[0].message.content.strip(), "DeepSeek V3", None
        except:
            pass

    if GROQ_AVAILABLE:
        groq_key = st.secrets.get("groq", {}).get("api_key", "")
        if groq_key:
            groq_client = Groq(api_key=groq_key)
            for model in ["llama-3.3-70b-versatile", "llama3-8b-8192", "mixtral-8x7b-32768"]:
                try:
                    time.sleep(1)
                    resp = groq_client.chat.completions.create(
                        model=model, messages=messages,
                        max_tokens=max_tokens, temperature=temperature)
                    return resp.choices[0].message.content.strip(), f"Groq/{model}", None
                except Exception as g_err:
                    last_err = g_err
                    time.sleep(2)
            return "", "none", f"Groq सभी models fail: {last_err}"

    return "", "none", "कोई AI available नहीं"


def ai_call_with_image(messages_with_image, max_tokens=2000, temperature=0.1):
    if GROQ_AVAILABLE:
        groq_key = st.secrets.get("groq", {}).get("api_key", "")
        if groq_key:
            groq_client = Groq(api_key=groq_key)
            try:
                resp = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile", messages=messages_with_image,
                    max_tokens=max_tokens, temperature=temperature)
                return resp.choices[0].message.content.strip(), "Groq/Vision", None
            except Exception as e:
                return "", "none", f"Vision error: {e}"
    return "", "none", "Groq unavailable"


def gspread_append_rows(ws, rows, retries=3, pause=15):
    if not rows:
        return
    for attempt in range(retries):
        try:
            ws.append_rows(rows)
            if attempt > 0:
                time.sleep(2)
            return
        except gspread.exceptions.APIError as e:
            if "429" in str(e) or "Quota" in str(e):
                time.sleep(pause * (attempt + 1))
            else:
                raise
    ws.append_rows(rows)


def safe_json_parse(raw_text):
    raw = re.sub(r'```json|```', '', raw_text).strip()
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        staff_matches = re.findall(
            r'\{[^{}]*"Mobile_No"[^{}]*"Employee_Name"[^{}]*"Designation"[^{}]*\}', raw)
        if staff_matches:
            try:
                staff_list = [json.loads(m) for m in staff_matches]
                date_match = re.search(r'"shift_date"\s*:\s*"([^"]*)"', raw)
                shift_date = date_match.group(1) if date_match else ""
                return {"shift_date": shift_date, "staff": staff_list}, None
            except:
                pass
        return None, f"JSON repair fail: {raw[:200]}..."


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

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;500;600;700;900&family=Rajdhani:wght@500;600;700&family=Space+Mono:wght@400;700&display=swap');

:root {
  --navy-deep:#060d1f; --navy-mid:#0d1b3e; --navy-light:#1a2d5a; --navy-glow:#1e3a7a;
  --accent-blue:#2E75B6; --accent-cyan:#00d4ff; --accent-gold:#ffd700;
  --accent-green:#22c55e; --accent-red:#ef4444; --accent-orange:#f97316;
  --accent-purple:#a855f7; --glass-bg:rgba(255,255,255,0.04);
  --glass-border:rgba(255,255,255,0.10); --text-primary:#e8f0ff; --text-muted:#7a92b8;
}
html,body,[class*="css"]{font-family:'Noto Sans Devanagari',sans-serif;background:var(--navy-deep)!important;color:var(--text-primary)!important;}
.stApp{background:linear-gradient(135deg,#060d1f 0%,#0a1628 40%,#060d1f 100%)!important;min-height:100vh;}
.main .block-container{padding:1.5rem 2rem 3rem 2rem!important;max-width:1400px!important;}

.login-wrap{max-width:420px;margin:60px auto 0 auto;background:linear-gradient(135deg,rgba(13,27,62,0.98),rgba(26,45,90,0.90));border:1px solid rgba(0,212,255,0.2);border-radius:24px;padding:44px 36px 16px;text-align:center;box-shadow:0 0 60px rgba(46,117,182,0.25);}
.login-icon{font-size:3rem;margin-bottom:10px;display:block;}
.login-title{font-size:1.4rem;font-weight:800;color:var(--text-primary);margin-bottom:4px;font-family:'Rajdhani',sans-serif;letter-spacing:1px;}
.login-sub{font-size:0.78rem;color:var(--text-muted);margin-bottom:0px;letter-spacing:2px;text-transform:uppercase;}

.magic-header-wrap{position:relative;margin-bottom:32px;border-radius:20px;padding:3px;overflow:hidden;background:linear-gradient(135deg,rgba(0,212,255,0.3),rgba(46,117,182,0.4),rgba(255,215,0,0.2),rgba(0,212,255,0.3));background-size:300% 300%;animation:gradient-shift 8s ease infinite;}
@keyframes gradient-shift{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
.magic-header-inner{position:relative;z-index:1;background:linear-gradient(135deg,#0d1b3e 0%,#132448 30%,#1a2d5a 60%,#0d1b3e 100%);border-radius:18px;padding:28px 36px 24px;text-align:center;overflow:hidden;}
.magic-header-inner::after{content:'';position:absolute;top:-50%;left:-50%;width:200%;height:200%;background:linear-gradient(105deg,transparent 40%,rgba(255,255,255,0.04) 50%,transparent 60%);animation:sweep 6s ease-in-out infinite;pointer-events:none;}
@keyframes sweep{0%{transform:translateX(-100%)}50%,100%{transform:translateX(100%)}}
.magic-header-inner h1{font-family:'Rajdhani','Noto Sans Devanagari',sans-serif;font-size:2.2rem;font-weight:700;margin:0 0 8px 0;background:linear-gradient(90deg,#fff 0%,#a8d4ff 20%,#ffd700 40%,#ffffff 60%,#a8d4ff 80%,#ffd700 100%);background-size:300% auto;-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;animation:shimmer-text 4s linear infinite;letter-spacing:1.5px;position:relative;z-index:1;}
@keyframes shimmer-text{0%{background-position:300% center}100%{background-position:-300% center}}
.magic-header-inner .subtitle{font-size:0.88rem;color:var(--text-muted);letter-spacing:3px;text-transform:uppercase;font-weight:600;position:relative;z-index:1;}
.header-badge{display:inline-block;background:rgba(0,212,255,0.12);border:1px solid rgba(0,212,255,0.3);border-radius:20px;padding:4px 14px;font-size:0.72rem;color:#00d4ff;letter-spacing:2px;text-transform:uppercase;margin-top:10px;position:relative;z-index:1;}
.particle{position:absolute;border-radius:50%;animation:float-up 4s ease-in infinite;opacity:0;z-index:2;}
.p1{width:5px;height:5px;background:#00cfff;left:8%;animation-delay:0s}
.p2{width:3px;height:3px;background:#ff0080;left:22%;animation-delay:1s}
.p3{width:6px;height:6px;background:#ffd700;left:48%;animation-delay:2s}
.p4{width:4px;height:4px;background:#00ff88;left:72%;animation-delay:0.5s}
.p5{width:5px;height:5px;background:#7f5fff;left:90%;animation-delay:1.5s}
.p6{width:3px;height:3px;background:#ff6b00;left:35%;animation-delay:2.5s}
@keyframes float-up{0%{opacity:0;transform:translateY(40px) scale(0)}20%{opacity:1}80%{opacity:0.6}100%{opacity:0;transform:translateY(-30px) scale(1.5)}}

.metric-card{background:var(--glass-bg);backdrop-filter:blur(12px);border:1px solid var(--glass-border);border-radius:16px;padding:20px 16px;text-align:center;position:relative;overflow:hidden;transition:transform 0.25s,box-shadow 0.25s;}
.metric-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:16px 16px 0 0;}
.metric-card:hover{transform:translateY(-5px);}
.metric-card .val{font-family:'Rajdhani',monospace;font-size:3rem;font-weight:700;line-height:1;margin-bottom:6px;}
.metric-card .lbl{font-size:0.78rem;color:var(--text-muted);font-weight:600;letter-spacing:0.5px;}
.metric-card .icon{font-size:1.4rem;margin-bottom:8px;display:block;}
.card-blue{box-shadow:0 4px 30px rgba(46,117,182,0.2);border-color:rgba(46,117,182,0.35)}.card-blue .val{color:#60a5fa}.card-blue::before{background:linear-gradient(90deg,#2E75B6,#60a5fa)}
.card-gold{box-shadow:0 4px 30px rgba(255,215,0,0.2);border-color:rgba(255,215,0,0.35)}.card-gold .val{color:#ffd700}.card-gold::before{background:linear-gradient(90deg,#b8860b,#ffd700)}
.card-green{box-shadow:0 4px 30px rgba(34,197,94,0.2);border-color:rgba(34,197,94,0.35)}.card-green .val{color:#4ade80}.card-green::before{background:linear-gradient(90deg,#16a34a,#4ade80)}
.card-cyan{box-shadow:0 4px 30px rgba(0,212,255,0.2);border-color:rgba(0,212,255,0.35)}.card-cyan .val{color:#00d4ff}.card-cyan::before{background:linear-gradient(90deg,#0ea5e9,#00d4ff)}
.card-orange{box-shadow:0 4px 30px rgba(249,115,22,0.2);border-color:rgba(249,115,22,0.35)}.card-orange .val{color:#fb923c}.card-orange::before{background:linear-gradient(90deg,#ea580c,#fb923c)}
.card-purple{box-shadow:0 4px 30px rgba(168,85,247,0.2);border-color:rgba(168,85,247,0.35)}.card-purple .val{color:#c084fc}.card-purple::before{background:linear-gradient(90deg,#9333ea,#c084fc)}

.shift-badge{display:inline-block;padding:4px 14px;border-radius:20px;font-size:0.78rem;font-weight:700;border:1px solid transparent;}
.s1{background:rgba(255,192,0,0.15);color:#ffd700;border-color:rgba(255,192,0,0.4)}
.s2{background:rgba(34,197,94,0.15);color:#4ade80;border-color:rgba(34,197,94,0.4)}
.s3{background:rgba(96,165,250,0.15);color:#60a5fa;border-color:rgba(96,165,250,0.4)}
.shift-card{background:var(--glass-bg);border:1px solid var(--glass-border);border-radius:16px;padding:18px 16px 12px;text-align:center;transition:transform 0.2s;margin-bottom:12px;}
.shift-card:hover{transform:translateY(-3px)}
.shift-card .count{font-family:'Rajdhani',monospace;font-size:2.8rem;font-weight:700;line-height:1}
.shift-card .unit{font-size:0.72rem;color:var(--text-muted);font-weight:600}
.sc-s1{border-top:3px solid #ffd700;box-shadow:0 4px 20px rgba(255,215,0,0.12)}.sc-s1 .count{color:#ffd700}
.sc-s2{border-top:3px solid #4ade80;box-shadow:0 4px 20px rgba(74,222,128,0.12)}.sc-s2 .count{color:#4ade80}
.sc-s3{border-top:3px solid #60a5fa;box-shadow:0 4px 20px rgba(96,165,250,0.12)}.sc-s3 .count{color:#60a5fa}

.section-title{font-family:'Rajdhani','Noto Sans Devanagari',sans-serif;font-size:1.05rem;font-weight:700;color:var(--text-primary);letter-spacing:1px;padding:10px 16px;margin:24px 0 14px 0;background:var(--glass-bg);border:1px solid var(--glass-border);border-left:4px solid var(--accent-blue);border-radius:0 10px 10px 0;display:flex;align-items:center;gap:8px;}
.ai-card{background:linear-gradient(135deg,rgba(168,85,247,0.08),rgba(46,117,182,0.08));border:1px solid rgba(168,85,247,0.3);border-radius:16px;padding:20px;margin-bottom:12px;}
.ai-response{background:rgba(0,0,0,0.3);border:1px solid rgba(168,85,247,0.2);border-radius:12px;padding:16px;margin-top:12px;font-size:0.88rem;line-height:1.8;color:var(--text-primary);white-space:pre-wrap;}

.stTabs [data-baseweb="tab-list"]{background:var(--glass-bg)!important;border:1px solid var(--glass-border)!important;border-radius:12px!important;padding:4px!important;gap:4px!important;}
.stTabs [data-baseweb="tab"]{background:transparent!important;border-radius:8px!important;color:var(--text-muted)!important;font-weight:600!important;font-size:0.82rem!important;padding:8px 16px!important;transition:all 0.2s!important;border:none!important;}
.stTabs [aria-selected="true"]{background:linear-gradient(135deg,var(--navy-glow),var(--accent-blue))!important;color:white!important;}
[data-testid="stDataFrame"]{border:1px solid var(--glass-border)!important;border-radius:12px!important;overflow:hidden!important;}

.stTextInput>div>div>input,div[data-testid="stTextInput"] input{background:#0d1b3e!important;border:1px solid rgba(255,255,255,0.12)!important;border-radius:10px!important;color:#e8f0ff!important;caret-color:#00d4ff!important;font-family:'Noto Sans Devanagari',sans-serif!important;}
.stTextInput>div>div>input:focus,div[data-testid="stTextInput"] input:focus{border-color:var(--accent-blue)!important;box-shadow:0 0 0 3px rgba(46,117,182,0.2)!important;outline:none!important;}
.stTextInput>div>div>input::placeholder,div[data-testid="stTextInput"] input::placeholder{color:#4a6080!important;opacity:1!important;}
.stTextInput label,.stTextInput label p,div[data-testid="stTextInput"] label,div[data-testid="stTextInput"] label p{color:#a0b8d8!important;font-weight:600!important;font-size:0.85rem!important;}
input[type="password"]{background:#0d1b3e!important;color:#e8f0ff!important;border:1px solid rgba(255,255,255,0.12)!important;border-radius:10px!important;caret-color:#00d4ff!important;}
.stSelectbox>div>div{background:#0d1b3e!important;border:1px solid rgba(255,255,255,0.12)!important;border-radius:10px!important;color:var(--text-primary)!important;}
.stTextArea textarea{background:#0d1b3e!important;border:1px solid rgba(255,255,255,0.12)!important;border-radius:10px!important;color:var(--text-primary)!important;}
.stButton>button{background:linear-gradient(135deg,var(--navy-mid),var(--accent-blue))!important;color:white!important;font-weight:700!important;font-size:0.9rem!important;border-radius:10px!important;border:1px solid rgba(46,117,182,0.5)!important;padding:10px 22px!important;transition:all 0.25s!important;}
.stButton>button:hover{background:linear-gradient(135deg,var(--accent-blue),#1a4d8a)!important;transform:translateY(-2px)!important;box-shadow:0 6px 20px rgba(46,117,182,0.4)!important;}
.stDownloadButton>button{background:linear-gradient(135deg,#16a34a,#15803d)!important;color:white!important;font-weight:700!important;font-size:0.82rem!important;border-radius:8px!important;border:1px solid rgba(34,197,94,0.4)!important;}
.stDownloadButton>button:hover{transform:translateY(-2px)!important;box-shadow:0 6px 18px rgba(22,163,74,0.4)!important;}
.stAlert{border-radius:10px!important;border-left:4px solid!important;}
[data-testid="stInfoMessage"]{background:rgba(46,117,182,0.1)!important;border-color:var(--accent-blue)!important;}
[data-testid="stSuccessMessage"]{background:rgba(34,197,94,0.1)!important;border-color:var(--accent-green)!important;}
[data-testid="stWarningMessage"]{background:rgba(249,115,22,0.1)!important;border-color:var(--accent-orange)!important;}
.stSpinner>div{border-top-color:var(--accent-cyan)!important;}
hr{border-color:var(--glass-border)!important;margin:20px 0!important;}

.clock-box{background:linear-gradient(135deg,var(--navy-deep),var(--navy-mid));border-radius:14px;padding:18px 16px;text-align:center;border:1px solid rgba(0,212,255,0.2);box-shadow:0 0 30px rgba(0,212,255,0.12);margin-top:8px;}
.clock-label{font-size:0.65rem;color:var(--text-muted);letter-spacing:2px;text-transform:uppercase;margin-bottom:6px}
.clock-date{font-size:1rem;font-weight:700;color:var(--accent-gold);margin-bottom:6px}
.clock-time{font-size:2rem;font-weight:700;color:var(--accent-cyan);font-family:'Space Mono',monospace;letter-spacing:3px;text-shadow:0 0 20px rgba(0,212,255,0.5)}
.clock-city{font-size:0.65rem;color:var(--text-muted);margin-top:6px;letter-spacing:1.5px}
.footer{text-align:center;color:var(--text-muted);font-size:0.75rem;padding:16px;border-top:1px solid var(--glass-border);margin-top:32px;letter-spacing:0.5px;}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-track{background:var(--navy-deep)}::-webkit-scrollbar-thumb{background:var(--navy-glow);border-radius:3px}
@keyframes pulse-dot{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.4;transform:scale(1.5)}}
.live-dot{display:inline-block;width:8px;height:8px;background:#22c55e;border-radius:50%;animation:pulse-dot 1.5s ease-in-out infinite;box-shadow:0 0 6px #22c55e;margin-right:6px;vertical-align:middle;}
@keyframes blink-alert{0%,100%{box-shadow:0 0 20px rgba(255,215,0,0.6);border-color:rgba(255,215,0,0.8)}50%{box-shadow:0 0 40px rgba(255,215,0,0.2);border-color:rgba(255,215,0,0.3)}}
.new-staff-alert{background:rgba(255,215,0,0.08);border:2px solid rgba(255,215,0,0.6);border-radius:14px;padding:14px 20px;margin:8px 0;animation:blink-alert 1.5s ease-in-out infinite;display:flex;align-items:center;gap:12px;}
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
        </div>""", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            pwd = st.text_input("पासवर्ड दर्ज करें", type="password", key="pwd_input", placeholder="••••••••")
            if st.button("🔓 लॉगिन करें", use_container_width=True, key="login_btn"):
                if pwd == st.secrets["passwords"]["app_password"]:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("❌ गलत पासवर्ड!")
        return False
    return True

if not check_password():
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
SHEET_ID    = "1TSq6eMn3jbFNqZuMjIpll09NWqO3XOEOmUCBs-0CATk"
SCOPES      = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
SHIFT_NAMES = ["Shift1","Shift2","Shift3"]
HINDI_MONTHS = {1:"जनवरी",2:"फ़रवरी",3:"मार्च",4:"अप्रैल",5:"मई",6:"जून",
                7:"जुलाई",8:"अगस्त",9:"सितम्बर",10:"अक्टूबर",11:"नवम्बर",12:"दिसम्बर"}

NAME_ALIASES    = ["Name","Employee_Name","employee_name","नाम","NAAM","कर्मचारी नाम","Staff_Name","staff_name"]
DESIG_ALIASES   = ["Designation","designation","Rank","rank","पदनाम","PAD","पद","RANK","DESIGNATION"]
MOBILE_ALIASES  = ["Mobile_No","mobile_no","Mobile","mobile","मो0न0","मोबाइल","Phone","phone","Contact","contact","PC NUMBER","pc_number","Mo_No","MobileNo"]
REMARKS_ALIASES = ["Remarks","remarks","REMARK","remark","टिप्पणी","Note","note","REMARKS","Notes"]

def find_col(headers_or_record, *alias_lists):
    keys = list(headers_or_record.keys()) if isinstance(headers_or_record, dict) else list(headers_or_record)
    for aliases in alias_lists:
        for alias in aliases:
            for k in keys:
                if str(k).strip().lower() == str(alias).strip().lower():
                    return k
    return None

def col_idx_from_header(header_list, *alias_lists):
    for aliases in alias_lists:
        for alias in aliases:
            for i, h in enumerate(header_list):
                if str(h).strip().lower() == str(alias).strip().lower():
                    return i
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  PDF DATE EXTRACT
# ══════════════════════════════════════════════════════════════════════════════
def extract_date_from_pdf_text(text):
    if not text:
        return None
    for pat in [r'(?:दिनांक|दिनाांक|dinank|date)[^\d]*(\d{1,2})[./:_\-](\d{1,2})[./:_\-](\d{4})']:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            d, mo, yr = m.groups()
            try:
                return date(int(yr), int(mo), int(d))
            except:
                pass
    for pat in [r'(\d{1,2})[./:_\-](\d{1,2})[./:_\-](\d{4})']:
        m = re.search(pat, text)
        if m:
            d, mo, yr = m.groups()
            try:
                return date(int(yr), int(mo), int(d))
            except:
                pass
    return None

def extract_date_from_pdf_bytes(pdf_bytes):
    extracted_date = None
    if PDF_AVAILABLE:
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        d = extract_date_from_pdf_text(t)
                        if d:
                            extracted_date = d
                            break
        except:
            pass
    if not extracted_date and OCR_AVAILABLE:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page in doc:
                t = page.get_text()
                if t:
                    d = extract_date_from_pdf_text(t)
                    if d:
                        extracted_date = d
                        break
            doc.close()
        except:
            pass
    return extracted_date

# ══════════════════════════════════════════════════════════════════════════════
#  DUPLICATE CHECK
# ══════════════════════════════════════════════════════════════════════════════
def check_shift_already_loaded(audit_df, shift_name, date_str):
    if audit_df.empty:
        return False, 0
    date_c  = find_col(audit_df.columns.tolist(), ["Date","date"])
    shift_c = find_col(audit_df.columns.tolist(), ["Shift","shift"])
    if not date_c or not shift_c:
        return False, 0
    mask = (audit_df[date_c].astype(str).str.strip() == date_str) & \
           (audit_df[shift_c].astype(str).str.strip() == shift_name)
    count = mask.sum()
    return (count > 0), int(count)

# ══════════════════════════════════════════════════════════════════════════════
#  GOOGLE SHEETS
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_resource(show_spinner=False)
def get_client():
    creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=SCOPES)
    return gspread.authorize(creds)

def get_or_create_worksheet(sh, title, rows=10000, cols=20):
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=rows, cols=cols)

@st.cache_data(ttl=60, show_spinner=False)
def load_all_data(sheet_id):
    client = get_client()
    sh = client.open_by_key(sheet_id)
    try:
        master_df = pd.DataFrame(sh.worksheet("Master_Data").get_all_records())
    except:
        master_df = pd.DataFrame(columns=["Sr_No","Mobile_No","Designation","Name","Remarks"])
    shift_dfs = {}
    for s in SHIFT_NAMES:
        try:
            shift_dfs[s] = pd.DataFrame(sh.worksheet(s).get_all_records())
        except:
            shift_dfs[s] = pd.DataFrame(columns=["Mobile_No","Employee_Name","Designation","Shift_Date"])
    try:
        audit_df = pd.DataFrame(sh.worksheet("Audit_Log").get_all_records())
    except:
        audit_df = pd.DataFrame(columns=["Date","Shift","Mobile_No","Employee_Name","Designation","Action","Remarks"])
    try:
        avkaash_df = pd.DataFrame(sh.worksheet("Avkaash").get_all_records())
    except:
        avkaash_df = pd.DataFrame(columns=["Mobile_No","Designation","Name","Leave_From","Leave_To","Leave_Reason","Sd_Days","Status"])
    return master_df, shift_dfs, audit_df, avkaash_df

def setup_sheets():
    client = get_client()
    sh = client.open_by_key(SHEET_ID)
    ws = get_or_create_worksheet(sh, "Master_Data")
    if not ws.get_all_values():
        ws.append_row(["Sr_No","Mobile_No","Designation","Name","Remarks"])
    for s in SHIFT_NAMES:
        ws = get_or_create_worksheet(sh, s)
        if not ws.get_all_values():
            ws.append_row(["Mobile_No","Employee_Name","Designation","Shift_Date"])
    ws = get_or_create_worksheet(sh, "Audit_Log")
    if not ws.get_all_values():
        ws.append_row(["Date","Shift","Mobile_No","Employee_Name","Designation","Action","Remarks"])
    ws = get_or_create_worksheet(sh, "Avkaash")
    if not ws.get_all_values():
        ws.append_row(["Mobile_No","Designation","Name","Leave_From","Leave_To","Leave_Reason","Sd_Days","Status"])

# ══════════════════════════════════════════════════════════════════════════════
#  PDF PARSE
# ══════════════════════════════════════════════════════════════════════════════
def extract_text_pdfplumber(pdf_bytes):
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
    except:
        pass
    return text.strip()

def pdf_to_images_base64(pdf_bytes):
    images_b64 = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_num in range(min(len(doc), 5)):
            page = doc[page_num]
            pix  = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            b64  = base64.b64encode(pix.tobytes("png")).decode("utf-8")
            images_b64.append(b64)
        doc.close()
    except Exception as e:
        st.error(f"PDF image error: {e}")
    return images_b64

def parse_pdf_with_ai(pdf_bytes, shift_name, shift_date_str):
    text_content = ""
    if PDF_AVAILABLE:
        text_content = extract_text_pdfplumber(pdf_bytes)
    auto_date = extract_date_from_pdf_bytes(pdf_bytes)

    if text_content and len(text_content) > 100:
        prompt = f"""यह एक duty roster PDF का text है। सभी कर्मचारियों की जानकारी निकालो।

PDF Text:
{text_content[:3000]}

JSON format में return करो, कोई extra text नहीं:
{{"shift_date": "DD-MM-YYYY या empty","staff": [{{"Mobile_No": "10 digit number","Employee_Name": "नाम","Designation": "पद"}}]}}

Rules:
- Mobile_No: 10 अंकों का नंबर, नहीं मिले तो ""
- Employee_Name: पूरा नाम
- Designation: SI, HC, Constable, ASI आदि"""

        raw, model_used, err = ai_call([{"role":"user","content":prompt}], max_tokens=4000)
        if err:
            return [], f"AI Error: {err}", auto_date
        data, parse_err = safe_json_parse(raw)
        if parse_err or data is None:
            return [], f"JSON parse error: {parse_err}", auto_date
        final_date = auto_date or data.get("shift_date","") or shift_date_str
        return data.get("staff",[]), None, final_date

    else:
        if not OCR_AVAILABLE:
            return [], "PyMuPDF install नहीं है", auto_date
        images_b64 = pdf_to_images_base64(pdf_bytes)
        if not images_b64:
            return [], "PDF से images नहीं बनीं", auto_date
        all_staff = []
        for img_b64 in images_b64[:3]:
            prompt_text = f"""यह {shift_name} duty roster की scanned image है। सभी कर्मचारियों की जानकारी निकालो।
JSON format में return करो ONLY:
{{"staff": [{{"Mobile_No":"10 digit","Employee_Name":"नाम","Designation":"पद"}}]}}"""
            raw, _, err = ai_call_with_image([{"role":"user","content":[
                {"type":"image_url","image_url":{"url":f"data:image/png;base64,{img_b64}"}},
                {"type":"text","text":prompt_text}]}], max_tokens=4000)
            if raw:
                data, _ = safe_json_parse(raw)
                if data:
                    all_staff.extend(data.get("staff",[]))
        seen, unique = set(), []
        for s in all_staff:
            key = str(s.get("Mobile_No","")) + str(s.get("Employee_Name",""))
            if key not in seen:
                seen.add(key)
                unique.append(s)
        return unique, None, auto_date

def smart_detect_remarks(staff_entry):
    KEYWORDS = ["CHO","Shift Incharge","Shift In-charge","Incharge","Inspector","SI","ASI","HC",
                "Constable","Head Constable","Sub Inspector","CFMC","Deputation","इन्चार्ज","प्रभारी"]
    all_text = " ".join(str(v) for v in staff_entry.values())
    for kw in KEYWORDS:
        if kw.lower() in all_text.lower():
            return kw
    return ""

# ══════════════════════════════════════════════════════════════════════════════
#  SHEET WRITERS
# ══════════════════════════════════════════════════════════════════════════════
def update_shift_sheet(shift_name, staff_list, date_str):
    client = get_client()
    sh     = client.open_by_key(SHEET_ID)

    ws_master      = sh.worksheet("Master_Data")
    all_master_vals= ws_master.get_all_values()
    if not all_master_vals:
        ws_master.append_row(["Sr_No","Mobile_No","Designation","Name","Remarks"])
        all_master_vals = [["Sr_No","Mobile_No","Designation","Name","Remarks"]]
    header = all_master_vals[0]

    idx_mob   = col_idx_from_header(header, MOBILE_ALIASES)
    idx_desig = col_idx_from_header(header, DESIG_ALIASES)
    idx_name  = col_idx_from_header(header, NAME_ALIASES)
    idx_srno  = col_idx_from_header(header, ["Sr_No","sr_no","srno"])
    idx_rem   = col_idx_from_header(header, REMARKS_ALIASES)

    if idx_mob is None:
        ws_master.clear()
        ws_master.append_row(["Sr_No","Mobile_No","Designation","Name","Remarks"])
        all_master_vals = [["Sr_No","Mobile_No","Designation","Name","Remarks"]]
        header = all_master_vals[0]
        idx_srno,idx_mob,idx_desig,idx_name,idx_rem = 0,1,2,3,4

    master_mobile_map, mobile_to_row = {}, {}
    for row_i, row in enumerate(all_master_vals[1:], start=2):
        if idx_mob is not None and idx_mob < len(row):
            m = str(row[idx_mob]).strip()
            if m:
                mobile_to_row[m] = row_i
                if idx_name is not None and idx_name < len(row):
                    n = str(row[idx_name]).strip()
                    if n:
                        master_mobile_map[m] = n

    # Write shift sheet
    ws_shift = sh.worksheet(shift_name)
    ws_shift.clear()
    shift_rows = [["Mobile_No","Employee_Name","Designation","Shift_Date"]]
    for s in staff_list:
        mob   = str(s.get("Mobile_No","")).strip()
        pname = str(s.get("Employee_Name","")).strip()
        desig = str(s.get("Designation","")).strip()
        fname = master_mobile_map.get(mob, pname)
        if fname:
            shift_rows.append([mob, fname, desig, date_str])
    gspread_append_rows(ws_shift, shift_rows)

    new_staff, audit_rows, new_master_rows = [], [], []
    next_sr = len(all_master_vals)

    for s in staff_list:
        mob   = str(s.get("Mobile_No","")).strip()
        pname = str(s.get("Employee_Name","")).strip()
        desig = str(s.get("Designation","")).strip()
        fname = master_mobile_map.get(mob, pname)
        if not fname:
            continue
        auto_remark = smart_detect_remarks(s)
        audit_rows.append([date_str, shift_name, mob, fname, desig, "Loaded",
                           auto_remark or "PDF से लोड"])
        if not mob or len(mob) != 10 or not mob.isdigit():
            continue
        if mob in mobile_to_row:
            row_num = mobile_to_row[mob]
            existing_row = all_master_vals[row_num - 1]
            old_desig = ""
            if idx_desig is not None and idx_desig < len(existing_row):
                old_desig = str(existing_row[idx_desig]).strip()
            if idx_desig is not None and desig and desig.upper() != old_desig.upper():
                ws_master.update_cell(row_num, idx_desig + 1, desig)
                audit_rows.append([date_str, shift_name, mob, fname, desig, "Designation_Updated",
                                   f"पुराना: {old_desig} → नया: {desig}"])
        else:
            new_row = [""] * max(5, len(header))
            if idx_srno  is not None: new_row[idx_srno]  = next_sr
            if idx_mob   is not None: new_row[idx_mob]   = mob
            if idx_desig is not None: new_row[idx_desig] = desig
            if idx_name  is not None: new_row[idx_name]  = fname
            if idx_rem   is not None: new_row[idx_rem]   = auto_remark
            new_master_rows.append(new_row)
            mobile_to_row[mob] = len(all_master_vals) + len(new_master_rows)
            all_master_vals.append(new_row)
            master_mobile_map[mob] = fname
            next_sr += 1
            new_staff.append({"Mobile_No":mob,"Employee_Name":fname,"Designation":desig,"Remarks":auto_remark})

    if new_master_rows:
        gspread_append_rows(ws_master, new_master_rows)
    ws_audit = get_or_create_worksheet(sh, "Audit_Log")
    if audit_rows:
        gspread_append_rows(ws_audit, audit_rows)
    load_all_data.clear()
    return new_staff


def load_historical_pdf(shift_name, staff_list, date_str):
    client = get_client()
    sh     = client.open_by_key(SHEET_ID)
    ws_audit = get_or_create_worksheet(sh, "Audit_Log")
    ws_master = sh.worksheet("Master_Data")
    all_master_vals = ws_master.get_all_values()
    if not all_master_vals:
        ws_master.append_row(["Sr_No","Mobile_No","Designation","Name","Remarks"])
        all_master_vals = [["Sr_No","Mobile_No","Designation","Name","Remarks"]]
    header = all_master_vals[0]
    idx_mob  = col_idx_from_header(header, MOBILE_ALIASES)
    idx_desig= col_idx_from_header(header, DESIG_ALIASES)
    idx_name = col_idx_from_header(header, NAME_ALIASES)
    idx_srno = col_idx_from_header(header, ["Sr_No","sr_no","srno"])
    idx_rem  = col_idx_from_header(header, REMARKS_ALIASES)
    if idx_mob is None:
        ws_master.clear()
        ws_master.append_row(["Sr_No","Mobile_No","Designation","Name","Remarks"])
        all_master_vals = [["Sr_No","Mobile_No","Designation","Name","Remarks"]]
        header = all_master_vals[0]
        idx_srno,idx_mob,idx_desig,idx_name,idx_rem = 0,1,2,3,4

    existing_mobiles, master_mobile_map = set(), {}
    for row in all_master_vals[1:]:
        if idx_mob is not None and idx_mob < len(row):
            m = str(row[idx_mob]).strip()
            if m:
                existing_mobiles.add(m)
                if idx_name is not None and idx_name < len(row):
                    n = str(row[idx_name]).strip()
                    if n: master_mobile_map[m] = n

    next_sr = len(all_master_vals)
    audit_rows, new_staff, new_master_rows = [], [], []

    for s in staff_list:
        mob   = str(s.get("Mobile_No","")).strip()
        pname = str(s.get("Employee_Name","")).strip()
        desig = str(s.get("Designation","")).strip()
        fname = master_mobile_map.get(mob, pname)
        if not fname:
            continue
        auto_remark = smart_detect_remarks(s)
        if mob and len(mob)==10 and mob.isdigit() and mob not in existing_mobiles:
            new_row = [""]*max(5,len(header))
            if idx_srno  is not None: new_row[idx_srno]  = next_sr
            if idx_mob   is not None: new_row[idx_mob]   = mob
            if idx_desig is not None: new_row[idx_desig] = desig
            if idx_name  is not None: new_row[idx_name]  = fname
            if idx_rem   is not None: new_row[idx_rem]   = auto_remark
            new_master_rows.append(new_row)
            existing_mobiles.add(mob)
            master_mobile_map[mob] = fname
            all_master_vals.append(new_row)
            next_sr += 1
            new_staff.append({"Mobile_No":mob,"Employee_Name":fname,"Designation":desig,"Remarks":auto_remark})
            audit_rows.append([date_str, shift_name, mob, fname, desig, "Historical",
                               auto_remark or "पुराना record — नया कर्मचारी Master में जोड़ा"])
        else:
            audit_rows.append([date_str, shift_name, mob, fname, desig, "Historical",
                               auto_remark or "पुराना record"])

    if new_master_rows:
        gspread_append_rows(ws_master, new_master_rows)
    if audit_rows:
        gspread_append_rows(ws_audit, audit_rows)
    load_all_data.clear()
    return len(audit_rows), new_staff


def bulk_historical_import_from_sheet(source_sheet_id, date_from, date_to, progress_cb=None):
    client  = get_client()
    sh_dest = client.open_by_key(SHEET_ID)
    try:
        sh_src = client.open_by_key(source_sheet_id)
        try:
            ws_src = sh_src.worksheet("Audit_Log")
        except:
            ws_src = sh_src.get_worksheet(0)
        src_records = ws_src.get_all_records()
    except Exception as e:
        return {"error": f"Source sheet नहीं खुली: {e}"}
    if not src_records:
        return {"error": "Source sheet खाली है"}

    sample    = src_records[0]
    col_date  = find_col(sample, ["Date","date","तारीख","दिनांक"])
    col_shift = find_col(sample, ["Shift","shift","शिफ्ट"])
    col_mob   = find_col(sample, MOBILE_ALIASES)
    col_name  = find_col(sample, NAME_ALIASES)
    col_desig = find_col(sample, DESIG_ALIASES)
    if not col_name:
        return {"error": "Name column नहीं मिला। Columns: " + str(list(sample.keys()))}

    try:
        d_from = datetime.strptime(date_from,"%d-%m-%Y").date()
        d_to   = datetime.strptime(date_to,  "%d-%m-%Y").date()
    except:
        return {"error": "तारीख format गलत — DD-MM-YYYY"}

    def parse_date_flex(s):
        for fmt in ["%d-%m-%Y","%d/%m/%Y","%Y-%m-%d","%d-%b-%Y"]:
            try:
                return datetime.strptime(str(s).strip(), fmt).date()
            except:
                pass
        return None

    ws_audit = get_or_create_worksheet(sh_dest, "Audit_Log")
    existing_audit_raw  = ws_audit.get_all_values()
    existing_audit_keys = set()
    if len(existing_audit_raw) > 1:
        ah = existing_audit_raw[0]
        ai_date  = next((i for i,h in enumerate(ah) if "date"  in h.lower()), 0)
        ai_shift = next((i for i,h in enumerate(ah) if "shift" in h.lower()), 1)
        ai_mob   = next((i for i,h in enumerate(ah) if "mobile" in h.lower()), 2)
        for row in existing_audit_raw[1:]:
            if len(row) > ai_mob:
                key = f"{str(row[ai_date]).strip()}|{str(row[ai_shift]).strip()}|{str(row[ai_mob]).strip()}"
                existing_audit_keys.add(key)

    ws_master  = sh_dest.worksheet("Master_Data")
    all_master = ws_master.get_all_values()
    if not all_master:
        ws_master.append_row(["Sr_No","Mobile_No","Designation","Name","Remarks"])
        all_master = [["Sr_No","Mobile_No","Designation","Name","Remarks"]]
    mh = all_master[0]
    mi_mob  = col_idx_from_header(mh, MOBILE_ALIASES)
    mi_desig= col_idx_from_header(mh, DESIG_ALIASES)
    mi_name = col_idx_from_header(mh, NAME_ALIASES)
    mi_srno = col_idx_from_header(mh, ["Sr_No","sr_no"])
    mi_rem  = col_idx_from_header(mh, REMARKS_ALIASES)
    if mi_mob is None:
        ws_master.clear()
        ws_master.append_row(["Sr_No","Mobile_No","Designation","Name","Remarks"])
        all_master = [["Sr_No","Mobile_No","Designation","Name","Remarks"]]
        mh = all_master[0]
        mi_srno,mi_mob,mi_desig,mi_name,mi_rem = 0,1,2,3,4

    existing_mobiles = {str(row[mi_mob]).strip() for row in all_master[1:]
                        if mi_mob is not None and mi_mob < len(row) and row[mi_mob]}
    next_sr = len(all_master)

    new_audit_rows, new_master_info = [], []
    added_master, added_audit, skipped_dup, total_processed = 0,0,0,0

    for idx, rec in enumerate(src_records):
        if progress_cb and idx % 50 == 0:
            progress_cb(idx, len(src_records))
        date_val  = str(rec.get(col_date, "")).strip()  if col_date  else ""
        shift_val = str(rec.get(col_shift,"")).strip()  if col_shift else "Unknown"
        mob_val   = str(rec.get(col_mob,  "")).strip()  if col_mob   else ""
        name_val  = str(rec.get(col_name, "")).strip()
        desig_val = str(rec.get(col_desig,"")).strip()  if col_desig else ""
        if not name_val:
            continue
        if date_val:
            rec_date = parse_date_flex(date_val)
            if rec_date is None or not (d_from <= rec_date <= d_to):
                continue
            formatted_date = rec_date.strftime("%d-%m-%Y")
        else:
            formatted_date = ""
        total_processed += 1
        shift_clean = shift_val if shift_val in SHIFT_NAMES else (shift_val or "Historical")
        audit_key   = f"{formatted_date}|{shift_clean}|{mob_val}"
        if audit_key in existing_audit_keys:
            skipped_dup += 1
            continue
        note = "पुराना record"
        if mob_val and len(mob_val)==10 and mob_val.isdigit() and mob_val not in existing_mobiles:
            new_row = [""]*max(5,len(mh))
            if mi_srno  is not None: new_row[mi_srno]  = next_sr
            if mi_mob   is not None: new_row[mi_mob]   = mob_val
            if mi_desig is not None: new_row[mi_desig] = desig_val
            if mi_name  is not None: new_row[mi_name]  = name_val
            if mi_rem   is not None: new_row[mi_rem]   = ""
            ws_master.append_row(new_row)
            existing_mobiles.add(mob_val)
            all_master.append(new_row)
            next_sr += 1
            added_master += 1
            new_master_info.append({"Mobile_No":mob_val,"Employee_Name":name_val,"Designation":desig_val})
            note = "Bulk Import — Master में जोड़ा"
        new_audit_rows.append([formatted_date, shift_clean, mob_val, name_val, desig_val, "Historical", note])
        existing_audit_keys.add(audit_key)
        added_audit += 1

    for i in range(0, len(new_audit_rows), 50):
        gspread_append_rows(ws_audit, new_audit_rows[i:i+50])
    load_all_data.clear()
    return {"total_src":len(src_records),"total_processed":total_processed,
            "added_audit":added_audit,"added_master":added_master,
            "skipped_dup":skipped_dup,"new_employees":new_master_info}


def add_leave(mob, name, desig, leave_from, leave_to, reason, sd_days):
    client = get_client()
    sh = client.open_by_key(SHEET_ID)
    ws = get_or_create_worksheet(sh, "Avkaash")
    today = now_ist().date()
    try:
        from_d = datetime.strptime(leave_from,"%d-%m-%Y").date()
        to_d   = datetime.strptime(leave_to,  "%d-%m-%Y").date()
        status = "Active" if from_d <= today <= to_d else ("Upcoming" if today < from_d else "Expired")
    except:
        status = "Active"
    ws.append_row([mob, desig, name, leave_from, leave_to, reason, sd_days, status])
    load_all_data.clear()

def add_employee_manual(mob, name, desig, remarks=""):
    client = get_client()
    sh = client.open_by_key(SHEET_ID)
    ws = sh.worksheet("Master_Data")
    sr_no = len(ws.get_all_values())
    ws.append_row([sr_no, mob, desig, name, remarks])
    load_all_data.clear()

# ══════════════════════════════════════════════════════════════════════════════
#  AI HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def ai_pattern_analysis(audit_df):
    if audit_df.empty:
        return "डेटा उपलब्ध नहीं है।"
    name_col  = find_col(audit_df.columns.tolist(), NAME_ALIASES)
    shift_col = find_col(audit_df.columns.tolist(), ["Shift","shift"])
    if name_col and shift_col:
        summary = audit_df.groupby([name_col, shift_col]).size().reset_index(name="count").head(50).to_string(index=False)
    else:
        summary = "Data available but columns missing"
    prompt = f"""यह पुलिस duty roster का audit data है।
{summary}
Hindi में बताओ:
1. किस कर्मचारी की कितनी duty किस shift में लगी
2. कोई shift bias है?
3. Fair rotation है या नहीं?
4. अगली duty के सुझाव?"""
    text, model_used, err = ai_call([{"role":"user","content":prompt}], max_tokens=800, temperature=0.3)
    if err:
        return f"AI Error: {err}"
    return f"_{model_used} द्वारा विश्लेषण_\n\n{text}"

def ai_virtual_duty_suggest(audit_df, master_df):
    name_col = find_col(master_df.columns.tolist(), NAME_ALIASES)
    staff_list = master_df[name_col].dropna().astype(str).tolist()[:20] if name_col and not master_df.empty else []
    emp_col   = find_col(audit_df.columns.tolist(), NAME_ALIASES)
    shift_col = find_col(audit_df.columns.tolist(), ["Shift","shift"])
    recent = audit_df.tail(30).to_string(index=False) if emp_col and shift_col else "No recent data"
    prompt = f"""Based on duty history, suggest virtual duty for next rotation.
Recent history: {recent}
Available staff: {', '.join(staff_list)}
Output in Hindi — who should go in Shift1/Shift2/Shift3.
Format:
🟡 Shift1: [names]
🟢 Shift2: [names]
🔵 Shift3: [names]"""
    text, model_used, err = ai_call([{"role":"user","content":prompt}], max_tokens=500, temperature=0.4)
    if err:
        return f"AI Error: {err}"
    return f"_{model_used} द्वारा सुझाव_\n\n{text}"

# ══════════════════════════════════════════════════════════════════════════════
#  EMPLOYEE SEARCH  — Audit_Log ही primary source है
# ══════════════════════════════════════════════════════════════════════════════
def ai_employee_search(mob, master_df, shift_dfs, audit_df, avkaash_df):
    mob = str(mob).strip()

    def clean_mob(x):
        s = str(x).strip()
        return s[:-2] if s.endswith('.0') else s

    # ── Step-1: Audit_Log से कर्मचारी का सारा data ──────────────────────────
    mob_col_audit = find_col(audit_df.columns.tolist(), MOBILE_ALIASES)
    emp_audit     = pd.DataFrame()
    if mob_col_audit and not audit_df.empty:
        emp_audit = audit_df[audit_df[mob_col_audit].apply(clean_mob) == mob].copy()

    # अगर Audit में बिल्कुल भी नहीं मिला तो Master Data check करो
    if emp_audit.empty:
        mob_col_m = find_col(master_df.columns.tolist(), MOBILE_ALIASES)
        if mob_col_m and not master_df.empty:
            res_m = master_df[master_df[mob_col_m].apply(clean_mob) == mob]
            if not res_m.empty:
                r       = res_m.iloc[0]
                name_c  = find_col(r.index.tolist(), NAME_ALIASES)
                desig_c = find_col(r.index.tolist(), DESIG_ALIASES)
                rem_c   = find_col(r.index.tolist(), REMARKS_ALIASES)
                return {
                    "name"       : str(r[name_c]).strip()  if name_c  else "—",
                    "designation": str(r[desig_c]).strip() if desig_c else "—",
                    "mobile"     : mob,
                    "remarks"    : str(r[rem_c]).strip()   if rem_c   else "",
                    "current_shift": "—",
                    "shift_totals" : {},
                    "total_duty"   : 0,
                    "history"      : [],
                    "leaves"       : [],
                    "total_leaves" : 0,
                }, None
        return None, "कर्मचारी नहीं मिला"

    # ── Step-2: Audit_Log से ही नाम / पद निकालो ────────────────────────────
    name_c_a  = find_col(emp_audit.columns.tolist(), NAME_ALIASES)
    desig_c_a = find_col(emp_audit.columns.tolist(), DESIG_ALIASES)
    date_c_a  = find_col(emp_audit.columns.tolist(), ["Date","date"])
    shift_c_a = find_col(emp_audit.columns.tolist(), ["Shift","shift"])

    name  = "—"
    desig = "—"
    if name_c_a:
        names = emp_audit[name_c_a].dropna().astype(str).str.strip()
        names = names[names != ""]
        if not names.empty:
            name = names.iloc[-1]
    if desig_c_a:
        desigs = emp_audit[desig_c_a].dropna().astype(str).str.strip()
        desigs = desigs[desigs != ""]
        if not desigs.empty:
            desig = desigs.iloc[-1]

    # Master_Data से remarks लेने की कोशिश
    remarks = ""
    mob_col_m = find_col(master_df.columns.tolist(), MOBILE_ALIASES)
    if mob_col_m and not master_df.empty:
        res_m = master_df[master_df[mob_col_m].apply(clean_mob) == mob]
        if not res_m.empty:
            rem_c = find_col(res_m.columns.tolist(), REMARKS_ALIASES)
            if rem_c:
                remarks = str(res_m.iloc[0][rem_c]).strip()
            # Master से बेहतर नाम/पद मिले तो ले लो
            nc2 = find_col(res_m.columns.tolist(), NAME_ALIASES)
            dc2 = find_col(res_m.columns.tolist(), DESIG_ALIASES)
            if nc2 and str(res_m.iloc[0][nc2]).strip():
                name = str(res_m.iloc[0][nc2]).strip()
            if dc2 and str(res_m.iloc[0][dc2]).strip():
                desig = str(res_m.iloc[0][dc2]).strip()

    # ── Step-3: Current shift (latest entry से) ──────────────────────────────
    current_shift = "—"
    if shift_c_a and date_c_a:
        try:
            tmp      = emp_audit.copy()
            tmp["_d"] = pd.to_datetime(tmp[date_c_a], dayfirst=True, errors="coerce")
            latest   = tmp.sort_values("_d", ascending=False).iloc[0]
            current_shift = str(latest[shift_c_a]).strip() or "—"
        except:
            current_shift = str(emp_audit.iloc[-1][shift_c_a]).strip() or "—"
    elif shift_c_a:
        current_shift = str(emp_audit.iloc[-1][shift_c_a]).strip() or "—"

    # ── Step-4: Per-Shift duty count (unique dates × shift) ─────────────────
    shift_totals = {}
    total_duty   = 0
    if shift_c_a:
        # हर shift में unique dates count करो
        for sh_name in SHIFT_NAMES:
            sh_rows = emp_audit[emp_audit[shift_c_a].astype(str).str.strip() == sh_name]
            if date_c_a:
                unique_days = sh_rows[date_c_a].astype(str).str.strip()
                unique_days = unique_days[unique_days != ""].nunique()
            else:
                unique_days = len(sh_rows)
            if unique_days > 0:
                shift_totals[sh_name] = unique_days
                total_duty += unique_days
    if total_duty == 0:
        # Fallback: सिर्फ rows count
        total_duty = len(emp_audit)

    # ── Step-5: Duty history (latest 25 entries) ─────────────────────────────
    history = []
    if date_c_a:
        try:
            tmp2      = emp_audit.copy()
            tmp2["_d"] = pd.to_datetime(tmp2[date_c_a], dayfirst=True, errors="coerce")
            tmp2      = tmp2.sort_values("_d", ascending=False)
        except:
            tmp2 = emp_audit
    else:
        tmp2 = emp_audit

    cols_avail = [c for c in [date_c_a, shift_c_a, desig_c_a,
                               find_col(emp_audit.columns.tolist(), ["Remarks","remarks"])]
                  if c]
    if cols_avail:
        history = tmp2[cols_avail].head(25).values.tolist()

    # ── Step-6: Avkaash (अवकाश) data ─────────────────────────────────────────
    leaves       = []
    total_leaves = 0
    mob_col_av   = find_col(avkaash_df.columns.tolist(), MOBILE_ALIASES)
    if mob_col_av and not avkaash_df.empty:
        emp_leave = avkaash_df[avkaash_df[mob_col_av].apply(clean_mob) == mob]
        if not emp_leave.empty:
            leave_cols = [c for c in ["Leave_From","Leave_To","Leave_Reason","Sd_Days","Status"]
                          if c in emp_leave.columns]
            leaves = emp_leave[leave_cols].values.tolist()
            # Total leave days
            sd_col = "Sd_Days"
            if sd_col in emp_leave.columns:
                try:
                    total_leaves = int(emp_leave[sd_col].fillna(0).astype(float).sum())
                except:
                    total_leaves = len(emp_leave)
            else:
                # Leave_From → Leave_To से calculate करो
                for _, lrow in emp_leave.iterrows():
                    try:
                        lf = pd.to_datetime(str(lrow.get("Leave_From","")), dayfirst=True)
                        lt = pd.to_datetime(str(lrow.get("Leave_To","")),   dayfirst=True)
                        total_leaves += max(1, (lt - lf).days + 1)
                    except:
                        total_leaves += 1

    return {
        "name"         : name,
        "designation"  : desig,
        "mobile"       : mob,
        "remarks"      : remarks,
        "current_shift": current_shift,
        "shift_totals" : shift_totals,   # {"Shift1":20, "Shift2":5, ...}
        "total_duty"   : total_duty,
        "history"      : history,
        "leaves"       : leaves,
        "total_leaves" : total_leaves,
    }, None


# ══════════════════════════════════════════════════════════════════════════════
#  RENDER EMPLOYEE CARD — Audit_Log based, shift-wise totals + leave summary
# ══════════════════════════════════════════════════════════════════════════════
def render_employee_card(emp_data, active_leave_mobs):
    mob           = str(emp_data.get("mobile",""))
    name          = _html.escape(str(emp_data.get("name","—")))
    desig         = _html.escape(str(emp_data.get("designation","—")))
    remarks       = _html.escape(str(emp_data.get("remarks","")))
    current_shift = str(emp_data.get("current_shift","—"))
    shift_totals  = emp_data.get("shift_totals", {})
    total_duty    = emp_data.get("total_duty", 0)
    total_leaves  = emp_data.get("total_leaves", 0)

    # ── Status & colors ──────────────────────────────────────────────────────
    if mob in active_leave_mobs:
        status_text  = "🌴 अवकाश पर"
        status_color = "#f97316"
        glow_color   = "rgba(249,115,22,0.15)"
        border_color = "rgba(249,115,22,0.4)"
    elif current_shift and current_shift != "—":
        _s = current_shift.lower()
        if "1" in _s:
            emoji, clr = "🟡", "#ffd700"
            glow_color, border_color = "rgba(255,215,0,0.15)", "rgba(255,215,0,0.4)"
        elif "3" in _s:
            emoji, clr = "🔵", "#60a5fa"
            glow_color, border_color = "rgba(96,165,250,0.15)", "rgba(96,165,250,0.4)"
        else:
            emoji, clr = "🟢", "#22c55e"
            glow_color, border_color = "rgba(34,197,94,0.15)", "rgba(34,197,94,0.4)"
        status_text  = f"{emoji} {_html.escape(current_shift)}"
        status_color = clr
    else:
        status_text  = "⏳ Unassigned"
        status_color = "#a855f7"
        glow_color   = "rgba(168,85,247,0.15)"
        border_color = "rgba(168,85,247,0.4)"

    remarks_badge = ""
    if remarks:
        remarks_badge = (
            f'<div style="margin-top:6px;">'
            f'<span style="background:rgba(255,215,0,0.15);border:1px solid rgba(255,215,0,0.4);'
            f'border-radius:20px;padding:3px 12px;font-size:0.78rem;color:#ffd700;font-weight:700;">'
            f'📌 {remarks}</span></div>'
        )

    # ── 1. Top card (नाम / पद / मोबाइल / status) ─────────────────────────────
    st.markdown(f"""
<div style="background:linear-gradient(135deg,rgba(13,27,62,0.97),rgba(26,45,90,0.82));
    border:1px solid {border_color};border-left:5px solid {status_color};border-radius:20px;
    padding:28px 32px;margin-top:16px;box-shadow:0 8px 40px {glow_color};">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;">
        <div>
            <div style="font-size:1.6rem;font-weight:800;color:#e8f0ff;margin-bottom:6px;font-family:'Rajdhani',sans-serif;">
                👤 {name}
            </div>
            <div style="font-size:0.85rem;color:#7a92b8;margin-bottom:3px;">
                🏷️ <span style="color:#a0b8d8;">{desig}</span>
            </div>
            <div style="font-size:0.85rem;color:#7a92b8;">
                📱 <span style="color:#a0b8d8;font-family:'Space Mono',monospace;">{_html.escape(mob)}</span>
            </div>
            {remarks_badge}
        </div>
        <div style="background:rgba(0,0,0,0.4);border:1px solid {border_color};
            border-radius:16px;padding:16px 28px;text-align:center;min-width:140px;">
            <div style="font-size:0.7rem;color:#7a92b8;margin-bottom:4px;letter-spacing:1px;text-transform:uppercase;">अंतिम शिफ्ट</div>
            <div style="font-size:1.05rem;font-weight:700;color:{status_color};">{status_text}</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

    # ── 2. Shift-wise Duty Totals (बड़े metric cards) ─────────────────────────
    SHIFT_CFG = {
        "Shift1": ("🟡", "#ffd700", "rgba(255,215,0,0.15)", "rgba(255,215,0,0.35)"),
        "Shift2": ("🟢", "#4ade80", "rgba(34,197,94,0.15)",  "rgba(34,197,94,0.35)"),
        "Shift3": ("🔵", "#60a5fa", "rgba(96,165,250,0.15)", "rgba(96,165,250,0.35)"),
    }

    cards_html = ""
    for sh, (em, clr, bg, brd) in SHIFT_CFG.items():
        cnt = shift_totals.get(sh, 0)
        cards_html += f"""
<div style="flex:1;min-width:120px;background:{bg};border:1px solid {brd};
    border-radius:16px;padding:18px 12px;text-align:center;">
    <div style="font-size:1.3rem;margin-bottom:4px;">{em}</div>
    <div style="font-family:'Rajdhani',monospace;font-size:2.4rem;font-weight:700;
        color:{clr};line-height:1;">{cnt}</div>
    <div style="font-size:0.72rem;color:#7a92b8;margin-top:4px;font-weight:600;">{sh} — दिन</div>
</div>"""

    # कुल + अवकाश
    cards_html += f"""
<div style="flex:1;min-width:120px;background:rgba(168,85,247,0.12);border:1px solid rgba(168,85,247,0.35);
    border-radius:16px;padding:18px 12px;text-align:center;">
    <div style="font-size:1.3rem;margin-bottom:4px;">📊</div>
    <div style="font-family:'Rajdhani',monospace;font-size:2.4rem;font-weight:700;
        color:#c084fc;line-height:1;">{total_duty}</div>
    <div style="font-size:0.72rem;color:#7a92b8;margin-top:4px;font-weight:600;">कुल ड्यूटी दिन</div>
</div>
<div style="flex:1;min-width:120px;background:rgba(249,115,22,0.10);border:1px solid rgba(249,115,22,0.35);
    border-radius:16px;padding:18px 12px;text-align:center;">
    <div style="font-size:1.3rem;margin-bottom:4px;">🌴</div>
    <div style="font-family:'Rajdhani',monospace;font-size:2.4rem;font-weight:700;
        color:#fb923c;line-height:1;">{total_leaves}</div>
    <div style="font-size:0.72rem;color:#7a92b8;margin-top:4px;font-weight:600;">कुल अवकाश दिन</div>
</div>"""

    st.markdown(f"""
<div style="background:rgba(0,0,0,0.2);border:1px solid rgba(255,255,255,0.07);
    border-radius:16px;padding:20px;margin-top:12px;">
    <div style="font-size:0.78rem;color:#7a92b8;margin-bottom:14px;font-weight:700;letter-spacing:1px;
        text-transform:uppercase;">📈 शिफ्ट-वार ड्यूटी सारांश (Audit Log आधारित)</div>
    <div style="display:flex;gap:12px;flex-wrap:wrap;">{cards_html}</div>
</div>
""", unsafe_allow_html=True)

    # ── 3. Duty history table (latest 25, newest first) ───────────────────────
    history = emp_data.get("history", [])
    if history:
        rows_html = ""
        SHIFT_COLORS = {"shift1":"#ffd700","shift2":"#4ade80","shift3":"#60a5fa"}
        for h in history:
            c0 = _html.escape(str(h[0])) if len(h) > 0 else ""
            c1_raw = str(h[1]) if len(h) > 1 else ""
            c1 = _html.escape(c1_raw)
            c2 = _html.escape(str(h[2])) if len(h) > 2 else ""
            c3 = _html.escape(str(h[3])) if len(h) > 3 else ""
            sc = SHIFT_COLORS.get(c1_raw.lower().replace(" ",""), "#a0b8d8")
            rows_html += (
                f"<tr style='border-bottom:1px solid rgba(255,255,255,0.04)'>"
                f"<td style='padding:5px 10px;color:#a0b8d8;white-space:nowrap'>{c0}</td>"
                f"<td style='padding:5px 10px;'><span style='background:rgba(0,0,0,0.3);"
                f"border-radius:6px;padding:2px 10px;color:{sc};font-weight:700;font-size:0.8rem'>{c1}</span></td>"
                f"<td style='padding:5px 10px;color:#4ade80;font-size:0.8rem'>{c2}</td>"
                f"<td style='padding:5px 10px;color:#fbbf24;font-size:0.75rem'>{c3}</td>"
                f"</tr>"
            )
        st.markdown(f"""
<div style="background:rgba(0,0,0,0.2);border:1px solid rgba(255,255,255,0.07);
    border-radius:14px;padding:16px;margin-top:12px;">
    <div style="font-size:0.78rem;color:#7a92b8;margin-bottom:10px;font-weight:700;letter-spacing:1px;
        text-transform:uppercase;">📅 ड्यूटी इतिहास — Audit Log (नवीनतम {len(history)} रिकॉर्ड)</div>
    <div style="overflow-x:auto;">
    <table style="width:100%;border-collapse:collapse;font-size:0.82rem;">
        <thead><tr style="background:rgba(255,255,255,0.06)">
            <th style="padding:6px 10px;text-align:left;color:#7a92b8;font-weight:700">📅 तारीख</th>
            <th style="padding:6px 10px;text-align:left;color:#7a92b8;font-weight:700">🔄 शिफ्ट</th>
            <th style="padding:6px 10px;text-align:left;color:#7a92b8;font-weight:700">🏷️ पद</th>
            <th style="padding:6px 10px;text-align:left;color:#7a92b8;font-weight:700">📌 Remarks</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
    </table>
    </div>
</div>
""", unsafe_allow_html=True)
    else:
        st.markdown("""
<div style="background:rgba(0,0,0,0.15);border:1px solid rgba(255,255,255,0.06);
    border-radius:12px;padding:14px 18px;margin-top:12px;color:#7a92b8;font-size:0.85rem;">
    📋 Audit Log में अभी कोई ड्यूटी रिकॉर्ड नहीं मिला।
</div>""", unsafe_allow_html=True)

    # ── 4. Leave history (date-wise, with days) ───────────────────────────────
    leaves = emp_data.get("leaves", [])
    if leaves:
        leave_rows_html = ""
        for lv in leaves:
            # Expected cols: Leave_From, Leave_To, Leave_Reason, Sd_Days, Status
            l_from   = _html.escape(str(lv[0])) if len(lv) > 0 else "—"
            l_to     = _html.escape(str(lv[1])) if len(lv) > 1 else "—"
            l_reason = _html.escape(str(lv[2])) if len(lv) > 2 else "—"
            l_sd     = str(lv[3]) if len(lv) > 3 else "—"
            l_status = _html.escape(str(lv[4])) if len(lv) > 4 else ""

            # SD days badge
            try:
                sd_val = int(float(l_sd))
                sd_badge = (f'<span style="background:rgba(249,115,22,0.2);border:1px solid rgba(249,115,22,0.5);'
                            f'border-radius:12px;padding:2px 10px;color:#fb923c;font-weight:700;font-size:0.8rem;">'
                            f'📅 {sd_val} दिन</span>')
            except:
                sd_badge = ""

            # Status badge
            status_clr = {"Active":"#4ade80","Upcoming":"#ffd700","Expired":"#94a3b8"}.get(l_status,"#a0b8d8")
            status_badge = (f'<span style="background:rgba(0,0,0,0.3);border-radius:8px;padding:2px 8px;'
                            f'color:{status_clr};font-size:0.75rem;font-weight:600;">{l_status}</span>'
                            if l_status else "")

            leave_rows_html += f"""
<div style="display:flex;align-items:center;gap:12px;padding:8px 0;
    border-bottom:1px solid rgba(255,255,255,0.05);flex-wrap:wrap;">
    <span style="color:#fb923c;font-weight:700;font-size:0.85rem;white-space:nowrap;">
        {l_from} → {l_to}
    </span>
    {sd_badge}
    <span style="color:#a0b8d8;font-size:0.82rem;flex:1;min-width:100px;">{l_reason}</span>
    {status_badge}
</div>"""

        st.markdown(f"""
<div style="background:rgba(249,115,22,0.08);border:1px solid rgba(249,115,22,0.25);
    border-radius:14px;padding:16px 20px;margin-top:12px;">
    <div style="font-size:0.78rem;color:#7a92b8;margin-bottom:10px;font-weight:700;letter-spacing:1px;
        text-transform:uppercase;">🌴 अवकाश इतिहास — कुल {total_leaves} दिन ({len(leaves)} प्रविष्टियाँ)</div>
    {leave_rows_html}
</div>
""", unsafe_allow_html=True)
    else:
        st.markdown("""
<div style="background:rgba(0,0,0,0.12);border:1px solid rgba(255,255,255,0.05);
    border-radius:12px;padding:12px 18px;margin-top:12px;color:#7a92b8;font-size:0.82rem;">
    🌴 इस कर्मचारी का कोई अवकाश रिकॉर्ड नहीं मिला।
</div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITY
# ══════════════════════════════════════════════════════════════════════════════
def df_to_excel_bytes(df, sheet_name="Sheet1"):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()

def get_active_leave_mobiles(avkaash_df):
    today  = now_ist().date()
    active = set()
    if avkaash_df.empty:
        return active
    mob_col = find_col(avkaash_df.columns.tolist(), MOBILE_ALIASES)
    if not mob_col:
        return active
    for _, row in avkaash_df.iterrows():
        try:
            f = pd.to_datetime(row.get("Leave_From",""), dayfirst=True).date()
            t = pd.to_datetime(row.get("Leave_To",""),   dayfirst=True).date()
            if f <= today <= t:
                active.add(str(row.get(mob_col,"")).strip())
        except:
            pass
    return active

# ══════════════════════════════════════════════════════════════════════════════
#  SHIFT DISPLAY: सिर्फ TODAY का data, historical upload से affect नहीं होगा
# ══════════════════════════════════════════════════════════════════════════════
def get_today_shift(df, today_str):
    """
    STRICTLY सिर्फ आज की date का data return करो।
    अगर आज का data नहीं है तो empty DataFrame return करो।
    Historical upload से display cards affect नहीं होंगे।
    """
    if df.empty:
        return df
    date_col = find_col(df.columns.tolist(),
                        ["Shift_Date","shift_date","Date","date"])
    if not date_col:
        return df
    df = df.copy()
    df[date_col] = df[date_col].astype(str).str.strip()
    return df[df[date_col] == today_str]


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
        with st.spinner("Setup..."):
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
    st.caption(f"DeepSeek: {'✅' if DEEPSEEK_AVAILABLE else '❌'}")
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

today_str         = now_ist().strftime("%d-%m-%Y")
active_leave_mobs = get_active_leave_mobiles(avkaash_df)

# ── FIX: सिर्फ TODAY का data display cards के लिए ─────────────────────────
shift1_today = get_today_shift(shift_dfs.get("Shift1", pd.DataFrame()), today_str)
shift2_today = get_today_shift(shift_dfs.get("Shift2", pd.DataFrame()), today_str)
shift3_today = get_today_shift(shift_dfs.get("Shift3", pd.DataFrame()), today_str)

# ══════════════════════════════════════════════════════════════════════════════
#  METRIC CARDS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">📊 सारांश डैशबोर्ड</div>', unsafe_allow_html=True)

c1,c2,c3,c4,c5 = st.columns(5)
for col,icon,val,lbl,cls in [
    (c1,"👥",len(master_df),"कुल कर्मचारी","card-blue"),
    (c2,"🟡",len(shift1_today),"Shift 1 (आज)","card-gold"),
    (c3,"🟢",len(shift2_today),"Shift 2 (आज)","card-green"),
    (c4,"🔵",len(shift3_today),"Shift 3 (आज)","card-cyan"),
    (c5,"🌴",len(active_leave_mobs),"अवकाश पर","card-orange"),
]:
    with col:
        st.markdown(
            f'<div class="metric-card {cls}"><span class="icon">{icon}</span>'
            f'<div class="val">{val}</div><div class="lbl">{lbl}</div></div>',
            unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  NEW STAFF ALERTS
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.get("new_staff_alerts"):
    st.markdown('<div class="section-title">🔔 नए कर्मचारी जोड़े गए</div>', unsafe_allow_html=True)
    for ns in st.session_state["new_staff_alerts"]:
        sn  = _html.escape(str(ns.get('Employee_Name','')))
        sd  = _html.escape(str(ns.get('Designation','')))
        sm  = _html.escape(str(ns.get('Mobile_No','')))
        st.markdown(f"""
<div class="new-staff-alert">
    <span style="font-size:1.5rem;">⚠️</span>
    <span style="color:#ffd700;font-weight:700;">नया कर्मचारी: {sn} | {sd} | 📱 {sm}</span>
</div>""", unsafe_allow_html=True)
    if st.button("✅ Alerts dismiss करें"):
        st.session_state["new_staff_alerts"] = []
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
#  PDF UPLOAD SECTION
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">🤖 Agent PDF Upload — तीनों Shifts</div>', unsafe_allow_html=True)

pdf_date_input = st.date_input(
    "📅 तारीख (PDF से auto-detect होगी | यह fallback है)",
    value=now_ist().date(), key="pdf_date")
pdf_date_str = pdf_date_input.strftime("%d-%m-%Y")

is_historical = st.checkbox(
    "📚 Historical Mode (पुराना data — सिर्फ Audit_Log में जाएगा, Shift sheet नहीं बदलेगी)",
    value=False, key="historical_mode")

for sn in SHIFT_NAMES:
    if f"agent_result_{sn}" not in st.session_state:
        st.session_state[f"agent_result_{sn}"] = None
    if f"agent_file_{sn}" not in st.session_state:
        st.session_state[f"agent_file_{sn}"] = None

pu1, pu2, pu3 = st.columns(3)
upload_configs = [
    (pu1,"Shift1","🟡","sc-s1","s1"),
    (pu2,"Shift2","🟢","sc-s2","s2"),
    (pu3,"Shift3","🔵","sc-s3","s3"),
]

for col, shift_name, emoji, card_cls, badge_cls in upload_configs:
    with col:
        st.markdown(
            f'<div class="shift-card {card_cls}">'
            f'<span class="shift-badge {badge_cls}">{emoji} {shift_name}</span>'
            f'</div>', unsafe_allow_html=True)
        uploaded = st.file_uploader(
            f"{shift_name} PDF", type=["pdf"],
            key=f"upload_{shift_name}", label_visibility="collapsed")

        if uploaded is not None:
            if st.session_state[f"agent_result_{shift_name}"] is None or \
               st.session_state[f"agent_file_{shift_name}"] != uploaded.name:

                st.session_state[f"agent_file_{shift_name}"] = uploaded.name
                st.session_state[f"agent_result_{shift_name}"] = None
                pdf_bytes_agent = uploaded.read()

                with st.spinner(f"🤖 {shift_name} parse हो रहा है..."):
                    auto_date = extract_date_from_pdf_bytes(pdf_bytes_agent)
                    effective_date = (auto_date.strftime("%d-%m-%Y") if auto_date else pdf_date_str)
                    already_loaded, existing_count = check_shift_already_loaded(
                        audit_df, shift_name, effective_date)
                    staff_list, err, detected_date = parse_pdf_with_ai(
                        pdf_bytes_agent, shift_name, pdf_date_str)
                    final_date = (auto_date.strftime("%d-%m-%Y") if auto_date else
                                  detected_date if detected_date else pdf_date_str)
                    st.session_state[f"agent_result_{shift_name}"] = {
                        "staff_list":staff_list,"err":err,"final_date":final_date,
                        "already_loaded":already_loaded,"existing_count":existing_count,
                        "auto_date":auto_date}

        result = st.session_state.get(f"agent_result_{shift_name}")
        if result:
            staff_list     = result["staff_list"]
            err            = result["err"]
            final_date     = result["final_date"]
            already_loaded = result["already_loaded"]
            existing_count = result["existing_count"]
            auto_date      = result["auto_date"]

            if err:
                st.error(f"❌ {err}")
            elif not staff_list:
                st.warning("⚠️ कोई कर्मचारी नहीं मिला")
            else:
                desig_counts = {}
                for s in staff_list:
                    d = str(s.get("Designation","अज्ञात")).strip() or "अज्ञात"
                    desig_counts[d] = desig_counts.get(d,0) + 1
                desig_html = " &nbsp;|&nbsp; ".join(
                    f"<b>{_html.escape(d)}</b>: {c}" for d,c in desig_counts.items())
                date_src = "📄 PDF से" if auto_date else "📅 Manual"
                dup_html = (
                    f'<div style="color:#f97316;font-size:0.82rem;margin-top:6px;">'
                    f'⚠️ पहले से {existing_count} records हैं इस date पर!</div>'
                    if already_loaded else
                    '<div style="color:#4ade80;font-size:0.82rem;margin-top:6px;">✅ कोई duplicate नहीं</div>')

                st.markdown(f"""
<div style="background:rgba(30,50,90,0.7);border:1px solid rgba(96,165,250,0.3);
    border-radius:14px;padding:16px;margin-top:8px;">
    <div style="font-size:0.95rem;font-weight:700;color:#e8f0ff;margin-bottom:8px;">
        🤖 Agent Summary — {shift_name}
    </div>
    <div style="font-size:0.85rem;color:#a0b8d8;">
        👥 कुल: <b style="color:#60a5fa;">{len(staff_list)}</b>
        &nbsp;&nbsp;|&nbsp;&nbsp;
        📅 तारीख: <b style="color:#4ade80;">{final_date}</b>
        &nbsp;({date_src})
    </div>
    <div style="font-size:0.8rem;color:#7a92b8;margin-top:5px;">{desig_html}</div>
    {dup_html}
</div>""", unsafe_allow_html=True)

                can_save = True
                if already_loaded:
                    can_save = st.checkbox(
                        f"🔄 फिर भी save करें ({shift_name})",
                        key=f"force_{shift_name}", value=False)

                if st.button(f"💾 {shift_name} Save करें",
                             key=f"save_{shift_name}",
                             use_container_width=True,
                             disabled=not can_save):
                    with st.spinner(f"💾 {shift_name} save हो रहा है..."):
                        try:
                            if is_historical:
                                count, new_staff_hist = load_historical_pdf(
                                    shift_name, staff_list, final_date)
                                st.success(f"📚 {shift_name}: {count} records Audit_Log में | {final_date}")
                                if new_staff_hist:
                                    st.info(f"➕ {len(new_staff_hist)} नए कर्मचारी Master में")
                                    st.session_state.setdefault("new_staff_alerts",[])
                                    st.session_state["new_staff_alerts"].extend(new_staff_hist)
                            else:
                                new_staff = update_shift_sheet(shift_name, staff_list, final_date)
                                st.success(f"✅ {shift_name}: {len(staff_list)} कर्मचारी | {final_date}")
                                if new_staff:
                                    st.session_state.setdefault("new_staff_alerts",[])
                                    st.session_state["new_staff_alerts"].extend(new_staff)
                            st.session_state[f"agent_result_{shift_name}"] = None
                            st.session_state[f"agent_file_{shift_name}"] = None
                            st.rerun()
                        except Exception as save_err:
                            st.error(f"❌ Save error: {save_err}")

# ══════════════════════════════════════════════════════════════════════════════
#  CURRENT DUTY — सिर्फ TODAY
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(f'<div class="section-title">📋 वर्तमान ड्यूटी — {today_str}</div>', unsafe_allow_html=True)

duty_cols    = st.columns(3)
shift_styles = [
    ("🟡 Shift 1","sc-s1","s1","#ffd700"),
    ("🟢 Shift 2","sc-s2","s2","#4ade80"),
    ("🔵 Shift 3","sc-s3","s3","#60a5fa"),
]
today_shift_map = {
    "Shift1": shift1_today,
    "Shift2": shift2_today,
    "Shift3": shift3_today,
}

for idx, (s_label, card_cls, badge_cls, color) in enumerate(shift_styles):
    s_name = SHIFT_NAMES[idx]
    s_df   = today_shift_map[s_name]   # ← strictly today only
    with duty_cols[idx]:
        count = len(s_df)
        st.markdown(f"""
<div class="shift-card {card_cls}">
    <span class="shift-badge {badge_cls}">{s_label}</span>
    <div class="count">{count}</div>
    <div class="unit">कर्मचारी</div>
</div>""", unsafe_allow_html=True)
        if not s_df.empty:
            name_c  = find_col(s_df.columns.tolist(), NAME_ALIASES)
            desig_c = find_col(s_df.columns.tolist(), DESIG_ALIASES)
            mob_c   = find_col(s_df.columns.tolist(), MOBILE_ALIASES)
            disp_cols  = [c for c in [name_c, desig_c, mob_c] if c]
            rename_map = {}
            if name_c:  rename_map[name_c]  = "नाम"
            if desig_c: rename_map[desig_c] = "पद"
            if mob_c:   rename_map[mob_c]   = "मोबाइल"
            st.dataframe(s_df[disp_cols].rename(columns=rename_map),
                         use_container_width=True, hide_index=True, height=280)
            st.download_button(
                label=f"⬇️ {s_name} Excel",
                data=df_to_excel_bytes(s_df, s_name),
                file_name=f"{s_name}_{today_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True, key=f"dl_{s_name}")
        else:
            st.info(f"आज ({today_str}) का कोई data नहीं\nPDF upload करें ↑")

# ══════════════════════════════════════════════════════════════════════════════
#  TABS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🤖 AI Analysis","🔍 कर्मचारी खोज","👥 Master Data",
    "🌴 अवकाश","📜 Audit Log","➕ कर्मचारी जोड़ें","📂 Bulk Historical Import"])

# ── TAB 1: AI ─────────────────────────────────────────────────────────────────
with tab1:
    st.markdown('<div class="section-title">🤖 AI Duty Analysis</div>', unsafe_allow_html=True)
    ai_c1, ai_c2 = st.columns(2)
    with ai_c1:
        st.markdown('<div class="ai-card">', unsafe_allow_html=True)
        st.markdown("**📊 Pattern Analysis**")
        st.caption("पिछले duty patterns देखकर bias और fairness check")
        if st.button("🔍 Pattern Analyze करें", use_container_width=True, key="btn_pattern"):
            with st.spinner("AI analysis..."):
                st.session_state["pattern_result"] = ai_pattern_analysis(audit_df)
        if "pattern_result" in st.session_state:
            st.markdown(f'<div class="ai-response">{st.session_state["pattern_result"]}</div>',
                        unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with ai_c2:
        st.markdown('<div class="ai-card">', unsafe_allow_html=True)
        st.markdown("**🎯 Virtual Duty Suggestion**")
        st.caption("AI suggest करेगा — सिर्फ preview, sheet में नहीं जाएगा")
        if st.button("✨ Virtual Duty Suggest", use_container_width=True, key="btn_virtual"):
            with st.spinner("AI duty suggest..."):
                st.session_state["virtual_result"] = ai_virtual_duty_suggest(audit_df, master_df)
        if "virtual_result" in st.session_state:
            st.markdown(f'<div class="ai-response">{st.session_state["virtual_result"]}</div>',
                        unsafe_allow_html=True)
            st.caption("⚠️ यह सिर्फ AI suggestion है — sheet में कोई बदलाव नहीं हुआ")
        st.markdown('</div>', unsafe_allow_html=True)

# ── TAB 2: Employee Search ────────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="section-title">🔍 मोबाइल नंबर से कर्मचारी खोजें</div>', unsafe_allow_html=True)

    sc1, sc2 = st.columns([3, 1])
    with sc1:
        search_mobile = st.text_input("📱 मोबाइल नंबर", placeholder="10 अंकों का नंबर...",
                                       key="mob_search", max_chars=10)
    with sc2:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        search_btn = st.button("🔍 खोजें", use_container_width=True, key="mob_search_btn")

    if search_btn or (search_mobile and len(search_mobile.strip()) == 10):
        mob_q = search_mobile.strip()
        if mob_q.isdigit() and len(mob_q) == 10:
            emp_data, err = ai_employee_search(
                mob_q, master_df, today_shift_map, audit_df, avkaash_df)
            if err:
                st.markdown(f"""
<div style="background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.3);
    border-radius:14px;padding:20px;margin-top:12px;text-align:center;">
    <div style="font-size:2rem;">🔍</div>
    <div style="color:#f87171;font-weight:700;">मोबाइल नं. {_html.escape(mob_q)} से कोई कर्मचारी नहीं मिला</div>
</div>""", unsafe_allow_html=True)
            else:
                render_employee_card(emp_data, active_leave_mobs)
        else:
            st.warning("⚠️ 10 अंकों का सही नंबर दर्ज करें")

# ── TAB 3: Master Data ────────────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="section-title">👥 Master Data — सम्पूर्ण कर्मचारी सूची</div>', unsafe_allow_html=True)
    if master_df.empty:
        st.info("Master Data खाली है। PDF upload करें या manually जोड़ें।")
    else:
        m_search = st.text_input("🔍 नाम / मोबाइल / पदनाम खोजें", placeholder="खोजें...", key="master_search")
        disp = master_df.copy()
        if m_search:
            mask = pd.Series([False]*len(disp), index=disp.index)
            for c in [find_col(disp.columns.tolist(), NAME_ALIASES),
                      find_col(disp.columns.tolist(), DESIG_ALIASES),
                      find_col(disp.columns.tolist(), MOBILE_ALIASES),
                      find_col(disp.columns.tolist(), REMARKS_ALIASES)]:
                if c:
                    mask |= disp[c].astype(str).str.contains(m_search, case=False, na=False)
            disp = disp[mask]
        st.dataframe(disp, use_container_width=True, hide_index=True, height=380)
        md1, _ = st.columns([1,3])
        with md1:
            st.download_button("⬇️ Master Data Excel",
                data=df_to_excel_bytes(disp,"Master_Data"),
                file_name=f"Master_Data_{today_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
        st.caption(f"कुल: {len(disp)} कर्मचारी")

# ── TAB 4: Avkaash ────────────────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="section-title">🌴 अवकाश प्रबंधन</div>', unsafe_allow_html=True)

    if not avkaash_df.empty:
        # ── Enhanced display with calculated days ──────────────────────────
        av_display = avkaash_df.copy()

        # Sd_Days अगर नहीं है या 0 है तो From-To से calculate करो
        def calc_days(row):
            try:
                sd = row.get("Sd_Days","")
                if sd and str(sd).strip() not in ("", "0", "0.0"):
                    return int(float(str(sd)))
                lf = pd.to_datetime(str(row.get("Leave_From","")), dayfirst=True)
                lt = pd.to_datetime(str(row.get("Leave_To","")),   dayfirst=True)
                return max(1, (lt - lf).days + 1)
            except:
                return 0

        av_display["दिन"] = avkaash_df.apply(calc_days, axis=1)

        # Show enhanced table
        name_c_av  = find_col(av_display.columns.tolist(), NAME_ALIASES)
        mob_c_av   = find_col(av_display.columns.tolist(), MOBILE_ALIASES)
        desig_c_av = find_col(av_display.columns.tolist(), DESIG_ALIASES)

        show_cols = []
        rename_av = {}
        for c, label in [(mob_c_av,"📱 मोबाइल"),(name_c_av,"👤 नाम"),
                         (desig_c_av,"🏷️ पद"),
                         ("Leave_From","📅 से"),("Leave_To","📅 तक"),
                         ("दिन","📆 दिन"),("Leave_Reason","कारण"),("Status","स्थिति")]:
            if c and c in av_display.columns:
                show_cols.append(c)
                rename_av[c] = label

        if show_cols:
            st.dataframe(av_display[show_cols].rename(columns=rename_av),
                         use_container_width=True, hide_index=True, height=280)
        else:
            st.dataframe(av_display, use_container_width=True, hide_index=True, height=280)

        # Summary metrics
        total_av_days = int(av_display["दिन"].sum())
        active_cnt    = len(active_leave_mobs)
        mc1, mc2, mc3 = st.columns(3)
        for cc, ic, vv, ll, cls in [
            (mc1,"📋",len(avkaash_df),"कुल प्रविष्टियाँ","card-blue"),
            (mc2,"🌴",active_cnt,    "सक्रिय अवकाश","card-orange"),
            (mc3,"📆",total_av_days, "कुल अवकाश दिन","card-purple")]:
            with cc:
                st.markdown(
                    f'<div class="metric-card {cls}" style="padding:14px 10px;">'
                    f'<span class="icon">{ic}</span>'
                    f'<div class="val" style="font-size:2rem;">{vv}</div>'
                    f'<div class="lbl">{ll}</div></div>',
                    unsafe_allow_html=True)

        av1, _ = st.columns([1,3])
        with av1:
            st.download_button("⬇️ अवकाश Excel",
                data=df_to_excel_bytes(avkaash_df,"Avkaash"),
                file_name=f"Avkaash_{today_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
    else:
        st.info("कोई अवकाश record नहीं। नीचे से नया अवकाश दर्ज करें।")

    st.markdown("---")
    st.markdown("**🌴 नया अवकाश जोड़ें**")

    def clean_mob_av(x):
        s = str(x).strip()
        return s[:-2] if s.endswith('.0') else s

    lc_mob_col, lc_info_col = st.columns([1, 2])
    with lc_mob_col:
        l_mob = st.text_input("📱 मोबाइल नं. *", key="l_mob", max_chars=10, placeholder="10 अंक...")

    auto_name, auto_desig = "", ""
    if l_mob and len(l_mob.strip()) == 10 and l_mob.strip().isdigit():
        mob_c = find_col(master_df.columns.tolist(), MOBILE_ALIASES)
        if mob_c and not master_df.empty:
            res = master_df[master_df[mob_c].apply(clean_mob_av) == l_mob.strip()]
            if not res.empty:
                row        = res.iloc[0]
                name_c_av  = find_col(row.index.tolist(), NAME_ALIASES)
                desig_c_av = find_col(row.index.tolist(), DESIG_ALIASES)
                auto_name  = str(row[name_c_av]).strip()  if name_c_av  else ""
                auto_desig = str(row[desig_c_av]).strip() if desig_c_av else ""

    with lc_info_col:
        if auto_name:
            st.markdown(f"""
<div style="background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.35);
    border-radius:10px;padding:10px 16px;margin-top:4px;display:flex;gap:16px;align-items:center;">
    <span style="font-size:1.3rem;">✅</span>
    <div>
        <div style="color:#4ade80;font-weight:700;">{_html.escape(auto_name)}</div>
        <div style="color:#7a92b8;font-size:0.8rem;">{_html.escape(auto_desig)}</div>
    </div>
</div>""", unsafe_allow_html=True)
        elif l_mob and len(l_mob.strip()) == 10:
            st.markdown("""
<div style="background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.3);
    border-radius:10px;padding:10px 16px;margin-top:4px;">
    <span style="color:#f87171;font-size:0.85rem;">⚠️ Master Data में नहीं मिला — नाम मैन्युअल भरें</span>
</div>""", unsafe_allow_html=True)

    lc1, lc2, lc3 = st.columns(3)
    with lc1:
        l_name  = st.text_input("नाम",  key="l_name",  value=auto_name,  placeholder="Auto-fill...")
        l_desig = st.text_input("पद",   key="l_desig", value=auto_desig, placeholder="Auto-fill...")
    with lc2:
        l_from = st.date_input("📅 छुट्टी से",  key="l_from", value=now_ist().date())
        l_to   = st.date_input("📅 छुट्टी तक", key="l_to",   value=now_ist().date())
    with lc3:
        l_sd     = st.number_input("SD Days", value=0, min_value=0, key="l_sd")
        l_reason = st.text_input("कारण", key="l_reason", placeholder="बीमारी, व्यक्तिगत...")

    if st.button("✅ अवकाश दर्ज करें", key="save_leave"):
        final_l_mob  = l_mob.strip() if l_mob else ""
        final_l_name = (l_name.strip() if l_name else "") or auto_name
        if final_l_mob and final_l_name:
            try:
                add_leave(final_l_mob, final_l_name,
                          (l_desig.strip() if l_desig else "") or auto_desig,
                          l_from.strftime("%d-%m-%Y"), l_to.strftime("%d-%m-%Y"),
                          l_reason, l_sd)
                st.success(f"✅ {final_l_name} का अवकाश दर्ज हो गया!")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.warning("मोबाइल नं. और नाम ज़रूरी है।")

# ── TAB 5: Audit Log ──────────────────────────────────────────────────────────
with tab5:
    st.markdown('<div class="section-title">📜 Audit Log — सम्पूर्ण इतिहास</div>', unsafe_allow_html=True)
    if audit_df.empty:
        st.info("अभी कोई audit record नहीं। PDF upload करने पर यहाँ entries आएंगी।")
    else:
        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            date_filter = st.text_input("तारीख (DD-MM-YYYY)", placeholder="15-03-2025", key="audit_date")
        with ac2:
            shift_filter = st.selectbox("Shift", ["सभी"] + SHIFT_NAMES, key="audit_shift")
        with ac3:
            action_filter = st.selectbox("Action", ["सभी","Loaded","Historical","Added"], key="audit_action")

        a_df    = audit_df.copy()
        date_c  = find_col(a_df.columns.tolist(), ["Date","date"])
        shift_c = find_col(a_df.columns.tolist(), ["Shift","shift"])
        action_c= find_col(a_df.columns.tolist(), ["Action","action"])

        if date_filter and date_c:
            a_df = a_df[a_df[date_c].astype(str).str.contains(date_filter, na=False)]
        if shift_filter != "सभी" and shift_c:
            a_df = a_df[a_df[shift_c] == shift_filter]
        if action_filter != "सभी" and action_c:
            a_df = a_df[a_df[action_c] == action_filter]

        a_sorted = a_df.sort_values(date_c, ascending=False) if date_c in a_df.columns else a_df
        st.dataframe(a_sorted, use_container_width=True, hide_index=True, height=380)
        al1, _ = st.columns([1,3])
        with al1:
            st.download_button("⬇️ Audit Log Excel",
                data=df_to_excel_bytes(a_sorted,"Audit_Log"),
                file_name=f"Audit_Log_{today_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
        st.caption(f"कुल records: {len(a_df)}")

# ── TAB 6: Add Employee ───────────────────────────────────────────────────────
with tab6:
    st.markdown('<div class="section-title">➕ नया कर्मचारी जोड़ें (Manual)</div>', unsafe_allow_html=True)
    ec1, ec2 = st.columns(2)
    with ec1:
        e_mob   = st.text_input("मोबाइल नं. *", key="e_mob", max_chars=10)
        e_name  = st.text_input("नाम *",         key="e_name")
    with ec2:
        e_desig  = st.text_input("पदनाम *",      key="e_desig")
        e_remarks = st.text_input("Remarks",      key="e_remarks")
    if st.button("💾 कर्मचारी सहेजें", key="save_employee"):
        if e_mob and e_name:
            try:
                add_employee_manual(e_mob, e_name, e_desig, e_remarks)
                st.success(f"✅ {e_name} Master_Data में जोड़ा!")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.warning("मोबाइल नं. और नाम ज़रूरी है।")

    st.markdown("---")
    st.markdown('<div class="section-title">📚 JSON से Bulk Import</div>', unsafe_allow_html=True)
    sample_json = '[{"Mobile_No":"9876543210","Designation":"SI","Name":"राम कुमार","Remarks":""}]'
    bulk_json = st.text_area("JSON Staff List", value="", height=150,
                              placeholder=sample_json, key="bulk_json")
    if st.button("📥 Bulk Import करें", key="bulk_import"):
        if bulk_json.strip():
            try:
                staff_list = json.loads(bulk_json)
                client = get_client()
                sh     = client.open_by_key(SHEET_ID)
                ws     = sh.worksheet("Master_Data")
                all_vals = ws.get_all_values()
                header   = all_vals[0] if all_vals else ["Sr_No","Mobile_No","Designation","Name","Remarks"]
                mi_mob   = col_idx_from_header(header, MOBILE_ALIASES)
                existing = {str(row[mi_mob]).strip() for row in all_vals[1:]
                            if mi_mob is not None and mi_mob < len(row)}
                added = 0
                for s in staff_list:
                    mob   = str(s.get("Mobile_No", s.get("mobile_no", s.get("Mobile","")))).strip()
                    name  = str(s.get("Name", s.get("Employee_Name", s.get("नाम","")))).strip()
                    desig = str(s.get("Designation", s.get("Rank", s.get("पदनाम","")))).strip()
                    rem   = str(s.get("Remarks", s.get("remarks",""))).strip()
                    if name and mob not in existing:
                        ws.append_row([len(all_vals)+added, mob, desig, name, rem])
                        existing.add(mob)
                        added += 1
                load_all_data.clear()
                st.success(f"✅ {added} नए कर्मचारी import हुए!")
                st.rerun()
            except json.JSONDecodeError:
                st.error("❌ JSON format गलत।")
            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.warning("JSON paste करें।")

# ── TAB 7: Bulk Historical Import ─────────────────────────────────────────────
with tab7:
    st.markdown('<div class="section-title">📂 Bulk Historical Import</div>', unsafe_allow_html=True)
    st.markdown("""
<div style="background:rgba(46,117,182,0.08);border:1px solid rgba(46,117,182,0.3);
    border-radius:14px;padding:16px 20px;margin-bottom:16px;font-size:0.85rem;line-height:1.8;">
<b style="color:#60a5fa;">📋 Source Sheet Format:</b><br>
&nbsp;&nbsp;• <b>Audit_Log tab</b>: Date | Shift | Mobile_No | Employee_Name | Designation<br>
<b style="color:#ffd700;">⚠️ Duplicate entries automatically skip होंगी</b>
</div>""", unsafe_allow_html=True)

    bh_c1, bh_c2 = st.columns(2)
    with bh_c1:
        bh_sheet_id = st.text_input("📊 Source Google Sheet ID",
            placeholder="1ABC...xyz", key="bh_sheet_id")
        st.caption("URL: docs.google.com/spreadsheets/d/**SHEET_ID**/edit")
    with bh_c2:
        bc1, bc2 = st.columns(2)
        with bc1:
            bh_date_from = st.date_input("📅 तारीख से",  value=date(now_ist().year,3,1), key="bh_date_from")
        with bc2:
            bh_date_to   = st.date_input("📅 तारीख तक", value=now_ist().date(),          key="bh_date_to")

    st.markdown("---")
    bh_preview_btn = st.button("🔍 Preview करें",         key="bh_preview")
    bh_import_btn  = st.button("🚀 Bulk Import शुरू करें", key="bh_import", type="primary")

    if bh_preview_btn or bh_import_btn:
        sid = bh_sheet_id.strip()
        if "/spreadsheets/d/" in sid:
            try:
                sid = sid.split("/spreadsheets/d/")[1].split("/")[0]
            except:
                pass
        if not sid:
            st.warning("⚠️ Source Sheet ID डालें।")
        else:
            d_from_str = bh_date_from.strftime("%d-%m-%Y")
            d_to_str   = bh_date_to.strftime("%d-%m-%Y")

            if bh_preview_btn:
                with st.spinner("Source sheet पढ़ी जा रही है..."):
                    try:
                        _client = get_client()
                        _sh     = _client.open_by_key(sid)
                        try:
                            _ws = _sh.worksheet("Audit_Log")
                        except:
                            _ws = _sh.get_worksheet(0)
                        _recs = _ws.get_all_records()
                        if not _recs:
                            st.error("Source sheet खाली है।")
                        else:
                            d_f    = datetime.strptime(d_from_str,"%d-%m-%Y").date()
                            d_t    = datetime.strptime(d_to_str,  "%d-%m-%Y").date()
                            sample = _recs[0]
                            _col_date = find_col(sample,["Date","date","तारीख"])
                            _col_name = find_col(sample, NAME_ALIASES)
                            filtered  = []
                            for r in _recs:
                                if _col_name and not str(r.get(_col_name,"")).strip():
                                    continue
                                if _col_date:
                                    for fmt in ["%d-%m-%Y","%d/%m/%Y","%Y-%m-%d"]:
                                        try:
                                            rd = datetime.strptime(str(r[_col_date]).strip(),fmt).date()
                                            if d_f <= rd <= d_t:
                                                filtered.append(r)
                                            break
                                        except: pass
                            st.success(f"✅ कुल **{len(_recs)}** rows | Range में **{len(filtered)}** records")
                            if filtered:
                                st.dataframe(pd.DataFrame(filtered[:10]),
                                             use_container_width=True, hide_index=True, height=200)
                                st.caption(f"Columns: {list(sample.keys())}")
                    except Exception as e:
                        st.error(f"❌ Sheet नहीं खुली: {e}")
                        st.info("💡 Service Account के साथ sheet share करें।")

            elif bh_import_btn:
                prog_bar = st.progress(0, text="Import शुरू...")
                def progress_update(done, total):
                    prog_bar.progress(int((done/total)*100) if total else 0,
                                      text=f"Processing... {done}/{total}")
                with st.spinner("Bulk import चल रही है..."):
                    result = bulk_historical_import_from_sheet(
                        sid, d_from_str, d_to_str, progress_cb=progress_update)
                prog_bar.empty()
                if "error" in result:
                    st.error(f"❌ {result['error']}")
                else:
                    r1,r2,r3,r4 = st.columns(4)
                    for c,ic,v,lb,cl in [
                        (r1,"📄",result["total_processed"],"Processed","card-blue"),
                        (r2,"✅",result["added_audit"],"Audit Log में","card-green"),
                        (r3,"👤",result["added_master"],"Master में नए","card-gold"),
                        (r4,"⏭️",result["skipped_dup"],"Duplicates Skip","card-orange")]:
                        with c:
                            st.markdown(
                                f'<div class="metric-card {cl}"><span class="icon">{ic}</span>'
                                f'<div class="val">{v}</div><div class="lbl">{lb}</div></div>',
                                unsafe_allow_html=True)
                    st.success(f"🎉 Import सफल! {result['added_audit']} records, {result['added_master']} नए कर्मचारी।")
                    if result["new_employees"]:
                        st.dataframe(pd.DataFrame(result["new_employees"]),
                                     use_container_width=True, hide_index=True)
                        st.session_state.setdefault("new_staff_alerts",[])
                        st.session_state["new_staff_alerts"].extend(result["new_employees"])
                    if result["skipped_dup"] > 0:
                        st.info(f"ℹ️ {result['skipped_dup']} duplicates skip हुए।")
                    st.rerun()

    with st.expander("❓ Source Sheet कैसे share करें?"):
        st.markdown("""
**Steps:**
1. अपनी पुरानी Google Sheet खोलें
2. **Share** बटन → Service Account Email डालें
3. **Editor** access → Share करें
4. Sheet URL copy करें → यहाँ paste करें
""")

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="footer">
  🚨 साइबर क्राइम हेल्पलाइन <strong>1930</strong> &nbsp;|&nbsp;
  ड्यूटी रोस्टर प्रणाली &nbsp;|&nbsp;
  <span class="live-dot"></span>
  {now_ist().strftime('%d-%m-%Y %H:%M')} IST
</div>
""", unsafe_allow_html=True)
