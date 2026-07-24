import streamlit as st
import pandas as pd
import requests

# 1. FACILITY SYSTEM APPLICATION ARCHITECTURE INITIALIZATION
st.set_page_config(page_title="Mine Task Tracker", layout="wide")

# 2. DIRECT CLOUD DATABASE CONNECTOR KEYS
# Make sure to update these two strings with your real keys from Supabase
SUPABASE_URL = "https://supabase.co"
SUPABASE_KEY = "your-anonymous-public-api-key-string"

DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_payload' not in st.session_state:
    st.session_state.user_payload = None

# 3. NATIVE POSTGRESQL NETWORK API OPERATIONS
def fetch_all_users_from_db():
    try:
        url = f"{SUPABASE_URL}/rest/v1/facility_users?select=*"
        res = requests.get(url, headers=DB_HEADERS, timeout=10)
        return res.json() if res.status_code == 200 else []
    except Exception:
        return []

def register_user_to_db(username, name, role, password):
    try:
        url = f"{SUPABASE_URL}/rest/v1/facility_users"
        payload = {"username": username, "full_name": name, "role": role, "password_hash": password}
        res = requests.post(url, headers=DB_HEADERS, json=payload, timeout=10)
        # FIXED: Explicit status check for successful entry insertion
        return True if res.status_code in [200, 201] else False
    except Exception:
        return False

def fetch_all_tasks_from_db():
    try:
        url = f"{SUPABASE_URL}/rest/v1/facility_tasks?select=*"
        res = requests.get(url, headers=DB_HEADERS, timeout=10)
        return res.json() if res.status_code == 200 else []
    except Exception:
        return []

# -------------------------------------------------------------
# INTERFACE GATEWAY 1: THE ACCREDITATION ENTRY FORM
# -------------------------------------------------------------
if not st.session_state.authenticated:
    st.title("🔒 Industrial Portal Secure Entry")
    
    st.markdown("### Sign In")
    user_in = st.text_input("Username", key="lin_user").strip().lower()
    pass_in = st.text_input("Password", type="password", key="lin_pass")
    
    if st.button("Authenticate Profile"):
        all_users = fetch_all_users_from_db()
        matched_user = None
        for u in all_users:
            if u["username"] == user_in and u["password_hash"] == pass_in:
                matched_user = u
                break
        
        if matched_user:
            st.session_state.user_payload = matched_user
            st.session_state.authenticated = True
            st.success("Authenticated! Tap button again to access terminal panels.")
            st.rerun()
        else:
            st.error("Invalid credentials entered or database unreachable.")
            
    st.markdown("---")
    st.markdown("### 🆕 Register New Account")
    reg_user = st.text_input("Choose Login Username", key="rg_u").strip().lower()
    reg_name = st.text_input("Enter Full Name", key="rg_n")
    reg_role = st.selectbox("Assign Access Level Role", ["Worker", "Supervisor", "Superintendent"], key="rg_r")
    reg_pass = st.text_input("Set Security Password", type="password", key="rg_p")
    
    if st.button("Register to System Ledger"):
        if not reg_user or not reg_name or not reg_pass:
            st.error("All data input values are mandatory.")
        else:
            success = register_user_to_db(reg_user, reg_name, reg_role, reg_pass)
            if success:
                st.success("Account profile successfully registered to cloud table ledger! Sign in above.")
            else:
                st.error("Registration failed. Username may be taken or table configurations block request.")
    st.stop()

# -------------------------------------------------------------
# INTERFACE GATEWAY 2: CORE SECURED WORKSPACES HUB
# -------------------------------------------------------------
user = st.session_state.user_payload
normalized_role = str(user['role']).strip().lower()

# Fetch active database rows live on loop load executions
raw_tasks = fetch_all_tasks_from_db()
tasks_df = pd.DataFrame(raw_tasks) if raw_tasks else pd.DataFrame(columns=["id", "title", "location", "status", "priority", "assigned_to", "loto_verified", "jsa_completed"])

raw_users = fetch_all_users_from_db()
crew_list = ["Unassigned"] + [u["full_name"] for u in raw_users if str(u["role"]).strip().lower() == "worker"]

with st.sidebar:
    st.markdown(f"### Profile: **{user['full_name']}**")
    st.info(f"Role: {user['role']}")
    if st.button("🚪 Logout Application"):
        st.session_state.authenticated = False
        st.session_state.user_payload = None
        st.rerun()

# === WORKER BOARD LOGIC ===
if normalized_role == "worker":
    st.title("👷 Field Worker Workspace")
    st.markdown("---")
    st.subheader("📋 My Active Task Dashboard")
    
    has_tasks = False
    for item in raw_tasks:
        if item['assigned_to'] == user['full_name']:
            has_tasks = True
            with st.container(border=True):
                st.markdown(f"#### Task #{item['id']}: {item['title']}")
                loto = st.checkbox("LOTO Isolated", value=item['loto_verified'], key=f"wk_loto_{item['id']}")
                jsa = st.checkbox("JSA Signed", value=item['jsa_completed'], key=f"wk_jsa_{item['id']}")
                
                if (loto != item['loto_verified']) or (jsa != item['jsa_completed']):
                    requests.patch(f"{SUPABASE_URL}/rest/v1/facility_tasks?id=eq.{item['id']}", headers=DB_HEADERS, json={"loto_verified": loto, "jsa_completed": jsa})
                    st.rerun()
                
                if not loto or not jsa:
                    st.error("🔒 Safety Interlocks Active.")
                else:
                    action_status = st.selectbox("Update Status:", ["In Progress", "Pending QA", "Blocked"], index=["In Progress", "Pending QA", "Blocked"].index(item['status']) if item['status'] in ["In Progress", "Pending QA", "Blocked"] else 0, key=f"wk_stat_{item['id']}")
                    if action_status != item['status']:
                        requests.patch(f"{SUPABASE_URL}/rest/v1/facility_tasks?id=eq.{item['id']}", headers=DB_HEADERS, json={"status": action_status})
                        st.rerun()
    if not has_tasks:
        st.info("No explicit jobs assigned to your specific tag name right now.")
                        
    st.markdown("---")
    st.subheader("🌐 Complete List of All Facility Open Tasks")
    if not tasks_df.empty:
        open_jobs = tasks_df[tasks_df['status'] != "Complete"]
        st.dataframe(open_jobs[["id", "title", "location", "priority", "status", "assigned_to"]], hide_index=True, use_container_width=True)

# === SUPERVISOR BOARD LOGIC ===
elif normalized_role == "supervisor":
    st.title("📋 Supervisor Control Terminal")
    st.markdown("---")
    st.subheader("📊 Live Shift Production Progress")
    
    u_count = sum(1 for t in raw_tasks if t['status'] == 'Unassigned')
    p_count = sum(1 for t in raw_tasks if t['status'] == 'In Progress')
    q_count = sum(1 for t in raw_tasks if t['status'] == 'Pending QA')
    c_count = sum(1 for t in raw_tasks if t['status'] == 'Complete')
    b_count = sum(1 for t in raw_tasks if t['status'] == 'Blocked')
    st.bar_chart(pd.DataFrame({"Count": [u_count, p_count, q_count, c_count, b_count]}, index=["Unassigned", "In Progress", "Pending QA", "Complete", "Blocked"]), color="#FF4B4B")
    
    st.markdown("---")
    st.subheader("⚡ Shift Job Editing Grid")
    st.dataframe(tasks_df, hide_index=True, use_container_width=True)
    
    st.markdown("---")
    st.subheader("🔍 Quality Assurance Sign-Off Deck")
    has_pending = False
    for item in raw_tasks:
        if item['status'] == "Pending QA":
            has_pending = True
            st.markdown(f"**Task #{item['id']}: {item['title']}** ({item['assigned_to']})")
            if st.button("✅ Approve & Close Task", key=f"sup_app_{item['id']}"):
                requests.patch(f"{SUPABASE_URL}/rest/v1/facility_tasks?id=eq.{item['id']}", headers=DB_HEADERS, json={"status": "Complete"})
                st.rerun()
            if st.button("❌ Reject back to Field", key=f"sup_rej_{item['id']}"):
                requests.patch(f"{SUPABASE_URL}/rest/v1/facility_tasks?id=eq.{item['id']}", headers=DB_HEADERS, json={"status": "In Progress"})
                st.rerun()
    if not has_pending:
        st.info("No field validation records are currently awaiting verification.")

    st.markdown("---")
    st.subheader("➕ Generate New Maintenance Work Order")
    new_title = st.text_input("Task Title Summary")
    new_loc = st.text_input("Target Location Sector")
    new_pri = st.selectbox("Urgency Grade", ["Low", "Medium", "High", "Critical"])
    new_tech = st.selectbox("Assign Primary Tech Profile", crew_list)
    if st.button("Publish Work Ticket"):
        if new_title and new_loc:
            requests.post(f"{SUPABASE_URL}/rest/v1/facility_tasks", headers=DB_HEADERS, json={"title": new_title, "location": new_loc, "priority": new_pri, "assigned_to": new_tech, "status": "In Progress" if new_tech != "Unassigned" else "Unassigned"})
            st.success("Dispatched successfully!")
            st.rerun()

# === SUPERINTENDENT BOARD LOGIC ===
elif normalized_role == "superintendent":
    st.title("📊 Control Room Live Command Hub")
    
    t_all = len(raw_tasks)
    t_done = sum(1 for t in raw_tasks if t['status'] == 'Complete')
    t_block = sum(1 for t in raw_tasks if t['status'] == 'Blocked')
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Active Records", t_all)
    m2.metric("Archive Closures", t_done)
    m3.metric("🚨 Active Shift Delays", t_block)
    
    st.markdown("---")
    st.subheader("📊 Production Yield Progress Evaluation")
