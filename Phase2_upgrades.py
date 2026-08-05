# ============================================================================
# PHASE 2 UPGRADE MODULE - MINE & WORKSHOP DIGITAL TRACKER
# ============================================================================
# Copy this entire file into your project root as phase2_upgrades.py
# Then follow the integration instructions at the bottom of this file.

import streamlit as st
import streamlit.components.v1 as components
import requests
from datetime import datetime, timedelta
import hashlib
import base64
import os
import json
import time
import html as html_lib
import re
import secrets
from io import BytesIO

# Import shared functions from the main app (assumed to be available)
# We'll define our own versions of needed helpers if not already global.
try:
    from app import esc, log_error, log_audit, send_notification, adjust_part_quantity, fetch_photos, validate_image, validate_attachment, fetch_all_parts, fetch_contractors, fetch_all_assets, fetch_all_tasks, fetch_meter_readings, task_parts_cost
except ImportError:
    # Fallback definitions (these should already exist in the main app)
    def esc(text):
        if text is None:
            return ""
        return html_lib.escape(str(text), quote=True)
    def log_error(error_message, details=None, user_name=None, endpoint=None):
        pass
    def log_audit(user_name, action, details=None):
        pass
    def send_notification(user_name, title, body):
        pass
    def adjust_part_quantity(part_id, delta, adjusted_by, reason):
        pass
    def validate_image(file_bytes, filename):
        return True, "ok"
    def validate_attachment(file_bytes, filename):
        return True, "ok"
    def fetch_all_parts():
        return []
    def fetch_contractors():
        return []
    def fetch_all_assets():
        return []
    def fetch_all_tasks():
        return []
    def fetch_meter_readings(asset_id, limit=200):
        return []
    def task_parts_cost(task_id, parts_lookup):
        return 0.0

# Try to import pandas and plotly (optional)
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# We need the supabase client from the main app.
# We'll use st.session_state to store it, or we can import supabase from the main app.
# Since this module is imported, we can access global supabase if defined.
# We'll create a function to get supabase from st.session_state.
def get_supabase():
    if "supabase" in st.session_state:
        return st.session_state.supabase
    # fallback: try to import from app
    try:
        from app import supabase
        st.session_state.supabase = supabase
        return supabase
    except ImportError:
        return None

# ---------- BOM ----------
def get_bom_for_task(task_id):
    supabase = get_supabase()
    if not supabase:
        return []
    try:
        res = supabase.table("boms").select("*, inventory_parts(*)").eq("task_template_id", task_id).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="get_bom")
        return []

# ---------- Purchase Orders ----------
def create_purchase_order(supplier_id, line_items, created_by):
    supabase = get_supabase()
    if not supabase:
        return None
    try:
        po_number = f"PO-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
        total = sum(i['quantity'] * i['unit_price'] for i in line_items)
        po_res = supabase.table("purchase_orders").insert({
            "po_number": po_number, "supplier_id": supplier_id,
            "total_cost": total, "created_by": created_by
        }).execute()
        if not po_res.data:
            return None
        po_id = po_res.data[0]['id']
        for item in line_items:
            supabase.table("po_line_items").insert({
                "po_id": po_id, "part_id": item['part_id'],
                "quantity_ordered": item['quantity'], "unit_price": item['unit_price'],
                "total_price": item['quantity'] * item['unit_price']
            }).execute()
        log_audit(created_by, "purchase_order_created", {"po_id": po_id, "total": total})
        return po_res.data[0]
    except Exception as e:
        log_error(str(e), endpoint="create_purchase_order")
        return None

def receive_purchase_order(po_id, received_items, received_by):
    supabase = get_supabase()
    if not supabase:
        return False
    try:
        for item in received_items:
            # Update PO line item
            supabase.table("po_line_items").update({
                "quantity_received": item['quantity_received']
            }).eq("po_id", po_id).eq("part_id", item['part_id']).execute()
            # Increase inventory
            adjust_part_quantity(item['part_id'], item['quantity_received'], received_by, reason=f"PO #{po_id} received")
        supabase.table("purchase_orders").update({
            "status": "Received", "received_at": datetime.now().isoformat()
        }).eq("id", po_id).execute()
        log_audit(received_by, "purchase_order_received", {"po_id": po_id})
        return True
    except Exception as e:
        log_error(str(e), endpoint="receive_purchase_order")
        return False

def get_purchase_orders(status=None):
    supabase = get_supabase()
    if not supabase:
        return []
    try:
        q = supabase.table("purchase_orders").select("*")
        if status:
            q = q.eq("status", status)
        res = q.order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="get_purchase_orders")
        return []

def get_po_line_items(po_id):
    supabase = get_supabase()
    if not supabase:
        return []
    try:
        res = supabase.table("po_line_items").select("*, inventory_parts(*)").eq("po_id", po_id).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="get_po_line_items")
        return []

# ---------- Shift Rostering ----------
def get_workers_on_shift(shift_time=None):
    if shift_time is None:
        shift_time = datetime.now()
    supabase = get_supabase()
    if not supabase:
        return []
    try:
        res = supabase.table("shift_rosters").select("*")\
            .lt("shift_start", shift_time.isoformat())\
            .gt("shift_end", shift_time.isoformat()).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="get_workers_on_shift")
        return []

def assign_shift(username, shift_start, shift_end, crew_name, assigned_by):
    supabase = get_supabase()
    if not supabase:
        return False
    try:
        res = supabase.table("shift_rosters").insert({
            "username": username,
            "shift_start": shift_start.isoformat(),
            "shift_end": shift_end.isoformat(),
            "crew_name": crew_name,
            "assigned_by": assigned_by
        }).execute()
        if res.data:
            log_audit(assigned_by, "shift_assigned", {"username": username})
            return True
        return False
    except Exception as e:
        log_error(str(e), endpoint="assign_shift")
        return False

# ---------- Automation Escalations ----------
def run_escalations():
    supabase = get_supabase()
    if not supabase:
        return
    try:
        # Overdue tasks that are still "In Progress" -> escalate to supervisor
        now = datetime.now().isoformat()
        # 1. Find tasks overdue and not complete, not blocked
        overdue = supabase.table("tasks").select("*")\
            .lt("due_date", now).neq("status", "Complete").neq("status", "Blocked").execute()
        for task in overdue.data:
            # Notify supervisor
            send_notification("superintendent1", "Task Overdue Escalation", 
                              f"Task #{task['id']} - {task['title']} is overdue.")
            # Optionally, add a system comment
            # We could also set status to Blocked if overdue > 7 days, but let's just notify.
            # Let's also increase priority if critical.
        # 2. Check for permits expiring in next hour
        now_dt = datetime.now()
        one_hour = now_dt + timedelta(hours=1)
        permits = supabase.table("permits").select("*").eq("status", "Active").execute()
        for p in permits.data:
            valid_until = p.get('valid_until')
            if valid_until:
                try:
                    expiry = datetime.fromisoformat(valid_until)
                    if now_dt < expiry < one_hour:
                        send_notification(p.get('issued_by'), "Permit Expiring Soon",
                                          f"Permit #{p['id']} expires at {expiry.strftime('%H:%M')}.")
                except:
                    pass
        log_audit("system", "escalations_run", {"timestamp": now})
    except Exception as e:
        log_error(str(e), endpoint="run_escalations")

# ---------- Document Management ----------
def upload_document(file_bytes, filename, title, description, asset_id, uploaded_by):
    supabase = get_supabase()
    if not supabase:
        return False
    valid, msg = validate_attachment(file_bytes, filename)
    if not valid:
        st.error(msg)
        return False
    try:
        ext = filename.split('.')[-1].lower()
        safe_name = f"sops/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(file_bytes).hexdigest()[:8]}.{ext}"
        res = supabase.storage.from_("documents").upload(safe_name, file_bytes)
        if not res:
            return False
        url = supabase.storage.from_("documents").get_public_url(safe_name)
        # Check if document with same title and asset exists to bump version
        existing = supabase.table("documents").select("version").eq("title", title).eq("asset_id", asset_id).execute()
        version = 1
        if existing.data:
            version = existing.data[0].get("version", 0) + 1
        supabase.table("documents").insert({
            "title": title, "description": description, "file_url": url,
            "file_type": ext, "asset_id": asset_id, "uploaded_by": uploaded_by,
            "version": version
        }).execute()
        log_audit(uploaded_by, "document_upload", {"title": title})
        return True
    except Exception as e:
        log_error(str(e), endpoint="upload_document")
        return False

def search_documents(query):
    supabase = get_supabase()
    if not supabase:
        return []
    try:
        res = supabase.table("documents").select("*")\
            .or_(f"title.ilike.%{query}%,description.ilike.%{query}%").execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="search_documents")
        return []

# ---------- Budget Tracking ----------
def get_budget_status(asset_id=None, department=None):
    supabase = get_supabase()
    if not supabase:
        return []
    try:
        q = supabase.table("budgets").select("*")
        if asset_id:
            q = q.eq("asset_id", asset_id)
        if department:
            q = q.eq("department", department)
        res = q.execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="get_budget_status")
        return []

def update_budget_spent(task_id):
    supabase = get_supabase()
    if not supabase:
        return
    # Get task details
    task_res = supabase.table("tasks").select("asset_id, labour_hours, labour_rate, id").eq("id", task_id).execute()
    if not task_res.data:
        return
    task = task_res.data[0]
    asset_id = task.get("asset_id")
    if not asset_id:
        return
    # Compute costs
    parts_cost = task_parts_cost(task_id, {})  # We'll need parts lookup; we'll use the function from app
    labour_cost = task.get("labour_hours", 0) * task.get("labour_rate", 0)
    total = parts_cost + labour_cost
    try:
        # Use a database function if available, else manual update
        # Attempt to call an RPC if defined
        # We'll just do manual update
        current = supabase.table("budgets").select("spent_to_date").eq("asset_id", asset_id).execute()
        if current.data:
            new_spent = current.data[0].get("spent_to_date", 0) + total
            supabase.table("budgets").update({"spent_to_date": new_spent}).eq("asset_id", asset_id).execute()
            log_audit("system", "budget_updated", {"asset_id": asset_id, "added": total})
    except Exception as e:
        log_error(str(e), endpoint="update_budget_spent")

# ---------- Anomaly Detection ----------
def detect_meter_anomaly(asset_id):
    readings = fetch_meter_readings(asset_id, limit=50)  # from main app
    if len(readings) < 10:
        return False
    try:
        vals = [float(r['reading']) for r in readings]
        mean = sum(vals) / len(vals)
        std = (sum((x - mean) ** 2 for x in vals) / len(vals)) ** 0.5
        latest = vals[-1]
        if std > 0 and abs(latest - mean) > 2 * std:
            return True
    except Exception:
        pass
    return False

# ---------- UI Rendering for Advanced Tab ----------
def render_advanced_tab():
    st.subheader("🚀 Advanced Operations Suite")
    st.caption("Phase 2: BOM, Purchase Orders, Rostering, Escalations, Document Library, Budgets, Anomaly Detection")
    
    tabs = option_menu(
        menu_title=None,
        options=["Procurement & BOM", "Shift Rostering", "Document Library", "Budget Center", "Automation"],
        icons=["cart-plus", "calendar-week", "folder-open", "coins", "robot"],
        orientation="horizontal",
        default_index=0,
        styles=menu_styles()
    )
    
    if tabs == "Procurement & BOM":
        render_procurement()
    elif tabs == "Shift Rostering":
        render_rostering()
    elif tabs == "Document Library":
        render_document_library()
    elif tabs == "Budget Center":
        render_budget_center()
    elif tabs == "Automation":
        render_automation()

def menu_styles():
    # Reuse the app's existing style, or define a minimal one
    return {
        "container": {"padding": "5px", "background-color": "#f0f2f6", "border-radius": "10px", "margin-bottom": "1rem"},
        "icon": {"color": "#1d4ed8", "font-size": "16px"},
        "nav-link": {"font-size": "14px", "font-weight": "600", "margin": "2px", "padding": "0.5rem 1rem", "border-radius": "8px"},
        "nav-link-selected": {"background-color": "#1d4ed8", "color": "white"},
    }

def render_procurement():
    st.markdown("### 📦 Procurement & BOM")
    tab1, tab2 = st.tabs(["Bill of Materials (BOM)", "Purchase Orders"])
    
    with tab1:
        st.markdown("#### Link Parts to a Preventive Maintenance Task")
        tasks = fetch_all_tasks()
        pm_tasks = [t for t in tasks if t.get('is_recurring')]
        if not pm_tasks:
            st.info("No recurring (PM) tasks found. Create a recurring task first.")
        else:
            selected_task = st.selectbox("Select PM Task", [f"#{t['id']} {t['title']}" for t in pm_tasks])
            task_id = int(selected_task.split()[0].replace("#", ""))
            existing_bom = get_bom_for_task(task_id)
            if existing_bom:
                st.write("Current BOM:")
                for item in existing_bom:
                    st.write(f"- {item['inventory_parts']['part_name']}: {item['quantity_required']} units")
            else:
                st.info("No parts linked yet.")
            with st.form("add_bom_item"):
                parts = fetch_all_parts()
                part_options = {p['part_name']: p['id'] for p in parts}
                selected_part = st.selectbox("Add part", list(part_options.keys()))
                qty = st.number_input("Quantity required", min_value=0.1, value=1.0, step=0.5)
                if st.form_submit_button("Add to BOM"):
                    supabase = get_supabase()
                    if supabase:
                        try:
                            supabase.table("boms").insert({
                                "task_template_id": task_id,
                                "part_id": part_options[selected_part],
                                "quantity_required": qty
                            }).execute()
                            st.success("Added.")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
    
    with tab2:
        st.markdown("#### Purchase Orders")
        # List existing POs
        pos = get_purchase_orders()
        if pos:
            for po in pos:
                with st.expander(f"PO #{po['po_number']} - {po['status']} - {po['created_at'][:10]}"):
                    lines = get_po_line_items(po['id'])
                    df = pd.DataFrame(lines) if PANDAS_AVAILABLE else lines
                    st.dataframe(df)
                    if po['status'] == 'Sent':
                        if st.button(f"📦 Receive PO #{po['id']}", key=f"recv_{po['id']}"):
                            # For simplicity, receive all items fully
                            receive_items = [{"part_id": l['part_id'], "quantity_received": l['quantity_ordered']} for l in lines]
                            if receive_purchase_order(po['id'], receive_items, st.session_state.user_payload.get('name')):
                                st.success("PO received and inventory updated.")
                                st.rerun()
                            else:
                                st.error("Failed to receive PO.")
        else:
            st.info("No purchase orders.")
        
        with st.form("create_po"):
            st.markdown("#### Create New Purchase Order")
            contractors = fetch_contractors()
            supplier_choices = {c['company_name']: c['id'] for c in contractors}
            if not supplier_choices:
                st.warning("No suppliers registered. Add a contractor first.")
            else:
                supplier = st.selectbox("Supplier", list(supplier_choices.keys()))
                parts = fetch_all_parts()
                part_choices = {f"{p['part_name']} (Stock: {p['quantity_on_hand']})": p['id'] for p in parts}
                # We'll allow adding multiple line items
                # Simpler: let user enter a part and quantity, then add to session state list
                if "po_line_items" not in st.session_state:
                    st.session_state.po_line_items = []
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    sel_part = st.selectbox("Part", list(part_choices.keys()), key="po_part")
                with col2:
                    qty = st.number_input("Qty", min_value=1, value=1, key="po_qty")
                with col3:
                    price = st.number_input("Unit price", min_value=0.0, value=0.0, step=0.01, key="po_price")
                if st.button("➕ Add line item"):
                    st.session_state.po_line_items.append({
                        "part_id": part_choices[sel_part],
                        "quantity": qty,
                        "unit_price": price
                    })
                    st.success("Added.")
                    st.rerun()
                if st.session_state.po_line_items:
                    st.write("Current line items:")
                    for idx, item in enumerate(st.session_state.po_line_items):
                        st.write(f"- Part ID {item['part_id']}, Qty {item['quantity']}, Price {item['unit_price']}")
                        if st.button(f"Remove {idx}", key=f"remove_{idx}"):
                            del st.session_state.po_line_items[idx]
                            st.rerun()
                    total_cost = sum(item['quantity'] * item['unit_price'] for item in st.session_state.po_line_items)
                    st.write(f"**Total: {total_cost:.2f}**")
                    if st.form_submit_button("💾 Create PO"):
                        if st.session_state.po_line_items:
                            po = create_purchase_order(supplier_choices[supplier], st.session_state.po_line_items, st.session_state.user_payload.get('name'))
                            if po:
                                st.success(f"PO {po['po_number']} created.")
                                st.session_state.po_line_items = []
                                st.rerun()
                            else:
                                st.error("Failed to create PO.")

def render_rostering():
    st.markdown("### 🗓️ Shift Rostering")
    all_workers = fetch_all_users_from_db()
    worker_names = [u['full_name'] for u in all_workers if u.get('role','').lower() == 'worker' and u.get('is_approved')]
    if not worker_names:
        st.info("No workers found.")
    else:
        with st.form("shift_form"):
            worker = st.selectbox("Worker", worker_names)
            start = st.datetime_input("Shift Start", datetime.now())
            end = st.datetime_input("Shift End", datetime.now() + timedelta(hours=8))
            crew = st.text_input("Crew Name (optional)")
            if st.form_submit_button("Assign Shift"):
                if assign_shift(worker, start, end, crew, st.session_state.user_payload.get('name')):
                    st.success("Shift assigned.")
                    st.rerun()
                else:
                    st.error("Failed to assign shift.")
    st.markdown("#### Current Shift Workers")
    on_shift = get_workers_on_shift()
    if on_shift:
        for s in on_shift:
            st.write(f"- {s['username']} ({s['shift_start'][:16]} - {s['shift_end'][:16]}) - {s.get('crew_name','')}")
    else:
        st.info("No one currently on shift.")

def render_document_library():
    st.markdown("### 📁 Document Library (SOPs, Drawings)")
    st.caption("Upload and search maintenance documents. Documents can be linked to assets.")
    search_term = st.text_input("Search documents by title or description")
    if search_term:
        docs = search_documents(search_term)
        if docs:
            for d in docs:
                st.markdown(f"[{d['title']}]({d['file_url']}) - v{d.get('version',1)} - Asset {d.get('asset_id','N/A')}")
        else:
            st.info("No documents found.")
    with st.expander("Upload new document"):
        with st.form("doc_upload"):
            title = st.text_input("Title")
            desc = st.text_area("Description")
            assets = fetch_all_assets()
            asset_opts = {f"#{a['id']} {a['name']}": a['id'] for a in assets}
            asset_sel = st.selectbox("Related Asset (optional)", ["None"] + list(asset_opts.keys()))
            uploaded_file = st.file_uploader("File", type=["pdf", "docx", "png", "jpg", "jpeg"])
            if st.form_submit_button("Upload"):
                if title and uploaded_file:
                    asset_id = None if asset_sel == "None" else asset_opts[asset_sel]
                    if upload_document(uploaded_file.getvalue(), uploaded_file.name, title, desc, asset_id, st.session_state.user_payload.get('name')):
                        st.success("Document uploaded.")
                        st.rerun()
                    else:
                        st.error("Upload failed.")

def render_budget_center():
    st.markdown("### 💰 Budget Center")
    st.caption("Track maintenance costs against budgets per asset or department.")
    budgets = get_budget_status()
    if budgets:
        df = pd.DataFrame(budgets) if PANDAS_AVAILABLE else budgets
        st.dataframe(df)
        if PLOTLY_AVAILABLE and PANDAS_AVAILABLE:
            fig = px.bar(df, x="asset_id", y=["allocated_amount", "spent_to_date"], title="Budget vs Actual Spend")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No budgets set. Add budget entries in the database or use the form below.")
    with st.form("add_budget"):
        col1, col2 = st.columns(2)
        with col1:
            asset_id = st.number_input("Asset ID", min_value=1, step=1)
            fiscal_year = st.number_input("Fiscal Year", value=datetime.now().year)
        with col2:
            allocated = st.number_input("Allocated Amount", min_value=0.0, value=10000.0, step=100.0)
            department = st.text_input("Department (optional)")
        if st.form_submit_button("Add Budget"):
            supabase = get_supabase()
            if supabase:
                try:
                    supabase.table("budgets").insert({
                        "asset_id": asset_id, "department": department,
                        "fiscal_year": fiscal_year, "allocated_amount": allocated
                    }).execute()
                    st.success("Budget added.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

def render_automation():
    st.markdown("### 🤖 Automation Rules")
    st.caption("Run escalations and anomaly checks manually, or they trigger automatically.")
    if st.button("🔄 Run Escalation Check Now"):
        run_escalations()
        st.success("Escalations processed.")
    if st.button("📊 Check Meter Anomalies"):
        assets = fetch_all_assets()
        anomalies = []
        for a in assets:
            if detect_meter_anomaly(a['id']):
                anomalies.append(a['name'])
        if anomalies:
            st.warning(f"Anomalies detected on: {', '.join(anomalies)}")
        else:
            st.success("No anomalies detected.")

# ============================================================================
# INTEGRATION INSTRUCTIONS FOR app.py
# ============================================================================
"""
To integrate these features into your main app.py:

1. Place this file (phase2_upgrades.py) in the same directory as app.py.

2. Add the import statement at the top of app.py (after the other imports):
   import phase2_upgrades

3. In the main navigation section, add "Advanced" to nav_options and nav_icons:
   nav_options = ["Task Dashboard", "Assets", "Permits", "Inventory", "Incidents",
                  "Handover", "Contractors", "Analytics", "Chat", "Feedback", "Admin", "Profile",
                  "Timeline", "About", "Advanced"]
   nav_icons = ["list-task", "hdd-stack-fill", "shield-lock-fill", "box-seam-fill",
                "exclamation-triangle-fill", "arrow-left-right", "people-fill",
                "graph-up-arrow", "chat-dots-fill", "lightbulb-fill", "gear-fill", "person-circle",
                "clock-history", "info-circle-fill", "cpu-fill"]

4. In the section where you handle selected_section, add:
   elif selected_section == "Advanced":
       phase2_upgrades.render_advanced_tab()

5. (Optional) Hook the automation into task completion:
   Find where you call update_task(...) with status "Complete" and add:
   phase2_updates.update_budget_spent(task_id)
   phase2_updates.run_escalations()
   (You can call these after updating the task.)

6. Ensure you have run the SQL schema for the new tables (see schema_additions_phase2.sql).
"""
