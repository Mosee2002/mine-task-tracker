# wallboard.py
# A standalone, read-only Operations Wallboard for MWDTS.
# Drag and drop this into your project folder. No changes to app-5.py needed except mounting.

import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

# -------------------------------
# 1. MINIMAL HELPERS (copied from main app to keep this standalone)
# -------------------------------
def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00").split("+")[0])
    except Exception:
        return None

def _fmt_date(value):
    dt = _parse_dt(value)
    return dt.strftime("%b %d, %H:%M") if dt else "N/A"

# -------------------------------
# 2. MAIN RENDER FUNCTION
# -------------------------------
def render_wallboard():
    # Data is already loaded into session_state by the main app (Section 27).
    # We just read it.
    tasks = st.session_state.get("tasks", [])
    assets = st.session_state.get("assets", [])
    incidents = st.session_state.get("incidents", [])
    
    # Fetch permits and production via the main app's real functions —
    # not a session_state key check, since SUPABASE_AVAILABLE lives as
    # a plain module-level variable in app.py, never stored in
    # session_state. Checking st.session_state.get("supabase_available")
    # would always be False regardless of the real connection status.
    permits = []
    productions = []
    try:
        import sys
        main_module = sys.modules.get('__main__')
        if main_module and hasattr(main_module, 'fetch_permits'):
            permits = [p for p in main_module.fetch_permits() if p.get("status") == "Active"]
        if main_module and hasattr(main_module, 'fetch_production_records'):
            productions = main_module.fetch_production_records(limit=20)
    except Exception:
        pass

    # If the main app's functions weren't reachable at all, fall back
    # to whatever's already in session_state rather than showing
    # nothing.
    if not permits:
        permits = st.session_state.get("permits_memory", [])

    # -------------------------------
    # 3. LAYOUT
    # -------------------------------
    st.markdown('<div class="main-header" style="font-size: 2.2rem; text-align: center;">'
                '<i class="fas fa-tv"></i> Operations Wallboard '
                '<small style="display:inline-block; font-size: 1rem;">Live Site Overview</small>'
                '</div>', unsafe_allow_html=True)

    # --- Top KPI Stats (reusing your existing stat-grid CSS) ---
    total_tasks = len(tasks)
    open_tasks = sum(1 for t in tasks if t.get('status') not in ['Complete', 'Closed'])
    active_permits = len(permits)
    assets_down = sum(1 for a in assets if a.get('status') == 'Down')
    today_prod = 0
    for p in productions:
        if _parse_dt(p.get('production_date')):
            if _parse_dt(p.get('production_date')).date() == datetime.now().date():
                today_prod += p.get('quantity', 0)

    st.markdown(f"""
    <div class="stat-grid">
        <div class="stat-card" style="--stat-color:var(--tone-info);--stat-bg:var(--tone-info-soft);">
            <div class="stat-icon"><i class="fas fa-clipboard-list"></i></div>
            <div class="stat-body"><div class="stat-value">{total_tasks}</div><div class="stat-label">Total Work Orders</div></div>
        </div>
        <div class="stat-card" style="--stat-color:var(--tone-warn);--stat-bg:var(--tone-warn-soft);">
            <div class="stat-icon"><i class="fas fa-spinner"></i></div>
            <div class="stat-body"><div class="stat-value">{open_tasks}</div><div class="stat-label">Open Tasks</div></div>
        </div>
        <div class="stat-card" style="--stat-color:var(--tone-ok);--stat-bg:var(--tone-ok-soft);">
            <div class="stat-icon"><i class="fas fa-lock"></i></div>
            <div class="stat-body"><div class="stat-value">{active_permits}</div><div class="stat-label">Active Permits</div></div>
        </div>
        <div class="stat-card" style="--stat-color:var(--tone-danger);--stat-bg:var(--tone-danger-soft);">
            <div class="stat-icon"><i class="fas fa-triangle-exclamation"></i></div>
            <div class="stat-body"><div class="stat-value">{assets_down}</div><div class="stat-label">Assets Down</div></div>
        </div>
        <div class="stat-card" style="--stat-color:var(--tone-info);--stat-bg:var(--tone-info-soft);">
            <div class="stat-icon"><i class="fas fa-industry"></i></div>
            <div class="stat-body"><div class="stat-value">{today_prod:,.0f}</div><div class="stat-label">Today's Production (t)</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # --- Kanban Board (Tasks by Status) ---
    st.markdown("### 📋 Work Order Board")
    statuses = ["Unassigned", "In Progress", "Pending QA", "Blocked"]
    cols = st.columns(4)
    
    for idx, status in enumerate(statuses):
        with cols[idx]:
            st.markdown(f"<div style='text-align:center; font-weight:700; padding:0.5rem; background:var(--bg-surface); border-radius:8px;'>{status}</div>", unsafe_allow_html=True)
            filtered = [t for t in tasks if t.get('status') == status]
            if not filtered:
                st.caption("No tasks")
            for t in filtered[:5]:  # Show max 5 per column to avoid clutter
                due = _parse_dt(t.get('due_date'))
                overdue = due and due < datetime.now()
                border_color = "#dc2626" if overdue else "#0f3460"
                st.markdown(f"""
                <div style="background:var(--bg-surface); border-left: 4px solid {border_color}; 
                            padding:0.5rem; border-radius:6px; margin-bottom:0.5rem; font-size:0.85rem;">
                    <strong>#{t['id']}</strong> {t.get('title', '')[:25]}
                    <div style="font-size:0.7rem; color:var(--text-secondary);">
                        {t.get('location', '')} 
                        {f'<span style="color:#dc2626;">🔴 OVERDUE</span>' if overdue else ''}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    # --- Bottom Row: Production Log & Recent Incidents ---
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🏭 Recent Production")
        if productions:
            df = pd.DataFrame(productions[:10])
            df['date'] = df['production_date'].apply(lambda x: _fmt_date(x))
            st.dataframe(df[['date', 'shift', 'material_type', 'quantity', 'unit']], 
                         use_container_width=True, hide_index=True)
        else:
            st.info("No production logged yet.")

    with col2:
        st.markdown("### 🚨 Recent Incidents")
        if incidents:
            for inc in incidents[:5]:
                sev = inc.get('severity', 'Low')
                color = {"Critical":"#dc2626", "High":"#b45309", "Medium":"#1d4ed8", "Low":"#15803d"}.get(sev, "#4b5563")
                st.markdown(f"""
                <div style="display:flex; justify-content:space-between; background:var(--bg-surface-2); 
                            padding:0.4rem 0.8rem; border-radius:6px; margin-bottom:0.3rem; border-left:3px solid {color};">
                    <span><strong>{inc.get('incident_type')}</strong> - {inc.get('location', '')}</span>
                    <span style="font-size:0.75rem; color:var(--text-secondary);">{_fmt_date(inc.get('created_at'))}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No recent incidents.")

    st.caption("⏱️ Auto-refreshes on every click. Pin this tab to a wall-mounted screen for live site visibility.")
        
