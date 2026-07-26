import streamlit as st
import requests

# 1. CORE APPLICATION SURFACE INITIALIZATION
st.title("⚙️ Mine & Workshop Digital Tracker")

# 2. YOUR SECURE CLOUD DATABASE CREDENTIALS
SUPABASE_URL = "https://xvfbxogzefhmitrtykce.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh2ZmJ4b2d6ZWZobWl0cnR5a2NlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ4MDMxMjEsImV4cCI6MjEwMDM3OTEyMX0.OP6VM6dIcCJGDetAdP53nrElhSLnZXg3m16t9dy6nE0"

DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# 3. LIVE CLOUD DATABASE READING AND WRITING ENGINES
def fetch_all_users_from_db():
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/facility_users?select=*", headers=DB_HEADERS, timeout=5)
        if res.status_code == 200 and len(res.json()) > 0:
            return res.json()
    except Exception:
        pass
    # Local fallback administrative profiles to prevent system lockouts
    return [
        {"username": "supervisor1", "full_name": "Sarah Connor", "role": "Supervisor", "password_hash": "super789"},
        {"username": "superintendent1", "full_name": "Anaba Moses", "role": "Superintendent", "password_hash": "boss000"}
    ]

def register_user_to_db(username, name, role, password):
    try:
        payload = {"username": username, "full_name": name, "role": role, "password_hash": password}
        res = requests.post(f"{SUPABASE_URL}/rest/v1/facility_users", headers=DB_HEADERS, json=payload, timeout=5)
        if res.status_code == 200 or res.status_code == 201:
            return True
    except Exception:
        pass
    return False

# Initialize fallback shift schedule registry
if 'tasks_memory' not in st.session_state:
    st.session_state.tasks_memory = [
        {"id": 101, "title": "Replace 45kW Pump Motor Starter", "location": "Workshop Bench 2", "status": "In Progress", "priority": "High", "assigned_to": "John Doe", "loto": False, "jsa": False},
        {"id": 102, "title": "Calibrate Underground Gas Detectors", "location": "Level 4 North Shaft", "status": "Unassigned", "priority": "Critical", "assigned_to": "Unassigned", "loto": False, "jsa": False},
        {"id": 103, "title": "Inspect Overhead Workshop Crane Cables", "location": "Workshop Bench 1", "status": "Complete", "priority": "High", "assigned_to": "Sarah Connor", "loto": True, "jsa": True},
        {"id": 104, "title": "Re-wire Level 3 Sump Pump Float", "location": "Level 3 South Sump", "status": "Blocked", "priority": "Medium", "assigned_to": "Unassigned", "loto": True, "jsa": False}
    ]

if 'broadcast_messages' not in st.session_state:
    st.session_state.broadcast_messages = []

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_payload' not in st.session_state:
    st.session_state.user_payload = None

# -------------------------------------------------------------
# GATEWAY SCREEN 1: ACCESS PROFILE ACCREDITATION WINDOW
# -------------------------------------------------------------
if not st.session_state.authenticated:
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
            st.error("Invalid credentials entered or database unreachable.")
            
    st.markdown("---")
    st.subheader("🆕 Create Account Profile")
    reg_user = st.text_input("Choose Username").strip().lower()
    reg_name = st.text_input("Full Name")
    reg_role = st.selectbox("Role Access Level", ["Worker", "Supervisor", "Superintendent"])
    reg_pass = st.text_input("Set Password", type="password")
    
    if st.button("Register Profile"):
        if reg_user and reg_name and reg_pass:
            # Save account details directly into Supabase SQL data columns permanently [INDEX]
            success = register_user_to_db(reg_user, reg_name, reg_role, reg_pass)
            if success:
                st.success(f"Account profile successfully locked inside your Supabase Cloud Database! Log in above.")
            else:
                st.error("Registration failed. Table Row Level Security (RLS) might be blocking the request.")
        else:
            st.error("All input fields are mandatory.")
    st.stop()

# -------------------------------------------------------------
# GATEWAY SCREEN 2: ACTIVE CONTROL INTERFACES (ROBUST CASCADE)
# -------------------------------------------------------------
user = st.session_state.user_payload
role_check = str(user['role']).strip().lower()

# Dynamic worker menu mapping directly from live cloud database profiles
raw_users = fetch_all_users_from_db()
all_workers_list = ["Unassigned"] + [u["full_name"] for u in raw_users if str(u["role"]).strip().lower() == "worker"]

with st.sidebar:
    st.write(f"Active User: **{user['name']}**")
    st.write(f"Authorization: **{user['role']}**")
    if st.button("🚪 Logout Portal"):
        st.session_state.authenticated = False
        st.session_state.user_payload = None
        st.rerun()

# --- INTERFACE A: WORKER DISPATCH TRACKER ---
if role_check == "worker":
    st.subheader("👷 Field Technician Workspace")
    
    if st.session_state.broadcast_messages:
        st.info("📢 Supervisor Alert Board:")
        for msg in reversed(st.session_state.broadcast_messages):
            st.warning(msg)
            
    for idx, task in enumerate(st.session_state.tasks_memory):
        if task['assigned_to'] == user['name']:
            with st.container(border=True):
                st.markdown(f"### Task #{task['id']}: {task['title']}")
                st.write(f"📍 Location: {task['location']} | Priority: **{task['priority']}**")
                
                l_check = st.checkbox("LOTO Isolated", value=task['loto'], key=f"loto_{task['id']}")
                j_check = st.checkbox("JSA Safety Signed", value=task['jsa'], key=f"jsa_{task['id']}")
                st.session_state.tasks_memory[idx]['loto'] = l_check
                st.session_state.tasks_memory[idx]['jsa'] = j_check
                
                if not l_check or not j_check:
                    st.error("🔒 Safety Isolation Forms Required.")
                else:
                    opt = ["In Progress", "Pending QA", "Blocked"]
                    curr_idx = opt.index(task['status']) if task['status'] in opt else 0
                    new_stat = st.selectbox("Update Status:", opt, index=curr_idx, key=f"stat_{task['id']}")
                    if new_stat != task['status']:
                        st.session_state.tasks_memory[idx]['status'] = new_stat
                        st.rerun()

# --- INTERFACE B: SUPERVISOR TASK HUB ---
elif role_check == "supervisor":
    st.subheader("📋 Supervisor Operations Control Desk")
    
    st.markdown("### Master Operational Schedule Log")
    for idx, task in enumerate(st.session_state.tasks_memory):
        with st.container(border=True):
            st.markdown(f"**Task #{task['id']}: {task['title']}**")
            st.write(f"Sector: {task['location']} | Status: `{task['status']}` | Current Owner: **{task['assigned_to']}**")
            
            new_worker = st.selectbox("Reassign Worker:", all_workers_list, index=all_workers_list.index(task['assigned_to']) if task['assigned_to'] in all_workers_list else 0, key=f"sup_assign_{task['id']}")
            if new_worker != task['assigned_to']:
                st.session_state.tasks_memory[idx]['assigned_to'] = new_worker
                st.rerun()
                
            if task['status'] == "Pending QA":
                if st.button("✅ Approve & Close Work Card", key=f"app_{task['id']}"):
                    st.session_state.tasks_memory[idx]['status'] = "Complete"
                    st.rerun()
                    
    st.markdown("---")
    st.markdown("### ➕ Dispatch New Maintenance Work Ticket")
    n_title = st.text_input("Task Title Description")
    n_loc = st.text_input("Mine Sector / Bench Area")
    n_pri = st.selectbox("Urgency Grade", ["Low", "Medium", "High", "Critical"])
    if st.button("Publish Work Ticket"):
        if n_title and n_loc:
            new_id = int(max(t['id'] for t in st.session_state.tasks_memory) + 1 if st.session_state.tasks_memory else 101)
            st.session_state.tasks_memory.append({"id": new_id, "title": n_title, "location": n_loc, "priority": n_pri, "assigned_to": "Unassigned", "status": "Unassigned", "loto": False, "jsa": False})
            st.success("Ticket Dispatched!")
            st.rerun()

    st.markdown("---")
    st.markdown("### 📣 Broadcast Notice to Team Notice Board")
    msg_input = st.text_area("Type instructions for field technician dashboards...")
    if st.button("Broadcast Message"):
        if msg_input:
            st.session_state.broadcast_messages.append(msg_input)
            st.success("Broadcast posted successfully!")

# --- INTERFACE C: SUPERINTENDENT EXECUTIVE DASHBOARD ---
elif role_check == "superintendent":
    st.subheader("📊 Executive Superintendent Control Room Hub")
    
    total_cards = len(st.session_state.tasks_memory)
    done_cards = sum(1 for t in st.session_state.tasks_memory if t['status'] == 'Complete')
         
