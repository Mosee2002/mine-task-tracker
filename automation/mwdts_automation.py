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
# Translations — self-contained, not shared with app.py's auto_t()
# ---------------------------------------------------------------
# This script has no Streamlit runtime and no session state, so it
# can't call app.py's auto_t() directly — that function depends on
# st.session_state and is designed to translate an unbounded, ever-
# growing set of UI strings via a live AI call, which is the right
# tool for app.py's hundreds of strings but overkill (and a new,
# unnecessary dependency) for the handful of message templates this
# script actually sends. Hand-writing these ~26 fragments instead
# keeps this script exactly as dependency-free and reliable as its
# own module docstring promises ("requests and stdlib only") — no
# AI-provider credentials, no network call beyond what's already
# needed, no risk of a translation service being unavailable at 2am
# when the cron fires.
#
# Twi (tw) and Fante (fat) are given the same text — same approach
# used in app.py, both being Akan-family languages this app doesn't
# have separately fluent coverage for; technical terms are kept in
# English with the local gloss around them, same convention app.py
# uses for exactly this reason.
AUTOMATION_TRANSLATIONS = {
    "en": {
        "weather.headline_alert": "⛈️ Hazardous weather forecast",
        "weather.headline_routine": "🌤️ Site weather outlook",
        "weather.lead_hazard": "Conditions crossing hazard thresholds on: {0}",
        "weather.col_date": "Date", "weather.col_rain": "Rain",
        "weather.col_wind": "Wind", "weather.col_temp": "Temp",
        "weather.rain_suffix": "% rain", "weather.wind_suffix": "km/h wind",
        "weather.open_mwdts": "Open MWDTS",
        "weather.subject_alert": "⛈️ MWDTS Weather Alert — hazardous conditions forecast",
        "weather.subject_routine": "🌤️ MWDTS Weather Outlook",
        "esc.overdue_intro": "{0} task(s) are now overdue:",
        "esc.no_location": "no location", "esc.unassigned": "unassigned",
        "esc.subject_overdue": "⚠️ {0} Overdue Task(s)",
        "esc.open_task_dashboard": "Open MWDTS → Task Dashboard",
        "esc.permit_default": "permit",
        "esc.permit_intro": "{0} permit(s) you issued expire within the hour:",
        "esc.permit_action": "Renew, extend, or formally sign the isolation back.",
        "esc.open_permits": "Open MWDTS → Permits",
        "esc.subject_permits": "🔒 {0} Permit(s) Expiring Within the Hour",
        "backup.subject": "💾 MWDTS Automated Backup — {0}",
        "backup.intro": "Automated backup completed.",
        "backup.stats": "{0} tables, {1} rows, {2} MB.",
        "backup.note": ("Point-in-time snapshot for disaster recovery. Restoring is a manual "
                        "process (re-inserting the JSON via the Supabase SQL editor or API), "
                        "not one-click."),
    },
    "fr": {
        "weather.headline_alert": "⛈️ Prévisions météo dangereuses",
        "weather.headline_routine": "🌤️ Bulletin météo du site",
        "weather.lead_hazard": "Conditions dépassant les seuils de danger le : {0}",
        "weather.col_date": "Date", "weather.col_rain": "Pluie",
        "weather.col_wind": "Vent", "weather.col_temp": "Temp.",
        "weather.rain_suffix": "% de pluie", "weather.wind_suffix": "km/h de vent",
        "weather.open_mwdts": "Ouvrir MWDTS",
        "weather.subject_alert": "⛈️ Alerte météo MWDTS — conditions dangereuses prévues",
        "weather.subject_routine": "🌤️ Bulletin météo MWDTS",
        "esc.overdue_intro": "{0} tâche(s) sont maintenant en retard :",
        "esc.no_location": "aucun emplacement", "esc.unassigned": "non assigné",
        "esc.subject_overdue": "⚠️ {0} tâche(s) en retard",
        "esc.open_task_dashboard": "Ouvrir MWDTS → Tableau de bord des tâches",
        "esc.permit_default": "permis",
        "esc.permit_intro": "{0} permis que vous avez délivré(s) expirent dans l'heure :",
        "esc.permit_action": "Renouvelez, prolongez ou signez formellement la remise en service de l'isolement.",
        "esc.open_permits": "Ouvrir MWDTS → Permis",
        "esc.subject_permits": "🔒 {0} permis expirant dans l'heure",
        "backup.subject": "💾 Sauvegarde automatique MWDTS — {0}",
        "backup.intro": "Sauvegarde automatique terminée.",
        "backup.stats": "{0} tables, {1} lignes, {2} Mo.",
        "backup.note": ("Instantané à un moment donné pour la reprise après sinistre. La "
                        "restauration est un processus manuel (réinsertion du JSON via "
                        "l'éditeur SQL ou l'API Supabase), pas en un clic."),
    },
    "es": {
        "weather.headline_alert": "⛈️ Pronóstico de clima peligroso",
        "weather.headline_routine": "🌤️ Perspectiva meteorológica del sitio",
        "weather.lead_hazard": "Condiciones que superan los umbrales de riesgo el: {0}",
        "weather.col_date": "Fecha", "weather.col_rain": "Lluvia",
        "weather.col_wind": "Viento", "weather.col_temp": "Temp.",
        "weather.rain_suffix": "% de lluvia", "weather.wind_suffix": "km/h de viento",
        "weather.open_mwdts": "Abrir MWDTS",
        "weather.subject_alert": "⛈️ Alerta meteorológica MWDTS — condiciones peligrosas previstas",
        "weather.subject_routine": "🌤️ Perspectiva meteorológica MWDTS",
        "esc.overdue_intro": "{0} tarea(s) están ahora atrasadas:",
        "esc.no_location": "sin ubicación", "esc.unassigned": "sin asignar",
        "esc.subject_overdue": "⚠️ {0} tarea(s) atrasada(s)",
        "esc.open_task_dashboard": "Abrir MWDTS → Panel de Tareas",
        "esc.permit_default": "permiso",
        "esc.permit_intro": "{0} permiso(s) que usted emitió vencen dentro de la hora:",
        "esc.permit_action": "Renueve, prorrogue o firme formalmente el restablecimiento del aislamiento.",
        "esc.open_permits": "Abrir MWDTS → Permisos",
        "esc.subject_permits": "🔒 {0} permiso(s) que vencen dentro de la hora",
        "backup.subject": "💾 Copia de seguridad automática de MWDTS — {0}",
        "backup.intro": "Copia de seguridad automática completada.",
        "backup.stats": "{0} tablas, {1} filas, {2} MB.",
        "backup.note": ("Instantánea puntual para recuperación ante desastres. Restaurar es un "
                        "proceso manual (reinsertando el JSON mediante el editor SQL o la API "
                        "de Supabase), no de un clic."),
    },
    "pt": {
        "weather.headline_alert": "⛈️ Previsão de clima perigoso",
        "weather.headline_routine": "🌤️ Perspectiva do tempo no local",
        "weather.lead_hazard": "Condições que ultrapassam os limites de risco em: {0}",
        "weather.col_date": "Data", "weather.col_rain": "Chuva",
        "weather.col_wind": "Vento", "weather.col_temp": "Temp.",
        "weather.rain_suffix": "% de chuva", "weather.wind_suffix": "km/h de vento",
        "weather.open_mwdts": "Abrir MWDTS",
        "weather.subject_alert": "⛈️ Alerta meteorológico MWDTS — condições perigosas previstas",
        "weather.subject_routine": "🌤️ Perspectiva do tempo MWDTS",
        "esc.overdue_intro": "{0} tarefa(s) estão agora atrasadas:",
        "esc.no_location": "sem localização", "esc.unassigned": "não atribuído",
        "esc.subject_overdue": "⚠️ {0} tarefa(s) atrasada(s)",
        "esc.open_task_dashboard": "Abrir MWDTS → Painel de Tarefas",
        "esc.permit_default": "licença",
        "esc.permit_intro": "{0} licença(s) que você emitiu expiram dentro de uma hora:",
        "esc.permit_action": "Renove, prorrogue ou assine formalmente o retorno do isolamento.",
        "esc.open_permits": "Abrir MWDTS → Licenças",
        "esc.subject_permits": "🔒 {0} licença(s) expirando dentro de uma hora",
        "backup.subject": "💾 Backup automático do MWDTS — {0}",
        "backup.intro": "Backup automático concluído.",
        "backup.stats": "{0} tabelas, {1} linhas, {2} MB.",
        "backup.note": ("Instantâneo pontual para recuperação de desastres. A restauração é um "
                        "processo manual (reinserindo o JSON pelo editor SQL ou API do "
                        "Supabase), não é de um clique."),
    },
    "zh": {
        "weather.headline_alert": "⛈️ 恶劣天气预警",
        "weather.headline_routine": "🌤️ 现场天气展望",
        "weather.lead_hazard": "以下日期天气达到危险阈值：{0}",
        "weather.col_date": "日期", "weather.col_rain": "降雨",
        "weather.col_wind": "风速", "weather.col_temp": "气温",
        "weather.rain_suffix": "% 降雨概率", "weather.wind_suffix": "公里/小时风速",
        "weather.open_mwdts": "打开 MWDTS",
        "weather.subject_alert": "⛈️ MWDTS 天气预警 — 预计有恶劣天气",
        "weather.subject_routine": "🌤️ MWDTS 天气展望",
        "esc.overdue_intro": "{0} 项任务现已逾期：",
        "esc.no_location": "无位置信息", "esc.unassigned": "未分配",
        "esc.subject_overdue": "⚠️ {0} 项逾期任务",
        "esc.open_task_dashboard": "打开 MWDTS → 任务看板",
        "esc.permit_default": "许可证",
        "esc.permit_intro": "您签发的 {0} 份许可证将在一小时内到期：",
        "esc.permit_action": "请续期、延长或正式签回隔离。",
        "esc.open_permits": "打开 MWDTS → 许可证",
        "esc.subject_permits": "🔒 {0} 份许可证将在一小时内到期",
        "backup.subject": "💾 MWDTS 自动备份 — {0}",
        "backup.intro": "自动备份已完成。",
        "backup.stats": "{0} 个表，{1} 行，{2} MB。",
        "backup.note": "用于灾难恢复的时间点快照。恢复是手动过程（通过 Supabase SQL 编辑器或 API 重新插入 JSON），并非一键完成。",
    },
    "hi": {
        "weather.headline_alert": "⛈️ खतरनाक मौसम का पूर्वानुमान",
        "weather.headline_routine": "🌤️ साइट मौसम पूर्वानुमान",
        "weather.lead_hazard": "इन तारीखों पर स्थितियां खतरे की सीमा पार कर रही हैं: {0}",
        "weather.col_date": "तारीख", "weather.col_rain": "बारिश",
        "weather.col_wind": "हवा", "weather.col_temp": "तापमान",
        "weather.rain_suffix": "% बारिश की संभावना", "weather.wind_suffix": "किमी/घंटा हवा",
        "weather.open_mwdts": "MWDTS खोलें",
        "weather.subject_alert": "⛈️ MWDTS मौसम चेतावनी — खतरनाक स्थितियों का पूर्वानुमान",
        "weather.subject_routine": "🌤️ MWDTS मौसम पूर्वानुमान",
        "esc.overdue_intro": "{0} कार्य अब समय सीमा पार कर चुके हैं:",
        "esc.no_location": "कोई स्थान नहीं", "esc.unassigned": "असाइन नहीं किया गया",
        "esc.subject_overdue": "⚠️ {0} समय-सीमा पार कार्य",
        "esc.open_task_dashboard": "MWDTS → टास्क डैशबोर्ड खोलें",
        "esc.permit_default": "परमिट",
        "esc.permit_intro": "आपके द्वारा जारी {0} परमिट एक घंटे के भीतर समाप्त हो रहे हैं:",
        "esc.permit_action": "आइसोलेशन को नवीनीकृत करें, बढ़ाएं, या औपचारिक रूप से वापस साइन करें।",
        "esc.open_permits": "MWDTS → परमिट खोलें",
        "esc.subject_permits": "🔒 {0} परमिट एक घंटे के भीतर समाप्त हो रहे हैं",
        "backup.subject": "💾 MWDTS स्वचालित बैकअप — {0}",
        "backup.intro": "स्वचालित बैकअप पूरा हुआ।",
        "backup.stats": "{0} टेबल, {1} पंक्तियाँ, {2} MB।",
        "backup.note": ("आपदा पुनर्प्राप्ति के लिए एक निश्चित समय का स्नैपशॉट। पुनर्स्थापना एक मैन्युअल "
                        "प्रक्रिया है (Supabase SQL एडिटर या API के माध्यम से JSON को फिर से डालना), "
                        "एक-क्लिक नहीं।"),
    },
    "tw": {
        "weather.headline_alert": "⛈️ Ewiem Tebea a Ɛyɛ Hu (Hazardous Weather Forecast)",
        "weather.headline_routine": "🌤️ Beaeɛ Ewiem Tebea (Site Weather Outlook)",
        "weather.lead_hazard": "Tebea a ɛtra amanehunu ano wɔ: {0}",
        "weather.col_date": "Da", "weather.col_rain": "Osu",
        "weather.col_wind": "Mframa", "weather.col_temp": "Ɔhyew",
        "weather.rain_suffix": "% osu", "weather.wind_suffix": "km/h mframa",
        "weather.open_mwdts": "Bue MWDTS",
        "weather.subject_alert": "⛈️ MWDTS Ewiem Kɔkɔbɔ (Weather Alert) — Tebea a ɛyɛ hu",
        "weather.subject_routine": "🌤️ MWDTS Ewiem Tebea",
        "esc.overdue_intro": "Adwuma {0} aka akyi (overdue) seesei:",
        "esc.no_location": "beaeɛ biara nni ho", "esc.unassigned": "obiara nni ho (unassigned)",
        "esc.subject_overdue": "⚠️ Adwuma {0} a aka akyi",
        "esc.open_task_dashboard": "Bue MWDTS → Adwuma Krataa (Task Dashboard)",
        "esc.permit_default": "permit (kwan)",
        "esc.permit_intro": "Permit {0} a wode maae no bɛba awiei dɔnhwerew baako mu:",
        "esc.permit_action": "Foa (renew), tenten (extend), anaa fa wo nsa hyɛ ho (sign back) permit no.",
        "esc.open_permits": "Bue MWDTS → Permits",
        "esc.subject_permits": "🔒 Permit {0} a ɛbɛba awiei dɔnhwerew baako mu",
        "backup.subject": "💾 MWDTS Backup a Ɛba Ankasa (Automated) — {0}",
        "backup.intro": "Backup a ɛba ankasa (automated) awie.",
        "backup.stats": "Table {0}, row {1}, MB {2}.",
        "backup.note": ("Snapshot a wɔde bɛboa berɛ a asɛm bi asi. Sɛ wopɛ sɛ wosan de bɛhyɛ mu "
                        "a, ɛyɛ adeɛ a wo ara wobɛyɛ (via Supabase SQL editor anaa API), ɛnyɛ "
                        "ade a ɛbɛba wɔ ɔkyerɛ baako mu."),
    },
}
AUTOMATION_TRANSLATIONS["fat"] = AUTOMATION_TRANSLATIONS["tw"]


def t(key, lang, *args):
    """Local translation lookup — English fallback if lang or key is
    missing, same fail-safe shape as app.py's t(), so an unrecognized
    or unset preferred_language never breaks a send, just shows
    English."""
    template = AUTOMATION_TRANSLATIONS.get(lang, {}).get(key) or AUTOMATION_TRANSLATIONS["en"].get(key) or key
    return template.format(*args) if args else template


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


def weather_body(forecast, bad_days, is_alert, lang="en"):
    rows = "".join(
        f"<tr><td style='padding:6px 10px;'>{d.get('date')}</td>"
        f"<td style='padding:6px 10px;'>{d.get('precip_probability_pct', '?')}{t('weather.rain_suffix', lang)}</td>"
        f"<td style='padding:6px 10px;'>{d.get('wind_speed_max_kmh', '?')} {t('weather.wind_suffix', lang)}</td>"
        f"<td style='padding:6px 10px;'>{d.get('temp_min_c', '?')}–{d.get('temp_max_c', '?')}°C</td></tr>"
        for d in forecast[:7])
    headline = t("weather.headline_alert", lang) if is_alert else t("weather.headline_routine", lang)
    lead = ("<p style='color:#b45309;'><strong>"
            + t("weather.lead_hazard", lang, ", ".join(d["date"] for d in bad_days))
            + "</strong></p>") if bad_days else ""
    return (f"<h2>{headline}</h2>{lead}"
            f"<table style='border-collapse:collapse;'>"
            f"<tr><th style='padding:6px 10px;text-align:left;'>{t('weather.col_date', lang)}</th>"
            f"<th style='padding:6px 10px;text-align:left;'>{t('weather.col_rain', lang)}</th>"
            f"<th style='padding:6px 10px;text-align:left;'>{t('weather.col_wind', lang)}</th>"
            f"<th style='padding:6px 10px;text-align:left;'>{t('weather.col_temp', lang)}</th></tr>{rows}</table>"
            + (f"<p><a href='{APP_URL}'>{t('weather.open_mwdts', lang)}</a></p>" if APP_URL else ""))


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

    # Each recipient's OWN preferred_language, not one language for
    # the whole batch — same reasoning as app.py's per-recipient
    # weather email rewrite: different leadership members can have
    # different saved preferences.
    sent = 0
    for u in recipients:
        _lang = u.get("preferred_language") or "en"
        _subject = t("weather.subject_alert", _lang) if alert_type == "bad_weather" else t("weather.subject_routine", _lang)
        _html = weather_body(forecast, bad_days, alert_type == "bad_weather", lang=_lang)
        if send_email(real_email(u), _subject, _html)[0]:
            sent += 1
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

    overdue = [task for task in tasks
               if task.get("status") not in ("Complete", "Blocked", "Closed", "Cancelled")
               and (parse_dt(task.get("due_date")) or datetime.max) < now]

    sent_overdue = 0
    if overdue and supers:
        for u in supers:
            _lang = u.get("preferred_language") or "en"
            _no_location = t("esc.no_location", _lang)
            _unassigned = t("esc.unassigned", _lang)
            rows = "".join(
                f"<li>#{task.get('id')} {task.get('title', '')} — {task.get('location') or _no_location}"
                f" ({task.get('assigned_to') or _unassigned})</li>" for task in overdue)
            html = (f"<p>{t('esc.overdue_intro', _lang, len(overdue))}</p><ul>{rows}</ul>"
                    + (f"<p><a href='{APP_URL}'>{t('esc.open_task_dashboard', _lang)}</a></p>" if APP_URL else ""))
            if send_email(real_email(u), t("esc.subject_overdue", _lang, len(overdue)), html)[0]:
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

    user_by_name = {u.get("full_name"): u for u in users}
    sent_permits = 0
    for issuer, plist in by_issuer.items():
        _issuer_user = user_by_name.get(issuer)
        addr = real_email(_issuer_user)
        if not addr:
            continue
        _lang = (_issuer_user or {}).get("preferred_language") or "en"
        _permit_default = t("esc.permit_default", _lang)
        rows = "".join(
            f"<li>#{p.get('id')} — {p.get('permit_type') or _permit_default}, "
            f"lock/tag {p.get('lock_tag_numbers') or '—'}</li>" for p in plist)
        html = (f"<p>{t('esc.permit_intro', _lang, len(plist))}</p><ul>{rows}</ul>"
                f"<p>{t('esc.permit_action', _lang)}</p>"
                + (f"<p><a href='{APP_URL}'>{t('esc.open_permits', _lang)}</a></p>" if APP_URL else ""))
        if send_email(addr, t("esc.subject_permits", _lang, len(plist)), html)[0]:
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
    _lang = (owner or {}).get("preferred_language") or "en"
    ok, err = send_email(
        addr, t("backup.subject", _lang, date_str),
        f"<p>{t('backup.intro', _lang)}</p>"
        f"<p>{t('backup.stats', _lang, len(counts), f'{sum(counts.values()):,}', f'{size_mb:.1f}')}</p>"
        f"<p>{t('backup.note', _lang)}</p>",
        attachment_bytes=data, attachment_filename=f"mwdts_backup_{date_str}.zip")
    return {"ok": ok, "error": err or None, "tables": len(counts),
            "total_rows": sum(counts.values()), "size_mb": round(size_mb, 2)}


# ---------------------------------------------------------------
def preflight(command):
    """Names exactly which secrets are missing, up front.

    Without this, a missing secret surfaces as a confusing downstream
    symptom instead of a cause — no SUPABASE_KEY looks like "every
    table is empty", and no SMTP_PASSWORD looks like "0 emails sent"
    with no reason given. Only the genuinely required ones for the
    requested command are checked: MINE_LATITUDE matters for weather
    and not for backup, and APP_URL is only a convenience link.
    """
    missing = []
    for name, value in (("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_KEY", SUPABASE_KEY)):
        if not value:
            missing.append(name)
    for name, value in (("SMTP_SERVER", SMTP_SERVER), ("SMTP_USER", SMTP_USER),
                        ("SMTP_PASSWORD", SMTP_PASSWORD)):
        if not value:
            missing.append(name)
    if command == "weather" and not (MINE_LATITUDE and MINE_LONGITUDE):
        missing.append("MINE_LATITUDE/MINE_LONGITUDE")
    if command == "backup" and not OWNER_USERNAME:
        missing.append("OWNER_USERNAME")
    return missing


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("weather", "escalations", "backup"):
        print("usage: mwdts_automation.py {weather|escalations|backup}", file=sys.stderr)
        return 2

    command = sys.argv[1]
    missing = preflight(command)
    if missing:
        print(json.dumps({
            "ok": False,
            "error": "Required repository secrets are not set: " + ", ".join(missing),
            "hint": "Add them under Settings -> Secrets and variables -> Actions. "
                    "SMTP_PORT is optional and defaults to 587.",
        }, indent=2))
        return 1

    result = {"weather": run_weather, "escalations": run_escalations, "backup": run_backup}[command]()
    print(json.dumps(result, indent=2))
    # Non-zero exit on failure so the Actions tab shows red rather than
    # a green run that quietly did nothing.
    return 0 if result.get("ok", False) else 1


if __name__ == "__main__":
    sys.exit(main())
