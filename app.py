import streamlit as st
import pandas as pd
from datetime import datetime

# 1. LIVE WEB LAYOUT CONFIGURATION
st.set_page_config(page_title="Mine Task Tracker", layout="wide")

# 2. INTERNAL PERSISTENT BACKUP MEMORY
if 'tasks_db' not in st.session_state:
    st.session_state.tasks_db = pd.DataFrame([
        {"id": 101, "title": "Replace 45kW Pump Motor Starter", "location": "Workshop Bench 2", "status": "In Progress", "priority": "High", "assigned_to": "John Doe", "loto_verified": False, "jsa_completed": False, "updated_at": "2026-07-23 04:30"},
        {"id": 102, "title": "Calibrate Underground Gas Detectors", "location": "Level 4 North Shaft", "status": "Unassigned", "priority": "Critical", "assigned_to": "Unassigned", "loto_verified": False, "jsa_completed": False, "updated_at": "2026-07-23 01:15"},
        {"id": 103, "title": "Rewire Overhead Crane Control Box", "location": "Main Workshop Bay 1", "status": "Pending QA", "priority": "Medium", "assigned_to": "Alex Smith", "loto_verified": True, "jsa_completed": True, "updated_at": "2026-07-23 05:00"}
    ])

crew_list = ["Unassigned", "John Doe", "Alex Smith", "Sarah Connor"]

# 3. IDENTITY AND SECURITY DATA TIER
USER_CREDENTIALS = {
    "worker1": {"password": "crew123", "name": "John Doe", "role": "Worker"},
    "supervisor1": {"password": "super789", "name": "Sarah Connor", "role": "Supervisor"},
    "superintendent1": {"password": "boss000", "name": "Mike Tyson", "role": "Superintendent"}
}

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_payload' not in st.session_state:
    st.session_state.user_payload = None

# SCREEN 1: THE PORTAL LOGIN GATE
if not st.session_state.authenticated:
    st.title("🔒 Industrial Portal Secure Login")
    username_input = st.text_input("Corporate Username").strip().lower()
    password_input = st.text_input("Security Password", type="password")
    
    if st.button("Authenticate Access Profile"):
        if username_input in USER_CREDENTIALS and USER_CREDENTIALS[username_input]["password"] == password_input:
            st.session_state.authenticated = True
            st.session_state.user_payload = USER_CREDENTIALS[username_input]
            st.rerun()
        else:
            st.error("Invalid Username or Security Password.")
            
    with st.expander("🔑 Click to see Demo Passwords"):
        st.write("User: worker1 | Pass: crew123")
        st.write("User: supervisor1 | Pass: super789")
        st.write("User: superintendent1 | Pass: boss000")

# SCREEN 2: THE SECURED OPERATIONAL HUB
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

    # INTERFACE TIER A: FIELD WORKERS
    if user['role'] == "Worker":
        st.title(" Worker Workspace")
        my_tasks = tasks_df[tasks_df['assigned_to'] == user['name']]
        
        if my_tasks.empty:
            st.success("No active assignments under your credentials.")
        else:
            for idx, row in my_tasks.iterrows():
                with st.container(border=True):
                    st.markdown(f"#### Task #{row['id']}: {row['title']}")
                    st.write(f"📍 Sector: {row['location']} | Status: `{row['status']}`")
                    
                    loto = st.checkbox("Lockout / Tagout (LOTO) Isolated", value=row['loto_verified'], key=f"wk_loto_{row['id']}")
                    jsa = st.checkbox("Job Safety Analysis (JSA) Signed", value=row['jsa_completed'], key=f"wk_jsa_{row['id']}")
                    
                    st.session_state.tasks_db.at[idx, 'loto_verified'] = loto
                    st.session_state.tasks_db.at[idx, 'jsa_completed'] = jsa
                    
                    if not loto or not jsa:
                        st.error("🔒 Safety Interlocks Active. Fulfill items to update status.")
                    else:
                        action_status = st.selectbox("Update Status:", ["In Progress", "Pending QA", "Blocked"], key=f"wk_stat_{row['id']}")
                        if action_status != row['status']:
                            st.session_state.tasks_db.at[idx, 'status'] = action_status
                            st.rerun()

    # INTERFACE TIER B: SUPERVISORS
    elif user['role'] == "Supervisor":
        st.title("📋 Supervisor Control Terminal")
        t1, t2, t3 = st.tabs(["⚡ Operations Matrix", "🔍 Verification Deck", "➕ Deploy Work Order"])
        
        with t1:
            st.dataframe(tasks_df, hide_index=True, use_container_width=True)
            
        with t2:
            pending_items = tasks_df[tasks_df['status'] == "Pending QA"]
            if pending_items.empty:
                st.info("No field completion validations are currently awaiting verification.")
            else:
                for idx, row in pending_items.iterrows():
                    st.markdown(f"**Task #{row['id']}: {row['title']}** ({row['assigned_to']})")
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("✅ Verify & Archive", key=f"sup_app_{row['id']}"):
                            st.session_state.tasks_db.at[idx, 'status'] = "Complete"
                            st.rerun()
                    with b2:
                        if st.button("❌ Reject Back to Shift", key=f"sup_rej_{row['id']}"):
                            st.session_state.tasks_db.at[idx, 'status'] = "In Progress"
                            st.rerun()
        with t3:
            new_title = st.text_input("Task Summary")
            new_loc = st.text_input("Target Location Location")
            new_pri = st.selectbox("Urgency Grade", ["Low", "Medium", "High", "Critical"])
            new_tech = st.selectbox("Assign Tech", ["Unassigned", "John Doe", "Alex Smith"])
            
            if st.button("Publish Work Ticket"):
                if new_title and new_loc:
                    new_id = int(st.session_state.tasks_db["id"].max() + 1)
                    new_row = {"id": new_id, "title": new_title, "location": new_loc, "priority": new_pri, "assigned_to": new_tech, "status": "In Progress" if new_tech != "Unassigned" else "Unassigned", "loto_verified": False, "jsa_completed": False, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
                    st.session_state.tasks_db = pd.concat([st.session_state.tasks_db, pd.DataFrame([new_row])], ignore_index=True)
                    st.success("Dispatched to database ledger successfully!")
                    st.rerun()

    # INTERFACE TIER C: SUPERINTENDENTS
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
