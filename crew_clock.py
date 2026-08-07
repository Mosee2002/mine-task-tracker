# crew_clock.py (DEBUG VERSION – prints payload to terminal)
import streamlit as st
from datetime import datetime, timedelta
import sys
import json

# ----- SENTINEL for open shifts -----
OPEN_SHIFT_SENTINEL = datetime.max.isoformat()  # "9999-12-31 23:59:59.999999"

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
    supabase = _get_supabase()
    now = datetime.now().isoformat()

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

    # ----- BUILD PAYLOAD -----
    payload = {
        "username": username,
        "shift_start": now,
        "shift_end": OPEN_SHIFT_SENTINEL,   # <<-- This is a valid timestamp!
        "crew_name": "Clock",
        "assigned_by": username
    }

    # ----- DEBUG: Print to terminal so you can see it -----
    print(f"🔍 DEBUG: Inserting into shift_rosters:", file=sys.stderr)
    print(json.dumps(payload, indent=2), file=sys.stderr)

    try:
        res = supabase.table("shift_rosters").insert(payload).execute()
        if res.data:
            return True, "✅ Punched in successfully!"
        else:
            return False, f"Insert returned no data. Response: {res}"
    except Exception as e:
        # Print the full exception to terminal
        print(f"❌ ERROR: {e}", file=sys.stderr)
        return False, f"Punch-in failed: {e}"

def punch_out(username):
    supabase = _get_supabase()
    now = datetime.now().isoformat()

    if not supabase:
        punches = st.session_state.get("crew_clock_memory", [])
        for p in punches:
            if p.get("username") == username and p.get("shift_end") == OPEN_SHIFT_SENTINEL:
                p["shift_end"] = now
                return True, "Punched out (memory mode)"
        return False, "No open punch found"

    try:
        open_punch = get_open_punch(username)
        if not open_punch:
            return False, "You don't have an open punch to close."

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
    supabase = _get_supabase()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    if not supabase:
        punches = st.session_state.get("crew_clock_memory", [])
        return [p for p in punches if p.get("username") == username and p.get("shift_end") != OPEN_SHIFT_SENTINEL]

    try:
        res = supabase.table("shift_rosters") \
            .select("*") \
            .eq("username", username) \
            .eq("crew_name", "Clock") \
            .ne("shift_end", OPEN_SHIFT_SENTINEL) \
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
            if st.button("⏹️ Punch Out", use_container_width=True, type="primary"):
                ok, msg = punch_out(username)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
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

    st.caption("⏱️ Debug version – check your terminal for the exact SQL payload.")
