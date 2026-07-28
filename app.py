import streamlit as st
import requests
from datetime import datetime, timedelta
import hashlib
import base64
import os
import json
import time
from io import BytesIO
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

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
# 0. SECRETS AND CONFIG (with fallback)
# -------------------------------
if 'SUPABASE_URL' in st.secrets:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    USING_HARDCODED = False
else:
    SUPABASE_URL = "https://xvfbxogzefhmitrtykce.supabase.co"
    SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh2ZmJ4b2d6ZWZobWl0cnR5a2NlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ4MDMxMjEsImV4cCI6MjEwMDM3OTEyMX0.OP6VM6dIcCJGDetAdP53nrElhSLnZXg3m16t9dy6nE0"
    USING_HARDCODED = True

SESSION_TIMEOUT_MINUTES = st.secrets.get("SESSION_TIMEOUT_MINUTES", 60) if 'SESSION_TIMEOUT_MINUTES' in st.secrets else 60
MAX_UPLOAD_SIZE_MB = st.secrets.get("MAX_UPLOAD_SIZE_MB", 5) if 'MAX_UPLOAD_SIZE_MB' in st.secrets else 5
MAX_UPLOAD_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# Use Supabase client
try:
    from supabase import create_client, Client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    st.warning("Supabase library not installed. Install with: pip install supabase")

# -------------------------------
# 1. CUSTOM CSS + FONT AWESOME + THEME
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
    .main-header { color: #f8fafc; }
    .sub-header { color: #94a3b8; }
    .css-1d391kg { background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%); }
    .custom-card { background: #1e293b; border-color: #334155; color: #e2e8f0; }
    .task-card { background: #1e293b; border-color: #334155; color: #e2e8f0; }
    .metric-box { background: #1e293b; border-color: #334155; color: #e2e8f0; }
    .stTabs [data-baseweb="tab"] { background: #1e293b; color: #e2e8f0; border-color: #334155; }
    .stTabs [aria-selected="true"] { background: #2563eb; color: white; }
    .stFileUploader { background: #1e293b; border-color: #334155; }
    .streamlit-expanderHeader { background: #1e293b; color: #e2e8f0; }
    .footer { border-top-color: #334155; color: #94a3b8; }
</style>
"""
light_css = """
<style>
    .stApp { background-color: #f8fafc; }
    .main-header { color: #1e293b; }
    .sub-header { color: #475569; }
    .css-1d391kg { background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%); }
    .custom-card { background: white; border-color: #e8ecf0; color: #1e293b; }
    .task-card { background: white; border-color: #e8ecf0; color: #1e293b; }
    .metric-box { background: white; border-color: #e2e8f0; color: #1e293b; }
    .stTabs [data-baseweb="tab"] { background: white; color: #1e293b; border-color: #e2e8f0; }
    .stTabs [aria-selected="true"] { background: #2563eb; color: white; }
    .stFileUploader { background: #f8fafc; border-color: #cbd5e1; }
    .streamlit-expanderHeader { background: #f1f5f9; color: #1e293b; }
    .footer { border-top-color: #e2e8f0; color: #94a3b8; }
</style>
"""

theme_css = dark_css if st.session_state.dark_mode else light_css

st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
""" + theme_css + """
<style>
    .main-header { font-size: 2.5rem; font-weight: 700; margin-bottom: 0.5rem; }
    .main-header i { color: #2563eb; margin-right: 10px; }
    .sub-header { font-size: 1.2rem; margin-bottom: 1.5rem; }
    .css-1d391kg .stButton button { background-color: #3b82f6; color: white; border-radius: 8px; border: none; padding: 0.5rem 1rem; transition: 0.3s; }
    .css-1d391kg .stButton button:hover { background-color: #2563eb; transform: scale(1.02); }
    .custom-card { border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06); padding: 1.2rem; margin-bottom: 1rem; border-left: 4px solid #2563eb; transition: 0.2s; }
    .custom-card:hover { box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); transform: translateY(-2px); }
    .priority-Critical { border-left-color: #dc2626; }
    .priority-High { border-left-color: #f59e0b; }
    .priority-Medium { border-left-color: #3b82f6; }
    .priority-Low { border-left-color: #10b981; }
    .status-badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.8rem; font-weight: 600; color: white; }
    .status-Unassigned { background: #94a3b8; }
    .status-InProgress { background: #3b82f6; }
    .status-PendingQA { background: #f59e0b; }
    .status-Blocked { background: #dc2626; }
    .status-Complete { background: #10b981; }
    .chat-message { padding: 0.5rem 1rem; border-radius: 8px; margin: 0.2rem 0; background: #f1f5f9; border-left: 3px solid #3b82f6; }
    .chat-message.self { background: #dbeafe; border-left-color: #2563eb; }
    .chat-message .sender { font-weight: 600; }
    .chat-message .timestamp { font-size: 0.7rem; color: #64748b; margin-left: 0.5rem; }
    .metric-box { border-radius: 10px; padding: 1rem; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; }
    .metric-box .value { font-size: 2rem; font-weight: 700; }
    .metric-box .label { font-size: 0.9rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 0.5rem; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px 8px 0 0; padding: 0.5rem 1rem; border: 1px solid #e2e8f0; border-bottom: none; }
    .stTabs [aria-selected="true"] { background: #2563eb; color: white; border-color: #2563eb; }
    .stFileUploader { border: 2px dashed #94a3b8; border-radius: 8px; padding: 0.5rem; background: #f8fafc; }
    .streamlit-expanderHeader { border-radius: 8px; }
    .footer { text-align: center; margin-top: 2rem; padding: 1rem; font-size: 0.8rem; border-top: 1px solid #e2e8f0; }
</style>
""", unsafe_allow_html=True)

# -------------------------------
# 2. PASSWORD HASHING (universal)
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
# 3. EMAIL NOTIFICATION (SMTP)
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
    except Exception:
        return False

# -------------------------------
# 4. IMAGE VALIDATION
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

# -------------------------------
# 5. USER FUNCTIONS (with universal verification)
# -------------------------------
def fetch_all_users_from_db():
    if not SUPABASE_AVAILABLE:
        fallback = [
            {"username": "supervisor1", "full_name": "Sarah Connor", "role": "Supervisor", "password_hash": hash_password("super789"), "email": "supervisor1@example.com", "avatar_url": None},
            {"username": "superintendent1", "full_name": "Anaba Moses", "role": "Superintendent", "password_hash": hash_password("boss000"), "email": "superintendent1@example.com", "avatar_url": None},
            {"username": "worker1", "full_name": "John Doe", "role": "Worker", "password_hash": hash_password("worker123"), "email": "worker1@example.com", "avatar_url": None}
        ]
        return fallback
    try:
        res = supabase.table("facility_users").select("*").execute()
        if res.data:
            return res.data
        else:
            return []
    except Exception:
        fallback = [
            {"username": "supervisor1", "full_name": "Sarah Connor", "role": "Supervisor", "password_hash": hash_password("super789"), "email": "supervisor1@example.com", "avatar_url": None},
            {"username": "superintendent1", "full_name": "Anaba Moses", "role": "Superintendent", "password_hash": hash_password("boss000"), "email": "superintendent1@example.com", "avatar_url": None},
            {"username": "worker1", "full_name": "John Doe", "role": "Worker", "password_hash": hash_password("worker123"), "email": "worker1@example.com", "avatar_url": None}
        ]
        return fallback

def register_user_to_db(username, name, role, password, email=None):
    if not SUPABASE_AVAILABLE:
        return False
    try:
        hashed = hash_password(password)
        payload = {"username": username, "full_name": name, "role": role, "password_hash": hashed, "email": email}
        supabase.table("facility_users").insert(payload).execute()
        log_audit(name, "user_register", {"username": username, "role": role})
        return True
    except Exception:
        return False

def authenticate_user(username, password):
    users = fetch_all_users_from_db()
    for u in users:
        if u["username"].lower() == username.lower():
            if verify_password(password, u["password_hash"]):
                return u
    return None

def update_user_profile(username, updates):
    if not SUPABASE_AVAILABLE:
        # Update in memory fallback?
        return False
    try:
        supabase.table("facility_users").update(updates).eq("username", username).execute()
        return True
    except Exception:
        return False

# -------------------------------
# 6. TASK FUNCTIONS (with due date)
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
    except Exception:
        return st.session_state.get("tasks_memory", [])

def create_task(title, location, priority, loto, jsa, created_by, due_date=None):
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
            "due_date": due_date.isoformat() if due_date else None
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
            "due_date": due_date.isoformat() if due_date else None
        }
        res = supabase.table("tasks").insert(new_task).execute()
        if res.data:
            task = res.data[0]
            log_audit(created_by, "task_create", {"task_id": task["id"]})
            return task
    except Exception:
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
        current = supabase.table("tasks").select("*").eq("id", task_id).execute()
        if current.data:
            old = current.data[0]
        else:
            old = {}
        supabase.table("tasks").update(updates).eq("id", task_id).execute()
        log_audit(updated_by, "task_update", {"task_id": task_id, "old": old, "new": updates})
        return True
    except Exception:
        return False

def delete_task(task_id, deleted_by):
    if not SUPABASE_AVAILABLE:
        st.session_state.tasks_memory = [t for t in st.session_state.get("tasks_memory", []) if t["id"] != task_id]
        log_audit(deleted_by, "task_delete_memory", {"task_id": task_id})
        return True
    try:
        supabase.table("tasks").delete().eq("id", task_id).execute()
        log_audit(deleted_by, "task_delete", {"task_id": task_id})
        return True
    except Exception:
        return False

# -------------------------------
# 7. PHOTO FUNCTIONS (with fallback)
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
                except Exception:
                    pass
        except Exception:
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
    except Exception:
        pass
    memory_photos = st.session_state.get("photos_memory", [])
    memory_photos = [p for p in memory_photos if p["task_id"] == task_id]
    all_photos = db_photos + memory_photos
    all_photos.sort(key=lambda x: x.get('uploaded_at', ''), reverse=True)
    return all_photos

# -------------------------------
# 8. FILE ATTACHMENTS (PDF/DOC)
# -------------------------------
def upload_attachment(task_id, file_bytes, filename, uploaded_by):
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
    except Exception:
        return []
# -------------------------------
# 9. TASK COMMENTS
# -------------------------------
def add_comment(task_id, comment, posted_by):
    if not SUPABASE_AVAILABLE:
        st.session_state.setdefault("comments_memory", []).append({
            "task_id": task_id,
            "comment": comment,
            "posted_by": posted_by,
            "posted_at": datetime.now().isoformat()
        })
        log_audit(posted_by, "comment_add_memory", {"task_id": task_id, "comment": comment, "posted_by": posted_by})
        supabase.table("task_comments").insert(data).execute()
        log_audit(posted_by, "comment_add", {"task_id": task_id, "comment": comment[:50]})
        return True
    except Exception:
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
    except Exception:
        return []
# -------------------------------
# 10. CHAT FUNCTIONS (unchanged)
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
    except Exception:
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
    except Exception:
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
        except Exception:
            return False

# -------------------------------
# 11. ENCRYPTION HELPERS
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
# 12. EXPORT REPORTS
# -------------------------------
def export_tasks_csv(tasks):
    if not tasks:
        return None
    df = pd.DataFrame(tasks)
    # Select columns to export
    cols = ['id', 'title', 'location', 'status', 'priority', 'assigned_to', 'due_date', 'created_at']
    df = df[[c for c in cols if c in df.columns]]
    return df.to_csv(index=False)

# -------------------------------
# 13. PUSH NOTIFICATIONS
# -------------------------------
def send_push_notification(title, body):
    try:
        # Use Streamlit's built-in toast for now; for true push, need service worker + Web Push API.
        st.toast(f"{title}: {body}")
    except:
        pass

# -------------------------------
# 14. SESSION STATE INIT
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

# -------------------------------
# 15. SESSION TIMEOUT CHECK
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
# 16. AUTHENTICATION GATEWAY (with forms)
# -------------------------------
if not st.session_state.authenticated:
    st.markdown('<div class="main-header"><i class="fas fa-hard-hat"></i> Mine & Workshop Digital Tracker</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header"><i class="fas fa-shield-alt"></i> Secure Login Gateway</div>', unsafe_allow_html=True)

    with st.form("login_form"):
        user_in = st.text_input("Username", placeholder="Enter your username").strip().lower()
        pass_in = st.text_input("Password", type="password", placeholder="Enter your password")
        login_submitted = st.form_submit_button('🔐 Authenticate Profile', use_container_width=True)

    if login_submitted:
        matched_user = authenticate_user(user_in, pass_in)
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
        else:
            st.error("Invalid credentials or database unreachable.")

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
                    st.success(f"Account '{reg_user}' created! Please log in.")
                else:
                    st.error("Registration failed. Database error.")
        else:
            st.error("All fields are mandatory.")
    st.stop()
else:
    check_timeout()

# -------------------------------
# 17. PWA MANIFEST & SERVICE WORKER
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
# 18. MAIN APP
# -------------------------------
user = st.session_state.user_payload
full_name = user['name']
username = user['username']
role = user['role'].strip().lower()
user_email = user.get('email', None)
avatar_url = user.get('avatar_url', None)

# Sidebar
with st.sidebar:
    # User profile mini
    col1, col2 = st.columns([1, 3])
    with col1:
        if avatar_url:
            st.image(avatar_url, width=50)
        else:
            st.markdown('<i class="fas fa-user-circle" style="font-size: 2.5rem; color: #3b82f6;"></i>', unsafe_allow_html=True)
    with col2:
        st.markdown(f"**{full_name}**")
        st.markdown(f"<small>{user['role']}</small>", unsafe_allow_html=True)

    if USING_HARDCODED:
        st.caption('⚠️ Using hardcoded Supabase – set secrets.toml for production')

    # Theme toggle
    if st.button("🌓 Toggle Theme", use_container_width=True):
        st.session_state.dark_mode = not st.session_state.dark_mode
        st.rerun()

    # Broadcast sender
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
                # Push notification to all workers (in browser)
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
    other_users = [u["full_name"] for u in all_users if u["full_name"] != full_name]
    if other_users:
        selected_user = st.selectbox("Choose contact", other_users)
        if st.button("🔐 Open Private Chat", use_container_width=True):
            sorted_names = sorted([full_name, selected_user])
            room_name = f"private:{sorted_names[0]}_{sorted_names[1]}"
            st.session_state.chat_room = room_name
            st.session_state.chat_partner = selected_user
            st.rerun()
    else:
        st.info("No other users available.")

    st.markdown("---")
    st.markdown("👤 **Profile**")
    if st.button("👤 My Profile", use_container_width=True):
        st.session_state.profile_tab = True
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

# Profile tab logic
if 'profile_tab' not in st.session_state:
    st.session_state.profile_tab = False

# Fetch tasks (merge DB + memory)
db_tasks = fetch_all_tasks()
if db_tasks:
    st.session_state.tasks = db_tasks
else:
    st.session_state.tasks = st.session_state.tasks_memory

# -------------------------------
# 19. TABS: TASKS, CHAT, ADMIN, PROFILE
# -------------------------------
tabs_list = ['📋 Task Dashboard', '💬 Chat Room', '⚙️ Admin Panel']
if role in ["worker", "supervisor", "superintendent"]:
    tabs_list.append('👤 Profile')
tab_tasks, tab_chat, tab_admin, tab_profile = st.tabs(tabs_list)

# ---- TASK DASHBOARD ----
with tab_tasks:
    if role == "worker":
        st.markdown('<div class="sub-header"><i class="fas fa-hard-hat"></i> Field Worker Workspace</div>', unsafe_allow_html=True)
        if st.session_state.broadcast_messages:
            st.info("📢 Latest Broadcasts:")
            for msg in reversed(st.session_state.broadcast_messages[-5:]):
                st.warning(f"**{msg['sender']}** ({msg['role']}) at {msg['timestamp']}: {msg['message']}")

        tab_my, tab_unassigned = st.tabs([
            '📋 My Assigned Tasks',
            '📥 Unassigned Board'
        ])

        with tab_my:
            my_tasks = [t for t in st.session_state.tasks if t['assigned_to'] == full_name]
            if not my_tasks:
                st.info("No tasks assigned to you.")
            else:
                for idx, task in enumerate(my_tasks):
                    with st.container(border=True):
                        st.markdown(f"**Task #{task['id']}:** {task['title']}")
                        st.write(f"📍 {task['location']} | Priority: **{task['priority']}** | Status: `{task['status']}`")
                        if task.get('due_date'):
                            due = datetime.fromisoformat(task['due_date']).strftime("%Y-%m-%d %H:%M")
                            st.write(f"📅 Due: {due}")
                            if datetime.now() > datetime.fromisoformat(task['due_date']):
                                st.error("⚠️ Overdue!")
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

                        # Comments
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

                        # Attachments
                        with st.expander("📎 Attachments"):
                            attachments = fetch_attachments(task['id'])
                            if attachments:
                                for a in attachments:
                                    st.markdown(f"[{a['file_name']}]({a['file_url']}) (uploaded by {a['uploaded_by']})")
                            else:
                                st.caption("No attachments.")
                            uploaded_file = st.file_uploader("Upload attachment (PDF, DOC, etc.)", key=f"attach_{task['id']}_{idx}")
                            if uploaded_file is not None:
                                if st.button("Upload Attachment", key=f"attach_btn_{task['id']}_{idx}"):
                                    bytes_data = uploaded_file.getvalue()
                                    if upload_attachment(task['id'], bytes_data, uploaded_file.name, full_name):
                                        st.success("Attachment uploaded!")
                                        st.rerun()

                        # Photo upload
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

        with tab_unassigned:
            unassigned = [t for t in st.session_state.tasks if t['assigned_to'] == "Unassigned" or t['status'] == "Unassigned"]
            if not unassigned:
                st.success("🎉 No unassigned tasks at the moment.")
            else:
                for task in unassigned:
                    with st.container(border=True):
                        st.markdown(f"**#{task['id']}:** {task['title']}")
                        st.write(f"📍 {task['location']} | Priority: **{task['priority']}**")
                        if task.get('due_date'):
                            due = datetime.fromisoformat(task['due_date']).strftime("%Y-%m-%d %H:%M")
                            st.write(f"📅 Due: {due}")

    elif role == "supervisor":
        st.markdown('<div class="sub-header"><i class="fas fa-clipboard"></i> Supervisor Operations Desk</div>', unsafe_allow_html=True)
        tab_manage, tab_create, tab_dashboard = st.tabs([
            '📋 Manage All Tasks',
            '➕ Create New Task',
            '📊 Dashboard'
        ])
        with tab_manage:
            st.markdown("### All Maintenance Tasks")
            all_users = fetch_all_users_from_db()
            worker_names = ["Unassigned"] + [u["full_name"] for u in all_users if u["role"].strip().lower() == "worker"]
            if not st.session_state.tasks:
                st.info("No tasks found.")
            for task in st.session_state.tasks:
                with st.container(border=True):
                    st.markdown(f"**#{task['id']}:** {task['title']}")
                    st.write(f"📍 {task['location']} | Status: `{task['status']}` | Priority: {task['priority']}")
                    if task.get('due_date'):
                        due = datetime.fromisoformat(task['due_date']).strftime("%Y-%m-%d %H:%M")
                        st.write(f"📅 Due: {due}")
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
                            # Push notification
                            send_push_notification("New Task Assigned", f"Task #{task['id']}: {task['title']}")
                        st.rerun()
                    if task['status'] == "Pending QA":
                        if cols[1].button("✅ Approve & Close", key=f"approve_{task['id']}"):
                            update_task(task['id'], {"status": "Complete"}, full_name)
                            log_audit(full_name, "task_approve", {"task_id": task['id']})
                            st.rerun()
                    # Comments
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
                    # Attachments
                    with st.expander("📎 Attachments"):
                        attachments = fetch_attachments(task['id'])
                        if attachments:
                            for a in attachments:
                                st.markdown(f"[{a['file_name']}]({a['file_url']}) (by {a['uploaded_by']})")
                        else:
                            st.caption("No attachments.")
                        uploaded_file = st.file_uploader("Upload attachment", key=f"attach_sup_{task['id']}")
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

        with tab_create:
            st.markdown("### Dispatch New Work Ticket")
            with st.form("new_task_form"):
                title = st.text_input("Task Title *", max_chars=100)
                location = st.text_input("Location / Area *", max_chars=100)
                priority = st.selectbox("Priority", ["Low", "Medium", "High", "Critical"])
                due_date = st.date_input("Due Date", value=datetime.now() + timedelta(days=7))
                loto = st.checkbox("Requires LOTO")
                jsa = st.checkbox("Requires JSA")
                submitted = st.form_submit_button('➕ Create Work Ticket')
                if submitted:
                    if title and location:
                        new_task = create_task(title, location, priority, loto, jsa, full_name, due_date)
                        if new_task:
                            st.success(f"Task #{new_task['id']} created!")
                            st.rerun()
                        else:
                            st.error("Failed to create task.")
                    else:
                        st.error("Title and Location are required.")

        with tab_dashboard:
            st.markdown("### 📊 Task Analytics")
            if st.session_state.tasks:
                df = pd.DataFrame(st.session_state.tasks)
                fig1 = px.pie(df, names='status', title='Tasks by Status')
                st.plotly_chart(fig1, use_container_width=True)
                fig2 = px.bar(df, x='priority', color='status', title='Tasks by Priority and Status')
                st.plotly_chart(fig2, use_container_width=True)
                # Completion trend (if created_at exists)
                if 'created_at' in df.columns:
                    df['created_at'] = pd.to_datetime(df['created_at'])
                    df['day'] = df['created_at'].dt.date
                    fig3 = px.line(df.groupby('day').size().reset_index(name='count'), x='day', y='count', title='Tasks Created Per Day')
                    st.plotly_chart(fig3, use_container_width=True)
            else:
                st.info("No data to display.")
            # Export report
            if st.button("📥 Export Tasks as CSV"):
                csv = export_tasks_csv(st.session_state.tasks)
                if csv:
                    st.download_button("Download CSV", data=csv, file_name="tasks_export.csv", mime="text/csv")

    elif role == "superintendent":
        st.markdown('<div class="sub-header"><i class="fas fa-hard-hat"></i> Superintendent Control Centre</div>', unsafe_allow_html=True)
        tab_overview, tab_manage, tab_broadcasts, tab_dashboard = st.tabs([
            '📊 Overview',
            '📋 Manage Tasks',
            '📢 Broadcast Log',
            '📊 Dashboard'
        ])
        with tab_overview:
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
            st.markdown("### Recent Broadcasts")
            if st.session_state.broadcast_messages:
                for msg in reversed(st.session_state.broadcast_messages[-3:]):
                    st.info(f"**{msg['sender']}** at {msg['timestamp']}: {msg['message']}")
            else:
                st.caption("No broadcasts yet.")
        with tab_manage:
            st.markdown("### Full Task Control")
            all_users = fetch_all_users_from_db()
            worker_names = ["Unassigned"] + [u["full_name"] for u in all_users if u["role"].strip().lower() == "worker"]
            if not st.session_state.tasks:
                st.info("No tasks to manage.")
            for task in st.session_state.tasks:
                with st.container(border=True):
                    st.markdown(f"**#{task['id']}:** {task['title']}")
                    st.write(f"📍 {task['location']} | Status: `{task['status']}` | Priority: {task['priority']}")
                    if task.get('due_date'):
                        due = datetime.fromisoformat(task['due_date']).strftime("%Y-%m-%d %H:%M")
                        st.write(f"📅 Due: {due}")
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
                    # Comments, attachments, photos (same as supervisor)
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
                        uploaded_file = st.file_uploader("Upload attachment", key=f"attach_sup_{task['id']}")
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
        with tab_broadcasts:
            st.markdown("### All Broadcast Messages")
            if st.session_state.broadcast_messages:
                for msg in reversed(st.session_state.broadcast_messages):
                    st.write(f"**{msg['sender']}** ({msg['role']}) at {msg['timestamp']}: {msg['message']}")
            else:
                st.info("No messages sent yet.")
        with tab_dashboard:
            st.markdown("### 📊 Task Analytics")
            if st.session_state.tasks:
                df = pd.DataFrame(st.session_state.tasks)
                fig1 = px.pie(df, names='status', title='Tasks by Status')
                st.plotly_chart(fig1, use_container_width=True)
                fig2 = px.bar(df, x='priority', color='status', title='Tasks by Priority and Status')
                st.plotly_chart(fig2, use_container_width=True)
                if 'created_at' in df.columns:
                    df['created_at'] = pd.to_datetime(df['created_at'])
                    df['day'] = df['created_at'].dt.date
                    fig3 = px.line(df.groupby('day').size().reset_index(name='count'), x='day', y='count', title='Tasks Created Per Day')
                    st.plotly_chart(fig3, use_container_width=True)
            else:
                st.info("No data to display.")
            if st.button("📥 Export Tasks as CSV"):
                csv = export_tasks_csv(st.session_state.tasks)
                if csv:
                    st.download_button("Download CSV", data=csv, file_name="tasks_export.csv", mime="text/csv")

# ---- CHAT ROOM (REAL-TIME) ----
with tab_chat:
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
                    st.markdown(f"**You** ({timestamp}): {content}")
                else:
                    st.markdown(f"**{sender}** ({timestamp}): {content}")
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
with tab_admin:
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
                    "Email": u.get("email", "Not set")
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
with tab_profile:
    st.subheader("👤 User Profile")
    st.markdown(f"**Username:** {username}")
    st.markdown(f"**Full Name:** {full_name}")
    st.markdown(f"**Role:** {user['role']}")
    st.markdown(f"**Email:** {user_email if user_email else 'Not set'}")
    # Avatar upload
    uploaded_avatar = st.file_uploader("Upload Avatar", type=["jpg", "jpeg", "png", "gif", "webp"], key="avatar_upload")
    if uploaded_avatar is not None:
        if st.button("Update Avatar"):
            # For now, just store in memory; in production, upload to Supabase Storage
            st.success("Avatar updated! (feature in development - will store to Supabase Storage)")
            # We'll implement actual storage later; for now just keep in session
            st.session_state.user_payload['avatar_url'] = "https://via.placeholder.com/150"
            st.rerun()
    # Change password
    st.markdown("### Change Password")
    old_pass = st.text_input("Current Password", type="password")
    new_pass1 = st.text_input("New Password", type="password")
    new_pass2 = st.text_input("Confirm New Password", type="password")
    if st.button("Update Password"):
        if old_pass and new_pass1 and new_pass2:
            if new_pass1 == new_pass2:
                # Verify old password
                users = fetch_all_users_from_db()
                for u in users:
                    if u["username"] == username:
                        if verify_password(old_pass, u["password_hash"]):
                            # Update password
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
    # Update email
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

# Footer
st.markdown("""
<div class="footer">
    <i class="fas fa-hard-hat"></i> Mine & Workshop Digital Tracker v2.0 &nbsp;|&nbsp; Powered by Streamlit & Supabase
</div>
""", unsafe_allow_html=True)
