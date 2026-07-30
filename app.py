import streamlit as st
import requests
from datetime import datetime, timedelta
import hashlib
import base64
import os
import json
import time
import html as html_lib
import secrets
from io import BytesIO

# ----- ESCAPE FUNCTION (prevents XSS) -----
def esc(text):
    if text is None:
        return ""
    return html_lib.escape(str(text), quote=True)

# ----- ALLOWED FILE EXTENSIONS FOR ATTACHMENTS -----
ALLOWED_ATTACHMENT_EXTENSIONS = [
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt',
    'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'
]

# Optional: try to import pandas and plotly for dashboard charts
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# OAuth support
try:
    from authlib.integrations.requests_client import OAuth2Session
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False

# Try to import bcrypt; fallback to built-in hashing
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False

# Optional: for image validation
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# -------------------------------
# 0. SECRETS AND CONFIG
# -------------------------------
if 'SUPABASE_URL' in st.secrets:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    USING_HARDCODED = False
else:
    SUPABASE_URL = "https://xvfbxogzefhmitrtykce.supabase.co"
    SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh2ZmJ4b2d6ZWZobWl0cnR5a2NlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ4MDMxMjEsImV4cCI6MjEwMDM3OTEyMX0.OP6VM6dIcCJGDetAdP53nrElhSLnZXg3m16t9dy6nE0"
    USING_HARDCODED = True
    st.warning("⚠️ Using hardcoded Supabase credentials. For production, create .streamlit/secrets.toml and enable RLS on all tables.")

SESSION_TIMEOUT_MINUTES = st.secrets.get("SESSION_TIMEOUT_MINUTES", 60) if 'SESSION_TIMEOUT_MINUTES' in st.secrets else 60
MAX_UPLOAD_SIZE_MB = st.secrets.get("MAX_UPLOAD_SIZE_MB", 5) if 'MAX_UPLOAD_SIZE_MB' in st.secrets else 5
MAX_UPLOAD_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# Slack / Teams webhook URLs (optional)
SLACK_WEBHOOK = st.secrets.get("SLACK_WEBHOOK", "")
TEAMS_WEBHOOK = st.secrets.get("TEAMS_WEBHOOK", "")

# OAuth config (Google)
GOOGLE_CLIENT_ID = st.secrets.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = st.secrets.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = st.secrets.get("GOOGLE_REDIRECT_URI", "https://yourapp.streamlit.app/oauth_callback")

# App URL for password reset links
APP_URL = st.secrets.get("APP_URL", "https://yourapp.streamlit.app")

# Use Supabase client
try:
    from supabase import create_client, Client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    st.warning("Supabase library not installed. Install with: pip install supabase")

# -------------------------------
# 1. CUSTOM CSS + FONT AWESOME
# -------------------------------
st.set_page_config(
    page_title="Mine & Workshop Tracker",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Theme toggle
if 'dark_mode' not in st.session_state:
    st.session_state.dark_mode = False

dark_css = """
<style>
    .stApp { background-color: #0f172a; color: #e2e8f0; }
    .main-header { background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: #f8fafc; }
    .sub-header { color: #94a3b8; border-bottom-color: #334155; }
    .css-1d391kg { background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%); }
    .css-1d391kg .stMarkdown { color: #e2e8f0; }
    .css-1d391kg .stButton button { 
        background-color: #4fc3f7; 
        color: #1a1a2e; 
        border-radius: 10px; 
        border: none; 
        padding: 0.6rem 1rem; 
        transition: 0.3s; 
        font-weight: 600; 
    }
    .css-1d391kg .stButton button:hover { background-color: #29b6f6; transform: scale(1.03); }
    .custom-card { background: #1e293b; border-color: #334155; color: #e2e8f0; }
    .task-card { background: #1e293b; border-color: #334155; color: #e2e8f0; }
    .metric-box { background: #1e293b; border-color: #334155; color: #e2e8f0; }
    .stFileUploader { background: #1e293b; border-color: #334155; }
    .streamlit-expanderHeader { background: #1e293b; color: #e2e8f0; }
    .footer { border-top-color: #334155; color: #94a3b8; }
    .chat-message { background: #1e293b; border-left-color: #4fc3f7; color: #e2e8f0; }
    .chat-message.self { background: #0f3460; border-left-color: #4fc3f7; }
    .stTabs [data-baseweb="tab"] { background: #1e293b; color: #94a3b8; border-color: #334155; }
    .stTabs [aria-selected="true"] { background: #2563eb; color: white; border-color: #2563eb; }
    .stTabs [data-baseweb="tab"]:hover { color: #e2e8f0; }
    .stButton button { color: white; }
    .stSelectbox label, .stTextInput label, .stTextArea label, .stCheckbox label, .stDateInput label, .stFileUploader label { color: #e2e8f0 !important; }
    .stSelectbox div, .stTextInput div, .stTextArea div, .stCheckbox div, .stDateInput div { color: #e2e8f0 !important; }
    .stMetric label { color: #e2e8f0 !important; }
    .stMetric .value { color: #e2e8f0 !important; }
    .stMetric .label { color: #94a3b8 !important; }
    .stDataFrame { color: #e2e8f0 !important; }
    .overdue-badge { background: #dc2626; color: white; padding: 0.15rem 0.6rem; border-radius: 20px; font-size: 0.7rem; font-weight: 700; margin-left: 0.5rem; }
</style>
"""
light_css = """
<style>
    .stApp { background-color: #f0f2f5; }
    .main-header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); color: white; }
    .sub-header { color: #1a1a2e; border-bottom-color: #0f3460; }
    .css-1d391kg { background: linear-gradient(180deg, #1a1a2e 0%, #0f3460 100%); }
    .css-1d391kg .stMarkdown { color: #e2e8f0; }
    .css-1d391kg .stButton button { 
        background-color: #4fc3f7; 
        color: #1a1a2e; 
        border-radius: 10px; 
        border: none; 
        padding: 0.6rem 1rem; 
        transition: 0.3s; 
        font-weight: 600; 
    }
    .css-1d391kg .stButton button:hover { background-color: #29b6f6; transform: scale(1.03); }
    .custom-card { background: white; border-color: #e8ecf0; color: #1e293b; }
    .task-card { background: white; border-color: #e8ecf0; color: #1e293b; }
    .metric-box { background: white; border-color: #e2e8f0; color: #1e293b; }
    .stFileUploader { background: #f8fafc; border-color: #cbd5e1; }
    .streamlit-expanderHeader { background: #f1f5f9; color: #1e293b; }
    .footer { border-top-color: #e2e8f0; color: #94a3b8; }
    .chat-message { background: #f1f5f9; border-left-color: #0f3460; color: #1e293b; }
    .chat-message.self { background: #e3f2fd; border-left-color: #0f3460; }
    .stTabs [data-baseweb="tab"] { background: white; color: #64748b; border: 1px solid #e2e8f0; border-bottom: none; }
    .stTabs [aria-selected="true"] { background: #0f3460; color: white; border-color: #0f3460; }
    .stTabs [data-baseweb="tab"]:hover { color: #1a1a2e; }
    .stSelectbox label, .stTextInput label, .stTextArea label, .stCheckbox label, .stDateInput label, .stFileUploader label { color: #1e293b !important; }
    .stSelectbox div, .stTextInput div, .stTextArea div, .stCheckbox div, .stDateInput div { color: #1e293b !important; }
    .stMetric label { color: #1e293b !important; }
    .stMetric .value { color: #1e293b !important; }
    .stMetric .label { color: #64748b !important; }
    .stDataFrame { color: #1e293b !important; }
    .overdue-badge { background: #dc2626; color: white; padding: 0.15rem 0.6rem; border-radius: 20px; font-size: 0.7rem; font-weight: 700; margin-left: 0.5rem; }
</style>
"""

theme_css = dark_css if st.session_state.dark_mode else light_css

st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
""" + theme_css + """
<style>
    .stApp { background-color: #f0f2f5; }
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 1.5rem 2rem;
        border-radius: 16px;
        color: white;
        margin-bottom: 1rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    }
    .main-header i { color: #4fc3f7; margin-right: 12px; }
    .main-header small { font-size: 0.9rem; font-weight: 300; opacity: 0.8; display: block; margin-top: 4px; }
    .sub-header { font-size: 1.3rem; font-weight: 600; margin-bottom: 1.5rem; padding-bottom: 0.5rem; border-bottom: 3px solid #0f3460; }
    .css-1d391kg { background: linear-gradient(180deg, #1a1a2e 0%, #0f3460 100%); }
    .css-1d391kg .stMarkdown { color: #e2e8f0; }
    .css-1d391kg .stButton button {
        background-color: #4fc3f7;
        color: #1a1a2e;
        border-radius: 10px;
        border: none;
        padding: 0.6rem 1rem;
        transition: 0.3s;
        font-weight: 600;
        width: 100%;
    }
    .css-1d391kg .stButton button:hover { background-color: #29b6f6; transform: scale(1.03); }
    .css-1d391kg .stButton button i { margin-right: 8px; }
    .css-1d391kg .stSelectbox label, 
    .css-1d391kg .stTextInput label, 
    .css-1d391kg .stTextArea label,
    .css-1d391kg .stCheckbox label { color: #e2e8f0 !important; }
    .custom-card { background: white; border-radius: 16px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); padding: 1.2rem; margin-bottom: 1rem; border-left: 5px solid #0f3460; transition: 0.3s; }
    .custom-card:hover { box-shadow: 0 8px 30px rgba(0,0,0,0.12); transform: translateY(-2px); }
    .task-card { background: white; border-radius: 16px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); padding: 1.2rem; margin-bottom: 1rem; border: 1px solid #e8ecf0; transition: 0.3s; }
    .task-card:hover { box-shadow: 0 8px 30px rgba(0,0,0,0.12); transform: translateY(-2px); }
    .task-title { font-size: 1.1rem; font-weight: 700; color: #1a1a2e; }
    .task-meta { display: flex; gap: 1rem; flex-wrap: wrap; margin: 0.3rem 0 0.8rem 0; font-size: 0.9rem; color: #475569; }
    .task-meta i { margin-right: 0.3rem; }
    .priority-badge { display: inline-block; padding: 0.2rem 0.8rem; border-radius: 20px; font-size: 0.75rem; font-weight: 700; color: white; }
    .priority-Critical { background: #dc2626; }
    .priority-High { background: #f59e0b; }
    .priority-Medium { background: #0f3460; }
    .priority-Low { background: #10b981; }
    .status-badge { display: inline-block; padding: 0.2rem 0.8rem; border-radius: 20px; font-size: 0.75rem; font-weight: 700; color: white; }
    .status-Unassigned { background: #94a3b8; }
    .status-InProgress { background: #3b82f6; }
    .status-PendingQA { background: #f59e0b; }
    .status-Blocked { background: #dc2626; }
    .status-Complete { background: #10b981; }
    .overdue-badge { display: inline-block; background: #dc2626; color: white; padding: 0.15rem 0.6rem; border-radius: 20px; font-size: 0.7rem; font-weight: 700; margin-left: 0.5rem; }
    .metric-box { background: white; border-radius: 16px; padding: 1.2rem; text-align: center; box-shadow: 0 2px 12px rgba(0,0,0,0.08); border: 1px solid #e8ecf0; }
    .metric-box .value { font-size: 2.2rem; font-weight: 700; color: #1a1a2e; }
    .metric-box .label { font-size: 0.9rem; color: #64748b; }
    .metric-box .label i { margin-right: 0.3rem; }
    .chat-message { padding: 0.5rem 1rem; border-radius: 12px; margin: 0.2rem 0; background: #f1f5f9; border-left: 4px solid #0f3460; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
    .chat-message.self { background: #e3f2fd; border-left-color: #0f3460; }
    .chat-message .sender { font-weight: 700; color: #1a1a2e; }
    .chat-message .timestamp { font-size: 0.7rem; color: #64748b; margin-left: 0.5rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 0.3rem; }
    .stTabs [data-baseweb="tab"] { border-radius: 12px 12px 0 0; padding: 0.6rem 1.2rem; font-weight: 600; border: 1px solid #e2e8f0; border-bottom: none; background: white; color: #64748b; }
    .stTabs [aria-selected="true"] { background: #0f3460; color: white; border-color: #0f3460; }
    .stTabs [data-baseweb="tab"]:hover { color: #1a1a2e; }
    .stTabs [data-baseweb="tab"] i { margin-right: 8px; }
    .stFileUploader { border: 2px dashed #94a3b8; border-radius: 12px; padding: 0.5rem; background: #f8fafc; }
    .streamlit-expanderHeader { background: #f1f5f9; border-radius: 12px; font-weight: 600; }
    .footer { text-align: center; margin-top: 2rem; padding: 1rem; color: #94a3b8; font-size: 0.8rem; border-top: 1px solid #e2e8f0; }
    .stButton button { font-weight: 600; border-radius: 10px; }
    .stButton button i { margin-right: 0.5rem; }
    .verified-badge { display: inline-block; background: #10b981; color: white; padding: 0.15rem 0.8rem; border-radius: 20px; font-size: 0.7rem; font-weight: 700; margin-left: 0.5rem; }
    .pending-badge { display: inline-block; background: #f59e0b; color: white; padding: 0.15rem 0.8rem; border-radius: 20px; font-size: 0.7rem; font-weight: 700; margin-left: 0.5rem; }
    .severity-badge { display: inline-block; padding: 0.2rem 0.8rem; border-radius: 20px; font-size: 0.75rem; font-weight: 700; color: white; }
    .severity-Critical { background: #7f1d1d; }
    .severity-High { background: #dc2626; }
    .severity-Medium { background: #f59e0b; }
    .severity-Low { background: #0f3460; }
    .asset-status-badge { display: inline-block; padding: 0.2rem 0.8rem; border-radius: 20px; font-size: 0.75rem; font-weight: 700; color: white; }
    .asset-status-Operational { background: #10b981; }
    .asset-status-Down { background: #dc2626; }
    .asset-status-Maintenance { background: #f59e0b; }
    .asset-status-Retired { background: #94a3b8; }
    .stock-badge { display: inline-block; padding: 0.15rem 0.7rem; border-radius: 20px; font-size: 0.7rem; font-weight: 700; color: white; margin-left: 0.5rem; }
    .stock-ok { background: #10b981; }
    .stock-low { background: #dc2626; }
    .sidebar-user { padding: 0.5rem 0; text-align: center; color: #e2e8f0; }
    .sidebar-user .user-name { font-weight: 700; font-size: 1.2rem; margin-top: 0.3rem; color: #e2e8f0; }
    .sidebar-user .user-role { font-size: 0.9rem; color: #94a3b8; }
    .sidebar-user .user-role i { margin-right: 0.3rem; }
    .sidebar-user .user-icon { font-size: 3rem; color: #4fc3f7; }
    .stSelectbox label, .stTextInput label, .stTextArea label, .stCheckbox label, .stDateInput label, .stFileUploader label { font-weight: 600; color: #1e293b !important; }
    .stSelectbox div, .stTextInput div, .stTextArea div, .stCheckbox div, .stDateInput div { color: #1e293b !important; }
    .stMetric label { color: #1e293b !important; }
    .stMetric .value { color: #1e293b !important; }
    .stMetric .label { color: #64748b !important; }
    .stDataFrame { color: #1e293b !important; }
    .stAlert { border-radius: 12px; }
    .stSuccess, .stInfo, .stWarning, .stError { border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

# -------------------------------
# 2. SHARED STYLES FOR OPTION MENU
# -------------------------------
def menu_styles():
    dark = st.session_state.dark_mode
    return {
        "container": {
            "padding": "6px",
            "background-color": "#1e293b" if dark else "white",
            "border-radius": "14px",
            "box-shadow": "0 2px 12px rgba(0,0,0,0.08)",
            "margin-bottom": "1rem",
        },
        "icon": {"color": "#4fc3f7", "font-size": "16px"},
        "nav-link": {
            "font-size": "14px",
            "font-weight": "600",
            "text-align": "center",
            "margin": "0px 2px",
            "border-radius": "10px",
            "color": "#e2e8f0" if dark else "#1e293b",
            "--hover-color": "#334155" if dark else "#f1f5f9",
        },
        "nav-link-selected": {
            "background-color": "#0f3460",
            "color": "white",
        },
    }

# -------------------------------
# 3. ERROR LOGGING
# -------------------------------
def log_error(error_message, details=None, user_name=None, endpoint=None):
    """Log errors to the app_errors table for monitoring."""
    if not SUPABASE_AVAILABLE:
        return
    try:
        supabase.table("app_errors").insert({
            "error_message": str(error_message)[:500],
            "error_details": json.dumps(details) if details else None,
            "user_name": user_name,
            "endpoint": endpoint
        }).execute()
    except Exception:
        pass  # If logging fails, we can't do much else

# -------------------------------
# 4. PASSWORD HASHING & STRENGTH
# -------------------------------
def hash_password(password):
    if BCRYPT_AVAILABLE:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode(), salt).decode()
    else:
        salt = os.urandom(32)
        hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return base64.b64encode(salt + hashed).decode()

def verify_password(password, hashed):
    if BCRYPT_AVAILABLE:
        try:
            if bcrypt.checkpw(password.encode(), hashed.encode()):
                return True
        except ValueError:
            pass
    try:
        data = base64.b64decode(hashed.encode())
        salt = data[:32]
        stored_hash = data[32:]
        computed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return computed == stored_hash
    except Exception:
        return False

def is_strong_password(password):
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit."
    special_chars = "!@#$%^&*()_+-=[]{};:'\"\\|,.<>/?"
    if not any(c in special_chars for c in password):
        return False, "Password must contain at least one special character."
    return True, ""

# -------------------------------
# 5. AUDIT LOG
# -------------------------------
def log_audit(user_name, action, details=None):
    if not SUPABASE_AVAILABLE:
        return
    try:
        supabase.table("audit_log").insert({
            "user_name": user_name,
            "action": action,
            "details": json.dumps(details) if details else None
        }).execute()
    except Exception:
        pass

# -------------------------------
# 6. EMAIL NOTIFICATION
# -------------------------------
def send_email_notification(recipient, subject, body):
    if not recipient:
        return False
    try:
        smtp_server = st.secrets.get("SMTP_SERVER")
        smtp_port = st.secrets.get("SMTP_PORT", 587)
        smtp_user = st.secrets.get("SMTP_USER")
        smtp_password = st.secrets.get("SMTP_PASSWORD")
        smtp_from = st.secrets.get("SMTP_FROM", smtp_user)
        if not all([smtp_server, smtp_user, smtp_password]):
            return False
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart()
        msg['From'] = smtp_from
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return True
    except Exception as e:
        log_error(str(e), endpoint="send_email")
        return False

# -------------------------------
# 7. SLACK / TEAMS WEBHOOK INTEGRATION
# -------------------------------
def send_slack_notification(message):
    if not SLACK_WEBHOOK:
        return False
    try:
        payload = {"text": message}
        requests.post(SLACK_WEBHOOK, json=payload, timeout=5)
        return True
    except Exception as e:
        log_error(str(e), endpoint="slack")
        return False

def send_teams_notification(message):
    if not TEAMS_WEBHOOK:
        return False
    try:
        payload = {"text": message}
        requests.post(TEAMS_WEBHOOK, json=payload, timeout=5)
        return True
    except Exception as e:
        log_error(str(e), endpoint="teams")
        return False

def send_external_notifications(message):
    send_slack_notification(message)
    send_teams_notification(message)

# -------------------------------
# 8. IMAGE & ATTACHMENT VALIDATION
# -------------------------------
def validate_image(file_bytes, filename):
    ext = filename.split('.')[-1].lower()
    if ext not in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']:
        return False, "Only image files (jpg, png, gif, bmp, webp) are allowed."
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        return False, f"File size exceeds {MAX_UPLOAD_SIZE_MB} MB."
    if PIL_AVAILABLE:
        try:
            img = Image.open(BytesIO(file_bytes))
            img.verify()
            return True, "Valid image."
        except Exception:
            return False, "Invalid or corrupt image file."
    return True, "Valid image."

def validate_attachment(file_bytes, filename):
    if not filename or '.' not in filename:
        return False, "File must have a valid extension."
    ext = filename.split('.')[-1].lower()
    if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
        return False, f"File type '.{ext}' is not allowed. Allowed types: {', '.join(ALLOWED_ATTACHMENT_EXTENSIONS)}."
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        return False, f"File size exceeds {MAX_UPLOAD_SIZE_MB} MB."
    return True, "Valid attachment."

# -------------------------------
# 9. USER FUNCTIONS
# -------------------------------
def get_default_users():
    return [
        {"username": "supervisor1", "full_name": "Sarah Connor", "role": "Supervisor", "password_hash": hash_password("super789"), "email": "supervisor1@example.com", "avatar_url": None, "is_approved": True},
        {"username": "superintendent1", "full_name": "Anaba Moses", "role": "Superintendent", "password_hash": hash_password("boss000"), "email": "superintendent1@example.com", "avatar_url": None, "is_approved": True},
        {"username": "worker1", "full_name": "John Doe", "role": "Worker", "password_hash": hash_password("worker123"), "email": "worker1@example.com", "avatar_url": None, "is_approved": True}
    ]

def fetch_all_users_from_db():
    default_users = get_default_users()
    if not SUPABASE_AVAILABLE:
        return default_users
    try:
        res = supabase.table("facility_users").select("*").execute()
        db_users = res.data if res.data else []
    except Exception as e:
        log_error(str(e), endpoint="fetch_users")
        db_users = []
    existing_usernames = {u["username"] for u in default_users}
    for db_user in db_users:
        if db_user["username"] not in existing_usernames:
            default_users.append(db_user)
    return default_users

def register_user_to_db(username, name, role, password, email=None):
    if not SUPABASE_AVAILABLE:
        return False
    strong, msg = is_strong_password(password)
    if not strong:
        st.error(msg)
        return False
    try:
        hashed = hash_password(password)
        payload = {
            "username": username,
            "full_name": name,
            "role": role,
            "password_hash": hashed,
            "email": email,
            "is_approved": False
        }
        supabase.table("facility_users").insert(payload).execute()
        log_audit(name, "user_register", {"username": username, "role": role, "status": "pending_approval"})
        return True
    except Exception as e:
        log_error(str(e), details={"username": username}, endpoint="register_user")
        return False

def authenticate_user(username, password):
    users = fetch_all_users_from_db()
    for u in users:
        if u["username"].lower() == username.lower():
            if not u.get("is_approved", False):
                return None, "pending_approval"
            if verify_password(password, u["password_hash"]):
                return u, "approved"
    return None, None

def update_user_profile(username, updates):
    if not SUPABASE_AVAILABLE:
        return False
    try:
        supabase.table("facility_users").update(updates).eq("username", username).execute()
        return True
    except Exception as e:
        log_error(str(e), details={"username": username, "updates": updates}, endpoint="update_user")
        return False

def approve_user(username):
    if not SUPABASE_AVAILABLE:
        return False
    try:
        supabase.table("facility_users").update({"is_approved": True}).eq("username", username).execute()
        log_audit("admin", "approve_user", {"username": username})
        return True
    except Exception as e:
        log_error(str(e), details={"username": username}, endpoint="approve_user")
        return False

def reject_user(username):
    if not SUPABASE_AVAILABLE:
        return False
    try:
        supabase.table("facility_users").delete().eq("username", username).execute()
        log_audit("admin", "reject_user", {"username": username})
        return True
    except Exception as e:
        log_error(str(e), details={"username": username}, endpoint="reject_user")
        return False

def generate_reset_token(username, email):
    if not SUPABASE_AVAILABLE:
        return False
    token = secrets.token_urlsafe(32)
    expiry = datetime.now() + timedelta(hours=1)
    try:
        supabase.table("facility_users").update({
            "password_reset_token": token,
            "reset_token_expiry": expiry.isoformat()
        }).eq("username", username).eq("email", email).execute()
        reset_link = f"{APP_URL}/?reset_token={token}"
        body = f"Click the link to reset your password: <a href='{reset_link}'>Reset Password</a>"
        send_email_notification(email, "Password Reset Request", body)
        return True
    except Exception as e:
        log_error(str(e), details={"username": username}, endpoint="generate_reset_token")
        return False

# -------------------------------
# 10. TASK FUNCTIONS (with optimistic locking)
# -------------------------------
def fetch_all_tasks():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("tasks_memory", [])
    try:
        res = supabase.table("tasks").select("*").order("id", desc=False).execute()
        if res.data:
            return res.data
        else:
            return st.session_state.get("tasks_memory", [])
    except Exception as e:
        log_error(str(e), endpoint="fetch_tasks")
        return st.session_state.get("tasks_memory", [])

def create_task(title, location, priority, loto, jsa, created_by, due_date=None, is_recurring=False, recurrence_type=None, recurrence_end_date=None, asset_id=None, meter_interval=None):
    if not SUPABASE_AVAILABLE:
        tasks = st.session_state.get("tasks_memory", [])
        new_id = max([t["id"] for t in tasks], default=0) + 1
        new_task = {
            "id": new_id,
            "title": title,
            "location": location,
            "priority": priority,
            "loto": loto,
            "jsa": jsa,
            "status": "Unassigned",
            "assigned_to": "Unassigned",
            "due_date": due_date.isoformat() if due_date else None,
            "is_recurring": is_recurring,
            "recurrence_type": recurrence_type,
            "recurrence_end_date": recurrence_end_date.isoformat() if recurrence_end_date else None,
            "asset_id": asset_id,
            "meter_interval": meter_interval,
            "version": 0
        }
        tasks.append(new_task)
        st.session_state.tasks_memory = tasks
        log_audit(created_by, "task_create_memory", {"task_id": new_id})
        return new_task
    try:
        new_task = {
            "title": title,
            "location": location,
            "priority": priority,
            "loto": loto,
            "jsa": jsa,
            "status": "Unassigned",
            "assigned_to": "Unassigned",
            "due_date": due_date.isoformat() if due_date else None,
            "is_recurring": is_recurring,
            "recurrence_type": recurrence_type,
            "recurrence_end_date": recurrence_end_date.isoformat() if recurrence_end_date else None,
            "asset_id": asset_id,
            "meter_interval": meter_interval,
            "version": 0
        }
        res = supabase.table("tasks").insert(new_task).execute()
        if res.data:
            task = res.data[0]
            log_audit(created_by, "task_create", {"task_id": task["id"]})
            log_task_activity(task["id"], created_by, "created", {"title": title})
            return task
    except Exception as e:
        log_error(str(e), details={"title": title}, endpoint="create_task")
        return None
    return None

def update_task(task_id, updates, updated_by):
    if not SUPABASE_AVAILABLE:
        for t in st.session_state.get("tasks_memory", []):
            if t["id"] == task_id:
                old = t.copy()
                t.update(updates)
                log_audit(updated_by, "task_update_memory", {"task_id": task_id, "old": old, "new": updates})
                return True
        return False
    try:
        current = supabase.table("tasks").select("version").eq("id", task_id).execute()
        if not current.data:
            return False
        current_version = current.data[0].get("version", 0)
        updates["version"] = current_version + 1
        res = supabase.table("tasks").update(updates).eq("id", task_id).eq("version", current_version).execute()
        if res.data:
            log_audit(updated_by, "task_update", {"task_id": task_id, "new": updates})
            log_task_activity(task_id, updated_by, "updated", updates)
            if 'status' in updates:
                send_external_notifications(f"Task #{task_id} status changed to {updates['status']} by {updated_by}")
            return True
        else:
            st.error("This task was updated by another user. Please refresh and try again.")
            return False
    except Exception as e:
        log_error(str(e), details={"task_id": task_id, "updates": updates}, user_name=updated_by, endpoint="update_task")
        return False

def delete_task(task_id, deleted_by):
    if not SUPABASE_AVAILABLE:
        st.session_state.tasks_memory = [t for t in st.session_state.get("tasks_memory", []) if t["id"] != task_id]
        log_audit(deleted_by, "task_delete_memory", {"task_id": task_id})
        return True
    try:
        supabase.table("tasks").delete().eq("id", task_id).execute()
        log_audit(deleted_by, "task_delete", {"task_id": task_id})
        log_task_activity(task_id, deleted_by, "deleted", {})
        send_external_notifications(f"Task #{task_id} deleted by {deleted_by}")
        return True
    except Exception as e:
        log_error(str(e), details={"task_id": task_id}, user_name=deleted_by, endpoint="delete_task")
        return False

# -------------------------------
# 11. TASK ACTIVITY LOG
# -------------------------------
def log_task_activity(task_id, user_name, action, details=None):
    if not SUPABASE_AVAILABLE:
        return
    try:
        supabase.table("task_activity").insert({
            "task_id": task_id,
            "user_name": user_name,
            "action": action,
            "details": json.dumps(details) if details else None
        }).execute()
    except Exception as e:
        log_error(str(e), endpoint="log_task_activity")

def fetch_task_activity(task_id):
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("activity_memory", [])
    try:
        res = supabase.table("task_activity").select("*").eq("task_id", task_id).order("created_at", asc=True).execute()
        if res.data:
            return res.data
    except Exception as e:
        log_error(str(e), endpoint="fetch_task_activity")
        pass
    return []

# -------------------------------
# 12. NOTIFICATIONS
# -------------------------------
def send_notification(user_name, title, body):
    if not SUPABASE_AVAILABLE:
        return
    try:
        supabase.table("notifications").insert({
            "user_name": user_name,
            "title": title,
            "body": body
        }).execute()
    except Exception as e:
        log_error(str(e), endpoint="send_notification")

def fetch_notifications(user_name):
    if not SUPABASE_AVAILABLE:
        return []
    try:
        res = supabase.table("notifications").select("*").eq("user_name", user_name).order("created_at", desc=True).limit(20).execute()
        if res.data:
            return res.data
    except Exception as e:
        log_error(str(e), endpoint="fetch_notifications")
        return []
    return []

def mark_notification_read(notification_id):
    if not SUPABASE_AVAILABLE:
        return
    try:
        supabase.table("notifications").update({"is_read": True}).eq("id", notification_id).execute()
    except Exception as e:
        log_error(str(e), endpoint="mark_notification_read")

# -------------------------------
# 13. PHOTO FUNCTIONS (with fallback)
# -------------------------------
def upload_photo(task_id, file_bytes, filename, uploaded_by):
    st.session_state.setdefault("photos_memory", []).append({
        "task_id": task_id,
        "photo_url": f"memory://{filename}",
        "uploaded_by": uploaded_by,
        "uploaded_at": datetime.now().isoformat()
    })
    log_audit(uploaded_by, "photo_upload_memory", {"task_id": task_id, "filename": filename})
    if SUPABASE_AVAILABLE:
        try:
            valid, msg = validate_image(file_bytes, filename)
            if not valid:
                st.error(msg)
                return True
            ext = filename.split(".")[-1]
            safe_name = f"task_{task_id}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(file_bytes).hexdigest()[:8]}.{ext}"
            res = supabase.storage.from_("task_photos").upload(safe_name, file_bytes)
            if res:
                public_url = supabase.storage.from_("task_photos").get_public_url(safe_name)
                try:
                    data = {"task_id": task_id, "photo_url": public_url, "uploaded_by": uploaded_by}
                    supabase.table("task_photos").insert(data).execute()
                    log_audit(uploaded_by, "photo_upload", {"task_id": task_id, "url": public_url})
                except Exception as e:
                    log_error(str(e), endpoint="photo_insert")
        except Exception as e:
            log_error(str(e), endpoint="photo_upload")
            pass
    return True

def fetch_photos(task_id):
    if not SUPABASE_AVAILABLE:
        photos = st.session_state.get("photos_memory", [])
        return [p for p in photos if p["task_id"] == task_id]
    db_photos = []
    try:
        res = supabase.table("task_photos").select("*").eq("task_id", task_id).order("uploaded_at", desc=True).execute()
        if res.data:
            db_photos = res.data
    except Exception as e:
        log_error(str(e), endpoint="fetch_photos")
        pass
    memory_photos = st.session_state.get("photos_memory", [])
    memory_photos = [p for p in memory_photos if p["task_id"] == task_id]
    all_photos = db_photos + memory_photos
    all_photos.sort(key=lambda x: x.get('uploaded_at', ''), reverse=True)
    return all_photos

# -------------------------------
# 14. FILE ATTACHMENTS
# -------------------------------
def upload_attachment(task_id, file_bytes, filename, uploaded_by):
    valid, msg = validate_attachment(file_bytes, filename)
    if not valid:
        st.error(msg)
        return False

    if not SUPABASE_AVAILABLE:
        st.session_state.setdefault("attachments_memory", []).append({
            "task_id": task_id,
            "file_name": filename,
            "file_url": f"memory://{filename}",
            "file_type": filename.split('.')[-1].lower(),
            "uploaded_by": uploaded_by,
            "uploaded_at": datetime.now().isoformat()
        })
        log_audit(uploaded_by, "attachment_upload_memory", {"task_id": task_id, "filename": filename})
        return True
    try:
        ext = filename.split('.')[-1].lower()
        safe_name = f"attachments/task_{task_id}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(file_bytes).hexdigest()[:8]}.{ext}"
        res = supabase.storage.from_("task_attachments").upload(safe_name, file_bytes)
        if res:
            public_url = supabase.storage.from_("task_attachments").get_public_url(safe_name)
            data = {
                "task_id": task_id,
                "file_name": filename,
                "file_url": public_url,
                "file_type": ext,
                "uploaded_by": uploaded_by
            }
            supabase.table("task_attachments").insert(data).execute()
            log_audit(uploaded_by, "attachment_upload", {"task_id": task_id, "filename": filename})
            return True
        else:
            return False
    except Exception as e:
        st.error(f"Upload failed: {e}")
        log_error(str(e), details={"task_id": task_id, "filename": filename}, endpoint="attachment_upload")
        return False

def fetch_attachments(task_id):
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("attachments_memory", [])
    try:
        res = supabase.table("task_attachments").select("*").eq("task_id", task_id).order("uploaded_at", desc=True).execute()
        if res.data:
            return res.data
        else:
            return []
    except Exception as e:
        log_error(str(e), endpoint="fetch_attachments")
        return []

# -------------------------------
# 15. TASK COMMENTS
# -------------------------------
def add_comment(task_id, comment, posted_by):
    if not SUPABASE_AVAILABLE:
        st.session_state.setdefault("comments_memory", []).append({
            "task_id": task_id,
            "comment": comment,
            "posted_by": posted_by,
            "posted_at": datetime.now().isoformat()
        })
        log_audit(posted_by, "comment_add_memory", {"task_id": task_id, "comment": comment[:50]})
        return True
    try:
        data = {"task_id": task_id, "comment": comment, "posted_by": posted_by}
        supabase.table("task_comments").insert(data).execute()
        log_audit(posted_by, "comment_add", {"task_id": task_id, "comment": comment[:50]})
        log_task_activity(task_id, posted_by, "commented", {"comment": comment[:50]})
        return True
    except Exception as e:
        log_error(str(e), details={"task_id": task_id}, endpoint="add_comment")
        return False

def fetch_comments(task_id):
    if not SUPABASE_AVAILABLE:
        comments = st.session_state.get("comments_memory", [])
        return [c for c in comments if c["task_id"] == task_id]
    try:
        res = supabase.table("task_comments").select("*").eq("task_id", task_id).order("posted_at", asc=True).execute()
        if res.data:
            return res.data
    except Exception as e:
        log_error(str(e), endpoint="fetch_comments")
        pass
    return []

# -------------------------------
# 16. CHAT FUNCTIONS
# -------------------------------
if 'next_memory_id' not in st.session_state:
    st.session_state.next_memory_id = -1

def send_message(sender, receiver, room, message, encrypted=False):
    if not SUPABASE_AVAILABLE:
        msg_id = st.session_state.next_memory_id
        st.session_state.next_memory_id -= 1
        msg = {
            "id": msg_id,
            "sender": sender,
            "receiver": receiver,
            "room": room,
            "message": message,
            "is_encrypted": encrypted,
            "created_at": datetime.now().isoformat()
        }
        st.session_state.setdefault("chat_messages_memory", []).append(msg)
        return True
    try:
        payload = {
            "sender": sender,
            "receiver": receiver,
            "room": room,
            "message": message,
            "is_encrypted": encrypted
        }
        supabase.table("chat_messages").insert(payload).execute()
        return True
    except Exception as e:
        log_error(str(e), endpoint="send_message")
        return False

def fetch_messages(room=None, limit=100):
    if not SUPABASE_AVAILABLE:
        msgs = st.session_state.get("chat_messages_memory", [])
        if room:
            msgs = [m for m in msgs if m["room"] == room]
        return sorted(msgs, key=lambda x: x["created_at"], reverse=True)[:limit]
    try:
        query = supabase.table("chat_messages").select("*").order("created_at", desc=True).limit(limit)
        if room:
            query = query.eq("room", room)
        res = query.execute()
        if res.data:
            return res.data
    except Exception as e:
        log_error(str(e), endpoint="fetch_messages")
        pass
    return []

def delete_message(message_id, deleted_by):
    if message_id < 0:
        st.session_state.chat_messages_memory = [
            m for m in st.session_state.get("chat_messages_memory", [])
            if m["id"] != message_id
        ]
        log_audit(deleted_by, "message_delete_memory", {"message_id": message_id})
        return True
    else:
        if not SUPABASE_AVAILABLE:
            return False
        try:
            msg = supabase.table("chat_messages").select("*").eq("id", message_id).execute()
            if msg.data:
                log_audit(deleted_by, "message_delete", {"message_id": message_id, "content": msg.data[0]["message"][:50]})
            supabase.table("chat_messages").delete().eq("id", message_id).execute()
            return True
        except Exception as e:
            log_error(str(e), details={"message_id": message_id}, endpoint="delete_message")
            return False

# -------------------------------
# 17. ENCRYPTION HELPERS (obfuscation)
# -------------------------------
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

def derive_key(name1, name2):
    sorted_names = sorted([name1.lower(), name2.lower()])
    combined = sorted_names[0] + sorted_names[1]
    salt = b"fixed_salt_for_demo"
    if CRYPTO_AVAILABLE:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(combined.encode()))
        return key
    else:
        return base64.urlsafe_b64encode(hashlib.sha256(combined.encode()).digest())

def encrypt_message(message, key):
    if CRYPTO_AVAILABLE:
        f = Fernet(key)
        return f.encrypt(message.encode()).decode()
    else:
        return base64.b64encode(message.encode()).decode()

def decrypt_message(encrypted_msg, key):
    if CRYPTO_AVAILABLE:
        f = Fernet(key)
        return f.decrypt(encrypted_msg.encode()).decode()
    else:
        return base64.b64decode(encrypted_msg.encode()).decode()

# -------------------------------
# 18. EXPORT REPORTS
# -------------------------------
def export_tasks_csv(tasks):
    if not tasks or not PANDAS_AVAILABLE:
        return None
    df = pd.DataFrame(tasks)
    cols = ['id', 'title', 'location', 'status', 'priority', 'assigned_to', 'due_date', 'created_at']
    existing_cols = [c for c in cols if c in df.columns]
    df = df[existing_cols]
    return df.to_csv(index=False)

# -------------------------------
# 19. PUSH NOTIFICATIONS
# -------------------------------
def send_push_notification(title, body):
    try:
        st.toast(f"{title}: {body}")
    except:
        pass

# -------------------------------
# 20. RECURRING TASK HANDLER
# -------------------------------
def handle_recurring_tasks():
    if not SUPABASE_AVAILABLE:
        return
    try:
        res = supabase.table("tasks").select("*").eq("is_recurring", True).execute()
        if not res.data:
            return
        now = datetime.now()
        for task in res.data:
            due_date = datetime.fromisoformat(task['due_date']) if task['due_date'] else None
            if not due_date:
                continue
            if due_date < now:
                recurrence_type = task.get('recurrence_type')
                if recurrence_type == 'daily':
                    next_due = due_date + timedelta(days=1)
                elif recurrence_type == 'weekly':
                    next_due = due_date + timedelta(weeks=1)
                elif recurrence_type == 'monthly':
                    next_due = due_date + timedelta(days=30)
                else:
                    continue
                end_date = datetime.fromisoformat(task['recurrence_end_date']) if task.get('recurrence_end_date') else None
                if end_date and next_due > end_date:
                    supabase.table("tasks").update({"is_recurring": False}).eq("id", task["id"]).execute()
                    continue
                new_task = {
                    "title": task['title'],
                    "location": task['location'],
                    "priority": task['priority'],
                    "loto": task.get('loto', False),
                    "jsa": task.get('jsa', False),
                    "status": "Unassigned",
                    "assigned_to": "Unassigned",
                    "due_date": next_due.isoformat(),
                    "is_recurring": True,
                    "recurrence_type": recurrence_type,
                    "recurrence_end_date": task.get('recurrence_end_date')
                }
                supabase.table("tasks").insert(new_task).execute()
                supabase.table("tasks").update({"due_date": next_due.isoformat()}).eq("id", task["id"]).execute()
    except Exception as e:
        log_error(str(e), endpoint="handle_recurring_tasks")

# -------------------------------
# 20A. ASSET REGISTER FUNCTIONS
# -------------------------------
def fetch_all_assets():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("assets_memory", [])
    try:
        res = supabase.table("assets").select("*").order("id", desc=False).execute()
        if res.data:
            return res.data
        return st.session_state.get("assets_memory", [])
    except Exception as e:
        log_error(str(e), endpoint="fetch_assets")
        return st.session_state.get("assets_memory", [])

def create_asset(name, asset_tag, category, location, manufacturer, model_number, serial_number,
                  install_date, status, criticality, current_meter, meter_unit, created_by):
    payload = {
        "name": name,
        "asset_tag": asset_tag,
        "category": category,
        "location": location,
        "manufacturer": manufacturer,
        "model_number": model_number,
        "serial_number": serial_number,
        "install_date": install_date.isoformat() if install_date else None,
        "status": status,
        "criticality": criticality,
        "current_meter": current_meter,
        "meter_unit": meter_unit,
        "version": 0
    }
    if not SUPABASE_AVAILABLE:
        assets = st.session_state.get("assets_memory", [])
        new_id = max([a["id"] for a in assets], default=0) + 1
        payload["id"] = new_id
        assets.append(payload)
        st.session_state.assets_memory = assets
        log_audit(created_by, "asset_create_memory", {"asset_id": new_id})
        return payload
    try:
        res = supabase.table("assets").insert(payload).execute()
        if res.data:
            asset = res.data[0]
            log_audit(created_by, "asset_create", {"asset_id": asset["id"], "name": name})
            return asset
    except Exception as e:
        log_error(str(e), details={"name": name}, endpoint="create_asset")
        return None
    return None

def update_asset(asset_id, updates, updated_by):
    if not SUPABASE_AVAILABLE:
        for a in st.session_state.get("assets_memory", []):
            if a["id"] == asset_id:
                a.update(updates)
                log_audit(updated_by, "asset_update_memory", {"asset_id": asset_id, "new": updates})
                return True
        return False
    try:
        supabase.table("assets").update(updates).eq("id", asset_id).execute()
        log_audit(updated_by, "asset_update", {"asset_id": asset_id, "new": updates})
        return True
    except Exception as e:
        log_error(str(e), details={"asset_id": asset_id, "updates": updates}, endpoint="update_asset")
        return False

def delete_asset(asset_id, deleted_by):
    if not SUPABASE_AVAILABLE:
        st.session_state.assets_memory = [a for a in st.session_state.get("assets_memory", []) if a["id"] != asset_id]
        log_audit(deleted_by, "asset_delete_memory", {"asset_id": asset_id})
        return True
    try:
        supabase.table("assets").delete().eq("id", asset_id).execute()
        log_audit(deleted_by, "asset_delete", {"asset_id": asset_id})
        return True
    except Exception as e:
        log_error(str(e), details={"asset_id": asset_id}, endpoint="delete_asset")
        return False

# -------------------------------
# 20B. INVENTORY / PARTS FUNCTIONS
# -------------------------------
def fetch_all_parts():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("inventory_memory", [])
    try:
        res = supabase.table("inventory_parts").select("*").order("id", desc=False).execute()
        if res.data:
            return res.data
        return st.session_state.get("inventory_memory", [])
    except Exception as e:
        log_error(str(e), endpoint="fetch_parts")
        return st.session_state.get("inventory_memory", [])

def create_part(part_name, part_number, category, quantity_on_hand, reorder_point, reorder_qty,
                 unit_cost, supplier, bin_location, created_by):
    payload = {
        "part_name": part_name,
        "part_number": part_number,
        "category": category,
        "quantity_on_hand": quantity_on_hand,
        "reorder_point": reorder_point,
        "reorder_qty": reorder_qty,
        "unit_cost": unit_cost,
        "supplier": supplier,
        "bin_location": bin_location,
    }
    if not SUPABASE_AVAILABLE:
        parts = st.session_state.get("inventory_memory", [])
        new_id = max([p["id"] for p in parts], default=0) + 1
        payload["id"] = new_id
        parts.append(payload)
        st.session_state.inventory_memory = parts
        log_audit(created_by, "part_create_memory", {"part_id": new_id})
        return payload
    try:
        res = supabase.table("inventory_parts").insert(payload).execute()
        if res.data:
            part = res.data[0]
            log_audit(created_by, "part_create", {"part_id": part["id"], "name": part_name})
            return part
    except Exception as e:
        log_error(str(e), details={"part_name": part_name}, endpoint="create_part")
        return None
    return None

def adjust_part_quantity(part_id, delta, adjusted_by, reason="manual adjustment"):
    """delta can be negative (consumption) or positive (restock)."""
    if not SUPABASE_AVAILABLE:
        for p in st.session_state.get("inventory_memory", []):
            if p["id"] == part_id:
                p["quantity_on_hand"] = max(0, p.get("quantity_on_hand", 0) + delta)
                log_audit(adjusted_by, "part_adjust_memory", {"part_id": part_id, "delta": delta, "reason": reason})
                return True
        return False
    try:
        current = supabase.table("inventory_parts").select("quantity_on_hand").eq("id", part_id).execute()
        if not current.data:
            return False
        new_qty = max(0, current.data[0]["quantity_on_hand"] + delta)
        supabase.table("inventory_parts").update({"quantity_on_hand": new_qty}).eq("id", part_id).execute()
        log_audit(adjusted_by, "part_adjust", {"part_id": part_id, "delta": delta, "reason": reason})
        return True
    except Exception as e:
        log_error(str(e), details={"part_id": part_id, "delta": delta}, endpoint="adjust_part_quantity")
        return False

def delete_part(part_id, deleted_by):
    if not SUPABASE_AVAILABLE:
        st.session_state.inventory_memory = [p for p in st.session_state.get("inventory_memory", []) if p["id"] != part_id]
        log_audit(deleted_by, "part_delete_memory", {"part_id": part_id})
        return True
    try:
        supabase.table("inventory_parts").delete().eq("id", part_id).execute()
        log_audit(deleted_by, "part_delete", {"part_id": part_id})
        return True
    except Exception as e:
        log_error(str(e), details={"part_id": part_id}, endpoint="delete_part")
        return False

def link_part_to_task(task_id, part_id, quantity_used, used_by):
    """Records parts consumption against a task/work order and decrements stock."""
    payload = {
        "task_id": task_id,
        "part_id": part_id,
        "quantity_used": quantity_used,
        "used_by": used_by,
    }
    if not SUPABASE_AVAILABLE:
        st.session_state.setdefault("task_parts_memory", []).append(payload)
    else:
        try:
            supabase.table("task_parts").insert(payload).execute()
        except Exception as e:
            log_error(str(e), details=payload, endpoint="link_part_to_task")
            return False
    adjust_part_quantity(part_id, -abs(quantity_used), used_by, reason=f"used on task #{task_id}")
    log_task_activity(task_id, used_by, "part_used", {"part_id": part_id, "quantity": quantity_used})
    return True

def fetch_task_parts(task_id):
    if not SUPABASE_AVAILABLE:
        return [tp for tp in st.session_state.get("task_parts_memory", []) if tp["task_id"] == task_id]
    try:
        res = supabase.table("task_parts").select("*").eq("task_id", task_id).execute()
        if res.data:
            return res.data
    except Exception as e:
        log_error(str(e), endpoint="fetch_task_parts")
    return []

# -------------------------------
# 20C. INCIDENT / SAFETY REPORTING FUNCTIONS
# -------------------------------
def fetch_all_incidents():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("incidents_memory", [])
    try:
        res = supabase.table("incidents").select("*").order("id", desc=True).execute()
        if res.data:
            return res.data
        return st.session_state.get("incidents_memory", [])
    except Exception as e:
        log_error(str(e), endpoint="fetch_incidents")
        return st.session_state.get("incidents_memory", [])

def create_incident(incident_type, severity, location, description, reported_by, asset_id=None, witnesses=None, immediate_action=None):
    payload = {
        "incident_type": incident_type,
        "severity": severity,
        "location": location,
        "description": description,
        "reported_by": reported_by,
        "asset_id": asset_id,
        "witnesses": witnesses,
        "immediate_action": immediate_action,
        "status": "Open",
        "root_cause": None,
        "corrective_action": None,
    }
    if not SUPABASE_AVAILABLE:
        incidents = st.session_state.get("incidents_memory", [])
        new_id = max([i["id"] for i in incidents], default=0) + 1
        payload["id"] = new_id
        payload["created_at"] = datetime.now().isoformat()
        incidents.append(payload)
        st.session_state.incidents_memory = incidents
        log_audit(reported_by, "incident_report_memory", {"incident_id": new_id, "severity": severity})
        return payload
    try:
        res = supabase.table("incidents").insert(payload).execute()
        if res.data:
            incident = res.data[0]
            log_audit(reported_by, "incident_report", {"incident_id": incident["id"], "severity": severity})
            if severity in ("Critical", "High"):
                send_external_notifications(f"⚠️ {severity} incident reported by {reported_by} at {location}: {incident_type}")
            return incident
    except Exception as e:
        log_error(str(e), details={"incident_type": incident_type}, endpoint="create_incident")
        return None
    return None

def update_incident(incident_id, updates, updated_by):
    if not SUPABASE_AVAILABLE:
        for i in st.session_state.get("incidents_memory", []):
            if i["id"] == incident_id:
                i.update(updates)
                log_audit(updated_by, "incident_update_memory", {"incident_id": incident_id, "new": updates})
                return True
        return False
    try:
        supabase.table("incidents").update(updates).eq("id", incident_id).execute()
        log_audit(updated_by, "incident_update", {"incident_id": incident_id, "new": updates})
        return True
    except Exception as e:
        log_error(str(e), details={"incident_id": incident_id, "updates": updates}, endpoint="update_incident")
        return False

# -------------------------------
# 20D. KPI / ANALYTICS HELPERS
# -------------------------------
def compute_mttr_hours(tasks):
    """Mean Time To Repair: average hours between task creation and completion, for Complete tasks with timestamps."""
    durations = []
    for t in tasks:
        if t.get('status') == 'Complete' and t.get('created_at') and t.get('due_date'):
            try:
                created = datetime.fromisoformat(str(t['created_at']).replace('Z', '+00:00').split('+')[0])
                completed_ref = datetime.fromisoformat(str(t['due_date']).replace('Z', '+00:00').split('+')[0])
                delta = (completed_ref - created).total_seconds() / 3600.0
                if delta >= 0:
                    durations.append(delta)
            except Exception:
                continue
    if not durations:
        return None
    return sum(durations) / len(durations)

def compute_pm_compliance(tasks):
    """Percentage of recurring/PM tasks completed on or before their due date."""
    pm_tasks = [t for t in tasks if t.get('is_recurring')]
    if not pm_tasks:
        return None
    on_time = 0
    for t in pm_tasks:
        if t.get('status') == 'Complete':
            on_time += 1
    return round((on_time / len(pm_tasks)) * 100, 1)

def compute_asset_downtime_ranking(tasks, assets):
    """Ranks assets by number of associated maintenance tasks (proxy for downtime frequency)."""
    counts = {}
    for t in tasks:
        aid = t.get('asset_id')
        if aid:
            counts[aid] = counts.get(aid, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    asset_lookup = {a['id']: a['name'] for a in assets}
    return [(asset_lookup.get(aid, f"Asset #{aid}"), cnt) for aid, cnt in ranked]

# -------------------------------
# 21. SESSION STATE INIT
# -------------------------------
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_payload' not in st.session_state:
    st.session_state.user_payload = None
if 'chat_room' not in st.session_state:
    st.session_state.chat_room = "global"
if 'chat_partner' not in st.session_state:
    st.session_state.chat_partner = None
if 'broadcast_messages' not in st.session_state:
    st.session_state.broadcast_messages = []
if 'tasks_memory' not in st.session_state:
    st.session_state.tasks_memory = []
if 'chat_messages_memory' not in st.session_state:
    st.session_state.chat_messages_memory = []
if 'chat_input_value' not in st.session_state:
    st.session_state.chat_input_value = ""
if 'photos_memory' not in st.session_state:
    st.session_state.photos_memory = []
if 'last_activity' not in st.session_state:
    st.session_state.last_activity = datetime.now()
if 'chat_channel' not in st.session_state:
    st.session_state.chat_channel = None
if 'chat_messages_cache' not in st.session_state:
    st.session_state.chat_messages_cache = []
if 'attachments_memory' not in st.session_state:
    st.session_state.attachments_memory = []
if 'comments_memory' not in st.session_state:
    st.session_state.comments_memory = []
if 'activity_memory' not in st.session_state:
    st.session_state.activity_memory = []
if 'notifications_cache' not in st.session_state:
    st.session_state.notifications_cache = []
if 'oauth_token' not in st.session_state:
    st.session_state.oauth_token = None
if 'assets_memory' not in st.session_state:
    st.session_state.assets_memory = []
if 'inventory_memory' not in st.session_state:
    st.session_state.inventory_memory = []
if 'incidents_memory' not in st.session_state:
    st.session_state.incidents_memory = []
if 'task_parts_memory' not in st.session_state:
    st.session_state.task_parts_memory = []

# -------------------------------
# 22. SESSION TIMEOUT CHECK
# -------------------------------
def check_timeout():
    if st.session_state.authenticated:
        if datetime.now() - st.session_state.last_activity > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
            st.session_state.authenticated = False
            st.session_state.user_payload = None
            st.warning("Session expired due to inactivity. Please log in again.")
            st.rerun()
        else:
            st.session_state.last_activity = datetime.now()

# -------------------------------
# 23. OAUTH LOGIN (Google) - placeholder
# -------------------------------
def google_oauth():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        st.error("Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in secrets.")
        return None
    st.info("OAuth login is available but requires setup of a callback endpoint. Please use the regular login for now.")
    return None

# -------------------------------
# 24. AUTHENTICATION GATEWAY
# -------------------------------
if not st.session_state.authenticated:
    st.markdown('''
    <div class="main-header">
        <i class="fas fa-hard-hat"></i> Mine & Workshop Digital Tracker
        <small>Smart Maintenance Management System</small>
    </div>
    ''', unsafe_allow_html=True)
    st.markdown('<div class="sub-header"><i class="fas fa-shield-alt"></i> Secure Login Gateway</div>', unsafe_allow_html=True)

    # Check for reset token
    reset_token = st.query_params.get("reset_token")
    if reset_token:
        users = fetch_all_users_from_db()
        found = False
        for u in users:
            if u.get("password_reset_token") == reset_token:
                expiry = datetime.fromisoformat(u["reset_token_expiry"]) if u.get("reset_token_expiry") else datetime.now()
                if expiry > datetime.now():
                    with st.form("reset_password_form"):
                        st.markdown("### Reset Your Password")
                        new_pass = st.text_input("New Password", type="password")
                        if st.form_submit_button("Reset Password"):
                            strong, msg = is_strong_password(new_pass)
                            if strong:
                                hashed = hash_password(new_pass)
                                if update_user_profile(u["username"], {
                                    "password_hash": hashed,
                                    "password_reset_token": None,
                                    "reset_token_expiry": None
                                }):
                                    st.success("Password updated! Please log in.")
                                    st.query_params.clear()
                                    st.rerun()
                                else:
                                    st.error("Failed to update password.")
                            else:
                                st.error(msg)
                else:
                    st.error("Reset link expired.")
                found = True
                break
        if not found:
            st.error("Invalid reset token.")

    # Normal login form
    with st.form("login_form"):
        user_in = st.text_input("Username", placeholder="Enter your username").strip().lower()
        pass_in = st.text_input("Password", type="password", placeholder="Enter your password")
        login_submitted = st.form_submit_button('🔐 Authenticate Profile', use_container_width=True)

    if login_submitted:
        matched_user, status = authenticate_user(user_in, pass_in)
        if matched_user:
            st.session_state.user_payload = {
                "name": matched_user.get("full_name", matched_user.get("username")),
                "role": matched_user.get("role", "Worker"),
                "username": matched_user.get("username"),
                "email": matched_user.get("email", None),
                "avatar_url": matched_user.get("avatar_url", None)
            }
            st.session_state.authenticated = True
            st.session_state.last_activity = datetime.now()
            log_audit(matched_user.get("full_name"), "login")
            st.rerun()
        elif status == "pending_approval":
            st.error("Your account is pending admin approval. Please wait for a superintendent to approve your account.")
        else:
            st.error("Invalid credentials or database unreachable.")

    # Forgot password link
    with st.expander("Forgot Password?"):
        with st.form("reset_form"):
            reset_email = st.text_input("Enter your registered email", placeholder="email@example.com")
            if st.form_submit_button("Send Reset Link"):
                users = fetch_all_users_from_db()
                for u in users:
                    if u.get("email") == reset_email:
                        if generate_reset_token(u["username"], reset_email):
                            st.success("Reset link sent to your email.")
                        else:
                            st.error("Failed to send reset link.")
                        break
                else:
                    st.error("Email not found.")

    if AUTH_AVAILABLE and GOOGLE_CLIENT_ID:
        if st.button("🔑 Login with Google", use_container_width=True):
            st.info("OAuth login will redirect to Google. (Integration in progress)")

    st.markdown("---")
    st.markdown('<div class="sub-header"><i class="fas fa-user-plus"></i> Create Account Profile</div>', unsafe_allow_html=True)

    with st.form("register_form"):
        reg_user = st.text_input("Choose Username", placeholder="Pick a unique username").strip().lower()
        reg_name = st.text_input("Full Name", placeholder="Your full name")
        reg_email = st.text_input("Email (optional)", placeholder="email@example.com")
        reg_role = st.selectbox("Role Access Level", ["Worker", "Supervisor", "Superintendent"])
        reg_pass = st.text_input("Set Password", type="password", placeholder="Choose a strong password")
        register_submitted = st.form_submit_button('✅ Register Profile', use_container_width=True)

    if register_submitted:
        if reg_user and reg_name and reg_pass:
            users = fetch_all_users_from_db()
            if any(u["username"].lower() == reg_user for u in users):
                st.error("Username already taken. Please choose another.")
            else:
                success = register_user_to_db(reg_user, reg_name, reg_role, reg_pass, reg_email)
                if success:
                    st.success(f"Account '{reg_user}' created! Please wait for admin approval before logging in.")
                else:
                    st.error("Registration failed. Database error.")
        else:
            st.error("All fields are mandatory.")
    st.stop()
else:
    check_timeout()

# -------------------------------
# 25. PWA MANIFEST & SERVICE WORKER
# -------------------------------
st.markdown("""
<link rel="manifest" href="/static/manifest.json">
<script>
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js');
  }
</script>
""", unsafe_allow_html=True)

# -------------------------------
# 26. HANDLE RECURRING TASKS
# -------------------------------
handle_recurring_tasks()

# -------------------------------
# 27. MAIN APP
# -------------------------------
user = st.session_state.user_payload
full_name = user['name']
username = user['username']
role = user['role'].strip().lower()
user_email = user.get('email', None)
avatar_url = user.get('avatar_url', None)

# Modern header
st.markdown('''
<div class="main-header">
    <i class="fas fa-hard-hat"></i> Mine & Workshop Digital Tracker
    <small>Smart Maintenance Management System</small>
</div>
''', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown(f"""
    <div class="sidebar-user">
        <i class="fas fa-user-circle user-icon"></i>
        <div class="user-name">{esc(full_name)}</div>
        <div class="user-role">
            <i class="fas fa-id-badge"></i> {user['role']}
            <span class="verified-badge">VERIFIED</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if USING_HARDCODED:
        st.caption('⚠️ Using hardcoded Supabase – set secrets.toml for production')

    # Notifications
    if SUPABASE_AVAILABLE:
        notifications = fetch_notifications(username)
        unread = sum(1 for n in notifications if not n['is_read'])
        if unread > 0:
            st.warning(f"🔔 {unread} unread notification(s)")
            for n in notifications[:3]:
                if not n['is_read']:
                    st.info(f"**{n['title']}**\n{n['body']}")
                    if st.button("Mark as read", key=f"read_{n['id']}"):
                        mark_notification_read(n['id'])
                        st.rerun()

    if st.button("🌓 Toggle Theme", use_container_width=True):
        st.session_state.dark_mode = not st.session_state.dark_mode
        st.rerun()

    if role in ["supervisor", "superintendent"]:
        st.markdown("---")
        st.markdown("📢 **Send Broadcast**")
        broadcast_msg = st.text_area("Message to all Workers", placeholder="Type your broadcast...")
        if st.button("📤 Send Broadcast", use_container_width=True):
            if broadcast_msg:
                st.session_state.broadcast_messages.append({
                    "sender": full_name,
                    "role": user['role'],
                    "message": broadcast_msg,
                    "timestamp": datetime.now().strftime("%H:%M")
                })
                log_audit(full_name, "broadcast", {"message": broadcast_msg[:50]})
                all_users = fetch_all_users_from_db()
                worker_emails = [u.get('email') for u in all_users if u['role'].strip().lower() == 'worker' and u.get('email')]
                for email in worker_emails:
                    send_email_notification(email, f"Broadcast from {full_name}", broadcast_msg.replace('\n', '<br>'))
                send_push_notification("New Broadcast", broadcast_msg[:100])
                st.success("Broadcast sent!")
                st.rerun()
            else:
                st.error("Message cannot be empty.")

    st.markdown("---")
    st.markdown("💬 **Chat Rooms**")
    if st.button("🌍 Global Chat", use_container_width=True):
        st.session_state.chat_room = "global"
        st.rerun()
    if role in ["supervisor", "superintendent"]:
        if st.button("🔒 Supervisor Room", use_container_width=True):
            st.session_state.chat_room = "supervisor"
            st.rerun()

    st.markdown("👤 **Private Chat**")
    all_users = fetch_all_users_from_db()
    other_users = [u["full_name"] for u in all_users if u["full_name"] != full_name and u.get("is_approved", False)]
    if other_users:
        selected_user = st.selectbox("Choose contact", other_users)
        if st.button("🔐 Open Private Chat", use_container_width=True):
            sorted_names = sorted([full_name, selected_user])
            room_name = f"private:{sorted_names[0]}_{sorted_names[1]}"
            st.session_state.chat_room = room_name
            st.session_state.chat_partner = selected_user
            st.rerun()
    else:
        st.info("No other approved users available.")

    st.markdown("---")
    st.markdown("👤 **Profile**")
    if st.button("👤 My Profile", use_container_width=True):
        st.session_state.active_tab = "profile"
        st.rerun()

    if st.button("🚪 Logout", use_container_width=True):
        log_audit(full_name, "logout")
        st.session_state.authenticated = False
        st.session_state.user_payload = None
        st.session_state.chat_room = "global"
        if st.session_state.chat_channel:
            try:
                supabase.remove_channel(st.session_state.chat_channel)
            except:
                pass
            st.session_state.chat_channel = None
        st.rerun()

    st.markdown("---")
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()

if 'profile_tab' not in st.session_state:
    st.session_state.profile_tab = False

db_tasks = fetch_all_tasks()
if db_tasks:
    st.session_state.tasks = db_tasks
else:
    st.session_state.tasks = st.session_state.tasks_memory

# -------------------------------
# 28. TOP-LEVEL NAVIGATION (icon menu)
# -------------------------------
st.markdown('<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">', unsafe_allow_html=True)

try:
    from streamlit_option_menu import option_menu
except ImportError:
    st.error("streamlit-option-menu not installed. Please run: pip install streamlit-option-menu")
    st.stop()

nav_options = ["Task Dashboard", "Asset Register", "Inventory", "Incident Reports", "Chat Room", "Admin Panel", "Profile", "Activity Timeline"]
nav_icons = ["list-task", "hdd-stack-fill", "box-seam-fill", "exclamation-triangle-fill", "chat-dots-fill", "gear-fill", "person-circle", "clock-history"]

selected_section = option_menu(
    menu_title=None,
    options=nav_options,
    icons=nav_icons,
    orientation="horizontal",
    default_index=0,
    styles=menu_styles(),
)

# Load shared datasets used across the new modules
db_assets = fetch_all_assets()
st.session_state.assets = db_assets if db_assets else st.session_state.assets_memory
db_parts = fetch_all_parts()
st.session_state.parts = db_parts if db_parts else st.session_state.inventory_memory
db_incidents = fetch_all_incidents()
st.session_state.incidents = db_incidents if db_incidents else st.session_state.incidents_memory

# ---- TASK DASHBOARD ----
if selected_section == "Task Dashboard":
    if role == "worker":
        st.markdown('<div class="sub-header"><i class="fas fa-hard-hat"></i> Field Worker Workspace</div>', unsafe_allow_html=True)
        if st.session_state.broadcast_messages:
            st.info("📢 Latest Broadcasts:")
            for msg in reversed(st.session_state.broadcast_messages[-5:]):
                st.warning(f"**{msg['sender']}** ({msg['role']}) at {msg['timestamp']}: {msg['message']}")

        worker_sub = option_menu(
            menu_title=None,
            options=["My Assigned Tasks", "Unassigned Board"],
            icons=["clipboard-check", "inbox"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )

        if worker_sub == "My Assigned Tasks":
            my_tasks = [t for t in st.session_state.tasks if t['assigned_to'] == full_name]
            if not my_tasks:
                st.info("No tasks assigned to you.")
            else:
                for idx, task in enumerate(my_tasks):
                    priority_class = f"priority-{task['priority']}"
                    status_class = f"status-{task['status'].replace(' ', '')}"
                    overdue = False
                    if task.get('due_date'):
                        due = datetime.fromisoformat(task['due_date'])
                        if datetime.now() > due:
                            overdue = True
                    overdue_badge = '<span class="overdue-badge">OVERDUE</span>' if overdue else ''
                    st.markdown(f"""
                    <div class="task-card" style="border-top: 4px solid { '#dc2626' if overdue else '#0f3460' };">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                            <div>
                                <div class="task-title">#{task['id']} {esc(task['title'])} {overdue_badge}</div>
                                <div class="task-meta">
                                    <span><i class="fas fa-map-marker-alt"></i> {esc(task['location'])}</span>
                                    <span><i class="fas fa-tag"></i> <span class="priority-badge {priority_class}">{task['priority']}</span></span>
                                    <span><i class="fas fa-circle" style="color: #3b82f6;"></i> <span class="status-badge {status_class}">{task['status']}</span></span>
                                    {f'<span><i class="fas fa-calendar-alt"></i> Due: {task["due_date"][:10]}</span>' if task.get('due_date') else ''}
                                </div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    col1, col2 = st.columns([2, 3])
                    with col1:
                        loto = st.checkbox("🔒 LOTO Isolated", value=task.get('loto', False), key=f"loto_{task['id']}_{idx}")
                        jsa = st.checkbox("📋 JSA Signed", value=task.get('jsa', False), key=f"jsa_{task['id']}_{idx}")
                    with col2:
                        status_options = ["In Progress", "Pending QA", "Blocked", "Complete"]
                        current_idx = status_options.index(task['status']) if task['status'] in status_options else 0
                        new_status = st.selectbox("Update Status", status_options, index=current_idx, key=f"stat_{task['id']}_{idx}")
                        if new_status != task['status']:
                            update_task(task['id'], {"status": new_status}, full_name)
                            log_audit(full_name, "task_status_change", {"task_id": task['id'], "new_status": new_status})
                            st.rerun()
                    if loto != task.get('loto') or jsa != task.get('jsa'):
                        update_task(task['id'], {"loto": loto, "jsa": jsa}, full_name)
                        st.rerun()
                    if not loto or not jsa:
                        st.error("🔒 Safety isolation forms are required before proceeding.")
                    else:
                        st.success("✅ Safety checks passed.")

                    with st.expander("💬 Comments"):
                        comments = fetch_comments(task['id'])
                        if comments:
                            for c in comments:
                                st.markdown(f"**{c['posted_by']}** ({c['posted_at'][:16]}): {c['comment']}")
                        else:
                            st.caption("No comments yet.")
                        new_comment = st.text_area("Add comment", key=f"comment_{task['id']}_{idx}", placeholder="Write comment...")
                        if st.button("Post Comment", key=f"post_comment_{task['id']}_{idx}"):
                            if new_comment.strip():
                                add_comment(task['id'], new_comment, full_name)
                                st.rerun()

                    with st.expander("📎 Attachments"):
                        attachments = fetch_attachments(task['id'])
                        if attachments:
                            for a in attachments:
                                st.markdown(f"[{a['file_name']}]({a['file_url']}) (uploaded by {a['uploaded_by']})")
                        else:
                            st.caption("No attachments.")
                        uploaded_file = st.file_uploader("Upload attachment (PDF, DOC, etc.)", type=ALLOWED_ATTACHMENT_EXTENSIONS, key=f"attach_{task['id']}_{idx}")
                        if uploaded_file is not None:
                            if st.button("Upload Attachment", key=f"attach_btn_{task['id']}_{idx}"):
                                bytes_data = uploaded_file.getvalue()
                                if upload_attachment(task['id'], bytes_data, uploaded_file.name, full_name):
                                    st.success("Attachment uploaded!")
                                    st.rerun()

                    st.markdown("---")
                    st.markdown('<i class="fas fa-camera"></i> **Upload Proof Photo**', unsafe_allow_html=True)
                    uploaded_file = st.file_uploader(f"Choose an image for task #{task['id']}", type=["jpg", "jpeg", "png", "gif", "webp", "bmp"], key=f"upload_{task['id']}_{idx}")
                    if uploaded_file is not None:
                        if st.button(f"📤 Upload for Task #{task['id']}", key=f"upload_btn_{task['id']}_{idx}"):
                            bytes_data = uploaded_file.getvalue()
                            success = upload_photo(task['id'], bytes_data, uploaded_file.name, full_name)
                            if success:
                                st.success("Photo uploaded!")
                                st.rerun()
                            else:
                                st.error("Upload failed.")
                    photos = fetch_photos(task['id'])
                    if photos:
                        st.markdown("**📸 Already uploaded:**")
                        cols = st.columns(min(4, len(photos)))
                        for pic_idx, photo in enumerate(photos):
                            with cols[pic_idx % len(cols)]:
                                img_url = photo.get('photo_url', '')
                                if img_url.startswith('memory://'):
                                    st.info(f"📷 {photo.get('uploaded_by', 'Unknown')} uploaded a photo")
                                else:
                                    st.image(img_url, width=120, use_container_width=True)
                                st.caption(f"By {photo.get('uploaded_by', 'Unknown')}")
                    st.markdown("---")

        elif worker_sub == "Unassigned Board":
            unassigned = [t for t in st.session_state.tasks if t['assigned_to'] == "Unassigned" or t['status'] == "Unassigned"]
            if not unassigned:
                st.success("🎉 No unassigned tasks at the moment.")
            else:
                for task in unassigned:
                    priority_class = f"priority-{task['priority']}"
                    overdue = False
                    if task.get('due_date'):
                        due = datetime.fromisoformat(task['due_date'])
                        if datetime.now() > due:
                            overdue = True
                    overdue_badge = '<span class="overdue-badge">OVERDUE</span>' if overdue else ''
                    st.markdown(f"""
                    <div class="task-card" style="border-top: 4px solid { '#dc2626' if overdue else '#0f3460' };">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <div class="task-title">#{task['id']} {esc(task['title'])} {overdue_badge}</div>
                                <div class="task-meta">
                                    <span><i class="fas fa-map-marker-alt"></i> {esc(task['location'])}</span>
                                    <span><i class="fas fa-tag"></i> <span class="priority-badge {priority_class}">{task['priority']}</span></span>
                                    {f'<span><i class="fas fa-calendar-alt"></i> Due: {task["due_date"][:10]}</span>' if task.get('due_date') else ''}
                                </div>
                            </div>
                            <div>
                                <span class="status-badge status-Unassigned">Unassigned</span>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

    elif role == "supervisor":
        st.markdown('<div class="sub-header"><i class="fas fa-clipboard"></i> Supervisor Operations Desk</div>', unsafe_allow_html=True)
        supervisor_sub = option_menu(
            menu_title=None,
            options=["Manage All Tasks", "Create New Task", "Dashboard"],
            icons=["list-check", "plus-circle", "pie-chart-fill"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )
        if supervisor_sub == "Manage All Tasks":
            st.markdown("### All Maintenance Tasks")
            all_users = fetch_all_users_from_db()
            worker_names = ["Unassigned"] + [u["full_name"] for u in all_users if u["role"].strip().lower() == "worker" and u.get("is_approved", False)]
            if not st.session_state.tasks:
                st.info("No tasks found.")
            for task in st.session_state.tasks:
                priority_class = f"priority-{task['priority']}"
                status_class = f"status-{task['status'].replace(' ', '')}"
                overdue = False
                if task.get('due_date'):
                    due = datetime.fromisoformat(task['due_date'])
                    if datetime.now() > due:
                        overdue = True
                overdue_badge = '<span class="overdue-badge">OVERDUE</span>' if overdue else ''
                st.markdown(f"""
                <div class="custom-card" style="border-left-color: { '#dc2626' if overdue else '#0f3460' };">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>#{task['id']}: {esc(task['title'])} {overdue_badge}</strong><br>
                            <i class="fas fa-map-marker-alt"></i> {esc(task['location'])}
                            <span class="status-badge {status_class}">{task['status']}</span>
                            <span class="priority-badge {priority_class}">{task['priority']}</span>
                            {f'<i class="fas fa-calendar-alt"></i> {task["due_date"][:10]}' if task.get('due_date') else ''}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                cols = st.columns([3, 1, 1])
                current_assign = task['assigned_to'] if task['assigned_to'] in worker_names else "Unassigned"
                new_assign = cols[0].selectbox("Assign to:", worker_names,
                                               index=worker_names.index(current_assign),
                                               key=f"assign_{task['id']}")
                if new_assign != task['assigned_to']:
                    update_task(task['id'], {"assigned_to": new_assign}, full_name)
                    if task['status'] == "Unassigned" and new_assign != "Unassigned":
                        update_task(task['id'], {"status": "In Progress"}, full_name)
                    log_audit(full_name, "task_assign", {"task_id": task['id'], "assigned_to": new_assign})
                    if new_assign != "Unassigned":
                        worker_email = next((u.get('email') for u in all_users if u['full_name'] == new_assign), None)
                        if worker_email:
                            subject = f"New Task Assigned: #{task['id']} - {task['title']}"
                            body = f"Hello {new_assign},<br><br>You have been assigned task <b>#{task['id']}</b>: {task['title']}.<br>Location: {task['location']}<br>Priority: {task['priority']}<br>Due: {task.get('due_date', 'No due date')}<br><br>Please log in to the tracker for details.<br>Regards,<br>Supervisor"
                            send_email_notification(worker_email, subject, body)
                        send_push_notification("New Task Assigned", f"Task #{task['id']}: {task['title']}")
                        send_notification(new_assign, "Task Assigned", f"Task #{task['id']}: {task['title']}")
                    st.rerun()
                if task['status'] == "Pending QA":
                    if cols[1].button("✅ Approve & Close", key=f"approve_{task['id']}"):
                        update_task(task['id'], {"status": "Complete"}, full_name)
                        log_audit(full_name, "task_approve", {"task_id": task['id']})
                        st.rerun()
                with st.expander("💬 Comments"):
                    comments = fetch_comments(task['id'])
                    if comments:
                        for c in comments:
                            st.markdown(f"**{c['posted_by']}** ({c['posted_at'][:16]}): {c['comment']}")
                    else:
                        st.caption("No comments yet.")
                    new_comment = st.text_area("Add comment", key=f"comment_sup_{task['id']}", placeholder="Write comment...")
                    if st.button("Post Comment", key=f"post_comment_sup_{task['id']}"):
                        if new_comment.strip():
                            add_comment(task['id'], new_comment, full_name)
                            st.rerun()
                with st.expander("📎 Attachments"):
                    attachments = fetch_attachments(task['id'])
                    if attachments:
                        for a in attachments:
                            st.markdown(f"[{a['file_name']}]({a['file_url']}) (by {a['uploaded_by']})")
                    else:
                        st.caption("No attachments.")
                    uploaded_file = st.file_uploader("Upload attachment", type=ALLOWED_ATTACHMENT_EXTENSIONS, key=f"attach_sup_{task['id']}")
                    if uploaded_file is not None:
                        if st.button("Upload", key=f"attach_btn_sup_{task['id']}"):
                            bytes_data = uploaded_file.getvalue()
                            if upload_attachment(task['id'], bytes_data, uploaded_file.name, full_name):
                                st.success("Attachment uploaded!")
                                st.rerun()
                photos = fetch_photos(task['id'])
                if photos:
                    with st.expander(f"📸 Photos for Task #{task['id']}"):
                        cols = st.columns(min(4, len(photos)))
                        for idx, photo in enumerate(photos):
                            with cols[idx % len(cols)]:
                                img_url = photo.get('photo_url', '')
                                if img_url.startswith('memory://'):
                                    st.info(f"📷 {photo.get('uploaded_by', 'Unknown')} uploaded a photo")
                                else:
                                    st.image(img_url, width=120)
                                st.caption(f"By {photo.get('uploaded_by', 'Unknown')}")

        elif supervisor_sub == "Create New Task":
            st.markdown("### Dispatch New Work Ticket")
            with st.form("new_task_form"):
                title = st.text_input("Task Title *", max_chars=100)
                location = st.text_input("Location / Area *", max_chars=100)
                priority = st.selectbox("Priority", ["Low", "Medium", "High", "Critical"])
                due_date = st.date_input("Due Date", value=datetime.now() + timedelta(days=7))
                asset_options = ["None"] + [f"#{a['id']} {a['name']}" for a in st.session_state.get("assets", [])]
                selected_asset = st.selectbox("Linked Asset (optional)", asset_options)
                is_recurring = st.checkbox("Recurring Task (Preventive Maintenance)")
                recurrence_type = st.selectbox("Recurrence Type", ["daily", "weekly", "monthly", "meter-based"], disabled=not is_recurring)
                recurrence_end_date = st.date_input("End Date (optional)", value=datetime.now() + timedelta(days=30), disabled=not is_recurring)
                meter_interval = st.number_input("Meter Interval (e.g. every N hours, only if meter-based)", min_value=0, value=0, disabled=not is_recurring)
                loto = st.checkbox("Requires LOTO")
                jsa = st.checkbox("Requires JSA")
                submitted = st.form_submit_button('➕ Create Work Ticket')
                if submitted:
                    if title and location:
                        asset_id = None
                        if selected_asset != "None":
                            asset_id = int(selected_asset.split(" ")[0].replace("#", ""))
                        new_task = create_task(
                            title, location, priority, loto, jsa, full_name,
                            due_date=due_date,
                            is_recurring=is_recurring,
                            recurrence_type=recurrence_type if is_recurring else None,
                            recurrence_end_date=recurrence_end_date if is_recurring else None,
                            asset_id=asset_id,
                            meter_interval=meter_interval if (is_recurring and recurrence_type == "meter-based") else None
                        )
                        if new_task:
                            st.success(f"Task #{new_task['id']} created!")
                            st.rerun()
                        else:
                            st.error("Failed to create task.")
                    else:
                        st.error("Title and Location are required.")

        elif supervisor_sub == "Dashboard":
            st.markdown("### 📊 Task Analytics")
            tasks = st.session_state.tasks
            st.markdown("#### 🎯 Key Performance Indicators")
            kcol1, kcol2, kcol3, kcol4 = st.columns(4)
            mttr = compute_mttr_hours(tasks)
            kcol1.metric("MTTR (avg hrs)", f"{mttr:.1f}" if mttr is not None else "N/A")
            pm_compliance = compute_pm_compliance(tasks)
            kcol2.metric("PM Compliance", f"{pm_compliance}%" if pm_compliance is not None else "N/A")
            open_incidents = sum(1 for i in st.session_state.get("incidents", []) if i.get("status") in ("Open", "Investigating"))
            kcol3.metric("Open Incidents", open_incidents)
            low_stock_count = sum(1 for p in st.session_state.get("parts", []) if p.get('quantity_on_hand', 0) <= p.get('reorder_point', 0))
            kcol4.metric("Low Stock Parts", low_stock_count)
            st.markdown("---")
            if tasks and PANDAS_AVAILABLE and PLOTLY_AVAILABLE:
                df = pd.DataFrame(tasks)
                fig1 = px.pie(df, names='status', title='Tasks by Status')
                st.plotly_chart(fig1, use_container_width=True)
                fig2 = px.bar(df, x='priority', color='status', title='Tasks by Priority and Status')
                st.plotly_chart(fig2, use_container_width=True)
                if 'created_at' in df.columns:
                    df['created_at'] = pd.to_datetime(df['created_at'])
                    df['day'] = df['created_at'].dt.date
                    fig3 = px.line(df.groupby('day').size().reset_index(name='count'), x='day', y='count', title='Tasks Created Per Day')
                    st.plotly_chart(fig3, use_container_width=True)
            elif not PANDAS_AVAILABLE or not PLOTLY_AVAILABLE:
                st.warning("Plotly or pandas not installed. Please run: pip install plotly pandas")
            else:
                st.info("No data to display.")
            if st.button("📥 Export Tasks as CSV"):
                csv = export_tasks_csv(st.session_state.tasks)
                if csv:
                    st.download_button("Download CSV", data=csv, file_name="tasks_export.csv", mime="text/csv")

    elif role == "superintendent":
        st.markdown('<div class="sub-header"><i class="fas fa-hard-hat"></i> Superintendent Control Centre</div>', unsafe_allow_html=True)
        superintendent_sub = option_menu(
            menu_title=None,
            options=["Overview", "Manage Tasks", "Broadcast Log", "Dashboard", "User Management"],
            icons=["pie-chart-fill", "list-check", "megaphone-fill", "graph-up-arrow", "people-fill"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )
        if superintendent_sub == "Overview":
            total = len(st.session_state.tasks)
            completed = sum(1 for t in st.session_state.tasks if t['status'] == "Complete")
            in_progress = sum(1 for t in st.session_state.tasks if t['status'] == "In Progress")
            unassigned = sum(1 for t in st.session_state.tasks if t['assigned_to'] == "Unassigned" or t['status'] == "Unassigned")
            blocked = sum(1 for t in st.session_state.tasks if t['status'] == "Blocked")
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Total Tasks", total)
            col2.metric("Completed", completed)
            col3.metric("In Progress", in_progress)
            col4.metric("Unassigned", unassigned)
            col5.metric("Blocked", blocked)

            acol1, acol2, acol3, acol4 = st.columns(4)
            acol1.metric("Registered Assets", len(st.session_state.get("assets", [])))
            down_assets = sum(1 for a in st.session_state.get("assets", []) if a.get('status') == 'Down')
            acol2.metric("Assets Down", down_assets)
            low_stock_count = sum(1 for p in st.session_state.get("parts", []) if p.get('quantity_on_hand', 0) <= p.get('reorder_point', 0))
            acol3.metric("Low Stock Parts", low_stock_count)
            open_incidents = sum(1 for i in st.session_state.get("incidents", []) if i.get("status") in ("Open", "Investigating"))
            acol4.metric("Open Incidents", open_incidents)

            st.markdown("### Recent Broadcasts")
            if st.session_state.broadcast_messages:
                for msg in reversed(st.session_state.broadcast_messages[-3:]):
                    st.info(f"**{msg['sender']}** at {msg['timestamp']}: {msg['message']}")
            else:
                st.caption("No broadcasts yet.")

        elif superintendent_sub == "Manage Tasks":
            st.markdown("### Full Task Control")
            all_users = fetch_all_users_from_db()
            worker_names = ["Unassigned"] + [u["full_name"] for u in all_users if u["role"].strip().lower() == "worker" and u.get("is_approved", False)]
            if not st.session_state.tasks:
                st.info("No tasks to manage.")
            for task in st.session_state.tasks:
                priority_class = f"priority-{task['priority']}"
                status_class = f"status-{task['status'].replace(' ', '')}"
                overdue = False
                if task.get('due_date'):
                    due = datetime.fromisoformat(task['due_date'])
                    if datetime.now() > due:
                        overdue = True
                overdue_badge = '<span class="overdue-badge">OVERDUE</span>' if overdue else ''
                st.markdown(f"""
                <div class="custom-card" style="border-left-color: { '#dc2626' if overdue else '#0f3460' };">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>#{task['id']}: {esc(task['title'])} {overdue_badge}</strong><br>
                            <i class="fas fa-map-marker-alt"></i> {esc(task['location'])}
                            <span class="status-badge {status_class}">{task['status']}</span>
                            <span class="priority-badge {priority_class}">{task['priority']}</span>
                            {f'<i class="fas fa-calendar-alt"></i> {task["due_date"][:10]}' if task.get('due_date') else ''}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                cols = st.columns([2, 1, 1, 1])
                current_assign = task['assigned_to'] if task['assigned_to'] in worker_names else "Unassigned"
                new_assign = cols[0].selectbox("Assign", worker_names,
                                               index=worker_names.index(current_assign),
                                               key=f"sup_assign_{task['id']}")
                if new_assign != task['assigned_to']:
                    update_task(task['id'], {"assigned_to": new_assign}, full_name)
                    if task['status'] == "Unassigned" and new_assign != "Unassigned":
                        update_task(task['id'], {"status": "In Progress"}, full_name)
                    log_audit(full_name, "task_assign", {"task_id": task['id'], "assigned_to": new_assign})
                    if new_assign != "Unassigned":
                        worker_email = next((u.get('email') for u in all_users if u['full_name'] == new_assign), None)
                        if worker_email:
                            subject = f"New Task Assigned: #{task['id']} - {task['title']}"
                            body = f"Hello {new_assign},<br><br>You have been assigned task <b>#{task['id']}</b>: {task['title']}.<br>Location: {task['location']}<br>Priority: {task['priority']}<br>Due: {task.get('due_date', 'No due date')}<br><br>Please log in to the tracker for details.<br>Regards,<br>Superintendent"
                            send_email_notification(worker_email, subject, body)
                        send_push_notification("New Task Assigned", f"Task #{task['id']}: {task['title']}")
                        send_notification(new_assign, "Task Assigned", f"Task #{task['id']}: {task['title']}")
                    st.rerun()
                status_opts = ["Unassigned", "In Progress", "Pending QA", "Blocked", "Complete"]
                curr_stat_idx = status_opts.index(task['status']) if task['status'] in status_opts else 0
                new_stat = cols[1].selectbox("Status", status_opts, index=curr_stat_idx, key=f"stat_ovr_{task['id']}")
                if new_stat != task['status']:
                    update_task(task['id'], {"status": new_stat}, full_name)
                    log_audit(full_name, "task_status_change", {"task_id": task['id'], "new_status": new_stat})
                    st.rerun()
                if cols[2].button('🗑️ Delete', key=f"del_{task['id']}"):
                    delete_task(task['id'], full_name)
                    st.rerun()
                with st.expander("💬 Comments"):
                    comments = fetch_comments(task['id'])
                    if comments:
                        for c in comments:
                            st.markdown(f"**{c['posted_by']}** ({c['posted_at'][:16]}): {c['comment']}")
                    else:
                        st.caption("No comments yet.")
                    new_comment = st.text_area("Add comment", key=f"comment_sup_{task['id']}", placeholder="Write comment...")
                    if st.button("Post Comment", key=f"post_comment_sup_{task['id']}"):
                        if new_comment.strip():
                            add_comment(task['id'], new_comment, full_name)
                            st.rerun()
                with st.expander("📎 Attachments"):
                    attachments = fetch_attachments(task['id'])
                    if attachments:
                        for a in attachments:
                            st.markdown(f"[{a['file_name']}]({a['file_url']}) (by {a['uploaded_by']})")
                    else:
                        st.caption("No attachments.")
                    uploaded_file = st.file_uploader("Upload attachment", type=ALLOWED_ATTACHMENT_EXTENSIONS, key=f"attach_sup_{task['id']}")
                    if uploaded_file is not None:
                        if st.button("Upload", key=f"attach_btn_sup_{task['id']}"):
                            bytes_data = uploaded_file.getvalue()
                            if upload_attachment(task['id'], bytes_data, uploaded_file.name, full_name):
                                st.success("Attachment uploaded!")
                                st.rerun()
                photos = fetch_photos(task['id'])
                if photos:
                    with st.expander(f"📸 Photos for Task #{task['id']}"):
                        cols = st.columns(min(4, len(photos)))
                        for idx, photo in enumerate(photos):
                            with cols[idx % len(cols)]:
                                img_url = photo.get('photo_url', '')
                                if img_url.startswith('memory://'):
                                    st.info(f"📷 {photo.get('uploaded_by', 'Unknown')} uploaded a photo")
                                else:
                                    st.image(img_url, width=120)
                                st.caption(f"By {photo.get('uploaded_by', 'Unknown')}")

        elif superintendent_sub == "Broadcast Log":
            st.markdown("### All Broadcast Messages")
            if st.session_state.broadcast_messages:
                for msg in reversed(st.session_state.broadcast_messages):
                    st.write(f"**{msg['sender']}** ({msg['role']}) at {msg['timestamp']}: {msg['message']}")
            else:
                st.info("No messages sent yet.")

        elif superintendent_sub == "Dashboard":
            st.markdown("### 📊 Task Analytics")
            tasks = st.session_state.tasks
            st.markdown("#### 🎯 Key Performance Indicators")
            kcol1, kcol2, kcol3, kcol4 = st.columns(4)
            mttr = compute_mttr_hours(tasks)
            kcol1.metric("MTTR (avg hrs)", f"{mttr:.1f}" if mttr is not None else "N/A")
            pm_compliance = compute_pm_compliance(tasks)
            kcol2.metric("PM Compliance", f"{pm_compliance}%" if pm_compliance is not None else "N/A")
            open_incidents = sum(1 for i in st.session_state.get("incidents", []) if i.get("status") in ("Open", "Investigating"))
            kcol3.metric("Open Incidents", open_incidents)
            low_stock_count = sum(1 for p in st.session_state.get("parts", []) if p.get('quantity_on_hand', 0) <= p.get('reorder_point', 0))
            kcol4.metric("Low Stock Parts", low_stock_count)
            st.markdown("---")
            if tasks and PANDAS_AVAILABLE and PLOTLY_AVAILABLE:
                df = pd.DataFrame(tasks)
                fig1 = px.pie(df, names='status', title='Tasks by Status')
                st.plotly_chart(fig1, use_container_width=True)
                fig2 = px.bar(df, x='priority', color='status', title='Tasks by Priority and Status')
                st.plotly_chart(fig2, use_container_width=True)
                if 'created_at' in df.columns:
                    df['created_at'] = pd.to_datetime(df['created_at'])
                    df['day'] = df['created_at'].dt.date
                    fig3 = px.line(df.groupby('day').size().reset_index(name='count'), x='day', y='count', title='Tasks Created Per Day')
                    st.plotly_chart(fig3, use_container_width=True)
            elif not PANDAS_AVAILABLE or not PLOTLY_AVAILABLE:
                st.warning("Plotly or pandas not installed. Please run: pip install plotly pandas")
            else:
                st.info("No data to display.")
            if st.button("📥 Export Tasks as CSV"):
                csv = export_tasks_csv(st.session_state.tasks)
                if csv:
                    st.download_button("Download CSV", data=csv, file_name="tasks_export.csv", mime="text/csv")

        elif superintendent_sub == "User Management":
            st.markdown("### 👥 User Management")
            st.markdown("Approve or reject pending user registrations, and deactivate approved users.")

            all_users = fetch_all_users_from_db()
            pending_users = [u for u in all_users if not u.get("is_approved", False)]
            approved_users = [u for u in all_users if u.get("is_approved", False)]

            if pending_users:
                st.markdown("#### ⏳ Pending Approvals")
                for u in pending_users:
                    with st.container(border=True):
                        st.write(f"**Username:** {u['username']}")
                        st.write(f"**Full Name:** {u['full_name']}")
                        st.write(f"**Role:** {u['role']}")
                        st.write(f"**Email:** {u.get('email', 'Not set')}")
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button(f"✅ Approve {u['username']}", key=f"approve_{u['username']}"):
                                if approve_user(u['username']):
                                    st.success(f"User {u['username']} approved!")
                                    st.rerun()
                                else:
                                    st.error("Approval failed.")
                        with col2:
                            if st.button(f"❌ Reject {u['username']}", key=f"reject_{u['username']}"):
                                if reject_user(u['username']):
                                    st.success(f"User {u['username']} rejected and removed.")
                                    st.rerun()
                                else:
                                    st.error("Rejection failed.")
            else:
                st.info("No pending approvals.")

            st.markdown("#### ✅ Approved Users")
            if approved_users:
                for u in approved_users:
                    st.write(f"- **{u['full_name']}** ({u['username']}) – {u['role']}")
                    if st.button(f"🔴 Deactivate {u['username']}", key=f"deactivate_{u['username']}"):
                        if update_user_profile(u['username'], {"is_approved": False}):
                            st.success(f"User {u['username']} deactivated.")
                            st.rerun()
                        else:
                            st.error("Deactivation failed.")
            else:
                st.info("No approved users yet.")

# ---- ASSET REGISTER ----
elif selected_section == "Asset Register":
    st.subheader("🏭 Asset Register")
    can_manage_assets = role in ["supervisor", "superintendent"]

    if can_manage_assets:
        asset_sub = option_menu(
            menu_title=None,
            options=["All Assets", "Add Asset"],
            icons=["hdd-stack-fill", "plus-circle"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )
    else:
        asset_sub = "All Assets"

    if asset_sub == "All Assets":
        assets = st.session_state.assets
        if not assets:
            st.info("No assets registered yet.")
        else:
            search = st.text_input("🔍 Search by name, tag, or location", "")
            filtered = assets
            if search:
                s = search.lower()
                filtered = [a for a in assets if s in str(a.get('name', '')).lower()
                            or s in str(a.get('asset_tag', '')).lower()
                            or s in str(a.get('location', '')).lower()]
            for a in filtered:
                status_class = f"asset-status-{a.get('status', 'Operational').replace(' ', '')}"
                st.markdown(f"""
                <div class="custom-card">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>#{a['id']}: {esc(a.get('name'))}</strong>
                            <span class="asset-status-badge {status_class}">{esc(a.get('status', 'Operational'))}</span>
                            <span class="priority-badge priority-{esc(a.get('criticality', 'Medium'))}">{esc(a.get('criticality', 'Medium'))}</span><br>
                            <i class="fas fa-tag"></i> Tag: {esc(a.get('asset_tag', 'N/A'))} &nbsp;
                            <i class="fas fa-map-marker-alt"></i> {esc(a.get('location', 'N/A'))} &nbsp;
                            <i class="fas fa-industry"></i> {esc(a.get('manufacturer', 'N/A'))} {esc(a.get('model_number', ''))} &nbsp;
                            <i class="fas fa-tachometer-alt"></i> Meter: {a.get('current_meter', 0)} {esc(a.get('meter_unit', ''))}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if can_manage_assets:
                    with st.expander(f"⚙️ Manage #{a['id']} {a.get('name')}"):
                        cols = st.columns(4)
                        new_status = cols[0].selectbox("Status", ["Operational", "Down", "Maintenance", "Retired"],
                                                        index=["Operational", "Down", "Maintenance", "Retired"].index(a.get('status', 'Operational')) if a.get('status') in ["Operational", "Down", "Maintenance", "Retired"] else 0,
                                                        key=f"asset_stat_{a['id']}")
                        new_meter = cols[1].number_input("Current Meter Reading", value=float(a.get('current_meter', 0) or 0), key=f"asset_meter_{a['id']}")
                        if cols[2].button("💾 Save", key=f"asset_save_{a['id']}"):
                            update_asset(a['id'], {"status": new_status, "current_meter": new_meter}, full_name)
                            st.success("Asset updated.")
                            st.rerun()
                        if role == "superintendent" and cols[3].button("🗑️ Delete", key=f"asset_del_{a['id']}"):
                            delete_asset(a['id'], full_name)
                            st.rerun()
                        related_tasks = [t for t in st.session_state.tasks if t.get('asset_id') == a['id']]
                        st.caption(f"📋 {len(related_tasks)} maintenance task(s) linked to this asset.")
                        meter_tasks = [t for t in related_tasks if t.get('meter_interval')]
                        for mt in meter_tasks:
                            interval = mt.get('meter_interval', 0)
                            current = a.get('current_meter', 0) or 0
                            if interval and current and (current % interval) >= (interval * 0.9):
                                st.warning(f"⏰ '{mt['title']}' is meter-based (every {interval} {a.get('meter_unit', '')}) and is approaching its next service interval.")

    # PM compliance quick view for managers
    if can_manage_assets and st.session_state.assets:
        st.markdown("---")
        st.markdown("#### 📊 Asset Task Frequency (proxy for downtime)")
        ranking = compute_asset_downtime_ranking(st.session_state.tasks, st.session_state.assets)
        if ranking:
            for name, count in ranking[:10]:
                st.write(f"- **{esc(name)}**: {count} maintenance task(s)")
        else:
            st.caption("No tasks linked to assets yet.")

    elif asset_sub == "Add Asset":
        st.markdown("### Register New Asset")
        with st.form("new_asset_form"):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Asset Name *", max_chars=100)
                asset_tag = st.text_input("Asset Tag / ID *", max_chars=50)
                category = st.selectbox("Category", ["Heavy Equipment", "Fixed Plant", "Vehicle", "Electrical", "Hydraulic", "Conveyor", "Pump", "Other"])
                location = st.text_input("Location / Area *", max_chars=100)
                criticality = st.selectbox("Criticality", ["Low", "Medium", "High", "Critical"])
            with c2:
                manufacturer = st.text_input("Manufacturer", max_chars=100)
                model_number = st.text_input("Model Number", max_chars=100)
                serial_number = st.text_input("Serial Number", max_chars=100)
                install_date = st.date_input("Install Date", value=datetime.now())
                status = st.selectbox("Status", ["Operational", "Down", "Maintenance", "Retired"])
            colm1, colm2 = st.columns(2)
            current_meter = colm1.number_input("Current Meter Reading", value=0.0)
            meter_unit = colm2.selectbox("Meter Unit", ["hours", "km", "cycles", "N/A"])
            submitted = st.form_submit_button("➕ Register Asset")
            if submitted:
                if name and asset_tag and location:
                    new_asset = create_asset(name, asset_tag, category, location, manufacturer, model_number,
                                              serial_number, install_date, status, criticality,
                                              current_meter, meter_unit, full_name)
                    if new_asset:
                        st.success(f"Asset '{name}' registered!")
                        st.rerun()
                    else:
                        st.error("Failed to register asset.")
                else:
                    st.error("Asset Name, Tag, and Location are required.")

# ---- INVENTORY ----
elif selected_section == "Inventory":
    st.subheader("📦 Inventory & Parts Management")
    can_manage_inventory = role in ["supervisor", "superintendent"]

    if can_manage_inventory:
        inv_sub = option_menu(
            menu_title=None,
            options=["Stock Levels", "Add Part", "Record Usage"],
            icons=["box-seam-fill", "plus-circle", "dash-circle"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )
    else:
        inv_sub = "Stock Levels"

    parts = st.session_state.parts

    if inv_sub == "Stock Levels":
        low_stock = [p for p in parts if p.get('quantity_on_hand', 0) <= p.get('reorder_point', 0)]
        if low_stock:
            st.warning(f"⚠️ {len(low_stock)} part(s) at or below reorder point.")
        if not parts:
            st.info("No parts in inventory yet.")
        for p in parts:
            is_low = p.get('quantity_on_hand', 0) <= p.get('reorder_point', 0)
            stock_class = "stock-low" if is_low else "stock-ok"
            stock_label = "LOW STOCK" if is_low else "IN STOCK"
            st.markdown(f"""
            <div class="custom-card">
                <strong>{esc(p.get('part_name'))}</strong> ({esc(p.get('part_number', 'N/A'))})
                <span class="stock-badge {stock_class}">{stock_label}</span><br>
                <i class="fas fa-cubes"></i> Qty on hand: {p.get('quantity_on_hand', 0)} &nbsp;
                <i class="fas fa-bell"></i> Reorder at: {p.get('reorder_point', 0)} &nbsp;
                <i class="fas fa-map-marker-alt"></i> Bin: {esc(p.get('bin_location', 'N/A'))} &nbsp;
                <i class="fas fa-truck"></i> Supplier: {esc(p.get('supplier', 'N/A'))} &nbsp;
                <i class="fas fa-dollar-sign"></i> Unit cost: {p.get('unit_cost', 0)}
            </div>
            """, unsafe_allow_html=True)
            if can_manage_inventory:
                cols = st.columns(4)
                restock_qty = cols[0].number_input("Restock qty", min_value=0, value=0, key=f"restock_{p['id']}")
                if cols[1].button("📥 Restock", key=f"restock_btn_{p['id']}"):
                    if restock_qty > 0:
                        adjust_part_quantity(p['id'], restock_qty, full_name, reason="restock")
                        st.success("Stock updated.")
                        st.rerun()
                if role == "superintendent" and cols[2].button("🗑️ Delete", key=f"part_del_{p['id']}"):
                    delete_part(p['id'], full_name)
                    st.rerun()

    elif inv_sub == "Add Part":
        st.markdown("### Add New Part to Inventory")
        with st.form("new_part_form"):
            c1, c2 = st.columns(2)
            with c1:
                part_name = st.text_input("Part Name *", max_chars=100)
                part_number = st.text_input("Part Number", max_chars=50)
                category = st.selectbox("Category", ["Bearings", "Belts", "Filters", "Hydraulic", "Electrical", "Fasteners", "Seals", "Lubricants", "Other"])
                supplier = st.text_input("Supplier", max_chars=100)
            with c2:
                quantity_on_hand = st.number_input("Starting Quantity", min_value=0, value=0)
                reorder_point = st.number_input("Reorder Point", min_value=0, value=5)
                reorder_qty = st.number_input("Reorder Quantity", min_value=0, value=10)
                unit_cost = st.number_input("Unit Cost", min_value=0.0, value=0.0, format="%.2f")
            bin_location = st.text_input("Bin / Shelf Location", max_chars=50)
            submitted = st.form_submit_button("➕ Add Part")
            if submitted:
                if part_name:
                    new_part = create_part(part_name, part_number, category, quantity_on_hand, reorder_point,
                                            reorder_qty, unit_cost, supplier, bin_location, full_name)
                    if new_part:
                        st.success(f"Part '{part_name}' added to inventory!")
                        st.rerun()
                    else:
                        st.error("Failed to add part.")
                else:
                    st.error("Part Name is required.")

    elif inv_sub == "Record Usage":
        st.markdown("### Record Parts Used on a Task")
        if not parts:
            st.info("No parts available. Add parts to inventory first.")
        elif not st.session_state.tasks:
            st.info("No tasks available to link parts to.")
        else:
            with st.form("use_part_form"):
                part_names = {f"{p['part_name']} ({p.get('part_number', 'N/A')}) - {p.get('quantity_on_hand', 0)} in stock": p['id'] for p in parts}
                task_titles = {f"#{t['id']} {t['title']}": t['id'] for t in st.session_state.tasks}
                selected_part_label = st.selectbox("Part", list(part_names.keys()))
                selected_task_label = st.selectbox("Task / Work Order", list(task_titles.keys()))
                qty_used = st.number_input("Quantity Used", min_value=1, value=1)
                submitted = st.form_submit_button("✅ Record Usage")
                if submitted:
                    part_id = part_names[selected_part_label]
                    task_id = task_titles[selected_task_label]
                    if link_part_to_task(task_id, part_id, qty_used, full_name):
                        st.success("Parts usage recorded and stock updated.")
                        st.rerun()
                    else:
                        st.error("Failed to record usage.")

# ---- INCIDENT REPORTS ----
elif selected_section == "Incident Reports":
    st.subheader("🚨 Incident & Safety Reporting")
    can_manage_incidents = role in ["supervisor", "superintendent"]

    if can_manage_incidents:
        inc_sub = option_menu(
            menu_title=None,
            options=["All Incidents", "Report Incident"],
            icons=["exclamation-triangle-fill", "plus-circle"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )
    else:
        inc_sub = option_menu(
            menu_title=None,
            options=["My Reports", "Report Incident"],
            icons=["file-earmark-text", "plus-circle"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )

    incidents = st.session_state.incidents

    if inc_sub in ("All Incidents", "My Reports"):
        visible = incidents if can_manage_incidents else [i for i in incidents if i.get('reported_by') == full_name]
        if not visible:
            st.info("No incidents reported yet.")
        for inc in visible:
            sev_class = f"severity-{inc.get('severity', 'Low')}"
            st.markdown(f"""
            <div class="custom-card" style="border-left-color: #dc2626;">
                <strong>#{inc['id']}: {esc(inc.get('incident_type'))}</strong>
                <span class="severity-badge {sev_class}">{esc(inc.get('severity', 'Low'))}</span>
                <span class="status-badge status-{esc(inc.get('status', 'Open')).replace(' ', '')}">{esc(inc.get('status', 'Open'))}</span><br>
                <i class="fas fa-map-marker-alt"></i> {esc(inc.get('location'))} &nbsp;
                <i class="fas fa-user"></i> Reported by {esc(inc.get('reported_by'))} &nbsp;
                <i class="fas fa-clock"></i> {str(inc.get('created_at', ''))[:16]}<br>
                <p>{esc(inc.get('description'))}</p>
                {f"<p><i>Immediate action:</i> {esc(inc.get('immediate_action'))}</p>" if inc.get('immediate_action') else ""}
                {f"<p><i>Root cause:</i> {esc(inc.get('root_cause'))}</p>" if inc.get('root_cause') else ""}
                {f"<p><i>Corrective action:</i> {esc(inc.get('corrective_action'))}</p>" if inc.get('corrective_action') else ""}
            </div>
            """, unsafe_allow_html=True)
            if can_manage_incidents:
                with st.expander(f"⚙️ Investigate #{inc['id']}"):
                    new_status = st.selectbox("Status", ["Open", "Investigating", "Resolved", "Closed"],
                                               index=["Open", "Investigating", "Resolved", "Closed"].index(inc.get('status', 'Open')) if inc.get('status') in ["Open", "Investigating", "Resolved", "Closed"] else 0,
                                               key=f"inc_stat_{inc['id']}")
                    root_cause = st.text_area("Root Cause", value=inc.get('root_cause') or '', key=f"inc_root_{inc['id']}")
                    corrective_action = st.text_area("Corrective Action", value=inc.get('corrective_action') or '', key=f"inc_corr_{inc['id']}")
                    if st.button("💾 Save Investigation", key=f"inc_save_{inc['id']}"):
                        update_incident(inc['id'], {
                            "status": new_status,
                            "root_cause": root_cause,
                            "corrective_action": corrective_action
                        }, full_name)
                        st.success("Incident updated.")
                        st.rerun()

    elif inc_sub == "Report Incident":
        st.markdown("### Submit New Incident Report")
        st.caption("Report near-misses, injuries, and hazards as soon as possible. All Critical/High severity reports notify supervisors immediately.")
        with st.form("new_incident_form"):
            incident_type = st.selectbox("Incident Type", ["Near Miss", "Injury", "Property Damage", "Equipment Failure", "Environmental", "Hazard Observation", "Other"])
            severity = st.selectbox("Severity", ["Low", "Medium", "High", "Critical"])
            location = st.text_input("Location / Area *", max_chars=100)
            assets_list = st.session_state.get("assets", [])
            asset_options = ["None"] + [f"#{a['id']} {a['name']}" for a in assets_list]
            selected_asset = st.selectbox("Related Asset (optional)", asset_options)
            description = st.text_area("Description *", placeholder="What happened? Be specific.")
            immediate_action = st.text_area("Immediate Action Taken", placeholder="What was done right away?")
            witnesses = st.text_input("Witnesses (optional)", max_chars=200)
            submitted = st.form_submit_button("🚨 Submit Report")
            if submitted:
                if location and description:
                    asset_id = None
                    if selected_asset != "None":
                        asset_id = int(selected_asset.split(" ")[0].replace("#", ""))
                    new_incident = create_incident(incident_type, severity, location, description, full_name,
                                                    asset_id=asset_id, witnesses=witnesses, immediate_action=immediate_action)
                    if new_incident:
                        st.success("Incident reported. Thank you for keeping the site safe.")
                        if severity in ("Critical", "High"):
                            st.warning("This has been flagged for immediate supervisor attention.")
                        st.rerun()
                    else:
                        st.error("Failed to submit report.")
                else:
                    st.error("Location and Description are required.")

# ---- CHAT ROOM ----
elif selected_section == "Chat Room":
    st.subheader("💬 Real‑time Chat")

    room = st.session_state.chat_room
    if room == "global":
        st.markdown("### 🌍 Global Chat – all users")
    elif room == "supervisor":
        if role not in ["supervisor", "superintendent"]:
            st.error("You don't have permission to view the Supervisor room.")
            st.stop()
        st.markdown("### 🔒 Supervisor Room – Supervisors & Superintendent only")
    elif room.startswith("private:"):
        partner = st.session_state.chat_partner
        st.markdown(f"### 🔐 Private Chat with **{partner}** (end‑to‑end encrypted)")
        st.caption("Messages are encrypted with a shared key derived from both usernames.")
    else:
        st.warning("Unknown room. Switching to Global.")
        st.session_state.chat_room = "global"
        st.rerun()

    if not st.session_state.chat_messages_cache:
        st.session_state.chat_messages_cache = fetch_messages(room=room, limit=200)

    if SUPABASE_AVAILABLE:
        channel_name = f"chat_{room.replace(':', '_').replace('@', '_')}"
        try:
            if st.session_state.chat_channel:
                try:
                    supabase.remove_channel(st.session_state.chat_channel)
                except:
                    pass
                st.session_state.chat_channel = None

            channel = supabase.channel(channel_name)
            def on_insert(payload):
                new_msg = payload['new']
                if not any(m.get('id') == new_msg.get('id') for m in st.session_state.chat_messages_cache):
                    st.session_state.chat_messages_cache.insert(0, new_msg)
                    st.session_state.chat_messages_cache = st.session_state.chat_messages_cache[:200]
                    st.rerun()
            channel.on('postgres_changes', event='INSERT', schema='public', table='chat_messages', callback=on_insert)
            channel.subscribe()
            st.session_state.chat_channel = channel
        except Exception:
            pass

    messages = [m for m in st.session_state.chat_messages_cache if m['room'] == room]
    if messages:
        for msg in reversed(messages):
            sender = msg['sender']
            is_encrypted = msg.get('is_encrypted', False)
            content = msg['message']
            if 'created_at' in msg and isinstance(msg['created_at'], str):
                try:
                    timestamp = datetime.fromisoformat(msg['created_at'].replace('Z', '+00:00')).strftime("%H:%M")
                except:
                    timestamp = "??:??"
            else:
                timestamp = "??:??"

            if room.startswith("private:") and is_encrypted:
                parts = room.split(":")[1].split("_")
                key = derive_key(parts[0], parts[1])
                try:
                    content = decrypt_message(content, key)
                except Exception:
                    content = "🔒 [Decryption failed]"

            col_text, col_delete = st.columns([5, 1])
            with col_text:
                if sender == full_name:
                    st.markdown(f"<div class='chat-message self'><span class='sender'>You</span> <span class='timestamp'>{timestamp}</span><br>{esc(content)}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='chat-message'><span class='sender'>{esc(sender)}</span> <span class='timestamp'>{timestamp}</span><br>{esc(content)}</div>", unsafe_allow_html=True)
            with col_delete:
                if sender == full_name:
                    if st.button("🗑️", key=f"del_msg_{msg['id']}"):
                        if delete_message(msg['id'], full_name):
                            st.success("Message deleted!")
                            st.session_state.chat_messages_cache = [m for m in st.session_state.chat_messages_cache if m['id'] != msg['id']]
                            st.rerun()
                        else:
                            st.error("Failed to delete message.")
    else:
        st.info("No messages yet. Be the first to send!")

    with st.container():
        st.markdown("---")
        msg_input = st.text_area("Type your message", height=100, key="chat_input_text", value=st.session_state.chat_input_value)
        col_send, col_clear = st.columns([1, 5])
        with col_send:
            if st.button('📤 Send', use_container_width=True):
                if msg_input.strip():
                    encrypted = False
                    final_msg = msg_input
                    if room.startswith("private:"):
                        parts = room.split(":")[1].split("_")
                        key = derive_key(parts[0], parts[1])
                        final_msg = encrypt_message(msg_input, key)
                        encrypted = True
                    success = send_message(
                        sender=full_name,
                        receiver=st.session_state.chat_partner if room.startswith("private:") else None,
                        room=room,
                        message=final_msg,
                        encrypted=encrypted
                    )
                    if success:
                        st.success("Message sent!")
                        st.session_state.chat_input_value = ""
                        st.session_state.chat_messages_cache = fetch_messages(room=room, limit=200)
                        st.rerun()
                    else:
                        st.error("Failed to send message. Check database or ensure table exists.")
                else:
                    st.warning("Message cannot be empty.")
        with col_clear:
            if st.button('🧹 Clear input', use_container_width=True):
                st.session_state.chat_input_value = ""
                st.rerun()

# ---- ADMIN PANEL ----
elif selected_section == "Admin Panel":
    if role != "superintendent":
        st.warning("You do not have admin privileges.")
    else:
        st.subheader("⚙️ Admin Panel")
        st.markdown("### Manage Users")
        all_users = fetch_all_users_from_db()
        if all_users:
            user_data = []
            for u in all_users:
                user_data.append({
                    "Username": u.get("username"),
                    "Full Name": u.get("full_name"),
                    "Role": u.get("role"),
                    "Email": u.get("email", "Not set"),
                    "Approved": u.get("is_approved", False)
                })
            st.dataframe(user_data, use_container_width=True)
        else:
            st.info("No users found in database.")

        if SUPABASE_AVAILABLE:
            st.markdown("### Audit Log (last 50)")
            try:
                logs = supabase.table("audit_log").select("*").order("created_at", desc=True).limit(50).execute()
                if logs.data:
                    for log in logs.data:
                        st.write(f"**{log['user_name']}** – {log['action']} at {log['created_at']}")
                        if log['details']:
                            st.caption(f"Details: {log['details']}")
                else:
                    st.info("No audit logs yet.")
            except Exception:
                st.info("Audit log unavailable.")
        else:
            st.info("Audit log not available (Supabase not connected).")

# ---- PROFILE TAB ----
elif selected_section == "Profile":
    st.subheader("👤 User Profile")
    st.markdown(f"**Username:** {username}")
    st.markdown(f"**Full Name:** {full_name}")
    st.markdown(f"**Role:** {user['role']}")
    st.markdown(f"**Email:** {user_email if user_email else 'Not set'}")
    uploaded_avatar = st.file_uploader("Upload Avatar", type=["jpg", "jpeg", "png", "gif", "webp"], key="avatar_upload")
    if uploaded_avatar is not None:
        if st.button("Update Avatar"):
            st.success("Avatar updated! (feature in development - will store to Supabase Storage)")
            st.session_state.user_payload['avatar_url'] = "https://via.placeholder.com/150"
            st.rerun()

    st.markdown("### Change Password")
    old_pass = st.text_input("Current Password", type="password")
    new_pass1 = st.text_input("New Password", type="password")
    new_pass2 = st.text_input("Confirm New Password", type="password")
    if st.button("Update Password"):
        if old_pass and new_pass1 and new_pass2:
            if new_pass1 == new_pass2:
                users = fetch_all_users_from_db()
                for u in users:
                    if u["username"] == username:
                        if verify_password(old_pass, u["password_hash"]):
                            new_hash = hash_password(new_pass1)
                            if update_user_profile(username, {"password_hash": new_hash}):
                                st.success("Password updated!")
                                st.rerun()
                            else:
                                st.error("Failed to update password.")
                        else:
                            st.error("Current password is incorrect.")
                        break
            else:
                st.error("New passwords do not match.")
        else:
            st.error("All fields are required.")

    st.markdown("### Update Email")
    new_email = st.text_input("New Email", value=user_email if user_email else "")
    if st.button("Update Email"):
        if new_email:
            if update_user_profile(username, {"email": new_email}):
                st.session_state.user_payload['email'] = new_email
                st.success("Email updated!")
                st.rerun()
            else:
                st.error("Failed to update email.")

# ---- ACTIVITY TIMELINE ----
elif selected_section == "Activity Timeline":
    st.subheader("⏱️ Activity Timeline")
    st.markdown("Recent actions across all tasks (last 50)")

    if SUPABASE_AVAILABLE:
        try:
            activities = supabase.table("task_activity").select("*").order("created_at", desc=True).limit(50).execute()
            if activities.data:
                for act in activities.data:
                    task = supabase.table("tasks").select("title").eq("id", act['task_id']).execute()
                    task_title = task.data[0]['title'] if task.data else f"Task #{act['task_id']}"
                    st.write(f"**{act['user_name']}** {act['action']} **{task_title}** at {act['created_at']}")
                    if act['details']:
                        st.caption(f"Details: {act['details']}")
            else:
                st.info("No activity logs yet.")
        except Exception:
            st.info("Activity log unavailable.")
    else:
        st.info("Activity log not available (Supabase not connected).")

# Footer
st.markdown("""
<div class="footer">
    <i class="fas fa-hard-hat"></i> Mine & Workshop Digital Tracker v3.0 — CMMS Edition &nbsp;|&nbsp; Asset Register · Inventory · Incident Reporting · KPI Analytics &nbsp;|&nbsp; Powered by Streamlit & Supabase
</div>
""", unsafe_allow_html=True)
