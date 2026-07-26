import streamlit as st
import requests
from datetime import datetime
import hashlib
import base64
import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from supabase import create_client, Client
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import asyncio
import threading

# -------------------------------
# 1. SUPABASE CONFIGURATION
# -------------------------------
SUPABASE_URL = "https://xvfbxogzefhmitrtykce.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh2ZmJ4b2d6ZWZobWl0cnR5a2NlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ4MDMxMjEsImV4cCI6MjEwMDM3OTEyMX0.OP6VM6dIcCJGDetAdP53nrElhSLnZXg3m16t9dy6nE0"

# Initialize Supabase client for realtime and storage
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# For legacy REST calls (still used for some operations)
DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# -------------------------------
# 2. EMAIL NOTIFICATION SETUP
# -------------------------------
# Choose your notification method: "sendgrid" or "smtp"
NOTIFICATION_METHOD = "smtp"  # change to "sendgrid" if you have an API key

# SMTP config (for Gmail example)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "your_email@gmail.com"      # Set your email
SMTP_PASSWORD = "your_app_password"     # Use app password, not regular password
SMTP_FROM = SMTP_USER

# SendGrid config (uncomment if using)
# SENDGRID_API_KEY = "your_sendgrid_api_key"
# SENDGRID_FROM = "noreply@yourdomain.com"

def send_email_notification(recipient_email, subject, body):
    """Send an email using either SendGrid or SMTP."""
    try:
        if NOTIFICATION_METHOD == "sendgrid":
            # SendGrid method
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            message = Mail(
                from_email=SENDGRID_FROM,
                to_emails=recipient_email,
                subject=subject,
                html_content=body
            )
            response = sg.send(message)
            return response.status_code in (200, 202)
        else:
            # SMTP method
            msg = MIMEMultipart()
            msg['From'] = SMTP_FROM
            msg['To'] = recipient_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'html'))
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
            return True
    except Exception as e:
        st.error(f"Email failed: {str(e)}")
        return False

# -------------------------------
# 3. USER FUNCTIONS (unchanged)
# -------------------------------
def fetch_all_users_from_db():
    try:
        res = supabase.table("facility_users").select("*").execute()
        if res.data:
            return res.data
    except Exception:
        pass
    return [
        {"username": "supervisor1", "full_name": "Sarah Connor", "role": "Supervisor", "password_hash": "super789"},
        {"username": "superintendent1", "full_name": "Anaba Moses", "role": "Superintendent", "password_hash": "boss000"},
        {"username": "worker1", "full_name": "John Doe", "role": "Worker", "password_hash": "worker123"}
    ]

def register_user_to_db(username, name, role, password):
    try:
        payload = {"username": username, "full_name": name, "role": role, "password_hash": password}
        supabase.table("facility_users").insert(payload).execute()
        return True
    except Exception:
        return False

# -------------------------------
# 4. TASK FUNCTIONS (Supabase)
# -------------------------------
def fetch_all_tasks():
    try:
        res = supabase.table("tasks").select("*").order("id", desc=False).execute()
        return res.data if res.data else []
    except Exception:
        return []

def create_task(title, location, priority, loto, jsa):
    try:
        new_task = {
            "title": title,
            "location": location,
            "priority": priority,
            "loto": loto,
            "jsa": jsa,
            "status": "Unassigned",
            "assigned_to": "Unassigned"
        }
        res = supabase.table("tasks").insert(new_task).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        st.error(f"Create task error: {e}")
    return None

def update_task(task_id, updates):
    try:
        supabase.table("tasks").update(updates).eq("id", task_id).execute()
        return True
    except Exception:
        return False

def delete_task(task_id):
    try:
        supabase.table("tasks").delete().eq("id", task_id).execute()
        return True
    except Exception:
        return False

# -------------------------------
# 5. CHAT FUNCTIONS (Supabase)
# -------------------------------
def send_message(sender, receiver, room, message, encrypted=False):
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
    try:
        query = supabase.table("chat_messages").select("*").order("created_at", desc=True).limit(limit)
        if room:
            query = query.eq("room", room)
        res = query.execute()
        return res.data if res.data else []
    except Exception:
        return []

# -------------------------------
# 6. ENCRYPTION HELPERS (unchanged)
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
# 7. FILE ATTACHMENT (Supabase Storage)
# -------------------------------
def upload_attachment(file, task_id):
    """Upload a file to Supabase Storage and return the public URL."""
    try:
        # Ensure bucket exists (must be created in Supabase Dashboard)
        file_extension = file.name.split(".")[-1]
        file_name = f"task_{task_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file_extension}"
        # Upload to bucket "task_attachments"
        res = supabase.storage.from_("task_attachments").upload(file_name, file.getvalue())
        if res:
            # Get public URL
            public_url = supabase.storage.from_("task_attachments").get_public_url(file_name)
            return public_url
    except Exception as e:
        st.error(f"Upload failed: {e}")
    return None

# -------------------------------
# 8. REAL-TIME CHAT (uses Supabase Realtime)
# -------------------------------
# We'll set up a simple polling mechanism because Streamlit doesn't support websockets easily.
# For a more robust solution, you'd use a background thread, but we'll keep it simple with periodic reruns.

# -------------------------------
# 9. SESSION STATE INIT
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
if 'tasks' not in st.session_state:
    st.session_state.tasks = fetch_all_tasks()

# -------------------------------
# 10. AUTHENTICATION GATEWAY (unchanged)
# -------------------------------
if not st.session_state.authenticated:
    st.title("⚙️ Mine & Workshop Digital Tracker")
    st.subheader("🔒 Secure Login Gateway")
    user_in = st.text_input("Username").strip().lower()
    pass_in = st.text_input("Password", type="password")
    
    if st.button("Authenticate Profile"):
        all_users = fetch_all_users_from_db()
        matched_user = None
        for u in all_users:
            if str(u["username"]).strip().lower() == user_in and str(u["password_hash"]).strip() == pass_in:
                matched_user = u
                break
        if matched_user:
            st.session_state.user_payload = {
                "name": matched_user.get("full_name", matched_user.get("username")),
                "role": matched_user.get("role", "Worker"),
                "username": matched_user.get("username"),
                "email": matched_user.get("email", None)  # add email column if you want notifications
            }
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Invalid credentials or database unreachable.")
    
    st.markdown("---")
    st.subheader("🆕 Create Account Profile")
    reg_user = st.text_input("Choose Username").strip().lower()
    reg_name = st.text_input("Full Name")
    reg_email = st.text_input("Email (for notifications)")  # new field
    reg_role = st.selectbox("Role Access Level", ["Worker", "Supervisor", "Superintendent"])
    reg_pass = st.text_input("Set Password", type="password")
    
    if st.button("Register Profile"):
        if reg_user and reg_name and reg_pass:
            # Add email column to facility_users if not exists (you can alter table)
            success = register_user_to_db(reg_user, reg_name, reg_role, reg_pass)
            if success:
                st.success(f"Account '{reg_user}' created! Please log in.")
            else:
                st.error("Registration failed. Username may be taken or database RLS is blocking.")
        else:
            st.error("All fields are mandatory.")
    st.stop()

# -------------------------------
# 11. MAIN APP
# -------------------------------
user = st.session_state.user_payload
full_name = user['name']
username = user['username']
role = user['role'].strip().lower()
user_email = user.get('email', None)

# Sidebar
with st.sidebar:
    st.write(f"**User:** {full_name}")
    st.write(f"**Role:** {user['role']}")
    
    # Broadcast sender (legacy, kept for compatibility)
    if role in ["supervisor", "superintendent"]:
        st.markdown("---")
        st.subheader("📢 Send Broadcast (Legacy)")
        broadcast_msg = st.text_area("Message to all Workers")
        if st.button("Send Broadcast"):
            if broadcast_msg:
                st.session_state.broadcast_messages.append({
                    "sender": full_name,
                    "role": user['role'],
                    "message": broadcast_msg,
                    "timestamp": datetime.now().strftime("%H:%M")
                })
                # Also send email to all workers? Could be done.
                st.success("Broadcast sent!")
                st.rerun()
    
    st.markdown("---")
    st.subheader("💬 Chat Rooms")
    if st.button("🌍 Global Chat"):
        st.session_state.chat_room = "global"
        st.rerun()
    if role in ["supervisor", "superintendent"]:
        if st.button("🔒 Supervisor Room"):
            st.session_state.chat_room = "supervisor"
            st.rerun()
    
    st.markdown("#### 👤 Private Chat")
    all_users = fetch_all_users_from_db()
    other_users = [u["full_name"] for u in all_users if u["full_name"] != full_name]
    if other_users:
        selected_user = st.selectbox("Choose contact", other_users)
        if st.button("Open Private Chat"):
            sorted_names = sorted([full_name, selected_user])
            room_name = f"private:{sorted_names[0]}_{sorted_names[1]}"
            st.session_state.chat_room = room_name
            st.session_state.chat_partner = selected_user
            st.rerun()
    else:
        st.info("No other users available.")
    
    if st.button("🚪 Logout"):
        st.session_state.authenticated = False
        st.session_state.user_payload = None
        st.session_state.chat_room = "global"
        st.rerun()

# Refresh tasks from DB on each load (or we can use realtime)
st.session_state.tasks = fetch_all_tasks()

# -------------------------------
# 12. TASK TRACKER + CHAT TABS
# -------------------------------
tab_tasks, tab_chat, tab_admin = st.tabs(["📋 Task Dashboard", "💬 Chat Room", "⚙️ Admin Panel"])

# ---- TASK DASHBOARD ----
with tab_tasks:
    if role == "worker":
        st.subheader("👷 Field Worker Workspace")
        if st.session_state.broadcast_messages:
            st.info("📢 Latest Broadcasts:")
            for msg in reversed(st.session_state.broadcast_messages[-5:]):
                st.warning(f"**{msg['sender']}** ({msg['role']}) at {msg['timestamp']}: {msg['message']}")
        
        tab_my, tab_unassigned = st.tabs(["📋 My Assigned Tasks", "🌐 Master Unassigned Board"])
        with tab_my:
            my_tasks = [t for t in st.session_state.tasks if t['assigned_to'] == full_name]
            if not my_tasks:
                st.info("No tasks assigned to you.")
            else:
                for idx, task in enumerate(st.session_state.tasks):
                    if task['assigned_to'] != full_name:
                        continue
                    with st.container(border=True):
                        st.markdown(f"### Task #{task['id']}: {task['title']}")
                        st.write(f"📍 {task['location']} | Priority: **{task['priority']}** | Status: `{task['status']}`")
                        loto = st.checkbox("LOTO Isolated", value=task['loto'], key=f"loto_{task['id']}")
                        jsa = st.checkbox("JSA Signed", value=task['jsa'], key=f"jsa_{task['id']}")
                        if loto != task['loto'] or jsa != task['jsa']:
                            update_task(task['id'], {"loto": loto, "jsa": jsa})
                            st.rerun()
                        if not loto or not jsa:
                            st.error("🔒 Safety isolation forms are required before proceeding.")
                        else:
                            status_options = ["In Progress", "Pending QA", "Blocked", "Complete"]
                            current_idx = status_options.index(task['status']) if task['status'] in status_options else 0
                            new_status = st.selectbox("Update Status", status_options, index=current_idx, key=f"stat_{task['id']}")
                            if new_status != task['status']:
                                update_task(task['id'], {"status": new_status})
                                # Send notification to supervisor? We'll handle in supervisor side.
                                st.rerun()
        with tab_unassigned:
            unassigned = [t for t in st.session_state.tasks if t['assigned_to'] == "Unassigned" or t['status'] == "Unassigned"]
            if not unassigned:
                st.success("🎉 No unassigned tasks at the moment.")
            else:
                for task in unassigned:
                    with st.container(border=True):
                        st.markdown(f"#### ⚙️ #{task['id']}: {task['title']}")
                        st.write(f"📍 {task['location']} | Priority: **{task['priority']}**")
    
    elif role == "supervisor":
        st.subheader("📋 Supervisor Operations Desk")
        tab_manage, tab_create = st.tabs(["📋 Manage All Tasks", "➕ Create New Task"])
        with tab_manage:
            st.markdown("### All Maintenance Tasks")
            all_users = fetch_all_users_from_db()
            worker_names = ["Unassigned"] + [u["full_name"] for u in all_users if u["role"].strip().lower() == "worker"]
            for idx, task in enumerate(st.session_state.tasks):
                with st.container(border=True):
                    cols = st.columns([3, 1, 1])
                    cols[0].markdown(f"**#{task['id']}:** {task['title']}  \n📍 {task['location']} | Status: `{task['status']}` | Priority: {task['priority']}")
                    current_assign = task['assigned_to'] if task['assigned_to'] in worker_names else "Unassigned"
                    new_assign = cols[1].selectbox("Assign to:", worker_names, 
                                                   index=worker_names.index(current_assign),
                                                   key=f"assign_{task['id']}")
                    if new_assign != task['assigned_to']:
                        update_task(task['id'], {"assigned_to": new_assign})
                        if task['status'] == "Unassigned" and new_assign != "Unassigned":
                            update_task(task['id'], {"status": "In Progress"})
                        # Send email notification to the assigned worker
                        if new_assign != "Unassigned":
                            # Find worker's email
                            worker_email = next((u.get('email') for u in all_users if u['full_name'] == new_assign), None)
                            if worker_email:
                                subject = f"New Task Assigned: #{task['id']} - {task['title']}"
                                body = f"Hello {new_assign},<br><br>You have been assigned to task <b>#{task['id']}</b>: {task['title']}.<br>Location: {task['location']}<br>Priority: {task['priority']}<br><br>Please login to the tracker for details.<br>Regards,<br>Supervisor"
                                send_email_notification(worker_email, subject, body)
                        st.rerun()
                    if task['status'] == "Pending QA":
                        if cols[2].button("✅ Approve & Close", key=f"approve_{task['id']}"):
                            update_task(task['id'], {"status": "Complete"})
                            st.rerun()
        with tab_create:
            st.markdown("### Dispatch New Work Ticket")
            with st.form("new_task_form"):
                title = st.text_input("Task Title *")
                location = st.text_input("Location / Area *")
                priority = st.selectbox("Priority", ["Low", "Medium", "High", "Critical"])
                loto = st.checkbox("Requires LOTO")
                jsa = st.checkbox("Requires JSA")
                submitted = st.form_submit_button("Create Work Ticket")
                if submitted:
                    if title and location:
                        new_task = create_task(title, location, priority, loto, jsa)
                        if new_task:
                            st.success(f"Task #{new_task['id']} created!")
                            # Optionally notify all supervisors
                            st.rerun()
                        else:
                            st.error("Failed to create task.")
                    else:
                        st.error("Title and Location are required.")

    
