"""
══════════════════════════════════════════════════════════════════
  साइबर क्राइम हेल्पलाइन 1930 — ड्यूटी रोस्टर प्रणाली v6.0
  
  MAJOR CHANGES:
  1. AI sirf Mobile No + "CHO" word extract karta hai PDF/Image se
  2. Naam/Padnaam HAMESHA Master se aata hai
  3. CFMC / Barrack duty → heading se detect hoti hai
  4. Login page clear/beautiful
  5. Duplicate detection before save
  6. Naye number → sirf Master mein (naam baad mein bharenge)
  7. Shift1/2/3 → Audit_Log ki sirf LATEST DATE ka data leti hain
══════════════════════════════════════════════════════════════════
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import datetime
import json
import time
import io
import re
import requests
import html as _html
import logging

try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from PIL import Image
    import fitz
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DutyRoster")

# ══════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════
SHEET_NAME  = "Cyber Crime Duty Sheet"
IST_OFFSET  = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

HINDI_MONTHS = {
    1:"जनवरी", 2:"फ़रवरी", 3:"मार्च", 4:"अप्रैल", 5:"मई", 6:"जून",
    7:"जुलाई", 8:"अगस्त", 9:"सितम्बर", 10:"अक्टूबर", 11:"नवम्बर", 12:"दिसम्बर"
}

TAB_MASTER  = "Master"
TAB_SHIFT1  = "Shift1"
TAB_SHIFT2  = "Shift2"
TAB_SHIFT3  = "Shift3"
TAB_AUDIT   = "Audit_Log"
TAB_AVKASH  = "Avkash"

MASTER_HEADERS = [
    "मो0न0", "नाम", "पदनाम", "REMARKS",
    "CURRENT पाली", "पाली START दिनांक", "DAYS ON DUTY",
    "प्रथम पाली COUNT", "द्वितीय पाली COUNT", "तृतीय पाली COUNT"
]
SHIFT_HEADERS  = ["मो0न0", "नाम", "पदनाम", "REMARKS", "दिनांक"]
AUDIT_HEADERS  = ["मो0न0", "नाम", "पदनाम", "REMARKS", "दिनांक", "पाली"]
AVKASH_HEADERS = ["मो0न0", "नाम", "पदनाम", "अवकाश से", "अवकाश तक", "कारण", "दिन", "स्थिति"]

SHIFT_LABELS = {
    "Shift1": "प्रथम पाली",
    "Shift2": "द्वितीय पाली",
    "Shift3": "तृतीय पाली",
}

# ══════════════════════════════════════════════════════════════
#  UTILITY
# ══════════════════════════════════════════════════════════════
def now_ist():
    return datetime.datetime.now(IST_OFFSET)

def today_str():
    return now_ist().strftime("%d-%m-%Y")

def clean_mobile(x):
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    digits = re.sub(r'\D', '', s)
    return digits[-10:] if len(digits) >= 10 else digits

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

def remarks_badge(rem: str) -> str:
    if not rem or rem.strip().lower() in ("", "other", "—"):
        return ""
    cls_map  = {"CHO":"rb-cho", "CFMC":"rb-cfmc", "Shift Incharge":"rb-si",
                "Barrack":"rb-barrack", "Other Duty":"rb-other"}
    icon_map = {"CHO":"📌", "CFMC":"🏢", "Shift Incharge":"⭐",
                "Barrack":"🏠", "Other Duty":"🔖"}
    cls  = cls_map.get(rem, "rb-other")
    icon = icon_map.get(rem, "🔖")
    return f'<span class="rem-badge {cls}">{icon} {_html.escape(rem)}</span>'


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
        ws = sh.add_worksheet(title=title, rows=5000, cols=len(headers)+2)
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
            ws   = sh.worksheet(tab)
            vals = ws.get_all_values()
            if len(vals) < 1:
                return pd.DataFrame(columns=headers)
            hdr  = vals[0]
            rows = vals[1:] if len(vals) > 1 else []
            rows = [r + [""]*(max(len(hdr)-len(r), 0)) for r in rows]
            return pd.DataFrame(rows, columns=hdr)
        except:
            return pd.DataFrame(columns=headers)
    return (
        safe_df(TAB_MASTER, MASTER_HEADERS),
        safe_df(TAB_SHIFT1, SHIFT_HEADERS),
        safe_df(TAB_SHIFT2, SHIFT_HEADERS),
        safe_df(TAB_SHIFT3, SHIFT_HEADERS),
        safe_df(TAB_AUDIT,  AUDIT_HEADERS),
        safe_df(TAB_AVKASH, AVKASH_HEADERS),
    )

def append_rows_safe(ws, rows, retries=3, pause=15):
    if not rows:
        return
    for attempt in range(retries):
        try:
            ws.append_rows(rows)
            return
        except gspread.exceptions.APIError as e:
            if "429" in str(e) or "Quota" in str(e):
                time.sleep(pause*(attempt+1))
            else:
                raise
    ws.append_rows(rows)


# ══════════════════════════════════════════════════════════════
#  MASTER HELPERS
# ══════════════════════════════════════════════════════════════
def get_master_lookup(master_df):
    """Mobile → {naam, padnaam, remarks} map"""
    lookup = {}
    for _, row in master_df.iterrows():
        mob = clean_mobile(row.get("मो0न0",""))
        if mob and len(mob) == 10:
            lookup[mob] = {
                "naam":    str(row.get("नाम","")).strip(),
                "padnaam": str(row.get("पदनाम","")).strip(),
                "remarks": str(row.get("REMARKS","")).strip(),
            }
    return lookup

def get_active_leaves(avkash_df):
    today  = now_ist().date()
    active = set()
    for _, row in avkash_df.iterrows():
        try:
            f = datetime.datetime.strptime(str(row.get("अवकाश से","")),"%d-%m-%Y").date()
            t = datetime.datetime.strptime(str(row.get("अवकाश तक","")),"%d-%m-%Y").date()
            if f <= today <= t:
                active.add(clean_mobile(row.get("मो0न0","")))
        except:
            pass
    return active

def get_latest_shift_date(shift_df):
    if shift_df.empty or "दिनांक" not in shift_df.columns:
        return None
    dates = []
    for d in shift_df["दिनांक"].dropna():
        try:
            dates.append(datetime.datetime.strptime(str(d).strip(),"%d-%m-%Y").date())
        except:
            pass
    return max(dates) if dates else None

def get_shift_for_date(shift_df, date_str):
    if shift_df.empty or "दिनांक" not in shift_df.columns:
        return pd.DataFrame(columns=SHIFT_HEADERS)
    return shift_df[shift_df["दिनांक"].astype(str).str.strip()==date_str].copy()


# ══════════════════════════════════════════════════════════════
#  AI — SIMPLIFIED: Sirf Mobile + CHO detect karo
#  Naam/Padnaam HAMESHA Master se aata hai
# ══════════════════════════════════════════════════════════════

# PDF text se special sections detect karna
SPECIAL_SECTION_KEYWORDS = {
    "CFMC": ["cfmc", "सीएफएमसी", "cfmc room"],
    "Barrack": ["बैरक", "barrack", "बैरक सुरक्षा", "barrack security"],
    "Other Duty": ["अन्य", "other", "09.00 am", "08.00 am", "15.00 pm"],
}

def detect_section_from_heading(heading_text: str) -> str:
    """Heading text se section type detect karo"""
    t = heading_text.strip().lower()
    if any(k in t for k in ["cfmc", "सीएफएमसी"]):
        return "CFMC"
    if any(k in t for k in ["बैरक", "barrack"]):
        return "Barrack"
    if any(k in t for k in ["09.00", "08.00", "15.00", "अन्य ड्यूटी", "other duty"]):
        return "Other Duty"
    return ""

class AgenticAI:
    GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
    DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
    GEMINI_URL   = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    # ── SIMPLIFIED PROMPT: Sirf Mobile + CHO ──────────────────
    EXTRACT_PROMPT = """
You are an Indian Police Duty Roster data extractor.
From the given text, extract ONLY these two things for each staff member:
1. mobile_no : 10-digit mobile number (leave "" if not found)
2. cho_flag  : true if the word "CHO" appears next to/near their entry, false otherwise

Also detect:
- dinank: Date in DD-MM-YYYY format (look for patterns like 22.04.2026 or 22-04-2026)
- shift: Shift1 / Shift2 / Shift3 (look for "प्रथम पाली"→Shift1, "द्वितीय पाली"→Shift2, "तृतीय पाली"→Shift3)

IMPORTANT RULES:
- Do NOT extract naam or padnaam — we get those from Master database
- Only extract mobile numbers (10 digits starting with 6/7/8/9)
- cho_flag = true ONLY if "CHO" word is clearly written next to that entry
- Also look for section headings like "CFMC ROOM", "बैरक सुरक्षा" and note them

Return ONLY valid JSON, no extra text:
{
  "dinank": "DD-MM-YYYY",
  "shift": "Shift1",
  "sections": [
    {
      "section_type": "CHO",
      "mobiles": ["9889301158", "8299279630"]
    },
    {
      "section_type": "CFMC",
      "mobiles": ["7388054141"]
    },
    {
      "section_type": "Barrack",
      "mobiles": ["9792828729", "8896133050"]
    },
    {
      "section_type": "Other Duty",
      "mobiles": ["8840299595"]
    }
  ]
}

If you cannot find sections clearly, use this simpler format:
{
  "dinank": "DD-MM-YYYY",
  "shift": "Shift1",
  "staff": [
    {"mobile_no": "9889301158", "cho_flag": true},
    {"mobile_no": "8299279630", "cho_flag": false}
  ]
}
"""

    def __init__(self):
        self.logs = []

    def log(self, step, status, detail=""):
        self.logs.append({
            "time":   now_ist().strftime("%H:%M:%S"),
            "step":   step,
            "status": status,
            "detail": detail
        })

    def extract_text_from_pdf(self, pdf_bytes):
        """PDF se text extract karo"""
        text = ""
        if PDF_AVAILABLE:
            try:
                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    for page in pdf.pages:
                        t = page.extract_text()
                        if t:
                            text += t + "\n"
            except Exception as e:
                self.log("PDF pdfplumber", "⚠️", str(e)[:60])

        if not text and OCR_AVAILABLE:
            try:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                for page in doc:
                    text += page.get_text() + "\n"
                doc.close()
            except Exception as e:
                self.log("PDF fitz", "⚠️", str(e)[:60])

        return text.strip()

    def extract_text_from_image(self, img_bytes):
        """Image se text extract karo (OCR)"""
        text = ""
        if OCR_AVAILABLE:
            try:
                doc = fitz.open(stream=img_bytes, filetype="png")
                for page in doc:
                    text += page.get_text() + "\n"
                doc.close()
            except:
                pass
            try:
                # Try as jpg if png failed
                if not text:
                    doc = fitz.open(stream=img_bytes, filetype="jpg")
                    for page in doc:
                        text += page.get_text() + "\n"
                    doc.close()
            except:
                pass
        return text.strip()

    def extract_mobiles_directly(self, text: str) -> list:
        """
        Directly text se mobile numbers extract karo (regex)
        Yeh AI se bhi reliable hai basic cases mein
        """
        # 10 digit numbers starting with 6,7,8,9
        pattern = r'\b([6-9]\d{9})\b'
        found = re.findall(pattern, text)
        return list(dict.fromkeys(found))  # unique, order preserved

    def parse_sections_from_text(self, text: str) -> dict:
        """
        Text ko manually parse karo sections ke basis par.
        Lines ko scan karo - heading detect karo - uske baad ke mobiles us section mein
        """
        lines = text.split('\n')
        sections = {}  # section_type → set of mobiles
        current_section = "CHO"  # default

        mobile_pattern = re.compile(r'\b([6-9]\d{9})\b')

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Section heading detect karo
            line_lower = line_stripped.lower()
            if any(k in line_lower for k in ["cfmc", "सीएफएमसी"]):
                current_section = "CFMC"
                continue
            if any(k in line_lower for k in ["बैरक", "barrack"]):
                current_section = "Barrack"
                continue
            if any(k in line_lower for k in ["09.00 am", "08.00 am", "15.00 pm", "अन्य ड्यूटी"]):
                current_section = "Other Duty"
                continue

            # Is line mein mobile number hai?
            mobiles_in_line = mobile_pattern.findall(line_stripped)

            # CHO check: agar "CHO" word hai is line mein
            has_cho = bool(re.search(r'\bCHO\b', line_stripped, re.IGNORECASE))

            for mob in mobiles_in_line:
                # Agar CHO explicitly likha hai to CHO section
                effective_section = "CHO" if has_cho else current_section
                if effective_section not in sections:
                    sections[effective_section] = []
                if mob not in sections[effective_section]:
                    sections[effective_section].append(mob)

        return sections

    def extract_from_pdf(self, pdf_bytes, shift_hint="Shift1", dinank_hint=""):
        """PDF se data extract karo"""
        text = self.extract_text_from_pdf(pdf_bytes)

        if not text:
            return None, "PDF से text नहीं निकला"

        self.log("Text Extract", "✅", f"{len(text)} chars")

        # Method 1: Direct regex parsing (fast, no AI tokens)
        sections = self.parse_sections_from_text(text)
        date_found = self._extract_date_from_text(text) or dinank_hint
        shift_found = self._extract_shift_from_text(text) or shift_hint

        if sections:
            self.log("Direct Parse", "✅", f"{sum(len(v) for v in sections.values())} numbers found")
            return self._build_result(sections, date_found, shift_found), None

        # Method 2: AI fallback (agar direct parse nahi chala)
        self.log("AI Fallback", "🔄", "Direct parse ne kuch nahi diya, AI try kar raha hai...")
        result, err = self.ai_call_chain(f"Shift: {shift_hint}\nDate: {dinank_hint}\n\nText:\n{text[:3000]}")
        return result, err

    def extract_from_image(self, img_bytes, shift_hint="Shift1", dinank_hint=""):
        """Image se data extract karo"""
        text = self.extract_text_from_image(img_bytes)

        if text:
            sections = self.parse_sections_from_text(text)
            date_found = self._extract_date_from_text(text) or dinank_hint
            shift_found = self._extract_shift_from_text(text) or shift_hint
            if sections:
                return self._build_result(sections, date_found, shift_found), None

        # AI se try karo
        result, err = self.ai_call_chain(f"Shift: {shift_hint}\nDate: {dinank_hint}\n\nImage text:\n{text[:3000] if text else 'No text extracted from image'}")
        return result, err

    def _extract_date_from_text(self, text: str) -> str:
        """Text se date DD-MM-YYYY format mein nikalo"""
        # Format: 22.04.2026 ya 22-04-2026 ya 22/04/2026
        patterns = [
            r'(\d{1,2})[.\-/](\d{1,2})[.\-/](20\d{2})',
            r'(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})',
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                g = m.groups()
                if len(g[0]) == 4:  # YYYY-MM-DD
                    return f"{g[2].zfill(2)}-{g[1].zfill(2)}-{g[0]}"
                else:  # DD-MM-YYYY
                    return f"{g[0].zfill(2)}-{g[1].zfill(2)}-{g[2]}"
        return ""

    def _extract_shift_from_text(self, text: str) -> str:
        """Text se shift detect karo"""
        t = text.lower()
        if "प्रथम पाली" in t or "first shift" in t or "shift1" in t:
            return "Shift1"
        if "द्वितीय पाली" in t or "second shift" in t or "shift2" in t:
            return "Shift2"
        if "तृतीय पाली" in t or "third shift" in t or "shift3" in t:
            return "Shift3"
        # Time-based detection
        if "07:00" in text or "07.00" in text:
            return "Shift1"
        if "14:00" in text or "14.00" in text:
            return "Shift2"
        if "21:00" in text or "21.00" in text:
            return "Shift3"
        return ""

    def _build_result(self, sections: dict, dinank: str, shift: str) -> dict:
        """Sections dict se final result banao"""
        staff = []
        for section_type, mobiles in sections.items():
            for mob in mobiles:
                staff.append({
                    "mobile_no":    mob,
                    "cho_flag":     section_type == "CHO",
                    "section_type": section_type,
                })
        return {
            "dinank":   dinank,
            "shift":    shift,
            "staff":    staff,
            "sections": sections,
        }

    def ai_call_chain(self, content):
        """AI providers chain"""
        for name, fn in [
            ("Groq",     self._call_groq),
            ("DeepSeek", self._call_deepseek),
            ("Gemini",   self._call_gemini),
        ]:
            self.log(f"AI: {name}", "🔄 कोशिश")
            try:
                raw  = fn(content)
                data, err = safe_json(raw)
                if data:
                    # Normalize AI response
                    normalized = self._normalize_ai_response(data)
                    if normalized and normalized.get("staff"):
                        self.log(f"AI: {name}", "✅ सफल",
                                 f"{len(normalized['staff'])} numbers")
                        return normalized, None
                self.log(f"AI: {name}", "⚠️ JSON Error", str(err))
            except Exception as e:
                self.log(f"AI: {name}", "❌ Failed", str(e)[:80])
        return None, "सभी AI providers fail हो गए"

    def _normalize_ai_response(self, data: dict) -> dict:
        """AI response ko standard format mein convert karo"""
        dinank = data.get("dinank", "")
        shift  = data.get("shift", "Shift1")
        staff  = []

        if "sections" in data:
            for sec in data["sections"]:
                stype   = sec.get("section_type", "CHO")
                mobiles = sec.get("mobiles", [])
                for mob in mobiles:
                    mob_clean = clean_mobile(str(mob))
                    if len(mob_clean) == 10:
                        staff.append({
                            "mobile_no":    mob_clean,
                            "cho_flag":     stype == "CHO",
                            "section_type": stype,
                        })
        elif "staff" in data:
            for s in data["staff"]:
                mob_clean = clean_mobile(str(s.get("mobile_no", "")))
                if len(mob_clean) == 10:
                    staff.append({
                        "mobile_no":    mob_clean,
                        "cho_flag":     s.get("cho_flag", False),
                        "section_type": "CHO" if s.get("cho_flag") else "Other",
                    })

        return {"dinank": dinank, "shift": shift, "staff": staff}

    @staticmethod
    def _get_key(top, section, sec_key="api_key"):
        for getter in [
            lambda: st.secrets.get(top, ""),
            lambda: st.secrets.get(section, {}).get(top, ""),
            lambda: st.secrets.get(section, {}).get(sec_key, ""),
        ]:
            try:
                v = getter()
                if v:
                    return str(v).strip()
            except:
                pass
        return ""

    def _call_groq(self, content):
        key = self._get_key("GROQ_API_KEY", "groq")
        if not key:
            raise Exception("Groq key नहीं मिली")
        r = requests.post(self.GROQ_URL, timeout=45,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile",
                  "messages": [{"role": "system", "content": self.EXTRACT_PROMPT},
                                {"role": "user",   "content": content}],
                  "temperature": 0.0, "max_tokens": 2000})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _call_deepseek(self, content):
        key = self._get_key("DEEPSEEK_API_KEY", "deepseek")
        if not key:
            raise Exception("DeepSeek key नहीं मिली")
        r = requests.post(self.DEEPSEEK_URL, timeout=45,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat",
                  "messages": [{"role": "system", "content": self.EXTRACT_PROMPT},
                                {"role": "user",   "content": content}],
                  "temperature": 0.0, "max_tokens": 2000})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _call_gemini(self, content):
        key = self._get_key("GEMINI_API_KEY", "gemini")
        if not key:
            raise Exception("Gemini key नहीं मिली")
        r = requests.post(f"{self.GEMINI_URL}?key={key}", timeout=45,
            json={"contents": [{"parts": [{"text": self.EXTRACT_PROMPT + "\n" + content}]}]})
        r.raise_for_status()
        return (r.json()["candidates"][0]["content"]["parts"][0]["text"]
                .replace('```json', '').replace('```', '').strip())


# ══════════════════════════════════════════════════════════════
#  SAVE FUNCTION — Master se naam/padnaam lo
# ══════════════════════════════════════════════════════════════
def prepare_staff_with_master(staff_list: list, master_lookup: dict) -> tuple:
    """
    staff_list mein sirf mobile_no + cho_flag + section_type hai
    Master se naam, padnaam, remarks fill karo
    
    Returns:
      - final_rows: [(mob, naam, padnaam, remarks)] 
      - new_mobiles: mobile numbers jo Master mein nahi hain
      - duplicates: mobile numbers jo already hai (same day)
    """
    final_rows  = []
    new_mobiles = []
    seen_in_batch = set()

    for s in staff_list:
        mob = clean_mobile(str(s.get("mobile_no", "")))
        if not mob or len(mob) != 10:
            continue

        # Duplicate check within this batch
        if mob in seen_in_batch:
            continue
        seen_in_batch.add(mob)

        section_type = s.get("section_type", "")
        cho_flag     = s.get("cho_flag", False)

        if mob in master_lookup:
            ml      = master_lookup[mob]
            naam    = ml["naam"]
            padnaam = ml["padnaam"]
            # REMARKS: section_type se determine karo
            if section_type == "CFMC":
                remarks = "CFMC"
            elif section_type == "Barrack":
                remarks = "Barrack"
            elif section_type == "Other Duty":
                remarks = "Other Duty"
            elif cho_flag or section_type == "CHO":
                remarks = "CHO"
            else:
                remarks = ml["remarks"] or "Other"
        else:
            # Naya employee — Master mein nahi hai
            naam    = ""  # Baad mein bhara jaayega
            padnaam = ""
            if section_type == "CFMC":
                remarks = "CFMC"
            elif cho_flag or section_type == "CHO":
                remarks = "CHO"
            else:
                remarks = section_type or "Other"
            new_mobiles.append(mob)

        final_rows.append((mob, naam, padnaam, remarks))

    return final_rows, new_mobiles


def check_duplicates_in_sheet(ws_shift, dinank_str: str, mobiles_to_check: list) -> list:
    """
    Shift sheet mein check karo ki yeh mobile + date already exist karta hai
    Returns: list of duplicate mobile numbers
    """
    try:
        all_vals = ws_shift.get_all_values()
        if len(all_vals) <= 1:
            return []
        existing = set()
        for row in all_vals[1:]:
            if len(row) >= 5:
                mob_ex  = clean_mobile(str(row[0]))
                date_ex = str(row[4]).strip()
                if date_ex == dinank_str:
                    existing.add(mob_ex)
        return [m for m in mobiles_to_check if m in existing]
    except:
        return []


def save_shift_and_audit(shift_name, final_rows, dinank_str, master_lookup, new_mobiles):
    """
    final_rows: [(mob, naam, padnaam, remarks)]
    Shift + Audit + Master (naye) mein save karo
    """
    sh        = get_sheet()
    ws_shift  = sh.worksheet(shift_name)
    ws_audit  = get_or_create_ws(sh, TAB_AUDIT, AUDIT_HEADERS)
    ws_master = sh.worksheet(TAB_MASTER)

    shift_rows = []
    audit_rows = []

    for mob, naam, padnaam, remarks in final_rows:
        if not naam and mob not in new_mobiles:
            continue  # Skip agar naam khali ho aur master mein nahi hai
        row_data = [mob, naam, padnaam, remarks, dinank_str]
        shift_rows.append(row_data)
        audit_rows.append([mob, naam, padnaam, remarks, dinank_str, shift_name])

    # Naye employees ko Master mein daalo (sirf mobile)
    new_master_rows = []
    all_master = ws_master.get_all_values()
    existing_in_master = set()
    if len(all_master) > 1:
        try:
            mi = all_master[0].index("मो0न0")
            existing_in_master = {clean_mobile(r[mi]) for r in all_master[1:] if mi < len(r)}
        except:
            pass

    for mob in new_mobiles:
        if mob not in existing_in_master:
            new_master_rows.append([mob, "", "", "", "", "", "", "", "", ""])
            existing_in_master.add(mob)

    if shift_rows:   append_rows_safe(ws_shift,  shift_rows)
    if audit_rows:   append_rows_safe(ws_audit,  audit_rows)
    if new_master_rows: append_rows_safe(ws_master, new_master_rows)

    load_all_data.clear()
    return len(shift_rows), len(new_master_rows)


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
#  MASTER STATS
# ══════════════════════════════════════════════════════════════
def compute_master_stats(master_df, audit_df, avkash_df):
    if audit_df.empty:
        return
    sh        = get_sheet()
    ws_master = sh.worksheet(TAB_MASTER)
    all_vals  = ws_master.get_all_values()
    if len(all_vals) < 2:
        return
    hdr = all_vals[0]
    try:
        idx_mob   = hdr.index("मो0न0")
        idx_cur   = hdr.index("CURRENT पाली")
        idx_start = hdr.index("पाली START दिनांक")
        idx_days  = hdr.index("DAYS ON DUTY")
        idx_s1    = hdr.index("प्रथम पाली COUNT")
        idx_s2    = hdr.index("द्वितीय पाली COUNT")
        idx_s3    = hdr.index("तृतीय पाली COUNT")
    except ValueError:
        return

    audit_stats = {}
    for _, row in audit_df.iterrows():
        mob    = clean_mobile(row.get("मो0न0",""))
        shift  = str(row.get("पाली","")).strip()
        dinank = str(row.get("दिनांक","")).strip()
        if not mob:
            continue
        if mob not in audit_stats:
            audit_stats[mob] = {"Shift1":0,"Shift2":0,"Shift3":0,
                                 "latest_shift":"","latest_date":"","days":set()}
        if shift in ("Shift1","Shift2","Shift3"):
            audit_stats[mob][shift] += 1
        if dinank:
            audit_stats[mob]["days"].add(dinank)
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

    shift_start = {}
    for _, row in audit_df.iterrows():
        mob    = clean_mobile(row.get("मो0न0",""))
        shift  = str(row.get("पाली","")).strip()
        dinank = str(row.get("दिनांक","")).strip()
        if not mob or mob not in audit_stats:
            continue
        if shift == audit_stats[mob]["latest_shift"] and dinank:
            if mob not in shift_start:
                shift_start[mob] = dinank
            else:
                try:
                    if (datetime.datetime.strptime(dinank, "%d-%m-%Y") <
                            datetime.datetime.strptime(shift_start[mob], "%d-%m-%Y")):
                        shift_start[mob] = dinank
                except:
                    pass

    updates = []
    for row_i, row in enumerate(all_vals[1:], start=2):
        mob = clean_mobile(row[idx_mob]) if idx_mob < len(row) else ""
        if not mob or mob not in audit_stats:
            continue
        stats = audit_stats[mob]
        updates.append({"range": f"E{row_i}:J{row_i}", "values": [[
            stats["latest_shift"], shift_start.get(mob,""),
            len(stats["days"]), stats["Shift1"], stats["Shift2"], stats["Shift3"]
        ]]})

    for i in range(0, len(updates), 10):
        try:
            ws_master.batch_update(updates[i:i+10])
            time.sleep(1)
        except:
            pass


# ══════════════════════════════════════════════════════════════
#  EMPLOYEE SEARCH
# ══════════════════════════════════════════════════════════════
def search_employee(mob, master_df, audit_df, avkash_df):
    mob = clean_mobile(mob)
    master_info = {}
    for _, row in master_df.iterrows():
        if clean_mobile(row.get("मो0न0","")) == mob:
            master_info = row.to_dict()
            break

    audit_emp = pd.DataFrame()
    if not audit_df.empty and "मो0न0" in audit_df.columns:
        audit_emp = audit_df[
            audit_df["मो0न0"].apply(clean_mobile) == mob
        ].copy()

    if audit_emp.empty and not master_info:
        return None, "कर्मचारी नहीं मिला"

    naam     = str(master_info.get("नाम","")).strip()
    padnaam  = str(master_info.get("पदनाम","")).strip()
    remarks  = str(master_info.get("REMARKS","")).strip()
    cur_pali = str(master_info.get("CURRENT पाली","")).strip()

    if not naam and not audit_emp.empty:
        naam    = str(audit_emp.iloc[-1].get("नाम","")).strip()
        padnaam = str(audit_emp.iloc[-1].get("पदनाम","")).strip()

    two_months_ago = now_ist().date() - datetime.timedelta(days=60)
    history_rows   = []
    shift_counts   = {"Shift1":0,"Shift2":0,"Shift3":0}
    if not audit_emp.empty:
        for _, row in audit_emp.iterrows():
            try:
                d = datetime.datetime.strptime(
                    str(row.get("दिनांक","")).strip(), "%d-%m-%Y").date()
                if d >= two_months_ago:
                    history_rows.append(row)
                    sh_k = str(row.get("पाली","")).strip()
                    if sh_k in shift_counts:
                        shift_counts[sh_k] += 1
            except:
                pass
        history_rows.sort(
            key=lambda r: datetime.datetime.strptime(
                str(r.get("दिनांक","01-01-2000")), "%d-%m-%Y"),
            reverse=True)

    leaves           = []
    total_leave_days = 0
    if not avkash_df.empty and "मो0न0" in avkash_df.columns:
        emp_av = avkash_df[avkash_df["मो0न0"].apply(clean_mobile) == mob]
        for _, row in emp_av.iterrows():
            leaves.append(row.to_dict())
            try:
                total_leave_days += int(float(str(row.get("दिन", 0))))
            except:
                try:
                    f = datetime.datetime.strptime(str(row.get("अवकाश से","")),"%d-%m-%Y").date()
                    t = datetime.datetime.strptime(str(row.get("अवकाश तक","")),"%d-%m-%Y").date()
                    total_leave_days += max(1,(t-f).days+1)
                except:
                    pass

    return {
        "mob":mob,"naam":naam,"padnaam":padnaam,"remarks":remarks,"cur_pali":cur_pali,
        "shift_counts":shift_counts,"total_duty":sum(shift_counts.values()),
        "history":history_rows,"leaves":leaves,"total_leave_days":total_leave_days,
        "master_row":master_info,
    }, None


# ══════════════════════════════════════════════════════════════
#  PAGE CONFIG & CSS  — Login page clear + beautiful
# ══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="ड्यूटी रोस्टर | 1930",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;500;600;700;900&family=Rajdhani:wght@500;600;700&family=Space+Mono:wght@400;700&display=swap');

:root{
  --bg-deep:#060d1f;--bg-mid:#0d1b3e;--bg-light:#1a2d5a;--bg-glow:#1e3a7a;
  --blue:#2E75B6;--cyan:#00d4ff;--gold:#ffd700;--green:#22c55e;--red:#ef4444;
  --orange:#f97316;--purple:#a855f7;
  --glass:rgba(255,255,255,0.04);--glass-b:rgba(255,255,255,0.10);
  --txt:#e8f0ff;--muted:#7a92b8;
}
html,body,[class*="css"]{
  font-family:'Noto Sans Devanagari',sans-serif;
  background:var(--bg-deep)!important;
  color:var(--txt)!important;
}
.stApp{
  background:linear-gradient(135deg,#060d1f 0%,#0a1628 50%,#060d1f 100%)!important;
}
.main .block-container{
  padding:1.5rem 2rem 3rem!important;max-width:1400px!important;
}

/* ═══ LOGIN PAGE ═══ */
.login-wrap{
  max-width:420px;margin:50px auto;
  background:linear-gradient(135deg,rgba(13,27,62,.98),rgba(26,45,90,.95));
  border:1px solid rgba(0,212,255,.3);
  border-radius:24px;padding:44px 36px;text-align:center;
  box-shadow:0 0 60px rgba(46,117,182,.3),0 0 120px rgba(0,0,0,.5);
}
.login-wrap .login-title{
  font-family:'Rajdhani',sans-serif;font-size:1.8rem;font-weight:700;
  background:linear-gradient(90deg,#fff,#00d4ff,#ffd700);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text;margin-bottom:4px;
}
.login-wrap .login-sub{
  font-size:.75rem;color:#a0c0e0;letter-spacing:3px;
  text-transform:uppercase;margin-bottom:28px;
}

/* Password input — clear white text */
.login-wrap .stTextInput>div>div>input,
.login-wrap input[type="password"],
div[data-testid="stTextInput"] input[type="password"]{
  background:rgba(255,255,255,0.12)!important;
  border:2px solid rgba(0,212,255,.4)!important;
  border-radius:10px!important;
  color:#ffffff!important;
  font-size:1.1rem!important;
  font-weight:600!important;
  letter-spacing:4px!important;
  caret-color:#00d4ff!important;
  text-align:center!important;
  padding:12px 16px!important;
}
div[data-testid="stTextInput"] input[type="password"]::placeholder{
  color:rgba(255,255,255,0.5)!important;
  letter-spacing:2px!important;
  font-size:.9rem!important;
}
div[data-testid="stTextInput"] input[type="password"]:focus{
  border-color:#00d4ff!important;
  background:rgba(255,255,255,0.16)!important;
  box-shadow:0 0 0 3px rgba(0,212,255,.2)!important;
}
.login-wrap .stTextInput label,.login-wrap .stTextInput label p{
  color:#c0d8f0!important;font-size:.88rem!important;
  font-weight:600!important;letter-spacing:1px!important;
}

/* ═══ HEADER ═══ */
.site-header{
  background:linear-gradient(135deg,#0d1b3e,#1a2d5a);
  border:1px solid rgba(0,212,255,.2);border-radius:18px;
  padding:24px 32px;text-align:center;margin-bottom:24px;
  position:relative;overflow:hidden;
}
.site-header::after{
  content:'';position:absolute;top:-50%;left:-50%;width:200%;height:200%;
  background:linear-gradient(105deg,transparent 40%,rgba(255,255,255,.04) 50%,transparent 60%);
  animation:sweep 8s ease-in-out infinite;pointer-events:none;
}
@keyframes sweep{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
.site-header h1{
  font-family:'Rajdhani',sans-serif;font-size:2rem;font-weight:700;margin:0 0 6px;
  background:linear-gradient(90deg,#fff 0%,#a8d4ff 30%,#ffd700 60%,#fff 100%);
  background-size:300%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text;animation:shimmer 4s linear infinite;
}
@keyframes shimmer{0%{background-position:300%}100%{background-position:-300%}}
.site-header .sub{font-size:.8rem;color:var(--muted);letter-spacing:3px;text-transform:uppercase;}
.live-dot{
  display:inline-block;width:8px;height:8px;background:#22c55e;border-radius:50%;
  animation:blink 1.5s ease-in-out infinite;box-shadow:0 0 6px #22c55e;
  margin-right:6px;vertical-align:middle;
}
@keyframes blink{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(1.5)}}

/* ═══ SUMMARY CARDS ═══ */
.sum-card{
  background:var(--glass);border:1px solid var(--glass-b);border-radius:14px;
  padding:16px 12px;text-align:center;position:relative;overflow:hidden;
}
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

/* ═══ SHIFT HEADERS ═══ */
.shift-header{
  border-radius:12px;padding:12px 16px;text-align:center;margin-bottom:8px;
  font-family:'Rajdhani',sans-serif;font-weight:700;font-size:1rem;letter-spacing:1px;
}
.sh-s1{background:rgba(255,215,0,.12);border:1px solid rgba(255,215,0,.4);color:#ffd700;}
.sh-s2{background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.4);color:#4ade80;}
.sh-s3{background:rgba(96,165,250,.12);border:1px solid rgba(96,165,250,.4);color:#60a5fa;}

/* ═══ SECTION TITLE ═══ */
.sec-title{
  font-family:'Rajdhani',sans-serif;font-size:1rem;font-weight:700;color:var(--txt);
  padding:8px 14px;margin:20px 0 12px;background:var(--glass);
  border:1px solid var(--glass-b);border-left:4px solid var(--blue);
  border-radius:0 8px 8px 0;display:flex;align-items:center;gap:8px;
}

/* ═══ INPUTS ═══ */
.stTextInput>div>div>input,input[type="password"]{
  background:#0d1b3e!important;border:1px solid rgba(255,255,255,.2)!important;
  border-radius:8px!important;color:#ffffff!important;
  font-size:.95rem!important;font-weight:500!important;
  caret-color:#00d4ff!important;
}
.stTextInput>div>div>input:focus{
  border-color:var(--blue)!important;box-shadow:0 0 0 3px rgba(46,117,182,.2)!important;
}
.stTextInput label,.stTextInput label p{color:#a0c0e0!important;font-size:.84rem!important;}
.stSelectbox>div>div,.stTextArea textarea{
  background:#0d1b3e!important;border:1px solid rgba(255,255,255,.2)!important;
  border-radius:8px!important;color:var(--txt)!important;
}

/* ═══ BUTTONS ═══ */
.stButton>button{
  background:linear-gradient(135deg,var(--bg-mid),var(--blue))!important;
  color:white!important;font-weight:700!important;border-radius:8px!important;
  border:1px solid rgba(46,117,182,.5)!important;transition:all .2s!important;
}
.stButton>button:hover{
  transform:translateY(-2px)!important;box-shadow:0 6px 18px rgba(46,117,182,.4)!important;
}
.stDownloadButton>button{
  background:linear-gradient(135deg,#16a34a,#15803d)!important;color:white!important;
  font-weight:700!important;border-radius:8px!important;
  border:1px solid rgba(34,197,94,.4)!important;
}

/* ═══ TABS ═══ */
.stTabs [data-baseweb="tab-list"]{
  background:var(--glass)!important;border:1px solid var(--glass-b)!important;
  border-radius:10px!important;padding:3px!important;gap:3px!important;
}
.stTabs [data-baseweb="tab"]{
  background:transparent!important;border-radius:7px!important;
  color:var(--muted)!important;font-weight:600!important;
  font-size:.82rem!important;padding:7px 14px!important;
  transition:all .2s!important;border:none!important;
}
.stTabs [aria-selected="true"]{
  background:linear-gradient(135deg,var(--bg-glow),var(--blue))!important;
  color:white!important;
}

/* ═══ BADGES ═══ */
.rem-badge{
  display:inline-block;padding:3px 12px;border-radius:16px;
  font-size:.78rem;font-weight:700;margin-top:4px;
}
.rb-cho{background:rgba(255,215,0,.15);border:1px solid rgba(255,215,0,.4);color:#ffd700;}
.rb-cfmc{background:rgba(168,85,247,.15);border:1px solid rgba(168,85,247,.4);color:#c084fc;}
.rb-si{background:rgba(0,212,255,.15);border:1px solid rgba(0,212,255,.4);color:#00d4ff;}
.rb-barrack{background:rgba(249,115,22,.15);border:1px solid rgba(249,115,22,.4);color:#fb923c;}
.rb-other{background:rgba(122,146,184,.1);border:1px solid rgba(122,146,184,.2);color:#7a92b8;}

/* ═══ DUPLICATE WARNING ═══ */
.dup-warn{
  background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.4);
  border-radius:10px;padding:12px 16px;margin:8px 0;
}
.new-mob-info{
  background:rgba(34,197,94,.08);border:1px solid rgba(34,197,94,.3);
  border-radius:10px;padding:12px 16px;margin:8px 0;
}

/* ═══ LOG ═══ */
.log-line{
  font-family:'Space Mono',monospace;font-size:.75rem;padding:4px 8px;
  border-radius:4px;margin:2px 0;background:rgba(0,0,0,.4);border-left:2px solid;
}
.log-ok{border-color:#22c55e;}.log-fail{border-color:#ef4444;}.log-work{border-color:#ffd700;}

/* ═══ MISC ═══ */
[data-testid="stDataFrame"]{border:1px solid var(--glass-b)!important;border-radius:10px!important;}
.clock-box{
  background:linear-gradient(135deg,var(--bg-deep),var(--bg-mid));border-radius:12px;
  padding:14px;text-align:center;border:1px solid rgba(0,212,255,.2);
  box-shadow:0 0 20px rgba(0,212,255,.1);
}
.clock-time{
  font-size:1.8rem;font-weight:700;color:var(--cyan);font-family:'Space Mono',monospace;
  letter-spacing:3px;text-shadow:0 0 16px rgba(0,212,255,.5);
}
.emp-card{
  background:linear-gradient(135deg,rgba(13,27,62,.97),rgba(26,45,90,.82));
  border-radius:18px;padding:24px 28px;margin-top:14px;
}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:var(--bg-deep)}
::-webkit-scrollbar-thumb{background:var(--bg-glow);border-radius:3px}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
#  PASSWORD — Clear login page
# ══════════════════════════════════════════════════════════════
def check_password():
    if st.session_state.get("auth"):
        return True

    st.markdown("""
<div class="login-wrap">
  <div style="font-size:3rem;margin-bottom:10px;filter:drop-shadow(0 0 12px rgba(0,212,255,.5));">🚨</div>
  <div class="login-title">साइबर क्राइम 1930</div>
  <div class="login-sub">ड्यूटी रोस्टर प्रणाली · v6.0</div>
</div>""", unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("""
<style>
/* Login specific overrides for clear visibility */
div[data-testid="stTextInput"] input {
  background: rgba(255,255,255,0.15) !important;
  color: #ffffff !important;
  font-size: 1.2rem !important;
  font-weight: 700 !important;
  letter-spacing: 6px !important;
  text-align: center !important;
  border: 2px solid rgba(0,212,255,0.5) !important;
  border-radius: 12px !important;
  padding: 14px !important;
}
div[data-testid="stTextInput"] input::placeholder {
  color: rgba(200,220,255,0.6) !important;
  letter-spacing: 3px !important;
  font-size: 0.9rem !important;
  font-weight: 400 !important;
}
div[data-testid="stTextInput"] label p {
  color: #c0d8f5 !important;
  font-size: 0.9rem !important;
  font-weight: 600 !important;
  letter-spacing: 1.5px !important;
  text-align: center !important;
}
</style>
""", unsafe_allow_html=True)
        pwd = st.text_input("🔐 पासवर्ड दर्ज करें", type="password",
                            key="pwd_in", placeholder="● ● ● ● ● ● ● ●")
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        if st.button("🔓 लॉगिन करें", use_container_width=True):
            if pwd == st.secrets["passwords"]["app_password"]:
                st.session_state["auth"] = True
                st.rerun()
            else:
                st.markdown("""
<div style="background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.4);
  border-radius:8px;padding:10px;text-align:center;color:#f87171;font-weight:600;margin-top:8px;">
  ❌ गलत पासवर्ड — पुनः प्रयास करें
</div>""", unsafe_allow_html=True)
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
    📅 {now.day} {HINDI_MONTHS[now.month]} {now.year} &nbsp;·&nbsp;
    ⏰ {now.strftime('%I:%M %p')} IST
  </div>
</div>""", unsafe_allow_html=True)


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
                mdf,_,_,_,adf,avdf = load_all_data()
                compute_master_stats(mdf, adf, avdf)
                load_all_data.clear()
                st.success("✅ Master stats अपडेट!")
            except Exception as e:
                st.error(f"Error: {e}")
    st.markdown("---")
    st.caption(f"PDF: {'✅' if PDF_AVAILABLE else '❌'} | OCR: {'✅' if OCR_AVAILABLE else '❌'}")
    st.caption("v6.0 — Master-First Logic ✅")


# ══════════════════════════════════════════════════════════════
#  LOAD DATA
# ══════════════════════════════════════════════════════════════
with st.spinner("डेटा लोड हो रहा है..."):
    try:
        master_df,shift1_df,shift2_df,shift3_df,audit_df,avkash_df = load_all_data()
    except Exception as e:
        st.error(f"❌ Sheet connect नहीं हुई: {e}")
        st.info("Sidebar में 'Sheets Setup' बटन दबाएं।")
        st.stop()

t_str         = today_str()
active_leaves = get_active_leaves(avkash_df)
master_lookup = get_master_lookup(master_df)

def get_latest_date_df(shift_df):
    ld = get_latest_shift_date(shift_df)
    if ld:
        return get_shift_for_date(shift_df, ld.strftime("%d-%m-%Y")), ld.strftime("%d-%m-%Y")
    return pd.DataFrame(columns=SHIFT_HEADERS), "—"

s1_latest_df, s1_date = get_latest_date_df(shift1_df)
s2_latest_df, s2_date = get_latest_date_df(shift2_df)
s3_latest_df, s3_date = get_latest_date_df(shift3_df)

total_karmchari = len(master_df)
duty_par        = len(s1_latest_df)+len(s2_latest_df)+len(s3_latest_df)
avkash_par      = len(active_leaves)

all_duty_mobs = set()
for df_ in [s1_latest_df, s2_latest_df, s3_latest_df]:
    if not df_.empty and "मो0न0" in df_.columns:
        all_duty_mobs.update(df_["मो0न0"].apply(clean_mobile).tolist())

nishkriya = cfmc_count = 0
if not master_df.empty and "मो0न0" in master_df.columns:
    for _, row in master_df.iterrows():
        mob = clean_mobile(row.get("मो0न0",""))
        if mob not in all_duty_mobs and mob not in active_leaves:
            nishkriya += 1
        if "CFMC" in str(row.get("REMARKS","")).upper():
            cfmc_count += 1


# ══════════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="sec-title">📊 सारांश डैशबोर्ड</div>', unsafe_allow_html=True)
cols_r1 = st.columns(4)
for col_,ic_,val_,lbl_,cls_ in [
    (cols_r1[0],"👥",total_karmchari,"कुल कर्मचारी","sc-blue"),
    (cols_r1[1],"✅",duty_par,"ड्यूटी पर","sc-green"),
    (cols_r1[2],"🌴",avkash_par,"अवकाश पर","sc-orange"),
    (cols_r1[3],"⏸️",nishkriya,"निष्क्रिय","sc-red"),
]:
    with col_:
        st.markdown(
            f'<div class="sum-card {cls_}"><span class="ic">{ic_}</span>'
            f'<div class="v">{val_}</div><div class="l">{lbl_}</div></div>',
            unsafe_allow_html=True)

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
cols_r2 = st.columns(4)
for col_,ic_,val_,lbl_,cls_ in [
    (cols_r2[0],"🟡",len(s1_latest_df),f"प्रथम पाली\n({s1_date})","sc-gold"),
    (cols_r2[1],"🟢",len(s2_latest_df),f"द्वितीय पाली\n({s2_date})","sc-green"),
    (cols_r2[2],"🔵",len(s3_latest_df),f"तृतीय पाली\n({s3_date})","sc-cyan"),
    (cols_r2[3],"🏢",cfmc_count,"CFMC कर्मचारी","sc-purple"),
]:
    with col_:
        st.markdown(
            f'<div class="sum-card {cls_}"><span class="ic">{ic_}</span>'
            f'<div class="v">{val_}</div>'
            f'<div class="l" style="white-space:pre-line">{lbl_}</div></div>',
            unsafe_allow_html=True)

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# Shift Display — Latest date ka data
st.markdown('<div class="sec-title">📋 वर्तमान पाली — नवीनतम तारीख</div>', unsafe_allow_html=True)
sc1, sc2, sc3 = st.columns(3)
for col_,df_,lbl_,hdr_cls,dt_,tab_name in [
    (sc1,s1_latest_df,"🟡 प्रथम पाली","sh-s1",s1_date,"Shift1"),
    (sc2,s2_latest_df,"🟢 द्वितीय पाली","sh-s2",s2_date,"Shift2"),
    (sc3,s3_latest_df,"🔵 तृतीय पाली","sh-s3",s3_date,"Shift3"),
]:
    with col_:
        st.markdown(f'<div class="shift-header {hdr_cls}">{lbl_} ({dt_})</div>',
                    unsafe_allow_html=True)
        if df_.empty:
            st.info("कोई data नहीं — PDF upload करें ↓")
        else:
            disp_cols = [c for c in ["नाम","पदनाम","REMARKS","मो0न0"] if c in df_.columns]
            st.dataframe(df_[disp_cols], use_container_width=True, hide_index=True, height=260)
            st.download_button(
                f"⬇️ {lbl_} Excel",
                data=df_to_excel(df_, tab_name),
                file_name=f"{tab_name}_{dt_}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key=f"dl_{tab_name}")

st.markdown("---")


# ══════════════════════════════════════════════════════════════
#  TABS
# ══════════════════════════════════════════════════════════════
tab_upload,tab_search,tab_master,tab_avkash,tab_audit,tab_debug = st.tabs([
    "📂 PDF/Image अपलोड","🔍 कर्मचारी खोज",
    "👥 Master Data","🌴 अवकाश","📜 Audit Log","🔧 Debug"
])


# ── TAB 1: PDF/IMAGE UPLOAD ───────────────────────────────────
with tab_upload:
    st.markdown('<div class="sec-title">🤖 Agentic PDF/Image अपलोड — v6.0</div>',
                unsafe_allow_html=True)

    st.markdown("""
<div style="background:rgba(46,117,182,.08);border:1px solid rgba(46,117,182,.3);
  border-radius:12px;padding:14px 18px;margin-bottom:16px;font-size:.85rem;line-height:2;">
<b style="color:#60a5fa;">🤖 v6.0 — Master-First Logic:</b><br>
&nbsp;✅ <b>AI केवल Mobile Number + CHO word</b> detect करता है<br>
&nbsp;✅ <b>नाम / पदनाम हमेशा Master Sheet से</b> आता है<br>
&nbsp;✅ <b>CFMC / बैरक</b> — PDF heading से automatically detect<br>
&nbsp;✅ <b>Duplicate check</b> — save से पहले दिखाएगा<br>
&nbsp;✅ <b>नया Mobile</b> → सिर्फ Master में जाएगा (नाम आप भरेंगे)<br>
&nbsp;✅ <b>AI tokens बचते हैं</b> — minimal AI use
</div>""", unsafe_allow_html=True)

    up_c1, up_c2, up_c3 = st.columns(3)
    with up_c1:
        sel_shift = st.selectbox(
            "📋 पाली चुनें",
            options=["Shift1","Shift2","Shift3"],
            format_func=lambda x: SHIFT_LABELS[x]+f" ({x})",
            key="sel_shift")
    with up_c2:
        upload_date = st.date_input("📅 तारीख", value=now_ist().date(), key="up_date")
    with up_c3:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        hist_mode = st.checkbox(
            "📚 Historical Mode", value=False, key="hist_mode",
            help="पुराना data — Shift sheet नहीं बदलेगी, केवल Audit में जाएगा")

    file_type = st.radio("📁 File Type", ["PDF", "Image (JPG/PNG)"],
                         horizontal=True, key="file_type_radio")

    uploaded_file = None
    if file_type == "PDF":
        uploaded_file = st.file_uploader("📄 Duty Roster PDF", type=["pdf"],
                                         key="pdf_upload")
    else:
        uploaded_file = st.file_uploader("🖼️ Duty Roster Image", type=["jpg","jpeg","png"],
                                         key="img_upload")

    # Session state
    if "parsed_result" not in st.session_state:
        st.session_state.parsed_result = None
    if "parsed_file_name" not in st.session_state:
        st.session_state.parsed_file_name = None

    if uploaded_file is not None:
        if st.session_state.parsed_file_name != uploaded_file.name:
            st.session_state.parsed_result = None

        if st.session_state.parsed_result is None:
            agent     = AgenticAI()
            file_bytes = uploaded_file.read()
            dinank_str = upload_date.strftime("%d-%m-%Y")

            with st.spinner("🔍 Mobile numbers extract हो रहे हैं..."):
                if file_type == "PDF":
                    data, err = agent.extract_from_pdf(file_bytes, sel_shift, dinank_str)
                else:
                    data, err = agent.extract_from_image(file_bytes, sel_shift, dinank_str)

                if err:
                    st.error(f"❌ {err}")
                elif data:
                    st.session_state.parsed_result    = data
                    st.session_state.parsed_result["dinank"] = (
                        data.get("dinank","") or dinank_str)
                    st.session_state.parsed_file_name = uploaded_file.name

            if agent.logs:
                with st.expander("🤖 Agent Activity Log"):
                    for lg in agent.logs:
                        css = ("log-ok" if "✅" in lg["status"] else
                               "log-fail" if "❌" in lg["status"] else "log-work")
                        st.markdown(
                            f'<div class="log-line {css}">'
                            f'<span style="color:var(--muted)">{lg["time"]}</span> '
                            f'<b>{lg["step"]}</b> {lg["status"]} '
                            f'<span style="color:var(--muted)">{lg["detail"]}</span></div>',
                            unsafe_allow_html=True)

    result = st.session_state.get("parsed_result")
    if result:
        staff_raw   = result.get("staff", [])
        final_date  = result.get("dinank", upload_date.strftime("%d-%m-%Y"))
        final_shift = sel_shift

        if not staff_raw:
            st.warning("⚠️ कोई mobile number नहीं मिला।")
        else:
            # Master se naam/padnaam fill karo
            final_rows, new_mobiles = prepare_staff_with_master(staff_raw, master_lookup)

            # Duplicate check
            sh_temp    = get_sheet()
            ws_temp    = sh_temp.worksheet(final_shift)
            dup_mobs   = check_duplicates_in_sheet(
                ws_temp, final_date, [r[0] for r in final_rows])

            # Summary display
            sections_summary = {}
            for s in staff_raw:
                stype = s.get("section_type", "Unknown")
                sections_summary[stype] = sections_summary.get(stype, 0) + 1

            sec_html = " | ".join(
                f"<b style='color:#ffd700'>{_html.escape(k)}</b>:{v}"
                for k, v in sections_summary.items())

            st.markdown(f"""
<div style="background:rgba(30,58,122,.5);border:1px solid rgba(96,165,250,.3);
  border-radius:12px;padding:16px;margin:12px 0;">
  <div style="font-weight:700;color:#e8f0ff;margin-bottom:8px;">
    📋 Parse Summary — {SHIFT_LABELS[final_shift]}
  </div>
  <div style="font-size:.85rem;color:#a0b8d8;">
    📱 <b style="color:#60a5fa">{len(final_rows)}</b> numbers मिले &nbsp;|&nbsp;
    📅 <b style="color:#4ade80">{final_date}</b> &nbsp;|&nbsp;
    📋 <b style="color:#ffd700">{SHIFT_LABELS[final_shift]}</b>
  </div>
  <div style="font-size:.78rem;color:var(--muted);margin-top:5px;">Sections → {sec_html}</div>
</div>""", unsafe_allow_html=True)

            # Duplicate warning
            if dup_mobs:
                dup_names = []
                for dm in dup_mobs:
                    if dm in master_lookup:
                        dup_names.append(f"{master_lookup[dm]['naam']} ({dm})")
                    else:
                        dup_names.append(dm)
                st.markdown(f"""
<div class="dup-warn">
  <b style="color:#f87171;">⚠️ {len(dup_mobs)} Duplicate मिले</b> — इस तारीख का data पहले से है:<br>
  <span style="color:#fca5a5;font-size:.85rem;">{', '.join(dup_names)}</span><br>
  <span style="color:#a0b8d8;font-size:.78rem;">Save करने पर ये entries फिर से add होंगी।
  अगर नहीं चाहते तो रुकें।</span>
</div>""", unsafe_allow_html=True)

            # New mobiles info
            if new_mobiles:
                st.markdown(f"""
<div class="new-mob-info">
  <b style="color:#4ade80;">➕ {len(new_mobiles)} नए Mobile Numbers</b> — Master में नहीं हैं:<br>
  <span style="color:#86efac;font-size:.85rem;">{', '.join(new_mobiles)}</span><br>
  <span style="color:#a0b8d8;font-size:.78rem;">
  Save करने पर ये Master Sheet में add हो जाएंगे — नाम/पदनाम आप बाद में भर सकते हैं।</span>
</div>""", unsafe_allow_html=True)

            # Preview table
            preview_data = []
            for mob, naam, padnaam, remarks in final_rows:
                is_dup = "⚠️ DUP" if mob in dup_mobs else ""
                is_new = "🆕 NEW" if mob in new_mobiles else ""
                preview_data.append({
                    "मोबाइल": mob,
                    "नाम":    naam or "— (Master में नहीं)",
                    "पदनाम":  padnaam or "—",
                    "REMARKS": remarks,
                    "Status":  is_dup or is_new or "✅",
                })
            st.dataframe(pd.DataFrame(preview_data),
                         use_container_width=True, hide_index=True, height=250)

            col_save, col_cancel = st.columns([1,1])
            with col_save:
                if st.button(f"💾 {SHIFT_LABELS[final_shift]} Save करें",
                             key="save_main"):
                    with st.spinner("💾 Save हो रहा है..."):
                        try:
                            if hist_mode:
                                # Historical — sirf Audit mein
                                sh_   = get_sheet()
                                ws_a_ = get_or_create_ws(sh_, TAB_AUDIT, AUDIT_HEADERS)
                                ws_m_ = sh_.worksheet(TAB_MASTER)
                                all_m_ = ws_m_.get_all_values()
                                ex_mob_ = set()
                                if len(all_m_) > 1:
                                    try:
                                        mi_ = all_m_[0].index("मो0न0")
                                        ex_mob_ = {clean_mobile(r[mi_])
                                                   for r in all_m_[1:] if mi_ < len(r)}
                                    except:
                                        pass
                                a_rows_ = []
                                nm_rows_ = []
                                for mob, naam, padnaam, remarks in final_rows:
                                    a_rows_.append([mob, naam, padnaam, remarks,
                                                    final_date, final_shift])
                                    if mob in new_mobiles and mob not in ex_mob_:
                                        nm_rows_.append([mob,"","","","","","","","",""])
                                        ex_mob_.add(mob)
                                if a_rows_:  append_rows_safe(ws_a_, a_rows_)
                                if nm_rows_: append_rows_safe(ws_m_, nm_rows_)
                                load_all_data.clear()
                                st.success(f"📚 Historical: {len(a_rows_)} records saved")
                            else:
                                count, new_count = save_shift_and_audit(
                                    final_shift, final_rows, final_date,
                                    master_lookup, new_mobiles)
                                st.success(
                                    f"✅ {count} कर्मचारी save हुए — "
                                    f"{SHIFT_LABELS[final_shift]} | {final_date}")
                                if new_count:
                                    st.info(
                                        f"➕ {new_count} नए mobile Master में add किए — "
                                        f"कृपया Master Tab में नाम/पदनाम भरें।")

                            st.session_state.parsed_result    = None
                            st.session_state.parsed_file_name = None
                            st.rerun()
                        except Exception as se:
                            st.error(f"❌ Save error: {se}")
            with col_cancel:
                if st.button("❌ रद्द करें", key="cancel_main"):
                    st.session_state.parsed_result    = None
                    st.session_state.parsed_file_name = None
                    st.rerun()


# ── TAB 2: EMPLOYEE SEARCH ────────────────────────────────────
with tab_search:
    st.markdown('<div class="sec-title">🔍 कर्मचारी खोज — मोबाइल नंबर से</div>',
                unsafe_allow_html=True)

    if "emp_result" not in st.session_state: st.session_state.emp_result = None
    if "emp_mob_q"  not in st.session_state: st.session_state.emp_mob_q  = ""

    sc_c1, sc_c2 = st.columns([2,1])
    with sc_c1:
        search_mob = st.text_input("📱 मोबाइल नंबर", placeholder="10 अंकों का नंबर...",
                                   max_chars=10, key="search_mob")
    with sc_c2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        srch_btn = st.button("🔍 खोजें", use_container_width=True, key="srch_btn")

    if search_mob and len(search_mob.strip()) >= 5 and search_mob.strip() in master_lookup:
        ml_info = master_lookup[search_mob.strip()]
        st.markdown(f"""<div style="background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.3);
  border-radius:8px;padding:8px 14px;display:inline-flex;align-items:center;gap:10px;">
  <span>✅</span>
  <span style="color:#4ade80;font-weight:700;">{_html.escape(ml_info['naam'])}</span>
  <span style="color:var(--muted);font-size:.82rem;">{_html.escape(ml_info['padnaam'])}</span>
  {remarks_badge(ml_info['remarks'])}
</div>""", unsafe_allow_html=True)

    if srch_btn and search_mob:
        mob_q = search_mob.strip()
        if not (mob_q.isdigit() and len(mob_q) == 10):
            st.warning("⚠️ 10 अंकों का सही नंबर दर्ज करें")
            st.session_state.emp_result = None
        else:
            emp, err = search_employee(mob_q, master_df, audit_df, avkash_df)
            if err:
                st.error(f"❌ {err}")
                st.session_state.emp_result = None
            else:
                st.session_state.emp_result = emp
                st.session_state.emp_mob_q  = mob_q

    emp = st.session_state.emp_result
    if emp:
        mob_q      = st.session_state.emp_mob_q
        on_leave   = mob_q in active_leaves
        cur_p      = emp["cur_pali"]
        pali_color = {"Shift1":"#ffd700","Shift2":"#4ade80","Shift3":"#60a5fa"}.get(cur_p,"#a0b8d8")

        st.markdown(f"""
<div class="emp-card" style="border:1px solid {pali_color}40;border-left:5px solid {pali_color};
  box-shadow:0 8px 30px {pali_color}20;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;
    gap:16px;flex-wrap:wrap;">
    <div>
      <div style="font-size:1.5rem;font-weight:800;font-family:'Rajdhani',sans-serif;
        color:#e8f0ff;margin-bottom:4px;">👤 {_html.escape(emp['naam'])}</div>
      <div style="font-size:.85rem;color:#7a92b8;margin-bottom:3px;">
        🏷️ {_html.escape(emp['padnaam'])}</div>
      <div style="font-size:.85rem;color:#7a92b8;">
        📱 <span style="font-family:'Space Mono',monospace;">{mob_q}</span></div>
      <div style="margin-top:8px;">{remarks_badge(emp['remarks'])}</div>
    </div>
    <div style="background:rgba(0,0,0,.4);border:1px solid {pali_color}40;
      border-radius:12px;padding:12px 20px;text-align:center;min-width:130px;">
      <div style="font-size:.65rem;color:var(--muted);text-transform:uppercase;
        letter-spacing:1px;margin-bottom:4px;">
        {"🌴 अवकाश पर" if on_leave else "अंतिम पाली"}</div>
      <div style="font-size:1rem;font-weight:700;color:{pali_color};">
        {SHIFT_LABELS.get(cur_p,cur_p) if cur_p else "—"}</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

        sc_counts = emp["shift_counts"]
        cards_h   = ""
        for sh_k,sh_l,clr_,bg_ in [
            ("Shift1","प्रथम पाली","#ffd700","rgba(255,215,0,.12)"),
            ("Shift2","द्वितीय पाली","#4ade80","rgba(34,197,94,.12)"),
            ("Shift3","तृतीय पाली","#60a5fa","rgba(96,165,250,.12)"),
        ]:
            cards_h += (
                f'<div style="flex:1;min-width:110px;background:{bg_};'
                f'border:1px solid {clr_}40;border-radius:12px;padding:14px 10px;text-align:center;">'
                f'<div style="font-family:\'Space Mono\',monospace;font-size:2rem;font-weight:700;'
                f'color:{clr_};">{sc_counts.get(sh_k,0)}</div>'
                f'<div style="font-size:.7rem;color:var(--muted);font-weight:600;">{sh_l}</div></div>')
        cards_h += (
            f'<div style="flex:1;min-width:110px;background:rgba(168,85,247,.1);'
            f'border:1px solid rgba(168,85,247,.3);border-radius:12px;padding:14px 10px;text-align:center;">'
            f'<div style="font-family:\'Space Mono\',monospace;font-size:2rem;font-weight:700;'
            f'color:#c084fc;">{emp["total_duty"]}</div>'
            f'<div style="font-size:.7rem;color:var(--muted);font-weight:600;">कुल ड्यूटी (2 माह)</div></div>'
            f'<div style="flex:1;min-width:110px;background:rgba(249,115,22,.08);'
            f'border:1px solid rgba(249,115,22,.3);border-radius:12px;padding:14px 10px;text-align:center;">'
            f'<div style="font-family:\'Space Mono\',monospace;font-size:2rem;font-weight:700;'
            f'color:#fb923c;">{emp["total_leave_days"]}</div>'
            f'<div style="font-size:.7rem;color:var(--muted);font-weight:600;">कुल अवकाश दिन</div></div>')

        st.markdown(f"""<div style="background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.07);
  border-radius:12px;padding:14px;margin-top:10px;">
  <div style="font-size:.72rem;color:var(--muted);margin-bottom:10px;font-weight:700;
    letter-spacing:1px;text-transform:uppercase;">📈 पाली सारांश (अंतिम 2 माह)</div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;">{cards_h}</div>
</div>""", unsafe_allow_html=True)

        if emp["history"]:
            rows_h = ""
            for row_ in emp["history"][:30]:
                d_  = _html.escape(str(row_.get("दिनांक","")))
                sh_ = str(row_.get("पाली",""))
                p_  = _html.escape(str(row_.get("पदनाम","")))
                r_  = str(row_.get("REMARKS",""))
                sc_ = {"Shift1":"#ffd700","Shift2":"#4ade80","Shift3":"#60a5fa"}.get(sh_,"#a0b8d8")
                rows_h += (
                    f"<tr style='border-bottom:1px solid rgba(255,255,255,.04)'>"
                    f"<td style='padding:6px 10px;color:#a0b8d8'>{d_}</td>"
                    f"<td style='padding:6px 10px'>"
                    f"<span style='background:rgba(0,0,0,.3);border-radius:6px;"
                    f"padding:2px 8px;color:{sc_};font-weight:700;font-size:.78rem'>"
                    f"{SHIFT_LABELS.get(sh_,sh_)}</span></td>"
                    f"<td style='padding:6px 10px;color:#4ade80;font-size:.8rem'>{p_}</td>"
                    f"<td style='padding:6px 10px'>{remarks_badge(r_)}</td></tr>")

            st.markdown(f"""<div style="background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.07);
  border-radius:12px;padding:14px;margin-top:10px;">
  <div style="font-size:.72rem;color:var(--muted);margin-bottom:8px;font-weight:700;
    text-transform:uppercase;letter-spacing:1px;">📅 ड्यूटी इतिहास</div>
  <div style="overflow-x:auto">
  <table style="width:100%;border-collapse:collapse;font-size:.82rem">
    <thead><tr style="background:rgba(255,255,255,.06)">
      <th style="padding:6px 10px;text-align:left;color:var(--muted)">📅 तारीख</th>
      <th style="padding:6px 10px;text-align:left;color:var(--muted)">🔄 पाली</th>
      <th style="padding:6px 10px;text-align:left;color:var(--muted)">🏷️ पदनाम</th>
      <th style="padding:6px 10px;text-align:left;color:var(--muted)">📌 REMARKS</th>
    </tr></thead>
    <tbody>{rows_h}</tbody>
  </table></div>
</div>""", unsafe_allow_html=True)

        for lv_ in emp["leaves"]:
            st.markdown(f"""<div style="background:rgba(249,115,22,.08);
  border:1px solid rgba(249,115,22,.25);border-radius:10px;padding:10px 14px;
  margin-top:6px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;font-size:.83rem;">
  <span style="color:#fb923c;font-weight:700;">
    {lv_.get('अवकाश से','—')} → {lv_.get('अवकाश तक','—')}</span>
  <span style="background:rgba(249,115,22,.2);border-radius:10px;padding:2px 8px;
    color:#fb923c;font-weight:700;">📅 {lv_.get('दिन',0)} दिन</span>
  <span style="color:#a0b8d8;">{lv_.get('कारण','—')}</span>
  <span style="color:#7a92b8;font-size:.75rem;">{lv_.get('स्थिति','')}</span>
</div>""", unsafe_allow_html=True)


# ── TAB 3: MASTER DATA ────────────────────────────────────────
with tab_master:
    st.markdown('<div class="sec-title">👥 Master Data</div>', unsafe_allow_html=True)
    if master_df.empty:
        st.info("Master Data खाली है।")
    else:
        ms_ = st.text_input("🔍 खोजें", placeholder="नाम / मोबाइल / REMARKS...",
                            key="ms_search")
        disp_m = master_df.copy()
        if ms_:
            mask = pd.Series([False]*len(disp_m), index=disp_m.index)
            for c in ["नाम","पदनाम","मो0न0","REMARKS","CURRENT पाली"]:
                if c in disp_m.columns:
                    mask |= disp_m[c].astype(str).str.contains(ms_, case=False, na=False)
            disp_m = disp_m[mask]
        st.dataframe(disp_m, use_container_width=True, hide_index=True, height=400)
        mc1,_ = st.columns([1,3])
        with mc1:
            st.download_button(
                "⬇️ Master Excel",
                data=df_to_excel(disp_m, "Master"),
                file_name=f"Master_{t_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
        st.caption(f"कुल: {len(disp_m)}")


# ── TAB 4: AVKASH ─────────────────────────────────────────────
with tab_avkash:
    st.markdown('<div class="sec-title">🌴 अवकाश प्रबंधन</div>', unsafe_allow_html=True)
    if not avkash_df.empty:
        st.dataframe(avkash_df, use_container_width=True, hide_index=True, height=260)
        av1,_ = st.columns([1,3])
        with av1:
            st.download_button(
                "⬇️ अवकाश Excel",
                data=df_to_excel(avkash_df, "Avkash"),
                file_name=f"Avkash_{t_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
    else:
        st.info("कोई अवकाश record नहीं।")

    st.markdown("---")
    st.markdown("**🌴 नया अवकाश दर्ज करें**")
    av_c1, av_c2 = st.columns([1,2])
    with av_c1:
        av_mob = st.text_input("📱 मोबाइल नं. *", key="av_mob", max_chars=10)

    av_naam = av_pad = ""
    if av_mob and len(av_mob.strip()) == 10 and av_mob.strip().isdigit():
        mob_k = av_mob.strip()
        if mob_k in master_lookup:
            av_naam = master_lookup[mob_k]["naam"]
            av_pad  = master_lookup[mob_k]["padnaam"]
            with av_c2:
                st.markdown(f"""<div style="background:rgba(34,197,94,.1);
  border:1px solid rgba(34,197,94,.3);border-radius:8px;padding:10px 14px;
  display:flex;gap:12px;align-items:center;">
  <span>✅</span><div>
    <div style="color:#4ade80;font-weight:700;">{_html.escape(av_naam)}</div>
    <div style="color:var(--muted);font-size:.8rem;">{_html.escape(av_pad)}</div>
  </div></div>""", unsafe_allow_html=True)
        else:
            with av_c2:
                st.warning("⚠️ Master में नहीं मिला")

    vc1, vc2, vc3 = st.columns(3)
    with vc1:
        av_naam_inp = st.text_input("नाम",   key="av_naam", value=av_naam)
        av_pad_inp  = st.text_input("पदनाम", key="av_pad",  value=av_pad)
    with vc2:
        av_from = st.date_input("📅 अवकाश से", key="av_from", value=now_ist().date())
        av_to   = st.date_input("📅 अवकाश तक", key="av_to",   value=now_ist().date())
    with vc3:
        av_karan = st.text_input("कारण", key="av_karan")
        av_days  = (av_to-av_from).days+1 if av_to >= av_from else 0
        st.info(f"📅 कुल: {av_days} दिन")

    if st.button("✅ अवकाश सहेजें", key="save_av"):
        fn = av_naam_inp.strip() or av_naam
        fm = av_mob.strip() if av_mob else ""
        if fm and fn:
            try:
                save_avkash(fm, fn, av_pad_inp.strip() or av_pad,
                            av_from.strftime("%d-%m-%Y"), av_to.strftime("%d-%m-%Y"),
                            av_karan, av_days)
                st.success(f"✅ {fn} — {av_days} दिन अवकाश दर्ज!")
                st.rerun()
            except Exception as ae:
                st.error(f"Error: {ae}")
        else:
            st.warning("मोबाइल नं. और नाम जरूरी है।")


# ── TAB 5: AUDIT LOG ─────────────────────────────────────────
with tab_audit:
    st.markdown('<div class="sec-title">📜 Audit Log</div>', unsafe_allow_html=True)
    if audit_df.empty:
        st.info("Audit Log खाली है।")
    else:
        ac1, ac2, ac3 = st.columns(3)
        with ac1: audit_date_f  = st.text_input("तारीख", placeholder="DD-MM-YYYY", key="aud_dt")
        with ac2: audit_shift_f = st.selectbox("पाली", ["सभी","Shift1","Shift2","Shift3"], key="aud_sh")
        with ac3: audit_naam_f  = st.text_input("नाम खोजें", key="aud_nm")

        a_df = audit_df.copy()
        if audit_date_f and "दिनांक" in a_df.columns:
            a_df = a_df[a_df["दिनांक"].astype(str).str.contains(audit_date_f, na=False)]
        if audit_shift_f != "सभी" and "पाली" in a_df.columns:
            a_df = a_df[a_df["पाली"] == audit_shift_f]
        if audit_naam_f and "नाम" in a_df.columns:
            a_df = a_df[a_df["नाम"].astype(str).str.contains(audit_naam_f, case=False, na=False)]

        st.dataframe(a_df, use_container_width=True, hide_index=True, height=400)
        al1,_ = st.columns([1,3])
        with al1:
            st.download_button(
                "⬇️ Audit Excel",
                data=df_to_excel(a_df, "Audit_Log"),
                file_name=f"Audit_{t_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
        st.caption(f"कुल records: {len(a_df)}")


# ── TAB 6: DEBUG ──────────────────────────────────────────────
with tab_debug:
    st.markdown("### 🔧 Debug Panel v6.0")
    try:
        st.success(f"✅ Secrets keys: {list(st.secrets.keys())}")
    except Exception as e:
        st.error(f"Secrets error: {e}")

    for kn in ["GROQ_API_KEY","DEEPSEEK_API_KEY","GEMINI_API_KEY","passwords","gcp_service_account"]:
        try:
            val = st.secrets.get(kn, None)
            if val:
                st.success(f"✅ {kn}: {'...' if isinstance(val,str) else 'dict'}")
            else:
                st.error(f"❌ {kn}: नहीं मिली")
        except Exception as e:
            st.error(f"❌ {kn}: {e}")

    st.markdown("---")
    st.markdown("**🔍 Mobile Regex Test**")
    test_text = st.text_area("Test Text paste करें:", height=100, key="debug_text")
    if test_text:
        agent_test = AgenticAI()
        mobs = agent_test.extract_mobiles_directly(test_text)
        sections = agent_test.parse_sections_from_text(test_text)
        st.write(f"**Mobiles found ({len(mobs)}):** {mobs}")
        st.write(f"**Sections:** {sections}")

    st.markdown("---")
    st.markdown("**📊 Data Summary**")
    st.write(f"Master: {len(master_df)} rows | Audit: {len(audit_df)} rows")
    st.write(f"Shift1: {len(shift1_df)} | Shift2: {len(shift2_df)} | Shift3: {len(shift3_df)}")
    st.write(f"Shift1 latest: {s1_date} ({len(s1_latest_df)} rows)")
    st.write(f"Shift2 latest: {s2_date} ({len(s2_latest_df)} rows)")
    st.write(f"Shift3 latest: {s3_date} ({len(s3_latest_df)} rows)")


# ── FOOTER ────────────────────────────────────────────────────
st.markdown(f"""
<div style="text-align:center;color:var(--muted);font-size:.72rem;padding:14px;
  border-top:1px solid rgba(255,255,255,.07);margin-top:24px;">
  🚨 साइबर क्राइम हेल्पलाइन <b>1930</b> &nbsp;|&nbsp;
  ड्यूटी रोस्टर v6.0 &nbsp;|&nbsp;
  <span class="live-dot"></span>
  {now_ist().strftime('%d-%m-%Y %H:%M')} IST &nbsp;|&nbsp;
  Master-First Logic ✅
</div>""", unsafe_allow_html=True)

if __name__ == "__main__":
    pass
