import streamlit as st

# 1. CORE APPLICATION SURFACE INITIALIZATION
st.title("⚙️ Mine & Electrical Workshop Digital Tracker")

# 2. FIXED SYSTEM MEMORY MEMORY REGISTRY 
if "user_registry" not in st.session_state:
    st.session_state.user_registry = {
        "supervisor1": {"password": "super789", "name": "Elvis Amevor", "role": "Supervisor"},
        "superintendent1": {"password": "boss000", "name": "Anaba Moses", "role": "Superintendent"}
    }

if 'tasks_memory' not in st.session_state:
    st.session_state.tasks_memory = [
        {"id": 101, "title": "Replace 45kW Pump Motor Starter", "location": "Workshop Bench 2", "status": "In Progress", "priority": "High", "assigned_to": "John Doe", "loto": False, "jsa": False},
        {"id": 102, "title": "Calibrate Underground Gas Detectors", "location": "Level 4 North Shaft", "status": "Unassigned", "priority": "Critical", "assigned_to": "Unassigned", "loto": False, "jsa": False},
        {"id": 103, "title": "Inspect Overhead Workshop Crane Cables", "location": "Workshop Bench 1", "status": "Complete", "priority": "High", "assigned_to": "Sarah Connor", "loto": True, "jsa": True},
        {"id": 104, "title": "Re-wire Level 3 Sump Pump Float", "location": "Level 3 South Sump", "status": "Blocked", "priority": "Medium", "assigned_to": "Unassigned", "loto": True, "jsa": False}
    ]

if 'broadcast_messages' not in st.session_state:
    st.session_state.broadcast_messages = []

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_payload' not in st.session_state:
    st.session_state.user_payload = None

# -------------------------------------------------------------
# GATEWAY SCREEN 1: THE ACCREDITED ACCESS GATEWAY
# -------------------------------------------------------------
if not st.session_state.authenticated:
    st.subheader("🔒 Secure Login Gateway")
    user_in = st.text_input("Username").strip().lower()
    pass_in = st.text_input("Password", type="password")
    
    if st.button("Authenticate Profile"):
        if user_in in st.session_state.user_registry and st.session_state.user_registry[user_in]["password"] == pass_in:
            st.session_state.user_payload = st.session_state.user_registry[user_in]
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Invalid credentials entered.")
            
    st.markdown("---")
    st.subheader("🆕 Create Account Profile")
    reg_user = st.text_input("Choose Username").strip().lower()
    reg_name = st.text_input("Full Name")
    reg_role = st.selectbox("Role Access Level", ["Worker", "Supervisor", "Superintendent"])
    reg_pass = st.text_input("Set Password", type="password")
    
    if st.button("Register Profile"):
        if reg_user and reg_name and reg_pass:
            st.session_state.user_registry[reg_user] = {"password": reg_pass, "name": reg_name, "role": reg_role}
            st.success("Registered! Log in above.")
        else:
            st.error("All inputs are mandatory.")
    st.stop()

# -------------------------------------------------------------
# GATEWAY SCREEN 2: ACTIVE CONTROL INTERFACES (ROBUST CASCADE)
# -------------------------------------------------------------
user = st.session_state.user_payload
role_check = str(user['role']).strip().lower()

with st.sidebar:
    st.write(f"Active User: **{user['name']}**")
    st.write(f"Authorization: **{user['role']}**")
    if st.button("🚪 Logout Portal"):
        st.session_state.authenticated = False
        st.session_state.user_payload = None
        st.rerun()

# --- INTERFACE A: WORKER DISPATCH TRACKER ---
if role_check == "worker":
    st.subheader("👷 Field Technician Workspace")
    
    if st.session_state.broadcast_messages:
        st.info("📢 Supervisor Alert Board:")
        for msg in reversed(st.session_state.broadcast_messages):
            st.warning(msg)
            
    for idx, task in enumerate(st.session_state.tasks_memory):
        if task['assigned_to'] == user['name']:
            with st.container(border=True):
                st.markdown(f"### Task #{task['id']}: {task['title']}")
                st.write(f"📍 Location: {task['location']} | Priority: **{task['priority']}**")
                
                l_check = st.checkbox("LOTO Isolated", value=task['loto'], key=f"loto_{task['id']}")
                j_check = st.checkbox("JSA Safety Signed", value=task['jsa'], key=f"jsa_{task['id']}")
                st.session_state.tasks_memory[idx]['loto'] = l_check
                st.session_state.tasks_memory[idx]['jsa'] = j_check
                
                if not l_check or not j_check:
                    st.error("🔒 Safety Isolation Forms Required.")
                else:
                    opt = ["In Progress", "Pending QA", "Blocked"]
                    curr_idx = opt.index(task['status']) if task['status'] in opt else 0
                    new_stat = st.selectbox("Update Status:", opt, index=curr_idx, key=f"stat_{task['id']}")
                    if new_stat != task['status']:
                        st.session_state.tasks_memory[idx]['status'] = new_stat
                        st.rerun()

# --- INTERFACE B: SUPERVISOR TASK HUB ---
elif role_check == "supervisor":
    st.subheader("📋 Supervisor Operations Control Desk")
    
    st.markdown("### Master Operational Schedule Log")
    for idx, task in enumerate(st.session_state.tasks_memory):
        with st.container(border=True):
            st.markdown(f"**Task #{task['id']}: {task['title']}**")
            st.write(f"Sector: {task['location']} | Status: `{task['status']}` | Current Owner: **{task['assigned_to']}**")
            
            # Simple dropdown mechanics that won't freeze a phone browser
            workers_list = ["Unassigned"] + [u["name"] for u in st.session_state.user_registry.values() if u["role"] == "Worker"]
            worker_idx = workers_list.index(task['assigned_to']) if task['assigned_to'] in workers_list else 0
            new_worker = st.selectbox("Reassign Worker:", workers_list, index=worker_idx, key=f"sup_assign_{task['id']}")
            
            if new_worker != task['assigned_to']:
                st.session_state.tasks_memory[idx]['assigned_to'] = new_worker
                st.rerun()
                
            if task['status'] == "Pending QA":
                if st.button("✅ Approve & Close Work Card", key=f"app_{task['id']}"):
                    st.session_state.tasks_memory[idx]['status'] = "Complete"
                    st.rerun()
                    
    st.markdown("---")
    st.markdown("### ➕ Dispatch New Maintenance Work Ticket")
    n_title = st.text_input("Task Title Description")
    n_loc = st.text_input("Mine Sector / Bench Area")
    n_pri = st.selectbox("Urgency Grade", ["Low", "Medium", "High", "Critical"])
    if st.button("Publish Work Ticket"):
        if n_title and n_loc:
            new_id = int(max(t['id'] for t in st.session_state.fallback_tasks) + 1 if st.session_state.tasks_memory else 101)
            st.session_state.tasks_memory.append({"id": new_id, "title": n_title, "location": n_loc, "priority": n_pri, "assigned_to": "Unassigned", "status": "Unassigned", "loto": False, "jsa": False})
            st.success("Ticket Dispatched!")
            st.rerun()

    st.markdown("---")
    st.markdown("### 📣 Broadcast Notice to Team Notice Board")
    msg_input = st.text_area("Type instructions for field technician dashboards...")
    if st.button("Broadcast Message"):
        if msg_input:
            st.session_state.broadcast_messages.append(msg_input)
            st.success("Broadcast broadcasted!")

# --- INTERFACE C: SUPERINTENDENT EXECUTIVE DASHBOARD ---
elif role_check == "superintendent":
    st.subheader("📊 Executive Superintendent Control Room Hub")
    
    # Standard math counts that process safely on mobile devices
    total_cards = len(st.session_state.tasks_memory)
    done_cards = sum(1 for t in st.session_state.tasks_memory if t['status'] == 'Complete')
    progress_cards = sum(1 for t in st.session_state.tasks_memory if t['status'] == 'In Progress')
    blocked_cards = sum(1 for t in st.session_state.tasks_memory if t['status'] == 'Blocked')
    
    st.info(f"Total Shift Operational Logs: **{total_cards}**")
    st.success(f"Safe Closed Tasks Archive: **{done_cards}**")
    st.warning(f"Technicians actively processing in field: **{progress_cards}**")
    st.error(f"🚨 Active Breakdown Delays Blocked: **{blocked_cards}**")
    
    st.markdown("---")
    st.markdown("### Master Facility Shift Record Table")
    for task in st.session_state.tasks_memory:
        st.write(f"🗂️ **Task #{task['id']}**: {task['title']} | Sector: `{task['location']}` | Status: `{task['status']}` | Urgency: `{task['priority']}` | Assigned: `{task['assigned_to']}`")
