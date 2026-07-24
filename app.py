import streamlit as st
import pandas as pd
from datetime import datetime

# 1. LIVE WEB LAYOUT CONFIGURATION
st.set_page_config(page_title="Mine Task Tracker", layout="wide")

# 2. STATE DATA REGISTRY FOR CORE REPOSITORIES
if "user_registry" not in st.session_state:
    st.session_state.user_registry = {
        "supervisor1": {"password": "super789", "name": "Sarah Connor", "role": "Supervisor"},
        "superintendent1": {"password": "boss000", "name": "Mike Tyson", "role": "Superintendent"}
    }

if 'tasks_db' not in st.session_state:
    st.session_state.tasks_db = pd.DataFrame([
        {"id": 101, "title": "Replace 45kW Pump Motor Starter", "location": "Workshop Bench 2", "status": "In Progress", "priority": "High", "assigned_to": "Unassigned", "loto_verified": False, "jsa_completed": False, "updated_at": "2026-07-23 04:30"},
        {"id": 102, "title": "Calibrate Underground Gas Detectors", "location": "Level 4 North Shaft", "status": "Unassigned", "priority": "Critical", "assigned_to": "Unassigned", "loto_verified": False, "jsa_completed": False, "updated_at": "2026-07-23 01:15"}
    ])

# Communications ledger channel memory lists
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
# SCREEN 1: LOGIN & CREATE PROFILE INTERFACE
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
                    st.error("Invalid credentials entered.")
                    
    with register_column:
        st.subheader("🆕 Create Account / Set Password")
        with st.form("registration_form"):
            reg_user = st.text_input("Choose Username (e.g. josh1)").strip().lower()
            reg_name = st.text_input("Full Name")
            reg_role = st.selectbox("Access Role", ["Worker", "Supervisor", "Superintendent"])
            reg_pass = st.text_input("Set Custom Password", type="password")
            
            if st.form_submit_button("Register to System Ledger"):
                if not reg_user or not reg_name or not reg_pass:
                    st.error("All registration inputs are mandatory.")
                elif reg_user in st.session_state.user_registry:
                    st.error("Username already claimed.")
                else:
                    st.session_state.user_registry[reg_user] = {"password": reg_pass, "name": reg_name, "role": reg_role}
                    st.success(f"Registered! Profile ready for sign-in.")

# -------------------------------------------------------------
# SCREEN 2: MAIN ACCREDITED OPERATION DECKS
# -------------------------------------------------------------
else:
    user = st.session_state.user_payload
    tasks_df = st.session_state.tasks_db
    
    with st.sidebar:
        st.markdown(f"### User: **{user['name']}**")
        st.info(f"Authorized Role: {user['role']}")
        if st.button("🚪 Logout Application"):
            st.session_state.authenticated = False
            st.session_state.user_payload = None
            st.rerun()

    # -------------------------------------------------------------
    # APPLICATION PROFILE A: WORKER VIEW
    # -------------------------------------------------------------
    if user['role'] == "Worker":
        st.title("👷 Field Worker Workspace")
        
        # Real-time Broadcast Messages received from Supervisors
        st.subheader("🔔 Communications Channel from Supervisors")
        if not st.session_state.sup_to_wrk_messages:
            st.info("No active broadcast dispatch notices active from supervisors.")
        else:
            for msg in reversed(st.session_state.sup_to_wrk_messages):
                st.warning(f"📣 **{msg['sender']}** ({msg['time']}): {msg['text']}")

        st.markdown("---")
        
        # Dual Segment View layout setup for Workers
        tab_personal, tab_master_board = st.tabs(["📋 My Assigned Job Dashboard", "🗂️ Master Facility Open Board"])
        
        with tab_personal:
            my_tasks = tasks_df[tasks_df['assigned_to'] == user['name']]
            if my_tasks.empty:
                st.info("No explicit jobs assigned to your specific technician tag right now.")
            else:
                for idx, row in my_tasks.iterrows():
                    with st.container(border=True):
                        st.markdown(f"#### Task #{row['id']}: {row['title']}")
                        st.write(f"📍 Sector Location: {row['location']} | Tier Status: `{row['status']}`")
                        
                        loto = st.checkbox("Lockout / Tagout (LOTO) Isolated", value=row['loto_verified'], key=f"wk_loto_{row['id']}")
                        jsa = st.checkbox("Job Safety Analysis (JSA) Signed", value=row['jsa_completed'], key=f"wk_jsa_{row['id']}")
                        st.session_state.tasks_db.at[idx, 'loto_verified'] = loto
                        st.session_state.tasks_db.at[idx, 'jsa_completed'] = jsa
                        
                        if not loto or not jsa:
                            st.error("🔒 Safety Interlocks Active. Fulfill compliance checkmarks to update status.")
                        else:
                            action_status = st.selectbox("Update Status:", ["In Progress", "Pending QA", "Blocked"], key=f"wk_stat_{row['id']}")
                            if action_status != row['status']:
                                st.session_state.tasks_db.at[idx, 'status'] = action_status
                                st.rerun()
                                
        with tab_master_board:
            st.subheader("🌐 Complete List of Pending and Unassigned Shift Tasks")
            st.caption("Every worker can inspect this board to review open, unassigned, or blocked maintenance work across the yard.")
            
            # Displays all tasks that are NOT complete so workers see what needs doing
            open_jobs_df = tasks_df[tasks_df['status'] != "Complete"]
            if open_jobs_df.empty:
                st.success("All facility maintenance tasks closed out for this rotation!")
            else:
                st.dataframe(
                    open_jobs_df[["id", "title", "location", "priority", "status", "assigned_to"]],
                    hide_index=True,
                    use_container_width=True
                )

    # -------------------------------------------------------------
    # APPLICATION PROFILE B: SUPERVISOR VIEW
    # -------------------------------------------------------------
    elif user['role'] == "Supervisor":
        st.title("📋 Supervisor Control Terminal")
        
        # Real-time Broadcast Messages received from Superintendents
        st.subheader("📥 Direct Messages from Superintendents")
        if not st.session_state.supt_to_sup_messages:
            st.info("No directive notifications logged from upper management command room.")
        else:
            for msg in reversed(st.session_state.supt_to_sup_messages):
                st.chat_message("user", avatar="📊").write(f"⚙️ **{msg['sender']}** ({msg['time']}): {msg['text']}")

        st.markdown("---")
        
        t1, t2, t3, t4 = st.tabs(["⚡ Shift Control Matrix", "🔍 QA Sign-Off Deck", "➕ Create New Task", "📣 Message Workers"])
        
        with t1:
            st.markdown("### Master Drag and Drop/Edit Tracker")
            updated_grid = st.data_editor(
                st.session_state.tasks_db,
                column_config={
                    "id": st.column_config.NumberColumn("ID", disabled=True),
                    "assigned_to": st.column_config.SelectboxColumn("Assigned Tech", options=crew_list)
                },
                hide_index=True, use_container_width=True
            )
            st.session_state.tasks_db = updated_grid
            
        with t2:
            pending_items = tasks_df[tasks_df['status'] == "Pending QA"]
            if pending_items.empty:
                st.info("No field validation records are currently awaiting verification.")
            else:
                for idx, row in pending_items.iterrows():
                    st.markdown(f"**Task #{row['id']}: {row['title']}** ({row['assigned_to']})")
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("✅ Verify & Close", key=f"sup_app_{row['id']}"):
                            st.session_state.tasks_db.at[idx, 'status'] = "Complete"
                            st.rerun()
                    with b2:
                        if st.button("❌ Return to Shift", key=f"sup_rej_{row['id']}"):
                            st.session_state.tasks_db.at[idx, 'status'] = "In Progress"
                            st.rerun()
        with t3:
            new_title = st.text_input("Task Summary")
