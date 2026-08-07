# jsa_library.py
# Standalone JSA / Risk Assessment Library for MWDTS.
# Uses the existing `documents` table – no new schema needed.
# JSA documents are tagged with "[JSA]" or "[SWP]" in the title.

import streamlit as st
from datetime import datetime
import sys
import re

# -------------------------------
# 1. HELPERS
# -------------------------------
def _get_main_module():
    """Get the main app's namespace to reuse its functions and client."""
    main = sys.modules.get('__main__')
    if main is None:
        st.error("Could not find main app module. Are you running this as a plugin?")
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
    """Call the main app's can() function."""
    main = _get_main_module()
    if main and hasattr(main, 'can'):
        return main.can(role, capability)
    return False

# -------------------------------
# 2. DATABASE FUNCTIONS
# -------------------------------
def fetch_jsa_documents(search_term=""):
    """Fetch documents tagged as JSA/SWP (title starts with [JSA] or [SWP])."""
    supabase = _get_supabase()
    if not supabase:
        # Memory fallback
        return st.session_state.get("jsa_memory", [])

    try:
        # Build query: title ILIKE '[JSA]%' OR title ILIKE '[SWP]%'
        # Also allow searching within title/description
        query = supabase.table("documents").select("*")
        if search_term:
            search = f"%{search_term}%"
            query = query.or_(f"title.ilike.{search},description.ilike.{search}")
        # We cannot do OR on two ILIKE patterns easily with the Python client's filter chaining
        # We'll fetch all and filter in Python (less efficient but simpler)
        res = query.order("created_at", desc=True).execute()
        docs = res.data or []
        # Filter by title prefix
        jsa_docs = [d for d in docs if d.get("title", "").startswith(("[JSA]", "[SWP]"))]
        return jsa_docs
    except Exception as e:
        st.error(f"Could not fetch JSA documents: {e}")
        return []

def upload_jsa_document(file_bytes, filename, title, description, doc_type, uploaded_by):
    """Upload a JSA/SWP document using the main app's upload_document function."""
    main = _get_main_module()
    if not main or not hasattr(main, 'upload_document'):
        st.error("Main app's upload_document function not available.")
        return False

    # Prepend tag to title
    tag = "[JSA]" if doc_type == "JSA" else "[SWP]"
    full_title = f"{tag} {title.strip()}"

    # Call the main app's upload_document (asset_id = None for general docs)
    try:
        success = main.upload_document(
            file_bytes=file_bytes,
            filename=filename,
            title=full_title,
            description=description.strip(),
            asset_id=None,  # not linked to a specific asset
            uploaded_by=uploaded_by
        )
        return success
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return False

def delete_jsa_document(doc_id, deleted_by):
    """Delete a JSA document (if user has permission)."""
    supabase = _get_supabase()
    if not supabase:
        # Memory fallback
        memory = st.session_state.get("jsa_memory", [])
        st.session_state.jsamemory = [d for d in memory if d.get("id") != doc_id]
        return True

    try:
        # First verify it's a JSA doc
        res = supabase.table("documents").select("title").eq("id", doc_id).execute()
        if not res.data:
            return False
        title = res.data[0].get("title", "")
        if not title.startswith(("[JSA]", "[SWP]")):
            st.error("This document is not a JSA/SWP. Deletion not allowed.")
            return False
        # Perform delete
        del_res = supabase.table("documents").delete().eq("id", doc_id).execute()
        if del_res.data:
            # Also delete from storage? That's optional; we can leave it.
            return True
        else:
            return False
    except Exception as e:
        st.error(f"Delete failed: {e}")
        return False

# -------------------------------
# 3. MAIN RENDER FUNCTION
# -------------------------------
def render_jsa_library():
    user = _get_user()
    username = user.get("username")
    full_name = user.get("name", username)
    role = user.get("role", "").strip().lower()

    # Determine if user can upload (Supervisor or above)
    can_upload = _can(role, "asset.edit") or _can(role, "task.create")  # reuse existing permissions

    st.markdown('<div class="main-header" style="font-size: 1.8rem;">'
                '<i class="fas fa-file-alt"></i> JSA / Risk Assessment Library '
                '<small style="display:inline-block; font-size: 1rem;">Safe Work Procedures & Job Safety Analyses</small>'
                '</div>', unsafe_allow_html=True)

    # Tabs
    tab1, tab2 = st.tabs(["📋 Browse JSAs", "📤 Upload New JSA"]) if can_upload else (st.tabs(["📋 Browse JSAs"]),)

    with tab1:
        st.markdown("### Search and view all JSA/SWP documents")
        search = st.text_input("🔍 Search by title or description", placeholder="e.g., 'confined space'")

        docs = fetch_jsa_documents(search)

        if not docs:
            st.info("No JSA/SWP documents found. Upload one using the 'Upload New JSA' tab.")
        else:
            st.caption(f"Found {len(docs)} document(s)")
            for doc in docs:
                with st.container(border=True):
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        title = doc.get("title", "Untitled")
                        # Remove the [JSA] or [SWP] tag for display
                        display_title = re.sub(r'^\[(JSA|SWP)\]\s*', '', title)
                        st.markdown(f"**{display_title}**")
                        if doc.get("description"):
                            st.markdown(f"<small>{doc.get('description')}</small>", unsafe_allow_html=True)
                        # Meta info
                        meta = []
                        if doc.get("uploaded_by"):
                            meta.append(f"📤 {doc['uploaded_by']}")
                        if doc.get("created_at"):
                            dt = doc['created_at']
                            try:
                                dt_parsed = datetime.fromisoformat(dt.replace('Z', '+00:00').split('+')[0])
                                meta.append(f"📅 {dt_parsed.strftime('%b %d, %Y')}")
                            except:
                                pass
                        if meta:
                            st.caption(" · ".join(meta))
                    with col2:
                        # Download button
                        file_url = doc.get("file_url")
                        if file_url:
                            st.download_button(
                                label="📥 Download",
                                data=requests.get(file_url).content if file_url.startswith("http") else None,
                                file_name=doc.get("title", "document") + "." + (doc.get("file_type") or "pdf"),
                                mime="application/octet-stream",
                                key=f"dl_{doc['id']}",
                                use_container_width=True
                            )
                        # Delete button for supervisors
                        if can_upload:
                            if st.button("🗑️", key=f"del_{doc['id']}", help="Delete this JSA"):
                                if delete_jsa_document(doc['id'], full_name):
                                    st.success("Deleted successfully.")
                                    st.rerun()
                                else:
                                    st.error("Delete failed.")

    if can_upload:
        with tab2:
            st.markdown("### Upload a new JSA or SWP document")
            st.caption("Upload PDF, Word, or image files. The document will be stored in the library and searchable by all users.")

            with st.form("upload_jsa_form", clear_on_submit=True):
                doc_type = st.selectbox("Document type", ["JSA (Job Safety Analysis)", "SWP (Safe Work Procedure)"])
                title = st.text_input("Title *", placeholder="e.g., 'Confined Space Entry'")
                description = st.text_area("Description", placeholder="Brief summary of the procedure")
                uploaded_file = st.file_uploader("Choose file", type=["pdf", "doc", "docx", "txt", "jpg", "jpeg", "png", "gif", "webp"])
                submitted = st.form_submit_button("📤 Upload")

                if submitted:
                    if not title.strip():
                        st.error("Title is required.")
                    elif not uploaded_file:
                        st.error("Please select a file to upload.")
                    else:
                        doc_type_code = "JSA" if "JSA" in doc_type else "SWP"
                        success = upload_jsa_document(
                            file_bytes=uploaded_file.getvalue(),
                            filename=uploaded_file.name,
                            title=title.strip(),
                            description=description.strip(),
                            doc_type=doc_type_code,
                            uploaded_by=full_name
                        )
                        if success:
                            st.success("Document uploaded successfully!")
                            st.rerun()
                        else:
                            st.error("Upload failed. Check permissions and try again.")

    # Footer / note
    st.markdown("---")
    st.caption("📌 JSA documents are stored in the `documents` table with a `[JSA]` or `[SWP]` prefix in the title. "
               "They can be linked to tasks manually by referencing the title.")

# -------------------------------
# 4. IMPORT REQUESTS (for download)
# -------------------------------
try:
    import requests
except ImportError:
    # If requests not installed, we'll handle download differently
    requests = None
