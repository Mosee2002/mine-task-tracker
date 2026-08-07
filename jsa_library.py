# jsa_library.py
# Standalone JSA / Risk Assessment Library for MWDTS.
# Uses the existing `documents` table – no new schema needed.
# JSA documents are tagged with "[JSA]" or "[SWP]" in the title.

import streamlit as st
from datetime import datetime
import sys
import re
import json

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
        # Fetch all docs, filter in Python for simplicity
        res = supabase.table("documents").select("*").order("created_at", desc=True).execute()
        docs = res.data or []
        jsa_docs = [d for d in docs if d.get("title", "").startswith(("[JSA]", "[SWP]"))]
        if search_term:
            s = search_term.lower()
            jsa_docs = [d for d in jsa_docs if s in d.get("title", "").lower() or s in d.get("description", "").lower()]
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

    try:
        success = main.upload_document(
            file_bytes=file_bytes,
            filename=filename,
            title=full_title,
            description=description.strip(),
            asset_id=None,
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
        memory = st.session_state.get("jsa_memory", [])
        st.session_state.jsamemory = [d for d in memory if d.get("id") != doc_id]
        return True

    try:
        res = supabase.table("documents").select("title").eq("id", doc_id).execute()
        if not res.data:
            return False
        title = res.data[0].get("title", "")
        if not title.startswith(("[JSA]", "[SWP]")):
            st.error("This document is not a JSA/SWP.")
            return False
        del_res = supabase.table("documents").delete().eq("id", doc_id).execute()
        return bool(del_res.data)
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

    can_upload = _can(role, "asset.edit") or _can(role, "task.create")

    st.markdown('<div class="main-header" style="font-size: 1.8rem;">'
                '<i class="fas fa-file-alt"></i> JSA / Risk Assessment Library '
                '<small style="display:inline-block; font-size: 1rem;">Safe Work Procedures & Job Safety Analyses</small>'
                '</div>', unsafe_allow_html=True)

    # ----- FIX: Use a single tabs variable and index it -----
    if can_upload:
        tabs = st.tabs(["📋 Browse JSAs", "📤 Upload New JSA"])
        tab1, tab2 = tabs[0], tabs[1]
    else:
        tabs = st.tabs(["📋 Browse JSAs"])
        tab1 = tabs[0]
        tab2 = None

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
                        display_title = re.sub(r'^\[(JSA|SWP)\]\s*', '', title)
                        st.markdown(f"**{display_title}**")
                        if doc.get("description"):
                            st.markdown(f"<small>{doc.get('description')}</small>", unsafe_allow_html=True)
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
                        file_url = doc.get("file_url")
                        if file_url:
                            st.download_button(
                                label="📥 Download",
                                data=file_url,
                                file_name=doc.get("title", "document") + "." + (doc.get("file_type") or "pdf"),
                                key=f"dl_{doc['id']}",
                                use_container_width=True
                            )
                        if can_upload:
                            if st.button("🗑️", key=f"del_{doc['id']}", help="Delete this JSA"):
                                if delete_jsa_document(doc['id'], full_name):
                                    st.success("Deleted successfully.")
                                    st.rerun()
                                else:
                                    st.error("Delete failed.")

    if can_upload and tab2 is not None:
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

    st.markdown("---")
    st.caption("📌 JSA documents are stored in the `documents` table with a `[JSA]` or `[SWP]` prefix in the title.")
