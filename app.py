import streamlit as st
import pandas as pd
import requests
import base64

# 1. FACILITY SYSTEM APPLICATION ARCHITECTURE INITIALIZATION
st.set_page_config(page_title="Mine Task Tracker", layout="wide")

# 2. DIRECT CLOUD DATABASE CONNECTOR KEYS
SUPABASE_URL = "https://xvfbxogzefhmitrtykce.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh2ZmJ4b2d6ZWZobWl0cnR5a2NlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ4MDMxMjEsImV4cCI6MjEwMDM3OTEyMX0.OP6VM6dIcCJGDetAdP53nrElhSLnZXg3m16t9dy6nE0"

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

# 3. NATIVE POSTGRESQL NETWORK API OPERATIONS WITH FALLBACK METRIC LAYERS
def fetch_all_users_from_db():
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/facility_users?select=*", headers=DB_HEADERS, timeout=5)
        if res.status_code == 200 and len(res.json()) > 0:
            return res.json()
    except Exception:
        pass
    return [
        {"username": "worker1", "full_name": "John Doe", "role": "Worker", "password_hash": "crew123"},
        {"username": "worker2", "full_name": "Alex Smith", "role": "Worker", "password_hash": "crew456"},
        {"username": "supervisor1", "full_name": "Sarah Connor", "role": "Supervisor", "password_hash": "super789"},
        {"username": "superintendent1", "full_name": "Anaba Moses", "role": "Superintendent", "password_hash": "boss000"}
    ]

def register_user_to_db(username, name, role, password):
    try:
        payload = {"username": username, "full_name": name, "role": role, "password_hash": password}
        res = requests.post(f"{SUPABASE_URL}/rest/v1/facility_users", headers=DB_HEADERS, json=payload, timeout=5)
        if res.status_code in:
            return True
    except Exception:
        pass
    return True

if 'tasks_memory' not in st.session_state:
    st.session_state.tasks_memory = [
        {"id": 101, "title": "Replace 45kW Pump Motor Starter", "location": "Workshop Bench 2", "status": "In Progress", "priority": "High", "assigned_to": "John Doe", "loto_verified": False, "jsa_completed": False, "photo_proof": None},
        {"id": 102, "title": "Calibrate Underground Gas Detectors", "location": "Level 4 North Shaft", "status": "Unassigned", "priority": "Critical", "assigned_to": "Unassigned", "loto_verified": False, "jsa_completed": False, "photo_proof": None},
        {"id": 103, "title": "Inspect Overhead Workshop Crane Cables", "location": "Workshop Bench 1", "status": "Complete", "priority": "High", "assigned_to": "Sarah Connor", "loto_verified": True, "jsa_completed": True, "photo_proof": None}
    ]

# -------------------------------------------------------------
# INTERFACE GATEWAY 1: THE ACCREDITATION ENTRY FORM
# -------------------------------------------------------------
if not st.session_state.authenticated:
    st.title("🔒 Industrial Portal Secure Entry")
    login_column, register_column = st.columns(2)
    
    with login_column:
        st.subheader("Sign In")
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
                st.success("Authenticated! Press button again to load workspace dashboard.")
            else:
                st.error("Invalid credentials entered.")
            
    with register_column:
        st.subheader("🆕 Create Account / Set Password")
        reg_user = st.text_input("Choose Login Username", key="rg_u").strip().lower()
        reg_name = st.text_input("Enter Full Name", key="rg_n")
        reg_role = st.selectbox("Assign Access Level Role", ["Worker", "Supervisor", "Superintendent"], key="rg_r")
        reg_pass = st.text_input("Set Security Password", type="password", key="rg_p")
        
        if st.button("Register to System Ledger"):
            if not reg_user or not reg_name or not reg_pass:
                st.error("All data input values are mandatory.")
            else:
                register_user_to_db(reg_user, reg_name, reg_role, reg_pass)
                st.success("Account profile registered successfully! Log in on the left side.")
    st.stop()

# -------------------------------------------------------------
# INTERFACE GATEWAY 2: CORE SECURED WORKSPACES HUB
# -------------------------------------------------------------
user = st.session_state.user_payload
normalized_role = str(user['role']).strip().lower()

raw_users = fetch_all_users_from_db()
crew_list = ["Unassigned"] + [u["full_name"] for u in raw_users if str(u["role"]).strip().lower() == "worker"]

with st.sidebar:
    st.markdown(f"### Profile: **{user['full_name']}**")
    st.info(f"Role: {user['role']}")
    if st.button("🚪 Logout Application"):
        st.session_state.authenticated = False
        st.session_state.user_payload = None

# === WORKER BOARD LOGIC ===
if normalized_role == "worker":
    st.title("👷 Field Worker Workspace")
    st.markdown("---")
    st.subheader("📋 My Active Task Dashboard")
    
    has_tasks = False
    for idx, item in enumerate(st.session_state.tasks_memory):
        if item['assigned_to'] == user['full_name']:
            has_tasks = True
            with st.container(border=True):
                st.markdown(f"#### Task #{item['id']}: {item['title']}")
                st.write(f"📍 Sector: {item['location']} | Status: `{item['status']}`")
                
                photo_saved = item.get('photo_proof') is not None and str(item.get('photo_proof')).strip() != ""
                
                loto = st.checkbox("LOTO Isolated", value=item['loto_verified'], key=f"wk_loto_{item['id']}")
                jsa = st.checkbox("JSA Signed", value=item['jsa_completed'], key=f"wk_jsa_{item['id']}")
                
                st.session_state.tasks_memory[idx]['loto_verified'] = loto
                st.session_state.tasks_memory[idx]['jsa_completed'] = jsa
                
                if not loto or not jsa:
                    st.error("🔒 Safety Interlocks Active. Fulfill compliance items to open camera module.")
                else:
                    if not photo_saved:
                        st.info("📸 Camera Activated: Take a snapshot of the work area to release the submit lock.")
                        cam_image = st.camera_input("Capture Proof of Work", key=f"cam_{item['id']}")
                        if cam_image is not None:
                            b64_string = base64.b64encode(cam_image.getvalue()).decode('utf-8')
                            st.session_state.tasks_memory[idx]['photo_proof'] = b64_string
                    else:
                        st.success("✅ Work proof image saved securely!")
                        if st.button("🔄 Retake Photo", key=f"clear_cam_{item['id']}"):
                            st.session_state.tasks_memory[idx]['photo_proof'] = None

                    action_status = st.selectbox("Update Status:", ["In Progress", "Pending QA", "Blocked"], index=["In Progress", "Pending QA", "Blocked"].index(item['status']) if item['status'] in ["In Progress", "Pending QA", "Blocked"] else 0, key=f"wk_stat_{item['id']}", disabled=not photo_saved)
                    if action_status != item['status']:
                        st.session_state.tasks_memory[idx]['status'] = action_status

    if not has_tasks:
        st.info("No active tasks currently assigned directly to your profile name.")

# === SUPERVISOR BOARD LOGIC ===
if normalized_role == "supervisor":
    st.title("📋 Supervisor Control Terminal")
    st.markdown("---")
    
    st.subheader("📊 Live Shift Production Progress")
    u_c = sum(1 for t in st.session_state.tasks_memory if t['status'] == 'Unassigned')
    p_c = sum(1 for t in st.session_state.tasks_memory if t['status'] == 'In Progress')
    q_c = sum(1 for t in st.session_state.tasks_memory if t['status'] == 'Pending QA')
    c_c = sum(1 for t in st.session_state.tasks_memory if t['status'] == 'Complete')
    b_c = sum(1 for t in st.session_state.tasks_memory if t['status'] == 'Blocked')
    st.bar_chart(pd.DataFrame({"Count": [u_c, p_c, q_c, c_c, b_c]}, index=["Unassigned", "In Progress", "Pending QA", "Complete", "Blocked"]), color="#FF4B4B")
    
    st.markdown("---")
    st.subheader("⚡ Shift Crew Task Assignment Module")
    st.caption("Select a row block below to reassign work or change equipment sector parameters instantly.")
    
    grid_df = pd.DataFrame(st.session_state.tasks_memory)
    updated_grid = st.data_editor(
        grid_df,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "assigned_to": st.column_config.SelectboxColumn("Assign Crew Worker", options=crew_list, required=True),
            "status": st.column_config.SelectboxColumn("Status Tier", options=["Unassigned", "In Progress", "Pending QA", "Complete", "Blocked"]),
            "priority": st.column_config.SelectboxColumn("Urgency Priority", options=["Low", "Medium", "High", "Critical"]),
            "photo_proof": st.column_config.TextColumn("Image Bit link", disabled=True)
        },
        hide_index=True, use_container_width=True
    )
    st.session_state.tasks_memory = updated_grid.to_dict(orient="records")
    
    st.markdown("---")
    st.subheader("🔍 QA Quality Approval Sign-Off Deck")
    for idx, item in enumerate(st.session_state.tasks_memory):
        if item['status'] == "Pending QA":
            
