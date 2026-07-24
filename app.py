import streamlit as st
import pandas as pd
from datetime import datetime

# 1. LIVE WEB LAYOUT CONFIGURATION
st.set_page_config(page_title="Mine Task Tracker", layout="wide")

# 2. STATE INITIALIZATION FOR DYNAMIC USER DB
# This acts as our live cloud registry allowing users to dynamically create profiles
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

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_payload' not in st.session_state:
    st.session_state.user_payload = None

# Build clean dynamic dropdown selection array for supervisor tasking assignments
crew_list = ["Unassigned"] + [info["name"] for info in st.session_state.user_registry.values()]

# -------------------------------------------------------------
# SCREEN 1: ENCRYPTED PORTAL GATEWAY (LOGIN & REGISTER)
# -------------------------------------------------------------
if not st.session_state.authenticated:
    st.title("🔒 Industrial Portal Secure Entry")
    
    # Split the screen into two modules using modern layout columns
    login_column, register_column = st.columns(2)
    
    with login_column:
        st.subheader("Sign In")
        with st.form("login_form"):
            user_in = st.text_input("Username").strip().lower()
            pass_in = st.text_input("Password", type="password")
            if st.form_submit_button("Authenticate Access Profile"):
                if user_in in st.session_state.user_registry and st.session_state.user_registry[user_in]["password"] == pass_in:
                    st.session_state.authenticated = True
                    st.session_state.user_payload = st.session_state.user_registry[user_in]
                    st.rerun()
                else:
                    st.error("Invalid credentials entered.")
                    
    with register_column:
        st.subheader("🆕 Create Account / Set Password")
        st.caption("New workers, supervisors, or management can register credentials below.")
        with st.form("registration_form"):
            reg_user = st.text_input("Choose Username (e.g. kwame1)").strip().lower()
            reg_name = st.text_input("Full Name (e.g. Kwame Mensah)")
            reg_role = st.selectbox("Operational Access Role", ["Worker", "Supervisor", "Superintendent"])
            reg_pass = st.text_input("Set Custom Password", type="password")
            
            if st.form_submit_button("Register to System Ledger"):
                if not reg_user or not reg_name or not reg_pass:
                    st.error("All registration form data elements are mandatory.")
                elif reg_user in st.session_state.user_registry:
                    st.error("Username already claimed by another crew member.")
                else:
                    # Inject the newly input user profile information into state registers
                    st.session_state.user_registry[reg_user] = {
                        "password": reg_pass,
                        "name": reg_name,
                        "role": reg_role
                    }
                    st.success(f"Profile saved! You can now sign in using username: `{reg_user}`")

# -------------------------------------------------------------
# SCREEN 2: THE SECURED OPERATIONAL HUB
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

    # SECTION A: FIELD WORKERS
    if user['role'] == "Worker":
        st.title("👷 Field Worker Workspace")
        my_tasks = tasks_df[tasks_df['assigned_to'] == user['name']]
        
        if my_tasks.empty:
            st.success("No active assignments under your credentials. Ask your area supervisor to assign a task card to your profile name.")
        else:
            for idx, row in my_tasks.iterrows():
                with st.container(border=True):
                    st.markdown(f"#### Task #{row['id']}: {row['title']}")
                    st.write(f"📍 Sector Location: {row['location']} | Status: `{row['status']}`")
                    
                    loto = st.checkbox("Lockout / Tagout (LOTO) Isolated", value=row['loto_verified'], key=f"wk_loto_{row['id']}")
                    jsa = st.checkbox("Job Safety Analysis (JSA) Signed", value=row['jsa_completed'], key=f"wk_jsa_{row['id']}")
                    st.session_state.tasks_db.at[idx, 'loto_verified'] = loto
                    st.session_state.tasks_db.at[idx, 'jsa_completed'] = jsa
                    
                    if not loto or not jsa:
                        st.error("🔒 Safety Interlocks Active. Fulfill compliance checkmarks to update progress indicators.")
                    else:
                        action_status = st.selectbox("Update Status:", ["In Progress", "Pending QA", "Blocked"], key=f"wk_stat_{row['id']}")
                        if action_status != row['status']:
                            st.session_state.tasks_db.at[idx, 'status'] = action_status
                            st.rerun()

    # SECTION B: AREA SUPERVISORS
    elif user['role'] == "Supervisor":
        st.title("📋 Supervisor Control Terminal")
        t1, t2, t3 = st.tabs(["⚡ Shift Control", "🔍 QA Sign-Off Deck", "➕ Deploy Work Order"])
        
        with t1:
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
            new_title = st.text_input("Task Summary Summary")
            new_loc = st.text_input("Target Location Sector")
            new_pri = st.selectbox("Urgency Grade", ["Low", "Medium", "High", "Critical"])
            new_tech = st.selectbox("Assign Primary Tech Profile", crew_list)
            
            if st.button("Publish Work Ticket"):
                if new_title and new_loc:
                    new_id = int(st.session_state.tasks_db["id"].max() + 1)
                    new_row = {"id": new_id, "title": new_title, "location": new_loc, "priority": new_pri, "assigned_to": new_tech, "status": "In Progress" if new_tech != "Unassigned" else "Unassigned", "loto_verified": False, "jsa_completed": False, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
                    st.session_state.tasks_db = pd.concat([st.session_state.tasks_db, pd.DataFrame([new_row])], ignore_index=True)
                    st.success("Dispatched to database ledger successfully!")
                    st.rerun()

    # SECTION C: SUPERINTENDENTS
    elif user['role'] == "Superintendent":
        st.title("📊 Control Room Live Command Hub")
        total = len(tasks_df)
        done = len(tasks_df[tasks_df['status'] == "Complete"])
        blocked = len(tasks_df[tasks_df['status'] == "Blocked"])
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Active Records", total)
        m2.metric("Safe Closures Archive", done)
        m3.metric("🚨 Active Shift Delays", blocked)
        
        st.markdown("---")
        st.dataframe(tasks_df, hide_index=True, use_container_width=True)
