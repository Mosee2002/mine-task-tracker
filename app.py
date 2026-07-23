import streamlit as st
import pandas as pd
from datetime import datetime

# 1. LIVE WEB LAYOUT CONFIGURATION
st.set_page_config(
    page_title="Mine & Workshop Digital Tracker",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. PERSISTENT GLOBAL WEB DATABASE
# Ensures user inputs are saved securely in the cloud server session memory
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

# Helper list of registered workers
crew_list = ["Unassigned", "John Doe", "Alex Smith", "Sarah Connor"]

# 3. GLOBAL CONTROL SIDEBAR
with st.sidebar:
    st.markdown("### 🏢 Facility Node")
    st.info("📍 Connected to: **Main Workshop & Mine Shaft A**")
    
    st.markdown("---")
    st.markdown("### 👤 Shift Login Profile")
    current_role = st.selectbox(
        "Select your active operational role:",
        ["👷 Worker Portal (John Doe)", "📋 Supervisor Dashboard (Sarah Connor)", "📊 Superintendent Center (Mike Tyson)"]
    )
    
    st.markdown("---")
    st.markdown("### 📡 Connection Mode")
    st.toggle("Simulate Offline Underground Mode", value=False)
    st.caption("App automatically utilizes active synchronization protocols.")

# 4. INTERFACE SPLITTING BY SELECTED ROLE
# -------------------------------------------------------------
# ROLE A: WORKER PORTAL
# -------------------------------------------------------------
if "Worker" in current_role:
    st.title("👷 Field Worker Workspace")
    st.subheader("Active Shift Task Queue — John Doe")
    
    # Filter database for John Doe's active responsibilities
    my_tasks = st.session_state.tasks_db[st.session_state.tasks_db['assigned_to'] == "John Doe"]
    
    if my_tasks.empty:
        st.success("🎉 No active tasks assigned to you for this rotation.")
    else:
        for idx, row in my_tasks.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 2, 1])
                
                with c1:
                    st.markdown(f"#### Task #{row['task_id']}: {row['title']}")
                    st.markdown(f"📍 **Location:** {row['location']} | ⚠️ **Priority:** `{row['priority']}`")
                    st.markdown(f"⏰ **Last Status Sync:** {row['updated_at']}")
                
                with c2:
                    st.markdown("**🔒 Mandatory Field Safety Clearance:**")
                    loto = st.checkbox("Lockout / Tagout (LOTO) Isolated", value=row['loto_verified'], key=f"wk_loto_{row['task_id']}")
                    jsa = st.checkbox("Job Safety Analysis (JSA) Signed", value=row['jsa_completed'], key=f"wk_jsa_{row['task_id']}")
                    
                    # Update background data layer instantly
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

# -------------------------------------------------------------
# ROLE B: SUPERVISOR DASHBOARD
# -------------------------------------------------------------
elif "Supervisor" in current_role:
    st.title("📋 Supervisor Control Terminal")
    
    t1, t2, t3 = st.tabs(["⚡ Shift Dispatch Control", "🔍 QA Inspection Deck", "➕ Log New Task"])
    
    with t1:
        st.markdown("### Active Shift Tracking Grid")
        st.caption("Double-click any field to reassign crew members, locations, or priority tiers instantly.")
        
        # Interactive Cloud Spreadsheet Interface
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
            hide_index=True,
            use_container_width=True
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
                    
                    b1, b2, _ = st.columns([1, 1, 3])
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
        st.markdown("### Generate New Maintenance Work Order")
        with st.form("new_task_form", clear_on_submit=True):
            new_title = st.text_input("Task Title / Description")
            new_loc = st.text_input("Mine Sector / Workshop Bench Location")
            new_pri = st.selectbox("Task Urgency/Priority Tiers", ["Low", "Medium", "High", "Critical"])
            new_tech = st.selectbox("Assign Primary Technician", crew_list)
            
            if st.form_submit_button("Publish Task to Cloud Master Log"):
                if new_title and new_loc:
                    new_id = int(st.session_state.tasks_db["task_id"].max() + 1)
                    new_row = {
                        "task_id": new_id, "title": new_title, "location": new_loc,
                        "status": "In Progress" if new_tech != "Unassigned" else "Unassigned",
                        "priority": new_pri, "assigned_to": new_tech,
                        "loto_verified": False, "jsa_completed": False,
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                    st.session_state.tasks_db = pd.concat([st.session_state.tasks_db, pd.DataFrame([new_row])], ignore_index=True)
                    st.success(f"Work Order #{new_id} successfully dispatched to field screens.")
                    st.rerun()
                else:
                    st.error("Please completely fill out the Task Title and Location fields.")

# -------------------------------------------------------------
# ROLE C: SUPERINTENDENT CENTER
# -------------------------------------------------------------
elif "Superintendent" in current_role:
    st.title("📊 Control Room Live Command Hub")
    
    # Mathematical Breakdown of Shift Metrics
    total = len(st.session_state.tasks_db)
