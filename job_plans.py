# job_plans.py
# Standalone Job Plan Templates for MWDTS.
# Uses the existing `documents` table – no new schema needed.
# Job plans are stored with "[JOBPLAN]" prefix in title, JSON in description.

import streamlit as st
from datetime import datetime, timedelta
import sys
import json
import re

# -------------------------------
# 1. HELPERS
# -------------------------------
def _get_main_module():
    main = sys.modules.get('__main__')
    if main is None:
        st.error("Could not find main app module.")
        return None
    return main

def _get_supabase():
    main = _get_main_module()
    if main and hasattr(main, 'supabase'):
        return main.supabase
    return None

def _get_user():
    return st.session_state.get("user_payload", {})

def _can(role, capability):
    main = _get_main_module()
    if main and hasattr(main, 'can'):
        return main.can(role, capability)
    return False

def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00").split("+")[0])
    except Exception:
        return None

def _fmt_date(value):
    dt = _parse_dt(value)
    return dt.strftime("%b %d, %Y") if dt else "—"

# -------------------------------
# 2. DATABASE FUNCTIONS
# -------------------------------
def fetch_job_plans(search_term=""):
    """Fetch documents tagged as job plans (title starts with [JOBPLAN])."""
    supabase = _get_supabase()
    if not supabase:
        return st.session_state.get("job_plans_memory", [])

    try:
        # Fetch all docs, filter in Python for simplicity
        res = supabase.table("documents").select("*").order("created_at", desc=True).execute()
        docs = res.data or []
        plans = [d for d in docs if d.get("title", "").startswith("[JOBPLAN]")]
        if search_term:
            s = search_term.lower()
            plans = [p for p in plans if s in p.get("title", "").lower() or s in p.get("description", "").lower()]
        return plans
    except Exception as e:
        st.error(f"Could not fetch job plans: {e}")
        return []

def save_job_plan(title, description, plan_data, uploaded_by):
    """Save a job plan as a document in the documents table."""
    supabase = _get_supabase()
    if not supabase:
        # Memory fallback
        memory = st.session_state.setdefault("job_plans_memory", [])
        new_plan = {
            "id": len(memory) + 1,
            "title": f"[JOBPLAN] {title}",
            "description": json.dumps(plan_data),
            "uploaded_by": uploaded_by,
            "created_at": datetime.now().isoformat(),
            "file_url": None,
            "file_type": "json"
        }
        memory.append(new_plan)
        return new_plan

    try:
        # Use the main app's upload_document function with a dummy file
        main = _get_main_module()
        if main and hasattr(main, 'upload_document'):
            # We'll store the JSON as a text file attachment
            json_bytes = json.dumps(plan_data, indent=2).encode('utf-8')
            filename = f"{title.replace(' ', '_')}.json"
            success = main.upload_document(
                file_bytes=json_bytes,
                filename=filename,
                title=f"[JOBPLAN] {title}",
                description=json.dumps(plan_data),
                asset_id=None,
                uploaded_by=uploaded_by
            )
            if success:
                # Fetch the newly created doc to return it
                res = supabase.table("documents").select("*").eq("title", f"[JOBPLAN] {title}").order("created_at", desc=True).limit(1).execute()
                return res.data[0] if res.data else None
            else:
                return None
        else:
            st.error("upload_document not available in main app.")
            return None
    except Exception as e:
        st.error(f"Failed to save job plan: {e}")
        return None

def delete_job_plan(doc_id, deleted_by):
    """Delete a job plan document."""
    supabase = _get_supabase()
    if not supabase:
        memory = st.session_state.get("job_plans_memory", [])
        st.session_state.job_plans_memory = [p for p in memory if p.get("id") != doc_id]
        return True

    try:
        # Verify it's a job plan
        res = supabase.table("documents").select("title").eq("id", doc_id).execute()
        if not res.data:
            return False
        title = res.data[0].get("title", "")
        if not title.startswith("[JOBPLAN]"):
            st.error("This is not a job plan.")
            return False
        # Delete
        del_res = supabase.table("documents").delete().eq("id", doc_id).execute()
        return bool(del_res.data)
    except Exception as e:
        st.error(f"Delete failed: {e}")
        return False

def apply_job_plan(plan_doc, user_full_name):
    """Create a new task from a job plan template."""
    main = _get_main_module()
    if not main or not hasattr(main, 'create_task'):
        st.error("Main app's create_task function not available.")
        return None, "create_task not found"

    try:
        plan_data = json.loads(plan_doc.get("description", "{}"))
    except json.JSONDecodeError:
        return None, "Invalid job plan data."

    # Extract plan fields with defaults
    title = plan_data.get("title", "Untitled Job")
    location = plan_data.get("location", "")
    priority = plan_data.get("priority", "Medium")
    loto = plan_data.get("loto", False)
    jsa = plan_data.get("jsa", False)
    work_type = plan_data.get("work_type", "Planned")
    labour_rate = plan_data.get("labour_rate", 0.0)
    weather_sensitive = plan_data.get("weather_sensitive", False)
    due_offset_days = plan_data.get("due_offset_days", 7)
    due_date = datetime.now() + timedelta(days=due_offset_days)
    asset_id = plan_data.get("asset_id")  # optional
    meter_interval = plan_data.get("meter_interval")  # optional
    recurrence_type = plan_data.get("recurrence_type")  # e.g. "weekly"
    recurrence_end_date = None
    if recurrence_type:
        recurrence_end_date = datetime.now() + timedelta(days=365)

    # Create the task
    new_task = main.create_task(
        title=title,
        location=location,
        priority=priority,
        loto=loto,
        jsa=jsa,
        created_by=user_full_name,
        due_date=due_date,
        is_recurring=bool(recurrence_type),
        recurrence_type=recurrence_type if recurrence_type else None,
        recurrence_end_date=recurrence_end_date,
        asset_id=asset_id,
        meter_interval=meter_interval,
        work_type=work_type,
        labour_rate=labour_rate,
        weather_sensitive=weather_sensitive,
    )

    if not new_task:
        return None, "Failed to create task. Check permissions."

    # If BOM parts are specified, link them
    parts = plan_data.get("parts", [])
    if parts and hasattr(main, 'link_part_to_task'):
        task_id = new_task.get("id")
        linked_count = 0
        for part_item in parts:
            part_id = part_item.get("part_id")
            quantity = part_item.get("quantity", 1)
            if part_id:
                success = main.link_part_to_task(task_id, part_id, quantity, user_full_name)
                if success:
                    linked_count += 1
        if linked_count > 0:
            st.success(f"Task #{task_id} created with {linked_count} part(s) linked.")
        else:
            st.success(f"Task #{task_id} created (no parts linked).")
    else:
        st.success(f"Task #{new_task.get('id')} created successfully.")

    return new_task, None

# -------------------------------
# 3. MAIN RENDER FUNCTION
# -------------------------------
def render_job_plans():
    user = _get_user()
    username = user.get("username")
    full_name = user.get("name", username)
    role = user.get("role", "").strip().lower()

    can_manage = _can(role, "task.create") or _can(role, "asset.edit")

    st.markdown('<div class="main-header" style="font-size: 1.8rem;">'
                '<i class="fas fa-cubes"></i> Job Plan Templates '
                '<small style="display:inline-block; font-size: 1rem;">Pre-built work orders – apply with one click</small>'
                '</div>', unsafe_allow_html=True)

    # Tabs
    if can_manage:
        tab1, tab2, tab3 = st.tabs(["📋 Browse Plans", "➕ Create New Plan", "🔄 Apply Plan"])
    else:
        tab1, tab2 = st.tabs(["📋 Browse Plans", "🔄 Apply Plan"])

    with tab1:
        st.markdown("### Available Job Plans")
        search = st.text_input("🔍 Search by title or description", placeholder="e.g., 'conveyor'")
        plans = fetch_job_plans(search)

        if not plans:
            st.info("No job plans found. Create one using the 'Create New Plan' tab.")
        else:
            st.caption(f"Found {len(plans)} plan(s)")
            for plan in plans:
                with st.container(border=True):
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        title = plan.get("title", "")
                        display_title = re.sub(r'^\[JOBPLAN\]\s*', '', title)
                        st.markdown(f"**{display_title}**")
                        try:
                            data = json.loads(plan.get("description", "{}"))
                            # Show summary
                            details = []
                            if data.get("location"):
                                details.append(f"📍 {data['location']}")
                            if data.get("work_type"):
                                details.append(f"🛠️ {data['work_type']}")
                            if data.get("priority"):
                                details.append(f"⚡ {data['priority']}")
                            if data.get("parts"):
                                details.append(f"📦 {len(data['parts'])} part(s)")
                            if data.get("loto"):
                                details.append("🔒 LOTO")
                            if data.get("jsa"):
                                details.append("📋 JSA")
                            st.caption(" · ".join(details))
                        except:
                            st.caption("(no structured data)")
                        meta = []
                        if plan.get("uploaded_by"):
                            meta.append(f"📤 {plan['uploaded_by']}")
                        if plan.get("created_at"):
                            meta.append(f"📅 {_fmt_date(plan['created_at'])}")
                        if meta:
                            st.caption(" · ".join(meta))
                    with col2:
                        if can_manage:
                            if st.button("🗑️", key=f"del_plan_{plan['id']}", help="Delete this plan"):
                                if delete_job_plan(plan['id'], full_name):
                                    st.success("Plan deleted.")
                                    st.rerun()
                                else:
                                    st.error("Delete failed.")

    if can_manage:
        with tab2:
            st.markdown("### Create a New Job Plan")
            st.caption("Define a standard job that can be applied repeatedly.")

            # Fetch parts for BOM selection
            main = _get_main_module()
            parts = []
            if main and hasattr(main, 'st') and hasattr(main, 'session_state'):
                parts = main.st.session_state.get("parts", [])
            else:
                # Fallback: try to fetch directly
                supabase = _get_supabase()
                if supabase:
                    try:
                        res = supabase.table("inventory_parts").select("*").execute()
                        parts = res.data or []
                    except:
                        pass

            with st.form("create_job_plan_form", clear_on_submit=True):
                plan_title = st.text_input("Plan Title *", placeholder="e.g., '5000hr Conveyor Service'")
                plan_location = st.text_input("Default Location / Area", placeholder="e.g., 'Plant 1 - Conveyor A'")
                col1, col2 = st.columns(2)
                with col1:
                    plan_priority = st.selectbox("Default Priority", ["Low", "Medium", "High", "Critical"])
                    plan_work_type = st.selectbox("Work Type", ["Planned", "Preventive", "Predictive", "Improvement", "Reactive"])
                    plan_loto = st.checkbox("Requires LOTO")
                    plan_jsa = st.checkbox("Requires JSA")
                with col2:
                    plan_labour_rate = st.number_input("Labour Rate (per hour)", min_value=0.0, value=0.0, step=1.0)
                    plan_due_days = st.number_input("Default Due In (days)", min_value=1, value=7, step=1)
                    plan_weather = st.checkbox("Weather-sensitive")
                    plan_recurrence = st.selectbox("Recurrence (optional)", ["None", "Weekly", "Monthly", "Quarterly"])

                # BOM (Bill of Materials) section
                st.markdown("#### Parts / BOM")
                st.caption("Add parts that this job typically requires. They will be auto-linked when the plan is applied.")
                part_options = {}
                selected_parts = []
                part_qty = {}
                if parts:
                    part_options = {f"{p.get('part_name', '')} (ID: {p['id']})": p["id"] for p in parts if p.get("id")}
                    selected_parts = st.multiselect("Select parts", list(part_options.keys()), key="bom_parts")
                    if selected_parts:
                        st.markdown("**Quantities**")
                        qty_cols = st.columns(min(len(selected_parts), 4))
                        for idx, part_label in enumerate(selected_parts):
                            with qty_cols[idx % len(qty_cols)]:
                                part_qty[part_label] = st.number_input(f"Qty for {part_label[:20]}...", min_value=1, value=1, key=f"qty_{idx}")
                else:
                    st.warning("No parts in inventory. You can add parts via the Inventory section first.")

                submitted = st.form_submit_button("💾 Save Job Plan")

                if submitted:
                    if not plan_title.strip():
                        st.error("Plan title is required.")
                    else:
                        # Build JSON payload
                        plan_data = {
                            "title": plan_title.strip(),
                            "location": plan_location.strip(),
                            "priority": plan_priority,
                            "work_type": plan_work_type,
                            "loto": plan_loto,
                            "jsa": plan_jsa,
                            "labour_rate": plan_labour_rate,
                            "due_offset_days": plan_due_days,
                            "weather_sensitive": plan_weather,
                            "recurrence_type": plan_recurrence if plan_recurrence != "None" else None,
                            "parts": []
                        }
                        for part_label in selected_parts:
                            part_id = part_options[part_label]
                            qty = part_qty.get(part_label, 1)
                            plan_data["parts"].append({"part_id": part_id, "quantity": qty})

                        saved = save_job_plan(plan_title.strip(), json.dumps(plan_data), plan_data, full_name)
                        if saved:
                            st.success(f"Job plan '{plan_title}' saved successfully!")
                            st.rerun()
                        else:
                            st.error("Failed to save job plan.")

    # Tab 2 or 3: Apply Plan
    apply_tab = tab2 if not can_manage else tab3
    with apply_tab:
        st.markdown("### Apply a Job Plan to Create a Work Order")
        st.caption("Select a plan, optionally override location/due date, and click Apply.")

        plans = fetch_job_plans()
        if not plans:
            st.info("No job plans available. Create one first.")
        else:
            plan_options = {}
            for p in plans:
                title = p.get("title", "")
                display_title = re.sub(r'^\[JOBPLAN\]\s*', '', title)
                plan_options[display_title] = p

            selected_plan_title = st.selectbox("Select Job Plan", list(plan_options.keys()))
            selected_plan = plan_options[selected_plan_title]

            # Show plan details
            plan_data = {}
            try:
                plan_data = json.loads(selected_plan.get("description", "{}"))
                with st.expander("📋 Plan Details", expanded=True):
                    st.markdown(f"**Title:** {plan_data.get('title', '')}")
                    st.markdown(f"**Location:** {plan_data.get('location', 'Not specified')}")
                    st.markdown(f"**Work Type:** {plan_data.get('work_type', 'Planned')}")
                    st.markdown(f"**Priority:** {plan_data.get('priority', 'Medium')}")
                    if plan_data.get('loto'):
                        st.markdown("🔒 **Requires LOTO**")
                    if plan_data.get('jsa'):
                        st.markdown("📋 **Requires JSA**")
                    parts_list = plan_data.get("parts", [])
                    if parts_list:
                        st.markdown("**Parts / BOM:**")
                        main = _get_main_module()
                        parts_lookup = {}
                        if main and hasattr(main, 'st'):
                            all_parts = main.st.session_state.get("parts", [])
                            parts_lookup = {p["id"]: p for p in all_parts}
                        for part in parts_list:
                            part_id = part.get("part_id")
                            qty = part.get("quantity", 1)
                            part_name = parts_lookup.get(part_id, {}).get("part_name", f"Part #{part_id}")
                            st.markdown(f"- {part_name} × {qty}")
            except:
                st.warning("Plan data could not be parsed.")

            # Override options
            col1, col2 = st.columns(2)
            with col1:
                override_location = st.text_input("Override Location (optional)", value=plan_data.get("location", ""))
            with col2:
                due_days = st.number_input("Due In (days)", min_value=1, value=plan_data.get("due_offset_days", 7), step=1)

            if st.button("🚀 Apply Plan", type="primary", use_container_width=True):
                # Update plan_data with overrides before creating task
                plan_data["location"] = override_location
                plan_data["due_offset_days"] = due_days
                # Update the doc description with the overrides (but don't persist)
                # We'll pass the modified data directly to apply function
                # We need to create a new doc dict with the modified description
                modified_doc = selected_plan.copy()
                modified_doc["description"] = json.dumps(plan_data)
                new_task, error = apply_job_plan(modified_doc, full_name)
                if error:
                    st.error(error)
                else:
                    st.rerun()

    st.markdown("---")
    st.caption("📌 Job plans are stored in the `documents` table with a `[JOBPLAN]` prefix. "
               "They include default settings and a BOM (Bill of Materials) for common jobs.")
