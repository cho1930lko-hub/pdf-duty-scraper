══════════════════════════════════════════════════════════════
  DUTY ROSTER AGENTIC AI — SETUP GUIDE
══════════════════════════════════════════════════════════════

📁 FOLDER STRUCTURE
─────────────────────
your_project/
├── duty_roster_agentic.py    ← main app
├── requirements.txt
└── .streamlit/
    └── secrets.toml          ← API keys (NEVER commit to git!)


🔑 SECRETS.TOML (.streamlit/secrets.toml)
──────────────────────────────────────────
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "xxxx"
private_key = "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n"
client_email = "your-sa@your-project.iam.gserviceaccount.com"
client_id = "xxxx"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"

GROQ_API_KEY    = "gsk_xxxx"
DEEPSEEK_API_KEY = "sk-xxxx"
GEMINI_API_KEY   = "AIzaxxxx"


📋 GOOGLE SHEET STRUCTURE
──────────────────────────
Sheet name: "Duty_Roster"

Tab 1 — Master:
  A: Mobile Number | B: Employee Name | C: Position | D: Department

Tab 2 — Audit_Log:
  A: Timestamp | B: Date/Dinank | C: Mobile Number | D: Name | E: Position | F: Shift/Column Detail

Tab 3 — Avkash:
  A: Timestamp | B: Mobile Number | C: Name | D: Position | E: From Date | F: To Date | G: Reason


🚀 RUN COMMANDS
────────────────
# Install dependencies
pip install -r requirements.txt

# Install Tesseract OCR (system-level)
# Ubuntu/Debian:
sudo apt-get install tesseract-ocr tesseract-ocr-hin

# macOS:
brew install tesseract tesseract-lang

# Run app
streamlit run duty_roster_agentic.py


🔒 SECURITY CHECKLIST
──────────────────────
✅ secrets.toml को .gitignore में add करें
✅ Service account को सिर्फ जरूरी sheets का access दें
✅ API keys को rotate करते रहें
✅ Streamlit Cloud पर deploy करते समय Secrets section use करें


🤖 AGENTIC FLOW DIAGRAM
────────────────────────
User uploads file
       ↓
AgenticAI.process_file()
       ↓
decide_strategy()  →  "ocr_only" OR "ai_extraction"
       ↓
Extract text  →  _call_groq()
                    ↓ (fail)
               _call_deepseek()
                    ↓ (fail)
               _call_gemini()
       ↓
_lookup_master()  →  Auto-fill name/position
       ↓
audit_ws.append_row()  →  Audit_Log में write
       ↓
UI में summary + agent log दिखाएं
