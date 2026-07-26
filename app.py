import streamlit as st
import requests
from datetime import datetime
import hashlib
import base64
from io import BytesIO
from PIL import Image  # optional, for image preview; install pillow if needed

# Try to import cryptography for real encryption; fallback to simple obfuscation
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

# -------------------------------
# 1. SUPABASE CONFIGURATION
# -------------------------------
SUPABASE_URL = "https://xvfbxogzefhmitrtykce.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh2ZmJ4b2d6ZWZobWl0cnR5a2NlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ4MDMxMjEsImV4cCI6MjEwMDM3OTEyMX0.OP6VM6dIcCJGDetAdP53nrElhSLnZXg3m16t9dy6nE0"

# Use Supabase client if available, otherwise fallback to requests
try:
    from supabase import create_client, Client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

# Headers for requests fallback
DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# -------------------------------
# 2. USER FUNCTIONS
# -------------------------------
def fetch_all_users_from_db():
    if not SUPABASE_AVAILABLE:
        return []
    try:
        res = supabase.table("facility_users").select("*").execute()
        return res.data if res.data else []
    except Exception:
        return []

def register_user_to_db(username, name, role, password):
    if not SUPABASE_AVAILABLE:
        return False
    try:
        payload = {"username": username, "full_name": name, "role": role, "password_hash": password}
        supabase.table("facility_users").insert(payload).execute()
        return True
    except Exception:
        return False

# -------------------------------
# 3. TASK FUNCTIONS (with fallback)
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

def create_task(title, location, priority, loto, jsa):
    if not SUPABASE_AVAILABLE:
        # fallback to memory
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
            "assigned_to": "Unassigned"
        }
        tasks.append(new_task)
        st.session_state.tasks_memory = tasks
        return new_task
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
    except Exception:
        return None
    return None

def update_task(task_id, updates):
    if not SUPABASE_AVAILABLE:
        for t in st.session_state.get("tasks_memory", []):
            if t["id"] == task_id:
                t.update(updates)
                return True
        return False
    try:
        supabase.table("tasks").update(updates).eq("id", task_id).execute()
        return True
    except Exception:
        return False

def delete_task(task_id):
    if not SUPABASE_AVAILABLE:
        st.session_state.tasks_memory = [t for t in st.session_state.get("tasks_memory", []) if t["id"] != task_id]
        return True
    try:
        supabase.table("tasks").delete().eq("id", task_id).execute()
        return True
    except Exception:
        return False

# -------------------------------
# 4. PHOTO FUNCTIONS (Supabase Storage)
# -------------------------------
def upload_photo(task_id, file_bytes, filename, uploaded_by):
    """Upload a photo to Supabase Storage and save record in task_photos table."""
    if not SUPABASE_AVAILABLE:
        # Fallback: store in memory (for demo only; won't persist)
        st.session_state.setdefault("photos_memory", []).append({
            "task_id": task_id,
            "photo_url": f"memory://{filename}",
            "uploaded_by": uploaded_by,
            "uploaded_at": datetime.now().isoformat()
        })
        return True
    try:
        # Generate a unique filename
        ext = filename.split(".")[-1]
        safe_name = f"task_{task_id}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(file_bytes).hexdigest()[:8]}.{ext}"
        # Upload to bucket 'task_photos'
        res = supabase.storage.from_("task_photos").upload(safe_name, file_bytes)
        if res:
            # Get public URL
            public_url = supabase.storage.from_("task_photos").get_public_url(safe_name)
            # Insert record in task_photos table
            data = {
                "task_id": task_id,
                "photo_url": public_url,
                "uploaded_by": uploaded_by
            }
            supabase.table("task_photos").insert(data).execute()
            return True
    except Exception as e:
        st.error(f"Upload failed: {e}")
    return False

def fetch_photos(task_id):
    """Fetch all photo URLs for a given task."""
    if not SUPABASE_AVAILABLE:
        photos = st.session_state.get("photos_memory", [])
        return [p for p in photos if p["task_id"] == task_id]
    try:
        res = supabase.table("task_photos").select("*").eq("task_id", task_id).order("uploaded_at", desc=True).execute()
        if res.data:
            return res.data
    except Exception:
        pass
    return []

# -------------------------------
# 5. CHAT FUNCTIONS (with delete support)
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
        res = supabase.table("chat_messages").insert(payload).execute()
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

def delete_message(message_id):
    if message_id < 0:
        st.session_state.chat_messages_memory = [
            m for m in st.session_state.get("chat_messages_memory", [])
            if m["id"] != message_id
        ]
        return True
    else:
        if not SUPABASE_AVAILABLE:
            return False
        try:
            supabase.table("chat_messages").delete().eq("id", message_id).execute()
            return True
        except Exception:
            return False

# -------------------------------
# 6. ENCRYPTION HELPERS
# -------------------------------
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
# 7. SESSION STATE INIT
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
    st.session_state.tasks_memory = [
        {"id": 101, "title": "Replace 45kW Pump Motor Starter", "location": "Workshop Bench 2",
         "status": "In Progress", "priority": "High", "assigned_to": "John Doe",
         "loto": False, "jsa": False},
        {"id": 102, "title": "Calibrate Underground Gas Detectors", "location": "Level 4 North Shaft",
         "status": "Unassigned", "priority": "Critical", "assigned_to": "Unassigned",
         "loto": False, "jsa": False},
        {"id": 103, "title": "Inspect Overhead Workshop Crane Cables", "location": "Workshop Bench 1",
         "status": "Complete", "priority": "High", "assigned_to": "Sarah Connor",
         "loto": True, "jsa": True},
        {"id": 104, "title": "Re-wire Level 3 Sump Pump Float", "location": "Level 3 South Sump",
         "status": "Blocked", "priority": "Medium", "assigned_to": "Unassigned",
         "loto": True, "jsa": False}
    ]
if 'chat_messages_memory' not in st.session_state:
    st.session_state.chat_messages_memory = []
if 'chat_input_value' not in st.session_state:
    st.session_state.chat_input_value = ""
if 'photos_memory' not in st.session_state:
    st.session_state.photos_memory = []

# -------------------------------
# 8. AUTHENTICATION GATEWAY
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
                "email": matched_user.get("email", None)
            }
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Invalid credentials or database unreachable.")

    st.markdown("---")
    st.subheader("🆕 Create Account Profile")
    reg_user = st.text_input("Choose Username").strip().lower()
    reg_name = st.text_input("Full Name")
    reg_email = st.text_input("Email (optional)")
    reg_role = st.selectbox("Role Access Level", ["Worker", "Supervisor", "Superintendent"])
    reg_pass = st.text_input("Set Password", type="password")

    if st.button("Register Profile"):
        if reg_user and reg_name and reg_pass:
            success = register_user_to_db(reg_user, reg_name, reg_role, reg_pass)
            if success:
                st.success(f"Account '{reg_user}' created! Please log in.")
            else:
                st.error("Registration failed. Username may be taken or database RLS is blocking.")
        else:
            st.error("All fields are mandatory.")
    st.stop()

# -------------------------------
# 9. MAIN APP
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

    # Broadcast sender
    if role in ["supervisor", "superintendent"]:
        st.markdown("---")
        st.subheader("📢 Send Broadcast")
        broadcast_msg = st.text_area("Message to all Workers")
        if st.button("Send Broadcast"):
            if broadcast_msg:
                st.session_state.broadcast_messages.append({
                    "sender": full_name,
                    "role": user['role'],
                    "message": broadcast_msg,
                    "timestamp": datetime.now().strftime("%H:%M")
                })
                st.success("Broadcast sent!")
                st.rerun()
            else:
                st.error("Message cannot be empty.")

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

    st.markdown("---")
    if st.button("🔄 Refresh Data"):
        st.rerun()

# Fetch tasks (merge DB + memory)
db_tasks = fetch_all_tasks()
if db_tasks:
    st.session_state.tasks = db_tasks
else:
    st.session_state.tasks = st.session_state.tasks_memory

# -------------------------------
# 10. TABS: TASKS, CHAT, ADMIN
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
                for task in st.session_state.tasks:
                    if task['assigned_to'] != full_name:
                        continue
                    with st.container(border=True):
                        st.markdown(f"### Task #{task['id']}: {task['title']}")
                        st.write(f"📍 {task['location']} | Priority: **{task['priority']}** | Status: `{task['status']}`")
                        loto = st.checkbox("LOTO Isolated", value=task.get('loto', False), key=f"loto_{task['id']}")
                        jsa = st.checkbox("JSA Signed", value=task.get('jsa', False), key=f"jsa_{task['id']}")
                        if loto != task.get('loto') or jsa != task.get('jsa'):
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
                                st.rerun()

                        # ---- PHOTO UPLOAD SECTION ----
                        st.markdown("#### 📸 Upload Proof Photo")
                        uploaded_file = st.file_uploader(f"Choose an image for task #{task['id']}", type=["jpg", "jpeg", "png", "gif"], key=f"upload_{task['id']}")
                        if uploaded_file is not None:
                            if st.button(f"Upload for Task #{task['id']}", key=f"upload_btn_{task['id']}"):
                                bytes_data = uploaded_file.getvalue()
                                success = upload_photo(task['id'], bytes_data, uploaded_file.name, full_name)
                                if success:
                                    st.success("Photo uploaded successfully!")
                                    st.rerun()
                                else:
                                    st.error("Upload failed. Check bucket and table.")

                        # Show existing photos for this task
                        photos = fetch_photos(task['id'])
                        if photos:
                            st.markdown("**Already uploaded:**")
                            cols = st.columns(min(4, len(photos)))
                            for idx, photo in enumerate(photos):
                                with cols[idx % len(cols)]:
                                    st.image(photo['photo_url'], width=100)

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
            if not st.session_state.tasks:
                st.info("No tasks found.")
            for task in st.session_state.tasks:
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
                        st.rerun()
                    if task['status'] == "Pending QA":
                        if cols[2].button("✅ Approve & Close", key=f"approve_{task['id']}"):
                            update_task(task['id'], {"status": "Complete"})
                            st.rerun()

                    # ---- Show photos for this task (Supervisor view) ----
                    photos = fetch_photos(task['id'])
                    if photos:
                        with st.expander(f"📸 Photos for Task #{task['id']}"):
                            cols = st.columns(min(4, len(photos)))
                            for idx, photo in enumerate(photos):
                                with cols[idx % len(cols)]:
                                    st.image(photo['photo_url'], width=120)
                                    st.caption(f"By {photo['uploaded_by']}")

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
                            st.rerun()
                        else:
                            st.error("Failed to create task.")
                    else:
                        st.error("Title and Location are required.")

    elif role == "superintendent":
        st.subheader("🏗️ Superintendent Control Centre")
        tab_overview, tab_manage, tab_broadcasts = st.tabs(["📊 Overview", "📋 Manage Tasks", "📢 Broadcast Log"])
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
                    cols = st.columns([2, 1, 1, 1])
                    cols[0].markdown(f"**#{task['id']}:** {task['title']}  \n📍 {task['location']} | Status: `{task['status']}` | Priority: {task['priority']}")
                    current_assign = task['assigned_to'] if task['assigned_to'] in worker_names else "Unassigned"
                    new_assign = cols[1].selectbox("Assign", worker_names,
                                                   index=worker_names.index(current_assign),
                                                   key=f"sup_assign_{task['id']}")
                    if new_assign != task['assigned_to']:
                        update_task(task['id'], {"assigned_to": new_assign})
                        if task['status'] == "Unassigned" and new_assign != "Unassigned":
                            update_task(task['id'], {"status": "In Progress"})
                        st.rerun()
                    status_opts = ["Unassigned", "In Progress", "Pending QA", "Blocked", "Complete"]
                    curr_stat_idx = status_opts.index(task['status']) if task['status'] in status_opts else 0
                    new_stat = cols[2].selectbox("Status", status_opts, index=curr_stat_idx, key=f"stat_ovr_{task['id']}")
                    if new_stat != task['status']:
                        update_task(task['id'], {"status": new_stat})
                        st.rerun()
                    if cols[3].button("🗑️ Delete", key=f"del_{task['id']}"):
                        delete_task(task['id'])
                        st.rerun()

                    # ---- Show photos for this task (Superintendent view) ----
                    photos = fetch_photos(task['id'])
                    if photos:
                        with st.expander(f"📸 Photos for Task #{task['id']}"):
                            cols = st.columns(min(4, len(photos)))
                            for idx, photo in enumerate(photos):
                                with cols[idx % len(cols)]:
                                    st.image(photo['photo_url'], width=120)
                                    st.caption(f"By {photo['uploaded_by']}")

        with tab_broadcasts:
            st.markdown("### All Broadcast Messages")
            if st.session_state.broadcast_messages:
                for msg in reversed(st.session_state.broadcast_messages):
                    st.write(f"**{msg['sender']}** ({msg['role']}) at {msg['timestamp']}: {msg['message']}")
            else:
                st.info("No messages sent yet.")

# ---- CHAT ROOM ----
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

    messages = fetch_messages(room=room, limit=200)
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
                        if delete_message(msg['id']):
                            st.success("Message deleted!")
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
            if st.button("Send", use_container_width=True):
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
                        st.rerun()
                    else:
                        st.error("Failed to send message. Check database or ensure table exists.")
                else:
                    st.warning("Message cannot be empty.")
        with col_clear:
            if st.button("Clear input", use_container_width=True):
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

# -------------------------------
# End of app
# -------------------------------
