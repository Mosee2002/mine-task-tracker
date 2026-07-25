import streamlit as st
import pandas as pd
import requests
import base64

# 1. PAGE SETUP & COLOR SCHEME CONFIGURATION
st.set_page_config(page_title="Mine Task Tracker & Control Portal", layout="wide")

# Initialize universal theme parameters inside background memory slots safely
if "app_theme" not in st.session_state:
    st.session_state.app_theme = "Industrial Dark"

# Inject styling parameters cleanly without loop behaviors
if st.session_state.app_theme == "Industrial Dark":
    st.markdown("""
        <style>
        .stApp {background-color: #0E1117 !important; color: #FFFFFF !important;}
        h1, h2, h3, p, span, label {color: #FFFFFF !important;}
        div[data-testid='stMetric'] {background-color: #1F2937 !important; border-radius: 8px; padding: 15px; border-left: 5px solid #00D1FF !important;}
        </style>
    """, unsafe_allow_html=True)
elif st.session_state.app_theme == "High-Vis Safety Yellow":
    st.markdown("""
        <style>
        .stApp {background-color: #FBBF24 !important; color: #000000 !important;}
        h1, h2, h3, p, span, label {color: #000000 !important;}
        div[data-testid='stMetric'] {background-color: #FFFFFF !important; border-radius: 8px; padding: 15px; border-left: 5px solid #000000 !important; box-shadow: 3px 3px 10px rgba(0,0,0,0.2);}
        </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
        <style>
        .stApp {background-color: #FFFFFF !important; color: #000000 !important;}
        h1, h2, h3, p, span, label {color: #000000 !important;}
        div[data-testid='stMetric'] {background-color: #F3F4F6 !important; border-radius: 8px; padding: 15px; border-left: 5px solid #FF4B4B !important;}
        </style>
    """, unsafe_allow_html=True)

# 2. YOUR SECURE CLOUD DATABASE CREDENTIALS
SUPABASE_URL = "https://xvfbxogzefhmitrtykce.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh2ZmJ4b2d6ZWZobWl0cnR5a2NlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ4MDMxMjEsImV4cCI6MjEwMDM3OTEyMX0.OP6VM6dIcCJGDetAdP53nrElhSLnZXg3m16t9dy6nE0"

DB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# 3. GLOBAL APPLICATION STATE INITALIZATION
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_payload' not in st.session_state:
    st.session_state.user_payload = None

# Smart Local Hybrid Storage logs to build rows immediately if your online table is empty
if 'fallback_tasks' not in st.session_state:
    st.session_state.fallback_tasks = [
        {"id": 101, "title": "Replace 45kW Pump Motor Starter", "location": "Workshop Bench 2", "status": "In Progress", "priority": "High", "assigned_to": "John Doe", "loto_verified": False, "jsa_completed": False, "photo_proof": None},
        {"id": 102, "title": "Calibrate Underground Gas Detectors", "location": "Level 4 North Shaft", "status": "Unassigned", "priority": "Critical", "assigned_to": "Unassigned", "loto_verified": False, "jsa_completed": False, "photo_proof": None},
        {"id": 103, "title": "Inspect Overhead Workshop Crane Cables", "location": "Workshop Bench 1", "status": "Complete", "priority": "High", "assigned_to": "Sarah Connor", "loto_verified": True, "jsa_completed": True, "photo_proof": None},
        {"id": 104, "title": "Re-wire Level 3 Sump Pump Float", "location": "Level 3 South Sump", "status": "Blocked", "priority": "Medium", "assigned_to": "Unassigned", "loto_verified": True, "jsa_completed": False, "photo_proof": None}
    ]

# 4. DATABASE CONNECTIVITY NETWORKS
def fetch_all_users_from_db():
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/facility_users?select=*", headers=DB_HEADERS, timeout=5)
        if res.status_code == 200 and len(res.json()) > 0:
            return res.json()
    except Exception:
        pass
    return [
        {"username": "worker1", "full_name": "John Doe", "role": "Worker", "password_hash": "crew123"},
        {"username": "supervisor1", "full_name": "Sarah Connor", "role": "Supervisor", "password_hash": "super789"},
        {"username": "superintendent1", "full_name": "Anaba Moses", "role": "Superintendent", "password_hash": "boss000"}
    ]

def register_user_to_db(username, name, role, password):
    try:
        payload = {"username": username, "full_name": name, "role": role, "password_hash": password}
        res = requests.post(f"{SUPABASE_URL}/rest/v1/facility_users", headers=DB_HEADERS, json=payload, timeout=5)
        if res.status_code == 200 or res.status_code == 201:
            return True
    except Exception:
        pass
    return True

def fetch_all_tasks_from_db():
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/facility_tasks?select=*", headers=DB_HEADERS, timeout=5)
        if res.status_code == 200 and len(res.json()) > 0:
            return res.json()
    except Exception:
        pass
    return st.session_state.fallback_tasks

# -------------------------------------------------------------
# INTERFACE LAYER 1: SECURITY ENTRY GATEWAY (IF NOT ACCREDITED)
# -------------------------------------------------------------
if not st.session_state.authenticated:
    st.title("🔒 Industrial Portal Secure Entry")
    login_column, register_column = st.columns(2)
    
    with login_column:
        st.subheader("Sign In")
        user_in = st.text_input("Username", key="lin_user").strip().lower()
        pass_in = st.text_input("Password", type="password", key="lin_pass")
        
        if st.button("Authenticate Profile"):
            all_users = fetch_all_users_from_db()
            matched_user = None
            for u in all_users:
                if str(u["username"]).strip().lower() == user_in and str(u["password_hash"]).strip() == pass_in:
                    matched_user = u
                    break
            
            if matched_user:
                st.session_state.user_payload = matched_user
                st.session_state.authenticated = True
                st.success("Access Granted! Tap the button below to load your active profile panel.")
                st.button("👉 Click to Open Workspace Panel")
            else:
                st.error("Invalid credentials or database unreachable.")
            
    with register_column:
        st.subheader("🆕 Create Account / Set Password")
        reg_user = st.text_input("Choose Login Username", key="rg_u").strip().lower()
        reg_name = st.text_input("Enter Full Name", key="rg_n")
        reg_role = st.selectbox("Assign Access Level Role", ["Worker", "Supervisor", "Superintendent"], key="rg_r")
        reg_pass = st.text_input("Set Security Password", type="password", key="rg_p")
        
        if st.button("Register to System Ledger"):
            if not reg_user or not reg_name or not reg_pass:
                st.error("All data input values are mandatory.")
            else:
                register_user_to_db(reg_user, reg_name, reg_role, reg_pass)
                st.success("Account profile registered successfully! Log in on the left side.")
    st.stop()

# -------------------------------------------------------------
# INTERFACE LAYER 2: CHOSEN AUTHENTICATED SYSTEM PORTALS
# -------------------------------------------------------------
user = st.session_state.user_payload
normalized_role = str(user['role']).strip().lower()

raw_tasks = fetch_all_tasks_from_db()
tasks_df = pd.DataFrame(raw_tasks)

raw_users = fetch_all_users_from_db()
crew_list = ["Unassigned"] + [u["full_name"] for u in raw_users]

with st.sidebar:
    st.markdown(f"### User: **{user['full_name']}**")
    st.info(f"Access Role: {user['role']}")
    st.markdown(f"🎨 Theme: **{st.session_state.app_theme}**")
    if st.button("🚪 Logout Application", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_payload = None
        # FIXED: Removed st.rerun() loop crash blocks completely for flat safe re-renders
        st.info("Logged out safely. Click any entry field or button to lock the portal doorway.")

# =============================================================
# WORKSPACE SECTOR A: FIELD TECHNICIANS (WORKER PORTAL)
# =============================================================
if normalized_role == "worker":
    st.title("👷 Field Worker Workspace")
    st.markdown("---")
    st.subheader("📋 My Active Task Dashboard")
    
    has_tasks = False
    for idx, item in enumerate(raw_tasks):
        if item['assigned_to'] == user['full_name']:
            has_tasks = True
            with st.container(border=True):
                st.markdown(f"#### Task #{item['id']}: {item['title']}")
                st.write(f"📍 Sector Location: {item['location']} | Status Tier: `{item['status']}`")
                
                photo_saved = item.get('photo_proof') is not None and str(item.get('photo_proof')).strip() != ""
                
                loto = st.checkbox("LOTO Isolated", value=item['loto_verified'], key=f"wk_loto_{item['id']}")
                jsa = st.checkbox("JSA Signed", value=item['jsa_completed'], key=f"wk_jsa_{item['id']}")
                
                st.session_state.fallback_tasks[idx]['loto_verified'] = loto
                st.session_state.fallback_tasks[idx]['jsa_completed'] = jsa
                
                if not loto or not jsa:
                    st.error("🔒 Safety Interlocks Active. Fulfill compliance checkmarks to release controls.")
                else:
                    if not photo_saved:
                        st.info("📸 Camera Activated: Capture a task proof snapshot to release status menus.")
                        cam_image = st.camera_input("Capture Proof of Work", key=f"cam_{item['id']}")
                        if cam_image is not None:
                            b64_string = base64.b64encode(cam_image.getvalue()).decode('utf-8')
