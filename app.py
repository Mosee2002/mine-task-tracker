import streamlit as st
import pandas as pd
from datetime import datetime

# 1. LIVE WEB LAYOUT CONFIGURATION
st.set_page_config(
    page_title="Mine & Workshop Digital Tracker",
    page_icon="⚙️",
    layout="wide"
)

# 2. SECURE PASSWORD REGISTRY (MOCK USER DATABASE)
# In production, these are stored as encrypted hashes in your database
USER_CREDENTIALS = {
    "worker1": {"password": "crew123", "name": "John Doe", "role": "Worker"},
    "worker2": {"password": "crew456", "name": "Alex Smith", "role": "Worker"},
    "supervisor1": {"password": "super789", "name": "Sarah Connor", "role": "Supervisor"},
    "superintendent1": {"password": "boss000", "name": "Mike Tyson", "role": "Superintendent"}
}

# 3. PERSISTENT GLOBAL WEB DATABASE
if 'tasks_db' not in st.session_state:
    st.session_state.tasks_db = pd.DataFrame([
        {
            "task_id": 101, 
            "title": "Replace 45kW Pump Motor Starter", 
            "location": "Workshop Bench 2", 
            "status": "In Progress", 
            "priority": "High", 
            "assigned_to": "John Doe",
            "loto_verified": False,
            "jsa_completed": False,
            "updated_at": "2026-07-23 04:30"
        },
        {
            "task_id": 102, 
            "title": "Calibrate Underground Gas Detectors", 
            "location": "Level 4 North Shaft", 
            "status": "Unassigned", 
            "priority": "Critical", 
            "assigned_to": "Unassigned",
            "loto_verified": False,
            "jsa_completed": False,
            "updated_at": "2026-07-23 01:15"
        },
        {
            "task_id": 103, 
            "title": "Rewire Overhead Crane Control Box", 
            "location": "Main Workshop Bay 1", 
            "status": "Pending QA", 
            "priority": "Medium", 
            "assigned_to": "Alex Smith",
            "loto_verified": True,
            "jsa_completed": True,
            "updated_at": "2026-07-23 05:00"
        }
    ])

crew_list = ["Unassigned", "John Doe", "Alex Smith", "Sarah Connor"]

# 4. INITIALIZE AUTHENTICATION STATE VARIABLES
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_payload' not in st.session_state:
    st.session_state.user_payload = None

# -------------------------------------------------------------
# SCREEN 1: THE LOGIN GATEWAY INTERFACE
# -------------------------------------------------------------
if not st.session_state.authenticated:
    st.title("🔒 Industrial Portal Secure Login")
    st.subheader("Mine & Workshop Digital Task Management System")
    
    with st.form("login_form", clear_on_submit=False):
        username_input = st.text_input("Corporate Username").strip().lower()
        password_input = st.text_input("Security Password", type="password")
        submit_login = st.form_submit_button("Authenticate Access Profile")
        
        if submit_login:
            if username_input in USER_CREDENTIALS and USER_CREDENTIALS[username_input]["password"] == password_input:
                st.session_state.authenticated = True
                st.session_state.user_payload = USER_CREDENTIALS[username_input]
                st.success("Access Granted. Synchronizing credentials...")
                st.rerun()
            else:
                st.error("Invalid Username or Security Password. Access Denied.")
                
    # Helper text for testing purposes during stakeholder demo
    with st.expander("🔑 Demo Testing Credentials (Click to Expand)"):
        st.markdown("""
        *   **Worker Account:** User: `worker1` | Password: `crew123` *(John Doe)*
        *   **Supervisor Account:** User: `supervisor1` | Password: `super789` *(Sarah Connor)*
        *   **Superintendent Account:** User: `superintendent1` | Password: `boss000` *(Mike Tyson)*
        """)

# -------------------------------------------------------------
# SCREEN 2: THE SECURED APPLICATION HUB
# -------------------------------------------------------------
else:
    user = st.session_state.user_payload
    
    # Secure Sidebar Header & Logout Mechanism
    with st.sidebar:
        st.markdown(f"### Welcome back, **{user['name']}**")
        st.info(f"🔰 Cleared Role: **{user['role']}**")
        st.markdown("---")
        if st.button("🚪 Secure Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.user_payload = None
            st.rerun()
            
        st.markdown("---")
        st.caption("📍 Node: Main Workshop & Mine Shaft A")

    # ROLE DISPATCH A: WORKER INTERFACE (🔒 Hard Restricted Access)
    if user['role'] == "Worker":
        st.title(" Worker Workspace")
        st.subheader(f"Active Shift Task Queue — {user['name']}")
        
        my_tasks = st.session_state.tasks_db[st.session_state.tasks_db['assigned_to'] == user['name']]
        
        if my_tasks.empty:
            st.success("🎉 No active tasks assigned to you for this rotation.")
        else:
            for idx, row in my_tasks.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns()
                    with c1:
                        st.markdown(f"#### Task #{row['task_id']}: {row['title']}")
                        st.markdown(f"📍 **Location:** {row['location']} | ⚠️ **Priority:** `{row['priority']}`")
                        st.markdown(f"⏰ **Last Status Sync:** {row['updated_at']}")
                    with c2:
                        st.markdown("**🔒 Mandatory Field Safety Clearance:**")
                        loto = st.checkbox("Lockout / Tagout (LOTO) Isolated", value=row['loto_verified'], key=f"wk_loto_{row['task_id']}")
                        jsa = st.checkbox("Job Safety Analysis (JSA) Signed", value=row['jsa_completed'], key=f"wk_jsa_{row['task_id']}")
                        st.session_state.tasks_db.at[idx, 'loto_verified'] = loto
                        st.session_state.tasks_db.at[idx, 'jsa_completed'] = jsa
                    with c3:
                        st.markdown("**Progress Status:**")
                        if not loto or not jsa:
                            st.error("🔒 Safety Locked")
                        else:
                            status_options = ["In Progress", "Pending QA", "Blocked"]
                            current_idx = status_options.index(row['status']) if row['status'] in status_options else 0
                            action_status = st.selectbox("Update Status:", status_options, index=current_idx, key=f"wk_stat_{row['task_id']}")
                            if action_status != row['status']:
                                st.session_state.tasks_db.at[idx, 'status'] = action_status
                                st.session_state.tasks_db.at[idx, 'updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                                st.rerun()

    # ROLE DISPATCH B: SUPERVISOR INTERFACE (🔒 Hard Restricted Access)
    elif user['role'] == "Supervisor":
        st.title("📋 Supervisor Control Terminal")
        t1, t2, t3 = st.tabs(["⚡ Shift Dispatch Control", "🔍 QA Inspection Deck", "➕ Log New Task"])
        
        with t1:
            st.markdown("### Active Shift Tracking Grid")
            updated_grid = st.data_editor(
                st.session_state.tasks_db,
                column_config={
                    "task_id": st.column_config.NumberColumn("Task ID", disabled=True),
                    "title": st.column_config.TextColumn("Task Title"),
                    "location": st.column_config.TextColumn("Location Work Area"),
                    "status": st.column_config.SelectboxColumn("Status Tier", options=["Unassigned", "In Progress", "Pending QA", "Complete", "Blocked"]),
                    "priority": st.column_config.SelectboxColumn("Priority", options=["Low", "Medium", "High", "Critical"]),
                    "assigned_to": st.column_config.SelectboxColumn("Assigned Tech", options=crew_list),
                    "loto_verified": st.column_config.CheckboxColumn("LOTO Active"),
                    "jsa_completed": st.column_config.CheckboxColumn("JSA Completed"),
                    "updated_at": st.column_config.TextColumn("Last Update Sync", disabled=True)
                },
                hide_index=True, use_container_width=True
            )
            st.session_state.tasks_db = updated_grid
            
        with t2:
            st.markdown("### Engineering Signs & Clearances Awaiting Approval")
            pending_items = st.session_state.tasks_db[st.session_state.tasks_db['status'] == "Pending QA"]
            if pending_items.empty:
                st.info("No field tickets are currently awaiting supervisory review.")
            else:
                for idx, row in pending_items.iterrows():
                    with st.chat_message("user", avatar="⚡"):
                        st.markdown(f"**Task #{row['task_id']}: {row['title']}**")
                        st.write(f"Completed by tech: **{row['assigned_to']}** | Work Location: **{row['location']}**")
                        b1, b2, _ = st.columns()
                        with b1:
                            if st.button("✅ Approve & Archive", key=f"sup_app_{row['task_id']}"):
                                st.session_state.tasks_db.at[idx, 'status'] = "Complete"
                                st.session_state.tasks_db.at[idx, 'updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                                st.rerun()
                        with b2:
                            if st.button("❌ Reject back to Field", key=f"sup_rej_{row['task_id']}"):
                                st.session_state.tasks_db.at[idx, 'status'] = "In Progress"
                                st.session_state.tasks_db.at[idx, 'updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                                st.rerun()
        with t3:
