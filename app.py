import streamlit as st
import pandas as pd

# 1. FACILITY SYSTEM APPLICATION ARCHITECTURE INITIALIZATION
st.set_page_config(page_title="Mine Task Tracker", layout="wide")

# 2. STATE DATA REGISTRY FOR OPERATIONAL MEMORY BLOCKS
if "user_registry" not in st.session_state:
    st.session_state.user_registry = {
        "supervisor1": {"password": "super789", "name": "Sarah Connor", "role": "Supervisor"},
        "superintendent1": {"password": "boss000", "name": "Mike Tyson", "role": "Superintendent"}
    }

if 'tasks_db' not in st.session_state:
    st.session_state.tasks_db = [
        {"id": 101, "title": "Replace 45kW Pump Motor Starter", "location": "Workshop Bench 2", "status": "In Progress", "priority": "High", "assigned_to": "Unassigned", "loto_verified": False, "jsa_completed": False},
        {"id": 102, "title": "Calibrate Underground Gas Detectors", "location": "Level 4 North Shaft", "status": "Unassigned", "priority": "Critical", "assigned_to": "Unassigned", "loto_verified": False, "jsa_completed": False},
        {"id": 103, "title": "Inspect Overhead Workshop Crane Cables", "location": "Workshop Bench 1", "status": "Complete", "priority": "High", "assigned_to": "Sarah Connor", "loto_verified": True, "jsa_completed": True},
        {"id": 104, "title": "Re-wire Level 3 Sump Pump Float", "location": "Level 3 South Sump", "status": "Blocked", "priority": "Medium", "assigned_to": "Unassigned", "loto_verified": True, "jsa_completed": False}
    ]

if "supt_to_sup_messages" not in st.session_state:
    st.session_state.supt_to_sup_messages = []
if "sup_to_wrk_messages" not in st.session_state:
    st.session_state.sup_to_wrk_messages = []

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_payload' not in st.session_state:
    st.session_state.user_payload = None

# 3. SECURE AUTHENTICATION SCREEN CONTROLS (IF NOT LOGGED IN)
if not st.session_state.authenticated:
    st.title("🔒 Industrial Portal Secure Entry")
    st.subheader("Sign In")
    user_in = st.text_input("Username", key="lin_user").strip().lower()
    pass_in = st.text_input("Password", type="password", key="lin_pass")
    if st.button("Authenticate Profile"):
        if user_in in st.session_state.user_registry and st.session_state.user_registry[user_in]["password"] == pass_in:
            st.session_state.user_payload = st.session_state.user_registry[user_in]
            st.session_state.authenticated = True
            st.success("Authenticated! Press button again to load workspace view.")
        else:
            st.error("Invalid credentials entered.")
    st.markdown("---")
    st.subheader("🆕 Register New Account")
    reg_user = st.text_input("Choose Username", key="rg_u").strip().lower()
    reg_name = st.text_input("Enter Full Name", key="rg_n")
    reg_role = st.selectbox("Assign Access Level Role", ["Worker", "Supervisor", "Superintendent"], key="rg_r")
    reg_pass = st.text_input("Set Security Password", type="password", key="rg_p")
    if st.button("Register to System Ledger"):
        if not reg_user or not reg_name or not reg_pass:
            st.error("All data input values are mandatory.")
        elif reg_user in st.session_state.user_registry:
            st.error("Username already registered inside memory.")
        else:
            st.session_state.user_registry[reg_user] = {"password": reg_pass, "name": reg_name, "role": reg_role}
            st.success("Account profile successfully registered! You can now sign in above.")
    st.stop()

# 4. UNIVERSAL APPLICATION WORKSPACE HEADER ENGINE
user = st.session_state.user_payload
normalized_role = str(user['role']).strip().lower()
tasks_df = pd.DataFrame(st.session_state.tasks_db)
crew_list = ["Unassigned"] + [info["name"] for info in st.session_state.user_registry.values() if str(info["role"]).strip().lower() == "worker"]

with st.sidebar:
    st.markdown(f"### Profile: **{user['name']}**")
    st.info(f"Role: {user['role']}")
    if st.button("🚪 Logout Application"):
        st.session_state.authenticated = False
        st.session_state.user_payload = None

# 5. RENDER PLATFORM SECTION A: WORKERS (Runs if user is a Worker)
if normalized_role == "worker":
    st.title("Worker Workspace")
    st.subheader("🔔 Direct Messages from Supervisors")
    if not st.session_state.sup_to_wrk_messages:
        st.info("No active broadcast dispatch notices from supervisors.")
    for msg in reversed(st.session_state.sup_to_wrk_messages):
        st.warning(f"📣 **{msg['sender']}**: {msg['text']}")
    st.markdown("---")
    st.subheader("📋 My Active Task Dashboard")
    has_tasks = False
    for idx, item in enumerate(st.session_state.tasks_db):
        if item['assigned_to'] == user['name']:
            has_tasks = True
            with st.container(border=True):
                st.markdown(f"#### Task #{item['id']}: {item['title']}")
                loto = st.checkbox("LOTO Isolated", value=item['loto_verified'], key=f"wk_loto_{item['id']}")
                jsa = st.checkbox("JSA Signed", value=item['jsa_completed'], key=f"wk_jsa_{item['id']}")
                st.session_state.tasks_db[idx]['loto_verified'] = loto
                st.session_state.tasks_db[idx]['jsa_completed'] = jsa
                if not loto or not jsa:
                    st.error("🔒 Safety Interlocks Active.")
                else:
                    action_status = st.selectbox("Update Status:", ["In Progress", "Pending QA", "Blocked"], index=["In Progress", "Pending QA", "Blocked"].index(item['status']) if item['status'] in ["In Progress", "Pending QA", "Blocked"] else 0, key=f"wk_stat_{item['id']}")
                    if action_status != item['status']:
                        st.session_state.tasks_db[idx]['status'] = action_status
    if not has_tasks:
        st.info("No explicit jobs assigned to your specific tag name right now.")
    st.markdown("---")
    st.subheader("🌐 Complete List of All Facility Open Tasks")
    open_jobs = tasks_df[tasks_df['status'] != "Complete"]
    st.dataframe(open_jobs[["id", "title", "location", "priority", "status", "assigned_to"]], hide_index=True, use_container_width=True)

# 6. RENDER PLATFORM SECTION B: SUPERVISORS (Runs if user is a Supervisor)
if normalized_role == "supervisor":
    st.title("📋 Supervisor Control Terminal")
    if st.session_state.supt_to_sup_messages:
        st.subheader("📥 Management Directives")
    for msg in reversed(st.session_state.supt_to_sup_messages):
        st.info(f"📊 **{msg['sender']}**: {msg['text']}")
    st.markdown("---")
    st.subheader("📊 Live Shift Production Progress")
    u_count = sum(1 for t in st.session_state.tasks_db if t['status'] == 'Unassigned')
    p_count = sum(1 for t in st.session_state.tasks_db if t['status'] == 'In Progress')
    q_count = sum(1 for t in st.session_state.tasks_db if t['status'] == 'Pending QA')
    c_count = sum(1 for t in st.session_state.tasks_db if t['status'] == 'Complete')
    b_count = sum(1 for t in st.session_state.tasks_db if t['status'] == 'Blocked')
    st.bar_chart(pd.DataFrame({"Count": [u_count, p_count, q_count, c_count, b_count]}, index=["Unassigned", "In Progress", "Pending QA", "Complete", "Blocked"]), color="#FF4B4B")
    st.markdown("---")
    st.subheader("⚡ Shift Job Editing Grid")
    updated_grid = st.data_editor(tasks_df, hide_index=True, use_container_width=True)
    st.session_state.tasks_db = updated_grid.to_dict(orient="records")
    st.markdown("---")
    st.subheader("🔍 Quality Assurance Sign-Off Deck")
    has_pending = False
    for idx, item in enumerate(st.session_state.tasks_db):
        if item['status'] == "Pending QA":
            has_pending = True
            st.markdown(f"**Task #{item['id']}: {item['title']}** ({item['assigned_to']})")
            if st.button("✅ Approve & Close Task", key=f"sup_app_{item['id']}"):
                st.session_state.tasks_db[idx]['status'] = "Complete"
            if st.button("❌ Reject back to Field", key=f"sup_rej_{item['id']}"):
                st.session_state.tasks_db[idx]['status'] = "In Progress"
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
            new_id = int(max(t['id'] for t in st.session_state.tasks_db) + 1)
            st.session_state.tasks_db.append({"id": new_id, "title": new_title, "location": new_loc, "priority": new_pri, "assigned_to": new_tech, "status": "In Progress" if new_tech != "Unassigned" else "Unassigned", "loto_verified": False, "jsa_completed": False})
            st.success("Dispatched successfully!")
    st.markdown("---")
    st.subheader("📣 Dispatch Text Notice to Workers Dashboard")
    msg_to_workers = st.text_area("Type instructions here...")
    if st.button("Broadcast Message to Workers"):
        if msg_to_workers:
            st.session_state.sup_to_wrk_messages.append({"sender": user['name'], "text": msg_to_workers})
            st.success("Broadcast dispatched!")

# 7. RENDER PLATFORM SECTION C: SUPERINTENDENTS (Runs if user is a Superintendent)
if normalized_role == "superintendent":
    st.title("📊 Control Room Live Command Hub")
    t_all = len(st.session_state.tasks_db)
    t_done = sum(1 for t in st.session_state.tasks_db if t['status'] == 'Complete')
    t_block = sum(1 for t in st.session_state.tasks_db if t['status'] == 'Blocked')
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Active Records", t_all)
    m2.metric("Archive Closures", t_done)
    m3.metric("🚨 Active Shift Delays", t_block)
    st.markdown("---")
    
