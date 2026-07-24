import streamlit as st
import pandas as pd

# 1. FACILITY WEB APP INTIALIZATION
st.set_page_config(page_title="Mine Task Tracker & Analytics", layout="wide")

# 2. STATE DATA REGISTRY FOR OPERATIONAL MEMORY
if "user_registry" not in st.session_state:
    st.session_state.user_registry = {
        "supervisor1": {"password": "super789", "name": "Sarah Connor", "role": "Supervisor"},
        "superintendent1": {"password": "boss000", "name": "Mike Tyson", "role": "Superintendent"}
    }

if 'tasks_db' not in st.session_state:
    st.session_state.tasks_db = [
        {"id": 101, "title": "Replace 45kW Pump Motor Starter", "location": "Workshop Bench 2", "status": "In Progress", "priority": "High", "assigned_to": "Unassigned", "loto_verified": False, "jsa_completed": False, "updated_at": "2026-07-23 04:30"},
        {"id": 102, "title": "Calibrate Underground Gas Detectors", "location": "Level 4 North Shaft", "status": "Unassigned", "priority": "Critical", "assigned_to": "Unassigned", "loto_verified": False, "jsa_completed": False, "updated_at": "2026-07-23 01:15"},
        {"id": 103, "title": "Inspect Overhead Workshop Crane Cables", "location": "Workshop Bench 1", "status": "Complete", "priority": "High", "assigned_to": "Sarah Connor", "loto_verified": True, "jsa_completed": True, "updated_at": "2026-07-22 14:00"},
        {"id": 104, "title": "Re-wire Level 3 Sump Pump Float", "location": "Level 3 South Sump", "status": "Blocked", "priority": "Medium", "assigned_to": "Unassigned", "loto_verified": True, "jsa_completed": False, "updated_at": "2026-07-24 02:00"}
    ]

if "supt_to_sup_messages" not in st.session_state:
    st.session_state.supt_to_sup_messages = []
if "sup_to_wrk_messages" not in st.session_state:
    st.session_state.sup_to_wrk_messages = []

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_payload' not in st.session_state:
    st.session_state.user_payload = None

# Build clean dynamic dropdown arrays to capture every created worker profile name
crew_list = ["Unassigned"] + [info["name"] for info in st.session_state.user_registry.values() if str(info["role"]).strip().lower() == "worker"]

# -------------------------------------------------------------
# SCREEN 1: LOGIN & REGISTRATION SECTOR
# -------------------------------------------------------------
if not st.session_state.authenticated:
    st.title("🔒 Industrial Portal Secure Entry")
    login_column, register_column = st.columns(2)
    
    with login_column:
        st.subheader("Sign In")
        user_in = st.text_input("Username", key="login_u").strip().lower()
        pass_in = st.text_input("Password", type="password", key="login_p")
        if st.button("Authenticate Profile"):
            if user_in in st.session_state.user_registry and st.session_state.user_registry[user_in]["password"] == pass_in:
                st.session_state.user_payload = st.session_state.user_registry[user_in]
                st.session_state.authenticated = True
                st.success("Authenticated! Press any button or change a field to enter.")
            else:
                st.error("Invalid credentials.")
                    
    with register_column:
        st.subheader("🆕 Create Account / Set Password")
        reg_user = st.text_input("Choose Username", key="reg_u").strip().lower()
        reg_name = st.text_input("Full Name", key="reg_n")
        reg_role = st.selectbox("Access Role", ["Worker", "Supervisor", "Superintendent"], key="reg_r")
        reg_pass = st.text_input("Set Custom Password", type="password", key="reg_p")
        if st.button("Register Profile"):
            if not reg_user or not reg_name or not reg_pass:
                st.error("All fields mandatory.")
            elif reg_user in st.session_state.user_registry:
                st.error("Username taken.")
            else:
                st.session_state.user_registry[reg_user] = {"password": reg_pass, "name": reg_name, "role": reg_role}
                st.success("Registered successfully! You can now log in.")

# -------------------------------------------------------------
# SCREEN 2: ACTIVE SECURED WORKSPACES
# -------------------------------------------------------------
else:
    user = st.session_state.user_payload
    normalized_role = str(user['role']).strip().lower()
    
    with st.sidebar:
        st.markdown(f"### User: **{user['name']}**")
        st.info(f"Authorized Role: {user['role']}")
        if st.button("🚪 Logout Application", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.user_payload = None
            st.write("Logged out. Please click anywhere to return to the login screen.")

    # Convert session state array directly into a DataFrame for standard filtering commands
    tasks_df = pd.DataFrame(st.session_state.tasks_db)

    # =============================================================
    # INTERFACE TIER A: FIELD WORKERS
    # =============================================================
    if normalized_role == "worker":
        st.title("👷 Field Worker Workspace")
        
        st.subheader("🔔 Supervisor Broadcast Notices")
        if not st.session_state.sup_to_wrk_messages:
            st.info("No active broadcast dispatch notices from supervisors.")
        else:
            for msg in reversed(st.session_state.sup_to_wrk_messages):
                st.warning(f"📣 **{msg['sender']}**: {msg['text']}")

        tab_personal, tab_master_board = st.tabs(["📋 My Dashboard", "🌐 Master Open Board"])
        
        with tab_personal:
            # Look up tasks assigned to this specific logged-in user name string
            has_tasks = False
            for idx, item in enumerate(st.session_state.tasks_db):
                if item['assigned_to'] == user['name']:
                    has_tasks = True
                    with st.container(border=True):
                        st.markdown(f"#### Task #{item['id']}: {item['title']}")
                        st.write(f"📍 Location: {item['location']} | Status: `{item['status']}`")
                        
                        loto = st.checkbox("LOTO Isolated", value=item['loto_verified'], key=f"wk_loto_{item['id']}")
                        jsa = st.checkbox("JSA Signed", value=item['jsa_completed'], key=f"wk_jsa_{item['id']}")
                        
                        st.session_state.tasks_db[idx]['loto_verified'] = loto
                        st.session_state.tasks_db[idx]['jsa_completed'] = jsa
                        
                        if not loto or not jsa:
                            st.error("🔒 Safety Checkboxes Required.")
                        else:
                            action_status = st.selectbox("Update Status:", ["In Progress", "Pending QA", "Blocked"], index=["In Progress", "Pending QA", "Blocked"].index(item['status']) if item['status'] in ["In Progress", "Pending QA", "Blocked"] else 0, key=f"wk_stat_{item['id']}")
                            if action_status != item['status']:
                                st.session_state.tasks_db[idx]['status'] = action_status
                                st.success("Status updated!")
            if not has_tasks:
                st.info("No explicitly assigned jobs.")
                                
        with tab_master_board:
            st.subheader("🌐 Pending & Unassigned Facility Tasks")
            open_jobs_df = tasks_df[tasks_df['status'] != "Complete"]
            st.dataframe(open_jobs_df[["id", "title", "location", "priority", "status", "assigned_to"]], hide_index=True, use_container_width=True)

    # =============================================================
    # INTERFACE TIER B: AREA SUPERVISORS
    # =============================================================
    elif normalized_role == "supervisor":
        st.title("📋 Supervisor Control Terminal")
        
        if st.session_state.supt_to_sup_messages:
            st.subheader("📥 Management Directives")
            for msg in reversed(st.session_state.supt_to_sup_messages):
                st.info(f"📊 **{msg['sender']}**: {msg['text']}")

        sup_t1, sup_t2, sup_t3, sup_t4 = st.tabs(["📊 Progress Charts", "⚡ Shift Tracking Grid", "🔍 QA Approval Deck", "📣 Message Board"])
        
        with sup_t1:
            st.subheader("📈 Live Shift Production Progress")
            u_count = sum(1 for t in st.session_state.tasks_db if t['status'] == 'Unassigned')
            p_count = sum(1 for t in st.session_state.tasks_db if t['status'] == 'In Progress')
            q_count = sum(1 for t in st.session_state.tasks_db if t['status'] == 'Pending QA')
            c_count = sum(1 for t in st.session_state.tasks_db if t['status'] == 'Complete')
            b_count = sum(1 for t in st.session_state.tasks_db if t['status'] == 'Blocked')
            
            chart_data = pd.DataFrame({"Tasks Count": [u_count, p_count, q_count, c_count, b_count]}, index=["Unassigned", "In Progress", "Pending QA", "Complete", "Blocked"])
            st.bar_chart(chart_data, color="#FF4B4B")
            
        with sup_t2:
            updated_grid = st.data_editor(tasks_df, hide_index=True, use_container_width=True)
            # Re-serialize edited grid back into session storage memory blocks safely
            st.session_state.tasks_db = updated_grid.to_dict(orient="records")
            
        with sup_t3:
            has_pending = False
            for idx, item in enumerate(st.session_state.tasks_db):
                if item['status'] == "Pending QA":
                    has_pending = True
                    st.markdown(f"**Task #{item['id']}: {item['title']}** ({item['assigned_to']})")
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("✅ Approve", key=f"sup_app_{item['id']}"):
                
