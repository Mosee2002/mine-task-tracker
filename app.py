import streamlit as st
import pandas as pd
from datetime import datetime

# 1. PAGE SETUP
st.set_page_config(page_title="Mine Task Tracker & Analytics", layout="wide")

# 2. STATE DATA REGISTRY
if "user_registry" not in st.session_state:
    st.session_state.user_registry = {
        "supervisor1": {"password": "super789", "name": "Sarah Connor", "role": "Supervisor"},
        "superintendent1": {"password": "boss000", "name": "Mike Tyson", "role": "Superintendent"}
    }

if 'tasks_db' not in st.session_state:
    st.session_state.tasks_db = pd.DataFrame([
        {"id": 101, "title": "Replace 45kW Pump Motor Starter", "location": "Workshop Bench 2", "status": "In Progress", "priority": "High", "assigned_to": "Unassigned", "loto_verified": False, "jsa_completed": False, "updated_at": "2026-07-23 04:30"},
        {"id": 102, "title": "Calibrate Underground Gas Detectors", "location": "Level 4 North Shaft", "status": "Unassigned", "priority": "Critical", "assigned_to": "Unassigned", "loto_verified": False, "jsa_completed": False, "updated_at": "2026-07-23 01:15"},
        {"id": 103, "title": "Inspect Overhead Workshop Crane Cables", "location": "Workshop Bench 1", "status": "Complete", "priority": "High", "assigned_to": "Sarah Connor", "loto_verified": True, "jsa_completed": True, "updated_at": "2026-07-22 14:00"},
        {"id": 104, "title": "Re-wire Level 3 Sump Pump Float", "location": "Level 3 South Sump", "status": "Blocked", "priority": "Medium", "assigned_to": "Unassigned", "loto_verified": True, "jsa_completed": False, "updated_at": "2026-07-24 02:00"}
    ])

if "supt_to_sup_messages" not in st.session_state:
    st.session_state.supt_to_sup_messages = []
if "sup_to_wrk_messages" not in st.session_state:
    st.session_state.sup_to_wrk_messages = []

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_payload' not in st.session_state:
    st.session_state.user_payload = None

crew_list = ["Unassigned"] + [info["name"] for info in st.session_state.user_registry.values() if info["role"] == "Worker"]

# -------------------------------------------------------------
# SCREEN 1: LOGIN & REGISTRATION
# -------------------------------------------------------------
if not st.session_state.authenticated:
    st.title("🔒 Industrial Portal Secure Entry")
    login_column, register_column = st.columns(2)
    
    with login_column:
        st.subheader("Sign In")
        with st.form("login_form"):
            user_in = st.text_input("Username").strip().lower()
            pass_in = st.text_input("Password", type="password")
            if st.form_submit_button("Authenticate Profile"):
                if user_in in st.session_state.user_registry and st.session_state.user_registry[user_in]["password"] == pass_in:
                    st.session_state.authenticated = True
                    st.session_state.user_payload = st.session_state.user_registry[user_in]
                    st.rerun()
                else:
                    st.error("Invalid credentials.")
                    
    with register_column:
        st.subheader("🆕 Create Account / Set Password")
        with st.form("registration_form"):
            reg_user = st.text_input("Choose Username").strip().lower()
            reg_name = st.text_input("Full Name")
            reg_role = st.selectbox("Access Role", ["Worker", "Supervisor", "Superintendent"])
            reg_pass = st.text_input("Set Custom Password", type="password")
            if st.form_submit_button("Register Profile"):
                if not reg_user or not reg_name or not reg_pass:
                    st.error("All fields mandatory.")
                elif reg_user in st.session_state.user_registry:
                    st.error("Username taken.")
                else:
                    st.session_state.user_registry[reg_user] = {"password": reg_pass, "name": reg_name, "role": reg_role}
                    st.success("Registered!")

# -------------------------------------------------------------
# SCREEN 2: ACTIVE SECURED WORKSPACES
# -------------------------------------------------------------
else:
    user = st.session_state.user_payload
    tasks_df = st.session_state.tasks_db
    
    with st.sidebar:
        st.markdown(f"### User: **{user['name']}**")
        st.info(f"Role: {user['role']}")
        if st.button("🚪 Logout Application"):
            st.session_state.authenticated = False
            st.session_state.user_payload = None
            st.rerun()

    # --- WORKER VIEW ---
    if user['role'] == "Worker":
        st.title("👷 Field Worker Workspace")
        
        st.subheader("🔔 Supervisor Broadcast Notices")
        if not st.session_state.sup_to_wrk_messages:
            st.info("No active broadcast dispatch notices from supervisors.")
        else:
            for msg in reversed(st.session_state.sup_to_wrk_messages):
                st.warning(f"📣 **{msg['sender']}**: {msg['text']}")

        tab_personal, tab_master_board = st.tabs(["📋 My Dashboard", "🌐 Master Open Board"])
        
        with tab_personal:
            my_tasks = tasks_df[tasks_df['assigned_to'] == user['name']]
            if my_tasks.empty:
                st.info("No explicitly assigned jobs.")
            else:
                for idx, row in my_tasks.iterrows():
                    with st.container(border=True):
                        st.markdown(f"#### Task #{row['id']}: {row['title']}")
                        loto = st.checkbox("LOTO Isolated", value=row['loto_verified'], key=f"wk_loto_{row['id']}")
                        jsa = st.checkbox("JSA Signed", value=row['jsa_completed'], key=f"wk_jsa_{row['id']}")
                        st.session_state.tasks_db.at[idx, 'loto_verified'] = loto
                        st.session_state.tasks_db.at[idx, 'jsa_completed'] = jsa
                        
                        if not loto or not jsa:
                            st.error("🔒 Safety Checkboxes Required.")
                        else:
                            action_status = st.selectbox("Update Status:", ["In Progress", "Pending QA", "Blocked"], key=f"wk_stat_{row['id']}")
                            if action_status != row['status']:
                                st.session_state.tasks_db.at[idx, 'status'] = action_status
                                st.rerun()
                                
        with tab_master_board:
            st.subheader("🌐 Pending & Unassigned Facility Tasks")
            open_jobs_df = tasks_df[tasks_df['status'] != "Complete"]
            st.dataframe(open_jobs_df[["id", "title", "location", "priority", "status", "assigned_to"]], hide_index=True, use_container_width=True)

    # --- SUPERVISOR VIEW ---
    elif user['role'] == "Supervisor":
        st.title("📋 Supervisor Control Terminal")
        
        if st.session_state.supt_to_sup_messages:
            st.subheader("📥 Management Directives")
            for msg in reversed(st.session_state.supt_to_sup_messages):
                st.info(f"📊 **{msg['sender']}**: {msg['text']}")

        sup_t1, sup_t2, sup_t3, sup_t4 = st.tabs(["📊 Progress Charts", "⚡ Shift Tracking Grid", "🔍 QA Approval Deck", "📣 Message Board"])
        
        with sup_t1:
            st.subheader("📈 Live Shift Production Progress")
            # Fail-safe indexing array structures
            u_count = len(tasks_df[tasks_df['status'] == 'Unassigned'])
            p_count = len(tasks_df[tasks_df['status'] == 'In Progress'])
            q_count = len(tasks_df[tasks_df['status'] == 'Pending QA'])
            c_count = len(tasks_df[tasks_df['status'] == 'Complete'])
            b_count = len(tasks_df[tasks_df['status'] == 'Blocked'])
            
            chart_data = pd.DataFrame({
                "Tasks Count": [u_count, p_count, q_count, c_count, b_count]
            }, index=["Unassigned", "In Progress", "Pending QA", "Complete", "Blocked"])
            st.bar_chart(chart_data, color="#FF4B4B")
            
        with sup_t2:
            updated_grid = st.data_editor(st.session_state.tasks_db, hide_index=True, use_container_width=True)
            st.session_state.tasks_db = updated_grid
            
        with sup_t3:
            pending_items = tasks_df[tasks_df['status'] == "Pending QA"]
            if pending_items.empty:
                st.info("No field cards awaiting verification.")
            else:
                for idx, row in pending_items.iterrows():
                    st.markdown(f"**Task #{row['id']}: {row['title']}**")
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("✅ Approve", key=f"sup_app_{row['id']}"):
                            st.session_state.tasks_db.at[idx, 'status'] = "Complete"
                            st.rerun()
                    with b2:
                        if st.button("❌ Reject", key=f"sup_rej_{row['id']}"):
                            st.session_state.tasks_db.at[idx, 'status'] = "In Progress"
                            st.rerun()
        with sup_t4:
            new_title = st.text_input("New Task Description")
            new_loc = st.text_input("Location Sector")
            new_pri = st.selectbox("Urgency", ["Low", "Medium", "High", "Critical"])
            new_tech = st.selectbox("Assign Profile", crew_list)
            if st.button("Publish Ticket"):
                new_id = int(st.session_state.tasks_db["id"].max() + 1)
                new_row = {"id": new_id, "title": new_title, "location": new_loc, "priority": new_pri, "assigned_to": new_tech, "status": "In Progress" if new_tech != "Unassigned" else "Unassigned", "loto_verified": False, "jsa_completed": False, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
                st.session_state.tasks_db = pd.concat([st.session_state.tasks_db, pd.DataFrame([new_row])], ignore_index=True)
                st.rerun()

            st.markdown("---")
            
