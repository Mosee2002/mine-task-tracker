import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# 1. LIVE WEB LAYOUT CONFIGURATION
st.set_page_config(page_title="Mine Task Tracker", layout="wide")

# 2. DIRECT CLOUD DATABASE CONNECTOR TERMINAL
# Paste your exact codes inside the quotation marks below
SUPABASE_URL = "https://xvfbxogzefhmitrtykce.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh2ZmJ4b2d6ZWZobWl0cnR5a2NlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ4MDMxMjEsImV4cCI6MjEwMDM3OTEyMX0.OP6VM6dIcCJGDetAdP53nrElhSLnZXg3m16t9dy6nE0..."


# Format communication channels directly using native web request protocols
DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def load_live_database_rows():
    try:
        response = requests.get(f"{SUPABASE_URL}/rest/v1/facility_tasks?select=*", headers=DB_HEADERS, timeout=10)
        return pd.DataFrame(response.json()) if response.status_code == 200 else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

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

# SCREEN 2: THE DATA CONNECTIONS HUB
else:
    user = st.session_state.user_payload
    tasks_df = load_live_database_rows()
    
    with st.sidebar:
        st.markdown(f"### User: **{user['name']}**")
        st.info(f"Role: {user['role']}")
        if st.button("🚪 Logout Application"):
            st.session_state.authenticated = False
            st.session_state.user_payload = None
            st.rerun()

    if tasks_df.empty:
        st.warning("⚠️ No data columns returned. Double-check your URL and Key strings in lines 11 & 12.")
        st.stop()

    # INTERFACE TIER A: FIELD WORKERS
    if user['role'] == "Worker":
        st.title("👷 Field Worker Workspace")
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
                    
                    if (loto != row['loto_verified']) or (jsa != row['jsa_completed']):
                        patch_data = {"loto_verified": loto, "jsa_completed": jsa}
                        requests.patch(f"{SUPABASE_URL}/rest/v1/facility_tasks?id=eq.{row['id']}", headers=DB_HEADERS, json=patch_data)
                        st.rerun()
                    
                    if not loto or not jsa:
                        st.error("🔒 Safety Interlocks Active. Fulfill items to update status.")
                    else:
                        action_status = st.selectbox("Update Status:", ["In Progress", "Pending QA", "Blocked"], key=f"wk_stat_{row['id']}")
                        if action_status != row['status']:
                            requests.patch(f"{SUPABASE_URL}/rest/v1/facility_tasks?id=eq.{row['id']}", headers=DB_HEADERS, json={"status": action_status})
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
                            requests.patch(f"{SUPABASE_URL}/rest/v1/facility_tasks?id=eq.{row['id']}", headers=DB_HEADERS, json={"status": "Complete"})
                            st.rerun()
                    with b2:
                        if st.button("❌ Reject Back to Shift", key=f"sup_rej_{row['id']}"):
                            requests.patch(f"{SUPABASE_URL}/rest/v1/facility_tasks?id=eq.{row['id']}", headers=DB_HEADERS, json={"status": "In Progress"})
                            st.rerun()
        with t3:
            new_title = st.text_input("Task Summary")
            new_loc = st.text_input("Target Location Location")
            new_pri = st.selectbox("Urgency Grade", ["Low", "Medium", "High", "Critical"])
            new_tech = st.selectbox("Assign Tech", ["Unassigned", "John Doe", "Alex Smith"])
            
            if st.button("Publish Work Ticket"):
                if new_title and new_loc:
                    new_task = {"title": new_title, "location": new_loc, "priority": new_pri, "assigned_to": new_tech, "status": "In Progress" if new_tech != "Unassigned" else "Unassigned"}
                    requests.post(f"{SUPABASE_URL}/rest/v1/facility_tasks", headers=DB_HEADERS, json=new_task)
                    st.success("Dispatched to cloud database ledger successfully!")
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
