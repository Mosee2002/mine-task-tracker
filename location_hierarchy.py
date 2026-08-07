# location_hierarchy.py
# Standalone Location Hierarchy (Digital Twin Lite) for MWDTS.
# Stores the entire site hierarchy in a single JSON document in the `documents` table.
# No new tables or schema changes required.

import streamlit as st
from datetime import datetime
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

def _get_document_by_title(title):
    """Fetch the document with the given title (exact match)."""
    supabase = _get_supabase()
    if not supabase:
        # Memory fallback
        docs = st.session_state.get("location_hierarchy_memory", [])
        for d in docs:
            if d.get("title") == title:
                return d
        return None
    try:
        res = supabase.table("documents").select("*").eq("title", title).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        st.error(f"Could not fetch hierarchy: {e}")
        return None

def _save_location_document(data, uploaded_by):
    """Save the hierarchy as a JSON document in the documents table."""
    supabase = _get_supabase()
    if not supabase:
        # Memory fallback
        st.session_state["location_hierarchy_memory"] = [{
            "id": 1,
            "title": "[LOCATION] Hierarchy",
            "description": json.dumps(data),
            "uploaded_by": uploaded_by,
            "created_at": datetime.now().isoformat()
        }]
        return True

    # Use the main app's upload_document to store the JSON
    main = _get_main_module()
    if not main or not hasattr(main, 'upload_document'):
        st.error("upload_document not available.")
        return False

    # Convert data to JSON string
    json_bytes = json.dumps(data, indent=2).encode('utf-8')
    filename = "location_hierarchy.json"

    # First, delete the existing location document if it exists
    existing = _get_document_by_title("[LOCATION] Hierarchy")
    if existing:
        try:
            supabase.table("documents").delete().eq("id", existing["id"]).execute()
        except:
            pass

    # Upload new
    success = main.upload_document(
        file_bytes=json_bytes,
        filename=filename,
        title="[LOCATION] Hierarchy",
        description=json.dumps(data),
        asset_id=None,
        uploaded_by=uploaded_by
    )
    return success

def _load_location_data():
    """Load the location hierarchy from the document."""
    doc = _get_document_by_title("[LOCATION] Hierarchy")
    if not doc:
        return None
    try:
        return json.loads(doc.get("description", "{}"))
    except:
        return None

def _get_next_id(data):
    """Return the next available ID for a new location."""
    if not data or "locations" not in data:
        return 1
    ids = [loc.get("id", 0) for loc in data["locations"]]
    return max(ids) + 1 if ids else 1

def _add_location(data, name, parent_id):
    """Add a new location to the hierarchy data."""
    if not data:
        data = {"locations": []}
    if not data.get("locations"):
        data["locations"] = []
    new_id = _get_next_id(data)
    data["locations"].append({
        "id": new_id,
        "name": name.strip(),
        "parent_id": parent_id
    })
    return data

def _delete_location(data, loc_id):
    """Delete a location and all its children recursively."""
    if not data or "locations" not in data:
        return data
    # Find all descendants
    to_delete = set()
    def find_children(parent_id):
        for loc in data["locations"]:
            if loc.get("parent_id") == parent_id:
                to_delete.add(loc["id"])
                find_children(loc["id"])
    to_delete.add(loc_id)
    find_children(loc_id)
    # Filter out deleted
    data["locations"] = [loc for loc in data["locations"] if loc["id"] not in to_delete]
    return data

def _get_children(data, parent_id):
    """Return list of locations with the given parent_id."""
    if not data or "locations" not in data:
        return []
    return [loc for loc in data["locations"] if loc.get("parent_id") == parent_id]

def _get_location_name(data, loc_id):
    """Get the name of a location by ID."""
    if not data or "locations" not in data:
        return None
    for loc in data["locations"]:
        if loc["id"] == loc_id:
            return loc["name"]
    return None

def _get_full_path(data, loc_id):
    """Get the full hierarchical path (root -> ... -> this) as a string."""
    if not data or "locations" not in data:
        return ""
    path = []
    current_id = loc_id
    while current_id is not None:
        loc = next((l for l in data["locations"] if l["id"] == current_id), None)
        if not loc:
            break
        path.insert(0, loc["name"])
        current_id = loc.get("parent_id")
    return " / ".join(path)

# -------------------------------
# 2. MAIN RENDER FUNCTION
# -------------------------------
def render_location_hierarchy():
    user = _get_user()
    full_name = user.get("name", "Unknown")
    role = user.get("role", "").strip().lower()
    can_manage = _can(role, "asset.edit") or _can(role, "task.create")

    st.markdown('<div class="main-header" style="font-size: 1.8rem;">'
                '<i class="fas fa-sitemap"></i> Location Hierarchy '
                '<small style="display:inline-block; font-size: 1rem;">Define your site structure – Site → Area → Zone → Equipment</small>'
                '</div>', unsafe_allow_html=True)

    # Load data
    data = _load_location_data()
    if data is None:
        data = {"locations": []}

    # Tabs
    tabs = ["🌳 View Hierarchy"]
    if can_manage:
        tabs.append("➕ Manage Locations")
    tab_objs = st.tabs(tabs)

    with tab_objs[0]:
        st.markdown("### Current Site Structure")
        if not data.get("locations"):
            st.info("No locations defined yet. Use the 'Manage Locations' tab to create your hierarchy.")
        else:
            # Render as a tree using nested expanders
            def render_tree(parent_id, indent=0):
                children = _get_children(data, parent_id)
                if not children:
                    return
                for child in children:
                    loc_id = child["id"]
                    loc_name = child["name"]
                    # Indent with spaces
                    st.markdown(f"{'&nbsp;' * indent * 4}📍 **{loc_name}**", unsafe_allow_html=True)
                    # Recursively render children
                    render_tree(loc_id, indent + 1)

            # Start from root (parent_id = None)
            root_children = _get_children(data, None)
            if root_children:
                for root in root_children:
                    st.markdown(f"## 🏗️ {root['name']}")
                    render_tree(root["id"], 1)
            else:
                st.caption("No root-level locations defined. Add a Site first.")

            # Show full table as well
            with st.expander("📋 Full List (all locations)"):
                if data.get("locations"):
                    rows = []
                    for loc in sorted(data["locations"], key=lambda x: x.get("id")):
                        path = _get_full_path(data, loc["id"])
                        rows.append({
                            "ID": loc["id"],
                            "Name": loc["name"],
                            "Parent ID": loc.get("parent_id"),
                            "Full Path": path
                        })
                    import pandas as pd
                    df = pd.DataFrame(rows)
                    st.dataframe(df, use_container_width=True, hide_index=True)

    if can_manage:
        with tab_objs[1]:
            st.markdown("### Manage Locations")
            st.caption("Add or delete locations. Use the 'Full Path' to see the hierarchy.")

            # Add new location form
            with st.form("add_location_form", clear_on_submit=True):
                loc_name = st.text_input("Location Name *", placeholder="e.g., 'Plant 1', 'Crushing Area', 'Conveyor B'")
                # Parent selection
                parent_options = [("Root (no parent)", None)]
                if data.get("locations"):
                    for loc in sorted(data["locations"], key=lambda x: x.get("id")):
                        path = _get_full_path(data, loc["id"])
                        parent_options.append((f"{loc['name']} ({path})", loc["id"]))
                parent_choice = st.selectbox("Parent Location", parent_options, format_func=lambda x: x[0])
                parent_id = parent_choice[1] if parent_choice else None
                submitted = st.form_submit_button("➕ Add Location")

                if submitted:
                    if not loc_name.strip():
                        st.error("Location name is required.")
                    else:
                        # Check for duplicate name under same parent
                        existing = [l for l in data["locations"] if l["name"].strip().lower() == loc_name.strip().lower() and l.get("parent_id") == parent_id]
                        if existing:
                            st.error(f"Location '{loc_name}' already exists under this parent.")
                        else:
                            data = _add_location(data, loc_name, parent_id)
                            if _save_location_document(data, full_name):
                                st.success(f"Added '{loc_name}'.")
                                st.rerun()
                            else:
                                st.error("Failed to save hierarchy.")

            # Delete section
            st.markdown("---")
            st.markdown("### Delete a Location")
            if not data.get("locations"):
                st.info("No locations to delete.")
            else:
                # Build dropdown of all locations with full path
                delete_options = []
                for loc in sorted(data["locations"], key=lambda x: x.get("id")):
                    path = _get_full_path(data, loc["id"])
                    delete_options.append((f"{loc['name']} (ID: {loc['id']}) – {path}", loc["id"]))
                del_choice = st.selectbox("Select location to delete", delete_options, format_func=lambda x: x[0])
                del_id = del_choice[1]
                # Check if it has children
                children = _get_children(data, del_id)
                if children:
                    st.warning(f"This location has {len(children)} child location(s). They will also be deleted.")
                confirm = st.checkbox("I understand this will permanently delete this location and all its children.")
                if st.button("🗑️ Delete", disabled=not confirm):
                    data = _delete_location(data, del_id)
                    if _save_location_document(data, full_name):
                        st.success("Deleted.")
                        st.rerun()
                    else:
                        st.error("Delete failed.")

            # Import/Export
            st.markdown("---")
            st.markdown("### Import / Export")
            # Export JSON
            if data.get("locations"):
                json_str = json.dumps(data, indent=2)
                st.download_button(
                    label="📥 Export Hierarchy as JSON",
                    data=json_str,
                    file_name="location_hierarchy.json",
                    mime="application/json",
                    key="export_loc"
                )
            # Import JSON
            uploaded_file = st.file_uploader("Import JSON hierarchy (overwrites current)", type=["json"], key="import_loc")
            if uploaded_file is not None:
                try:
                    import_data = json.load(uploaded_file)
                    if "locations" not in import_data:
                        st.error("Invalid format: missing 'locations' key.")
                    else:
                        if st.button("⚠️ Overwrite Current Hierarchy"):
                            if _save_location_document(import_data, full_name):
                                st.success("Imported successfully.")
                                st.rerun()
                            else:
                                st.error("Import failed.")
                except Exception as e:
                    st.error(f"Invalid JSON: {e}")

    # Footer note
    st.markdown("---")
    st.caption("📍 Locations are stored as a single JSON document in the `documents` table. "
               "Use the full path when manually entering locations in tasks, assets, or incidents.")
