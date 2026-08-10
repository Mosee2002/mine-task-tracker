# crew_clock.py
# Crew Clock – uses shift_rosters with a sentinel for open punches (because shift_end is NOT NULL)

import streamlit as st
from datetime import datetime, timedelta
import sys
import json

# ----- SENTINEL for open shifts (must be a valid timestamp, NOT NULL) -----
OPEN_SHIFT_SENTINEL = "9999-12-31 23:59:59"

# -------------------------------
# HELPERS
# -------------------------------
def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00").split("+")[0])
    except Exception:
        return None

def _fmt_time(value):
    dt = _parse_dt(value)
    return dt.strftime("%H:%M") if dt else "—"

def _fmt_date(value):
    dt = _parse_dt(value)
    return dt.strftime("%b %d, %Y") if dt else "—"

def _get_supabase():
    main = sys.modules.get('__main__')
    if main and hasattr(main, 'supabase'):
        return main.supabase
    return None

def get_open_punch(username):
    """Returns the open punch record (where shift_end == sentinel)."""
    supabase = _get_supabase()
    if not supabase:
        punches = st.session_state.get("crew_clock_memory", [])
        for p in punches:
            if p.get("username") == username and p.get("shift_end") == OPEN_SHIFT_SENTINEL:
                return p
        return None
    try:
        res = supabase.table("shift_rosters") \
            .select("*") \
            .eq("username", username) \
            .eq("shift_end", OPEN_SHIFT_SENTINEL) \
            .eq("crew_name", "Clock") \
            .order("shift_start", desc=True) \
            .limit(1) \
            .execute()
        return res.data[0] if res.data else None
    except Exception as e:
        st.error(f"Could not fetch clock status: {e}")
        return None

def punch_in(username, full_name):
    """Insert a new punch with shift_end = sentinel."""
    supabase = _get_supabase()
    now = datetime.now().isoformat()

    # Check if already punched in
    if get_open_punch(username):
        return False, "You are already punched in. Please punch out first."

    if not supabase:
        punches = st.session_state.setdefault("crew_clock_memory", [])
        punches.append({
            "username": username,
            "full_name": full_name,
            "shift_start": now,
            "shift_end": OPEN_SHIFT_SENTINEL,
            "crew_name": "Clock",
            "assigned_by": username
        })
        return True, "Punched in (memory mode)"

    payload = {
        "username": username,
        "shift_start": now,
        "shift_end": OPEN_SHIFT_SENTINEL,
        "crew_name": "Clock",
        "assigned_by": username
    }

    try:
        res = supabase.table("shift_rosters").insert(payload).execute()
        if res.data:
            return True, "✅ Punched in successfully!"
        else:
            return False, f"Insert returned no data. Response: {res}"
    except Exception as e:
        return False, f"Punch-in failed: {e}"

def punch_out(username):
    """Update the open punch with actual shift_end."""
    supabase = _get_supabase()
    now = datetime.now().isoformat()

    if not supabase:
        punches = st.session_state.get("crew_clock_memory", [])
        for p in punches:
            if p.get("username") == username and p.get("shift_end") == OPEN_SHIFT_SENTINEL:
                p["shift_end"] = now
                return True, "Punched out (memory mode)"
        return False, "No open punch found"

    open_punch = get_open_punch(username)
    if not open_punch:
        return False, "You don't have an open punch to close."

    try:
        res = supabase.table("shift_rosters") \
            .update({"shift_end": now}) \
            .eq("id", open_punch["id"]) \
            .execute()
        if res.data:
            return True, "✅ Punched out successfully!"
        else:
            return False, "Update returned no data – check RLS"
    except Exception as e:
        return False, f"Punch-out failed: {e}"

def get_punch_history(username, days=7):
    """Get completed punches (real end times, not sentinel) for the last N days."""
    supabase = _get_supabase()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    if not supabase:
        punches = st.session_state.get("crew_clock_memory", [])
        return [p for p in punches if p.get("username") == username and p.get("shift_end") != OPEN_SHIFT_SENTINEL]

    try:
        # Use .neq() for "not equal"
        res = supabase.table("shift_rosters") \
            .select("*") \
            .eq("username", username) \
            .eq("crew_name", "Clock") \
            .neq("shift_end", OPEN_SHIFT_SENTINEL) \
            .gte("shift_start", cutoff) \
            .order("shift_start", desc=True) \
            .execute()
        return res.data or []
    except Exception as e:
        st.error(f"Could not fetch history: {e}")
        return []

# -------------------------------
# MAIN RENDER
# -------------------------------
def render_crew_clock():
    user = st.session_state.get("user_payload", {})
    username = user.get("username")
    full_name = user.get("name", username)

    if not username:
        st.warning("Please log in to use the Crew Clock.")
        return

    st.markdown('<div class="main-header" style="font-size: 1.8rem;">'
                '<i class="fas fa-clock"></i> Crew Time Clock '
                '<small style="display:inline-block; font-size: 1rem;">Punch in / out for your shift</small>'
                '</div>', unsafe_allow_html=True)

    open_punch = get_open_punch(username)
    is_punched_in = open_punch is not None

    col1, col2, col3 = st.columns([2, 1, 2])

    with col1:
        if is_punched_in:
            start_time = _parse_dt(open_punch["shift_start"])
            duration = datetime.now() - start_time if start_time else timedelta(0)
            hours, remainder = divmod(duration.total_seconds(), 3600)
            minutes = remainder // 60
            st.markdown(f"""
            <div class="stat-card" style="--stat-color:var(--tone-ok);--stat-bg:var(--tone-ok-soft);">
                <div class="stat-icon"><i class="fas fa-check-circle" style="color: #15803d;"></i></div>
                <div class="stat-body">
                    <div class="stat-value">🟢 Punched In</div>
                    <div class="stat-label">Started at {_fmt_time(open_punch['shift_start'])} · {int(hours)}h {int(minutes)}m ago</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="stat-card" style="--stat-color:var(--tone-neutral);--stat-bg:var(--tone-neutral-soft);">
                <div class="stat-icon"><i class="fas fa-circle" style="color: #4b5563;"></i></div>
                <div class="stat-body">
                    <div class="stat-value">⚪ Punched Out</div>
                    <div class="stat-label">You are not currently clocked in</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    with col2:
        if is_punched_in:
            if st.session_state.get("_pending_punch_out"):
                st.caption("Confirm below to finish punching out.")
            elif st.button("⏹️ Punch Out", use_container_width=True, type="primary"):
                # Don't punch out immediately — go to a confirm step first,
                # so hours can be attributed to a task (Auto-Costing) before
                # the punch actually closes. Splitting this into two clicks
                # is deliberate: computing hours-worked and picking a task
                # both need the ACTUAL punch-out moment as their reference
                # point, so they have to happen together, not after the
                # punch already closed.
                st.session_state["_pending_punch_out"] = True
                st.rerun()
        else:
            if st.button("🟢 Punch In", use_container_width=True, type="primary"):
                ok, msg = punch_in(username, full_name)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    with col3:
        history = get_punch_history(username, days=30)
        total_punches = len(history)
        days_worked = len(set(_fmt_date(p["shift_start"]) for p in history if p.get("shift_start")))
        st.metric("Total Punches (30d)", total_punches)
        st.caption(f"Days worked: {days_worked}")

    st.markdown("---")

    if st.session_state.get("_pending_punch_out"):
        st.markdown("#### ⏹️ Confirm Punch Out")
        _hours_worked = 0.0
        if open_punch and open_punch.get("shift_start"):
            _start = _parse_dt(open_punch["shift_start"])
            if _start:
                _hours_worked = (datetime.now() - _start).total_seconds() / 3600.0
        st.caption(f"Shift length: {_hours_worked:.1f} hours")

        main = sys.modules.get('__main__')
        _my_tasks = []
        if main and hasattr(main, 'st'):
            try:
                _my_tasks = [t2 for t2 in main.st.session_state.get("tasks", [])
                            if t2.get("assigned_to") == full_name and t2.get("status") in ("In Progress", "Pending QA")]
            except Exception:
                _my_tasks = []

        _no_task_option = "N/A — general work, no specific task"
        _task_choices = {_no_task_option: None}
        _task_choices.update({f"#{t2['id']} {t2['title']}": t2['id'] for t2 in _my_tasks})
        _picked = st.selectbox(
            "Which task did you work on this shift? (Auto-Costing)",
            list(_task_choices.keys()),
            help="Adds this shift's hours to the task's labour cost automatically — "
                "select N/A if the shift wasn't spent on one specific task.")

        _cc1, _cc2 = st.columns(2)
        with _cc1:
            if st.button("✅ Confirm Punch Out", use_container_width=True, type="primary"):
                ok, msg = punch_out(username)
                if ok:
                    _task_id = _task_choices[_picked]
                    if _task_id is not None and _hours_worked > 0 and main and hasattr(main, 'apply_labour_hours_to_task'):
                        main.apply_labour_hours_to_task(_task_id, _hours_worked, full_name)
                    st.session_state.pop("_pending_punch_out", None)
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        with _cc2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.pop("_pending_punch_out", None)
                st.rerun()
        st.markdown("---")

    st.markdown("### 📋 Last 7 Days")
    history_7d = get_punch_history(username, days=7)

    if not history_7d:
        st.info("No completed clock entries in the last 7 days.")
    else:
        rows = []
        for p in history_7d:
            start = _parse_dt(p.get("shift_start"))
            end = _parse_dt(p.get("shift_end"))
            date_str = start.strftime("%a %d %b") if start else "—"
            start_str = start.strftime("%H:%M") if start else "—"
            end_str = end.strftime("%H:%M") if end else "—"
            if start and end:
                delta = (end - start).total_seconds() / 3600.0
                hours_str = f"{delta:.1f}h"
            else:
                hours_str = "—"
            rows.append({
                "Date": date_str,
                "In": start_str,
                "Out": end_str,
                "Hours": hours_str,
            })

        import pandas as pd
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        total_hours = sum(float(r["Hours"].replace("h", "")) for r in rows if r["Hours"] != "—")
        days_with_punch = len(rows)
        avg_hours = total_hours / days_with_punch if days_with_punch > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Hours", f"{total_hours:.1f}h")
        c2.metric("Days Worked", days_with_punch)
        c3.metric("Avg Hours/Day", f"{avg_hours:.1f}h")

    st.caption("⏱️ Uses `shift_rosters` with `crew_name='Clock'`. Open punches have `shift_end='9999-12-31 23:59:59'`.")
