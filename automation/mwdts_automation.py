#!/usr/bin/env python3
"""
MWDTS scheduled automation — runs OUTSIDE the Streamlit app.

WHY THIS EXISTS
---------------
The original design pointed GitHub Actions at URL endpoints inside the
Streamlit app itself (?weather_check=1, ?run_escalations=1,
?run_backup=1). That approach is dead: Streamlit Community Cloud
intercepts those requests and redirects them to its own login page,
even for an app set to "Public and searchable". Following that
redirect lands in an infinite auth loop (curl exits 47, "too many
redirects"). No User-Agent spoofing or redirect handling gets around
it — it is a platform-level behaviour, not something app code can fix.

So this script does the work directly instead: it talks to Supabase
over its REST API and sends mail over SMTP, with no Streamlit in the
path at all. That also makes it strictly more reliable than the old
approach even if Streamlit later changes its behaviour, because it no
longer depends on the app being awake — a Community Cloud app that
has gone to sleep cannot run a scheduled check either way.

THE HONEST TRADE-OFF
--------------------
The thresholds and cooldown rules below are DUPLICATED from app.py
rather than imported, because app.py is a Streamlit script: importing
it executes the whole UI and requires a Streamlit runtime. That
duplication is a genuine maintenance cost — if you change a threshold
in app.py, change it here too. The constants are grouped together at
the top for exactly that reason, and each notes its app.py
counterpart. This was the lesser evil versus having no working
automation at all.

USAGE
    python mwdts_automation.py weather
    python mwdts_automation.py escalations
    python mwdts_automation.py backup

Every subcommand prints a JSON summary and exits non-zero on failure,
so a failed run shows up red in the GitHub Actions tab rather than
passing silently.
"""

import io
import json
import os
import smtplib
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

# ---------------------------------------------------------------
# Config from environment (set as GitHub Actions repository secrets)
# ---------------------------------------------------------------
def _env(name, default=""):
    """Read an env var, treating EMPTY as absent.

    os.environ.get(name, default) only falls back when the key is
    genuinely missing — but GitHub Actions maps every secret listed in
    the workflow's env: block, so a secret you simply haven't created
    arrives as an empty STRING, not a missing key. The default
    therefore never fires, and int("") raised ValueError at import
    time, before main() could report anything useful. Stripping and
    treating blank as absent is what makes the defaults below actually
    work the way they read.
    """
    value = os.environ.get(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()


SUPABASE_URL = _env("SUPABASE_URL").rstrip("/")
SUPABASE_KEY = _env("SUPABASE_KEY")
SMTP_SERVER = _env("SMTP_SERVER")
try:
    SMTP_PORT = int(_env("SMTP_PORT", "587"))
except ValueError:
    # A non-numeric SMTP_PORT is a typo, not a reason to take the whole
    # run down — 587 is the standard submission port and the same
    # default app.py uses.
    print("  ! SMTP_PORT is not a number; falling back to 587", file=sys.stderr)
    SMTP_PORT = 587
SMTP_USER = _env("SMTP_USER")
SMTP_PASSWORD = _env("SMTP_PASSWORD")
SMTP_FROM = _env("SMTP_FROM") or SMTP_USER
OWNER_USERNAME = _env("OWNER_USERNAME").lower()
MINE_LATITUDE = _env("MINE_LATITUDE")
MINE_LONGITUDE = _env("MINE_LONGITUDE")
APP_URL = _env("APP_URL")

# --- Thresholds mirrored from app.py (see module docstring) ---
# app.py: SEVERE_WEATHER_CODES / BAD_WEATHER_WIND_KMH / BAD_WEATHER_PRECIP_PROB_PCT
SEVERE_WEATHER_CODES = {65, 67, 75, 82, 86, 95, 96, 99}
BAD_WEATHER_WIND_KMH = 50
BAD_WEATHER_PRECIP_PROB_PCT = 70
# app.py: WEATHER_BAD_ALERT_COOLDOWN_HOURS / WEATHER_ROUTINE_COOLDOWN_HOURS
WEATHER_BAD_ALERT_COOLDOWN_HOURS = 6
WEATHER_ROUTINE_COOLDOWN_HOURS = 12
# app.py: BACKUP_TABLES
BACKUP_TABLES = [
    "facility_users", "tasks", "task_comments", "task_activity", "task_attachments",
    "task_photos", "task_parts", "assets", "asset_status_history", "inventory_parts",
    "meter_readings", "suppliers", "purchase_orders", "po_line_items", "boms",
    "incidents", "permits", "contractors", "shift_handovers", "shift_production",
    "shift_rosters", "budgets", "documents", "haulage_shipments", "motor_rewinds",
    "instrument_calibrations", "outage_runbook_templates", "outage_events",
    "transformer_dga_tests", "fault_events", "hv_switching_orders", "relay_setting_records",
    "arc_flash_studies", "technician_certifications", "worker_reports", "audit_log",
    "access_decisions", "app_announcements", "app_feedback", "app_feedback_votes",
    "app_posters", "app_branding", "app_feature_flags", "notifications",
    "push_subscriptions", "chat_messages", "ai_chat_messages", "email_login_codes",
    "translation_cache", "erp_sync_log", "active_sessions", "app_errors",
]

PLACEHOLDER_EMAIL_SUFFIX = "@mwdts.internal"


# ---------------------------------------------------------------
# Supabase REST helpers
# ---------------------------------------------------------------
def _sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def sb_select(table, params=None):
    """GET rows from a table. Returns [] on any failure rather than
    raising — one missing/renamed table must not abort a whole run
    that could still do useful work on the others."""
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}",
                         headers=_sb_headers(),
                         params={"select": "*", **(params or {})},
                         timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  ! select {table} failed: {type(e).__name__}: {e}", file=sys.stderr)
        return []


def sb_insert(table, payload):
    try:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}",
                          headers=_sb_headers(), json=payload, timeout=30)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"  ! insert {table} failed: {type(e).__name__}: {e}", file=sys.stderr)
        return False


def parse_dt(value):
    """Tolerant ISO parser that always returns a NAIVE datetime.

    Supabase returns offset-aware timestamps; comparing those to
    datetime.now() raises TypeError in Python. app.py hit this exact
    bug once and it silently aborted an entire recurring-task pass,
    so everything is normalised to naive local time here up front.
    """
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


# ---------------------------------------------------------------
# Email
# ---------------------------------------------------------------
def send_email(recipient, subject, body_html, attachment_bytes=None, attachment_filename=None):
    if not recipient or not all([SMTP_SERVER, SMTP_USER, SMTP_PASSWORD]):
        return False, "SMTP not configured or no recipient"
    try:
        import re
        plain = re.sub(r"<br\s*/?>", "\n", body_html, flags=re.I)
        plain = re.sub(r"</p>", "\n\n", plain, flags=re.I)
        plain = re.sub(r"<[^>]+>", "", plain)
        plain = re.sub(r"\n{3,}", "\n\n", plain).strip()

        if attachment_bytes and attachment_filename:
            msg = MIMEMultipart("mixed")
            body = MIMEMultipart("alternative")
            body.attach(MIMEText(plain, "plain"))
            body.attach(MIMEText(body_html, "html"))
            msg.attach(body)
            part = MIMEApplication(attachment_bytes, _subtype="zip")
            part.add_header("Content-Disposition", "attachment", filename=attachment_filename)
            msg.attach(part)
        else:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(plain, "plain"))
            msg.attach(MIMEText(body_html, "html"))

        msg["From"] = SMTP_FROM
        msg["To"] = recipient
        msg["Subject"] = subject
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def real_email(user):
    """A usable address — excludes the @mwdts.internal placeholders
    app.py generates for accounts created without a real one."""
    email = (user or {}).get("email")
    if not email or str(email).endswith(PLACEHOLDER_EMAIL_SUFFIX):
        return None
    return email


def active_users():
    return [u for u in sb_select("facility_users")
            if u.get("is_approved") and not u.get("is_suspended")]


def leadership_recipients(users=None):
    """Supervisors, superintendents, and the owner — same audience as
    app.py's site_leadership_recipients()."""
    users = users if users is not None else active_users()
    out = []
    for u in users:
        role = str(u.get("role", "")).strip().lower()
        is_owner = OWNER_USERNAME and str(u.get("username", "")).strip().lower() == OWNER_USERNAME
        if role in ("supervisor", "superintendent") or is_owner:
            if real_email(u):
                out.append(u)
    return out


# ---------------------------------------------------------------
# weather
# ---------------------------------------------------------------
def fetch_forecast():
    """One retry on failure — Open-Meteo's free tier returns spurious
    429s that do not correlate with actual caller volume (confirmed on
    their own issue tracker), so a transient failure shouldn't mean
    skipping a whole check cycle."""
    if not MINE_LATITUDE or not MINE_LONGITUDE:
        return []
    import time
    for attempt in range(2):
        try:
            r = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": MINE_LATITUDE, "longitude": MINE_LONGITUDE,
                "daily": ("precipitation_sum,precipitation_probability_max,"
                          "windspeed_10m_max,temperature_2m_max,temperature_2m_min,weathercode"),
                "forecast_days": 7, "timezone": "auto",
            }, timeout=20)
            if r.status_code == 429 and attempt == 0:
                time.sleep(5)
                continue
            r.raise_for_status()
            d = r.json().get("daily", {})
            dates = d.get("time", [])
            return [{
                "date": day,
                "precip_mm": (d.get("precipitation_sum") or [None] * len(dates))[i],
                "precip_probability_pct": (d.get("precipitation_probability_max") or [None] * len(dates))[i],
                "wind_speed_max_kmh": (d.get("windspeed_10m_max") or [None] * len(dates))[i],
                "temp_max_c": (d.get("temperature_2m_max") or [None] * len(dates))[i],
                "temp_min_c": (d.get("temperature_2m_min") or [None] * len(dates))[i],
                "weather_code": (d.get("weathercode") or [None] * len(dates))[i],
            } for i, day in enumerate(dates)]
        except Exception as e:
            print(f"  ! forecast attempt {attempt + 1} failed: {e}", file=sys.stderr)
    return []


def is_bad_weather_day(day):
    if not day:
        return False
    if (day.get("precip_probability_pct") or 0) >= BAD_WEATHER_PRECIP_PROB_PCT:
        return True
    if (day.get("wind_speed_max_kmh") or 0) >= BAD_WEATHER_WIND_KMH:
        return True
    return day.get("weather_code") in SEVERE_WEATHER_CODES


def weather_last_sent(alert_type):
    rows = sb_select("weather_alert_log", {
        "alert_type": f"eq.{alert_type}", "order": "sent_at.desc", "limit": "1",
    })
    return parse_dt(rows[0]["sent_at"]) if rows else None


def weather_body(forecast, bad_days, is_alert):
    rows = "".join(
        f"<tr><td style='padding:6px 10px;'>{d.get('date')}</td>"
        f"<td style='padding:6px 10px;'>{d.get('precip_probability_pct', '?')}% rain</td>"
        f"<td style='padding:6px 10px;'>{d.get('wind_speed_max_kmh', '?')} km/h wind</td>"
        f"<td style='padding:6px 10px;'>{d.get('temp_min_c', '?')}–{d.get('temp_max_c', '?')}°C</td></tr>"
        for d in forecast[:7])
    headline = ("⛈️ Hazardous weather forecast" if is_alert else "🌤️ Site weather outlook")
    lead = ("<p style='color:#b45309;'><strong>Conditions crossing hazard thresholds on: "
            + ", ".join(d["date"] for d in bad_days) + "</strong></p>") if bad_days else ""
    return (f"<h2>{headline}</h2>{lead}"
            f"<table style='border-collapse:collapse;'>"
            f"<tr><th style='padding:6px 10px;text-align:left;'>Date</th>"
            f"<th style='padding:6px 10px;text-align:left;'>Rain</th>"
            f"<th style='padding:6px 10px;text-align:left;'>Wind</th>"
            f"<th style='padding:6px 10px;text-align:left;'>Temp</th></tr>{rows}</table>"
            + (f"<p><a href='{APP_URL}'>Open MWDTS</a></p>" if APP_URL else ""))


def run_weather():
    forecast = fetch_forecast()
    if not forecast:
        return {"ok": True, "sent": 0, "reason": "No forecast available (API unreachable or lat/long unset)."}

    bad_days = [d for d in forecast[:3] if is_bad_weather_day(d)]
    now = datetime.now()
    recipients = leadership_recipients()
    if not recipients:
        return {"ok": True, "sent": 0, "reason": "No leadership recipients with a real email."}

    alert_type, due = None, False
    if bad_days:
        last = weather_last_sent("bad_weather")
        if not last or (now - last) >= timedelta(hours=WEATHER_BAD_ALERT_COOLDOWN_HOURS):
            alert_type, due = "bad_weather", True
    if not due:
        last = weather_last_sent("routine")
        if not last or (now - last) >= timedelta(hours=WEATHER_ROUTINE_COOLDOWN_HOURS):
            alert_type, due = "routine", True
    if not due:
        return {"ok": True, "sent": 0, "reason": "Within cooldown — nothing due yet."}

    subject = ("⛈️ MWDTS Weather Alert — hazardous conditions forecast"
               if alert_type == "bad_weather" else "🌤️ MWDTS Weather Outlook")
    html = weather_body(forecast, bad_days, alert_type == "bad_weather")
    sent = sum(1 for u in recipients if send_email(real_email(u), subject, html)[0])
    sb_insert("weather_alert_log", {
        "alert_type": alert_type, "recipient_count": len(recipients), "sent_count": sent,
    })
    return {"ok": sent > 0, "sent": sent, "recipients": len(recipients),
            "alert_type": alert_type, "bad_days": [d["date"] for d in bad_days]}


# ---------------------------------------------------------------
# escalations
# ---------------------------------------------------------------
def run_escalations():
    now = datetime.now()
    users = active_users()
    tasks = sb_select("tasks")
    permits = sb_select("permits")

    supers = [u for u in users
              if str(u.get("role", "")).strip().lower() == "superintendent" and real_email(u)]

    overdue = [t for t in tasks
               if t.get("status") not in ("Complete", "Blocked", "Closed", "Cancelled")
               and (parse_dt(t.get("due_date")) or datetime.max) < now]

    sent_overdue = 0
    if overdue and supers:
        rows = "".join(
            f"<li>#{t.get('id')} {t.get('title', '')} — {t.get('location') or 'no location'}"
            f" ({t.get('assigned_to') or 'unassigned'})</li>" for t in overdue)
        html = (f"<p>{len(overdue)} task(s) are now overdue:</p><ul>{rows}</ul>"
                + (f"<p><a href='{APP_URL}'>Open MWDTS → Task Dashboard</a></p>" if APP_URL else ""))
        for u in supers:
            if send_email(real_email(u), f"⚠️ {len(overdue)} Overdue Task(s)", html)[0]:
                sent_overdue += 1

    # Permits expiring within the hour, grouped per issuer so one
    # person gets one email listing all of theirs, not one per permit.
    soon = now + timedelta(hours=1)
    by_issuer = {}
    for p in permits:
        if p.get("status") not in ("Active", "Issued"):
            continue
        vu = parse_dt(p.get("valid_until"))
        if vu and now < vu < soon:
            by_issuer.setdefault(p.get("issued_by"), []).append(p)

    email_by_name = {u.get("full_name"): real_email(u) for u in users}
    sent_permits = 0
    for issuer, plist in by_issuer.items():
        addr = email_by_name.get(issuer)
        if not addr:
            continue
        rows = "".join(
            f"<li>#{p.get('id')} — {p.get('permit_type') or 'permit'}, "
            f"lock/tag {p.get('lock_tag_numbers') or '—'}</li>" for p in plist)
        html = (f"<p>{len(plist)} permit(s) you issued expire within the hour:</p><ul>{rows}</ul>"
                f"<p>Renew, extend, or formally sign the isolation back.</p>"
                + (f"<p><a href='{APP_URL}'>Open MWDTS → Permits</a></p>" if APP_URL else ""))
        if send_email(addr, f"🔒 {len(plist)} Permit(s) Expiring Within the Hour", html)[0]:
            sent_permits += 1

    return {"ok": True, "overdue_tasks": len(overdue), "overdue_emails_sent": sent_overdue,
            "permits_expiring": sum(len(v) for v in by_issuer.values()),
            "permit_emails_sent": sent_permits}


# ---------------------------------------------------------------
# backup
# ---------------------------------------------------------------
def run_backup():
    buf = io.BytesIO()
    counts = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for table in BACKUP_TABLES:
            rows = sb_select(table)
            if not rows:
                continue
            counts[table] = len(rows)
            zf.writestr(f"{table}.json", json.dumps(rows, indent=2, default=str))
        zf.writestr("_manifest.json", json.dumps({
            "generated_at": datetime.now().isoformat(),
            "tables": counts,
            "total_rows": sum(counts.values()),
        }, indent=2))

    if not counts:
        return {"ok": False, "error": "Backup produced no data — check SUPABASE_URL/SUPABASE_KEY."}

    owner = next((u for u in sb_select("facility_users")
                  if str(u.get("username", "")).strip().lower() == OWNER_USERNAME), None)
    addr = real_email(owner)
    if not addr:
        return {"ok": False, "error": "Owner has no usable email on file.",
                "tables": len(counts), "total_rows": sum(counts.values())}

    data = buf.getvalue()
    size_mb = len(data) / (1024 * 1024)
    date_str = datetime.now().strftime("%Y-%m-%d")
    ok, err = send_email(
        addr, f"💾 MWDTS Automated Backup — {date_str}",
        f"<p>Automated backup completed.</p>"
        f"<p>{len(counts)} tables, {sum(counts.values()):,} rows, {size_mb:.1f} MB.</p>"
        f"<p>Point-in-time snapshot for disaster recovery. Restoring is a manual process "
        f"(re-inserting the JSON via the Supabase SQL editor or API), not one-click.</p>",
        attachment_bytes=data, attachment_filename=f"mwdts_backup_{date_str}.zip")
    return {"ok": ok, "error": err or None, "tables": len(counts),
            "total_rows": sum(counts.values()), "size_mb": round(size_mb, 2)}


# ---------------------------------------------------------------
def preflight(command):
    """Names exactly which secrets are missing, up front.

    Without this, a missing secret surfaces as a confusing downstream
    symptom instead of a cause — no SUPABASE_KEY looks like "every
    tab
