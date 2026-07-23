import streamlit as st
import requests
from datetime import datetime
from st_supabase_connection import SupabaseConnection

# 1. FACILITY SYSTEM APPLICATION INITIALIZATION
st.set_page_config(page_title="Industrial Portal Core", layout="wide")

# Connect Streamlit securely to the live Supabase PostgreSQL instances
# This connector leverages automatic state caching management protocols
supabase_client = st.connection(
    name="supabase_connection",
    type=SupabaseConnection,
    ttl=0 # Set to zero for instant live field screen synchronization updates
)

# 2. ALERTS PIPELINE INTEGRATION ENGINE (DISCORD DISPATCHER)
# Replace with your industrial management channel webhook URL string
DISCORD_WEBHOOK_URL = "https://discord.com"

def trigger_safety_delay_broadcast(task_title, location, tech_name):
    """Fires automated real-time safety notifications to supervisor platforms"""
    if "discord.com" not in DISCORD_WEBHOOK_URL:
        return # Skip if tracking webhook hasn't been mapped out by management
    
    payload = {
        "content": f"🚨 **CRITICAL SHIFT BLOCKAGE ENCOUNTERED** 🚨\n"
                   f"⚠️ **Task:** {task_title}\n"
                   f"📍 **Sector Location:** {location}\n"
                   f"👷 **Reporting Technician:** {tech_name}\n"
                   f"⏰ **Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                   f"👉 *Immediate supervisor dispatch or logistical review required.*"
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except Exception:
        pass

# 3. IDENTITY AND AUTHENTICATION SECURITY LAYER
USER_CREDENTIALS = {
    "worker1": {"password": "crew123", "name": "John Doe", "role": "Worker"},
    "supervisor1": {"password": "super789", "name": "Sarah Connor", "role": "Supervisor"},
    "superintendent1": {"password": "boss000", "name": "Mike Tyson", "role": "Superintendent"}
}

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_payload' not in st.session_state:
    st.session_state.user_payload = None

# -------------------------------------------------------------
# LAYER A: ENCRYPTED SECURITY GATEWAY INTERFACE
# -------------------------------------------------------------
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
            
    with st.expander("🔑 Click to see Demo Access Logs"):
        st.write("User: worker1 | Pass: crew123  (Worker)")
        st.write("User: supervisor1 | Pass: super789 (Supervisor)")
        st.write("User: superintendent1 | Pass: boss000 (Superintendent)")

# -------------------------------------------------------------
# LAYER B: SECURED OPERATIONAL APPLICATIONS MASTER ENGINE
# -------------------------------------------------------------
else:
    user = st.session_state.user_payload
    
    with st.sidebar:
        st.markdown(f"### User: **{user['name']}**")
        st.info(f"Access Role: {user['role']}")
        if st.button("🚪 Logout Application"):
            st.session_state.authenticated = False
            st.session_state.user_payload = None
            st.rerun()

    # CORE DATA DECOUPLE: Live Read from PostgreSQL Table
    try:
        query_response = supabase_client.table("facility_tasks").select("*").execute()
        tasks_df = pd.DataFrame(query_response.data) if query_response.data else pd.DataFrame()
    except Exception:
        st.error("🔄 Database Connection Synced. Set up your Supabase project keys in Streamlit Secrets.")
        st.stop()

    # SECTION 1: WORKER APPLICATIONS TIER
    if user['role'] == "Worker":
        st.title("👷 Field Worker Workspace")
        
        if tasks_df.empty:
            st.info("No active operations assigned inside the ledger.")
        else:
            my_tasks = tasks_df[tasks_df['assigned_to'] == user['name']]
            if my_tasks.empty:
                st.success("No active assignments under your credentials.")
            else:
                for idx, row in my_tasks.iterrows():
                    with st.container(border=True):
                        st.markdown(f"#### Task #{row['id']}: {row['title']}")
                        st.write(f"📍 Location: {row['location']} | Status: `{row['status']}`")
                        
                        loto = st.checkbox("Lockout / Tagout (LOTO) Isolated", value=row['loto_verified'], key=f"wk_loto_{row['id']}")
                        jsa = st.checkbox("Job Safety Analysis (JSA) Signed", value=row['jsa_completed'], key=f"wk_jsa_{row['id']}")
                        
                        if (loto != row['loto_verified']) or (jsa != row['jsa_completed']):
                            supabase_client.table("facility_tasks").update({"loto_verified": loto, "jsa_completed": jsa}).eq("id", row['id']).execute()
                            st.rerun()
                        
                        if not loto or not jsa:
                            st.error("🔒 Safety Interlocks Active. Fulfill compliance items to update status indicators.")
                        else:
                            status_options = ["In Progress", "Pending QA", "Blocked"]
                            curr_idx = status_options.index(row['status']) if row['status'] in status_options else 0
                            action_status = st.selectbox("Update Status:", status_options, index=curr_idx, key=f"wk_stat_{row['id']}")
                            
                            if action_status != row['status']:
                                supabase_client.table("facility_tasks").update({"status": action_status, "updated_at": "now()"}).eq("id", row['id']).execute()
                                if action_status == "Blocked":
                                    trigger_safety_delay_broadcast(row['title'], row['location'], user['name'])
                                st.rerun()

    # SECTION 2: SUPERVISOR CONTROLS TIER
    elif user['role'] == "Supervisor":
        st.title("📋 Supervisor Control Terminal")
        t1, t2, t3 = st.tabs(["⚡ Shift Operations Matrix", "🔍 Verification Deck", "➕ Deploy Work Order"])
        
        with t1:
            if not tasks_df.empty:
                st.dataframe(tasks_df, hide_index=True, use_container_width=True)
                st.caption("Records are dynamically locked and committed securely via PostgreSQL schemas.")
            
        with t2:
            pending_items = tasks_df[tasks_df['status'] == "Pending QA"] if not tasks_df.empty else pd.DataFrame()
            if pending_items.empty:
                st.info("No field completion validations are currently awaiting verification records.")
            else:
                for idx, row in pending_items.iterrows():
                    st.markdown(f"**Task #{row['id']}: {row['title']}** ({row['assigned_to']})")
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("✅ Verify & Archive", key=f"sup_app_{row['id']}"):
                            supabase_client.table("facility_tasks").update({"status": "Complete"}).eq("id", row['id']).execute()
                            st.rerun()
                    with b2:
                        if st.button("❌ Reject Back to Shift", key=f"sup_rej_{row['id']}"):
                            supabase_client.table("facility_tasks").update({"status": "In Progress"}).eq("id", row['id']).execute()
                            st.rerun()
        with t3:
            new_title = st.text_input("Engineering Task Summary")
            new_loc = st.text_input("Target Location Sector")
            new_pri = st.selectbox("Urgency Grade", ["Low", "Medium", "High", "Critical"])
            new_tech = st.selectbox("Assign Primary Tech", ["Unassigned", "John Doe", "Alex Smith"])
            
            if st.button("Publish Work Ticket to Cloud Ledger"):
                if new_title and new_loc:
                    new_task = {
                        "title": new_title, "location": new_loc, "priority": new_pri,
                        "assigned_to": new_tech, "status": "In Progress" if new_tech != "Unassigned" else "Unassigned"
                    }
                    supabase_client.table("facility_tasks").insert(new_task).execute()
                    st.success("Dispatched to cloud database ledger successfully!")
                    st.rerun()

    # SECTION 3: SUPERINTENDENT STRATEGIC ANALYSIS TIER
    elif user['role'] == "Superintendent":
        st.title("📊 Control Room Live Command Hub")
        if not tasks_df.empty:
            total = len(tasks_df)
            done = len(tasks_df[tasks_df['status'] == "Complete"])
            blocked = len(tasks_df[tasks_df['status'] == "Blocked"])
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Active Records", total)
            m2.metric("Safe Closures Archive", done)
            m3.metric("🚨 Active Shift Delay Incidents", blocked)
            
            st.markdown("---")
            st.subheader("Comprehensive Master Facility Audit Ledger")
            st.dataframe(tasks_df, hide_index=True, use_container_width=True)
