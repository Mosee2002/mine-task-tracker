import streamlit as st
import requests
from datetime import datetime

# -------------------------------
# 1. SUPABASE CONFIGURATION
# -------------------------------
SUPABASE_URL = "https://xvfbxogzefhmitrtykce.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh2ZmJ4b2d6ZWZobWl0cnR5a2NlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ4MDMxMjEsImV4cCI6MjEwMDM3OTEyMX0.OP6VM6dIcCJGDetAdP53nrElhSLnZXg3m16t9dy6nE0"

DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# -------------------------------
# 2. SUPABASE HELPER FUNCTIONS
# -------------------------------
def fetch_all_users_from_db():
    """Fetch all facility_users from Supabase; fallback to defaults if offline."""
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/facility_users?select=*", headers=DB_HEADERS, timeout=5)
        if res.status_code == 200 and res.json():
            return res.json()
    except Exception:
        pass
    # Fallback static users (for demo if Supabase is unreachable)
    return [
        {"username": "supervisor1", "full_name": "Sarah Connor", "role": "Supervisor", "password_hash": "super789"},
        {"username": "superintendent1", "full_name": "Anaba Moses", "role": "Superintendent", "password_hash": "boss000"},
        {"username": "worker1", "full_name": "John Doe", "role": "Worker", "password_hash": "worker123"}
    ]

def register_user_to_db(username, name, role, password):
    """Register a new user in Supabase. Returns True on success."""
    try:
        payload = {"username": username, "full_name": name, "role": role, "password_hash": password}
        res = requests.post(f"{SUPABASE_URL}/rest/v1/facility_users", headers=DB_HEADERS, json=payload, timeout=5)
        if res.status_code in (200, 201):
            return True
    except Exception:
        pass
    return False

# (Optional) If you later create a `tasks` table, you can add fetch/create/update functions here.
# For now we keep tasks in session state.

# -------------------------------
# 3. SESSION STATE INITIALIZATION
# -------------------------------
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

if 'broadcast_messages' not in st.session_state:
    st.session_state.broadcast_messages = []   # each: {"sender": "Name", "role": "Role", "message": "...", "timestamp": "..."}

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_payload' not in st.session_state:
    st.session_state.user_payload = None

# -------------------------------
# 4. AUTHENTICATION GATEWAY
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
                "role": matched_user.get("role", "Worker")
            }
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Invalid credentials or database unreachable.")
    
    st.markdown("---")
    st.subheader("🆕 Create Account Profile")
    reg_user = st.text_input("Choose Username").strip().lower()
    reg_name = st.text_input("Full Name")
    reg_role = st.selectbox("Role Access Level", ["Worker", "Supervisor", "Superintendent"])
    reg_pass = st.text_input("Set Password", type="password")
    
    if st.button("Register Profile"):
        if reg_user and reg_name and reg_pass:
            success = register_user_to_db(reg_user, reg_name, reg_role, reg_pass)
            if success:
                st.success(f"Account '{reg_user}' successfully created! Please log in.")
            else:
                st.error("Registration failed. Username may be taken or database RLS is blocking.")
        else:
            st.error("All fields are mandatory.")
    st.stop()   # Stop execution if not authenticated

# -------------------------------
# 5. MAIN APPLICATION (Authenticated)
# -------------------------------
user = st.session_state.user_payload
role = user['role'].strip().lower()
full_name = user['name']

# Sidebar – user info and broadcast sender (for Supervisors and Superintendents)
with st.sidebar:
    st.write(f"**User:** {full_name}")
    st.write(f"**Role:** {user['role']}")
    
    # Broadcast sender (only for Supervisor & Superintendent)
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
    
    if st.button("🚪 Logout"):
        st.session_state.authenticated = False
        st.session_state.user_payload = None
        st.rerun()

# Main content based on role
if role == "worker":
    st.subheader("👷 Field Worker Workspace")
    
    # Display broadcasts
    if st.session_state.broadcast_messages:
        st.info("📢 Latest Broadcasts:")
        for msg in reversed(st.session_state.broadcast_messages[-5:]):   # show last 5
            st.warning(f"**{msg['sender']}** ({msg['role']}) at {msg['timestamp']}: {msg['message']}")
    
    # Worker tabs: My Tasks & Unassigned Board
    tab_my, tab_unassigned = st.tabs(["📋 My Assigned Tasks", "🌐 Master Unassigned Board"])
    
    with tab_my:
        my_tasks = [t for t in st.session_state.tasks_memory if t['assigned_to'] == full_name]
        if not my_tasks:
            st.info("No tasks assigned to you.")
        else:
            for idx, task in enumerate(st.session_state.tasks_memory):
                if task['assigned_to'] != full_name:
                    continue
                with st.container(border=True):
                    st.markdown(f"### Task #{task['id']}: {task['title']}")
                    st.write(f"📍 {task['location']} | Priority: **{task['priority']}** | Status: `{task['status']}`")
                    
                    # Safety checkboxes
                    loto = st.checkbox("LOTO Isolated", value=task['loto'], key=f"loto_{task['id']}")
                    jsa = st.checkbox("JSA Signed", value=task['jsa'], key=f"jsa_{task['id']}")
                    # Update in memory
                    task['loto'] = loto
                    task['jsa'] = jsa
                    
                    if not loto or not jsa:
                        st.error("🔒 Safety isolation forms are required before proceeding.")
                    else:
                        status_options = ["In Progress", "Pending QA", "Blocked", "Complete"]
                        current_idx = status_options.index(task['status']) if task['status'] in status_options else 0
                        new_status = st.selectbox("Update Status", status_options, index=current_idx, key=f"stat_{task['id']}")
                        if new_status != task['status']:
                            task['status'] = new_status
                            st.rerun()
    
    with tab_unassigned:
        st.markdown("### 🔍 Unassigned Open Tasks")
        unassigned = [t for t in st.session_state.tasks_memory if t['assigned_to'] == "Unassigned" or t['status'] == "Unassigned"]
        if not unassigned:
            st.success("🎉 No unassigned tasks at the moment.")
        else:
            for task in unassigned:
                with st.container(border=True):
                    st.markdown(f"#### ⚙️ #{task['id']}: {task['title']}")
                    st.write(f"📍 {task['location']} | Priority: **{task['priority']}**")

elif role == "supervisor":
    st.subheader("📋 Supervisor Operations Desk")
    
    # Supervisor tabs: Manage Tasks & Create New Task
    tab_manage, tab_create = st.tabs(["📋 Manage All Tasks", "➕ Create New Task"])
    
    with tab_manage:
        st.markdown("### All Maintenance Tasks")
        # Re‑fetch fresh list of workers for assignment
        all_users = fetch_all_users_from_db()
        worker_names = ["Unassigned"] + [u["full_name"] for u in all_users if u["role"].strip().lower() == "worker"]
        
        for idx, task in enumerate(st.session_state.tasks_memory):
            with st.container(border=True):
                cols = st.columns([3, 1, 1])
                cols[0].markdown(f"**#{task['id']}:** {task['title']}  \n📍 {task['location']} | Status: `{task['status']}` | Priority: {task['priority']}")
                
                # Assignment dropdown
                current_assign = task['assigned_to'] if task['assigned_to'] in worker_names else "Unassigned"
                new_assign = cols[1].selectbox("Assign to:", worker_names, 
                                               index=worker_names.index(current_assign),
                                               key=f"assign_{task['id']}")
                if new_assign != task['assigned_to']:
                    task['assigned_to'] = new_assign
                    if task['status'] == "Unassigned" and new_assign != "Unassigned":
                        task['status'] = "In Progress"
                    st.rerun()
                
                # Approve button for Pending QA
                if task['status'] == "Pending QA":
                    if cols[2].button("✅ Approve & Close", key=f"approve_{task['id']}"):
                        task['status'] = "Complete"
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
                    new_id = max([t["id"] for t in st.session_state.tasks_memory], default=0) + 1
                    st.session_state.tasks_memory.append({
                        "id": new_id,
                        "title": title,
                        "location": location,
                        "status": "Unassigned",
                        "priority": priority,
                        "assigned_to": "Unassigned",
                        "loto": loto,
                        "jsa": jsa
                    })
                    st.success(f"Task #{new_id} created successfully!")
                    st.rerun()
                else:
                    st.error("Title and Location are required.")

elif role == "superintendent":
    st.subheader("🏗️ Superintendent Control Centre")
    
    # Superintendent tabs: Overview, Manage All Tasks, Broadcast History
    tab_overview, tab_manage, tab_broadcasts = st.tabs(["📊 Overview", "📋 Manage Tasks", "📢 Broadcast Log"])
    
    with tab_overview:
        total = len(st.session_state.tasks_memory)
        completed = sum(1 for t in st.session_state.tasks_memory if t['status'] == "Complete")
        in_progress = sum(1 for t in st.session_state.tasks_memory if t['status'] == "In Progress")
        unassigned = sum(1 for t in st.session_state.tasks_memory if t['assigned_to'] == "Unassigned" or t['status'] == "Unassigned")
        blocked = sum(1 for t in st.session_state.tasks_memory if t['status'] == "Blocked")
        
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
        
        for idx, task in enumerate(st.session_state.tasks_memory):
            with st.container(border=True):
                cols = st.columns([2, 1, 1, 1])
                cols[0].markdown(f"**#{task['id']}:** {task['title']}  \n📍 {task['location']} | Status: `{task['status']}` | Priority: {task['priority']}")
                
                # Assignment
                current_assign = task['assigned_to'] if task['assigned_to'] in worker_names else "Unassigned"
                new_assign = cols[1].selectbox("Assign", worker_names, 
                                               index=worker_names.index(current_assign),
                                               key=f"sup_assign_{task['id']}")
                if new_assign != task['assigned_to']:
                    task['assigned_to'] = new_assign
                    if task['status'] == "Unassigned" and new_assign != "Unassigned":
                        task['status'] = "In Progress"
                    st.rerun()
                
                # Status override
                status_opts = ["Unassigned", "In Progress", "Pending QA", "Blocked", "Complete"]
                curr_stat_idx = status_opts.index(task['status']) if task['status'] in status_opts else 0
                new_stat = cols[2].selectbox("Status", status_opts, index=curr_stat_idx, key=f"stat_ovr_{task['id']}")
                if new_stat != task['status']:
                    task['status'] = new_stat
                    st.rerun()
                
                # Delete button (Superintendent only)
                if cols[3].button("🗑️ Delete", key=f"del_{task['id']}"):
                    st.session_state.tasks_memory = [t for t in st.session_state.tasks_memory if t['id'] != task['id']]
                    st.rerun()
    
    with tab_broadcasts:
        st.markdown("### All Broadcast Messages")
        if st.session_state.broadcast_messages:
            for msg in reversed(st.session_state.broadcast_messages):
                st.write(f"**{msg['sender']}** ({msg['role']}) at {msg['timestamp']}: {msg['message']}")
        else:
            st.info("No messages sent yet.")

else:
    st.error("Unknown role. Please contact administrator.")

# -------------------------------
# End of script
# -------------------------------
