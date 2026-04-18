"""
══════════════════════════════════════════════════════════════════
  साइबर क्राइम हेल्पलाइन 1930 — ड्यूटी रोस्टर प्रणाली v3.0
  Agentic AI · Google Sheets · Multi-Shift · Hindi UI
══════════════════════════════════════════════════════════════════
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import datetime
import json
import time
import base64
import io
import re
import requests
import html as _html
import logging

# ── Optional imports ──────────────────────────────────────────
try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from PIL import Image
    import fitz  # PyMuPDF
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DutyRoster")

# ══════════════════════════════════════════════════════════════
#  CONSTANTS & CONFIG
# ══════════════════════════════════════════════════════════════
SHEET_NAME  = "Cyber Crime Duty Sheet"
IST_OFFSET  = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

HINDI_MONTHS = {
    1:"जनवरी", 2:"फ़रवरी", 3:"मार्च", 4:"अप्रैल", 5:"मई", 6:"जून",
    7:"जुलाई", 8:"अगस्त", 9:"सितम्बर", 10:"अक्टूबर", 11:"नवम्बर", 12:"दिसम्बर"
}

# ── Google Sheet Tab Names ────────────────────────────────────
TAB_MASTER  = "Master"     # मास्टर डेटा
TAB_SHIFT1  = "Shift1"     # प्रथम पाली
TAB_SHIFT2  = "Shift2"     # द्वितीय पाली
TAB_SHIFT3  = "Shift3"     # तृतीय पाली
TAB_AUDIT   = "Audit_Log"  # ऑडिट लॉग
TAB_AVKASH  = "Avkash"     # अवकाश

# ── Master Tab Headers (exact) ────────────────────────────────
# मो0न0 | नाम | पदनाम | REMARKS | CURRENT पाली | पाली START दिनांक | DAYS ON DUTY
# प्रथम पाली COUNT | द्वितीय पाली COUNT | तृतीय पाली COUNT
MASTER_HEADERS = [
    "मो0न0", "नाम", "पदनाम", "REMARKS",
    "CURRENT पाली", "पाली START दिनांक", "DAYS ON DUTY",
    "प्रथम पाली COUNT", "द्वितीय पाली COUNT", "तृतीय पाली COUNT"
]

# ── Shift Tab Headers ─────────────────────────────────────────
# मो0न0 | नाम | पदनाम | REMARKS | दिनांक
SHIFT_HEADERS = ["मो0न0", "नाम", "पदनाम", "REMARKS", "दिनांक"]

# ── Audit Tab Headers ─────────────────────────────────────────
# मो0न0 | नाम | पदनाम | REMARKS | दिनांक | पाली
AUDIT_HEADERS = ["मो0न0", "नाम", "पदनाम", "REMARKS", "दिनांक", "पाली"]

# ── Avkash Tab Headers ────────────────────────────────────────
# मो0न0 | नाम | पदनाम | अवकाश से | अवकाश तक | कारण | दिन | स्थिति
AVKASH_HEADERS = ["मो0न0", "नाम", "पदनाम", "अवकाश से", "अवकाश तक", "कारण", "दिन", "स्थिति"]

REMARKS_OPTIONS = ["CHO", "CFMC", "Shift Incharge", "Other"]

SHIFT_LABELS = {
    "Shift1": "प्रथम पाली",
    "Shift2": "द्वितीय पाली",
    "Shift3": "तृतीय पाली",
}

# ══════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ══════════════════════════════════════════════════════════════
def now_ist():
    return datetime.datetime.now(IST_OFFSET)

def today_str():
    return now_ist().strftime("%d-%m-%Y")

def clean_mobile(x):
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s

def safe_json(raw):
    raw = re.sub(r'```json|```', '', raw).strip()
    try:
        return json.loads(raw), None
    except:
        return None, "JSON parse failed"

def df_to_excel(df, sheet_name="Sheet1"):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=sheet_name)
    return buf.getvalue()

# ══════════════════════════════════════════════════════════════
#  GOOGLE SHEETS
# ══════════════════════════════════════════════════════════════
@st.cache_resource(ttl=300, show_spinner=False)
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=scopes
    )
    return gspread.authorize(creds)

def get_sheet():
    return get_gspread_client().open(SHEET_NAME)

def get_or_create_ws(sh, title, headers):
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=5000, cols=len(headers) + 2)
    # Ensure headers
    existing = ws.row_values(1)
    if not existing or existing[0] != headers[0]:
        ws.clear()
        ws.append_row(headers)
    return ws

def setup_all_sheets():
    sh = get_sheet()
    get_or_create_ws(sh, TAB_MASTER, MASTER_HEADERS)
    get_or_create_ws(sh, TAB_SHIFT1, SHIFT_HEADERS)
    get_or_create_ws(sh, TAB_SHIFT2, SHIFT_HEADERS)
    get_or_create_ws(sh, TAB_SHIFT3, SHIFT_HEADERS)
    get_or_create_ws(sh, TAB_AUDIT,  AUDIT_HEADERS)
    get_or_create_ws(sh, TAB_AVKASH, AVKASH_HEADERS)

@st.cache_data(ttl=60, show_spinner=False)
def load_all_data():
    sh = get_sheet()
    def safe_df(tab, headers):
        try:
            ws = sh.worksheet(tab)
            vals = ws.get_all_values()
            if len(vals) < 1:
                return pd.DataFrame(columns=headers)
            hdr = vals[0]
            rows = vals[1:] if len(vals) > 1 else []
            # Pad rows
            rows = [r + [""] * (len(hdr) - len(r)) for r in rows]
            return pd.DataFrame(rows, columns=hdr)
        except:
            return pd.DataFrame(columns=headers)

    master_df  = safe_df(TAB_MASTER,  MASTER_HEADERS)
    shift1_df  = safe_df(TAB_SHIFT1,  SHIFT_HEADERS)
    shift2_df  = safe_df(TAB_SHIFT2,  SHIFT_HEADERS)
    shift3_df  = safe_df(TAB_SHIFT3,  SHIFT_HEADERS)
    audit_df   = safe_df(TAB_AUDIT,   AUDIT_HEADERS)
    avkash_df  = safe_df(TAB_AVKASH,  AVKASH_HEADERS)
    return master_df, shift1_df, shift2_df, shift3_df, audit_df, avkash_df

def append_rows_safe(ws, rows, retries=3, pause=15):
    if not rows:
        return
    for attempt in range(retries):
        try:
            ws.append_rows(rows)
            return
        except gspread.exceptions.APIError as e:
            if "429" in str(e) or "Quota" in str(e):
                time.sleep(pause * (attempt + 1))
            else:
                raise
    ws.append_rows(rows)

# ══════════════════════════════════════════════════════════════
#  AGENTIC AI ENGINE
# ══════════════════════════════════════════════════════════════
class AgenticAI:
    GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
    DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
    GEMINI_URL   = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    EXTRACT_PROMPT = """
तुम एक Indian Police Duty Roster AI हो।
नीचे दिए गए text से सभी कर्मचारियों की जानकारी निकालो।

निकालने वाले fields:
- mobile_no: 10 अंकों का मोबाइल नंबर (नहीं मिले तो "")
- naam: कर्मचारी का पूरा नाम
- padnaam: पदनाम / Designation (SI, HC, Constable, ASI, Inspector आदि)
- shift: Shift1 या Shift2 या Shift3 (जो भी document में हो)
- dinank: तारीख DD-MM-YYYY format में

ONLY JSON return करो, कोई extra text नहीं:
{"dinank":"DD-MM-YYYY","shift":"Shift1","staff":[{"mobile_no":"","naam":"","padnaam":""}]}
"""

    def __init__(self):
        self.logs = []

    def log(self, step, status, detail=""):
        self.logs.append({
            "time": now_ist().strftime("%H:%M:%S"),
            "step": step, "status": status, "detail": detail
        })

    def extract_from_pdf(self, pdf_bytes, shift_hint="Shift1"):
        """PDF से text निकालो और AI से parse करो"""
        text = ""
        # Try pdfplumber first
        if PDF_AVAILABLE:
            try:
                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    for page in pdf.pages:
                        t = page.extract_text()
                        if t:
                            text += t + "\n"
            except:
                pass

        # Try PyMuPDF
        if not text and OCR_AVAILABLE:
            try:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                for page in doc:
                    text += page.get_text() + "\n"
                doc.close()
            except:
                pass

        if not text.strip():
            return None, "PDF से text नहीं निकला"

        prompt_content = f"Shift: {shift_hint}\n\nPDF Text:\n{text[:4000]}"
        result, err = self.ai_call_chain(prompt_content)
        return result, err

    def ai_call_chain(self, content):
        """Groq → DeepSeek → Gemini fallback chain"""
        providers = [
            ("Groq",     self._call_groq),
            ("DeepSeek", self._call_deepseek),
            ("Gemini",   self._call_gemini),
        ]
        for name, fn in providers:
            self.log(f"AI: {name}", "🔄 कोशिश")
            try:
                raw = fn(content)
                data, err = safe_json(raw)
                if data and "staff" in data:
                    self.log(f"AI: {name}", "✅ सफल", f"{len(data['staff'])} कर्मचारी")
                    return data, None
                else:
                    self.log(f"AI: {name}", "⚠️ JSON Error", str(err))
            except Exception as e:
                self.log(f"AI: {name}", "❌ Failed", str(e)[:80])
                continue
        return None, "सभी AI providers fail हो गए"

    def _call_groq(self, content):
        key = st.secrets.get("GROQ_API_KEY", "")
        if not key:
            raise Exception("Groq key नहीं मिली")
        r = requests.post(self.GROQ_URL, timeout=30,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile",
                  "messages": [{"role": "system", "content": self.EXTRACT_PROMPT},
                                {"role": "user",   "content": content}],
                  "temperature": 0.1, "max_tokens": 3000})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _call_deepseek(self, content):
        key = st.secrets.get("DEEPSEEK_API_KEY", "")
        if not key:
            raise Exception("DeepSeek key नहीं मिली")
        r = requests.post(self.DEEPSEEK_URL, timeout=30,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat",
                  "messages": [{"role": "system", "content": self.EXTRACT_PROMPT},
                                {"role": "user",   "content": content}],
                  "temperature": 0.1, "max_tokens": 3000})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _call_gemini(self, content):
        key = st.secrets.get("GEMINI_API_KEY", "")
        if not key:
            raise Exception("Gemini key नहीं मिली")
        url = f"{self.GEMINI_URL}?key={key}"
        r = requests.post(url, timeout=30,
            json={"contents": [{"parts": [{"text": self.EXTRACT_PROMPT + "\n\n" + content}]}]})
        r.raise_for_status()
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return raw.replace("```json","").replace("```","").strip()


# ══════════════════════════════════════════════════════════════
#  DATA PROCESSING
# ══════════════════════════════════════════════════════════════
def auto_remarks(entry):
    """PDF data से auto REMARKS detect करो"""
    all_text = " ".join(str(v) for v in entry.values()).lower()
    if "cfmc" in all_text:
        return "CFMC"
    elif "shift incharge" in all_text or "incharge" in all_text or "प्रभारी" in all_text or "इन्चार्ज" in all_text:
        return "Shift Incharge"
    elif "cho" in all_text:
        return "CHO"
    return "Other"

def get_master_lookup(master_df):
    """mobile → {naam, padnaam, remarks} lookup dict"""
    lookup = {}
    for _, row in master_df.iterrows():
        mob = clean_mobile(row.get("मो0न0", ""))
        if mob:
            lookup[mob] = {
                "naam":    str(row.get("नाम", "")).strip(),
                "padnaam": str(row.get("पदनाम", "")).strip(),
                "remarks": str(row.get("REMARKS", "")).strip(),
            }
    return lookup

def get_active_leaves(avkash_df):
    today = now_ist().date()
    active = set()
    for _, row in avkash_df.iterrows():
        try:
            f = datetime.datetime.strptime(str(row.get("अवकाश से","")), "%d-%m-%Y").date()
            t = datetime.datetime.strptime(str(row.get("अवकाश तक","")), "%d-%m-%Y").date()
            if f <= today <= t:
                active.add(clean_mobile(row.get("मो0न0","")))
        except:
            pass
    return active

def get_latest_shift_date(shift_df):
    """Shift sheet की latest तारीख निकालो"""
    if shift_df.empty or "दिनांक" not in shift_df.columns:
        return None
    dates = []
    for d in shift_df["दिनांक"].dropna():
        try:
            dates.append(datetime.datetime.strptime(str(d).strip(), "%d-%m-%Y").date())
        except:
            pass
    return max(dates) if dates else None

def get_shift_for_date(shift_df, date_str):
    """Specific date का shift data"""
    if shift_df.empty or "दिनांक" not in shift_df.columns:
        return pd.DataFrame(columns=SHIFT_HEADERS)
    return shift_df[shift_df["दिनांक"].astype(str).str.strip() == date_str].copy()

def compute_master_stats(master_df, audit_df, avkash_df):
    """Master tab के computed columns update करो (Audit_Log से)"""
    if audit_df.empty:
        return
    sh = get_sheet()
    ws_master = sh.worksheet(TAB_MASTER)
    all_vals  = ws_master.get_all_values()
    if len(all_vals) < 2:
        return
    hdr = all_vals[0]
    try:
        idx_mob     = hdr.index("मो0न0")
        idx_cur     = hdr.index("CURRENT पाली")
        idx_start   = hdr.index("पाली START दिनांक")
        idx_days    = hdr.index("DAYS ON DUTY")
        idx_s1      = hdr.index("प्रथम पाली COUNT")
        idx_s2      = hdr.index("द्वितीय पाली COUNT")
        idx_s3      = hdr.index("तृतीय पाली COUNT")
    except ValueError:
        return  # Headers not matching, skip

    # Build audit stats
    audit_stats = {}  # mob → {Shift1:n, Shift2:n, Shift3:n, latest_shift, latest_date, days}
    for _, row in audit_df.iterrows():
        mob   = clean_mobile(row.get("मो0न0", ""))
        shift = str(row.get("पाली", "")).strip()
        dinank= str(row.get("दिनांक","")).strip()
        if not mob:
            continue
        if mob not in audit_stats:
            audit_stats[mob] = {"Shift1":0, "Shift2":0, "Shift3":0,
                                 "latest_shift":"", "latest_date":"", "days":set()}
        if shift in ("Shift1","Shift2","Shift3"):
            audit_stats[mob][shift] += 1
        if dinank:
            audit_stats[mob]["days"].add(dinank)
        # Track latest
        try:
            new_d = datetime.datetime.strptime(dinank, "%d-%m-%Y")
            if audit_stats[mob]["latest_date"]:
                old_d = datetime.datetime.strptime(audit_stats[mob]["latest_date"], "%d-%m-%Y")
                if new_d >= old_d:
                    audit_stats[mob]["latest_date"]  = dinank
                    audit_stats[mob]["latest_shift"] = shift
            else:
                audit_stats[mob]["latest_date"]  = dinank
                audit_stats[mob]["latest_shift"] = shift
        except:
            if not audit_stats[mob]["latest_date"]:
                audit_stats[mob]["latest_date"]  = dinank
                audit_stats[mob]["latest_shift"] = shift

    # Compute start date per shift
    shift_start = {}  # mob → earliest date in latest shift
    for _, row in audit_df.iterrows():
        mob   = clean_mobile(row.get("मो0न0",""))
        shift = str(row.get("पाली","")).strip()
        dinank= str(row.get("दिनांक","")).strip()
        if not mob or mob not in audit_stats:
            continue
        if shift == audit_stats[mob]["latest_shift"] and dinank:
            if mob not in shift_start:
                shift_start[mob] = dinank
            else:
                try:
                    if datetime.datetime.strptime(dinank,"%d-%m-%Y") < datetime.datetime.strptime(shift_start[mob],"%d-%m-%Y"):
                        shift_start[mob] = dinank
                except:
                    pass

    # Update Master rows
    updates = []
    for row_i, row in enumerate(all_vals[1:], start=2):
        mob = clean_mobile(row[idx_mob]) if idx_mob < len(row) else ""
        if not mob or mob not in audit_stats:
            continue
        stats = audit_stats[mob]
        total_days = len(stats["days"])
        new_row = list(row)
        while len(new_row) <= max(idx_cur, idx_start, idx_days, idx_s1, idx_s2, idx_s3):
            new_row.append("")
        new_row[idx_cur]   = stats["latest_shift"]
        new_row[idx_start] = shift_start.get(mob, "")
        new_row[idx_days]  = total_days
        new_row[idx_s1]    = stats["Shift1"]
        new_row[idx_s2]    = stats["Shift2"]
        new_row[idx_s3]    = stats["Shift3"]
        # Batch update - store cell range
        updates.append({
            "range": f"E{row_i}:J{row_i}",
            "values": [[stats["latest_shift"],
                        shift_start.get(mob,""),
                        total_days,
                        stats["Shift1"],
                        stats["Shift2"],
                        stats["Shift3"]]]
        })

    if updates:
        # Batch update in chunks
        for i in range(0, len(updates), 10):
            try:
                ws_master.batch_update(updates[i:i+10])
                time.sleep(1)
            except:
                pass

def save_shift_and_audit(shift_name, staff_list, dinank_str, master_lookup):
    """Shift sheet + Audit_Log में save करो। Master में नए कर्मचारी जोड़ो।"""
    sh        = get_sheet()
    ws_shift  = sh.worksheet(shift_name)
    ws_audit  = get_or_create_ws(sh, TAB_AUDIT,  AUDIT_HEADERS)
    ws_master = sh.worksheet(TAB_MASTER)

    # ── Check existing master mobiles ─────────────────────────
    all_master = ws_master.get_all_values()
    existing_mobiles = set()
    master_data = {}  # mob → row_num
    if len(all_master) > 1:
        hdr = all_master[0]
        try:
            mi = hdr.index("मो0न0")
        except:
            mi = 0
        for ri, row in enumerate(all_master[1:], start=2):
            mob = clean_mobile(row[mi]) if mi < len(row) else ""
            if mob:
                existing_mobiles.add(mob)
                master_data[mob] = ri

    # ── Clear & rewrite shift sheet for this date ─────────────
    # Remove existing rows for this date, keep others
    existing_shift_vals = ws_shift.get_all_values()
    if len(existing_shift_vals) > 1:
        rows_to_keep = [existing_shift_vals[0]]  # header
        for row in existing_shift_vals[1:]:
            row_date = row[4] if len(row) > 4 else ""
            if str(row_date).strip() != dinank_str:
                rows_to_keep.append(row)
        ws_shift.clear()
        if rows_to_keep:
            ws_shift.update(f"A1", rows_to_keep)
            time.sleep(1)

    # ── Write new staff to shift sheet ───────────────────────
    shift_rows  = []
    audit_rows  = []
    new_master  = []

    for s in staff_list:
        mob    = clean_mobile(s.get("mobile_no", ""))
        naam   = str(s.get("naam", "")).strip()
        padnaam= str(s.get("padnaam","")).strip()

        # Master lookup - prefer master data
        if mob and mob in master_lookup:
            ml = master_lookup[mob]
            naam    = ml["naam"]    or naam
            padnaam = ml["padnaam"] or padnaam
            remarks = ml["remarks"] or auto_remarks(s)
        else:
            remarks = auto_remarks(s)
            if not remarks:
                remarks = "Other"

        if not naam:
            continue

        # Shift row
        shift_rows.append([mob, naam, padnaam, remarks, dinank_str])
        # Audit row
        audit_rows.append([mob, naam, padnaam, remarks, dinank_str, shift_name])

        # New master entry
        if mob and len(mob) == 10 and mob.isdigit() and mob not in existing_mobiles:
            new_master.append([mob, naam, padnaam, remarks, "", "", "", "", "", ""])
            existing_mobiles.add(mob)

    if shift_rows:
        append_rows_safe(ws_shift, shift_rows)
    if audit_rows:
        append_rows_safe(ws_audit, audit_rows)
    if new_master:
        append_rows_safe(ws_master, new_master)

    load_all_data.clear()
    return len(shift_rows), new_master

def save_avkash(mob, naam, padnaam, av_from, av_to, karan, days):
    sh = get_sheet()
    ws = get_or_create_ws(sh, TAB_AVKASH, AVKASH_HEADERS)
    today = now_ist().date()
    try:
        f = datetime.datetime.strptime(av_from, "%d-%m-%Y").date()
        t = datetime.datetime.strptime(av_to,   "%d-%m-%Y").date()
        status = "सक्रिय" if f <= today <= t else ("आगामी" if today < f else "समाप्त")
    except:
        status = "सक्रिय"
    ws.append_row([mob, naam, padnaam, av_from, av_to, karan, days, status])
    load_all_data.clear()

# ══════════════════════════════════════════════════════════════
#  EMPLOYEE SEARCH (from Audit + Master)
# ══════════════════════════════════════════════════════════════
def search_employee(mob, master_df, audit_df, avkash_df):
    mob = clean_mobile(mob)

    # ── From Master ───────────────────────────────────────────
    master_info = {}
    for _, row in master_df.iterrows():
        if clean_mobile(row.get("मो0न0","")) == mob:
            master_info = row.to_dict()
            break

    # ── From Audit ────────────────────────────────────────────
    audit_emp = pd.DataFrame()
    if not audit_df.empty and "मो0न0" in audit_df.columns:
        audit_emp = audit_df[audit_df["मो0न0"].apply(clean_mobile) == mob].copy()

    if audit_emp.empty and not master_info:
        return None, "कर्मचारी नहीं मिला"

    # Name / Pad preference: Master > Audit
    naam    = str(master_info.get("नाम","")).strip()
    padnaam = str(master_info.get("पदनाम","")).strip()
    remarks = str(master_info.get("REMARKS","")).strip()
    cur_pali= str(master_info.get("CURRENT पाली","")).strip()

    if not naam and not audit_emp.empty:
        naam    = str(audit_emp.iloc[-1].get("नाम","")).strip()
        padnaam = str(audit_emp.iloc[-1].get("पदनाम","")).strip()

    # ── Last 2 months audit ───────────────────────────────────
    two_months_ago = now_ist().date() - datetime.timedelta(days=60)
    history_rows = []
    shift_counts = {"Shift1":0, "Shift2":0, "Shift3":0}
    if not audit_emp.empty:
        for _, row in audit_emp.iterrows():
            try:
                d = datetime.datetime.strptime(str(row.get("दिनांक","")).strip(), "%d-%m-%Y").date()
                if d >= two_months_ago:
                    history_rows.append(row)
                    sh = str(row.get("पाली","")).strip()
                    if sh in shift_counts:
                        shift_counts[sh] += 1
            except:
                pass
        history_rows.sort(key=lambda r: datetime.datetime.strptime(str(r.get("दिनांक","01-01-2000")), "%d-%m-%Y"), reverse=True)

    # ── Avkash ────────────────────────────────────────────────
    leaves = []
    total_leave_days = 0
    if not avkash_df.empty and "मो0न0" in avkash_df.columns:
        emp_av = avkash_df[avkash_df["मो0न0"].apply(clean_mobile) == mob]
        for _, row in emp_av.iterrows():
            leaves.append(row.to_dict())
            try:
                total_leave_days += int(float(str(row.get("दिन",0))))
            except:
                try:
                    f = datetime.datetime.strptime(str(row.get("अवकाश से","")), "%d-%m-%Y").date()
                    t = datetime.datetime.strptime(str(row.get("अवकाश तक","")), "%d-%m-%Y").date()
                    total_leave_days += max(1,(t-f).days+1)
                except:
                    pass

    return {
        "mob": mob, "naam": naam, "padnaam": padnaam,
        "remarks": remarks, "cur_pali": cur_pali,
        "shift_counts": shift_counts,
        "total_duty": sum(shift_counts.values()),
        "history": history_rows,
        "leaves": leaves,
        "total_leave_days": total_leave_days,
        "master_row": master_info,
    }, None

# ══════════════════════════════════════════════════════════════
#  UI: PAGE CONFIG & CSS
# ══════════════════════════════════════════════════════════════
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
  --bg-deep:#060d1f;--bg-mid:#0d1b3e;--bg-light:#1a2d5a;--bg-glow:#1e3a7a;
  --blue:#2E75B6;--cyan:#00d4ff;--gold:#ffd700;
  --green:#22c55e;--red:#ef4444;--orange:#f97316;--purple:#a855f7;
  --glass:rgba(255,255,255,0.04);--glass-b:rgba(255,255,255,0.10);
  --txt:#e8f0ff;--muted:#7a92b8;
}
html,body,[class*="css"]{font-family:'Noto Sans Devanagari',sans-serif;
  background:var(--bg-deep)!important;color:var(--txt)!important;}
.stApp{background:linear-gradient(135deg,#060d1f 0%,#0a1628 50%,#060d1f 100%)!important;}
.main .block-container{padding:1.5rem 2rem 3rem!important;max-width:1400px!important;}

/* ── Header ── */
.site-header{background:linear-gradient(135deg,#0d1b3e,#1a2d5a);
  border:1px solid rgba(0,212,255,0.2);border-radius:18px;padding:24px 32px;
  text-align:center;margin-bottom:24px;position:relative;overflow:hidden;}
.site-header::after{content:'';position:absolute;top:-50%;left:-50%;width:200%;height:200%;
  background:linear-gradient(105deg,transparent 40%,rgba(255,255,255,0.04) 50%,transparent 60%);
  animation:sweep 8s ease-in-out infinite;pointer-events:none;}
@keyframes sweep{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
.site-header h1{font-family:'Rajdhani',sans-serif;font-size:2rem;font-weight:700;margin:0 0 6px;
  background:linear-gradient(90deg,#fff 0%,#a8d4ff 30%,#ffd700 60%,#fff 100%);
  background-size:300%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text;animation:shimmer 4s linear infinite;}
@keyframes shimmer{0%{background-position:300%}100%{background-position:-300%}}
.site-header .sub{font-size:.8rem;color:var(--muted);letter-spacing:3px;text-transform:uppercase;}
.live-dot{display:inline-block;width:8px;height:8px;background:#22c55e;border-radius:50%;
  animation:blink 1.5s ease-in-out infinite;box-shadow:0 0 6px #22c55e;
  margin-right:6px;vertical-align:middle;}
@keyframes blink{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(1.5)}}

/* ── Summary Cards ── */
.sum-card{background:var(--glass);border:1px solid var(--glass-b);border-radius:14px;
  padding:16px 12px;text-align:center;position:relative;overflow:hidden;}
.sum-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:14px 14px 0 0;}
.sum-card .v{font-family:'Rajdhani',monospace;font-size:2.6rem;font-weight:700;line-height:1;margin-bottom:4px;}
.sum-card .l{font-size:.72rem;color:var(--muted);font-weight:600;letter-spacing:.5px;}
.sum-card .ic{font-size:1.2rem;margin-bottom:6px;display:block;}
.sc-blue{border-color:rgba(46,117,182,.4);box-shadow:0 4px 20px rgba(46,117,182,.15);}
.sc-blue .v{color:#60a5fa;}.sc-blue::before{background:linear-gradient(90deg,#2E75B6,#60a5fa);}
.sc-gold{border-color:rgba(255,215,0,.4);box-shadow:0 4px 20px rgba(255,215,0,.15);}
.sc-gold .v{color:#ffd700;}.sc-gold::before{background:linear-gradient(90deg,#b8860b,#ffd700);}
.sc-green{border-color:rgba(34,197,94,.4);box-shadow:0 4px 20px rgba(34,197,94,.15);}
.sc-green .v{color:#4ade80;}.sc-green::before{background:linear-gradient(90deg,#16a34a,#4ade80);}
.sc-orange{border-color:rgba(249,115,22,.4);box-shadow:0 4px 20px rgba(249,115,22,.15);}
.sc-orange .v{color:#fb923c;}.sc-orange::before{background:linear-gradient(90deg,#ea580c,#fb923c);}
.sc-red{border-color:rgba(239,68,68,.4);box-shadow:0 4px 20px rgba(239,68,68,.15);}
.sc-red .v{color:#f87171;}.sc-red::before{background:linear-gradient(90deg,#dc2626,#f87171);}
.sc-purple{border-color:rgba(168,85,247,.4);box-shadow:0 4px 20px rgba(168,85,247,.15);}
.sc-purple .v{color:#c084fc;}.sc-purple::before{background:linear-gradient(90deg,#9333ea,#c084fc);}
.sc-cyan{border-color:rgba(0,212,255,.4);box-shadow:0 4px 20px rgba(0,212,255,.15);}
.sc-cyan .v{color:#00d4ff;}.sc-cyan::before{background:linear-gradient(90deg,#0ea5e9,#00d4ff);}

/* ── Shift Cards ── */
.shift-header{border-radius:12px;padding:12px 16px;text-align:center;margin-bottom:8px;
  font-family:'Rajdhani',sans-serif;font-weight:700;font-size:1rem;letter-spacing:1px;}
.sh-s1{background:rgba(255,215,0,.12);border:1px solid rgba(255,215,0,.4);color:#ffd700;}
.sh-s2{background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.4);color:#4ade80;}
.sh-s3{background:rgba(96,165,250,.12);border:1px solid rgba(96,165,250,.4);color:#60a5fa;}

/* ── Section Title ── */
.sec-title{font-family:'Rajdhani',sans-serif;font-size:1rem;font-weight:700;
  color:var(--txt);padding:8px 14px;margin:20px 0 12px;
  background:var(--glass);border:1px solid var(--glass-b);
  border-left:4px solid var(--blue);border-radius:0 8px 8px 0;
  display:flex;align-items:center;gap:8px;}

/* ── Inputs ── */
.stTextInput>div>div>input,input[type="password"]{
  background:#0d1b3e!important;border:1px solid rgba(255,255,255,.12)!important;
  border-radius:8px!important;color:#e8f0ff!important;caret-color:#00d4ff!important;}
.stTextInput>div>div>input:focus{border-color:var(--blue)!important;
  box-shadow:0 0 0 3px rgba(46,117,182,.2)!important;}
.stTextInput label,.stTextInput label p{color:#a0b8d8!important;font-size:.84rem!important;}
.stSelectbox>div>div,.stTextArea textarea{
  background:#0d1b3e!important;border:1px solid rgba(255,255,255,.12)!important;
  border-radius:8px!important;color:var(--txt)!important;}
.stButton>button{
  background:linear-gradient(135deg,var(--bg-mid),var(--blue))!important;
  color:white!important;font-weight:700!important;border-radius:8px!important;
  border:1px solid rgba(46,117,182,.5)!important;transition:all .2s!important;}
.stButton>button:hover{transform:translateY(-2px)!important;
  box-shadow:0 6px 18px rgba(46,117,182,.4)!important;}
.stDownloadButton>button{background:linear-gradient(135deg,#16a34a,#15803d)!important;
  color:white!important;font-weight:700!important;border-radius:8px!important;
  border:1px solid rgba(34,197,94,.4)!important;}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"]{background:var(--glass)!important;
  border:1px solid var(--glass-b)!important;border-radius:10px!important;
  padding:3px!important;gap:3px!important;}
.stTabs [data-baseweb="tab"]{background:transparent!important;border-radius:7px!important;
  color:var(--muted)!important;font-weight:600!important;font-size:.82rem!important;
  padding:7px 14px!important;transition:all .2s!important;border:none!important;}
.stTabs [aria-selected="true"]{
  background:linear-gradient(135deg,var(--bg-glow),var(--blue))!important;color:white!important;}

/* ── Agent Log ── */
.log-line{font-family:'Space Mono',monospace;font-size:.75rem;padding:4px 8px;
  border-radius:4px;margin:2px 0;background:rgba(0,0,0,.4);border-left:2px solid;}
.log-ok{border-color:#22c55e;}.log-fail{border-color:#ef4444;}.log-work{border-color:#ffd700;}

/* ── Alerts ── */
[data-testid="stInfoMessage"]{background:rgba(46,117,182,.1)!important;border-color:var(--blue)!important;}
[data-testid="stSuccessMessage"]{background:rgba(34,197,94,.1)!important;border-color:var(--green)!important;}
[data-testid="stWarningMessage"]{background:rgba(249,115,22,.1)!important;border-color:var(--orange)!important;}

/* ── Table ── */
[data-testid="stDataFrame"]{border:1px solid var(--glass-b)!important;border-radius:10px!important;}

/* ── Clock ── */
.clock-box{background:linear-gradient(135deg,var(--bg-deep),var(--bg-mid));
  border-radius:12px;padding:14px;text-align:center;
  border:1px solid rgba(0,212,255,.2);box-shadow:0 0 20px rgba(0,212,255,.1);}
.clock-time{font-size:1.8rem;font-weight:700;color:var(--cyan);
  font-family:'Space Mono',monospace;letter-spacing:3px;
  text-shadow:0 0 16px rgba(0,212,255,.5);}

/* ── Employee card ── */
.emp-card{background:linear-gradient(135deg,rgba(13,27,62,.97),rgba(26,45,90,.82));
  border-radius:18px;padding:24px 28px;margin-top:14px;}

::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:var(--bg-deep)}
::-webkit-scrollbar-thumb{background:var(--bg-glow);border-radius:3px}

/* login */
.login-wrap{max-width:400px;margin:60px auto;background:linear-gradient(135deg,rgba(13,27,62,.98),rgba(26,45,90,.9));
  border:1px solid rgba(0,212,255,.2);border-radius:22px;padding:40px 32px;text-align:center;
  box-shadow:0 0 50px rgba(46,117,182,.2);}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  PASSWORD
# ══════════════════════════════════════════════════════════════
def check_password():
    if st.session_state.get("auth"):
        return True
    st.markdown("""
<div class="login-wrap">
  <div style="font-size:2.5rem;margin-bottom:10px;">🔐</div>
  <div style="font-size:1.4rem;font-weight:800;font-family:'Rajdhani',sans-serif;">साइबर क्राइम 1930</div>
  <div style="font-size:.75rem;color:var(--muted);letter-spacing:2px;text-transform:uppercase;margin-bottom:4px;">ड्यूटी रोस्टर प्रणाली</div>
</div>""", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        pwd = st.text_input("पासवर्ड", type="password", key="pwd_in", placeholder="••••••••")
        if st.button("🔓 लॉगिन", use_container_width=True):
            if pwd == st.secrets["passwords"]["app_password"]:
                st.session_state["auth"] = True
                st.rerun()
            else:
                st.error("❌ गलत पासवर्ड")
    return False

if not check_password():
    st.stop()

# ══════════════════════════════════════════════════════════════
#  HEADER
# ══════════════════════════════════════════════════════════════
now = now_ist()
st.markdown(f"""
<div class="site-header">
  <h1>🚨 साइबर क्राइम हेल्पलाइन 1930</h1>
  <div class="sub"><span class="live-dot"></span>ड्यूटी रोस्टर प्रबंधन · LIVE SYSTEM</div>
  <div style="font-size:.8rem;color:var(--muted);margin-top:6px;">
    📅 {now.day} {HINDI_MONTHS[now.month]} {now.year} &nbsp;·&nbsp; ⏰ {now.strftime('%I:%M %p')} IST
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### ⚙️ नियंत्रण")
    st.markdown("---")
    st.markdown(f"""<div class="clock-box">
      <div style="font-size:.65rem;color:var(--muted);letter-spacing:2px;text-transform:uppercase;margin-bottom:4px;">IST</div>
      <div class="clock-time">{now.strftime('%I:%M %p')}</div>
      <div style="font-size:.8rem;color:var(--gold);margin-top:4px;">{now.day} {HINDI_MONTHS[now.month]} {now.year}</div>
    </div>""", unsafe_allow_html=True)
    st.markdown("---")
    if st.button("🔧 Sheets Setup", use_container_width=True):
        with st.spinner("Setup..."):
            try:
                setup_all_sheets()
                st.success("✅ सभी Tabs तैयार!")
            except Exception as e:
                st.error(f"Error: {e}")
    if st.button("🔃 Cache रिफ्रेश", use_container_width=True):
        load_all_data.clear()
        st.rerun()
    if st.button("📊 Master Stats Update", use_container_width=True):
        with st.spinner("Stats compute हो रहे हैं..."):
            try:
                master_df_s, _, _, _, audit_df_s, avkash_df_s = load_all_data()
                compute_master_stats(master_df_s, audit_df_s, avkash_df_s)
                load_all_data.clear()
                st.success("✅ Master stats अपडेट!")
            except Exception as e:
                st.error(f"Error: {e}")
    st.markdown("---")
    st.caption(f"PDF: {'✅' if PDF_AVAILABLE else '❌'} | OCR: {'✅' if OCR_AVAILABLE else '❌'}")

# ══════════════════════════════════════════════════════════════
#  LOAD DATA
# ══════════════════════════════════════════════════════════════
with st.spinner("डेटा लोड हो रहा है..."):
    try:
        master_df, shift1_df, shift2_df, shift3_df, audit_df, avkash_df = load_all_data()
    except Exception as e:
        st.error(f"❌ Sheet connect नहीं हुई: {e}")
        st.info("Sidebar में 'Sheets Setup' बटन दबाएं।")
        st.stop()

t_str           = today_str()
active_leaves   = get_active_leaves(avkash_df)
master_lookup   = get_master_lookup(master_df)

# ── Latest date for each shift (for dashboard display) ────────
def get_latest_date_df(shift_df):
    ld = get_latest_shift_date(shift_df)
    if ld:
        return get_shift_for_date(shift_df, ld.strftime("%d-%m-%Y")), ld.strftime("%d-%m-%Y")
    return pd.DataFrame(columns=SHIFT_HEADERS), "—"

s1_latest_df, s1_date = get_latest_date_df(shift1_df)
s2_latest_df, s2_date = get_latest_date_df(shift2_df)
s3_latest_df, s3_date = get_latest_date_df(shift3_df)

# ── Compute dashboard numbers ─────────────────────────────────
total_karmchari = len(master_df)
duty_par        = len(s1_latest_df) + len(s2_latest_df) + len(s3_latest_df)
avkash_par      = len(active_leaves)

# Inactive = in master but not in any latest shift and not on leave
all_duty_mobs = set()
for df_ in [s1_latest_df, s2_latest_df, s3_latest_df]:
    if not df_.empty and "मो0न0" in df_.columns:
        all_duty_mobs.update(df_["मो0न0"].apply(clean_mobile).tolist())

nishkriya = 0
cfmc_count = 0
if not master_df.empty and "मो0न0" in master_df.columns:
    for _, row in master_df.iterrows():
        mob = clean_mobile(row.get("मो0न0",""))
        if mob not in all_duty_mobs and mob not in active_leaves:
            nishkriya += 1
        rem = str(row.get("REMARKS","")).upper()
        if "CFMC" in rem:
            cfmc_count += 1

# ══════════════════════════════════════════════════════════════
#  DASHBOARD — SUMMARY CARDS (Row 1)
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="sec-title">📊 सारांश डैशबोर्ड</div>', unsafe_allow_html=True)

# Row 1: कुल, Duty, Avkash, Nishkriya
cols_r1 = st.columns(4)
for col_, ic_, val_, lbl_, cls_ in [
    (cols_r1[0], "👥", total_karmchari, "कुल कर्मचारी",     "sc-blue"),
    (cols_r1[1], "✅", duty_par,        "ड्यूटी पर",        "sc-green"),
    (cols_r1[2], "🌴", avkash_par,      "अवकाश पर",         "sc-orange"),
    (cols_r1[3], "⏸️", nishkriya,       "निष्क्रिय",         "sc-red"),
]:
    with col_:
        st.markdown(
            f'<div class="sum-card {cls_}"><span class="ic">{ic_}</span>'
            f'<div class="v">{val_}</div><div class="l">{lbl_}</div></div>',
            unsafe_allow_html=True)

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# Row 2: 3 Shift cards + CFMC
cols_r2 = st.columns(4)
for col_, ic_, val_, lbl_, cls_, dt_ in [
    (cols_r2[0], "🟡", len(s1_latest_df), f"प्रथम पाली\n({s1_date})",    "sc-gold",   s1_date),
    (cols_r2[1], "🟢", len(s2_latest_df), f"द्वितीय पाली\n({s2_date})", "sc-green",  s2_date),
    (cols_r2[2], "🔵", len(s3_latest_df), f"तृतीय पाली\n({s3_date})",   "sc-cyan",   s3_date),
    (cols_r2[3], "🏢", cfmc_count,        "CFMC कर्मचारी",               "sc-purple", ""),
]:
    with col_:
        st.markdown(
            f'<div class="sum-card {cls_}"><span class="ic">{ic_}</span>'
            f'<div class="v">{val_}</div>'
            f'<div class="l" style="white-space:pre-line">{lbl_}</div></div>',
            unsafe_allow_html=True)

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SHIFT DISPLAY (Latest date, not hardcoded today)
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="sec-title">📋 वर्तमान पाली — नवीनतम तारीख</div>', unsafe_allow_html=True)
sc1, sc2, sc3 = st.columns(3)
shift_display_cfg = [
    (sc1, s1_latest_df, "🟡 प्रथम पाली",    "sh-s1", "#ffd700", s1_date, "Shift1"),
    (sc2, s2_latest_df, "🟢 द्वितीय पाली",  "sh-s2", "#4ade80", s2_date, "Shift2"),
    (sc3, s3_latest_df, "🔵 तृतीय पाली",    "sh-s3", "#60a5fa", s3_date, "Shift3"),
]
for col_, df_, lbl_, hdr_cls, clr_, dt_, tab_name in shift_display_cfg:
    with col_:
        st.markdown(f'<div class="shift-header {hdr_cls}">{lbl_} ({dt_})</div>', unsafe_allow_html=True)
        if df_.empty:
            st.info("कोई data नहीं — PDF upload करें ↓")
        else:
            disp_cols = [c for c in ["नाम","पदनाम","मो0न0"] if c in df_.columns]
            st.dataframe(df_[disp_cols], use_container_width=True, hide_index=True, height=260)
            st.download_button(
                label=f"⬇️ {lbl_} Excel",
                data=df_to_excel(df_, tab_name),
                file_name=f"{tab_name}_{dt_}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True, key=f"dl_{tab_name}")

st.markdown("---")

# ══════════════════════════════════════════════════════════════
#  MAIN TABS
# ══════════════════════════════════════════════════════════════
tab_upload, tab_search, tab_master, tab_avkash, tab_audit = st.tabs([
    "📂 PDF अपलोड",
    "🔍 कर्मचारी खोज",
    "👥 Master Data",
    "🌴 अवकाश",
    "📜 Audit Log",
])

# ══════════════════════════════════════════════════════════════
#  TAB 1 — PDF UPLOAD (Single button, 3 shifts selectable)
# ══════════════════════════════════════════════════════════════
with tab_upload:
    st.markdown('<div class="sec-title">🤖 Agentic PDF अपलोड — पाली चुनें</div>', unsafe_allow_html=True)

    st.markdown("""
<div style="background:rgba(46,117,182,.08);border:1px solid rgba(46,117,182,.3);
  border-radius:12px;padding:14px 18px;margin-bottom:16px;font-size:.85rem;line-height:1.8;">
<b style="color:#60a5fa;">🤖 Agentic AI कैसे काम करता है:</b><br>
&nbsp;1. PDF upload → text extract (pdfplumber / PyMuPDF)<br>
&nbsp;2. Groq → DeepSeek → Gemini fallback chain<br>
&nbsp;3. Master Data से नाम/पद auto-fill<br>
&nbsp;4. Shift Sheet + Audit_Log में write | REMARKS auto-assign
</div>""", unsafe_allow_html=True)

    up_c1, up_c2, up_c3 = st.columns(3)
    with up_c1:
        sel_shift = st.selectbox(
            "📋 पाली चुनें",
            options=["Shift1","Shift2","Shift3"],
            format_func=lambda x: SHIFT_LABELS[x] + f" ({x})",
            key="sel_shift"
        )
    with up_c2:
        upload_date = st.date_input("📅 तारीख (PDF से auto-detect होगी)", value=now_ist().date(), key="up_date")
    with up_c3:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        hist_mode = st.checkbox("📚 Historical Mode", value=False, key="hist_mode",
                                 help="पुराना data — Shift sheet नहीं बदलेगी")

    uploaded_file = st.file_uploader(
        "📄 Duty Roster PDF यहाँ upload करें",
        type=["pdf"],
        key="single_upload",
        accept_multiple_files=False,
    )

    # Session state for parsed result
    if "parsed_result" not in st.session_state:
        st.session_state.parsed_result = None
    if "parsed_file_name" not in st.session_state:
        st.session_state.parsed_file_name = None

    if uploaded_file is not None:
        if st.session_state.parsed_file_name != uploaded_file.name:
            st.session_state.parsed_result = None

        if st.session_state.parsed_result is None:
            agent = AgenticAI()
            with st.spinner(f"🤖 AI parse कर रहा है — {sel_shift}..."):
                pdf_bytes = uploaded_file.read()
                date_str_fallback = upload_date.strftime("%d-%m-%Y")
                data, err = agent.extract_from_pdf(pdf_bytes, sel_shift)
                if err:
                    st.error(f"❌ {err}")
                else:
                    detected_date = data.get("dinank","").strip() or date_str_fallback
                    shift_from_ai = data.get("shift", sel_shift)
                    st.session_state.parsed_result = {
                        "staff": data.get("staff",[]),
                        "dinank": detected_date,
                        "shift": shift_from_ai,
                        "agent_logs": agent.logs,
                        "err": None,
                    }
                    st.session_state.parsed_file_name = uploaded_file.name

            # Show agent log
            if agent.logs:
                with st.expander("🤖 Agent Activity Log"):
                    for lg in agent.logs:
                        css = "log-ok" if "✅" in lg["status"] else "log-fail" if "❌" in lg["status"] else "log-work"
                        st.markdown(
                            f'<div class="log-line {css}">'
                            f'<span style="color:var(--muted)">{lg["time"]}</span> '
                            f'<b>{lg["step"]}</b> {lg["status"]} '
                            f'<span style="color:var(--muted)">{lg["detail"]}</span></div>',
                            unsafe_allow_html=True)

    result = st.session_state.get("parsed_result")
    if result and not result.get("err"):
        staff_list    = result["staff"]
        final_date    = result["dinank"]
        final_shift   = sel_shift  # user override takes priority

        if not staff_list:
            st.warning("⚠️ कोई कर्मचारी नहीं मिला। Manual check करें।")
        else:
            # Summary
            desig_ct = {}
            for s in staff_list:
                d = str(s.get("padnaam","अज्ञात")).strip() or "अज्ञात"
                desig_ct[d] = desig_ct.get(d,0) + 1
            desig_html = " | ".join(f"<b>{_html.escape(d)}</b>:{c}" for d,c in desig_ct.items())

            st.markdown(f"""
<div style="background:rgba(30,58,122,.5);border:1px solid rgba(96,165,250,.3);
  border-radius:12px;padding:16px;margin:12px 0;">
  <div style="font-weight:700;color:#e8f0ff;margin-bottom:8px;">📋 Parse Summary — {SHIFT_LABELS[final_shift]}</div>
  <div style="font-size:.85rem;color:#a0b8d8;">
    👥 कर्मचारी: <b style="color:#60a5fa">{len(staff_list)}</b> &nbsp;|&nbsp;
    📅 तारीख: <b style="color:#4ade80">{final_date}</b> &nbsp;|&nbsp;
    📋 पाली: <b style="color:#ffd700">{SHIFT_LABELS[final_shift]}</b>
  </div>
  <div style="font-size:.78rem;color:var(--muted);margin-top:5px;">{desig_html}</div>
</div>""", unsafe_allow_html=True)

            # Preview table
            preview_df = pd.DataFrame(staff_list)
            st.dataframe(preview_df, use_container_width=True, hide_index=True, height=200)

            save_btn = st.button(f"💾 {SHIFT_LABELS[final_shift]} Save करें", use_container_width=False, key="save_main")
            if save_btn:
                with st.spinner("💾 Save हो रहा है..."):
                    try:
                        if hist_mode:
                            # Historical: only audit, no shift sheet rewrite
                            sh_ = get_sheet()
                            ws_audit_ = get_or_create_ws(sh_, TAB_AUDIT, AUDIT_HEADERS)
                            audit_rows_ = []
                            new_master_ = []
                            ws_master_ = sh_.worksheet(TAB_MASTER)
                            all_m_ = ws_master_.get_all_values()
                            ex_mob_ = set()
                            if len(all_m_) > 1:
                                try:
                                    mi_ = all_m_[0].index("मो0न0")
                                    ex_mob_ = {clean_mobile(r[mi_]) for r in all_m_[1:] if mi_ < len(r)}
                                except:
                                    pass
                            for s in staff_list:
                                mob_  = clean_mobile(s.get("mobile_no",""))
                                naam_ = str(s.get("naam","")).strip()
                                pad_  = str(s.get("padnaam","")).strip()
                                if mob_ and mob_ in master_lookup:
                                    ml_ = master_lookup[mob_]
                                    naam_ = ml_["naam"] or naam_
                                    pad_  = ml_["padnaam"] or pad_
                                    rem_  = ml_["remarks"] or auto_remarks(s)
                                else:
                                    rem_  = auto_remarks(s) or "Other"
                                if not naam_:
                                    continue
                                audit_rows_.append([mob_, naam_, pad_, rem_, final_date, final_shift])
                                if mob_ and len(mob_)==10 and mob_.isdigit() and mob_ not in ex_mob_:
                                    new_master_.append([mob_, naam_, pad_, rem_, "","","","","",""])
                                    ex_mob_.add(mob_)
                            if audit_rows_:
                                append_rows_safe(ws_audit_, audit_rows_)
                            if new_master_:
                                append_rows_safe(ws_master_, new_master_)
                            load_all_data.clear()
                            st.success(f"📚 Historical: {len(audit_rows_)} records Audit_Log में | {final_date}")
                        else:
                            count, new_m = save_shift_and_audit(final_shift, staff_list, final_date, master_lookup)
                            st.success(f"✅ {count} कर्मचारी — {SHIFT_LABELS[final_shift]} | {final_date}")
                            if new_m:
                                st.info(f"➕ {len(new_m)} नए कर्मचारी Master में जोड़े गए")
                        st.session_state.parsed_result = None
                        st.session_state.parsed_file_name = None
                        st.rerun()
                    except Exception as se:
                        st.error(f"❌ Save error: {se}")

# ══════════════════════════════════════════════════════════════
#  TAB 2 — EMPLOYEE SEARCH
# ══════════════════════════════════════════════════════════════
with tab_search:
    st.markdown('<div class="sec-title">🔍 कर्मचारी खोज — मोबाइल नंबर से</div>', unsafe_allow_html=True)

    # Auto-fill naam on mobile input
    sc_c1, sc_c2 = st.columns([2,1])
    with sc_c1:
        search_mob = st.text_input("📱 मोबाइल नंबर दर्ज करें",
                                    placeholder="10 अंकों का नंबर...",
                                    max_chars=10, key="search_mob")
    with sc_c2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        srch_btn = st.button("🔍 खोजें", use_container_width=True, key="srch_btn")

    # Auto show name while typing
    if search_mob and len(search_mob.strip()) >= 5:
        mob_partial = search_mob.strip()
        if mob_partial in master_lookup:
            ml_info = master_lookup[mob_partial]
            st.markdown(f"""
<div style="background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.3);
  border-radius:8px;padding:8px 14px;display:inline-flex;align-items:center;gap:10px;">
  <span>✅</span>
  <span style="color:#4ade80;font-weight:700;">{_html.escape(ml_info['naam'])}</span>
  <span style="color:var(--muted);font-size:.82rem;">{_html.escape(ml_info['padnaam'])}</span>
</div>""", unsafe_allow_html=True)

    if srch_btn and search_mob:
        mob_q = search_mob.strip()
        if not (mob_q.isdigit() and len(mob_q)==10):
            st.warning("⚠️ 10 अंकों का सही नंबर दर्ज करें")
        else:
            emp, err = search_employee(mob_q, master_df, audit_df, avkash_df)
            if err:
                st.error(f"❌ {err}")
            else:
                # Employee Card
                naam_e    = _html.escape(emp["naam"])
                pad_e     = _html.escape(emp["padnaam"])
                rem_e     = _html.escape(emp["remarks"])
                cur_p     = emp["cur_pali"]
                sc_counts = emp["shift_counts"]
                tot_duty  = emp["total_duty"]
                tot_leave = emp["total_leave_days"]

                pali_color = {"Shift1":"#ffd700","Shift2":"#4ade80","Shift3":"#60a5fa"}.get(cur_p,"#a0b8d8")
                on_leave   = mob_q in active_leaves

                st.markdown(f"""
<div class="emp-card" style="border:1px solid {pali_color}40;border-left:5px solid {pali_color};
  box-shadow:0 8px 30px {pali_color}20;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;">
    <div>
      <div style="font-size:1.5rem;font-weight:800;font-family:'Rajdhani',sans-serif;
        color:#e8f0ff;margin-bottom:4px;">👤 {naam_e}</div>
      <div style="font-size:.85rem;color:#7a92b8;margin-bottom:3px;">🏷️ {pad_e}</div>
      <div style="font-size:.85rem;color:#7a92b8;">📱 <span style="font-family:'Space Mono',monospace;">{mob_q}</span></div>
      {"<div style='margin-top:6px'><span style='background:rgba(255,215,0,.15);border:1px solid rgba(255,215,0,.4);border-radius:16px;padding:3px 12px;font-size:.78rem;color:#ffd700;font-weight:700'>📌 " + rem_e + "</span></div>" if rem_e else ""}
    </div>
    <div style="background:rgba(0,0,0,.4);border:1px solid {pali_color}40;
      border-radius:12px;padding:12px 20px;text-align:center;min-width:120px;">
      <div style="font-size:.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">{"🌴 अवकाश पर" if on_leave else "अंतिम पाली"}</div>
      <div style="font-size:1rem;font-weight:700;color:{pali_color};">{SHIFT_LABELS.get(cur_p,cur_p) if cur_p else "—"}</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

                # Shift count cards
                cards_h = ""
                for sh_k, sh_l, clr_, bg_ in [
                    ("Shift1","प्रथम पाली","#ffd700","rgba(255,215,0,.12)"),
                    ("Shift2","द्वितीय पाली","#4ade80","rgba(34,197,94,.12)"),
                    ("Shift3","तृतीय पाली","#60a5fa","rgba(96,165,250,.12)"),
                ]:
                    cnt_ = sc_counts.get(sh_k,0)
                    cards_h += f"""
<div style="flex:1;min-width:110px;background:{bg_};border:1px solid {clr_}40;
  border-radius:12px;padding:14px 10px;text-align:center;">
  <div style="font-family:'Rajdhani',monospace;font-size:2rem;font-weight:700;color:{clr_};">{cnt_}</div>
  <div style="font-size:.7rem;color:var(--muted);font-weight:600;">{sh_l}</div>
</div>"""
                cards_h += f"""
<div style="flex:1;min-width:110px;background:rgba(168,85,247,.1);border:1px solid rgba(168,85,247,.3);
  border-radius:12px;padding:14px 10px;text-align:center;">
  <div style="font-family:'Rajdhani',monospace;font-size:2rem;font-weight:700;color:#c084fc;">{tot_duty}</div>
  <div style="font-size:.7rem;color:var(--muted);font-weight:600;">कुल ड्यूटी (2 माह)</div>
</div>
<div style="flex:1;min-width:110px;background:rgba(249,115,22,.08);border:1px solid rgba(249,115,22,.3);
  border-radius:12px;padding:14px 10px;text-align:center;">
  <div style="font-family:'Rajdhani',monospace;font-size:2rem;font-weight:700;color:#fb923c;">{tot_leave}</div>
  <div style="font-size:.7rem;color:var(--muted);font-weight:600;">कुल अवकाश दिन</div>
</div>"""

                st.markdown(f"""
<div style="background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.07);
  border-radius:12px;padding:14px;margin-top:10px;">
  <div style="font-size:.72rem;color:var(--muted);margin-bottom:10px;font-weight:700;
    letter-spacing:1px;text-transform:uppercase;">📈 पाली सारांश (अंतिम 2 माह)</div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;">{cards_h}</div>
</div>""", unsafe_allow_html=True)

                # Duty History
                history = emp["history"]
                if history:
                    rows_h = ""
                    for row_ in history[:25]:
                        d_  = _html.escape(str(row_.get("दिनांक","")))
                        sh_ = str(row_.get("पाली",""))
                        p_  = _html.escape(str(row_.get("पदनाम","")))
                        r_  = _html.escape(str(row_.get("REMARKS","")))
                        sc_ = {"Shift1":"#ffd700","Shift2":"#4ade80","Shift3":"#60a5fa"}.get(sh_,"#a0b8d8")
                        rows_h += (f"<tr style='border-bottom:1px solid rgba(255,255,255,.04)'>"
                            f"<td style='padding:5px 10px;color:#a0b8d8'>{d_}</td>"
                            f"<td style='padding:5px 10px'><span style='background:rgba(0,0,0,.3);border-radius:6px;"
                            f"padding:2px 8px;color:{sc_};font-weight:700;font-size:.78rem'>{SHIFT_LABELS.get(sh_,sh_)}</span></td>"
                            f"<td style='padding:5px 10px;color:#4ade80;font-size:.78rem'>{p_}</td>"
                            f"<td style='padding:5px 10px;color:#fbbf24;font-size:.75rem'>{r_}</td>"
                            f"</tr>")
                    st.markdown(f"""
<div style="background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.07);
  border-radius:12px;padding:14px;margin-top:10px;">
  <div style="font-size:.72rem;color:var(--muted);margin-bottom:8px;font-weight:700;
    text-transform:uppercase;letter-spacing:1px;">📅 ड्यूटी इतिहास (अंतिम 2 माह — नवीनतम पहले)</div>
  <div style="overflow-x:auto">
  <table style="width:100%;border-collapse:collapse;font-size:.82rem">
    <thead><tr style="background:rgba(255,255,255,.06)">
      <th style="padding:5px 10px;text-align:left;color:var(--muted)">📅 तारीख</th>
      <th style="padding:5px 10px;text-align:left;color:var(--muted)">🔄 पाली</th>
      <th style="padding:5px 10px;text-align:left;color:var(--muted)">🏷️ पदनाम</th>
      <th style="padding:5px 10px;text-align:left;color:var(--muted)">📌 REMARKS</th>
    </tr></thead>
    <tbody>{rows_h}</tbody>
  </table></div>
</div>""", unsafe_allow_html=True)
                else:
                    st.info("इस कर्मचारी का पिछले 2 महीनों में कोई Audit record नहीं।")

                # Leave History
                if emp["leaves"]:
                    for lv_ in emp["leaves"]:
                        st.markdown(f"""
<div style="background:rgba(249,115,22,.08);border:1px solid rgba(249,115,22,.25);
  border-radius:10px;padding:10px 14px;margin-top:6px;display:flex;gap:12px;
  align-items:center;flex-wrap:wrap;font-size:.83rem;">
  <span style="color:#fb923c;font-weight:700;">{lv_.get('अवकाश से','—')} → {lv_.get('अवकाश तक','—')}</span>
  <span style="background:rgba(249,115,22,.2);border-radius:10px;padding:2px 8px;
    color:#fb923c;font-weight:700;">📅 {lv_.get('दिन',0)} दिन</span>
  <span style="color:#a0b8d8;">{lv_.get('कारण','—')}</span>
  <span style="color:#7a92b8;font-size:.75rem;">{lv_.get('स्थिति','')}</span>
</div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  TAB 3 — MASTER DATA
# ══════════════════════════════════════════════════════════════
with tab_master:
    st.markdown('<div class="sec-title">👥 Master Data — सम्पूर्ण कर्मचारी सूची</div>', unsafe_allow_html=True)
    if master_df.empty:
        st.info("Master Data खाली है। PDF upload करें।")
    else:
        ms_ = st.text_input("🔍 खोजें (नाम / मोबाइल / पदनाम)", placeholder="खोजें...", key="ms_search")
        disp_m = master_df.copy()
        if ms_:
            mask = pd.Series([False]*len(disp_m), index=disp_m.index)
            for c in ["नाम","पदनाम","मो0न0","REMARKS","CURRENT पाली"]:
                if c in disp_m.columns:
                    mask |= disp_m[c].astype(str).str.contains(ms_, case=False, na=False)
            disp_m = disp_m[mask]
        st.dataframe(disp_m, use_container_width=True, hide_index=True, height=380)
        mc1, _ = st.columns([1,3])
        with mc1:
            st.download_button("⬇️ Master Excel",
                data=df_to_excel(disp_m,"Master"),
                file_name=f"Master_{t_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
        st.caption(f"कुल: {len(disp_m)} कर्मचारी")

# ══════════════════════════════════════════════════════════════
#  TAB 4 — AVKASH
# ══════════════════════════════════════════════════════════════
with tab_avkash:
    st.markdown('<div class="sec-title">🌴 अवकाश प्रबंधन</div>', unsafe_allow_html=True)

    if not avkash_df.empty:
        st.dataframe(avkash_df, use_container_width=True, hide_index=True, height=260)
        av1, _ = st.columns([1,3])
        with av1:
            st.download_button("⬇️ अवकाश Excel",
                data=df_to_excel(avkash_df,"Avkash"),
                file_name=f"Avkash_{t_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
    else:
        st.info("कोई अवकाश record नहीं।")

    st.markdown("---")
    st.markdown("**🌴 नया अवकाश दर्ज करें**")

    av_c1, av_c2 = st.columns([1,2])
    with av_c1:
        av_mob = st.text_input("📱 मोबाइल नं. *", key="av_mob", max_chars=10, placeholder="10 अंक")

    av_naam, av_pad = "", ""
    if av_mob and len(av_mob.strip())==10 and av_mob.strip().isdigit():
        mob_k = av_mob.strip()
        if mob_k in master_lookup:
            av_naam = master_lookup[mob_k]["naam"]
            av_pad  = master_lookup[mob_k]["padnaam"]
            with av_c2:
                st.markdown(f"""
<div style="background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.3);
  border-radius:8px;padding:10px 14px;margin-top:4px;display:flex;gap:12px;align-items:center;">
  <span>✅</span>
  <div>
    <div style="color:#4ade80;font-weight:700;">{_html.escape(av_naam)}</div>
    <div style="color:var(--muted);font-size:.8rem;">{_html.escape(av_pad)}</div>
  </div>
</div>""", unsafe_allow_html=True)
        else:
            with av_c2:
                st.warning("⚠️ Master में नहीं मिला — मैन्युअल भरें")

    vc1, vc2, vc3 = st.columns(3)
    with vc1:
        av_naam_inp  = st.text_input("नाम",   key="av_naam",  value=av_naam,  placeholder="Auto-fill")
        av_pad_inp   = st.text_input("पदनाम", key="av_pad",   value=av_pad,   placeholder="Auto-fill")
    with vc2:
        av_from = st.date_input("📅 अवकाश से", key="av_from", value=now_ist().date())
        av_to   = st.date_input("📅 अवकाश तक", key="av_to",   value=now_ist().date())
    with vc3:
        av_karan  = st.text_input("कारण", key="av_karan", placeholder="बीमारी / व्यक्तिगत...")
        av_days   = (av_to - av_from).days + 1 if av_to >= av_from else 0
        st.info(f"📅 कुल: {av_days} दिन")

    if st.button("✅ अवकाश सहेजें", key="save_av"):
        final_naam = av_naam_inp.strip() or av_naam
        final_mob  = av_mob.strip() if av_mob else ""
        if final_mob and final_naam:
            try:
                save_avkash(final_mob, final_naam, av_pad_inp.strip() or av_pad,
                            av_from.strftime("%d-%m-%Y"), av_to.strftime("%d-%m-%Y"),
                            av_karan, av_days)
                st.success(f"✅ {final_naam} का {av_days} दिन का अवकाश दर्ज!")
                st.rerun()
            except Exception as ae:
                st.error(f"Error: {ae}")
        else:
            st.warning("मोबाइल नं. और नाम जरूरी है।")

# ══════════════════════════════════════════════════════════════
#  TAB 5 — AUDIT LOG
# ══════════════════════════════════════════════════════════════
with tab_audit:
    st.markdown('<div class="sec-title">📜 Audit Log — सम्पूर्ण इतिहास</div>', unsafe_allow_html=True)
    if audit_df.empty:
        st.info("Audit Log खाली है।")
    else:
        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            audit_date_f  = st.text_input("तारीख फ़िल्टर", placeholder="DD-MM-YYYY", key="aud_dt")
        with ac2:
            audit_shift_f = st.selectbox("पाली", ["सभी","Shift1","Shift2","Shift3"], key="aud_sh")
        with ac3:
            audit_naam_f  = st.text_input("नाम खोजें", placeholder="नाम...", key="aud_nm")

        a_df = audit_df.copy()
        if audit_date_f and "दिनांक" in a_df.columns:
            a_df = a_df[a_df["दिनांक"].astype(str).str.contains(audit_date_f, na=False)]
        if audit_shift_f != "सभी" and "पाली" in a_df.columns:
            a_df = a_df[a_df["पाली"] == audit_shift_f]
        if audit_naam_f and "नाम" in a_df.columns:
            a_df = a_df[a_df["नाम"].astype(str).str.contains(audit_naam_f, case=False, na=False)]

        st.dataframe(a_df, use_container_width=True, hide_index=True, height=380)
        al1, _ = st.columns([1,3])
        with al1:
            st.download_button("⬇️ Audit Excel",
                data=df_to_excel(a_df,"Audit_Log"),
                file_name=f"Audit_{t_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
        st.caption(f"कुल records: {len(a_df)}")

# ── FOOTER ────────────────────────────────────────────────────
st.markdown(f"""
<div style="text-align:center;color:var(--muted);font-size:.72rem;padding:14px;
  border-top:1px solid rgba(255,255,255,.07);margin-top:24px;letter-spacing:.5px;">
  🚨 साइबर क्राइम हेल्पलाइन <b>1930</b> &nbsp;|&nbsp;
  ड्यूटी रोस्टर प्रणाली &nbsp;|&nbsp;
  <span class="live-dot"></span>
  {now_ist().strftime('%d-%m-%Y %H:%M')} IST
</div>""", unsafe_allow_html=True)

if __name__ == "__main__":
    pass
