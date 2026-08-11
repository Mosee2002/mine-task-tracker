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

# Five standalone feature modules, each a separate file alongside
# app.py. Wrapped defensively — a missing or broken module file must
# degrade to that one section showing an "unavailable" message, not
# crash the entire app for every user, the same principle already
# applied to every other optional dependency here (plotly, reportlab,
# pywebpush, etc.).
try:
    import wallboard
    WALLBOARD_MODULE_AVAILABLE = True
except Exception:
    WALLBOARD_MODULE_AVAILABLE = False
try:
    import crew_clock
    CREW_CLOCK_MODULE_AVAILABLE = True
except Exception:
    CREW_CLOCK_MODULE_AVAILABLE = False
try:
    import jsa_library
    JSA_LIBRARY_MODULE_AVAILABLE = True
except Exception:
    JSA_LIBRARY_MODULE_AVAILABLE = False
try:
    import job_plans
    JOB_PLANS_MODULE_AVAILABLE = True
except Exception:
    JOB_PLANS_MODULE_AVAILABLE = False
try:
    import location_hierarchy
    LOCATION_HIERARCHY_MODULE_AVAILABLE = True
except Exception:
    LOCATION_HIERARCHY_MODULE_AVAILABLE = False
import re
import secrets
from io import BytesIO

# ----- ESCAPE FUNCTION (prevents XSS) -----
def esc(text):
    if text is None:
        return ""
    return html_lib.escape(str(text), quote=True)

# ----- ALLOWED FILE EXTENSIONS FOR ATTACHMENTS -----
ALLOWED_ATTACHMENT_EXTENSIONS = [
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt',
    'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'
]

# Optional: try to import pandas and plotly for dashboard charts
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

# Shared chart color sequence — every other element in this app (badges,
# Every chart in the app uses this instead of Plotly's default blue/
# orange/green palette — without it, charts are the one part of the
# interface with zero connection to the navy/lime identity used
# everywhere else (headers, badges, cards, buttons). Navy and lime
# lead since they're the actual brand colors; the rest are harmonious
# extensions for categories beyond the first two, not arbitrary.
GMC_CHART_COLORS = ["#001530", "#b9c901", "#0f3460", "#7c9c02",
                    "#3b5f8a", "#5a7a01", "#94a3b8", "#dc2626"]

# Company KPI targets — kept as named constants in one place rather
# than scattered magic numbers, so a future target change is a
# one-line edit here, not a hunt through the Executive Dashboard code.
KPI_MONTHLY_PRODUCTION_TONNES = 700_000
KPI_ANNUAL_PRODUCTION_TONNES = 8_000_000
KPI_EQUIPMENT_AVAILABILITY_PCT = 85
KPI_ORE_GRADE_BASELINE_PCT = 27
KPI_ORE_GRADE_TARGET_PCT = 40

# Heights (in px) of the fixed elements stacked at the top of the
# screen — measured from each element's own CSS (padding, line
# heights, image height), not guessed. Three of these four elements
# are conditional (a logo, posters, or announcements may or may not
# be configured), so a hard-coded CSS `top` per element would leave
# an awkward gap whenever one is absent. Instead, each render
# function below returns the height it actually occupied (0 if it
# rendered nothing), and the caller tracks a running offset — these
# constants are the values used when an element DOES render.
LOGO_BAR_HEIGHT = 95  # 0.7rem padding (top+bottom, 22.4px) + 3px top border + 1px bottom
                       # border + 0.8rem margin-bottom (12.8px) + 56px max image height ≈ 95px.
                       # Recalculated against the current CSS when the logo bar became sticky
                       # (this constant was previously unused, and imprecise, when it wasn't).
POSTER_SLIDESHOW_HEIGHT = 236  # 220px image + 16px margin-bottom
TICKER_BAR_HEIGHT = 54         # padding + line height + margin-bottom
MAIN_HEADER_HEIGHT = 115

# OAuth support
try:
    from authlib.integrations.requests_client import OAuth2Session
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False

# Try to import bcrypt; fallback to built-in hashing
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False

# Optional: for image validation
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Optional: QR code generation for asset labels (Print QR Label).
# reportlab is a real, tested QR encoder — same one already proven out
# for the app's own install QR codes — used here only for computing
# the correct module grid; PIL (already available above) does the
# actual image rendering, so this is the one new dependency needed
# for generation specifically.
try:
    from reportlab.graphics.barcode import qr as _qr_encoder
    QR_GENERATION_AVAILABLE = PIL_AVAILABLE
except ImportError:
    QR_GENERATION_AVAILABLE = False

# Optional: PDF report generation (Analytics -> Exports -> PDF Report).
# Same reportlab library as QR generation above, but a different
# submodule (Platypus, for laying out real documents rather than
# encoding a barcode) — checked separately in case one submodule is
# available and the other genuinely isn't, however unlikely.
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors as _rl_colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, PageBreak)
    PDF_REPORT_AVAILABLE = True
except ImportError:
    PDF_REPORT_AVAILABLE = False

# Optional: QR code SCANNING (decoding a photo of a printed label back
# into an asset lookup). opencv-python-headless specifically — the
# headless variant, not the full opencv-python package, since this is
# a server/cloud deployment with no display; the headless build skips
# GUI dependencies neither Streamlit Cloud nor this feature need.
try:
    import cv2
    import numpy as np
    QR_SCANNING_AVAILABLE = True
except ImportError:
    QR_SCANNING_AVAILABLE = False

# Optional: Web Push notifications (real, device-level alerts, not
# just the in-app notifications list). Needs VAPID keys generated
# once and stored as secrets — see PUSH_NOTIFICATIONS_SETUP.md.
try:
    from pywebpush import webpush, WebPushException
    PUSH_AVAILABLE = True
except ImportError:
    PUSH_AVAILABLE = False

# Optional: Google Workspace mailbox auto-provisioning
try:
    from google.oauth2 import service_account as _gws_service_account
    from googleapiclient.discovery import build as _gws_build
    from googleapiclient.errors import HttpError as _gws_HttpError
    GOOGLE_WORKSPACE_LIB_AVAILABLE = True
except ImportError:
    GOOGLE_WORKSPACE_LIB_AVAILABLE = False

# -------------------------------
# 0. PAGE CONFIG  (must be the very first Streamlit command)
# -------------------------------
# This MUST run before any other st.* call. Previously the credential
# warnings fired first, which raises StreamlitAPIException and can
# swallow the real connection error, making every failure look
# identical ("demo mode") regardless of its actual cause.
#
# page_title/page_icon here are what actually shows in the browser
# tab and window title on every normal visit — this is DIFFERENT from
# the PWA manifest (further down), which only applies once someone
# explicitly installs the app as a desktop/home-screen shortcut, and
# even then browsers cache that install metadata aggressively (an
# already-installed shortcut won't pick up a rename just because the
# server redeployed — it needs to be uninstalled and reinstalled).
# If a name/icon change isn't showing up, THIS is the one to check
# first, since it applies immediately with no install or caching step.
_PAGE_ICON_B64 = "iVBORw0KGgoAAAANSUhEUgAAAMAAAADACAYAAABS3GwHAAAFnUlEQVR4nO3dvY7bRhSG4RmBRS5gF5JdWBsgiLdy6Z8gTYoEdpdLTRckVWJv/u4gBmLtugoF30A6pVDkyLJEUdQMz5z53gdQZUCkyfPxzCGlVbx//1EwsLLYKFyIY26sGakSKXj0tVsrWQPRZHxvih4pbNdR8jCkDgBFj5ySh6FJGCqKH2NahQTFm6IDUPiwsqm9wUGYJNoBwNLgOhzaASh8lGZQN2hCPLl7UPwo2UmzwalLIIofHvSu01MCQPHDk1712jcAFD88Olq3fZ4DUPzwrHMmONYBKH7U4GAdn/scAHCt6VgBcfVHTfYuhQ7NABQ/avRRCFgCQdq+L8Rw9UfNPugCux2A4oeC93We8vsAgDvMAJC2HQCWP1CyCqH7OQBQPWYASNssgVj+QNGKIRjSWAJBGh0A0iaB9T+EcRsU0pgBMvr77R/J3uve/Emy98L/4uzBY5ZAA6Us8HMRkGEIQE8lFXtfhOI4AtDBY9EfQhj2i9MHTwjAf9q3v1vvwmhm86fWu1AE+QAoFf0hymGI07lmANo7Cn/X7EovCFIBoOj7UwlDnM6fVh+A9u43611wa3b1zHoXsqo6ABR+OrUGodoPw1H8adV6PKvrALWeqJLU1A3idP6sigC0d79a74Kc2dUX1rtwtiqWQBS/jRqOe5xe+e0A7a3/E1CL2ac+u4HbDkDxl8Xr+Zisvw/g6+X1YNdufV7s6+OUl7sO0N7+Yr0L6ODt/LgKgLeDq8rTeXKzBPJ0ULEJgX3dVLEEam9vrHcBA3g4b5MCQtj58nAQcVh7e2NeQ12vySqs/zBQia92QfHXoF3cmNfSoVexM8CS4q/K+nza19Xuq8gZYLl4Zb0LyKDE81pkAICxFBeAEq8SSKe081vUDFDawUEe6/NsX2/FzgDAWIp5DrBcvMz+n0U5louX5jUXYoEzADCmImaA5Ruu/orW59229ugAkEYAIM08AMs3P1vvAgxZn39+IgkFsKtBfiQP9gxr0HQJtPzrJ8vNoxCWdWA+AwCWmhVrIBTAqg7pAJBGACCN26AohE0dxsvPvnL7x3GBc7EEgjQCAGnMAJBGB4A0AgBpBADSmAEgjY9DQxpLIEgjAJDGDABpdABIIwCQ1vBRUChrQhxvBnj3+sfRtgXfLh9+M8p24sXnX2dvAhQ+hsodhOwB6Cr+b2/+yblpOPLdl58c/LecIcg6BHPlRwo564jnAHAiT51m6wDvXv+Q660hKFc98RwA0ka9DQqcJUOt0gEgjQBAWrYAXF4/z/XWEJSrnrgNCiec3QYNIYTL6xc53x4ictZRvHj4PP9ngf78PvcmUKncF9FRArBBENDXWKuHeHH9gq8EQBZfiIE0ngNAGgGANJ4DQBodANIIAKTxx3EhjRkA0lgCQRoBgDQCAGnMAJBGB4A0AgBpPAeANGYASGMJBGkEANKaFUsgCKMDQBoBgDRug0Iat0EhjSUQpBEASCMAkMYMAGl0AEjjNiik0QEgjRkA0ugAkEYAII0AQBozAKTxE0mQxnMASGMGgDRmAEijA0AaAYA0lkCQRgeANG6DQhodANKYASCNDgBpBADSCACkMQNAGh0A0ngOAGl0AEjjJ5IgjQ4AaQQA0ggApPEcANK4DQppk0ALgDBmAEhjBoA0OgCkbQJAG4CiyBII0rgNCmnbMwBRgJIYAkMwxDEDQNpuByANUPC+zvf9RFIMIfDLSajVBxd5ZgBIOzQD0AVQo4+Kves5ACFATfZWOksgSDsWAO4KoQYH67jPcwCWQvCss8D7LoHoBPDoaN2eMgMQAnjSq15PHYIJATzoXadNiCfXNDMBSnZSQTdnboQgoBSDVifnPgdgSYQSDK7DoR1g38bpBhjb2RfglN8HYDbAmJIUbooOsG17pwgDUku+5E4dgG2EASlknTP/BdPRSAFECwQ8AAAAAElFTkSuQmCC"
_page_icon = "\U0001F6E0\uFE0F"  # hard-hat emoji fallback
if PIL_AVAILABLE:
    try:
        _page_icon = Image.open(BytesIO(base64.b64decode(_PAGE_ICON_B64)))
    except Exception:
        pass  # keep the emoji fallback — a broken tab icon is not worth crashing over

st.set_page_config(
    page_title="MWDTS",
    page_icon=_page_icon,
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------
# 0B. SECRETS AND CONFIG
# -------------------------------
# Startup notices are COLLECTED here and rendered later, so nothing
# competes with set_page_config and no error gets hidden.
_startup_notices = []          # list of (level, message)
_diag = {}                     # structured facts for the diagnostics panel


def _secret_get(key, default=None):
    """Read a secret without exploding when no secrets.toml exists."""
    try:
        return st.secrets[key]
    except Exception:
        return default


# Can st.secrets be read at all?
try:
    _all_secret_keys = list(st.secrets.keys())
    _diag["secrets_readable"] = True
    _diag["secrets_error"] = None
except Exception as _e:
    _all_secret_keys = []
    _diag["secrets_readable"] = False
    _diag["secrets_error"] = f"{type(_e).__name__}: {_e}"
_diag["secret_keys_found"] = sorted(_all_secret_keys)   # NAMES only, never values

SUPABASE_URL = _secret_get("SUPABASE_URL")
SUPABASE_KEY = _secret_get("SUPABASE_KEY")
USING_HARDCODED = not (SUPABASE_URL and SUPABASE_KEY)

_diag["has_url"] = bool(SUPABASE_URL)
_diag["has_key"] = bool(SUPABASE_KEY)

if USING_HARDCODED:
    _missing = [k for k in ("SUPABASE_URL", "SUPABASE_KEY") if not _secret_get(k)]
    _startup_notices.append((
        "warning",
        "No Supabase credentials found - running in local demo mode "
        f"(data will not persist). Missing: {', '.join(_missing) or 'unknown'}. "
        "Expand **Connection diagnostics** below to see exactly why."
    ))

SESSION_TIMEOUT_MINUTES = _secret_get("SESSION_TIMEOUT_MINUTES", 60)
MAX_UPLOAD_SIZE_MB = _secret_get("MAX_UPLOAD_SIZE_MB", 5)
try:
    SESSION_TIMEOUT_MINUTES = int(SESSION_TIMEOUT_MINUTES)
    MAX_UPLOAD_SIZE_MB = int(MAX_UPLOAD_SIZE_MB)
except (TypeError, ValueError):
    SESSION_TIMEOUT_MINUTES, MAX_UPLOAD_SIZE_MB = 60, 5
    _startup_notices.append(("warning",
        "SESSION_TIMEOUT_MINUTES / MAX_UPLOAD_SIZE_MB must be numbers "
        "(no quotes in secrets.toml). Falling back to defaults."))
MAX_UPLOAD_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

SLACK_WEBHOOK = _secret_get("SLACK_WEBHOOK", "")
TEAMS_WEBHOOK = _secret_get("TEAMS_WEBHOOK", "")
GOOGLE_CLIENT_ID = _secret_get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = _secret_get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = _secret_get("GOOGLE_REDIRECT_URI", "")
APP_URL = _secret_get("APP_URL", "")

# Smart Work Order Descriptions / Incident Severity Prediction — both
# AI-assisted features share this one config. Supports three
# providers, not just one — whichever key is actually configured is
# used, checked at call time in generate_smart_text() below. Gemini
# added specifically because Google AI Studio offers a genuine free
# tier (no payment method required) on Flash-class models, unlike
# Anthropic/OpenAI which are both usage-billed with no free tier —
# this matters for a site that wants AI features without a card on file.
ANTHROPIC_API_KEY = _secret_get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = _secret_get("OPENAI_API_KEY", "")
GEMINI_API_KEY = _secret_get("GEMINI_API_KEY", "")
AI_FEATURES_AVAILABLE = bool(ANTHROPIC_API_KEY or OPENAI_API_KEY or GEMINI_API_KEY)
ANTHROPIC_MODEL = _secret_get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
OPENAI_MODEL = _secret_get("OPENAI_MODEL", "gpt-4o-mini")
# Configurable rather than hardcoded — Gemini's recommended model name
# has shifted more than once in recent memory (2.0 -> 2.5 -> 3 ->
# 3.5 Flash), so a site can update this without needing a code change
# if Google renames the current default again.
GEMINI_MODEL = _secret_get("GEMINI_MODEL", "gemini-2.0-flash")
# Model availability genuinely varies by account/region/API version —
# gemini-2.5-flash (the prior default here) returned a 404 for at
# least one real deployment, confirmed via the exact error message,
# not assumed. gemini-2.0-flash is sourced from Google's own direct
# API reference example (ai.google.dev/api/generate-content), the
# most authoritative source found, but even this isn't guaranteed for
# every account. If this 404s too: fetch
# https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_KEY
# in a browser — it lists exactly which models YOUR key can use — and
# set GEMINI_MODEL in secrets.toml to one of those exact names.

# -------------------------------
# 0C. SUPABASE CLIENT
# -------------------------------
supabase = None
SUPABASE_AVAILABLE = False

try:
    import supabase as _supabase_pkg
    from supabase import create_client, Client
    _diag["library_installed"] = True
    _diag["library_version"] = getattr(_supabase_pkg, "__version__", "unknown")
    _diag["library_error"] = None
except ImportError as _e:
    _diag["library_installed"] = False
    _diag["library_version"] = None
    _diag["library_error"] = str(_e)
    _startup_notices.append(("error",
        "The `supabase` package is NOT installed. Even with correct "
        "credentials the app cannot connect. Fix: pip install supabase"))

if _diag.get("library_installed") and SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        SUPABASE_AVAILABLE = True
        _diag["client_created"] = True
        _diag["client_error"] = None
    except Exception as _e:
        SUPABASE_AVAILABLE = False
        _diag["client_created"] = False
        _diag["client_error"] = f"{type(_e).__name__}: {_e}"
        _startup_notices.append(("error",
            f"Credentials were found but the Supabase client failed to "
            f"build: {type(_e).__name__}: {_e}"))
else:
    _diag["client_created"] = False
    _diag.setdefault("client_error", "not attempted")

# -------------------------------
# 0D. SUPABASE ADMIN CLIENT (Phase 2 of the Auth migration only)
# -------------------------------
# Uses the service_role key, NOT the anon key — a far more privileged
# credential that bypasses Row Level Security entirely and can create/
# delete Auth accounts. Deliberately isolated: this client is used in
# exactly one place in the whole codebase (provision_auth_accounts, in
# the Owner Console's Auth Migration tab) and nowhere else. Everything
# else in the app continues using the ordinary anon-key `supabase`
# client above.
#
# Entirely optional. If SUPABASE_SERVICE_ROLE_KEY isn't set, Phase 2
# provisioning simply isn't available yet — no startup warning banner,
# since most people using this app day-to-day have no reason to know
# this key exists at all. The explanation surfaces only inside the
# Owner Console screen where it's actually relevant.
SUPABASE_SERVICE_ROLE_KEY = _secret_get("SUPABASE_SERVICE_ROLE_KEY")
supabase_admin = None
SUPABASE_ADMIN_AVAILABLE = False
_diag["admin_client_error"] = None
if _diag.get("library_installed") and SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    try:
        supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        SUPABASE_ADMIN_AVAILABLE = True
    except Exception as _e:
        SUPABASE_ADMIN_AVAILABLE = False
        # NOTE: log_error() is not yet defined at this point in the file
        # (it's Section 3, much later) — calling it here would crash the
        # entire app at startup for every user the moment this branch is
        # hit, not just the Owner. Stored in _diag instead, following the
        # exact same pattern the main anon-key client above already uses
        # for its own connection errors at this same point in the file.
        _diag["admin_client_error"] = f"{type(_e).__name__}: {_e}"

# VAPID keys for Web Push — generated once (see
# PUSH_NOTIFICATIONS_SETUP.md), never per-user or per-session. The
# public key is safe to embed in client-side JS (that's its whole
# purpose — the browser needs it to subscribe); the private key stays
# server-side only, used to sign outgoing push messages.
VAPID_PUBLIC_KEY = _secret_get("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = _secret_get("VAPID_PRIVATE_KEY")
VAPID_CLAIMS_EMAIL = _secret_get("VAPID_CLAIMS_EMAIL") or "admin@example.com"
PUSH_CONFIGURED = bool(PUSH_AVAILABLE and VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)

# Site coordinates for weather-adaptive planning — a plain, non-secret
# setting (latitude/longitude aren't sensitive), but kept in
# secrets.toml anyway for consistency with how every other
# deployment-specific value in this app is configured, rather than
# introducing a second, different configuration mechanism just for
# these two numbers.
_MINE_LAT_RAW = _secret_get("MINE_LATITUDE")
_MINE_LON_RAW = _secret_get("MINE_LONGITUDE")
try:
    MINE_LATITUDE = float(_MINE_LAT_RAW) if _MINE_LAT_RAW else None
    MINE_LONGITUDE = float(_MINE_LON_RAW) if _MINE_LON_RAW else None
except (TypeError, ValueError):
    MINE_LATITUDE = None
    MINE_LONGITUDE = None
WEATHER_CONFIGURED = MINE_LATITUDE is not None and MINE_LONGITUDE is not None

# Theme toggle
if 'dark_mode' not in st.session_state:
    st.session_state.dark_mode = False
if 'glove_mode' not in st.session_state:
    st.session_state.glove_mode = False

# =========================================================================
# THEME SYSTEM
# =========================================================================
# Rewritten to fix three real bugs in the previous version:
#
#  1. Metric values were invisible. The old CSS targeted `.stMetric .value`,
#     which does not exist in current Streamlit — metrics render as
#     [data-testid="stMetricValue"]. The rule silently never applied, so the
#     big numbers fell back to a washed-out default.
#  2. Sidebar styling was dead code. It targeted `.css-1d391kg`, an
#     auto-generated hash class that changes on every Streamlit release.
#     Now uses the stable [data-testid="stSidebar"].
#  3. Dark mode was overridden. A third <style> block hardcoded light
#     colours *after* the theme was chosen. There is now ONE injection.
#
# Colours are defined once as CSS custom properties, so every rule below
# is theme-agnostic. All body text meets WCAG AA (>= 4.5:1) and large text
# meets AA Large (>= 3:1) against its background.
# =========================================================================

LIGHT_TOKENS = """
    --bg-app: #eef1f6;
    --bg-surface: #ffffff;
    --bg-surface-2: #f6f8fb;
    --bg-sidebar: #16213e;
    --border: #d3dae6;
    --border-strong: #b6c0d1;

    --text-primary: #101828;      /* 16.9:1 on white */
    --text-secondary: #475569;    /*  7.5:1 on white */
    --text-muted: #5b6879;        /*  5.6:1 on white - still AA */
    --text-on-dark: #f1f5f9;
    --text-on-dark-muted: #c3cddc;

    --accent: #1d4ed8;            /*  6.3:1 on white */
    --accent-hover: #1740ad;
    --accent-contrast: #ffffff;
    --accent-soft: #e6ecfb;

    /* Brand colors sampled directly from the company's marketing
       material (poster: "WORK SMARTER. STAY SAFER. DELIVER MORE.").
       Theme-invariant by design — a brand identity shouldn't shift
       between light/dark mode, same reasoning already applied to the
       logo bar's fixed-white background.
       IMPORTANT: --brand-lime fails WCAG contrast as text on white
       (1.84:1, needs 4.5:1) — verified by computing the actual
       relative-luminance contrast ratio, not assumed. It is safe as
       a BACKGROUND with dark navy text/icons on top (9.9:1), or as an
       accent ON TOP of dark navy backgrounds (8.6–9.9:1) — exactly
       how the source poster itself uses it. Never use it as body text
       or link color on a light surface. */
    --brand-lime: #b9c901;
    --brand-navy: #001530;

    /* Stat-card tones — deliberately the SAME hex values already used by
       priority/status/severity badges elsewhere in the app (see the
       .priority-*, .status-*, .severity-* rules below). New components
       borrow the app's existing semantic color language instead of
       inventing a second one. */
    --tone-info: #1d4ed8;    --tone-info-soft: #dbe6fb;
    --tone-ok: #15803d;      --tone-ok-soft: #dcf1e3;
    --tone-warn: #b45309;    --tone-warn-soft: #faeadb;
    --tone-danger: #a4161a;  --tone-danger-soft: #f8dcdd;
    --tone-neutral: #4b5563; --tone-neutral-soft: #e6e8eb;

    --focus-ring: #1d4ed8;
    --shadow-sm: 0 1px 3px rgba(16,24,40,.08);
    --shadow-md: 0 4px 12px rgba(16,24,40,.10);
    --shadow-lg: 0 10px 28px rgba(16,24,40,.14);
"""

DARK_TOKENS = """
    --bg-app: #0b1220;
    --bg-surface: #151d2e;
    --bg-surface-2: #1b2536;
    --bg-sidebar: #080d18;
    --border: #2b3648;
    --border-strong: #3d4c66;

    --text-primary: #f3f6fb;      /* 15.8:1 on --bg-surface */
    --text-secondary: #c8d3e3;    /*  9.7:1 */
    --text-muted: #a6b3c6;        /*  6.8:1 */
    --text-on-dark: #f3f6fb;
    --text-on-dark-muted: #c8d3e3;

    --accent: #7cb3ff;            /*  7.9:1 on --bg-surface */
    --accent-hover: #a3caff;
    --accent-contrast: #0b1220;
    --accent-soft: #1e2f4d;

    /* Brand colors — identical to LIGHT_TOKENS, deliberately not
       theme-adaptive. See LIGHT_TOKENS for the contrast-verification
       notes on where --brand-lime is and isn't safe to use. */
    --brand-lime: #b9c901;
    --brand-navy: #001530;

    --tone-info: #7cb3ff;    --tone-info-soft: #16233f;
    --tone-ok: #34d399;      --tone-ok-soft: #0f2e21;
    --tone-warn: #fbbf24;    --tone-warn-soft: #3a2a0d;
    --tone-danger: #f87171;  --tone-danger-soft: #3a1416;
    --tone-neutral: #9aa5b5; --tone-neutral-soft: #232d3d;

    --focus-ring: #7cb3ff;
    --shadow-sm: 0 1px 3px rgba(0,0,0,.4);
    --shadow-md: 0 4px 12px rgba(0,0,0,.45);
    --shadow-lg: 0 10px 28px rgba(0,0,0,.55);
"""

_tokens = DARK_TOKENS if st.session_state.dark_mode else LIGHT_TOKENS

# Glove-Friendly Field Mode — roughly doubles the size of interactive
# elements (buttons, inputs, checkboxes) for use with thick gloves or
# in low-light/dusty conditions where precise taps are hard. Built as
# an ADDITIONAL css block appended after the normal CSS, not a
# replacement — everything not explicitly enlarged here keeps its
# normal size, so this only touches what actually needs bigger touch
# targets rather than blowing up the whole layout.
_GLOVE_MODE_CSS = """
[data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button {
    min-height: 3.2rem !important;
    font-size: 1.15rem !important;
    padding: 0.9rem 1.4rem !important;
}
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea, [data-testid="stDateInput"] input,
[data-testid="stTimeInput"] input {
    min-height: 3rem !important;
    font-size: 1.1rem !important;
    padding: 0.7rem !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] {
    min-height: 3rem !important;
    font-size: 1.1rem !important;
}
[data-testid="stCheckbox"] label, [data-testid="stRadio"] label {
    font-size: 1.1rem !important;
    padding: 0.4rem 0 !important;
}
[data-testid="stCheckbox"] span[role="checkbox"], [data-testid="stRadio"] span[role="radio"] {
    transform: scale(1.4);
    margin-right: 0.5rem;
}
.nav-link { min-height: 3rem !important; font-size: 1.05rem !important; }
"""

_CSS_BODY = """

/* ---------- Base ---------- */
.stApp { background-color: var(--bg-app); }

/* Raise default text contrast across the whole app. Streamlit's own
   defaults are too light for a screen viewed in bright light or through
   a dusty visor, which is the actual use case here. */
.stApp, .stApp p, .stApp li, .stApp span, .stApp label,
.stApp div[data-testid="stMarkdownContainer"] {
    color: var(--text-primary);
}
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
    color: var(--text-primary);
    font-weight: 700;
    letter-spacing: -0.01em;
}
.stApp small, .stCaption, [data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {
    color: var(--text-secondary) !important;
}

/* ---------- METRICS (the invisible-numbers fix) ---------- */
[data-testid="stMetric"] {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1rem 1.1rem;
    box-shadow: var(--shadow-sm);
}
[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] p {
    color: var(--text-secondary) !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
[data-testid="stMetricValue"] {
    color: var(--text-primary) !important;
    font-size: 2.1rem !important;
    font-weight: 800 !important;
    line-height: 1.15 !important;
}
[data-testid="stMetricDelta"] { font-weight: 700 !important; }

/* ---------- Sidebar (stable selector) ---------- */
[data-testid="stSidebar"] { background: var(--bg-sidebar); }
[data-testid="stSidebar"] * { color: var(--text-on-dark); }
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3, [data-testid="stSidebar"] strong {
    color: #ffffff;
}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
[data-testid="stSidebar"] small {
    color: var(--text-on-dark-muted) !important;
}
[data-testid="stSidebar"] .stButton button {
    background: var(--accent);
    color: var(--accent-contrast);
    border: none;
    border-radius: 8px;
    padding: 0.55rem 0.9rem;
    font-weight: 700;
    width: 100%;
}
[data-testid="stSidebar"] .stButton button:hover {
    background: var(--accent-hover);
    color: var(--accent-contrast);
}
/* Sidebar inputs need a light field with dark text, or they vanish
   against the dark sidebar background. */
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] textarea,
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: #ffffff !important;
    color: #101828 !important;
    border: 1px solid var(--border-strong) !important;
}
[data-testid="stSidebar"] input::placeholder,
[data-testid="stSidebar"] textarea::placeholder {
    color: #5b6879 !important;
}

/* ---------- Form controls ---------- */
.stTextInput label, .stTextArea label, .stSelectbox label,
.stNumberInput label, .stDateInput label, .stCheckbox label,
.stFileUploader label, .stRadio label, .stMultiSelect label {
    color: var(--text-primary) !important;
    font-weight: 600 !important;
    font-size: 0.92rem !important;
}
.stTextInput input, .stTextArea textarea, .stNumberInput input,
.stDateInput input {
    background: var(--bg-surface) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border-strong) !important;
    border-radius: 8px !important;
}
.stTextInput input::placeholder, .stTextArea textarea::placeholder {
    color: var(--text-muted) !important;
    opacity: 1 !important;
}
[data-baseweb="select"] > div {
    background: var(--bg-surface) !important;
    color: var(--text-primary) !important;
    border-color: var(--border-strong) !important;
}
[data-baseweb="popover"] li { color: var(--text-primary) !important; }

/* Visible keyboard focus — needed for accessibility and for gloved
   tab-navigation on shared terminals. */
.stApp *:focus-visible {
    outline: 3px solid var(--focus-ring) !important;
    outline-offset: 2px !important;
}

/* ---------- Buttons ---------- */
.stButton button, .stDownloadButton button, .stFormSubmitButton button {
    background: var(--accent);
    color: var(--accent-contrast);
    border: 1px solid transparent;
    border-radius: 8px;
    font-weight: 700;
    padding: 0.5rem 1rem;
}
.stButton button:hover, .stDownloadButton button:hover,
.stFormSubmitButton button:hover {
    background: var(--accent-hover);
    color: var(--accent-contrast);
}

/* ---------- Company logo bar ----------
   Sits above the app's own navy header, deliberately in a neutral
   white/light surface rather than matching the navy gradient — a
   company logo needs to read on its own, not compete with the app's
   own branding color. Renders only when a logo is actually set (see
   render_logo_bar()); no empty bar before one is uploaded.

   Background is a HARDCODED white, not var(--bg-surface) — that
   variable turns dark navy (#151d2e) in dark mode, which would make
   any logo using dark text (including the generated app logo, which
   uses navy) unreadable. Company logos are near-universally designed
   assuming a white backdrop, so this bar deliberately opts out of the
   dark theme rather than risk an invisible logo. */
.logo-bar {
    background: #ffffff;
    border: 1px solid var(--border);
    border-top: 3px solid var(--brand-lime);
    border-radius: 14px;
    padding: 0.7rem 1.2rem;
    margin-bottom: 0.8rem;
    box-shadow: var(--shadow-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    /* Sticky at the same clearance point main-header uses below —
       it's now the topmost sticky element, so it takes that spot,
       and main-header shifts down to stack beneath it (see
       --header-top-offset below and render_logo_bar()). Same
       position:sticky reasoning as main-header itself: avoids the
       layer-artifact class of bug fixed:sticky was already chosen
       to avoid there. */
    position: sticky;
    top: 60px;
    z-index: 999998;  /* one below main-header's 999999, so if they ever visually collide, header still wins */
}
.logo-bar img {
    max-height: 56px;
    max-width: 100%;
    object-fit: contain;
}

/* ---------- Announcement ticker ----------
   Sits between the logo bar and the main header. Unlike the logo bar,
   this uses normal theme variables rather than a forced white
   background — it's native app text, not an uploaded image with
   fixed colors, so there's no reason to opt out of dark mode here.

   The scroll direction is deliberately LEFT-TO-RIGHT (content enters
   from the left, exits to the right) — translateX(-100%) starts the
   content just off-screen to the left (shifted left by its own full
   width), animating to translateX(100%) which ends it just off-screen
   to the right. Respects prefers-reduced-motion (WCAG 2.2.2 — content
   that moves continuously for more than 5 seconds needs a way to
   stop), and pauses on hover so anyone who wants to actually read it
   can.

   Background is the brand navy with lime text — deliberately NOT
   using theme variables here, unlike before. This bar is inherently
   promotional (announcements, notices), and matches the source
   marketing poster's own "DOWNLOAD NOW" banner treatment far more
   honestly than a neutral theme-surface background would. Verified
   9.93:1 contrast for lime-on-navy — comfortably above the 4.5:1 AA
   threshold, not just eyeballed. */
.ticker-bar {
    overflow: hidden;
    white-space: nowrap;
    background: var(--brand-navy);
    border: 1px solid var(--brand-navy);
    border-radius: 14px;
    padding: 0.55rem 0;
    margin-bottom: 0.8rem;
    box-shadow: var(--shadow-sm);
}
.ticker-content {
    display: inline-block;
    white-space: nowrap;
    font-weight: 650;
    font-size: 0.88rem;
    color: var(--brand-lime);
    transform: translateX(-100%);
    animation: ticker-scroll-ltr 22s linear infinite;
}
.ticker-bar:hover .ticker-content {
    animation-play-state: paused;
}
@keyframes ticker-scroll-ltr {
    0%   { transform: translateX(-100%); }
    100% { transform: translateX(100%); }
}
@media (prefers-reduced-motion: reduce) {
    .ticker-content {
        animation: none;
        transform: none;
        padding-left: 1rem;
    }
    .ticker-bar { overflow-x: auto; }
}

/* ---------- Poster slideshow ----------
   Base styles live here (static, always loaded) rather than solely in
   the per-render inline <style> block — the multi-image crossfade
   needs per-render generation since keyframe timing depends on how
   many posters are active, but the single-image path was skipping
   that block entirely and rendering completely unstyled. Base sizing/
   positioning here means both paths are always styled correctly. */
.poster-slideshow {
    position: relative;
    width: 100%;
    height: 220px;
    border-radius: 14px;
    overflow: hidden;
    margin-bottom: 0.8rem;
    box-shadow: var(--shadow-md);
}
.poster-slide {
    position: absolute;
    top: 0; left: 0;
    width: 100%; height: 100%;
    object-fit: cover;
}
.poster-slide-solo {
    opacity: 1;
}

/* ---------- Detail field grid ----------
   Replaces the old "<p><i>Label:</i> value</p>" list style used on
   incident and handover cards — a flat stack of italic labels reads
   as dated. Each field becomes its own small card: colored accent bar
   (reusing the tone system), an icon-labeled heading, then the value.
   Scans as a real detail panel instead of a paragraph of labels. */
.field-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 0.6rem;
    margin-top: 0.7rem;
}
.field-card {
    background: var(--bg-surface-2);
    border-left: 3px solid var(--stat-color, var(--accent));
    border-radius: 8px;
    padding: 0.55rem 0.8rem;
}
.field-card .field-label {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.045em;
    color: var(--text-secondary);
    margin-bottom: 0.2rem;
}
.field-card .field-label i { color: var(--stat-color, var(--accent)); }
.field-card .field-value {
    font-size: 0.9rem;
    color: var(--text-primary);
    line-height: 1.45;
    overflow-wrap: anywhere;
}

/* ---------- Meta chips ----------
   Replaces a long inline run like "icon text &nbsp; icon text &nbsp;
   icon text..." — on a narrow screen that wraps mid-fact with no
   visual boundary between one piece of metadata and the next (see
   the incident card on mobile). Each fact becomes its own pill, so
   wrapping happens BETWEEN facts, never inside one. Two tones only,
   deliberately grouped by meaning rather than one-color-per-field:
   "info" for who/organizational-identity facts (reporter, employee
   ID, department), "neutral" for when/where/reference facts
   (location, time, shift, paper ref) — enough to let the eye group
   related facts without turning the row into a rainbow. */
.meta-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin: 0.55rem 0;
}
.meta-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    background: var(--stat-bg, var(--bg-surface-2));
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 0.28rem 0.75rem;
    font-size: 0.8rem;
    color: var(--text-primary);
    white-space: nowrap;
}
.meta-chip i {
    color: var(--stat-color, var(--text-secondary));
    font-size: 0.78rem;
}

/* Streamlit's OWN native header — a real, separate fixed element at
   the very top of the viewport, holding the sidebar toggle button.
   Found through direct research after a user reported the top of the
   custom header being cut off: Streamlit's header is itself
   position:fixed at top:0, so this app's own header at the same
   top:0 was directly colliding with it rather than the two stacking
   as expected. Made transparent (not hidden — hiding it would take
   the sidebar toggle button with it) so its own bar doesn't show a
   visible seam above this app's navy header, and STREAMLIT_HEADER_HEIGHT
   below shifts everything else down to actually clear it. */
[data-testid="stHeader"] {
    background: transparent;
}

/* ---------- Header ---------- */
.main-header {
    background: linear-gradient(135deg, var(--brand-navy) 0%, #051d3f 55%, var(--brand-navy) 100%);
    color: #ffffff;
    padding: 1.25rem 1.6rem;
    border-radius: 0;
    box-shadow: var(--shadow-md);
    font-size: 1.75rem;      /* was 2.5rem, which clipped its own text */
    font-weight: 800;
    line-height: 1.25;       /* the actual cause of the clipped title */
    position: sticky;  /* was fixed — testing sticky to address a rendering
    artifact reported across multiple browsers, where old content stayed
    visible behind the browser's own collapsing toolbar. fixed pulls an
    element onto its own always-repaint compositing layer, which can fall
    out of sync with a mobile browser's dynamic toolbar during scroll;
    sticky keeps the element in normal document flow until it reaches its
    stuck position, avoiding that specific class of layer artifact. */
    top: var(--header-top-offset, 60px);  /* clears Streamlit's native header, or also the logo bar when one is set — see render_logo_bar() */
    /* Deliberately a very high value, not the usual small documented
       scale (10 for nav, 50 for modals, etc.) — a screenshot showed
       an st.info() box visually escaping ABOVE this header despite
       the previous z-index:999, which points to a stacking-context
       issue: some Streamlit widgets apply transform/opacity
       internally for their own transitions, and that silently
       creates a new stacking context that a merely-higher z-index
       elsewhere can't reach into. This is the one place in the app
       where "must always win against literally everything else,
       including Streamlit's own internals" is the actual
       requirement, which is what justifies breaking from the
       otherwise-sensible small-number convention. */
    z-index: 999999;
    letter-spacing: -0.01em;
    border-bottom: 3px solid var(--brand-lime);
}
/* No longer needed with position:sticky — a sticky element occupies
   its own real space in normal document flow (unlike fixed, which
   removes the element from flow entirely and needs a stand-in
   spacer so content doesn't render underneath it). The three
   <div class="main-header-spacer"> markup calls are harmless no-ops
   now (an empty div with zero height), left in place rather than
   also removing three separate st.markdown() calls for a rule this
   easy to just zero out here. */
.main-header-spacer { height: 0; }
/* Same visual branding as .main-header (navy gradient, lime border,
   white text) but genuinely in normal document flow — for standalone
   module section headers (Wallboard, Crew Clock, JSA Library, Job
   Plans, Locations), which used to share .main-header directly. That
   meant each one also inherited position:sticky at the exact same
   top:60px stick-point as the app's own global branding header,
   causing two sticky elements to compete for the same spot. */
.section-header {
    background: linear-gradient(135deg, var(--brand-navy) 0%, #051d3f 55%, var(--brand-navy) 100%);
    color: #ffffff;
    padding: 1.25rem 1.6rem;
    border-radius: 14px;
    margin-bottom: 1.1rem;
    box-shadow: var(--shadow-md);
    font-size: 1.75rem;
    font-weight: 800;
    line-height: 1.25;
    letter-spacing: -0.01em;
    border-bottom: 3px solid var(--brand-lime);
}
.section-header i { color: var(--brand-lime); margin-right: 10px; }
.section-header small {
    display: block;
    margin-top: 6px;
    font-size: 0.85rem;
    font-weight: 500;
    line-height: 1.4;
    color: #d7e2f2;
    opacity: 1;
}
/* The header spans the full viewport width (left:0; right:0;), but
   Streamlit's sidebar sits on top of that same region on the left
   side of the screen — without this, the header's z-index:999999
   would win there too, visually burying the sidebar's own nav items
   (a screenshot showed "Owner Console", the first item, partially
   swallowed behind the header's background). The sidebar's width is
   user-resizable/draggable, so there's no reliable fixed pixel value
   the header could stop short at — giving the sidebar itself an even
   higher z-index is robust regardless of how wide someone drags it,
   rather than trying to calculate a boundary that can change at
   runtime. */
[data-testid="stSidebar"] {
    position: relative;
    z-index: 1000000;
}
.main-header i { color: var(--brand-lime); margin-right: 10px; }
.main-header small {
    display: block;
    margin-top: 6px;
    font-size: 0.85rem;
    font-weight: 500;
    line-height: 1.4;
    color: #d7e2f2;          /* 9.4:1 on the header gradient */
    opacity: 1;              /* opacity dimming was hurting contrast */
}
.sub-header {
    font-size: 1.2rem;
    font-weight: 700;
    color: var(--text-primary);
    margin: 0.4rem 0 1.1rem 0;
    padding-bottom: 0.45rem;
    border-bottom: 2px solid var(--accent);
}
.breadcrumb-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.6rem 0.9rem;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    margin-bottom: 1rem;
    font-size: 0.85rem;
}
.breadcrumb-bar .crumbs {
    color: var(--text-secondary);
}
.breadcrumb-bar .crumbs .current {
    color: var(--text-primary);
    font-weight: 700;
}
.breadcrumb-bar .welcome {
    color: var(--text-secondary);
}
.breadcrumb-bar .welcome b { color: var(--text-primary); }

/* ---------- Pre-login landing page ---------- */
.landing-hero {
    background: linear-gradient(135deg, var(--brand-navy) 0%, #051d3f 100%);
    color: #ffffff;
    border-radius: 18px;
    padding: 2rem 1.6rem;
    margin-bottom: 1.2rem;
    text-align: center;
}
.landing-hero h1 {
    font-size: 1.6rem;
    font-weight: 800;
    margin: 0.6rem 0 0.5rem 0;
    color: #ffffff;
}
.landing-hero p {
    font-size: 0.95rem;
    color: #d7e2f2;
    max-width: 32rem;
    margin: 0 auto;
    line-height: 1.5;
}
.landing-hero .landing-icon {
    font-size: 2.4rem;
    color: var(--brand-lime);
}
.landing-feature-card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-top: 4px solid var(--brand-lime);
    border-radius: 14px;
    padding: 1.1rem;
    margin-bottom: 0.8rem;
    box-shadow: var(--shadow-sm);
}
.landing-feature-card .landing-feature-icon {
    font-size: 1.4rem;
    color: var(--accent);
    margin-bottom: 0.4rem;
}
.landing-feature-card h4 {
    font-size: 1rem;
    font-weight: 700;
    color: var(--text-primary);
    margin: 0.2rem 0 0.3rem 0;
}
.landing-feature-card p {
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin: 0;
    line-height: 1.4;
}

/* ---------- Stat cards ----------
   Icon-badge status tiles, styled after industrial control-room /
   SCADA dashboard tiles rather than a generic KPI-card template — the
   right reference point for a mine ops tool. The icon sits in a
   hexagonal badge (a workshop motif: bolt heads, hazard/PPE badges are
   commonly hexagonal) rather than a plain circle. Tone colors are the
   exact hex values already used by the priority/status/severity
   badges elsewhere, so a red stat card means the same thing a red
   badge means anywhere else in the app. */
.stat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 0.85rem;
    margin: 0.75rem 0 1.25rem 0;
}
.stat-card {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.85rem;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 0.95rem 1.05rem;
    box-shadow: var(--shadow-sm);
    overflow: hidden;
    transition: transform .15s ease, box-shadow .15s ease;
}
.stat-card::before {
    content: "";
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 4px;
    background: var(--stat-color, var(--accent));
}
.stat-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); }
.stat-icon {
    flex: 0 0 auto;
    width: 42px; height: 42px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 12px;
    background: var(--stat-bg, var(--accent-soft));
    color: var(--stat-color, var(--accent));
    font-size: 1rem;
}
.stat-body { min-width: 0; }

/* Action-card grid — a tappable-feeling card with a colored icon box,
   bold title, and a short description underneath, in a responsive
   2-column grid. New pattern, not a rename of anything existing;
   built for the "Quick Actions" style shortcut grids this app didn't
   have a component for before. */
.action-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 0.85rem;
    margin-bottom: 1rem;
}
.action-card {
    background: var(--stat-bg, var(--accent-soft));
    border: 1px solid var(--stat-color, var(--accent));
    border-radius: 16px;
    padding: 1.1rem 1rem;
    min-height: 148px;
    transition: transform .15s ease, box-shadow .15s ease;
}
.action-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); }
.action-card .action-icon {
    width: 44px; height: 44px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 12px;
    background: var(--bg-surface);
    color: var(--stat-color, var(--accent));
    font-size: 1.15rem;
    margin-bottom: 0.6rem;
}
.action-card .action-title {
    font-weight: 700;
    font-size: 0.98rem;
    color: var(--text-primary);
    margin-bottom: 0.2rem;
}
.action-card .action-desc {
    font-size: 0.83rem;
    color: var(--text-secondary);
    line-height: 1.35;
}
/* Progress steps — a horizontal lifecycle tracker (e.g. permit
   Issued -> Accepted -> Signed Back). Completed and current steps
   use the brand accent; future steps stay muted so the current
   position in the process reads at a glance without needing to
   parse a status badge's text. */
.progress-steps {
    display: flex;
    align-items: center;
    margin: 0.6rem 0 0.4rem 0;
}
.progress-step {
    display: flex;
    flex-direction: column;
    align-items: center;
    flex: 1;
    position: relative;
    font-size: 0.72rem;
    color: var(--text-secondary);
}
.progress-step .dot {
    width: 22px; height: 22px;
    border-radius: 50%;
    background: var(--bg-surface-2);
    border: 2px solid var(--border-strong);
    display: flex; align-items: center; justify-content: center;
    font-size: 0.7rem;
    margin-bottom: 0.25rem;
    color: var(--text-secondary);
}
.progress-step.done .dot { background: var(--tone-ok); border-color: var(--tone-ok); color: #fff; }
.progress-step.current .dot { background: var(--accent); border-color: var(--accent); color: #fff; }
.progress-step.done, .progress-step.current { color: var(--text-primary); font-weight: 600; }
.progress-step .line {
    position: absolute;
    top: 11px; left: -50%; width: 100%;
    height: 2px;
    background: var(--border-strong);
    z-index: -1;
}
.progress-step.done .line, .progress-step.current .line { background: var(--tone-ok); }
.progress-step:first-child .line { display: none; }
.progress-step.cancelled .dot { background: var(--tone-danger); border-color: var(--tone-danger); color: #fff; }
.empty-state {
    text-align: center;
    padding: 2.2rem 1.5rem;
    background: var(--bg-surface);
    border: 1px dashed var(--border);
    border-radius: 16px;
    margin-bottom: 0.85rem;
}
.empty-state .empty-icon {
    width: 52px; height: 52px;
    margin: 0 auto 0.9rem;
    display: flex; align-items: center; justify-content: center;
    border-radius: 50%;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 1.4rem;
}
.empty-state .empty-title {
    font-weight: 700;
    font-size: 1rem;
    color: var(--text-primary);
    margin-bottom: 0.25rem;
}
.empty-state .empty-sub {
    font-size: 0.85rem;
    color: var(--text-secondary);
}
/* Makes the whole action-card clickable: the real click target is a
   Streamlit button, immediately following the card in the DOM, pulled
   up over the card with a negative margin and made invisible. This
   is deliberately NOT position:absolute — the card and button are
   SIBLING elements (both direct children of the same column), and
   position:absolute only anchors to an ANCESTOR's positioning
   context, not a sibling's — it would end up positioned against the
   whole column, not the card specifically. A negative margin pull-up
   works correctly for siblings, which is why the card above was
   given a fixed min-height: this technique only lines up reliably
   when both sides agree on the same height, rather than the button
   guessing at a card whose height changes with its description text.
   Built on div[data-testid="stButton"], a long-stable Streamlit
   internal attribute already relied on elsewhere in this app's CSS. */
div[data-testid="element-container"]:has(> div.action-grid) {
    margin-bottom: -148px;
    position: relative;
    z-index: 0;
}
div[data-testid="element-container"]:has(> div.action-grid) + div[data-testid="element-container"] {
    position: relative;
    z-index: 1;
}
div[data-testid="element-container"]:has(> div.action-grid) + div[data-testid="element-container"] div[data-testid="stButton"] button {
    width: 100%;
    height: 148px;
    opacity: 0;
    cursor: pointer;
    margin: 0;
}
.stat-value {
    font-size: 1.65rem;
    font-weight: 800;
    color: var(--text-primary);
    line-height: 1.1;
    font-variant-numeric: tabular-nums;
}
.stat-label {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.045em;
    text-transform: uppercase;
    color: var(--text-secondary);
    margin-top: 3px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

/* ---------- Cards ---------- */
.custom-card, .task-card, .metric-box {
    background: var(--bg-surface);
    color: var(--text-primary);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1rem 1.1rem;
    margin-bottom: 0.85rem;
    box-shadow: var(--shadow-sm);
    line-height: 1.55;
}
.custom-card { border-left: 4px solid var(--accent); }
.custom-card:hover, .task-card:hover { box-shadow: var(--shadow-md); }
.custom-card strong, .task-card strong { color: var(--text-primary); }
.custom-card small, .task-card small { color: var(--text-secondary); }
.custom-card i, .task-card i { color: var(--text-secondary); }
/* Deep Linking — the task a ?task=142 URL pointed to gets this pulse
   so it's findable at a glance in a list, without needing separate
   scroll-to-element JavaScript (a more fragile addition given this
   app's own past experience with unreliable scroll-via-script
   approaches in Streamlit specifically). */
@keyframes task-highlight-pulse {
    0%, 100% { box-shadow: 0 0 0 3px var(--brand-lime); }
    50% { box-shadow: 0 0 0 6px var(--brand-lime); }
}
.task-card-highlighted {
    animation: task-highlight-pulse 1.5s ease-in-out 3;
}
.task-title { font-size: 1.05rem; font-weight: 700; color: var(--text-primary); }
.task-meta {
    display: flex; gap: 0.9rem; flex-wrap: wrap;
    margin: 0.35rem 0 0.6rem 0;
    font-size: 0.88rem; color: var(--text-secondary);
}
.metric-box { text-align: center; }
.metric-box .value { font-size: 2rem; font-weight: 800; color: var(--text-primary); }
.metric-box .label { font-size: 0.85rem; color: var(--text-secondary); }

/* ---------- Badges ----------
   All badge text is white on a colour dark enough to clear 4.5:1.
   The old Medium/Low priority colours were too light for white text. */
.priority-badge, .status-badge, .severity-badge, .asset-status-badge {
    display: inline-block;
    padding: 0.2rem 0.65rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.03em;
    color: #ffffff;
    white-space: nowrap;
}
.priority-Critical  { background: #a4161a; }
.priority-High      { background: #b45309; }
.priority-Medium    { background: #1d4ed8; }
.priority-Low       { background: #15803d; }

.status-Unassigned  { background: #4b5563; }
.status-InProgress  { background: #1d4ed8; }
.status-PendingQA   { background: #b45309; }
.status-Blocked     { background: #a4161a; }
.status-Complete    { background: #15803d; }
.status-Open        { background: #b45309; }
.status-Investigating { background: #1d4ed8; }
.status-Resolved    { background: #15803d; }
.status-Closed      { background: #4b5563; }

.severity-Critical  { background: #7f1d1d; }
.severity-High      { background: #a4161a; }
.severity-Medium    { background: #b45309; }
.severity-Low       { background: #1d4ed8; }

.asset-status-Operational { background: #15803d; }
.asset-status-Down        { background: #a4161a; }
.asset-status-Maintenance { background: #b45309; }
.asset-status-Retired     { background: #4b5563; }

.overdue-badge, .verified-badge, .pending-badge, .stock-badge {
    display: inline-block;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 800;
    color: #ffffff;
    margin-left: 0.4rem;
    white-space: nowrap;
}
.overdue-badge  { background: #a4161a; }
.verified-badge { background: #15803d; }
.pending-badge  { background: #b45309; }
.stock-ok       { background: #15803d; }
.stock-low      { background: #a4161a; }

/* ---------- Tabs ---------- */
.stTabs [data-baseweb="tab-list"] { gap: 0.25rem; }
.stTabs [data-baseweb="tab"] {
    background: var(--bg-surface-2);
    color: var(--text-secondary);
    border: 1px solid var(--border);
    border-bottom: none;
    border-radius: 10px 10px 0 0;
    padding: 0.5rem 1rem;
    font-weight: 600;
}
.stTabs [aria-selected="true"] {
    background: var(--accent);
    color: var(--accent-contrast);
    border-color: var(--accent);
}

/* ---------- Expanders ---------- */
[data-testid="stExpander"] {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 10px;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p {
    color: var(--text-primary) !important;
    font-weight: 650 !important;
}

/* ---------- Alerts: keep Streamlit's semantic tints but force
   readable text, since the defaults wash out in dark mode. ---------- */
[data-testid="stAlert"] { border-radius: 10px; }
[data-testid="stAlert"] p, [data-testid="stAlert"] div { color: #101828 !important; }

/* ---------- Tables ---------- */
[data-testid="stDataFrame"], [data-testid="stTable"] {
    color: var(--text-primary);
    border: 1px solid var(--border);
    border-radius: 10px;
}

/* ---------- Chat ---------- */
.chat-message {
    display: flex;
    align-items: flex-start;
    gap: 0.65rem;
    background: var(--bg-surface-2);
    color: var(--text-primary);
    border-left: 4px solid var(--accent);
    border-radius: 10px;
    padding: 0.55rem 0.9rem;
    margin: 0.25rem 0;
    line-height: 1.5;
}
.chat-message.self { background: var(--accent-soft); }
.chat-avatar {
    flex: 0 0 auto;
    width: 30px; height: 30px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.72rem; font-weight: 800;
    background: var(--stat-bg, var(--tone-neutral-soft));
    color: var(--stat-color, var(--tone-neutral));
    margin-top: 0.1rem;
}
.chat-body { min-width: 0; flex: 1; }
.chat-message .sender { font-weight: 800; color: var(--text-primary); }
.chat-message .timestamp {
    font-size: 0.72rem;
    color: var(--text-secondary);
    margin-left: 0.4rem;
}
.chat-message .chat-text { margin-top: 0.1rem; overflow-wrap: anywhere; }

.chat-date-sep {
    display: flex; align-items: center; gap: 0.7rem;
    margin: 0.9rem 0 0.5rem 0;
    color: var(--text-secondary);
    font-size: 0.72rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.04em;
}
.chat-date-sep::before, .chat-date-sep::after {
    content: ""; flex: 1; height: 1px; background: var(--border);
}

.chat-room-header {
    display: flex; align-items: center; gap: 0.7rem;
    background: var(--bg-surface); border: 1px solid var(--border);
    border-left: 4px solid var(--accent);
    border-radius: 12px; padding: 0.8rem 1.05rem;
    margin-bottom: 0.75rem; box-shadow: var(--shadow-sm);
}
.chat-room-icon {
    flex: 0 0 auto; width: 38px; height: 38px;
    border-radius: 9px; display: flex; align-items: center; justify-content: center;
    background: var(--tone-info-soft); color: var(--tone-info); font-size: 1rem;
}
.chat-room-title { font-weight: 800; color: var(--text-primary); font-size: 1.02rem; }
.chat-room-sub { font-size: 0.78rem; color: var(--text-secondary); margin-top: 0.1rem; }

/* ---------- Log / activity timeline ----------
   A third, deliberately distinct shape from the stat-card hexagon and
   the chat avatar circle: a rounded-square icon chip. The app now has
   three shape families that each mean one thing consistently —
   hexagon = status/metric, circle = a person, rounded-square = a
   logged event — so the shape itself is informative before you even
   read the icon inside it. */
.log-list { display: flex; flex-direction: column; }
.log-entry {
    display: flex;
    align-items: flex-start;
    gap: 0.8rem;
    padding: 0.6rem 0.1rem;
    border-bottom: 1px solid var(--border);
}
.log-entry:last-child { border-bottom: none; }
.log-icon {
    flex: 0 0 auto;
    width: 32px; height: 32px;
    border-radius: 9px;
    display: flex; align-items: center; justify-content: center;
    background: var(--stat-bg, var(--tone-neutral-soft));
    color: var(--stat-color, var(--tone-neutral));
    font-size: 0.82rem;
    margin-top: 0.1rem;
}
.log-body { min-width: 0; flex: 1; }
.log-line {
    display: flex; align-items: baseline; justify-content: space-between;
    gap: 0.6rem; flex-wrap: wrap;
    color: var(--text-primary);
    font-size: 0.9rem;
    line-height: 1.4;
}
.log-line b { font-weight: 700; }
.log-time {
    font-size: 0.72rem; color: var(--text-secondary);
    white-space: nowrap; flex-shrink: 0;
}
.log-details {
    font-size: 0.76rem;
    color: var(--text-secondary);
    margin-top: 0.25rem;
    font-family: ui-monospace, "SF Mono", Consolas, monospace;
    background: var(--bg-surface-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.3rem 0.55rem;
    overflow-wrap: anywhere;
}

/* ---------- Feedback board ---------- */
.vote-btn-wrap { display: flex; flex-direction: column; align-items: center; }
.feedback-response {
    background: var(--tone-info-soft); border-left: 3px solid var(--tone-info);
    border-radius: 8px; padding: 0.6rem 0.8rem; margin-top: 0.5rem;
    font-size: 0.88rem; color: var(--text-primary);
}

/* ---------- User directory table ---------- */
.user-table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
.user-table th {
    text-align: left; padding: 0.55rem 0.7rem;
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.04em;
    text-transform: uppercase; color: var(--text-secondary);
    border-bottom: 2px solid var(--border);
}
.user-table td {
    padding: 0.6rem 0.7rem;
    border-bottom: 1px solid var(--border);
    color: var(--text-primary);
    vertical-align: middle;
}
.user-table tr:hover td { background: var(--bg-surface-2); }
.user-table .u-name { font-weight: 700; }
.user-table .u-mono { font-family: ui-monospace, monospace; font-size: 0.85rem; color: var(--text-secondary); }

/* ---------- File uploader ---------- */
[data-testid="stFileUploader"] {
    background: var(--bg-surface-2);
    border: 2px dashed var(--border-strong);
    border-radius: 10px;
    padding: 0.5rem;
}
[data-testid="stFileUploader"] * { color: var(--text-primary) !important; }

/* ---------- Sidebar user block ---------- */
.sidebar-user { text-align: center; padding: 0.4rem 0 0.2rem; }
.sidebar-user .user-icon { font-size: 2.6rem; color: #7cb3ff; }
.sidebar-user .user-name {
    font-weight: 800; font-size: 1.1rem; margin-top: 0.25rem; color: #ffffff;
}
.sidebar-user .user-role { font-size: 0.85rem; color: var(--text-on-dark-muted); }

/* ---------- Footer ---------- */
.footer {
    text-align: center;
    margin-top: 2rem;
    padding: 0.9rem;
    color: var(--text-secondary);
    font-size: 0.8rem;
    line-height: 1.6;
    border-top: 1px solid var(--border);
}

/* ---------- Field-condition affordances ----------
   Larger tap targets and text on small screens: this gets used on
   phones, in gloves, in bad light. */
@media (max-width: 900px) {
    .main-header { font-size: 1.4rem; padding: 1rem 1.1rem; }
    [data-testid="stMetricValue"] { font-size: 1.8rem !important; }
    .stButton button, .stFormSubmitButton button {
        padding: 0.7rem 1rem;
        font-size: 1rem;
    }
    .task-meta { gap: 0.5rem; font-size: 0.85rem; }
}
"""


def _inline_css(tokens, body):
    """Emit the stylesheet as a SINGLE line of HTML.

    This is not cosmetic. st.markdown() runs the string through a
    markdown parser before treating it as HTML, and in markdown a
    BLANK LINE closes the current block. A <style> block containing
    blank lines therefore gets cut short: everything after the first
    blank line is re-parsed as markdown, so indented CSS renders as
    code blocks and the rest as paragraphs — the stylesheet appears
    on screen as literal text instead of being applied.

    Stripping comments and joining to one line keeps the source above
    readable while emitting markdown-safe HTML.
    """
    combined = ":root {" + tokens + "}" + body
    combined = re.sub(r"/\*.*?\*/", "", combined, flags=re.S)  # drop comments
    parts = [ln.strip() for ln in combined.splitlines()]
    result = " ".join(p for p in parts if p)
    # Guard against regression: if a newline ever survives into the output,
    # markdown will truncate the <style> block and dump the remaining CSS
    # on screen as text. Fail loudly here instead.
    assert "\n" not in result, "CSS must be emitted as a single line"
    return result


st.markdown(
    '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">'
    "<style>" + _inline_css(_tokens, _CSS_BODY + (_GLOVE_MODE_CSS if st.session_state.glove_mode else "")) + "</style>",
    unsafe_allow_html=True,
)

# -------------------------------
# 1B. STARTUP NOTICES + CONNECTION DIAGNOSTICS
# -------------------------------
# Notices are rendered here (after set_page_config and the stylesheet)
# rather than at the point of failure, so nothing runs before
# set_page_config and no error gets swallowed.
for _level, _msg in _startup_notices:
    getattr(st, _level)(_msg)

if not SUPABASE_AVAILABLE:
    with st.expander("🔎 Connection diagnostics — click to see why", expanded=False):
        st.caption("Shows key NAMES and error types only. Never displays secret values.")

        import os as _os
        import sys as _sys
        from pathlib import Path as _Path

        _cwd = _Path.cwd()
        _expected = _cwd / ".streamlit" / "secrets.toml"

        st.markdown("**Step 1 — Is Streamlit finding a secrets file?**")
        st.code(f"Working directory : {_cwd}\n"
                f"Expects file at   : {_expected}\n"
                f"File exists there : {_expected.exists()}", language="text")
        if not _expected.exists():
            _alt = list(_cwd.rglob(".streamlit/secrets.toml"))[:5]
            if _alt:
                st.error("A secrets.toml exists elsewhere. Streamlit only reads the "
                         "path above — launch from that directory instead:")
                for _p in _alt:
                    st.code(f"cd {_p.parent.parent} && streamlit run app.py", language="bash")
            else:
                st.error("No .streamlit/secrets.toml found anywhere below this directory.")
            st.info("On Streamlit Community Cloud a local file is IGNORED. "
                    "Paste your TOML into: App → Settings → Secrets.")

        st.markdown("**Step 2 — Can st.secrets be read?**")
        if _diag.get("secrets_readable"):
            _keys = _diag.get("secret_keys_found", [])
            st.success(f"Yes. {len(_keys)} key(s) loaded.")
            if _keys:
                st.code("\n".join(_keys), language="text")
            else:
                st.warning("Readable, but EMPTY — the file parsed to zero keys. "
                           "Check for a stray [section] header above your keys, "
                           "which would nest them.")
        else:
            st.error(f"No. {_diag.get('secrets_error')}")

        st.markdown("**Step 3 — Are the two required keys present?**")
        _c1, _c2 = st.columns(2)
        _c1.metric("SUPABASE_URL", "found" if _diag.get("has_url") else "MISSING")
        _c2.metric("SUPABASE_KEY", "found" if _diag.get("has_key") else "MISSING")

        st.markdown("**Step 4 — Is the supabase library installed?**")
        if _diag.get("library_installed"):
            st.success(f"Yes — version {_diag.get('library_version')}")
        else:
            st.error(f"No. {_diag.get('library_error')}")
            st.code(f"{_sys.executable} -m pip install supabase", language="bash")
            st.caption("Use the exact interpreter above — installing into a different "
                       "environment than the one running Streamlit is a common trap.")

        st.markdown("**Step 5 — Did the client build?**")
        if _diag.get("client_created"):
            st.success("Yes.")
        else:
            st.error(f"No. {_diag.get('client_error')}")

        st.markdown("---")
        st.markdown("**Environment**")
        st.code(f"Python     : {_sys.version.split()[0]}\n"
                f"Executable : {_sys.executable}\n"
                f"Streamlit  : {getattr(st, '__version__', 'unknown')}", language="text")

        st.markdown("**Live connection test**")
        if st.button("▶️ Test the Supabase connection now"):
            if not _diag.get("library_installed"):
                st.error("Cannot test — the supabase library is not installed.")
            elif not (SUPABASE_URL and SUPABASE_KEY):
                st.error("Cannot test — credentials are missing.")
            else:
                try:
                    _c = create_client(SUPABASE_URL, SUPABASE_KEY)
                    _c.table("tasks").select("id").limit(1).execute()
                    st.success("Connected and queried the `tasks` table successfully. "
                               "Restart the app and this banner should disappear.")
                except Exception as _te:
                    st.error(f"{type(_te).__name__}: {_te}")
                    _t = str(_te).lower()
                    if "does not exist" in _t or "relation" in _t:
                        st.info("Connected, but the `tasks` table is missing. "
                                "Run schema_additions.sql (and your original table setup) "
                                "in the Supabase SQL editor.")
                    elif "invalid" in _t and "key" in _t:
                        st.info("The key was rejected. Confirm you copied the "
                                "`anon` `public` key, complete and unbroken.")
                    elif "row-level security" in _t or "rls" in _t or "policy" in _t:
                        st.info("Connected, but RLS is blocking the query. Run the "
                                "policy statements at the end of schema_additions.sql.")
                    elif "name or service not known" in _t or "getaddrinfo" in _t:
                        st.info("DNS lookup failed — check SUPABASE_URL for typos, "
                                "and whether site network policy allows outbound HTTPS.")

# -------------------------------
# 2. SHARED STYLES FOR OPTION MENU
# -------------------------------
def menu_styles(orientation="horizontal"):
    """Styling for streamlit-option-menu.

    This component takes inline styles rather than CSS classes, so the
    theme tokens have to be mirrored here as literal values. Keep these
    in sync with LIGHT_TOKENS / DARK_TOKENS above.

    Note the icon colour: the old value (#4fc3f7) was a pale cyan that
    sat at roughly 1.9:1 against a white container — effectively
    invisible in light mode. Each theme now gets an icon colour that
    contrasts with its own container.

    orientation="vertical" left-aligns nav-link text instead of
    centering it — centered text reads fine in a horizontal bar but
    looks visibly off in a vertical sidebar list, where every other
    convention (this app's own sidebar buttons included) is
    left-aligned.
    """
    dark = st.session_state.dark_mode
    return {
        "container": {
            "padding": "5px",
            "background-color": "#151d2e" if dark else "#ffffff",
            "border": f"1px solid {'#2b3648' if dark else '#d3dae6'}",
            "border-radius": "12px",
            "box-shadow": "0 1px 3px rgba(16,24,40,.08)",
            "margin-bottom": "1rem",
        },
        "icon": {
            # 7.9:1 on dark surface / 6.3:1 on white
            "color": "#7cb3ff" if dark else "#1d4ed8",
            "font-size": "15px",
        },
        "nav-link": {
            "font-size": "13.5px",
            "font-weight": "650",
            "text-align": "left" if orientation == "vertical" else "center",
            "margin": "2px 2px",
            "padding": "0.5rem 0.6rem",
            "border-radius": "9px",
            "color": "#f3f6fb" if dark else "#101828",
            "--hover-color": "#1b2536" if dark else "#e6ecfb",
        },
        "nav-link-selected": {
            "background-color": "#7cb3ff" if dark else "#1d4ed8",
            "color": "#0b1220" if dark else "#ffffff",
            "font-weight": "800",
        },
    }


def render_stat_cards(cards):
    """Render a row of icon-badge stat tiles.

    `cards` is a list of dicts, each with:
        icon  - a Font Awesome class suffix, e.g. "fa-clipboard-list"
        label - the metric name, e.g. "Total Tasks"
        value - the number/string to display (already computed by the
                caller — this function only renders, it never counts
                anything itself, so the underlying logic everywhere
                that used to call st.metric() is completely unchanged)
        tone  - one of "info", "ok", "warn", "danger", "neutral"
                (defaults to "info"). These map to the exact colors
                already used by the app's priority/status/severity
                badges — see the --tone-* CSS variables — so a red
                stat card and a red badge always mean the same thing.

    This is a pure rendering swap for st.metric()/st.columns(); nothing
    about what gets counted or when changes.
    """
    valid_tones = {"info", "ok", "warn", "danger", "neutral"}
    html = ['<div class="stat-grid">']
    for c in cards:
        tone = c.get("tone", "info")
        if tone not in valid_tones:
            tone = "info"
        icon = c.get("icon", "fa-chart-simple")
        html.append(
            f'<div class="stat-card" style="--stat-color:var(--tone-{tone});'
            f'--stat-bg:var(--tone-{tone}-soft);">'
            f'<div class="stat-icon"><i class="fas {esc(icon)}"></i></div>'
            f'<div class="stat-body">'
            f'<div class="stat-value">{esc(c.get("value", 0))}</div>'
            f'<div class="stat-label">{esc(c.get("label", ""))}</div>'
            f'</div></div>'
        )
    html.append('</div>')
    st.markdown("".join(html), unsafe_allow_html=True)


_VALID_TONES = {"info", "ok", "warn", "danger", "neutral"}

# Keyword rules, checked in order, first match wins. Substring-based
# rather than an exhaustive per-action dict, so an action name added
# later (a new log_audit(...) call somewhere) degrades to a sensible
# neutral default instead of needing this list updated in lockstep.
_LOG_ACTION_RULES = [
    (("lockout", "denied", "deny"), ("fa-ban", "danger")),
    (("delete", "remove"), ("fa-trash", "danger")),
    (("suspend",), ("fa-pause", "warn")),
    (("permit",), ("fa-shield-halved", "info")),
    (("password", "reset"), ("fa-key", "warn")),
    (("mailbox", "workspace"), ("fa-envelope", "ok")),
    (("approve", "created", "create", "bootstrap", "reinstate"), ("fa-circle-check", "ok")),
    (("login",), ("fa-right-to-bracket", "neutral")),
    (("logout",), ("fa-right-from-bracket", "neutral")),
    (("request",), ("fa-paper-plane", "info")),
    (("assign", "status_change", "role_change", "update"), ("fa-pen", "info")),
    (("upload",), ("fa-upload", "info")),
    (("comment",), ("fa-comment", "neutral")),
    (("broadcast",), ("fa-bullhorn", "info")),
    (("meter",), ("fa-gauge", "neutral")),
    (("incident",), ("fa-triangle-exclamation", "warn")),
]


def log_action_style(action):
    """Maps an audit/activity action string to (icon, tone)."""
    a = (action or "").lower()
    for keywords, style in _LOG_ACTION_RULES:
        if any(k in a for k in keywords):
            return style
    return ("fa-circle-info", "neutral")


def _fmt_log_time(value):
    """Short, readable timestamp for a log line — 'Jul 31, 03:07' instead
    of a raw ISO string with a microsecond-precision UTC offset."""
    dt = _parse_dt(value)
    if not dt:
        return str(value or "")[:16]
    return dt.strftime("%b %d, %H:%M")


def render_log_entries(entries, actor_key="user_name", action_key="action",
                       time_key="created_at", details_key="details",
                       action_verb=None):
    """Render a list of audit/activity rows as an icon timeline.

    `entries` is the raw list of dicts from Supabase (or the in-memory
    fallback) — no transformation of the underlying data happens here,
    this only changes how each row is drawn. `action_verb`, if given,
    is called as action_verb(entry) to build the human-readable phrase
    (e.g. to interpolate a task title); otherwise the raw action string
    is shown with underscores turned to spaces.
    """
    if not entries:
        st.info("Nothing logged yet.")
        return
    html = ['<div class="log-list">']
    for e in entries:
        action = e.get(action_key, "")
        icon, tone = log_action_style(action)
        actor = esc(e.get(actor_key, "Unknown"))
        when = esc(_fmt_log_time(e.get(time_key)))
        phrase = esc(action_verb(e)) if action_verb else esc(action.replace("_", " "))
        details = e.get(details_key)
        details_html = ""
        if details:
            details_str = details if isinstance(details, str) else json.dumps(details)
            if len(details_str) > 300:
                details_str = details_str[:300] + "…"
            details_html = f'<div class="log-details">{esc(details_str)}</div>'
        html.append(
            f'<div class="log-entry">'
            f'<div class="log-icon" style="--stat-color:var(--tone-{tone});'
            f'--stat-bg:var(--tone-{tone}-soft);"><i class="fas {icon}"></i></div>'
            f'<div class="log-body">'
            f'<div class="log-line"><span><b>{actor}</b> {phrase}</span>'
            f'<span class="log-time">{when}</span></div>'
            f'{details_html}'
            f'</div></div>'
        )
    html.append('</div>')
    st.markdown("".join(html), unsafe_allow_html=True)


_AVATAR_TONES = ["info", "ok", "warn", "danger", "neutral"]


def _person_initials(name):
    parts = [p for p in (name or "?").strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _person_tone(name):
    """Deterministic tone per name, so the same person always gets the
    same avatar color across sessions — not random, just hashed."""
    h = sum(ord(c) for c in (name or "?"))
    return _AVATAR_TONES[h % len(_AVATAR_TONES)]


def render_avatar_html(name):
    tone = _person_tone(name)
    initials = esc(_person_initials(name))
    return (f'<div class="chat-avatar" style="--stat-color:var(--tone-{tone});'
            f'--stat-bg:var(--tone-{tone}-soft);">{initials}</div>')


def generate_asset_qr(asset_id):
    """Generates a QR code encoding a structured, unambiguous asset
    identifier — 'MWDTS-ASSET:<id>' rather than the bare id or the
    asset_tag, so a scan can never be confused with some unrelated QR
    code someone happens to photograph, and doesn't depend on
    asset_tag being unique (only the database id is guaranteed to be).
    Uses the exact same proven method as the app's own install QR
    codes: reportlab's real encoder for the module grid, rendered with
    PIL using NEAREST-neighbor scaling specifically — smoothing/
    anti-aliasing is what silently broke a QR code earlier this
    project by blurring the sharp module edges decoding depends on.
    Returns a PIL Image, or None if the optional dependencies aren't
    installed.
    """
    if not QR_GENERATION_AVAILABLE:
        return None
    payload = f"MWDTS-ASSET:{asset_id}"
    widget = _qr_encoder.QrCodeWidget(payload)
    widget.qr.make()
    inner = widget.qr
    module_count = inner.getModuleCount()

    px_per_module = 10
    quiet_zone = 4
    size = (module_count + quiet_zone * 2) * px_per_module
    img = Image.new("RGB", (size, size), "white")
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    for row in range(module_count):
        for col in range(module_count):
            if inner.isDark(row, col):
                x0 = (col + quiet_zone) * px_per_module
                y0 = (row + quiet_zone) * px_per_module
                d.rectangle([x0, y0, x0 + px_per_module, y0 + px_per_module], fill="black")
    return img


def decode_asset_qr(image_bytes):
    """Decodes a photographed QR label back into an asset id. Returns
    the asset id (int) on a genuine MWDTS asset QR, None on anything
    else — an unrelated QR code, a blurry photo, or no QR code at all
    all return None rather than raising, since a failed scan is an
    expected, ordinary outcome here, not an error condition."""
    if not QR_SCANNING_AVAILABLE:
        return None
    try:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        detector = cv2.QRCodeDetector()
        data, points, _ = detector.detectAndDecode(img)
        if data and data.startswith("MWDTS-ASSET:"):
            try:
                return int(data.split(":", 1)[1])
            except ValueError:
                return None
        return None
    except Exception:
        return None


def render_empty_state(icon, title, subtitle=None):
    """A warmer alternative to a bare st.info() for the moment a
    section has no data yet — a small icon in a soft circle, a short
    title, and an optional line of context underneath. Deliberately
    not applied to every empty-state message in the app: places like
    'no accounts locked out' or 'no decisions recorded' are
    reassuring administrative absences, not a first-impression moment
    worth the extra visual weight — this is for the core data
    sections a new user actually lands on."""
    sub_html = f'<div class="empty-sub">{esc(subtitle)}</div>' if subtitle else ""
    st.markdown(f"""
    <div class="empty-state">
        <div class="empty-icon"><i class="fas {esc(icon)}"></i></div>
        <div class="empty-title">{esc(title)}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)


def quick_filter(items, query, fields):
    """Case-insensitive substring filter across a list of dicts,
    checking the given field names. Shared across every list-heavy
    section (Tasks, Assets, Inventory, ...) so filtering behaves
    identically everywhere rather than each section growing its own
    slightly-different version. An empty query returns the list
    unchanged — the caller doesn't need its own "if not query" guard
    before calling this.
    """
    q = (query or "").strip().lower()
    if not q:
        return items
    return [
        item for item in items
        if any(q in str(item.get(f, "")).lower() for f in fields)
    ]


def render_progress_steps(steps, current_index, cancelled=False):
    """Renders a horizontal lifecycle tracker — e.g. a permit's
    Issued -> Accepted -> Signed Back progression. `steps` is a list
    of label strings; `current_index` is the position of the
    CURRENT step (everything before it renders as done/completed,
    everything after as not-yet-reached). `cancelled=True` overrides
    the current step to render in the danger tone instead, for a
    terminal state that isn't forward progress (a cancelled permit
    isn't "stuck partway through succeeding" — it's a different
    outcome entirely, and the visual should say so).
    """
    html = ['<div class="progress-steps">']
    for i, label in enumerate(steps):
        if cancelled and i == current_index:
            state = "cancelled"
            icon = "fa-xmark"
        elif i < current_index:
            state = "done"
            icon = "fa-check"
        elif i == current_index:
            state = "current"
            icon = "fa-circle-notch"
        else:
            state = ""
            icon = ""
        icon_html = f'<i class="fas {icon}"></i>' if icon else str(i + 1)
        html.append(
            f'<div class="progress-step {state}">'
            f'<div class="line"></div>'
            f'<div class="dot">{icon_html}</div>'
            f'<div>{esc(label)}</div>'
            f'</div>'
        )
    html.append('</div>')
    return "".join(html)


def render_action_cards(cards):
    """Renders a responsive grid of tappable-feeling shortcut cards —
    icon in a colored box, bold title, short description underneath.
    `cards` is a list of dicts with icon/title/desc/tone (tone is one
    of the same five established tones as render_stat_cards, so a
    shortcut card's color always means the same thing a badge or stat
    card's color already means elsewhere in the app).

    This doesn't navigate anywhere by itself — Streamlit can't make an
    arbitrary chunk of HTML clickable and trigger a rerun, so each
    card is paired with a real st.button by the caller. This function
    only renders the visual card; wiring it to navigate_to() is the
    caller's job, same division of responsibility as every other
    render_* helper in this file.
    """
    valid_tones = {"info", "ok", "warn", "danger", "neutral"}
    html = ['<div class="action-grid">']
    for c in cards:
        tone = c.get("tone", "info")
        if tone not in valid_tones:
            tone = "info"
        html.append(
            f'<div class="action-card" style="--stat-color:var(--tone-{tone});'
            f'--stat-bg:var(--tone-{tone}-soft);">'
            f'<div class="action-icon"><i class="fas {esc(c.get("icon", "fa-bolt"))}"></i></div>'
            f'<div class="action-title">{esc(c.get("title", ""))}</div>'
            f'<div class="action-desc">{esc(c.get("desc", ""))}</div>'
            f'</div>'
        )
    html.append('</div>')
    return "".join(html)


def render_field_grid(fields):
    """Render a set of labeled detail fields as a proper grid instead
    of the old '<p><i>Label:</i> value</p>' stack (still used before
    this — see the incident and handover cards).

    `fields` is a list of (icon, label, value, tone) tuples. Any field
    whose value is empty/None is automatically skipped, so callers
    don't need their own per-field `if x else ''` conditional — that
    was the actual source of the old pattern's clutter.

    Returns the HTML string rather than calling st.markdown directly,
    since callers embed this inside a larger card block rather than
    rendering it standalone.
    """
    items = [(icon, label, value, tone) for icon, label, value, tone in fields if value]
    if not items:
        return ""
    parts = ['<div class="field-grid">']
    for icon, label, value, tone in items:
        parts.append(
            f'<div class="field-card" style="--stat-color:var(--tone-{tone});">'
            f'<div class="field-label"><i class="fas {icon}"></i>{esc(label)}</div>'
            f'<div class="field-value">{esc(value)}</div>'
            f'</div>'
        )
    parts.append('</div>')
    return "".join(parts)


def render_meta_chips(chips):
    """Render a set of small metadata facts (location, reporter, time,
    etc.) as wrapping pill chips instead of one long inline text run
    joined by '&nbsp;' — on a narrow screen that run wraps mid-fact
    with no visual boundary between one piece of info and the next.

    `chips` is a list of (icon, text, tone) tuples. Empty/None text is
    skipped automatically. Returns an HTML string for embedding inside
    a larger card, same convention as render_field_grid.
    """
    items = [(icon, text, tone) for icon, text, tone in chips if text]
    if not items:
        return ""
    parts = ['<div class="meta-chips">']
    for icon, text, tone in items:
        parts.append(
            f'<span class="meta-chip" style="--stat-color:var(--tone-{tone});'
            f'--stat-bg:var(--tone-{tone}-soft);">'
            f'<i class="fas {icon}"></i>{esc(text)}</span>'
        )
    parts.append('</div>')
    return "".join(parts)


def selectbox_with_other(label, options, key_prefix, other_option="Other", help_text=None):
    """A dropdown that lets the person type their own value when none of
    the fixed options fit.

    IMPORTANT — why this doesn't conditionally show/hide the text field:
    every call site for this is inside st.form(...), and Streamlit forms
    do not rerun the script when a widget inside them changes — only
    st.form_submit_button() does. A "text box appears the instant you
    pick Other" pattern would silently lag a full submit cycle behind
    the actual selection, which is worse than not having it at all: the
    person types their answer into a box that looks live but isn't.

    Instead the companion text field is always visible, with a caption
    making clear it only takes effect when the dropdown above is set to
    other_option. This works correctly regardless of Streamlit's form
    rerun behavior, at the minor cost of one always-present input.

    Returns the single RESOLVED value — call sites don't need their own
    "if choice == 'Other'" branch, they just get the final string back.
    Only used for descriptive/display fields (category, type, etc.) —
    never for a field that drives status logic, badge styling, or
    analytics bucketing elsewhere in the app, since a free-typed value
    there would silently fall outside whatever exact strings that logic
    matches on.
    """
    opts = list(options)
    if other_option not in opts:
        opts.append(other_option)
    choice = st.selectbox(label, opts, key=f"{key_prefix}_select", help=help_text)
    custom = st.text_input(
        f'If "{other_option}", specify',
        key=f"{key_prefix}_custom",
        placeholder=f'Only used when {label} above is set to "{other_option}"',
    )
    if choice == other_option:
        custom = (custom or "").strip()
        return custom if custom else other_option
    return choice


def navigate_to(section_name):
    """Force the top nav to a specific section from anywhere else in the
    app (a sidebar button, a card's 'view details' link, etc).

    Why this exists: streamlit-option-menu has no key/session-state
    wiring by default, so a button elsewhere that sets some related
    piece of state (e.g. chat_room) and calls st.rerun() does NOT
    actually change which tab is showing — the nav just keeps rendering
    whatever it last had. This was silently broken for four sidebar
    buttons (Global Chat, Supervisor Room, Open Private Chat, My
    Profile) — clicking them changed data behind the scenes but never
    navigated anywhere, which looks like nothing happened.

    Also collapses the nav menu — landing on a section via a Quick
    Action card or a search result should feel the same as clicking
    its icon directly, not leave the menu bar sitting there as if
    nothing happened.

    Call this, then st.rerun(). The option_menu call reads and clears
    this flag via its manual_select parameter — the library's own
    documented mechanism for programmatic selection.
    """
    st.session_state["_nav_jump_to"] = section_name
    st.session_state["_active_section"] = section_name
    st.session_state["_nav_collapsed"] = True

# -------------------------------
# 2B. CENTRAL PERMISSION MATRIX
# -------------------------------
# All authorization decisions resolve through this one table so a
# security reviewer can audit the whole model in one place, rather
# than tracing scattered `if role in [...]` checks through the UI.
# Add a capability here, then gate the UI with can(role, "capability").
ROLE_PERMISSIONS = {
    "worker": {
        "task.view_assigned", "task.update_status", "task.comment",
        "task.upload_photo", "task.upload_attachment",
        "asset.view", "asset.log_meter",
        "inventory.view",
        "incident.report", "incident.view_own",
        "permit.accept", "permit.sign_back", "permit.view",
        "handover.view",
        "chat.global", "chat.private",
        "profile.edit_own",
    },
    "supervisor": {
        "task.view_all", "task.create", "task.assign", "task.update_status",
        "task.approve_qa", "task.comment", "task.upload_photo",
        "task.upload_attachment", "task.record_cost",
        "asset.view", "asset.create", "asset.edit", "asset.log_meter",
        "inventory.view", "inventory.create", "inventory.adjust", "inventory.record_usage",
        "incident.report", "incident.view_all", "incident.investigate",
        "permit.issue", "permit.accept", "permit.sign_back", "permit.view", "permit.cancel",
        "handover.view", "handover.create", "handover.acknowledge",
        "contractor.view", "contractor.manage",
        "analytics.view", "analytics.export",
        "feedback.manage",
        "broadcast.send",
        "chat.global", "chat.private", "chat.supervisor_room",
        "profile.edit_own",
    },
    "superintendent": {
        "task.view_all", "task.create", "task.assign", "task.update_status",
        "task.approve_qa", "task.comment", "task.delete", "task.upload_photo",
        "task.upload_attachment", "task.record_cost",
        "asset.view", "asset.create", "asset.edit", "asset.delete", "asset.log_meter",
        "inventory.view", "inventory.create", "inventory.adjust",
        "inventory.record_usage", "inventory.delete",
        "incident.report", "incident.view_all", "incident.investigate",
        "permit.issue", "permit.accept", "permit.sign_back", "permit.view", "permit.cancel",
        "handover.view", "handover.create", "handover.acknowledge",
        "contractor.view", "contractor.manage",
        "analytics.view", "analytics.export",
        "feedback.manage",
        "broadcast.send",
        "chat.global", "chat.private", "chat.supervisor_room",
        "user.approve", "user.reject", "user.deactivate", "user.view_all",
        "audit.view",
        "profile.edit_own",
    },
}

# The owner tier is NOT a role in this table. Owner status is resolved
# from OWNER_USERNAME in secrets (see is_owner), and owner-only screens
# check is_owner() directly rather than can(). Keeping it out of the
# role matrix means it cannot be granted by editing a user's role.
OWNER_CAPABILITIES = {
    "access.view_requests", "access.approve", "access.deny",
    "access.set_role", "access.suspend", "access.remove",
    "access.view_history",
}


def can(user_role, capability):
    """Single authorization entry point. Unknown roles get nothing."""
    if not user_role:
        return False
    return capability in ROLE_PERMISSIONS.get(str(user_role).strip().lower(), set())

def require(user_role, capability, message="You do not have permission to do that."):
    """Gate a UI block. Returns True if allowed, else renders a notice."""
    if can(user_role, capability):
        return True
    st.warning(f"🔒 {message}")
    return False

# -------------------------------
# 2C. LOGIN RATE LIMITING
# -------------------------------
# LIMITATION — READ BEFORE RELYING ON THIS:
# These counters live in Streamlit session state, so they stop
# casual repeated guessing in one browser session but do NOT stop a
# determined attacker, who can simply open a new session to reset
# the counter. Real brute-force protection needs server-side
# tracking keyed on username/IP (a `login_attempts` table, or an
# edge/WAF rate limit), and is one of the things you get for free
# by migrating to Supabase Auth. Treat this as a speed bump, not a
# control you can present as sufficient in a security review.
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15

def _login_state():
    if 'login_attempts' not in st.session_state:
        st.session_state.login_attempts = {}
    return st.session_state.login_attempts

def is_login_locked(username):
    """Returns (locked, seconds_remaining)."""
    attempts = _login_state().get(str(username).lower())
    if not attempts:
        return False, 0
    if attempts.get("count", 0) < LOGIN_MAX_ATTEMPTS:
        return False, 0
    last = attempts.get("last_attempt")
    if not last:
        return False, 0
    unlock_at = last + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
    if datetime.now() >= unlock_at:
        _login_state().pop(str(username).lower(), None)
        return False, 0
    return True, int((unlock_at - datetime.now()).total_seconds())

def record_login_failure(username):
    key = str(username).lower()
    state = _login_state()
    entry = state.get(key, {"count": 0})
    entry["count"] = entry.get("count", 0) + 1
    entry["last_attempt"] = datetime.now()
    state[key] = entry
    if entry["count"] >= LOGIN_MAX_ATTEMPTS:
        log_audit(username, "login_lockout", {"attempts": entry["count"]})

def clear_login_failures(username):
    _login_state().pop(str(username).lower(), None)


def create_session_token(username):
    """Generates an unguessable token allowing login to survive a hard
    refresh — Streamlit's session_state is tied to the live browser
    connection and is genuinely lost on one, so without this the
    person is dropped back to the login screen every time.

    Stored in the URL via st.query_params, which does mean the token
    is visible in the address bar — mitigated by the short expiry
    (SESSION_TIMEOUT_MINUTES, already 60 min by default) and immediate
    invalidation on explicit logout, but a copied URL while the token
    is still valid could let someone else resume the session. This
    trade-off was discussed and accepted rather than silently made.
    """
    token = secrets.token_hex(32)
    expires_at = datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    if not SUPABASE_AVAILABLE:
        sessions = st.session_state.get("active_sessions_memory", [])
        sessions.append({"session_token": token, "username": username,
                        "created_at": datetime.now().isoformat(), "expires_at": expires_at.isoformat()})
        st.session_state.active_sessions_memory = sessions
        return token
    try:
        res = supabase.table("active_sessions").insert({
            "session_token": token, "username": username, "expires_at": expires_at.isoformat(),
        }).execute()
        if res.data:
            return token
        log_error("active_sessions insert affected 0 rows — likely RLS blocking writes.",
                 endpoint="create_session_token")
        return None
    except Exception as e:
        log_error(str(e), endpoint="create_session_token")
        return None


def validate_session_token(token):
    """Returns the username if the token exists and hasn't expired,
    None otherwise. Expiry is checked in Python against the stored
    timestamp rather than trusting a database-side filter alone —
    this must fail closed: any ambiguity about whether a token is
    still valid should end in "log in again," never in silently
    granting access on a token that might have expired.
    """
    if not token:
        return None
    if not SUPABASE_AVAILABLE:
        sessions = st.session_state.get("active_sessions_memory", [])
        match = next((s for s in sessions if s["session_token"] == token), None)
        if not match:
            return None
        if datetime.fromisoformat(match["expires_at"]) < datetime.now():
            return None
        return match["username"]
    try:
        res = supabase.table("active_sessions").select("*").eq("session_token", token).execute()
        if not res.data:
            return None
        match = res.data[0]
        expires_at = _parse_dt(match.get("expires_at"))
        if not expires_at or expires_at < datetime.now():
            return None
        return match["username"]
    except Exception as e:
        log_error(str(e), endpoint="validate_session_token")
        return None


def invalidate_session_token(token):
    """Deletes the token — called on explicit logout so a stale URL
    stops working immediately rather than waiting out its expiry.
    """
    if not token:
        return
    if not SUPABASE_AVAILABLE:
        sessions = st.session_state.get("active_sessions_memory", [])
        st.session_state.active_sessions_memory = [s for s in sessions if s["session_token"] != token]
        return
    try:
        supabase.table("active_sessions").delete().eq("session_token", token).execute()
    except Exception as e:
        log_error(str(e), endpoint="invalidate_session_token")

# -------------------------------
# 3. ERROR LOGGING
# -------------------------------
def log_error(error_message, details=None, user_name=None, endpoint=None):
    """Log errors to the app_errors table for monitoring.

    Also classifies whether this specific failure looks like a
    connectivity problem (dropped connection, timeout, DNS failure)
    rather than a genuine data/permission issue, setting a session
    flag the UI can check right after a failed save to show "check
    your connection" instead of a generic failure message. This is
    the one shared place nearly every backend function's exception
    handler already calls — extending it here reaches all of them
    without changing any function's return signature or touching each
    call site individually, which would have been a much larger,
    riskier change for the same result.
    """
    _err_lower = str(error_message).lower()
    _connectivity_signals = [
        "connection", "timeout", "timed out", "max retries exceeded",
        "failed to establish a new connection", "network is unreachable",
        "name or service not known", "getaddrinfo failed", "temporary failure in name resolution",
    ]
    try:
        st.session_state["_last_error_was_connectivity"] = any(
            sig in _err_lower for sig in _connectivity_signals)
    except Exception:
        pass  # log_error must never itself be the thing that crashes a page

    if not SUPABASE_AVAILABLE:
        return
    try:
        supabase.table("app_errors").insert({
            "error_message": str(error_message)[:500],
            "error_details": json.dumps(details) if details else None,
            "user_name": user_name,
            "endpoint": endpoint
        }).execute()
    except Exception:
        pass  # If logging fails, we can't do much else

# -------------------------------
# 4. PASSWORD HASHING & STRENGTH
# -------------------------------
def hash_password(password):
    if BCRYPT_AVAILABLE:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode(), salt).decode()
    else:
        salt = os.urandom(32)
        hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return base64.b64encode(salt + hashed).decode()

def verify_password(password, hashed):
    if BCRYPT_AVAILABLE:
        try:
            if bcrypt.checkpw(password.encode(), hashed.encode()):
                return True
        except ValueError:
            pass
    try:
        data = base64.b64decode(hashed.encode())
        salt = data[:32]
        stored_hash = data[32:]
        computed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return computed == stored_hash
    except Exception:
        return False

def is_strong_password(password):
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit."
    special_chars = "!@#$%^&*()_+-=[]{};:'\"\\|,.<>/?"
    if not any(c in special_chars for c in password):
        return False, "Password must contain at least one special character."
    return True, ""

# -------------------------------
# 5. AUDIT LOG
# -------------------------------
def log_audit(user_name, action, details=None):
    if not SUPABASE_AVAILABLE:
        return
    try:
        supabase.table("audit_log").insert({
            "user_name": user_name,
            "action": action,
            "details": json.dumps(details) if details else None
        }).execute()
    except Exception:
        pass

# -------------------------------
# 6. EMAIL NOTIFICATION
# -------------------------------
def send_email_notification(recipient, subject, body_html, _return_error=False):
    """Send an email. Returns True/False, or (bool, error_str) if
    _return_error=True — used by the Owner Console health check so a
    misconfiguration shows the actual SMTP error instead of a bare
    failure.

    Sends multipart/alternative with a plain-text fallback alongside
    the HTML. Plain text matters here for two practical reasons: some
    site email gateways strip or quarantine HTML-only mail more
    aggressively, and a plain fallback still gets read on a phone with
    a broken mail-app renderer.
    """
    if not recipient:
        return (False, "No recipient") if _return_error else False
    smtp_server = st.secrets.get("SMTP_SERVER")
    smtp_port = st.secrets.get("SMTP_PORT", 587)
    smtp_user = st.secrets.get("SMTP_USER")
    smtp_password = st.secrets.get("SMTP_PASSWORD")
    smtp_from = st.secrets.get("SMTP_FROM", smtp_user)
    if not all([smtp_server, smtp_user, smtp_password]):
        return (False, "SMTP not configured") if _return_error else False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        plain_text = body_html
        plain_text = re.sub(r"<br\s*/?>", "\n", plain_text, flags=re.I)
        plain_text = re.sub(r"</p>", "\n\n", plain_text, flags=re.I)
        plain_text = re.sub(r"<[^>]+>", "", plain_text)
        plain_text = re.sub(r"\n{3,}", "\n\n", plain_text).strip()
        msg = MIMEMultipart("alternative")
        msg['From'] = smtp_from
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(plain_text, 'plain'))
        msg.attach(MIMEText(body_html, 'html'))
        with smtplib.SMTP(smtp_server, int(smtp_port), timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return (True, "") if _return_error else True
    except Exception as e:
        _err = f"{type(e).__name__}: {e}"
        log_error(_err, details={"recipient": recipient, "subject": subject},
                  endpoint="send_email")
        return (False, _err) if _return_error else False

# -------------------------------
# 7. SLACK / TEAMS WEBHOOK INTEGRATION
# -------------------------------
def send_slack_notification(message, _return_error=False):
    if not SLACK_WEBHOOK:
        return (False, "Slack webhook not configured") if _return_error else False
    try:
        payload = {"text": message}
        resp = requests.post(SLACK_WEBHOOK, json=payload, timeout=5)
        resp.raise_for_status()
        return (True, "") if _return_error else True
    except Exception as e:
        _err = f"{type(e).__name__}: {e}"
        log_error(_err, endpoint="slack")
        return (False, _err) if _return_error else False

def send_teams_notification(message, _return_error=False):
    """Posts to a Teams incoming webhook using the MessageCard format.

    IMPORTANT, time-sensitive context: Microsoft retired the old-style
    "Office 365 Connector" webhooks in a rollout completing May 22,
    2026 — a webhook URL obtained through that legacy setup will no
    longer work. The current, correct way to get a Teams webhook URL
    is via the Workflows app's "When a Teams webhook request is
    received" trigger template, not the old Connectors page. The
    MessageCard payload format used below is still explicitly
    supported through Workflows, so no payload change was needed —
    only awareness that HOW the URL is obtained changed, not the
    format sent to it.
    """
    if not TEAMS_WEBHOOK:
        return (False, "Teams webhook not configured") if _return_error else False
    try:
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": "MWDTS Notification",
            "themeColor": "001530",
            "title": "MWDTS Notification",
            "text": message,
        }
        resp = requests.post(TEAMS_WEBHOOK, json=payload, timeout=5)
        resp.raise_for_status()
        return (True, "") if _return_error else True
    except Exception as e:
        _err = f"{type(e).__name__}: {e}"
        log_error(_err, endpoint="teams")
        return (False, _err) if _return_error else False

def send_external_notifications(message):
    send_slack_notification(message)
    send_teams_notification(message)

# -------------------------------
# 7B. AI-ASSISTED FEATURES (Smart Descriptions, Severity Prediction)
# -------------------------------
def generate_smart_text(prompt, max_tokens=300, _return_error=False):
    """Calls whichever AI provider is configured — Anthropic if its key
    is set, otherwise OpenAI. Shared by all AI-assisted features
    (Smart Work Order Descriptions, Incident Severity Prediction,
    Maintenance Assistant) rather than each having its own separate
    API-calling logic, so a provider or model change only needs to
    happen in one place.

    `prompt` is EITHER a plain string (single-turn — wrapped into a
    one-message list internally, existing single-turn callers are
    unaffected) OR a list of {"role": "user"/"assistant", "content":
    ...} dicts for genuine multi-turn conversation. Both Anthropic and
    OpenAI natively accept a messages array in this same shape, so
    this needed no provider-specific special-casing.

    Returns the generated text (str), or None on any failure — a down
    API, a bad key, a network timeout, or neither provider configured
    at all. This must never be the thing that blocks someone from
    creating a task or reporting an incident just because a third-party
    AI service had a bad moment; callers fall back to the person's own
    typed input, not this failing outright.
    """
    messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]

    if ANTHROPIC_API_KEY:
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": max_tokens,
                    "messages": messages,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
            return (text, "") if _return_error else text
        except Exception as e:
            _err = f"{type(e).__name__}: {e}"
            log_error(_err, endpoint="generate_smart_text_anthropic")
            return (None, _err) if _return_error else None

    if OPENAI_API_KEY:
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": OPENAI_MODEL,
                    "max_tokens": max_tokens,
                    "messages": messages,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            return (text, "") if _return_error else text
        except Exception as e:
            _err = f"{type(e).__name__}: {e}"
            log_error(_err, endpoint="generate_smart_text_openai")
            return (None, _err) if _return_error else None

    if GEMINI_API_KEY:
        try:
            # Gemini's request shape genuinely differs from the shared
            # messages format used above — a "contents" array of
            # {"role", "parts": [{"text": ...}]} rather than
            # {"role", "content"}, and it names the model's own prior
            # turns "model", not "assistant" (verified directly against
            # Google's current API docs before writing this, not
            # assumed from general familiarity with other providers).
            gemini_contents = [
                {"role": "user" if m["role"] == "user" else "model",
                 "parts": [{"text": m["content"]}]}
                for m in messages
            ]
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
                headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                json={
                    "contents": gemini_contents,
                    "generationConfig": {"maxOutputTokens": max_tokens},
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return (text, "") if _return_error else text
        except Exception as e:
            _err = f"{type(e).__name__}: {e}"
            log_error(_err, endpoint="generate_smart_text_gemini")
            return (None, _err) if _return_error else None

    return (None, "No AI provider configured") if _return_error else None


def generate_smart_work_order_description(brief_notes):
    """Expands a supervisor's brief, shorthand notes into a clearer,
    fuller work order description. Returns None on failure — the
    caller must fall back to the supervisor's own raw notes, not
    block task creation on an AI call succeeding.
    """
    prompt = (
        "You are helping a mine maintenance supervisor write a clear work order "
        "description from their brief notes. Expand the following short, informal "
        "note into a clear, professional 2-4 sentence work order description. "
        "Do not invent specific details (part numbers, exact measurements, root "
        "causes) that weren't in the original note — only clarify and expand the "
        "wording itself. Return ONLY the description text, no preamble.\n\n"
        f"Supervisor's notes: {brief_notes}"
    )
    return generate_smart_text(prompt, max_tokens=200)


def predict_incident_severity(incident_type, description):
    """Suggests a severity level from the incident description — a
    SUGGESTION ONLY, always shown as one to be reviewed and confirmed
    by the person reporting, never auto-applied to the actual form
    field. Getting a severity wrong has real consequences (a
    misclassified "Low" delaying an appropriately urgent response),
    so the response is validated strictly against the exact 4
    canonical values this app uses elsewhere — returns None (not a
    guess, not the closest-sounding word) if the AI's response
    doesn't cleanly match one of them, rather than risk silently
    coercing something unexpected into a specific severity claim.
    """
    valid_severities = {"Low", "Medium", "High", "Critical"}
    prompt = (
        "You are helping assess the severity of a mine safety incident. Based on the "
        "incident type and description below, respond with EXACTLY ONE WORD: Low, "
        "Medium, High, or Critical. No other text, no explanation, no punctuation — "
        "just the single severity word.\n\n"
        f"Incident type: {incident_type}\n"
        f"Description: {description}"
    )
    result = generate_smart_text(prompt, max_tokens=10)
    if not result:
        return None
    cleaned = result.strip().strip(".").strip()
    return cleaned if cleaned in valid_severities else None


def get_app_context_summary(tasks, assets, incidents, parts_lookup):
    """A compact, current-data snapshot fed to the Maintenance
    Assistant chatbot as grounding context — the whole point being
    that it answers from what's ACTUALLY in the app right now, not
    from whatever an LLM might otherwise guess or hallucinate about a
    mine site it has no real access to.

    Deliberately a summary, not a full data dump — the underlying
    tasks/incidents lists can run into the hundreds, which would
    blow past a reasonable prompt size and cost. Reuses functions
    already established elsewhere (safety_leading_indicators,
    compute_mtbf_hours, cost_by_category) rather than recalculating
    the same numbers a different way here.

    Also includes the full How It Works guide (~1,600 tokens,
    reasonable to send in full rather than truncate) — this is what
    lets the assistant answer "how do I..." questions about a
    feature's actual workflow, not just its data. Same grounding
    principle either way: answer from what's actually documented in
    this app, never guessed.
    """
    open_tasks = [t2 for t2 in tasks if t2.get("status") != "Complete"]
    overdue_tasks = [t2 for t2 in open_tasks if t2.get("due_date")
                     and (_parse_dt(t2["due_date"]) or datetime.max) < datetime.now()]
    si = safety_leading_indicators(incidents, tasks)
    mtbf, mtbf_n = compute_mtbf_hours(tasks)
    cost_cats = cost_by_category(tasks, parts_lookup)
    top_cost_cat = cost_cats[0] if cost_cats else None

    lines = [
        f"Open tasks: {len(open_tasks)} (of which {len(overdue_tasks)} overdue)",
        f"Total assets tracked: {len(assets)}",
        f"Incidents in last 30 days: {si['last_30_days']} (near-misses/hazards: {si['proactive_reports']}, injuries: {si['injuries']})",
        f"MTBF (mean time between failures): {f'{mtbf:.0f} hours' if mtbf is not None else 'not enough data yet'}",
    ]
    if top_cost_cat:
        lines.append(f"Highest-cost work category: {top_cost_cat['category']} (total: {top_cost_cat['total_cost']:,.2f})")
    if overdue_tasks:
        lines.append("Overdue task titles: " + "; ".join(t2.get("title", "") for t2 in overdue_tasks[:10]))

    lines.append("\n--- How each app feature works (use this to answer 'how do I...' questions) ---")
    for category, features in HOW_IT_WORKS_GUIDE.items():
        lines.append(f"\n{category}:")
        for name, desc in features.items():
            lines.append(f"- {name}: {desc}")

    return "\n".join(lines)


def ask_maintenance_assistant(question, context_summary, conversation_history=None):
    """Answers a question grounded in the current app data summary,
    with genuine multi-turn memory of earlier questions in the same
    session when conversation_history is provided.

    conversation_history, if given, is a list of {"role": "user"/
    "assistant", "content": ...} dicts from earlier turns — appended
    to before this question, so the AI can resolve follow-ups like
    "what about the other one?" against what was actually asked and
    answered earlier, not just this single question in isolation.
    """
    system_context = (
        "You are a maintenance assistant for a mine's task and asset tracking system. "
        "Answer the user's question using ONLY the data summary below — do not invent "
        "specific numbers, asset names, or task details that aren't in it. If the "
        "summary doesn't contain enough information to answer, say so plainly rather "
        "than guessing. Keep answers concise (2-4 sentences unless more detail is "
        "clearly needed).\n\n"
        f"Current data summary:\n{context_summary}"
    )
    messages = list(conversation_history) if conversation_history else []
    # The system context rides on THIS turn's question rather than a
    # separate system-role message — keeps the data summary current
    # even mid-conversation (it's regenerated fresh each call from
    # live app data), rather than baked into a system message from
    # whenever the conversation started.
    messages.append({"role": "user", "content": f"{system_context}\n\nQuestion: {question}"})
    return generate_smart_text(messages, max_tokens=300)

# 8. IMAGE & ATTACHMENT VALIDATION
# -------------------------------
def validate_image(file_bytes, filename):
    ext = filename.split('.')[-1].lower()
    if ext not in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']:
        return False, "Only image files (jpg, png, gif, bmp, webp) are allowed."
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        return False, f"File size exceeds {MAX_UPLOAD_SIZE_MB} MB."
    if PIL_AVAILABLE:
        try:
            img = Image.open(BytesIO(file_bytes))
            img.verify()
            return True, "Valid image."
        except Exception:
            return False, "Invalid or corrupt image file."
    return True, "Valid image."

def validate_attachment(file_bytes, filename):
    if not filename or '.' not in filename:
        return False, "File must have a valid extension."
    ext = filename.split('.')[-1].lower()
    if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
        return False, f"File type '.{ext}' is not allowed. Allowed types: {', '.join(ALLOWED_ATTACHMENT_EXTENSIONS)}."
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        return False, f"File size exceeds {MAX_UPLOAD_SIZE_MB} MB."
    return True, "Valid attachment."

# -------------------------------
# 9. USER FUNCTIONS
# -------------------------------
def get_default_users():
    """Demo accounts — ONLY available when there is no database.

    SECURITY: these previously loaded in production too, which meant
    anyone who could reach the app could log in as Superintendent with
    the publicly-known password below and get delete rights, user
    management, and the audit log. They are now hard-gated on
    SUPABASE_AVAILABLE being False, so they cannot exist once a real
    database is connected.
    """
    if SUPABASE_AVAILABLE:
        return []
    return [
        {"username": "supervisor1", "full_name": "Demo Supervisor", "role": "Supervisor",
         "password_hash": hash_password("super789"), "email": None,
         "avatar_url": None, "is_approved": True, "_is_demo": True},
        {"username": "superintendent1", "full_name": "Demo Superintendent", "role": "Superintendent",
         "password_hash": hash_password("boss000"), "email": None,
         "avatar_url": None, "is_approved": True, "_is_demo": True},
        {"username": "worker1", "full_name": "Demo Worker", "role": "Worker",
         "password_hash": hash_password("worker123"), "email": None,
         "avatar_url": None, "is_approved": True, "_is_demo": True},
    ]


# =====================================================================
# SUPABASE AUTH MIGRATION — STEP 1: email mapping (schema-only, no
# change to login behavior yet)
# =====================================================================
def _sanitize_email_localpart(username):
    """Turn an arbitrary username into a safe email local-part.
    Usernames have no character restrictions at registration (no
    regex validation exists there), so this can't assume the input is
    already email-safe — spaces, apostrophes, anything is possible."""
    s = (username or "").strip().lower()
    s = re.sub(r'[^a-z0-9.\-_]', '-', s)
    s = re.sub(r'-+', '-', s).strip('-.')
    return s or "user"


def _looks_like_real_email(value):
    """Pragmatic check, not full RFC validation — just enough to
    decide 'does this look like a real address' vs 'empty/garbage'."""
    if not value:
        return False
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', value.strip()))


def compute_auth_email(username, existing_email):
    """Returns the email Supabase Auth would use for this person.
    Uses their real email if they have one; otherwise a placeholder
    that's never shown or emailed anywhere — it exists only because
    Supabase Auth requires SOME email per account.

    The placeholder always includes a hash of the full original
    username, not just the sanitized version — this guarantees
    uniqueness by construction (since username is already unique)
    rather than needing to detect and react to collisions after the
    fact. ".invalid" is the IANA-reserved TLD specifically meant for
    this kind of placeholder use (RFC 2606) — guaranteed to never
    resolve to a real domain, unlike making up something that could
    theoretically be real.
    """
    if _looks_like_real_email(existing_email):
        return existing_email.strip().lower()
    local = _sanitize_email_localpart(username)
    suffix = hashlib.md5((username or "").encode()).hexdigest()[:6]
    return f"{local}-{suffix}@placeholder.invalid"


def preview_auth_email_backfill():
    """Computes what EVERY user's auth_email would become, without
    writing anything — for the owner to review before committing.
    Also flags real-email duplicates across different accounts, since
    Supabase Auth requires unique emails and that's a data problem
    only a human should resolve, not something to silently patch."""
    users = fetch_all_users_from_db()
    rows = []
    seen_real_emails = {}
    for u in users:
        username = u.get("username")
        existing_email = u.get("email")
        computed = compute_auth_email(username, existing_email)
        is_placeholder = computed.endswith("@placeholder.invalid")
        rows.append({
            "username": username,
            "full_name": u.get("full_name"),
            "current_email": existing_email or "",
            "computed_auth_email": computed,
            "is_placeholder": is_placeholder,
            # Renamed from "already_migrated" — that label was genuinely
            # misleading, since it only ever checked whether Phase 1's
            # auth_email is set, not whether a real Supabase Auth
            # account exists (that's Phase 2's separate, correct gate
            # in preview_auth_provisioning below, which checks
            # auth_user_id specifically). Someone reading "already
            # migrated: true" here could reasonably think Phase 2 was
            # already done, when it wasn't.
            "email_already_mapped": bool(u.get("auth_email")),
        })
        if not is_placeholder:
            seen_real_emails.setdefault(computed, []).append(username)

    duplicates = {email: usernames for email, usernames in seen_real_emails.items()
                 if len(usernames) > 1}
    return rows, duplicates


def run_auth_email_backfill(usernames_to_migrate, performed_by):
    """Writes auth_email for the given usernames only — never all
    users blindly, so the owner can exclude anything flagged in the
    preview (like the duplicate-email case) and handle it manually
    first. Returns (success_count, failures) — failures is a list of
    (username, reason) so a partial run is fully diagnosable rather
    than an opaque 'some failed'."""
    users = {u["username"]: u for u in fetch_all_users_from_db()}
    success, failures = 0, []
    for username in usernames_to_migrate:
        u = users.get(username)
        if not u:
            failures.append((username, "user not found"))
            continue
        auth_email = compute_auth_email(username, u.get("email"))
        if update_user_profile(username, {"auth_email": auth_email}):
            success += 1
        else:
            failures.append((username, "write failed — check Row Level Security"))
    log_audit(performed_by, "auth_email_backfill", {
        "requested": len(usernames_to_migrate), "succeeded": success, "failed": len(failures)
    })
    return success, failures


# =====================================================================
# SUPABASE AUTH MIGRATION — PHASE 2 (provision real Auth accounts)
# =====================================================================
# See MIGRATION_PLAN.md. Still non-disruptive — these accounts exist
# in parallel with the old bcrypt login, which keeps working exactly
# as before until Phase 4 explicitly switches login over. Nobody is
# forced onto a new account by anything in this phase.
def preview_auth_provisioning():
    """Everyone with an auth_email (Phase 1 output) but no
    auth_user_id yet — i.e. mapped, but no real Supabase Auth account
    created for them. Read-only; creates nothing."""
    users = fetch_all_users_from_db()
    return [u for u in users if u.get("auth_email") and not u.get("auth_user_id")]


def provision_auth_accounts(usernames_to_provision, performed_by):
    """Creates a real Supabase Auth account for each given username,
    via the Admin API (requires supabase_admin — the service_role/
    secret-key client, never the ordinary anon-key one). Returns
    (success_count, failures) — failures is a list of (username,
    reason), same convention as run_auth_email_backfill.

    email_confirm=True is set at creation time deliberately, rather
    than relying on a project-wide 'disable email confirmation'
    setting — this marks only THESE synthetic-address accounts as
    pre-confirmed without touching how confirmation works for anyone
    who later signs up with a real, genuinely unconfirmed email.

    Idempotent in the sense that matters: if an account with this
    email already exists in Supabase Auth (e.g. a retry after a
    partial previous run), that specific user is reported as a
    failure with a clear reason rather than guessed-at and silently
    re-linked — linking the wrong Auth account to the wrong person is
    exactly the kind of mistake that should require a human to look
    at it, not code that assumes it knows best.
    """
    if not SUPABASE_ADMIN_AVAILABLE:
        return 0, [("(all)", "Admin client not configured — "
                   "SUPABASE_SERVICE_ROLE_KEY is missing. See MIGRATION_PLAN.md Phase 2.")]

    users = {u["username"]: u for u in fetch_all_users_from_db()}
    success, failures = 0, []
    for username in usernames_to_provision:
        u = users.get(username)
        if not u:
            failures.append((username, "user not found"))
            continue
        if u.get("auth_user_id"):
            failures.append((username, "already provisioned — skipped"))
            continue
        auth_email = u.get("auth_email")
        if not auth_email:
            failures.append((username, "no auth_email set — run Phase 1 backfill first"))
            continue

        temp_password = secrets.token_urlsafe(24)
        try:
            res = supabase_admin.auth.admin.create_user({
                "email": auth_email,
                "password": temp_password,
                "email_confirm": True,
            })
            new_user = getattr(res, "user", None)
            new_uuid = getattr(new_user, "id", None) if new_user else None
            if not new_uuid:
                failures.append((username, "Admin API returned no user ID — unexpected response shape"))
                continue
        except Exception as e:
            msg = str(e)
            if "already" in msg.lower() or "registered" in msg.lower() or "exists" in msg.lower():
                failures.append((username, f"an Auth account for {auth_email} already exists — "
                               "not auto-linked; verify by hand in the Supabase dashboard "
                               "(Authentication > Users) before deciding how to proceed"))
            else:
                log_error(msg, details={"username": username, "auth_email": auth_email},
                         endpoint="provision_auth_accounts")
                failures.append((username, f"Admin API error: {msg[:120]}"))
            continue

        linked = update_user_profile(username, {
            "auth_user_id": new_uuid,
            "auth_migrated_at": datetime.now().isoformat(),
            "must_change_password": True,
        })
        if not linked:
            # The Auth account now genuinely exists even though this
            # specific write failed — surfaced distinctly so it's clear
            # this isn't "nothing happened", it's "half happened".
            failures.append((username, f"Auth account created (id {new_uuid}) but linking it back to "
                           "facility_users failed — check Row Level Security, then link auth_user_id "
                           "manually rather than re-running (re-running would try to create a second "
                           "Auth account for the same email and fail)."))
            continue

        success += 1

    log_audit(performed_by, "auth_provisioning", {
        "requested": len(usernames_to_provision), "succeeded": success, "failed": len(failures)
    })
    return success, failures


def fetch_all_users_from_db():
    """Return real users. Demo accounts appear only in demo mode.

    SECURITY: the previous version let hardcoded accounts SHADOW real
    ones — a genuine 'superintendent1' in the database was discarded in
    favour of the built-in copy with the known password. Database
    records now always win.
    """
    if not SUPABASE_AVAILABLE:
        return get_default_users()

    try:
        res = supabase.table("facility_users").select("*").execute()
        return res.data if res.data else []
    except Exception as e:
        log_error(str(e), endpoint="fetch_users")
        # Fail CLOSED. Returning demo accounts here would reintroduce the
        # known-password login the moment the database has a hiccup.
        return []


# =====================================================================
# OWNER / ACCESS CONTROL
# =====================================================================
# The owner is the person who runs this deployment. Owner status is
# resolved from OWNER_USERNAME in secrets.toml — NOT from a database
# column and NOT from anything settable in the UI.
#
# Why: if "owner" were a role stored in facility_users, then anyone who
# could write that table (directly via the anon key, or through any bug
# in the role-editing screens) could make themselves owner. Anchoring it
# to a secret means seizing it requires access to the deployment
# configuration, which is a much higher bar than access to the app.
#
# Consequence to be aware of: if you lose OWNER_USERNAME you must edit
# secrets.toml to recover. There is deliberately no in-app path.
# =====================================================================

OWNER_USERNAME = str(_secret_get("OWNER_USERNAME", "") or "").strip().lower()


def is_owner(username):
    """True only for the single configured owner account."""
    if not OWNER_USERNAME or not username:
        return False
    return str(username).strip().lower() == OWNER_USERNAME


def owner_is_configured():
    return bool(OWNER_USERNAME)


def friendly_db_error(err):
    """Translate a raw Supabase/PostgREST error into something actionable.

    Specifically catches the 'column does not exist in schema cache'
    class of error — this happens whenever code references a column
    that schema_additions.sql adds but that hasn't actually been run
    against this database yet. It's easy to hit this once (fix it),
    then hit a DIFFERENT missing column later from a different feature,
    and not recognize it as the same root cause each time. This makes
    that connection explicit instead of showing a bare PGRST204.

    Also catches connection/timeout failures specifically — the
    difference between "your save failed because of a real problem"
    and "your save failed because your connection dropped" matters:
    the first needs a report or a fix, the second just needs a retry.
    Streamlit is server-rendered, so there's no way to genuinely queue
    an action and sync it later when truly offline (see
    MIGRATION_PLAN.md-adjacent notes on this) — but telling someone
    plainly "check your connection and try again" instead of a vague
    failure message is a real, honest improvement within that limit.
    Checked by message content rather than one specific exception
    class, since the exact type raised depends on which HTTP library
    is active underneath supabase-py at any given version.
    """
    err_str = str(err)
    if "PGRST204" in err_str or ("schema cache" in err_str.lower() and "column" in err_str.lower()):
        m = re.search(r"'([a-z_]+)' column", err_str)
        col = m.group(1) if m else "a required"
        return (f"{err_str}\n\n"
                f"→ This means the `{col}` column doesn't exist in your database yet. "
                f"Run the full `schema_additions.sql` in the Supabase SQL editor — "
                f"it's safe to run more than once (every statement checks IF NOT EXISTS "
                f"first). This is the same class of error as the earlier 'department "
                f"column' issue, just a different column this time.")

    connectivity_signals = [
        "connection", "timeout", "timed out", "max retries exceeded",
        "failed to establish a new connection", "network is unreachable",
        "name or service not known", "getaddrinfo failed", "temporary failure in name resolution",
    ]
    if any(sig in err_str.lower() for sig in connectivity_signals):
        return ("📶 This didn't save — it looks like your connection dropped or "
               "timed out, not a problem with what you entered. Check your network "
               "and try again; nothing was lost on your screen, so you don't need "
               "to re-type anything.")

    return err_str


def log_access_decision(target_username, target_full_name, action,
                        decided_by, old_role=None, new_role=None, reason=None):
    """Append-only record of an access decision."""
    payload = {
        "target_username": target_username,
        "target_full_name": target_full_name,
        "action": action,
        "old_role": old_role,
        "new_role": new_role,
        "reason": reason,
        "decided_by": decided_by,
    }
    if not SUPABASE_AVAILABLE:
        st.session_state.setdefault("access_decisions_memory", []).append(
            {**payload, "decided_at": datetime.now().isoformat()})
        return
    try:
        supabase.table("access_decisions").insert(payload).execute()
    except Exception as e:
        log_error(str(e), details=payload, endpoint="log_access_decision")


def fetch_access_decisions(limit=100):
    if not SUPABASE_AVAILABLE:
        rows = st.session_state.get("access_decisions_memory", [])
        return sorted(rows, key=lambda r: r.get("decided_at", ""), reverse=True)[:limit]
    try:
        res = (supabase.table("access_decisions").select("*")
               .order("decided_at", desc=True).limit(limit).execute())
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_access_decisions")
        return []


def approve_access(username, granted_role, decided_by, reason=None):
    """Approve a pending request AND set the granted role.

    The role granted here is authoritative — it deliberately overrides
    whatever the applicant selected at registration, so signing up as
    'Superintendent' confers nothing by itself.
    """
    if not SUPABASE_AVAILABLE:
        return False, "No database connected."
    if granted_role not in ("Worker", "Supervisor", "Superintendent"):
        return False, f"Invalid role: {granted_role}"
    try:
        target = supabase.table("facility_users").select("*").eq("username", username).execute()
        if not target.data:
            return False, "User not found."
        old_role = target.data[0].get("role")
        full_name = target.data[0].get("full_name")
        res = supabase.table("facility_users").update({
            "is_approved": True,
            "is_suspended": False,
            "role": granted_role,
            "decision_by": decided_by,
            "decision_at": datetime.now().isoformat(),
            "denial_reason": None,
        }).eq("username", username).execute()
        if not res.data:
            # PostgREST returns HTTP 200 with an empty data list when Row
            # Level Security silently blocks the write — no exception is
            # raised, so without this check the caller would report
            # "approved" while nothing in the database actually changed.
            return False, "Update was accepted but changed nothing — Row Level Security is most likely blocking writes to facility_users. Run the RLS fix in schema_additions.sql (Phase 6), then try again."
        log_access_decision(username, full_name, "approved", decided_by,
                            old_role=old_role, new_role=granted_role, reason=reason)
        log_audit(decided_by, "access_approve",
                  {"username": username, "granted_role": granted_role})
        send_notification(full_name, "Access approved",
                          f"Your access has been approved with the role: {granted_role}.")
        return True, ""
    except Exception as e:
        log_error(str(e), details={"username": username}, endpoint="approve_access")
        return False, str(e)


def deny_access(username, decided_by, reason=None):
    """Deny a pending request. The record is KEPT (not deleted) so the
    decision remains auditable and the same person cannot silently
    re-apply without it being visible."""
    if not SUPABASE_AVAILABLE:
        return False, "No database connected."
    try:
        target = supabase.table("facility_users").select("*").eq("username", username).execute()
        if not target.data:
            return False, "User not found."
        full_name = target.data[0].get("full_name")
        res = supabase.table("facility_users").update({
            "is_approved": False,
            "is_suspended": True,
            "decision_by": decided_by,
            "decision_at": datetime.now().isoformat(),
            "denial_reason": reason,
        }).eq("username", username).execute()
        if not res.data:
            return False, "Update was accepted but changed nothing — Row Level Security is most likely blocking writes to facility_users. Run the RLS fix in schema_additions.sql (Phase 6), then try again."
        log_access_decision(username, full_name, "denied", decided_by, reason=reason)
        log_audit(decided_by, "access_deny", {"username": username, "reason": reason})
        return True, ""
    except Exception as e:
        log_error(str(e), details={"username": username}, endpoint="deny_access")
        return False, str(e)


def set_user_role(username, new_role, decided_by, reason=None):
    if not SUPABASE_AVAILABLE:
        return False, "No database connected."
    if new_role not in ("Worker", "Supervisor", "Superintendent"):
        return False, f"Invalid role: {new_role}"
    if is_owner(username) and new_role != "Superintendent":
        return False, ("The owner account cannot be demoted — that would lock you "
                       "out of access management. Change OWNER_USERNAME in "
                       "secrets.toml first if you intend to hand over.")
    try:
        target = supabase.table("facility_users").select("*").eq("username", username).execute()
        if not target.data:
            return False, "User not found."
        old_role = target.data[0].get("role")
        full_name = target.data[0].get("full_name")
        if old_role == new_role:
            return False, f"Already {new_role}."
        res = supabase.table("facility_users").update({
            "role": new_role,
            "decision_by": decided_by,
            "decision_at": datetime.now().isoformat(),
        }).eq("username", username).execute()
        if not res.data:
            return False, "Update was accepted but changed nothing — Row Level Security is most likely blocking writes to facility_users. Run the RLS fix in schema_additions.sql (Phase 6), then try again."
        log_access_decision(username, full_name, "role_changed", decided_by,
                            old_role=old_role, new_role=new_role, reason=reason)
        log_audit(decided_by, "role_change",
                  {"username": username, "from": old_role, "to": new_role})
        send_notification(full_name, "Role changed",
                          f"Your role changed from {old_role} to {new_role}.")
        return True, ""
    except Exception as e:
        log_error(str(e), details={"username": username}, endpoint="set_user_role")
        return False, str(e)


def set_user_suspended(username, suspended, decided_by, reason=None):
    """Suspend or reinstate. Suspension blocks login but keeps the
    account and its history, which is what you want when someone leaves
    or is under investigation — deleting them would orphan their audit
    trail."""
    if not SUPABASE_AVAILABLE:
        return False, "No database connected."
    if is_owner(username) and suspended:
        return False, ("You cannot suspend the owner account — it is the only "
                       "route into access management.")
    try:
        target = supabase.table("facility_users").select("*").eq("username", username).execute()
        if not target.data:
            return False, "User not found."
        full_name = target.data[0].get("full_name")
        res = supabase.table("facility_users").update({
            "is_suspended": suspended,
            "is_approved": (not suspended) and target.data[0].get("is_approved", False),
            "decision_by": decided_by,
            "decision_at": datetime.now().isoformat(),
        }).eq("username", username).execute()
        if not res.data:
            return False, "Update was accepted but changed nothing — Row Level Security is most likely blocking writes to facility_users. Run the RLS fix in schema_additions.sql (Phase 6), then try again."
        action = "suspended" if suspended else "reinstated"
        log_access_decision(username, full_name, action, decided_by, reason=reason)
        log_audit(decided_by, f"access_{action}", {"username": username})
        return True, ""
    except Exception as e:
        log_error(str(e), endpoint="set_user_suspended")
        return False, str(e)


# =====================================================================
# GOOGLE WORKSPACE MAILBOX AUTO-PROVISIONING
# =====================================================================
# Creates a REAL mailbox via the Admin SDK Directory API, not a
# fabricated address. A generated-but-nonexistent email is worse than
# no email: self-service password reset would report success while
# silently vanishing into nothing, hiding the fact that the person has
# no way to receive it. This only ever writes `email` after Google has
# actually confirmed the mailbox was created.
#
# Requires, entirely outside this app:
#   - gmc.com verified in Google Workspace
#   - a Google Cloud service account with domain-wide delegation
#   - the admin.directory.user scope authorized by a Workspace Super
#     Admin, for the service account to impersonate
#   - GOOGLE_WORKSPACE_SA_JSON, GOOGLE_WORKSPACE_ADMIN_EMAIL, and
#     GOOGLE_WORKSPACE_DOMAIN set in secrets.toml
#
# See GOOGLE_WORKSPACE_SETUP.md for the full walkthrough — none of
# that setup can be done from inside this app.
# =====================================================================

def workspace_provisioning_configured():
    return bool(GOOGLE_WORKSPACE_LIB_AVAILABLE
               and _secret_get("GOOGLE_WORKSPACE_SA_JSON")
               and _secret_get("GOOGLE_WORKSPACE_ADMIN_EMAIL"))


def _sanitize_name_part(s):
    """Lowercase, ASCII letters only.

    Accented Latin characters are transliterated, not dropped: NFKD
    decomposition splits 'é' into 'e' + a combining accent mark, and the
    combining mark is then stripped — so 'García' becomes 'garcia', not
    'garca'. Dropping the base letter entirely (the earlier, naive
    version of this function did that) mangles the name rather than
    cleanly stripping diacritics.

    Scripts that aren't Latin-based (Cyrillic, CJK, Arabic, etc.) have
    no ASCII fallback and are dropped to empty — generate_workspace_username
    falls back to "user" in that case. There's no good automatic answer
    there; a real transliteration table is a much bigger undertaking
    than this address-generation helper should take on.
    """
    import unicodedata
    normalized = unicodedata.normalize("NFKD", (s or "").strip().lower())
    ascii_only = "".join(c for c in normalized if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", ascii_only)


def generate_workspace_username(full_name, role, existing_local_parts=None):
    """Build the local-part (before the @) from name + role.

    Format: firstname.lastname.role — e.g. john.doe.worker
    Collisions get a numeric suffix: john.doe.worker2, john.doe.worker3.

    `existing_local_parts` should be the set of local-parts already in
    use (from your existing facility_users.email values), so this
    never proposes an address you already assigned to someone else in
    THIS app — Google's own 409-on-conflict is still the authoritative
    check for the Workspace directory as a whole.
    """
    existing_local_parts = existing_local_parts or set()
    parts = [p for p in (full_name or "").strip().split() if p]
    name_bits = [_sanitize_name_part(p) for p in parts] or ["user"]
    name_bits = [b for b in name_bits if b] or ["user"]
    role_bit = _sanitize_name_part(role) or "worker"

    base = ".".join(name_bits + [role_bit])
    candidate = base
    n = 2
    while candidate in existing_local_parts:
        candidate = f"{base}{n}"
        n += 1
    return candidate


def _get_workspace_directory_service():
    """Build an authenticated Admin SDK Directory client.

    Returns (service, error_string). service is None on any failure —
    every failure mode is caught and reported, never raised, since this
    runs inside an approval click and must not crash the console.
    """
    if not GOOGLE_WORKSPACE_LIB_AVAILABLE:
        return None, "google-api-python-client / google-auth not installed"
    sa_json = _secret_get("GOOGLE_WORKSPACE_SA_JSON")
    admin_email = _secret_get("GOOGLE_WORKSPACE_ADMIN_EMAIL")
    if not sa_json or not admin_email:
        return None, "GOOGLE_WORKSPACE_SA_JSON / GOOGLE_WORKSPACE_ADMIN_EMAIL not set"
    try:
        info = json.loads(sa_json) if isinstance(sa_json, str) else dict(sa_json)
        scopes = ["https://www.googleapis.com/auth/admin.directory.user"]
        credentials = _gws_service_account.Credentials.from_service_account_info(
            info, scopes=scopes)
        delegated = credentials.with_subject(admin_email)
        service = _gws_build("admin", "directory_v1", credentials=delegated,
                             cache_discovery=False)
        return service, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def provision_workspace_mailbox(full_name, role, decided_by, existing_local_parts=None):
    """Create a real Workspace mailbox and return the address plus a
    one-time initial password for it.

    Returns (ok, error, email, initial_password). initial_password is
    for WORKSPACE / Gmail login specifically — separate from and
    unrelated to this app's own password. The recipient will need both,
    relayed the same way admin_reset_password() already relays the
    app's temp password: in person, shown once, never emailed.
    """
    domain = _secret_get("GOOGLE_WORKSPACE_DOMAIN", "gmc.com")
    service, err = _get_workspace_directory_service()
    if not service:
        return False, err, None, None

    parts = [p for p in (full_name or "").strip().split() if p]
    given = parts[0] if parts else "User"
    family = " ".join(parts[1:]) if len(parts) > 1 else given

    base_local = generate_workspace_username(full_name, role, existing_local_parts)
    initial_password = generate_temp_password()

    for attempt in range(6):
        candidate_local = base_local if attempt == 0 else f"{base_local}{attempt + 1}"
        candidate_email = f"{candidate_local}@{domain}"
        try:
            service.users().insert(body={
                "primaryEmail": candidate_email,
                "name": {"givenName": given, "familyName": family},
                "password": initial_password,
                "changePasswordAtNextLogin": True,
            }).execute()
            log_audit(decided_by, "workspace_mailbox_created",
                     {"email": candidate_email, "for": full_name})
            return True, "", candidate_email, initial_password
        except _gws_HttpError as e:
            status = getattr(e, "status_code", None) or getattr(e.resp, "status", None)
            if status == 409:
                # Address taken in the real directory (even if it wasn't
                # in our local set) — the next loop iteration tries the
                # next numbered variant of the SAME base name.
                continue
            _err = f"HTTP {status}: {e}"
            log_error(_err, details={"full_name": full_name}, endpoint="provision_workspace_mailbox")
            return False, _err, None, None
        except Exception as e:
            _err = f"{type(e).__name__}: {e}"
            log_error(_err, details={"full_name": full_name}, endpoint="provision_workspace_mailbox")
            return False, _err, None, None

    return False, "Could not find an unused address after 6 attempts", None, None


def generate_temp_password():
    """A random password guaranteed to satisfy is_strong_password —
    one from each required character class, then padded and shuffled
    so the class-guarantee isn't visible as a fixed prefix pattern."""
    import string
    upper = secrets.choice(string.ascii_uppercase)
    lower = secrets.choice(string.ascii_lowercase)
    digit = secrets.choice(string.digits)
    special = secrets.choice("!@#$%^&*")
    rest = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
    chars = list(upper + lower + digit + special + rest)
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def admin_reset_password(username, decided_by):
    """Set a temporary password for a user who cannot complete
    self-service reset (no email on file, or SMTP unavailable).

    SECURITY:
    - The temp password is returned ONCE to the caller for the admin
      to relay in person or via whatever secure channel the site uses.
      It is never stored anywhere in plaintext and never emailed.
    - must_change_password is set, forcing a real password to be
      chosen before the account can do anything else.
    - The decision is logged with the actor's name, not a generic
      'admin' string, in the same append-only history as every other
      access decision.
    """
    if not SUPABASE_AVAILABLE:
        return False, "No database connected.", None
    try:
        target = supabase.table("facility_users").select("*").eq("username", username).execute()
        if not target.data:
            return False, "User not found.", None
        full_name = target.data[0].get("full_name")
        temp_password = generate_temp_password()
        res = supabase.table("facility_users").update({
            "password_hash": hash_password(temp_password),
            "must_change_password": True,
            "password_reset_token": None,   # invalidate any pending self-service link too
            "reset_token_expiry": None,
        }).eq("username", username).execute()
        if not res.data:
            return False, "Update was accepted but changed nothing — Row Level Security is most likely blocking writes to facility_users. Run the RLS fix in schema_additions.sql (Phase 6), then try again.", None
        log_access_decision(username, full_name, "password_reset_by_admin", decided_by)
        log_audit(decided_by, "admin_password_reset", {"username": username})
        return True, "", temp_password
    except Exception as e:
        log_error(str(e), details={"username": username}, endpoint="admin_reset_password")
        return False, str(e), None


def remove_user(username, decided_by, reason=None):
    if not SUPABASE_AVAILABLE:
        return False, "No database connected."
    if is_owner(username):
        return False, "The owner account cannot be removed from inside the app."
    try:
        target = supabase.table("facility_users").select("*").eq("username", username).execute()
        full_name = target.data[0].get("full_name") if target.data else None
        old_role = target.data[0].get("role") if target.data else None
        res = supabase.table("facility_users").delete().eq("username", username).execute()
        if not res.data:
            return False, "Delete was accepted but changed nothing — Row Level Security is most likely blocking writes to facility_users. Run the RLS fix in schema_additions.sql (Phase 6), then try again."
        log_access_decision(username, full_name, "removed", decided_by,
                            old_role=old_role, reason=reason)
        log_audit(decided_by, "access_remove", {"username": username})
        return True, ""
    except Exception as e:
        log_error(str(e), endpoint="remove_user")
        return False, str(e)


def has_any_admin():
    """True if at least one approved Superintendent exists in the DB.
    Used to gate first-run setup."""
    if not SUPABASE_AVAILABLE:
        return True
    try:
        res = (supabase.table("facility_users").select("username")
               .eq("role", "Superintendent").eq("is_approved", True).limit(1).execute())
        return bool(res.data)
    except Exception:
        # Fail closed: assume an admin exists rather than opening the
        # bootstrap form on a transient database error.
        return True


def create_first_admin(username, full_name, password, email=None):
    """One-time bootstrap: create the initial Superintendent.

    Only callable while no approved Superintendent exists. Re-checked
    server-side here so the gate cannot be bypassed by manipulating the
    UI state."""
    if not SUPABASE_AVAILABLE:
        return False, "No database connected."
    if has_any_admin():
        return False, "An administrator already exists. Register normally instead."
    strong, msg = is_strong_password(password)
    if not strong:
        return False, msg
    try:
        res = supabase.table("facility_users").insert({
            "username": username,
            "full_name": full_name,
            "role": "Superintendent",
            "password_hash": hash_password(password),
            "email": email,
            "auth_email": compute_auth_email(username, email),
            "is_approved": True,
        }).execute()
        if not res.data:
            return False, ("Insert was accepted but created nothing — Row Level Security is "
                          "most likely blocking writes to facility_users. Run schema_additions.sql "
                          "Phase 6, then try again.")
        log_audit(full_name, "bootstrap_first_admin", {"username": username})
        return True, ""
    except Exception as e:
        log_error(str(e), endpoint="create_first_admin")
        return False, str(e)

def register_user_to_db(username, name, requested_role, password, email=None,
                        job_title=None, department=None, employee_id=None):
    """Create an ACCESS REQUEST — not an account with the requested role.

    SECURITY: the applicant's choice is stored in `requested_role` only.
    The live `role` column is always seeded to the lowest privilege
    (Worker) and is set for real by the owner at approval time. Before
    this, someone could select "Superintendent" on the signup form and
    an inattentive approver would grant it with one click.
    """
    if not SUPABASE_AVAILABLE:
        return False, "No database connected — cannot register in demo mode."
    strong, msg = is_strong_password(password)
    if not strong:
        return False, msg

    full_payload = {
        "username": username,
        "full_name": name,
        "role": "Worker",                 # lowest privilege until granted — TRUE even
                                           # with auto-approve on; that policy only
                                           # relaxes whether a human reviews the sign-up,
                                           # never this separate role-escalation protection
        "requested_role": requested_role,  # what they asked for
        "password_hash": hash_password(password),
        "email": email,
        "auth_email": compute_auth_email(username, email),
        "job_title": job_title,
        "department": department,
        "employee_id": employee_id,
        "is_approved": fetch_access_policies()["auto_approve_registration"],
        "is_suspended": False,
        "requested_at": datetime.now().isoformat(),
    }
    # Columns that only exist after the Phase 3 migration. If the database
    # hasn't been migrated yet, PostgREST returns PGRST204 and the whole
    # insert fails — which blocks signup completely. Rather than hard-fail,
    # drop the optional fields and retry with the core ones, then tell the
    # user which migration is outstanding.
    OPTIONAL = ("requested_role", "job_title", "department", "employee_id",
                "is_suspended", "requested_at", "auth_email")
    try:
        res = supabase.table("facility_users").insert(full_payload).execute()
        if not res.data:
            return False, ("Registration was accepted but nothing was created — Row Level "
                          "Security is most likely blocking writes to facility_users. Run "
                          "schema_additions.sql Phase 6, then try again.")
        _degraded = False
    except Exception as e:
        if "PGRST204" not in str(e) and "schema cache" not in str(e).lower():
            log_error(str(e), details={"username": username}, endpoint="register_user")
            return False, str(e)
        minimal = {k: v for k, v in full_payload.items() if k not in OPTIONAL}
        try:
            res = supabase.table("facility_users").insert(minimal).execute()
            if not res.data:
                return False, ("Registration was accepted but nothing was created — Row Level "
                              "Security is most likely blocking writes to facility_users. Run "
                              "schema_additions.sql Phase 6, then try again.")
            _degraded = True
        except Exception as e2:
            log_error(str(e2), details={"username": username}, endpoint="register_user_minimal")
            return False, (f"{e2}\n\nYour `facility_users` table is missing required "
                           "columns. Run FIX_registration_columns.sql in the Supabase "
                           "SQL editor.")

    try:
        log_audit(name, "access_request",
                  {"username": username, "requested_role": requested_role})
        if OWNER_USERNAME:
            send_notification(OWNER_USERNAME, "New access request",
                              f"{name} ({username}) requested access as {requested_role}.")
    except Exception:
        pass  # never fail a signup because a notification failed

    if _degraded:
        return True, ("__DEGRADED__Your request was saved, but the job title, "
                      "department, ID, and requested role could NOT be stored — "
                      "those columns are missing from the database. Run "
                      "FIX_registration_columns.sql, then the administrator will "
                      "see full details on future requests.")
    return True, ""

def authenticate_user(username, password):
    """Authenticate and return (user, status).

    Order matters: the password is verified BEFORE reporting suspension
    or denial, so the login form cannot be used to enumerate which
    usernames exist or what state they are in.
    """
    users = fetch_all_users_from_db()
    for u in users:
        if u["username"].lower() == username.lower():
            if not verify_password(password, u["password_hash"]):
                return None, None                       # wrong password
            if u.get("is_suspended", False):
                return None, "suspended"
            if not u.get("is_approved", False):
                if u.get("denial_reason"):
                    return None, "denied"
                return None, "pending_approval"
            return u, "approved"
    return None, None

def update_user_profile(username, updates):
    if not SUPABASE_AVAILABLE:
        return False
    try:
        res = supabase.table("facility_users").update(updates).eq("username", username).execute()
        return bool(res.data)
    except Exception as e:
        log_error(str(e), details={"username": username, "updates": updates}, endpoint="update_user")
        return False

# REMOVED: approve_user() / reject_user().
# They granted or destroyed access with no role assignment, no reason
# captured, and an audit entry attributed to the literal string "admin"
# rather than to whoever clicked. Access changes now go through
# approve_access() / deny_access() / remove_user() in the owner section,
# which record the actual decision-maker in the append-only
# access_decisions table.

def generate_reset_token(username, email):
    """Create a reset token and email it.

    Always returns quickly and the caller shows an identical message to
    the requester regardless of outcome (see the login-page enumeration
    fix). Delivery failures are logged and, if persistent, surfaced to
    the owner — the requester should never learn from this function's
    result whether the email step succeeded, only the operator should.
    """
    if not SUPABASE_AVAILABLE:
        return False
    token = secrets.token_urlsafe(32)
    expiry = datetime.now() + timedelta(hours=1)
    try:
        res = supabase.table("facility_users").update({
            "password_reset_token": token,
            "reset_token_expiry": expiry.isoformat()
        }).eq("username", username).eq("email", email).execute()
        if not res.data:
            # The token was never actually stored (RLS-blocked write —
            # HTTP 200, empty result, no exception). Sending the email
            # anyway would hand out a reset link that can never work,
            # since nothing in the database matches its token. Log it
            # for the operator; the requester still sees the same
            # generic message either way, by design.
            log_error("Reset token update affected 0 rows — likely RLS blocking "
                     "writes to facility_users", details={"username": username},
                     endpoint="generate_reset_token")
            return False
        reset_link = f"{APP_URL}/?reset_token={token}"
        sent = send_email_notification(
            email, "Password Reset Request",
            f"<p>A password reset was requested for your account on the "
            f"Mine & Workshop Tracker.</p>"
            f"<p><a href='{reset_link}'>Click here to reset your password</a> "
            f"(expires in 1 hour).</p>"
            f"<p>If the link above doesn't work, copy this URL into your browser:<br>"
            f"{reset_link}</p>"
            f"<p>If you did not request this, you can ignore this email — "
            f"your password will not change unless the link above is used.</p>")
        if not sent:
            log_error("Password reset email did not send (SMTP not configured or failed)",
                      details={"username": username}, endpoint="generate_reset_token")
            log_audit(username, "reset_email_delivery_failed", {})
        return True
    except Exception as e:
        log_error(str(e), details={"username": username}, endpoint="generate_reset_token")
        return False

# -------------------------------
# 10. TASK FUNCTIONS (with optimistic locking)
# -------------------------------
def fetch_all_tasks():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("tasks_memory", [])
    try:
        res = supabase.table("tasks").select("*").order("id", desc=False).execute()
        if res.data:
            return res.data
        else:
            return st.session_state.get("tasks_memory", [])
    except Exception as e:
        log_error(str(e), endpoint="fetch_tasks")
        return st.session_state.get("tasks_memory", [])

def get_location_path_options():
    """All locations in the hierarchy as full path strings
    ("Plant 1 / Crushing / Conveyor B"), for use in a dropdown.

    Reuses location_hierarchy.py's own _load_location_data() and
    _get_full_path() rather than re-parsing the stored JSON here —
    those functions are the single source of truth for how a path
    string gets built, and duplicating that logic risks the two
    falling out of sync if the hierarchy's storage format ever changes.

    Returns an empty list if the module isn't available or no
    hierarchy has been set up yet — callers should fall back to a
    plain text input in that case, not assume this always has data.
    """
    if not LOCATION_HIERARCHY_MODULE_AVAILABLE:
        return []
    try:
        data = location_hierarchy._load_location_data()
        if not data or not data.get("locations"):
            return []
        paths = [location_hierarchy._get_full_path(data, loc["id"]) for loc in data["locations"]]
        return sorted(p for p in paths if p)
    except Exception as e:
        log_error(str(e), endpoint="get_location_path_options")
        return []


def apply_labour_hours_to_task(task_id, hours, updated_by):
    """Adds `hours` to a task's labour_hours — increments, does NOT
    overwrite, since a worker may log hours to the same task across
    several shifts (a 2-day repair job gets hours added on day 1 AND
    day 2, not day 2's punch replacing day 1's).

    Called from crew_clock.py's punch-out flow (Auto-Costing feature)
    — reached via the same sys.modules['__main__'] pattern every other
    module already uses to call back into app.py.
    """
    if not SUPABASE_AVAILABLE:
        tasks = st.session_state.get("tasks_memory", [])
        for t2 in tasks:
            if t2["id"] == task_id:
                t2["labour_hours"] = (t2.get("labour_hours") or 0) + hours
                return True
        return False
    try:
        current = supabase.table("tasks").select("labour_hours").eq("id", task_id).execute()
        if not current.data:
            return False
        new_hours = (current.data[0].get("labour_hours") or 0) + hours
        res = supabase.table("tasks").update({"labour_hours": new_hours}).eq("id", task_id).execute()
        if res.data:
            log_audit(updated_by, "labour_hours_auto_applied", {"task_id": task_id, "hours_added": round(hours, 2)})
            return True
        return False
    except Exception as e:
        log_error(str(e), endpoint="apply_labour_hours_to_task")
        return False


def create_task(title, location, priority, loto, jsa, created_by, due_date=None,
                is_recurring=False, recurrence_type=None, recurrence_end_date=None,
                asset_id=None, meter_interval=None, work_type="Reactive",
                failure_code=None, failure_start=None, labour_rate=0, weather_sensitive=False,
                jsa_document_id=None, description=None, subsection=None):
    # For a meter-based recurring task (Job Plan Auto-Scheduler), the
    # "next due" concept isn't a date — it's a meter reading. Computed
    # here, once, at creation time: next_meter_threshold = the asset's
    # current reading + meter_interval. handle_recurring_tasks() later
    # compares each check against this stored value rather than
    # re-deriving it from scratch every time, since the interval should
    # stay anchored to where the LAST instance fired, not silently
    # drift if readings are logged unevenly.
    next_meter_threshold = None
    if is_recurring and recurrence_type == "meter-based" and meter_interval and asset_id and SUPABASE_AVAILABLE:
        try:
            _mr = supabase.table("meter_readings").select("reading") \
                .eq("asset_id", asset_id).order("recorded_at", desc=True).limit(1).execute()
            _current_reading = float(_mr.data[0]["reading"]) if _mr.data else 0
            next_meter_threshold = _current_reading + meter_interval
        except Exception as e:
            log_error(str(e), endpoint="create_task_meter_threshold")

    if not SUPABASE_AVAILABLE:
        tasks = st.session_state.get("tasks_memory", [])
        new_id = max([t["id"] for t in tasks], default=0) + 1
        new_task = {
            "id": new_id,
            "title": title,
            "location": location,
            "priority": priority,
            "loto": loto,
            "jsa": jsa,
            "status": "Unassigned",
            "assigned_to": "Unassigned",
            "due_date": due_date.isoformat() if due_date else None,
            "is_recurring": is_recurring,
            "recurrence_type": recurrence_type,
            "recurrence_end_date": recurrence_end_date.isoformat() if recurrence_end_date else None,
            "asset_id": asset_id,
            "meter_interval": meter_interval,
            "work_type": work_type,
            "failure_code": failure_code,
            "failure_start": failure_start.isoformat() if hasattr(failure_start, "isoformat") else failure_start,
            "labour_hours": 0,
            "labour_rate": labour_rate,
            "weather_sensitive": weather_sensitive,
            "jsa_document_id": jsa_document_id,
            "next_meter_threshold": next_meter_threshold,
            "description": description,
            "subsection": subsection,
            "completed_at": None,
            "version": 0
        }
        tasks.append(new_task)
        st.session_state.tasks_memory = tasks
        log_audit(created_by, "task_create_memory", {"task_id": new_id})
        return new_task
    try:
        new_task = {
            "title": title,
            "location": location,
            "priority": priority,
            "loto": loto,
            "jsa": jsa,
            "status": "Unassigned",
            "assigned_to": "Unassigned",
            "due_date": due_date.isoformat() if due_date else None,
            "is_recurring": is_recurring,
            "recurrence_type": recurrence_type,
            "recurrence_end_date": recurrence_end_date.isoformat() if recurrence_end_date else None,
            "asset_id": asset_id,
            "meter_interval": meter_interval,
            "work_type": work_type,
            "failure_code": failure_code,
            "failure_start": failure_start.isoformat() if hasattr(failure_start, "isoformat") else failure_start,
            "labour_hours": 0,
            "labour_rate": labour_rate,
            "weather_sensitive": weather_sensitive,
            "jsa_document_id": jsa_document_id,
            "next_meter_threshold": next_meter_threshold,
            "description": description,
            "subsection": subsection,
            "completed_at": None,
            "version": 0
        }
        res = supabase.table("tasks").insert(new_task).execute()
        if res.data:
            task = res.data[0]
            log_audit(created_by, "task_create", {"task_id": task["id"]})
            log_task_activity(task["id"], created_by, "created", {"title": title})
            return task
    except Exception as e:
        log_error(str(e), details={"title": title}, endpoint="create_task")
        return None
    return None

def update_task(task_id, updates, updated_by):
    # Stamp real completion/reopen timestamps. Every downstream metric
    # (MTTR, MTBF, PM compliance) depends on this being accurate, so it
    # is set here centrally rather than at each call site.
    if "status" in updates:
        if updates["status"] == "Complete":
            updates.setdefault("completed_at", datetime.now().isoformat())
        else:
            # Reopened or moved backwards — the old completion is no
            # longer true and must not linger in the metrics.
            updates["completed_at"] = None
    if not SUPABASE_AVAILABLE:
        for t in st.session_state.get("tasks_memory", []):
            if t["id"] == task_id:
                old = t.copy()
                t.update(updates)
                log_audit(updated_by, "task_update_memory", {"task_id": task_id, "old": old, "new": updates})
                return True
        return False
    try:
        current = supabase.table("tasks").select("version").eq("id", task_id).execute()
        if not current.data:
            return False
        current_version = current.data[0].get("version", 0)
        updates["version"] = current_version + 1
        res = supabase.table("tasks").update(updates).eq("id", task_id).eq("version", current_version).execute()
        if res.data:
            log_audit(updated_by, "task_update", {"task_id": task_id, "new": updates})
            log_task_activity(task_id, updated_by, "updated", updates)
            if 'status' in updates:
                send_external_notifications(f"Task #{task_id} status changed to {updates['status']} by {updated_by}")
            return True
        else:
            st.error("This task was updated by another user. Please refresh and try again.")
            return False
    except Exception as e:
        log_error(str(e), details={"task_id": task_id, "updates": updates}, user_name=updated_by, endpoint="update_task")
        return False

def delete_task(task_id, deleted_by):
    if not SUPABASE_AVAILABLE:
        st.session_state.tasks_memory = [t for t in st.session_state.get("tasks_memory", []) if t["id"] != task_id]
        log_audit(deleted_by, "task_delete_memory", {"task_id": task_id})
        return True
    try:
        res = supabase.table("tasks").delete().eq("id", task_id).execute()
        if not res.data:
            return False
        log_audit(deleted_by, "task_delete", {"task_id": task_id})
        log_task_activity(task_id, deleted_by, "deleted", {})
        send_external_notifications(f"Task #{task_id} deleted by {deleted_by}")
        return True
    except Exception as e:
        log_error(str(e), details={"task_id": task_id}, user_name=deleted_by, endpoint="delete_task")
        return False

# -------------------------------
# 11. TASK ACTIVITY LOG
# -------------------------------
def log_task_activity(task_id, user_name, action, details=None):
    if not SUPABASE_AVAILABLE:
        return
    try:
        supabase.table("task_activity").insert({
            "task_id": task_id,
            "user_name": user_name,
            "action": action,
            "details": json.dumps(details) if details else None
        }).execute()
    except Exception as e:
        log_error(str(e), endpoint="log_task_activity")

def fetch_task_activity(task_id):
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("activity_memory", [])
    try:
        res = supabase.table("task_activity").select("*").eq("task_id", task_id).order("created_at", desc=False).execute()
        if res.data:
            return res.data
    except Exception as e:
        log_error(str(e), endpoint="fetch_task_activity")
        pass
    return []

# -------------------------------
# 12. NOTIFICATIONS
# -------------------------------
def send_push_to_user(username, title, body):
    """Sends a real device-level push notification to every device
    that username has subscribed from (a person can have more than
    one). Best-effort by design, matching every other notification/
    logging function in this file — a failed push should never block
    or crash whatever triggered it. A subscription that comes back as
    permanently dead (410 Gone — the browser unsubscribed or the
    device is gone for good) gets cleaned up automatically instead of
    failing silently forever on every future send.
    """
    if not PUSH_CONFIGURED or not SUPABASE_AVAILABLE:
        return
    try:
        res = supabase.table("push_subscriptions").select("*").eq("username", username).execute()
        subs = res.data or []
    except Exception as e:
        log_error(str(e), endpoint="send_push_to_user:fetch")
        return

    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh_key"], "auth": sub["auth_key"]},
                },
                data=json.dumps({"title": title, "body": body}),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{VAPID_CLAIMS_EMAIL}"},
            )
        except WebPushException as e:
            _status = getattr(getattr(e, "response", None), "status_code", None)
            if _status == 410:
                try:
                    supabase.table("push_subscriptions").delete().eq("id", sub["id"]).execute()
                except Exception:
                    pass  # cleanup is a nicety, not worth a second error over
            else:
                log_error(str(e), endpoint="send_push_to_user:send", details={"username": username})
        except Exception as e:
            log_error(str(e), endpoint="send_push_to_user:send", details={"username": username})


def save_push_subscription(username, endpoint, p256dh_key, auth_key):
    """Persists a new device subscription. Uses the endpoint's own
    UNIQUE constraint (see schema) to make re-subscribing the same
    device harmless rather than creating duplicate rows that would
    each separately (and redundantly) receive every push."""
    if not SUPABASE_AVAILABLE:
        return False
    try:
        res = supabase.table("push_subscriptions").upsert({
            "username": username, "endpoint": endpoint,
            "p256dh_key": p256dh_key, "auth_key": auth_key,
        }, on_conflict="endpoint").execute()
        return bool(res.data)
    except Exception as e:
        log_error(str(e), endpoint="save_push_subscription")
        return False


def send_notification(user_name, title, body):
    if not SUPABASE_AVAILABLE:
        return
    try:
        supabase.table("notifications").insert({
            "user_name": user_name,
            "title": title,
            "body": body
        }).execute()
    except Exception as e:
        log_error(str(e), endpoint="send_notification")
    send_push_to_user(user_name, title, body)  # best-effort, real device push
    # alongside the in-app notification record above — a failure here
    # (no subscription, push not configured, etc.) never affects
    # whether the in-app notification itself was recorded.

def fetch_notifications(user_name):
    if not SUPABASE_AVAILABLE:
        return []
    try:
        res = supabase.table("notifications").select("*").eq("user_name", user_name).order("created_at", desc=True).limit(20).execute()
        if res.data:
            return res.data
    except Exception as e:
        log_error(str(e), endpoint="fetch_notifications")
        return []
    return []

def mark_notification_read(notification_id):
    if not SUPABASE_AVAILABLE:
        return
    try:
        supabase.table("notifications").update({"is_read": True}).eq("id", notification_id).execute()
    except Exception as e:
        log_error(str(e), endpoint="mark_notification_read")

# -------------------------------
# 13. PHOTO FUNCTIONS (with fallback)
# -------------------------------
def upload_photo(task_id, file_bytes, filename, uploaded_by):
    """Upload proof-of-work/safety photo evidence.

    FIXED: this previously returned True unconditionally — even on a
    failed validation, a failed storage upload, or a caught exception.
    Nothing that happened in this function's body could ever make it
    report failure, which is a serious gap for what's often compliance
    evidence (LOTO isolation photos, incident scenes). The in-session
    memory fallback below is intentional and kept — it lets a photo
    still SHOW UP for the current browser session even if the durable
    write fails — but the return value now reflects whether it was
    actually saved somewhere that survives a refresh or a different
    user loading the same task, not just whether this call ran.
    """
    st.session_state.setdefault("photos_memory", []).append({
        "task_id": task_id,
        "photo_url": f"memory://{filename}",
        "uploaded_by": uploaded_by,
        "uploaded_at": datetime.now().isoformat()
    })
    log_audit(uploaded_by, "photo_upload_memory", {"task_id": task_id, "filename": filename})
    if not SUPABASE_AVAILABLE:
        return True  # demo mode — the memory fallback IS the intended store
    try:
        valid, msg = validate_image(file_bytes, filename)
        if not valid:
            st.error(msg)
            return False
        ext = filename.split(".")[-1]
        safe_name = f"task_{task_id}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(file_bytes).hexdigest()[:8]}.{ext}"
        storage_res = supabase.storage.from_("task_photos").upload(safe_name, file_bytes)
        if not storage_res:
            log_error("Storage upload returned a falsy result", details={"task_id": task_id},
                     endpoint="photo_upload")
            return False
        public_url = supabase.storage.from_("task_photos").get_public_url(safe_name)
        try:
            data = {"task_id": task_id, "photo_url": public_url, "uploaded_by": uploaded_by}
            res = supabase.table("task_photos").insert(data).execute()
            if not res.data:
                log_error("task_photos insert affected 0 rows — likely RLS blocking writes. "
                         "The file reached Storage but has no metadata row, so it won't "
                         "appear when this task is loaded again.",
                         details=data, endpoint="photo_insert")
                return False
            log_audit(uploaded_by, "photo_upload", {"task_id": task_id, "url": public_url})
            return True
        except Exception as e:
            log_error(str(e), endpoint="photo_insert")
            return False
    except Exception as e:
        log_error(str(e), endpoint="photo_upload")
        return False

def fetch_photos(task_id):
    if not SUPABASE_AVAILABLE:
        photos = st.session_state.get("photos_memory", [])
        return [p for p in photos if p["task_id"] == task_id]
    db_photos = []
    try:
        res = supabase.table("task_photos").select("*").eq("task_id", task_id).order("uploaded_at", desc=True).execute()
        if res.data:
            db_photos = res.data
    except Exception as e:
        log_error(str(e), endpoint="fetch_photos")
        pass
    memory_photos = st.session_state.get("photos_memory", [])
    memory_photos = [p for p in memory_photos if p["task_id"] == task_id]
    all_photos = db_photos + memory_photos
    all_photos.sort(key=lambda x: x.get('uploaded_at', ''), reverse=True)
    return all_photos

# -------------------------------
# 14. FILE ATTACHMENTS
# -------------------------------
def upload_attachment(task_id, file_bytes, filename, uploaded_by):
    valid, msg = validate_attachment(file_bytes, filename)
    if not valid:
        st.error(msg)
        return False

    if not SUPABASE_AVAILABLE:
        st.session_state.setdefault("attachments_memory", []).append({
            "task_id": task_id,
            "file_name": filename,
            "file_url": f"memory://{filename}",
            "file_type": filename.split('.')[-1].lower(),
            "uploaded_by": uploaded_by,
            "uploaded_at": datetime.now().isoformat()
        })
        log_audit(uploaded_by, "attachment_upload_memory", {"task_id": task_id, "filename": filename})
        return True
    try:
        ext = filename.split('.')[-1].lower()
        safe_name = f"attachments/task_{task_id}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(file_bytes).hexdigest()[:8]}.{ext}"
        res = supabase.storage.from_("task_attachments").upload(safe_name, file_bytes)
        if res:
            public_url = supabase.storage.from_("task_attachments").get_public_url(safe_name)
            data = {
                "task_id": task_id,
                "file_name": filename,
                "file_url": public_url,
                "file_type": ext,
                "uploaded_by": uploaded_by
            }
            res2 = supabase.table("task_attachments").insert(data).execute()
            if not res2.data:
                log_error("task_attachments insert affected 0 rows — likely RLS blocking "
                         "writes. The file reached Storage but has no metadata row.",
                         details=data, endpoint="attachment_insert")
                return False
            log_audit(uploaded_by, "attachment_upload", {"task_id": task_id, "filename": filename})
            return True
        else:
            return False
    except Exception as e:
        st.error(f"Upload failed: {e}")
        log_error(str(e), details={"task_id": task_id, "filename": filename}, endpoint="attachment_upload")
        return False

def fetch_attachments(task_id):
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("attachments_memory", [])
    try:
        res = supabase.table("task_attachments").select("*").eq("task_id", task_id).order("uploaded_at", desc=True).execute()
        if res.data:
            return res.data
        else:
            return []
    except Exception as e:
        log_error(str(e), endpoint="fetch_attachments")
        return []

# -------------------------------
# 15. TASK COMMENTS
# -------------------------------
def add_comment(task_id, comment, posted_by):
    if not SUPABASE_AVAILABLE:
        st.session_state.setdefault("comments_memory", []).append({
            "task_id": task_id,
            "comment": comment,
            "posted_by": posted_by,
            "posted_at": datetime.now().isoformat()
        })
        log_audit(posted_by, "comment_add_memory", {"task_id": task_id, "comment": comment[:50]})
        return True
    try:
        data = {"task_id": task_id, "comment": comment, "posted_by": posted_by}
        res = supabase.table("task_comments").insert(data).execute()
        if not res.data:
            return False
        log_audit(posted_by, "comment_add", {"task_id": task_id, "comment": comment[:50]})
        log_task_activity(task_id, posted_by, "commented", {"comment": comment[:50]})
        return True
    except Exception as e:
        log_error(str(e), details={"task_id": task_id}, endpoint="add_comment")
        return False

def fetch_comments(task_id):
    if not SUPABASE_AVAILABLE:
        comments = st.session_state.get("comments_memory", [])
        return [c for c in comments if c["task_id"] == task_id]
    try:
        res = supabase.table("task_comments").select("*").eq("task_id", task_id).order("posted_at", desc=False).execute()
        if res.data:
            return res.data
    except Exception as e:
        log_error(str(e), endpoint="fetch_comments")
        pass
    return []

# -------------------------------
# 16. CHAT FUNCTIONS
# -------------------------------
if 'next_memory_id' not in st.session_state:
    st.session_state.next_memory_id = -1

def send_message(sender, receiver, room, message, encrypted=False):
    if not SUPABASE_AVAILABLE:
        msg_id = st.session_state.next_memory_id
        st.session_state.next_memory_id -= 1
        msg = {
            "id": msg_id,
            "sender": sender,
            "receiver": receiver,
            "room": room,
            "message": message,
            "is_encrypted": encrypted,
            "created_at": datetime.now().isoformat()
        }
        st.session_state.setdefault("chat_messages_memory", []).append(msg)
        return True
    try:
        payload = {
            "sender": sender,
            "receiver": receiver,
            "room": room,
            "message": message,
            "is_encrypted": encrypted
        }
        res = supabase.table("chat_messages").insert(payload).execute()
        if not res.data:
            return False
        return True
    except Exception as e:
        log_error(str(e), endpoint="send_message")
        return False

def fetch_messages(room=None, limit=100):
    if not SUPABASE_AVAILABLE:
        msgs = st.session_state.get("chat_messages_memory", [])
        if room:
            msgs = [m for m in msgs if m["room"] == room]
        return sorted(msgs, key=lambda x: x["created_at"], reverse=True)[:limit]
    try:
        query = supabase.table("chat_messages").select("*").order("created_at", desc=True).limit(limit)
        if room:
            query = query.eq("room", room)
        res = query.execute()
        if res.data:
            return res.data
    except Exception as e:
        log_error(str(e), endpoint="fetch_messages")
        pass
    return []

def delete_message(message_id, deleted_by):
    if message_id < 0:
        st.session_state.chat_messages_memory = [
            m for m in st.session_state.get("chat_messages_memory", [])
            if m["id"] != message_id
        ]
        log_audit(deleted_by, "message_delete_memory", {"message_id": message_id})
        return True
    else:
        if not SUPABASE_AVAILABLE:
            return False
        try:
            msg = supabase.table("chat_messages").select("*").eq("id", message_id).execute()
            res = supabase.table("chat_messages").delete().eq("id", message_id).execute()
            if not res.data:
                return False
            if msg.data:
                log_audit(deleted_by, "message_delete", {"message_id": message_id, "content": msg.data[0]["message"][:50]})
            return True
        except Exception as e:
            log_error(str(e), details={"message_id": message_id}, endpoint="delete_message")
            return False

# -------------------------------
# 17. ENCRYPTION HELPERS (obfuscation)
# -------------------------------
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

def derive_key(name1, name2):
    """
    ⚠️ THIS IS OBFUSCATION, NOT SECURE ENCRYPTION. ⚠️

    The key material is just the two usernames, which are public
    within the app, combined with a salt. Anyone who knows both
    usernames can regenerate this key and decrypt the messages.
    It protects against nothing more than a casual glance at the
    raw database rows.

    To make private chat genuinely confidential you need per-user
    asymmetric keypairs, with private keys held client-side and
    never sent to the server. That is a real project, not a patch.
    Until then the UI warns users not to trust this channel.

    CHAT_KEY_SALT (optional, from secrets) at least prevents someone
    reading this public source from deriving keys without also
    having your deployment secret. It does NOT fix the fundamental
    weakness above.
    """
    sorted_names = sorted([name1.lower(), name2.lower()])
    combined = sorted_names[0] + sorted_names[1]
    salt = str(st.secrets.get("CHAT_KEY_SALT", "fixed_salt_for_demo")).encode()
    if CRYPTO_AVAILABLE:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(combined.encode()))
        return key
    else:
        return base64.urlsafe_b64encode(hashlib.sha256(combined.encode()).digest())

def encrypt_message(message, key):
    if CRYPTO_AVAILABLE:
        f = Fernet(key)
        return f.encrypt(message.encode()).decode()
    else:
        return base64.b64encode(message.encode()).decode()

def decrypt_message(encrypted_msg, key):
    if CRYPTO_AVAILABLE:
        f = Fernet(key)
        return f.decrypt(encrypted_msg.encode()).decode()
    else:
        return base64.b64decode(encrypted_msg.encode()).decode()

# -------------------------------
# 18. EXPORT REPORTS
# -------------------------------
def export_tasks_csv(tasks):
    if not tasks or not PANDAS_AVAILABLE:
        return None
    df = pd.DataFrame(tasks)
    cols = ['id', 'title', 'location', 'status', 'priority', 'assigned_to', 'due_date', 'created_at']
    existing_cols = [c for c in cols if c in df.columns]
    df = df[existing_cols]
    return df.to_csv(index=False)

def export_assets_csv(assets):
    if not assets or not PANDAS_AVAILABLE:
        return None
    df = pd.DataFrame(assets)
    cols = ['id', 'name', 'asset_tag', 'category', 'location', 'manufacturer', 'model_number',
            'serial_number', 'status', 'criticality', 'current_meter', 'meter_unit', 'install_date']
    existing_cols = [c for c in cols if c in df.columns]
    df = df[existing_cols]
    return df.to_csv(index=False)

def export_inventory_csv(parts):
    if not parts or not PANDAS_AVAILABLE:
        return None
    df = pd.DataFrame(parts)
    cols = ['id', 'part_name', 'part_number', 'category', 'quantity_on_hand', 'reorder_point',
            'reorder_qty', 'unit_cost', 'supplier', 'bin_location']
    existing_cols = [c for c in cols if c in df.columns]
    df = df[existing_cols]
    return df.to_csv(index=False)

def export_incidents_csv(incidents):
    if not incidents or not PANDAS_AVAILABLE:
        return None
    df = pd.DataFrame(incidents)
    cols = ['id', 'incident_type', 'severity', 'location', 'department', 'shift',
            'status', 'reported_by', 'reporter_id_no', 'paper_ref_no', 'description',
            'immediate_action', 'reporter_suggestion', 'root_cause', 'corrective_action',
            'acknowledged_by', 'acknowledged_at', 'created_at']
    existing_cols = [c for c in cols if c in df.columns]
    df = df[existing_cols]
    return df.to_csv(index=False)


def generate_pdf_report(tasks, assets, incidents):
    """Builds a formatted Safety & Operations PDF report from data
    that's already computed elsewhere in Analytics — this function
    doesn't calculate anything new, it reuses the exact same
    compute_mttr_hours_v2 / compute_mtbf_hours / compute_pm_compliance_v2
    / planned_vs_reactive / safety_leading_indicators functions
    already driving the on-screen Analytics tabs, so the PDF can never
    show a different number than what someone just saw on their
    screen. Returns PDF bytes, or None if reportlab isn't available.
    """
    if not PDF_REPORT_AVAILABLE:
        return None

    NAVY = _rl_colors.HexColor("#001530")
    GRAY = _rl_colors.HexColor("#475569")

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("RptTitle", fontSize=20, leading=26,
                              textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=6))
    styles.add(ParagraphStyle("RptSub", fontSize=11, leading=15,
                              textColor=GRAY, fontName="Helvetica", spaceAfter=16))
    styles.add(ParagraphStyle("RptH2", fontSize=14, leading=18,
                              textColor=NAVY, fontName="Helvetica-Bold",
                              spaceBefore=16, spaceAfter=8))
    styles.add(ParagraphStyle("RptBody", fontSize=10, leading=14, spaceAfter=6))
    styles.add(ParagraphStyle("RptCaption", fontSize=8.5, leading=11,
                              textColor=GRAY, spaceAfter=10))

    story = []
    story.append(Paragraph("MWDTS Safety &amp; Operations Report", styles["RptTitle"]))
    story.append(Paragraph(f"Generated {datetime.now().strftime('%B %d, %Y at %H:%M')}", styles["RptSub"]))

    def metric_table(rows):
        t = Table(rows, colWidths=[2.6*inch, 3.6*inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 9.5),
            ("TEXTCOLOR", (0,0), (0,-1), NAVY),
            ("GRID", (0,0), (-1,-1), 0.5, _rl_colors.HexColor("#d3dae6")),
            ("ROWBACKGROUNDS", (0,0), (-1,-1), [_rl_colors.white, _rl_colors.HexColor("#f6f8fb")]),
            ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))
        return t

    # --- Reliability ---
    story.append(Paragraph("Reliability", styles["RptH2"]))
    mttr, mttr_n = compute_mttr_hours_v2(tasks)
    mtbf, mtbf_n = compute_mtbf_hours(tasks)
    story.append(metric_table([
        ["MTTR (Mean Time To Repair)", f"{mttr:.1f} hours ({mttr_n} completed task(s))" if mttr is not None else "No data yet"],
        ["MTBF (Mean Time Between Failures)", f"{mtbf:.1f} hours ({mtbf_n} interval(s))" if mtbf is not None else "No data yet"],
    ]))
    if (mttr_n and mttr_n < 10) or (mtbf_n and mtbf_n < 10):
        story.append(Paragraph(
            "Small sample — these figures are based on very few data points and will "
            "shift significantly as more work is completed. Treat as indicative only.",
            styles["RptCaption"]))

    # --- Compliance ---
    story.append(Paragraph("Backlog &amp; Compliance", styles["RptH2"]))
    pm_pct, pm_n = compute_pm_compliance_v2(tasks)
    planned_pct, reactive_pct, wt_total = planned_vs_reactive(tasks)
    story.append(metric_table([
        ["PM Compliance", f"{pm_pct}% ({pm_n} PM task(s) due)" if pm_pct is not None else "No data yet"],
        ["Planned Work", f"{planned_pct}%" if planned_pct is not None else "No data yet"],
        ["Reactive Work", f"{reactive_pct}%" if reactive_pct is not None else "No data yet"],
    ]))

    # --- Safety ---
    story.append(Paragraph("Safety Leading Indicators", styles["RptH2"]))
    si = safety_leading_indicators(incidents, tasks)
    story.append(metric_table([
        ["Total Incidents", str(si["total_incidents"])],
        ["Proactive Reports (near-miss + hazard)", str(si["proactive_reports"])],
        ["Injuries", str(si["injuries"])],
        ["Incidents in Last 30 Days", str(si["last_30_days"])],
        ["Near-miss Share", f"{si['near_miss_ratio']}%" if si["near_miss_ratio"] is not None else "No data"],
        ["Open, No Corrective Action", str(si["open_without_action"])],
    ]))
    if si["open_without_action"] > 0:
        story.append(Paragraph(
            f"⚠ {si['open_without_action']} open incident(s) have no corrective action recorded.",
            styles["RptBody"]))
    story.append(Paragraph(
        "Reading note: a rising near-miss/hazard count usually reflects improving reporting "
        "culture, not a more dangerous site. The pattern worth watching is proactive reports "
        "falling while injuries hold steady — that combination suggests under-reporting.",
        styles["RptCaption"]))

    # --- Recent incidents table ---
    if incidents:
        story.append(PageBreak())
        story.append(Paragraph("Recent Incidents", styles["RptH2"]))
        rows = [["#", "Type", "Severity", "Status", "Date"]]
        for inc in incidents[:25]:
            rows.append([
                str(inc.get("id", "")),
                (inc.get("incident_type") or "")[:20],
                inc.get("severity", ""),
                inc.get("status", ""),
                _fmt_log_time(inc.get("created_at")) if inc.get("created_at") else "",
            ])
        it = Table(rows, colWidths=[0.4*inch, 1.8*inch, 1*inch, 1.2*inch, 1.8*inch])
        it.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), NAVY), ("TEXTCOLOR", (0,0), (-1,0), _rl_colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 8.5),
            ("GRID", (0,0), (-1,-1), 0.4, _rl_colors.HexColor("#d3dae6")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [_rl_colors.white, _rl_colors.HexColor("#f6f8fb")]),
            ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]))
        story.append(it)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            topMargin=0.7*inch, bottomMargin=0.7*inch,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            title="MWDTS Safety & Operations Report")
    doc.build(story)
    return buf.getvalue()


def generate_executive_monthly_report(tasks, assets, incidents, parts_lookup, month_start=None):
    """Board-ready monthly PDF: Safety (TRIFR), Production vs Target,
    and Top 5 Cost Drivers — deliberately narrower than
    generate_pdf_report()'s full operational detail, matching what an
    executive audience actually wants (three headline numbers, not
    every reliability metric a maintenance supervisor would need).

    Every number here is computed by a function ALSO used elsewhere in
    the app (compute_trifr, compute_monthly_production_vs_target,
    top_cost_drivers) — none of this report's figures are calculated
    fresh just for this PDF, so it can't show something a supervisor
    wouldn't also see on their own screen.

    Auto-emailing this on the 1st of every month, as originally
    requested, isn't something Streamlit can do on its own — there's
    no background scheduler here, only code that runs while someone
    has the app open. This generates the report on demand; sending it
    out automatically would need an external scheduler (e.g. a cron
    job hitting a small script) triggering this same function.
    """
    if not PDF_REPORT_AVAILABLE:
        return None
    if not month_start:
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    NAVY = _rl_colors.HexColor("#001530")
    GRAY = _rl_colors.HexColor("#475569")

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("ExecTitle", fontSize=20, leading=26,
                              textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=6))
    styles.add(ParagraphStyle("ExecSub", fontSize=11, leading=15,
                              textColor=GRAY, fontName="Helvetica", spaceAfter=16))
    styles.add(ParagraphStyle("ExecH2", fontSize=14, leading=18,
                              textColor=NAVY, fontName="Helvetica-Bold",
                              spaceBefore=16, spaceAfter=8))
    styles.add(ParagraphStyle("ExecBody", fontSize=10, leading=14, spaceAfter=6))
    styles.add(ParagraphStyle("ExecCaption", fontSize=8.5, leading=11,
                              textColor=GRAY, spaceAfter=10))

    def metric_table(rows):
        t = Table(rows, colWidths=[2.6*inch, 3.6*inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 9.5),
            ("TEXTCOLOR", (0,0), (0,-1), NAVY),
            ("GRID", (0,0), (-1,-1), 0.5, _rl_colors.HexColor("#d3dae6")),
            ("ROWBACKGROUNDS", (0,0), (-1,-1), [_rl_colors.white, _rl_colors.HexColor("#f6f8fb")]),
            ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))
        return t

    story = []
    story.append(Paragraph("MWDTS Executive Monthly Report", styles["ExecTitle"]))
    story.append(Paragraph(
        f"{month_start.strftime('%B %Y')} — Generated {datetime.now().strftime('%B %d, %Y at %H:%M')}",
        styles["ExecSub"]))

    # --- Safety: TRIFR ---
    story.append(Paragraph("Safety", styles["ExecH2"]))
    hours_worked = compute_hours_worked(month_start, datetime.now())
    trifr = compute_trifr(incidents, hours_worked)
    story.append(metric_table([
        ["TRIFR (Total Recordable Injury Frequency Rate)",
        f"{trifr}" if trifr is not None else "No data — hours worked not yet logged via Crew Clock"],
        ["Hours Worked This Month", f"{hours_worked:,.0f}" if hours_worked else "0"],
    ]))
    story.append(Paragraph(
        "TRIFR = (recordable injuries × 1,000,000) ÷ hours worked. Requires Crew Clock punch "
        "data to compute — a site not yet using Crew Clock will show no data here, not a false zero.",
        styles["ExecCaption"]))

    # --- Production vs Target ---
    story.append(Paragraph("Production vs Target", styles["ExecH2"]))
    ore_actual, ore_target, ore_pct = compute_monthly_production_vs_target(month_start)
    story.append(metric_table([
        ["Ore Production This Month", f"{ore_actual:,.0f} tonnes" if ore_actual else "No data yet"],
        ["Monthly Target", f"{ore_target:,.0f} tonnes"],
        ["% of Target", f"{ore_pct:.0f}%" if ore_pct is not None else "N/A"],
    ]))

    # --- Top 5 Cost Drivers ---
    story.append(Paragraph("Top 5 Cost Drivers", styles["ExecH2"]))
    top5 = top_cost_drivers(assets, tasks, parts_lookup, top_n=5)
    if not top5:
        story.append(Paragraph("No cost data recorded yet.", styles["ExecBody"]))
    else:
        rows = [["Asset", "Total Spend (Parts + Labour)"]]
        for c in top5:
            rows.append([c["asset_name"], f"${c['spend']:,.2f}"])
        ct = Table(rows, colWidths=[3.6*inch, 2.6*inch])
        ct.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), NAVY), ("TEXTCOLOR", (0,0), (-1,0), _rl_colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 9.5),
            ("GRID", (0,0), (-1,-1), 0.4, _rl_colors.HexColor("#d3dae6")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [_rl_colors.white, _rl_colors.HexColor("#f6f8fb")]),
            ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(ct)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            topMargin=0.7*inch, bottomMargin=0.7*inch,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            title="MWDTS Executive Monthly Report")
    doc.build(story)
    return buf.getvalue()


def generate_motor_test_certificate(rewind):
    """Builds a formatted motor rewind test certificate PDF — the
    actual point being that a technician's recorded test values
    become a professional, shareable document the moment QC is
    signed off, rather than test readings scribbled on a workshop
    notepad that never leaves the bench. Returns PDF bytes, or None
    if reportlab isn't available.
    """
    if not PDF_REPORT_AVAILABLE:
        return None

    NAVY = _rl_colors.HexColor("#001530")
    GRAY = _rl_colors.HexColor("#475569")

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("CertTitle", fontSize=20, leading=26,
                              textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=6))
    styles.add(ParagraphStyle("CertSub", fontSize=11, leading=15,
                              textColor=GRAY, fontName="Helvetica", spaceAfter=16))
    styles.add(ParagraphStyle("CertH2", fontSize=14, leading=18,
                              textColor=NAVY, fontName="Helvetica-Bold",
                              spaceBefore=16, spaceAfter=8))
    styles.add(ParagraphStyle("CertCaption", fontSize=8.5, leading=11,
                              textColor=GRAY, spaceAfter=10))

    def cert_table(rows):
        t = Table(rows, colWidths=[2.6*inch, 3.6*inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 9.5),
            ("TEXTCOLOR", (0,0), (0,-1), NAVY),
            ("GRID", (0,0), (-1,-1), 0.5, _rl_colors.HexColor("#d3dae6")),
            ("ROWBACKGROUNDS", (0,0), (-1,-1), [_rl_colors.white, _rl_colors.HexColor("#f6f8fb")]),
            ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))
        return t

    story = []
    story.append(Paragraph("Motor Rewind Test Certificate", styles["CertTitle"]))
    story.append(Paragraph(
        f"Certificate generated {datetime.now().strftime('%B %d, %Y at %H:%M')}",
        styles["CertSub"]))

    story.append(Paragraph("Motor Details", styles["CertH2"]))
    story.append(cert_table([
        ["Motor Tag / ID", rewind.get("motor_tag", "")],
        ["Description", rewind.get("description") or "—"],
        ["Rewind Started", _fmt_log_time(rewind.get("created_at")) if rewind.get("created_at") else "—"],
        ["Completed", _fmt_log_time(rewind.get("completed_at")) if rewind.get("completed_at") else "—"],
        ["Tested By", rewind.get("tested_by") or "—"],
    ]))

    story.append(Paragraph("Test Results", styles["CertH2"]))
    story.append(cert_table([
        ["No-load Current", rewind.get("test_no_load_current") or "Not recorded"],
        ["Resistance", rewind.get("test_resistance") or "Not recorded"],
        ["Insulation Megger", rewind.get("test_insulation_megger") or "Not recorded"],
        ["Hi-Pot Result", rewind.get("test_hipot_result") or "Not recorded"],
    ]))
    story.append(Paragraph(
        "This certificate reflects test values as recorded by the technician at QC sign-off. "
        "Not recorded fields indicate no value was entered — this is not the same as a passing result.",
        styles["CertCaption"]))

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            topMargin=0.7*inch, bottomMargin=0.7*inch,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            title=f"Motor Test Certificate - {rewind.get('motor_tag', '')}")
    doc.build(story)
    return buf.getvalue()


def export_feedback_csv(feedback_list, vote_counts):
    if not feedback_list or not PANDAS_AVAILABLE:
        return None
    rows = []
    for f in feedback_list:
        row = dict(f)
        row['vote_count'] = vote_counts.get(f.get('id'), 0)
        rows.append(row)
    df = pd.DataFrame(rows)
    cols = ['id', 'title', 'category', 'status', 'vote_count', 'submitted_by',
            'description', 'admin_response', 'responded_by', 'responded_at', 'created_at']
    existing_cols = [c for c in cols if c in df.columns]
    df = df[existing_cols]
    return df.to_csv(index=False)

# -------------------------------
# 19. PUSH NOTIFICATIONS
# -------------------------------
def send_push_notification(title, body):
    try:
        st.toast(f"{title}: {body}")
    except:
        pass

# -------------------------------
# 20. RECURRING TASK HANDLER
# -------------------------------
def handle_recurring_tasks():
    """Roll forward due preventive-maintenance tasks.

    THROTTLED. This used to run on every Streamlit rerun — i.e. on every
    click, checkbox, and dropdown change. Each run both INSERTS a new
    task and updates the original's due date, so rapid reruns could
    spawn duplicate work orders and it hammered the database on every
    interaction. It now runs at most once every RECURRING_CHECK_MINUTES
    per session.
    """
    if not SUPABASE_AVAILABLE:
        return

    RECURRING_CHECK_MINUTES = 15
    last = st.session_state.get("_last_recurring_check")
    if last and (datetime.now() - last) < timedelta(minutes=RECURRING_CHECK_MINUTES):
        return
    st.session_state._last_recurring_check = datetime.now()

    try:
        res = supabase.table("tasks").select("*").eq("is_recurring", True).execute()
        if not res.data:
            return
        now = datetime.now()
        for task in res.data:
            recurrence_type = task.get('recurrence_type')

            # Meter-based (Job Plan Auto-Scheduler) — handled separately
            # from the date-based logic below, since its trigger
            # condition is a meter reading crossing a threshold, not a
            # due_date passing. Checked first so these tasks don't also
            # fall through into the date-based branch, which would
            # otherwise skip them anyway (their due_date is often
            # unset/not meaningful) but do so silently rather than
            # explicitly.
            if recurrence_type == 'meter-based':
                if not task.get('asset_id') or not task.get('meter_interval') or task.get('next_meter_threshold') is None:
                    continue
                try:
                    _mr = supabase.table("meter_readings").select("reading") \
                        .eq("asset_id", task['asset_id']).order("recorded_at", desc=True).limit(1).execute()
                    if not _mr.data:
                        continue
                    current_reading = float(_mr.data[0]["reading"])
                except Exception as e:
                    log_error(str(e), endpoint="handle_recurring_tasks_meter_read")
                    continue
                if current_reading < task['next_meter_threshold']:
                    continue
                new_meter_task = {
                    "title": task['title'],
                    "location": task['location'],
                    "priority": task['priority'],
                    "loto": task.get('loto', False),
                    "jsa": task.get('jsa', False),
                    "status": "Unassigned",
                    "assigned_to": "Unassigned",
                    "due_date": now.isoformat(),
                    "is_recurring": True,
                    "recurrence_type": "meter-based",
                    "asset_id": task['asset_id'],
                    "meter_interval": task['meter_interval'],
                    # This new instance's OWN next threshold — anchored
                    # to the reading that just triggered it, not the
                    # original's now-stale threshold, so consecutive
                    # intervals stay evenly spaced even if this reading
                    # overshot the threshold by some amount.
                    "next_meter_threshold": current_reading + task['meter_interval'],
                }
                _insert_res = supabase.table("tasks").insert(new_meter_task).execute()
                if not _insert_res.data:
                    log_error("Failed to create next meter-based task instance — RLS may be "
                             "blocking writes to tasks. Threshold NOT advanced, will retry.",
                             details={"task_id": task["id"]}, endpoint="handle_recurring_tasks_meter")
                    continue
                _advance_res = supabase.table("tasks").update(
                    {"next_meter_threshold": current_reading + task['meter_interval']}
                ).eq("id", task["id"]).execute()
                if not _advance_res.data:
                    log_error("New meter-based task instance created, but failed to advance "
                             "the original's next_meter_threshold — it may be recreated again next check",
                             details={"task_id": task["id"]}, endpoint="handle_recurring_tasks_meter")
                continue

            # Uses the timezone-safe parser, not datetime.fromisoformat()
            # directly: Supabase can return timestamps with a UTC offset
            # (offset-aware), which cannot be compared to datetime.now()
            # (offset-naive) — Python raises TypeError. This was silently
            # aborting the ENTIRE recurring-task pass on the first task
            # that hit it, which also broke the "All Maintenance Tasks"
            # overdue-badge rendering with the same root cause.
            due_date = _parse_dt(task['due_date'])
            if not due_date:
                continue
            if due_date < now:
                if recurrence_type == 'daily':
                    next_due = due_date + timedelta(days=1)
                elif recurrence_type == 'weekly':
                    next_due = due_date + timedelta(weeks=1)
                elif recurrence_type == 'monthly':
                    next_due = due_date + timedelta(days=30)
                elif recurrence_type == 'quarterly':
                    next_due = due_date + timedelta(days=90)
                else:
                    continue
                end_date = _parse_dt(task.get('recurrence_end_date'))
                if end_date and next_due > end_date:
                    _stop_res = supabase.table("tasks").update({"is_recurring": False}).eq("id", task["id"]).execute()
                    if not _stop_res.data:
                        log_error("Failed to stop expired recurring task — RLS may be "
                                 "blocking writes to tasks", details={"task_id": task["id"]},
                                 endpoint="handle_recurring_tasks")
                    continue
                new_task = {
                    "title": task['title'],
                    "location": task['location'],
                    "priority": task['priority'],
                    "loto": task.get('loto', False),
                    "jsa": task.get('jsa', False),
                    "status": "Unassigned",
                    "assigned_to": "Unassigned",
                    "due_date": next_due.isoformat(),
                    "is_recurring": True,
                    "recurrence_type": recurrence_type,
                    "recurrence_end_date": task.get('recurrence_end_date')
                }
                _insert_res = supabase.table("tasks").insert(new_task).execute()
                if not _insert_res.data:
                    # Do NOT advance the original's due_date if the new
                    # instance was never actually created — doing so would
                    # silently skip an entire maintenance cycle with no
                    # task, no error, and no way to notice short of
                    # checking the database by hand. Leaving due_date
                    # alone means this task is picked up and retried on
                    # the next check instead of vanishing.
                    log_error("Failed to create next recurring task instance — RLS may be "
                             "blocking writes to tasks. Schedule NOT advanced, will retry.",
                             details={"task_id": task["id"], "recurrence_type": recurrence_type},
                             endpoint="handle_recurring_tasks")
                    continue
                _advance_res = supabase.table("tasks").update({"due_date": next_due.isoformat()}).eq("id", task["id"]).execute()
                if not _advance_res.data:
                    log_error("New recurring task instance created, but failed to advance "
                             "the original's due_date — it may be recreated again next check",
                             details={"task_id": task["id"]}, endpoint="handle_recurring_tasks")
    except Exception as e:
        log_error(str(e), endpoint="handle_recurring_tasks")

# -------------------------------
# 20A. ASSET REGISTER FUNCTIONS
# -------------------------------
def fetch_all_assets():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("assets_memory", [])
    try:
        res = supabase.table("assets").select("*").order("id", desc=False).execute()
        if res.data:
            return res.data
        return st.session_state.get("assets_memory", [])
    except Exception as e:
        log_error(str(e), endpoint="fetch_assets")
        return st.session_state.get("assets_memory", [])

def create_asset(name, asset_tag, category, location, manufacturer, model_number, serial_number,
                  install_date, status, criticality, current_meter, meter_unit, created_by):
    payload = {
        "name": name,
        "asset_tag": asset_tag,
        "category": category,
        "location": location,
        "manufacturer": manufacturer,
        "model_number": model_number,
        "serial_number": serial_number,
        "install_date": install_date.isoformat() if install_date else None,
        "status": status,
        "criticality": criticality,
        "current_meter": current_meter,
        "meter_unit": meter_unit,
        "version": 0
    }
    if not SUPABASE_AVAILABLE:
        assets = st.session_state.get("assets_memory", [])
        new_id = max([a["id"] for a in assets], default=0) + 1
        payload["id"] = new_id
        assets.append(payload)
        st.session_state.assets_memory = assets
        log_audit(created_by, "asset_create_memory", {"asset_id": new_id})
        return payload
    try:
        res = supabase.table("assets").insert(payload).execute()
        if res.data:
            asset = res.data[0]
            log_audit(created_by, "asset_create", {"asset_id": asset["id"], "name": name})
            return asset
    except Exception as e:
        log_error(str(e), details={"name": name}, endpoint="create_asset")
        return None
    return None

def update_asset(asset_id, updates, updated_by):
    if not SUPABASE_AVAILABLE:
        for a in st.session_state.get("assets_memory", []):
            if a["id"] == asset_id:
                a.update(updates)
                log_audit(updated_by, "asset_update_memory", {"asset_id": asset_id, "new": updates})
                return True
        return False
    # Fetch the CURRENT status before applying the update, but only
    # when status is actually part of this update — every other field
    # update (meter readings, name changes, etc.) skips this entirely,
    # so this doesn't add an extra read to every single asset update,
    # only the ones that could plausibly represent a status change.
    _old_status = None
    if "status" in updates:
        try:
            _current = supabase.table("assets").select("status").eq("id", asset_id).execute()
            if _current.data:
                _old_status = _current.data[0].get("status")
        except Exception as e:
            log_error(str(e), endpoint="update_asset:fetch_old_status")
    try:
        res = supabase.table("assets").update(updates).eq("id", asset_id).execute()
        if not res.data:
            return False
        log_audit(updated_by, "asset_update", {"asset_id": asset_id, "new": updates})
        # Only log a transition if status was actually part of this
        # update AND genuinely changed — re-saving the same status
        # (e.g. editing a different field on the same form) must not
        # create a false transition record.
        if "status" in updates and updates["status"] != _old_status:
            try:
                _hist_res = supabase.table("asset_status_history").insert({
                    "asset_id": asset_id, "old_status": _old_status,
                    "new_status": updates["status"], "changed_by": updated_by,
                }).execute()
                if not _hist_res.data:
                    log_error("asset_status_history insert affected 0 rows — likely RLS blocking writes",
                             endpoint="update_asset:status_history")
            except Exception as e:
                log_error(str(e), endpoint="update_asset:status_history")
        return True
    except Exception as e:
        log_error(str(e), details={"asset_id": asset_id, "updates": updates}, endpoint="update_asset")
        return False

def delete_asset(asset_id, deleted_by):
    if not SUPABASE_AVAILABLE:
        st.session_state.assets_memory = [a for a in st.session_state.get("assets_memory", []) if a["id"] != asset_id]
        log_audit(deleted_by, "asset_delete_memory", {"asset_id": asset_id})
        return True
    try:
        res = supabase.table("assets").delete().eq("id", asset_id).execute()
        if not res.data:
            return False
        log_audit(deleted_by, "asset_delete", {"asset_id": asset_id})
        return True
    except Exception as e:
        log_error(str(e), details={"asset_id": asset_id}, endpoint="delete_asset")
        return False


def fetch_asset_status_history(asset_id, start_dt=None, end_dt=None):
    if not SUPABASE_AVAILABLE:
        return []
    try:
        q = supabase.table("asset_status_history").select("*").eq("asset_id", asset_id)
        if start_dt:
            q = q.gte("changed_at", start_dt.isoformat())
        if end_dt:
            q = q.lte("changed_at", end_dt.isoformat())
        res = q.order("changed_at").execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_asset_status_history")
        return []


def compute_asset_downtime(asset_id, window_start, window_end, down_statuses=("Down", "Maintenance")):
    """Computes hours spent in a 'down' status within [window_start,
    window_end], from real logged transitions — not an estimate.

    Two edge cases matter here, both handled explicitly rather than
    ignored:
    - A status is held from one transition until the NEXT one, or
      until window_end if there is no next transition yet (the asset
      is still in that status right now).
    - Time before the FIRST recorded transition within the window is
      honestly excluded, not assumed to be any particular status —
      this table only captures transitions from when it was deployed
      onward, so there's no way to know what status applied before
      the first entry without guessing.

    Returns (downtime_hours, coverage_start) — coverage_start is the
    timestamp of the first known transition, so callers can show
    "data available from X onward" rather than silently presenting a
    partial-window number as if it covered the whole requested range.
    """
    history = fetch_asset_status_history(asset_id, start_dt=window_start, end_dt=window_end)
    if not history:
        return 0.0, None

    downtime_seconds = 0.0
    for i, entry in enumerate(history):
        status = entry.get("new_status")
        start = _parse_dt(entry.get("changed_at"))
        if not start:
            continue
        end = _parse_dt(history[i + 1]["changed_at"]) if i + 1 < len(history) else window_end
        if not end:
            end = window_end
        if status in down_statuses and end > start:
            downtime_seconds += (end - start).total_seconds()

    coverage_start = _parse_dt(history[0].get("changed_at"))
    return downtime_seconds / 3600.0, coverage_start


def compute_asset_utilization(asset_id, window_start, window_end, down_statuses=("Down", "Maintenance")):
    """Utilization % = time NOT down, over the covered window (from
    the first known transition to window_end — see
    compute_asset_downtime's coverage_start for why it isn't the
    full requested window when history doesn't reach that far back).
    Returns (utilization_pct, coverage_start), or (None, None) if
    there's no history at all to compute from."""
    downtime_hours, coverage_start = compute_asset_downtime(asset_id, window_start, window_end, down_statuses)
    if coverage_start is None:
        return None, None
    total_hours = (window_end - coverage_start).total_seconds() / 3600.0
    if total_hours <= 0:
        return None, None
    utilization_pct = max(0.0, (total_hours - downtime_hours) / total_hours * 100.0)
    return utilization_pct, coverage_start

# -------------------------------
# 20B. INVENTORY / PARTS FUNCTIONS
# -------------------------------
def fetch_all_parts():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("inventory_memory", [])
    try:
        res = supabase.table("inventory_parts").select("*").order("id", desc=False).execute()
        if res.data:
            return res.data
        return st.session_state.get("inventory_memory", [])
    except Exception as e:
        log_error(str(e), endpoint="fetch_parts")
        return st.session_state.get("inventory_memory", [])

def create_part(part_name, part_number, category, quantity_on_hand, reorder_point, reorder_qty,
                 unit_cost, supplier, bin_location, created_by):
    payload = {
        "part_name": part_name,
        "part_number": part_number,
        "category": category,
        "quantity_on_hand": quantity_on_hand,
        "reorder_point": reorder_point,
        "reorder_qty": reorder_qty,
        "unit_cost": unit_cost,
        "supplier": supplier,
        "bin_location": bin_location,
    }
    if not SUPABASE_AVAILABLE:
        parts = st.session_state.get("inventory_memory", [])
        new_id = max([p["id"] for p in parts], default=0) + 1
        payload["id"] = new_id
        parts.append(payload)
        st.session_state.inventory_memory = parts
        log_audit(created_by, "part_create_memory", {"part_id": new_id})
        return payload
    try:
        res = supabase.table("inventory_parts").insert(payload).execute()
        if res.data:
            part = res.data[0]
            log_audit(created_by, "part_create", {"part_id": part["id"], "name": part_name})
            return part
    except Exception as e:
        log_error(str(e), details={"part_name": part_name}, endpoint="create_part")
        return None
    return None

def adjust_part_quantity(part_id, delta, adjusted_by, reason="manual adjustment"):
    """delta can be negative (consumption) or positive (restock)."""
    if not SUPABASE_AVAILABLE:
        for p in st.session_state.get("inventory_memory", []):
            if p["id"] == part_id:
                p["quantity_on_hand"] = max(0, p.get("quantity_on_hand", 0) + delta)
                log_audit(adjusted_by, "part_adjust_memory", {"part_id": part_id, "delta": delta, "reason": reason})
                return True
        return False
    try:
        current = supabase.table("inventory_parts").select("quantity_on_hand").eq("id", part_id).execute()
        if not current.data:
            return False
        new_qty = max(0, current.data[0]["quantity_on_hand"] + delta)
        res = supabase.table("inventory_parts").update({"quantity_on_hand": new_qty}).eq("id", part_id).execute()
        if not res.data:
            return False
        log_audit(adjusted_by, "part_adjust", {"part_id": part_id, "delta": delta, "reason": reason})
        return True
    except Exception as e:
        log_error(str(e), details={"part_id": part_id, "delta": delta}, endpoint="adjust_part_quantity")
        return False

def delete_part(part_id, deleted_by):
    if not SUPABASE_AVAILABLE:
        st.session_state.inventory_memory = [p for p in st.session_state.get("inventory_memory", []) if p["id"] != part_id]
        log_audit(deleted_by, "part_delete_memory", {"part_id": part_id})
        return True
    try:
        res = supabase.table("inventory_parts").delete().eq("id", part_id).execute()
        if not res.data:
            return False
        log_audit(deleted_by, "part_delete", {"part_id": part_id})
        return True
    except Exception as e:
        log_error(str(e), details={"part_id": part_id}, endpoint="delete_part")
        return False

def link_part_to_task(task_id, part_id, quantity_used, used_by):
    """Records parts consumption against a task/work order and decrements stock.

    Both steps' results are checked now — previously this always
    returned True regardless of whether the stock adjustment actually
    happened, which meant a work order could show "parts used" in its
    activity log while inventory counts silently drifted from reality.
    """
    payload = {
        "task_id": task_id,
        "part_id": part_id,
        "quantity_used": quantity_used,
        "used_by": used_by,
    }
    if not SUPABASE_AVAILABLE:
        st.session_state.setdefault("task_parts_memory", []).append(payload)
    else:
        try:
            res = supabase.table("task_parts").insert(payload).execute()
            if not res.data:
                log_error("task_parts insert affected 0 rows — likely RLS blocking writes",
                         details=payload, endpoint="link_part_to_task")
                return False
        except Exception as e:
            log_error(str(e), details=payload, endpoint="link_part_to_task")
            return False
    if not adjust_part_quantity(part_id, -abs(quantity_used), used_by, reason=f"used on task #{task_id}"):
        log_error("Stock adjustment failed after recording parts usage — inventory count "
                 "may now be out of sync with what was actually consumed",
                 details=payload, endpoint="link_part_to_task")
        return False
    log_task_activity(task_id, used_by, "part_used", {"part_id": part_id, "quantity": quantity_used})
    return True

def fetch_task_parts(task_id):
    if not SUPABASE_AVAILABLE:
        return [tp for tp in st.session_state.get("task_parts_memory", []) if tp["task_id"] == task_id]
    try:
        res = supabase.table("task_parts").select("*").eq("task_id", task_id).execute()
        if res.data:
            return res.data
    except Exception as e:
        log_error(str(e), endpoint="fetch_task_parts")
    return []

# -------------------------------
# 20B2. BILL OF MATERIALS + PURCHASE ORDERS
# -------------------------------
# Suppliers are deliberately their own table, not reusing `contractors`
# — a contractor is a third party with site-access compliance
# requirements (induction, insurance); a parts supplier is just who
# you order from, and usually never needs site access at all.

def fetch_suppliers():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("suppliers_memory", [])
    try:
        res = supabase.table("suppliers").select("*").order("company_name").execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_suppliers")
        return []


def create_supplier(company_name, contact_person, contact_email, contact_phone, created_by):
    payload = {
        "company_name": company_name, "contact_person": contact_person,
        "contact_email": contact_email, "contact_phone": contact_phone,
    }
    if not SUPABASE_AVAILABLE:
        suppliers = st.session_state.get("suppliers_memory", [])
        new_id = max([s["id"] for s in suppliers], default=0) + 1
        payload["id"] = new_id
        suppliers.append(payload)
        st.session_state.suppliers_memory = suppliers
        return payload
    try:
        res = supabase.table("suppliers").insert(payload).execute()
        if res.data:
            log_audit(created_by, "supplier_create", {"company_name": company_name})
            return res.data[0]
    except Exception as e:
        log_error(str(e), details=payload, endpoint="create_supplier")
    return None


def get_bom_for_task(task_template_id):
    """Bill of Materials for a recurring/PM task template — which
    parts, and how many, it typically needs."""
    if not SUPABASE_AVAILABLE:
        return []
    try:
        res = supabase.table("boms").select("*, inventory_parts(*)") \
            .eq("task_template_id", task_template_id).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="get_bom_for_task")
        return []


def add_bom_item(task_template_id, part_id, quantity_required, added_by):
    payload = {"task_template_id": task_template_id, "part_id": part_id,
              "quantity_required": quantity_required}
    if not SUPABASE_AVAILABLE:
        return False
    try:
        res = supabase.table("boms").insert(payload).execute()
        if not res.data:
            return False
        log_audit(added_by, "bom_item_add", payload)
        return True
    except Exception as e:
        log_error(str(e), details=payload, endpoint="add_bom_item")
        return False


def remove_bom_item(bom_id, removed_by):
    if not SUPABASE_AVAILABLE:
        return False
    try:
        res = supabase.table("boms").delete().eq("id", bom_id).execute()
        if not res.data:
            return False
        log_audit(removed_by, "bom_item_remove", {"bom_id": bom_id})
        return True
    except Exception as e:
        log_error(str(e), endpoint="remove_bom_item")
        return False


def upload_document(file_bytes, filename, title, description, asset_id, uploaded_by):
    """Uploads to the 'documents' Storage bucket, then records
    metadata — matching the exact same pattern as task attachments
    elsewhere in this file. Auto-increments version if a document
    with the same title already exists for the same asset, so
    re-uploading an updated SOP doesn't silently create a same-named
    duplicate with no indication which one is current."""
    if not SUPABASE_AVAILABLE:
        return False
    try:
        ext = filename.split(".")[-1].lower()
        safe_name = (f"docs/{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
                    f"{hashlib.md5(file_bytes).hexdigest()[:8]}.{ext}")
        res = supabase.storage.from_("documents").upload(safe_name, file_bytes)
        if not res:
            log_error("documents storage upload returned falsy result", endpoint="upload_document")
            return False
        public_url = supabase.storage.from_("documents").get_public_url(safe_name)

        version = 1
        existing = supabase.table("documents").select("version") \
            .eq("title", title).eq("asset_id", asset_id).order("version", desc=True).limit(1).execute()
        if existing.data:
            version = existing.data[0].get("version", 0) + 1

        res2 = supabase.table("documents").insert({
            "title": title, "description": description, "file_url": public_url,
            "file_type": ext, "asset_id": asset_id, "uploaded_by": uploaded_by, "version": version,
        }).execute()
        if not res2.data:
            log_error("documents insert affected 0 rows — likely RLS blocking writes",
                     endpoint="upload_document")
            return False
        log_audit(uploaded_by, "document_upload", {"title": title, "version": version})
        return True
    except Exception as e:
        log_error(str(e), details={"title": title}, endpoint="upload_document")
        return False


def search_documents(query):
    if not SUPABASE_AVAILABLE or not query.strip():
        return []
    try:
        q = f"%{query.strip()}%"
        res = supabase.table("documents").select("*") \
            .or_(f"title.ilike.{q},description.ilike.{q}").order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="search_documents")
        return []


def fetch_all_documents():
    if not SUPABASE_AVAILABLE:
        return []
    try:
        res = supabase.table("documents").select("*").order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_all_documents")
        return []


def assign_shift(username, shift_start, shift_end, crew_name, assigned_by):
    """shift_start/shift_end are real datetime objects (built by
    combining a date_input and a time_input in the UI — Streamlit has
    no single combined datetime widget, unlike what the original
    source assumed)."""
    if not SUPABASE_AVAILABLE:
        return False
    if shift_end <= shift_start:
        log_error("Shift end time is not after shift start time", endpoint="assign_shift")
        return False
    try:
        res = supabase.table("shift_rosters").insert({
            "username": username, "shift_start": shift_start.isoformat(),
            "shift_end": shift_end.isoformat(), "crew_name": crew_name, "assigned_by": assigned_by,
        }).execute()
        if not res.data:
            return False
        log_audit(assigned_by, "shift_assigned", {"username": username})
        return True
    except Exception as e:
        log_error(str(e), endpoint="assign_shift")
        return False


def get_workers_on_shift(at_time=None):
    """Who's rostered on right now (or at a given time).

    Excludes crew_name='Clock' — the Crew Clock feature reuses this
    same table for punch-in/out records, using a far-future sentinel
    date as the "still punched in" end time. Without this exclusion,
    every open clock punch would always satisfy shift_end > at_time
    and leak into this supervisor-facing roster view, mixed in with
    real assigned shifts.
    """
    if not SUPABASE_AVAILABLE:
        return []
    at_time = at_time or datetime.now()
    try:
        res = supabase.table("shift_rosters").select("*") \
            .lt("shift_start", at_time.isoformat()).gt("shift_end", at_time.isoformat()) \
            .neq("crew_name", "Clock").execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="get_workers_on_shift")
        return []


def fetch_upcoming_shifts(limit=50):
    """Same crew_name='Clock' exclusion as get_workers_on_shift, and
    for the same reason — an open clock punch's far-future sentinel
    end time would otherwise always look like an 'upcoming shift'
    that never actually starts."""
    if not SUPABASE_AVAILABLE:
        return []
    try:
        res = supabase.table("shift_rosters").select("*") \
            .gt("shift_end", datetime.now().isoformat()).neq("crew_name", "Clock") \
            .order("shift_start").limit(limit).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_upcoming_shifts")
        return []


def delete_shift(shift_id, deleted_by):
    if not SUPABASE_AVAILABLE:
        return False
    try:
        res = supabase.table("shift_rosters").delete().eq("id", shift_id).execute()
        if not res.data:
            return False
        log_audit(deleted_by, "shift_deleted", {"shift_id": shift_id})
        return True
    except Exception as e:
        log_error(str(e), endpoint="delete_shift")
        return False


def fetch_budgets():
    if not SUPABASE_AVAILABLE:
        return []
    try:
        res = supabase.table("budgets").select("*, assets(name)").order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_budgets")
        return []


def create_budget(asset_id, period_label, allocated_amount, created_by):
    payload = {"asset_id": asset_id, "period_label": period_label, "allocated_amount": allocated_amount}
    if not SUPABASE_AVAILABLE:
        return None
    try:
        res = supabase.table("budgets").insert(payload).execute()
        if not res.data:
            return None
        log_audit(created_by, "budget_created", payload)
        return res.data[0]
    except Exception as e:
        log_error(str(e), details=payload, endpoint="create_budget")
        return None


def delete_budget(budget_id, deleted_by):
    if not SUPABASE_AVAILABLE:
        return False
    try:
        res = supabase.table("budgets").delete().eq("id", budget_id).execute()
        if not res.data:
            return False
        log_audit(deleted_by, "budget_deleted", {"budget_id": budget_id})
        return True
    except Exception as e:
        log_error(str(e), endpoint="delete_budget")
        return False


def actual_spend_for_asset(asset_id, tasks, parts_lookup):
    """Real spend for one asset, computed live from actual task and
    parts cost data — the same underlying calculation cost_by_asset()
    uses elsewhere in Analytics, just scoped to a single asset_id
    instead of grouped by name. This is what Budget Center compares
    an allocated amount against, so there's never a separately-tracked
    'spent' number that could drift from what tasks actually cost."""
    return sum(task_total_cost(t, parts_lookup) for t in tasks if t.get("asset_id") == asset_id)


@st.cache_data(ttl=1800)
def fetch_weather_forecast():
    """Daily precipitation forecast for the configured site, next 7
    days, via Open-Meteo — no API key needed for non-commercial use,
    which is why this app uses it rather than a key-gated provider.
    Cached for 30 minutes: weather forecasts don't change meaningfully
    minute to minute, and this avoids hitting the API on every single
    Task Dashboard page load from every user.

    Returns a list of {date, precip_mm, precip_probability_pct}
    dicts, or an empty list on ANY failure — a down API, a network
    timeout, a malformed response, or the site coordinates not being
    configured at all. This must never be the thing that breaks Task
    Dashboard just because a third-party weather service had a bad
    moment; an empty list means 'no forecast to show,' handled the
    same as 'nothing to warn about' by every caller.
    """
    if not WEATHER_CONFIGURED:
        return []
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": MINE_LATITUDE, "longitude": MINE_LONGITUDE,
                "daily": "precipitation_sum,precipitation_probability_max",
                "forecast_days": 7, "timezone": "auto",
            },
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        precip_mm = daily.get("precipitation_sum", [])
        precip_prob = daily.get("precipitation_probability_max", [])
        return [
            {"date": d, "precip_mm": precip_mm[i] if i < len(precip_mm) else None,
            "precip_probability_pct": precip_prob[i] if i < len(precip_prob) else None}
            for i, d in enumerate(dates)
        ]
    except Exception as e:
        log_error(str(e), endpoint="fetch_weather_forecast")
        return []


def weather_sensitive_tasks_at_risk(tasks, forecast, probability_threshold=60):
    """Cross-references weather-sensitive, not-yet-complete tasks
    against the forecast, returning (task, forecast_day) pairs for
    any day within the forecast where rain probability exceeds the
    threshold — regardless of a task's own due_date, since a
    weather-sensitive task without a specific due date is still worth
    flagging against tomorrow's forecast, not just tasks explicitly
    scheduled for a matching date."""
    if not forecast:
        return []
    risky_days = [d for d in forecast
                 if (d.get("precip_probability_pct") or 0) >= probability_threshold]
    if not risky_days:
        return []
    at_risk = []
    for t in tasks:
        if not t.get("weather_sensitive") or t.get("status") in ("Complete", "Blocked"):
            continue
        for day in risky_days:
            at_risk.append((t, day))
    return at_risk


@st.cache_data(ttl=86400)
def fetch_historical_weather(start_date, end_date):
    """Daily precipitation for a past date range, via Open-Meteo's
    Historical Weather API — a DIFFERENT subdomain
    (archive-api.open-meteo.com) than the forecast endpoint
    (api.open-meteo.com), easy to get wrong by assuming they share a
    host. Same no-key access for non-commercial use.

    Cached for 24 hours rather than 30 minutes like the forecast —
    historical data for a past date never changes, so there's no
    reason to refetch it as often as a live forecast.

    ERA5 data has roughly a 5-day processing delay, so very recent
    dates may come back without data — this isn't a bug in this
    function, just how the underlying dataset updates. Returns an
    empty list on any failure, same defensive contract as
    fetch_weather_forecast — a down API must never break whatever
    page called this.
    """
    if not WEATHER_CONFIGURED:
        return []
    try:
        resp = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude": MINE_LATITUDE, "longitude": MINE_LONGITUDE,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "daily": "precipitation_sum", "timezone": "auto",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        precip = daily.get("precipitation_sum", [])
        return [{"date": d, "precip_mm": precip[i] if i < len(precip) else None}
                for i, d in enumerate(dates)]
    except Exception as e:
        log_error(str(e), endpoint="fetch_historical_weather")
        return []


def rainy_vs_dry_production(production_records, historical_weather, rain_threshold_mm=1.0):
    """Compares average DAILY ore production on rainy days vs dry
    days. Ore-only, same reasoning as the KPI target comparison —
    mixing in waste rock would produce a number that doesn't mean
    what it claims to. A day counts as 'rainy' if precipitation_sum
    exceeds rain_threshold_mm (1mm default — enough to distinguish a
    genuine rain day from trace/measurement noise, not so high that
    a moderate but real rainy day gets miscounted as dry).

    Only dates with BOTH a known ore total AND known weather are
    used — a date missing either is excluded rather than guessed at.
    Returns a dict with rainy/dry average daily tonnes, sample sizes
    for each, and the percentage difference — or None fields where
    there isn't enough data to say anything real, rather than a
    misleading number built from too little.
    """
    weather_by_date = {d["date"]: d.get("precip_mm") for d in historical_weather if d.get("precip_mm") is not None}

    ore_by_date = {}
    for r in production_records:
        if "ore" not in (r.get("material_type") or "").lower():
            continue
        date_key = r.get("production_date")
        ore_by_date[date_key] = ore_by_date.get(date_key, 0) + (r.get("quantity") or 0)

    rainy_totals, dry_totals = [], []
    for date_key, ore_qty in ore_by_date.items():
        if date_key not in weather_by_date:
            continue
        if weather_by_date[date_key] > rain_threshold_mm:
            rainy_totals.append(ore_qty)
        else:
            dry_totals.append(ore_qty)

    rainy_avg = sum(rainy_totals) / len(rainy_totals) if rainy_totals else None
    dry_avg = sum(dry_totals) / len(dry_totals) if dry_totals else None
    pct_loss = None
    if rainy_avg is not None and dry_avg is not None and dry_avg > 0:
        pct_loss = (dry_avg - rainy_avg) / dry_avg * 100

    return {
        "rainy_avg_tonnes": rainy_avg, "rainy_days": len(rainy_totals),
        "dry_avg_tonnes": dry_avg, "dry_days": len(dry_totals),
        "pct_loss_on_rainy_days": pct_loss,
    }


def create_shipment(material_type, quantity, unit, transport_mode, destination, carrier,
                    expected_arrival, created_by):
    shipment_ref = f"SHP-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
    payload = {
        "shipment_ref": shipment_ref, "material_type": material_type, "quantity": quantity,
        "unit": unit, "transport_mode": transport_mode, "destination": destination,
        "carrier": carrier, "status": "Scheduled",
        "expected_arrival": expected_arrival.isoformat() if expected_arrival else None,
        "created_by": created_by,
    }
    if not SUPABASE_AVAILABLE:
        return None
    try:
        res = supabase.table("haulage_shipments").insert(payload).execute()
        if not res.data:
            log_error("haulage_shipments insert affected 0 rows — likely RLS blocking writes",
                     endpoint="create_shipment")
            return None
        log_audit(created_by, "shipment_created", {"shipment_ref": shipment_ref})
        return res.data[0]
    except Exception as e:
        log_error(str(e), details=payload, endpoint="create_shipment")
        return None


def mark_shipment_departed(shipment_id, updated_by):
    if not SUPABASE_AVAILABLE:
        return False
    try:
        res = supabase.table("haulage_shipments").update({
            "status": "In Transit", "departure_time": datetime.now().isoformat(),
        }).eq("id", shipment_id).execute()
        if not res.data:
            return False
        log_audit(updated_by, "shipment_departed", {"shipment_id": shipment_id})
        return True
    except Exception as e:
        log_error(str(e), endpoint="mark_shipment_departed")
        return False


def mark_shipment_arrived(shipment_id, delay_reason, updated_by):
    """Records the actual arrival time as right now. Lateness itself
    is NOT stored here — it's computed by comparing actual_arrival
    against expected_arrival wherever it's needed, the same
    don't-store-a-derived-fact principle already used for Budget
    Center's spend tracking. delay_reason is optional free text,
    worth capturing even for an on-time arrival in case something
    relevant happened en route that didn't end up costing time."""
    if not SUPABASE_AVAILABLE:
        return False
    try:
        res = supabase.table("haulage_shipments").update({
            "status": "Delivered", "actual_arrival": datetime.now().isoformat(),
            "delay_reason": delay_reason or None,
        }).eq("id", shipment_id).execute()
        if not res.data:
            return False
        log_audit(updated_by, "shipment_arrived", {"shipment_id": shipment_id})
        return True
    except Exception as e:
        log_error(str(e), endpoint="mark_shipment_arrived")
        return False


def fetch_shipments(status=None, limit=200):
    if not SUPABASE_AVAILABLE:
        return []
    try:
        q = supabase.table("haulage_shipments").select("*")
        if status:
            q = q.eq("status", status)
        res = q.order("created_at", desc=True).limit(limit).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_shipments")
        return []


def shipment_delay_hours(shipment):
    """Positive = late, negative = early, None = can't be computed
    yet (no actual_arrival recorded, or no expected_arrival was ever
    set for this shipment)."""
    actual = _parse_dt(shipment.get("actual_arrival"))
    expected = _parse_dt(shipment.get("expected_arrival"))
    if not actual or not expected:
        return None
    return (actual - expected).total_seconds() / 3600.0


def average_delay_hours(shipments):
    """Average delay across delivered shipments that actually have
    both timestamps to compare — shipments still in transit, or
    missing an expected_arrival, are excluded rather than silently
    treated as zero delay, which would understate the real average."""
    delays = [d for d in (shipment_delay_hours(s) for s in shipments) if d is not None]
    if not delays:
        return None
    return sum(delays) / len(delays)


def fleet_average_utilization(assets, window_start, window_end):
    """Averages compute_asset_utilization() across every asset that
    HAS enough status history to produce a real number — assets with
    zero logged transitions are excluded from the average entirely,
    not counted as 0% (which would understate fleet performance) or
    100% (which would overstate it). Returns (avg_pct, assets_counted,
    assets_total) so a caller can show 'based on N of M assets' rather
    than presenting a fleet-wide figure that's silently based on only
    a fraction of the actual fleet."""
    utils = []
    for a in assets:
        pct, _coverage = compute_asset_utilization(a["id"], window_start, window_end)
        if pct is not None:
            utils.append(pct)
    if not utils:
        return None, 0, len(assets)
    return sum(utils) / len(utils), len(utils), len(assets)


def mttr_trend(tasks, now=None):
    """This-month vs last-month MTTR, using the same
    compute_mttr_hours_v2 calculation already trusted elsewhere in
    Analytics — not a separate, parallel calculation that could give
    a different answer for the same underlying question. Returns
    (this_month_hours, this_month_n, last_month_hours, last_month_n).
    Any value can independently be None if that period doesn't have
    enough completed tasks to compute a real number — a missing prior
    month must never be silently treated as 0 (which would make any
    real MTTR look like a worsening trend by comparison)."""
    now = now or datetime.now()
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_end = this_month_start
    last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)

    def _completed_in_range(task, start, end):
        completed = _parse_dt(task.get("completed_at"))
        return completed is not None and start <= completed < end

    this_month_tasks = [t for t in tasks if _completed_in_range(t, this_month_start, now)]
    last_month_tasks = [t for t in tasks if _completed_in_range(t, last_month_start, last_month_end)]

    this_hours, this_n = compute_mttr_hours_v2(this_month_tasks)
    last_hours, last_n = compute_mttr_hours_v2(last_month_tasks)
    return this_hours, this_n, last_hours, last_n


def average_ore_grade(records):
    """Average grade across production records that actually have
    one logged — most records won't (grade is optional, and doesn't
    apply to waste rock at all), so this must exclude anything
    missing rather than treat it as 0%, which would badly understate
    real ore quality. Returns (avg_pct, sample_size) so the UI can
    show how many shift logs the average is actually based on."""
    graded = [r.get("ore_grade_pct") for r in records if r.get("ore_grade_pct") is not None]
    if not graded:
        return None, 0
    return sum(graded) / len(graded), len(graded)


def run_escalations(tasks, permits, triggered_by):
    """Checks for overdue tasks and soon-to-expire permits, sending a
    notification for each. This is NOT a scheduled background job —
    Streamlit has no true scheduler, so this only runs when something
    in the app actually calls it (a button click, or once per session
    on load). A permit expiring at 3am with nobody using the app
    won't trigger anything until someone next opens it. Genuine
    always-on scheduling would need something outside this app
    entirely — e.g. a scheduled GitHub Action or Supabase Edge
    Function hitting a dedicated trigger — not something this
    function can promise on its own.

    Fixes a real bug from the original source material: it hardcoded
    a single username ("superintendent1") to notify, which would
    silently fail to reach anyone else holding that role. This
    notifies every actual superintendent instead.
    """
    if not SUPABASE_AVAILABLE:
        return {"overdue_notified": 0, "permits_notified": 0}

    superintendents = [u["full_name"] for u in fetch_all_users_from_db()
                       if u.get("role", "").strip().lower() == "superintendent"
                       and u.get("is_approved") and u.get("full_name")]

    overdue_count = 0
    now = datetime.now()
    for task in tasks:
        if task.get("status") in ("Complete", "Blocked"):
            continue
        due = _parse_dt(task.get("due_date"))
        if due and due < now:
            for s_name in superintendents:
                send_notification(s_name, "Task Overdue",
                                  f"Task #{task['id']} — {task['title']} is overdue.")
            overdue_count += 1

    permit_count = 0
    soon = now + timedelta(hours=1)
    for p in permits:
        if p.get("status") != "Active":
            continue
        valid_until = _parse_dt(p.get("valid_until"))
        if valid_until and now < valid_until < soon:
            _issuer = p.get("issued_by")
            if _issuer:
                send_notification(_issuer, "Permit Expiring Soon",
                                  f"Permit #{p['id']} ({p.get('permit_type')}) expires within the hour.")
            permit_count += 1

    log_audit(triggered_by, "escalations_run", {"overdue": overdue_count, "permits_expiring": permit_count})
    return {"overdue_notified": overdue_count, "permits_notified": permit_count}


def detect_meter_anomaly(asset_id):
    """Flags a meter reading more than 2 standard deviations from the
    recent mean — a simple, transparent statistical check, not a
    trained model, so it's inspectable and its false-positive rate is
    predictable. Needs at least 10 readings to say anything meaningful;
    returns False (not an error) below that, since 'not enough data
    yet' and 'no anomaly' are both honestly 'nothing to flag' from
    the caller's perspective."""
    if not SUPABASE_AVAILABLE:
        return False
    try:
        res = supabase.table("meter_readings").select("reading").eq("asset_id", asset_id) \
            .order("recorded_at", desc=True).limit(50).execute()
        vals = [float(r["reading"]) for r in (res.data or []) if r.get("reading") is not None]
        if len(vals) < 10:
            return False
        mean = sum(vals) / len(vals)
        variance = sum((x - mean) ** 2 for x in vals) / len(vals)
        std = variance ** 0.5
        if std == 0:
            return False
        latest = vals[0]
        return abs(latest - mean) > 2 * std
    except Exception as e:
        log_error(str(e), endpoint="detect_meter_anomaly")
        return False


def detect_cost_anomalies(tasks, parts_lookup):
    """Flags completed tasks whose total cost is more than 2 standard
    deviations from the mean cost of OTHER tasks in the same work
    type — same simple, transparent statistical approach as
    detect_meter_anomaly() (not a trained model), extended to a new
    dimension rather than a separate detection philosophy, so both
    anomaly checks in this app reason about "unusual" the same way.

    Grouped by work_type specifically, not compared against the whole
    fleet at once — a Reactive emergency repair and a routine
    Preventive check have very different normal cost ranges, so
    comparing a task only against its own category's mean is what
    makes a flagged outlier actually meaningful rather than just
    "more expensive than an unrelated routine task."

    Needs at least 5 other tasks in the same category to compute a
    meaningful mean/std — returns no flags for categories below that,
    same "not enough data yet" reasoning as the meter check.

    Returns a list of dicts (task_id, title, work_type, cost, category_mean),
    worst (furthest from the mean) first.
    """
    by_category = {}
    for t2 in tasks:
        if t2.get("status") != "Complete":
            continue
        category = t2.get("work_type") or "Unspecified"
        cost = task_total_cost(t2, parts_lookup)
        by_category.setdefault(category, []).append({"task_id": t2["id"], "title": t2.get("title"), "cost": cost})

    anomalies = []
    for category, entries in by_category.items():
        if len(entries) < 6:  # need at least 5 OTHERS to compare each task against
            continue
        costs = [e["cost"] for e in entries]
        mean = sum(costs) / len(costs)
        variance = sum((c - mean) ** 2 for c in costs) / len(costs)
        std = variance ** 0.5
        if std == 0:
            continue
        for e in entries:
            if abs(e["cost"] - mean) > 2 * std:
                anomalies.append({
                    "task_id": e["task_id"], "title": e["title"], "work_type": category,
                    "cost": e["cost"], "category_mean": mean,
                })
    anomalies.sort(key=lambda a: abs(a["cost"] - a["category_mean"]), reverse=True)
    return anomalies


def log_production(production_date, shift, location, material_type, quantity, unit, notes, recorded_by,
                   ore_grade_pct=None):
    payload = {
        "production_date": production_date.isoformat(), "shift": shift, "location": location,
        "material_type": material_type, "quantity": quantity, "unit": unit,
        "notes": notes, "recorded_by": recorded_by, "ore_grade_pct": ore_grade_pct,
    }
    if not SUPABASE_AVAILABLE:
        return None
    try:
        res = supabase.table("shift_production").insert(payload).execute()
        if not res.data:
            log_error("shift_production insert affected 0 rows — likely RLS blocking writes",
                     endpoint="log_production")
            return None
        log_audit(recorded_by, "production_logged",
                  {"date": payload["production_date"], "shift": shift, "quantity": quantity})
        return res.data[0]
    except Exception as e:
        log_error(str(e), details=payload, endpoint="log_production")
        return None


def fetch_production_records(start_date=None, end_date=None, limit=200):
    if not SUPABASE_AVAILABLE:
        return []
    try:
        q = supabase.table("shift_production").select("*")
        if start_date:
            q = q.gte("production_date", start_date.isoformat())
        if end_date:
            q = q.lte("production_date", end_date.isoformat())
        res = q.order("production_date", desc=True).limit(limit).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_production_records")
        return []


def delete_production_record(record_id, deleted_by):
    if not SUPABASE_AVAILABLE:
        return False
    try:
        res = supabase.table("shift_production").delete().eq("id", record_id).execute()
        if not res.data:
            return False
        log_audit(deleted_by, "production_record_deleted", {"record_id": record_id})
        return True
    except Exception as e:
        log_error(str(e), endpoint="delete_production_record")
        return False


def production_totals_by_date(records):
    """Groups records by date, summing quantity WITHIN each
    (date, material_type, unit) combination separately — deliberately
    not just summing everything into one number per day, since
    'tonnes of ore' and 'tonnes of waste rock' are not interchangeable
    quantities, and silently adding them together would produce a
    number that means nothing real. Returns a dict keyed by date,
    each value itself a dict keyed by (material_type, unit)."""
    totals = {}
    for r in records:
        date_key = r.get("production_date")
        mat_key = (r.get("material_type"), r.get("unit"))
        if date_key not in totals:
            totals[date_key] = {}
        totals[date_key][mat_key] = totals[date_key].get(mat_key, 0) + (r.get("quantity") or 0)
    return totals


def get_purchase_orders(status=None):
    if not SUPABASE_AVAILABLE:
        return []
    try:
        q = supabase.table("purchase_orders").select("*, suppliers(company_name)")
        if status:
            q = q.eq("status", status)
        res = q.order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="get_purchase_orders")
        return []


def get_po_line_items(po_id):
    if not SUPABASE_AVAILABLE:
        return []
    try:
        res = supabase.table("po_line_items").select("*, inventory_parts(part_name, part_number)") \
            .eq("po_id", po_id).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="get_po_line_items")
        return []


def create_purchase_order(supplier_id, line_items, created_by):
    """line_items: list of {part_id, quantity, unit_price}. Both the
    PO header and every line item's insert result are checked — a
    line item silently failing to insert would mean a PO shows a
    total cost that doesn't match what was actually ordered."""
    if not SUPABASE_AVAILABLE or not line_items:
        return None
    try:
        po_number = f"PO-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
        total = sum(i["quantity"] * i["unit_price"] for i in line_items)
        po_res = supabase.table("purchase_orders").insert({
            "po_number": po_number, "supplier_id": supplier_id,
            "total_cost": total, "created_by": created_by, "status": "Sent",
        }).execute()
        if not po_res.data:
            log_error("purchase_orders insert affected 0 rows — likely RLS blocking writes",
                     endpoint="create_purchase_order")
            return None
        po = po_res.data[0]
        for item in line_items:
            li_res = supabase.table("po_line_items").insert({
                "po_id": po["id"], "part_id": item["part_id"],
                "quantity_ordered": item["quantity"], "unit_price": item["unit_price"],
            }).execute()
            if not li_res.data:
                log_error("po_line_items insert affected 0 rows — PO total will not match "
                         "its actual line items", details={"po_id": po["id"], "item": item},
                         endpoint="create_purchase_order")
        log_audit(created_by, "purchase_order_created", {"po_id": po["id"], "po_number": po_number})
        return po
    except Exception as e:
        log_error(str(e), endpoint="create_purchase_order")
        return None


def receive_purchase_order(po_id, received_items, received_by):
    """received_items: list of {part_id, quantity_received}. Stock is
    only adjusted for items that successfully update in
    po_line_items first — matching the same check-before-trusting
    pattern as link_part_to_task above, so a PO can't show as
    'Received' while some lines silently failed to update."""
    if not SUPABASE_AVAILABLE:
        return False
    try:
        all_ok = True
        for item in received_items:
            upd = supabase.table("po_line_items").update({
                "quantity_received": item["quantity_received"]
            }).eq("po_id", po_id).eq("part_id", item["part_id"]).execute()
            if not upd.data:
                log_error("po_line_items update affected 0 rows", details={"po_id": po_id, "item": item},
                         endpoint="receive_purchase_order")
                all_ok = False
                continue
            if not adjust_part_quantity(item["part_id"], item["quantity_received"], received_by,
                                        reason=f"received against PO #{po_id}"):
                all_ok = False
        po_res = supabase.table("purchase_orders").update({
            "status": "Received", "received_at": datetime.now().isoformat()
        }).eq("id", po_id).execute()
        if not po_res.data:
            return False
        log_audit(received_by, "purchase_order_received", {"po_id": po_id, "fully_ok": all_ok})
        return all_ok
    except Exception as e:
        log_error(str(e), endpoint="receive_purchase_order")
        return False

# -------------------------------
# 20C. INCIDENT / SAFETY REPORTING FUNCTIONS
# -------------------------------
def fetch_all_incidents():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("incidents_memory", [])
    try:
        res = supabase.table("incidents").select("*").order("id", desc=True).execute()
        if res.data:
            return res.data
        return st.session_state.get("incidents_memory", [])
    except Exception as e:
        log_error(str(e), endpoint="fetch_incidents")
        return st.session_state.get("incidents_memory", [])

def create_incident(incident_type, severity, location, description, reported_by, asset_id=None,
                    witnesses=None, immediate_action=None, paper_ref_no=None, reporter_id_no=None,
                    department=None, shift=None, reporter_suggestion=None):
    payload = {
        "incident_type": incident_type,
        "severity": severity,
        "location": location,
        "description": description,
        "reported_by": reported_by,
        "asset_id": asset_id,
        "witnesses": witnesses,
        "immediate_action": immediate_action,
        "paper_ref_no": paper_ref_no,
        "reporter_id_no": reporter_id_no,
        "department": department,
        "shift": shift,
        "reporter_suggestion": reporter_suggestion,
        "status": "Open",
        "root_cause": None,
        "corrective_action": None,
        "acknowledged_by": None,
        "acknowledged_at": None,
    }
    if not SUPABASE_AVAILABLE:
        incidents = st.session_state.get("incidents_memory", [])
        new_id = max([i["id"] for i in incidents], default=0) + 1
        payload["id"] = new_id
        payload["created_at"] = datetime.now().isoformat()
        incidents.append(payload)
        st.session_state.incidents_memory = incidents
        log_audit(reported_by, "incident_report_memory", {"incident_id": new_id, "severity": severity})
        return payload
    try:
        res = supabase.table("incidents").insert(payload).execute()
        if res.data:
            incident = res.data[0]
            log_audit(reported_by, "incident_report", {"incident_id": incident["id"], "severity": severity})
            if severity in ("Critical", "High"):
                send_external_notifications(f"⚠️ {severity} incident reported by {reported_by} at {location}: {incident_type}")
            return incident
    except Exception as e:
        log_error(str(e), details={"incident_type": incident_type}, endpoint="create_incident")
        return None
    return None

def update_incident(incident_id, updates, updated_by):
    if not SUPABASE_AVAILABLE:
        for i in st.session_state.get("incidents_memory", []):
            if i["id"] == incident_id:
                i.update(updates)
                log_audit(updated_by, "incident_update_memory", {"incident_id": incident_id, "new": updates})
                return True
        return False
    try:
        res = supabase.table("incidents").update(updates).eq("id", incident_id).execute()
        if not res.data:
            # Same silent-RLS-block failure mode fixed earlier for the
            # Owner Console write functions — PostgREST returns HTTP 200
            # with an empty result when RLS blocks the write, no
            # exception raised. Without this check, "Save Investigation"
            # would report success while nothing actually changed.
            return False
        log_audit(updated_by, "incident_update", {"incident_id": incident_id, "new": updates})
        return True
    except Exception as e:
        log_error(str(e), details={"incident_id": incident_id, "updates": updates}, endpoint="update_incident")
        return False


def acknowledge_incident(incident_id, acknowledged_by):
    """Records that a supervisor has received/taken ownership of a
    report — the digital equivalent of the paper form's supervisor
    receipt signature, and a distinct, earlier step than the full
    investigation (root cause / corrective action)."""
    return update_incident(incident_id, {
        "acknowledged_by": acknowledged_by,
        "acknowledged_at": datetime.now().isoformat(),
        "status": "Investigating",
    }, acknowledged_by)

# -------------------------------
# 20D. KPI / ANALYTICS HELPERS
# -------------------------------
def compute_mttr_hours(tasks):
    """Mean Time To Repair: average hours between task creation and completion, for Complete tasks with timestamps."""
    durations = []
    for t in tasks:
        if t.get('status') == 'Complete' and t.get('created_at') and t.get('due_date'):
            try:
                created = datetime.fromisoformat(str(t['created_at']).replace('Z', '+00:00').split('+')[0])
                completed_ref = datetime.fromisoformat(str(t['due_date']).replace('Z', '+00:00').split('+')[0])
                delta = (completed_ref - created).total_seconds() / 3600.0
                if delta >= 0:
                    durations.append(delta)
            except Exception:
                continue
    if not durations:
        return None
    return sum(durations) / len(durations)

def compute_pm_compliance(tasks):
    """Percentage of recurring/PM tasks completed on or before their due date."""
    pm_tasks = [t for t in tasks if t.get('is_recurring')]
    if not pm_tasks:
        return None
    on_time = 0
    for t in pm_tasks:
        if t.get('status') == 'Complete':
            on_time += 1
    return round((on_time / len(pm_tasks)) * 100, 1)

def compute_asset_downtime_ranking(tasks, assets):
    """Ranks assets by number of associated maintenance tasks (proxy for downtime frequency)."""
    counts = {}
    for t in tasks:
        aid = t.get('asset_id')
        if aid:
            counts[aid] = counts.get(aid, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    asset_lookup = {a['id']: a['name'] for a in assets}
    return [(asset_lookup.get(aid, f"Asset #{aid}"), cnt) for aid, cnt in ranked]

# -------------------------------
# 20E. PERMIT TO WORK / LOTO REGISTER
# -------------------------------
FAILURE_CODES = {
    "BRG": "Bearing failure", "SEAL": "Seal / gasket leak", "BELT": "Belt wear or breakage",
    "HYD": "Hydraulic system fault", "ELEC": "Electrical fault", "MOTOR": "Motor failure",
    "SENSOR": "Sensor / instrumentation fault", "STRUCT": "Structural / weld failure",
    "LUBE": "Lubrication failure", "OPER": "Operator error / misuse",
    "WEAR": "Normal wear and tear", "CORR": "Corrosion",
    # More specific than the general "ELEC" code above — needed for the
    # Heavy Equipment Electrical Health Dashboard, which distinguishes
    # alternator/starter/battery failures rather than lumping them
    # into one generic "electrical fault" bucket.
    "ALT": "Alternator failure", "STARTER": "Starter motor failure", "BATT": "Battery failure",
    "OTHER": "Other / uncategorised",
}

def _mem(key):
    return st.session_state.setdefault(key, [])

def _mem_insert(key, payload, audit_user, audit_action):
    rows = _mem(key)
    payload["id"] = max([r.get("id", 0) for r in rows], default=0) + 1
    payload.setdefault("created_at", datetime.now().isoformat())
    rows.append(payload)
    log_audit(audit_user, audit_action + "_memory", {"id": payload["id"]})
    return payload

def fetch_permits(task_id=None):
    if not SUPABASE_AVAILABLE:
        rows = _mem("permits_memory")
        return [p for p in rows if task_id is None or p.get("task_id") == task_id]
    try:
        q = supabase.table("permits").select("*").order("id", desc=True)
        if task_id is not None:
            q = q.eq("task_id", task_id)
        res = q.execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_permits")
        return []

def issue_permit(task_id, asset_id, permit_type, lock_tag_numbers, isolation_points,
                  hazards_identified, issued_by, valid_until):
    payload = {
        "task_id": task_id, "asset_id": asset_id, "permit_type": permit_type,
        "lock_tag_numbers": lock_tag_numbers, "isolation_points": isolation_points,
        "hazards_identified": hazards_identified, "issued_by": issued_by,
        "issued_at": datetime.now().isoformat(), "status": "Issued",
        "valid_until": valid_until.isoformat() if valid_until else None,
    }
    if not SUPABASE_AVAILABLE:
        return _mem_insert("permits_memory", payload, issued_by, "permit_issue")
    try:
        res = supabase.table("permits").insert(payload).execute()
        if res.data:
            permit = res.data[0]
            log_audit(issued_by, "permit_issue", {"permit_id": permit["id"], "task_id": task_id})
            if task_id:
                log_task_activity(task_id, issued_by, "permit_issued", {"permit_id": permit["id"]})
            return permit
    except Exception as e:
        log_error(str(e), details=payload, endpoint="issue_permit")
    return None

def accept_permit(permit_id, accepted_by):
    updates = {"accepted_by": accepted_by, "accepted_at": datetime.now().isoformat(), "status": "Active"}
    return _update_permit(permit_id, updates, accepted_by, "permit_accept")

def sign_back_permit(permit_id, signed_back_by):
    updates = {"signed_back_by": signed_back_by, "signed_back_at": datetime.now().isoformat(), "status": "Closed"}
    return _update_permit(permit_id, updates, signed_back_by, "permit_sign_back")

def cancel_permit(permit_id, cancelled_by):
    return _update_permit(permit_id, {"status": "Cancelled"}, cancelled_by, "permit_cancel")

def _update_permit(permit_id, updates, actor, action):
    if not SUPABASE_AVAILABLE:
        for p in _mem("permits_memory"):
            if p["id"] == permit_id:
                p.update(updates)
                log_audit(actor, action + "_memory", {"permit_id": permit_id})
                return True
        return False
    try:
        res = supabase.table("permits").update(updates).eq("id", permit_id).execute()
        if not res.data:
            return False
        log_audit(actor, action, {"permit_id": permit_id, "updates": updates})
        return True
    except Exception as e:
        log_error(str(e), details={"permit_id": permit_id}, endpoint=action)
        return False

def task_has_active_permit(task_id, permits=None):
    """Safety gate: is there a live accepted permit for this task?

    Pass `permits` (the full list) when calling inside a loop. Without
    it this issued one query per task rendered, which on a worker with
    20 assigned tasks meant 20 round trips on every single rerun.
    """
    if permits is None:
        candidates = fetch_permits(task_id=task_id)
    else:
        candidates = [p for p in permits if p.get("task_id") == task_id]
    for p in candidates:
        if p.get("status") == "Active":
            valid_until = p.get("valid_until")
            if valid_until:
                try:
                    if datetime.fromisoformat(str(valid_until).split("+")[0]) < datetime.now():
                        continue
                except Exception:
                    pass
            return True
    return False

# -------------------------------
# 20F. SHIFT HANDOVER LOG
# -------------------------------
def fetch_handovers(limit=50):
    if not SUPABASE_AVAILABLE:
        return sorted(_mem("handovers_memory"), key=lambda x: x.get("created_at", ""), reverse=True)[:limit]
    try:
        res = supabase.table("shift_handovers").select("*").order("created_at", desc=True).limit(limit).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_handovers")
        return []

def create_handover(shift, crew, outgoing, incoming, work_completed, work_outstanding,
                     safety_concerns, equipment_status):
    payload = {
        "shift": shift, "crew": crew, "outgoing_supervisor": outgoing,
        "incoming_supervisor": incoming, "work_completed": work_completed,
        "work_outstanding": work_outstanding, "safety_concerns": safety_concerns,
        "equipment_status": equipment_status, "acknowledged": False,
    }
    if not SUPABASE_AVAILABLE:
        return _mem_insert("handovers_memory", payload, outgoing, "handover_create")
    try:
        res = supabase.table("shift_handovers").insert(payload).execute()
        if res.data:
            log_audit(outgoing, "handover_create", {"handover_id": res.data[0]["id"], "shift": shift})
            if safety_concerns and safety_concerns.strip():
                send_external_notifications(f"Shift handover ({shift}) logged safety concerns by {outgoing}")
            return res.data[0]
    except Exception as e:
        log_error(str(e), details=payload, endpoint="create_handover")
    return None

def acknowledge_handover(handover_id, acknowledged_by):
    updates = {"acknowledged": True, "acknowledged_by": acknowledged_by,
               "acknowledged_at": datetime.now().isoformat()}
    if not SUPABASE_AVAILABLE:
        for h in _mem("handovers_memory"):
            if h["id"] == handover_id:
                h.update(updates)
                return True
        return False
    try:
        res = supabase.table("shift_handovers").update(updates).eq("id", handover_id).execute()
        if not res.data:
            return False
        log_audit(acknowledged_by, "handover_acknowledge", {"handover_id": handover_id})
        return True
    except Exception as e:
        log_error(str(e), endpoint="acknowledge_handover")
        return False

# -------------------------------
# 20G. CONTRACTOR MANAGEMENT
# -------------------------------
def fetch_contractors():
    if not SUPABASE_AVAILABLE:
        return _mem("contractors_memory")
    try:
        res = supabase.table("contractors").select("*").order("company_name").execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_contractors")
        return []

def create_contractor(company_name, contact_person, contact_email, contact_phone,
                       induction_date, induction_expiry, insurance_expiry,
                       competencies, notes, created_by):
    payload = {
        "company_name": company_name, "contact_person": contact_person,
        "contact_email": contact_email, "contact_phone": contact_phone,
        "induction_date": induction_date.isoformat() if induction_date else None,
        "induction_expiry": induction_expiry.isoformat() if induction_expiry else None,
        "insurance_expiry": insurance_expiry.isoformat() if insurance_expiry else None,
        "competencies": competencies, "notes": notes, "status": "Active",
    }
    if not SUPABASE_AVAILABLE:
        return _mem_insert("contractors_memory", payload, created_by, "contractor_create")
    try:
        res = supabase.table("contractors").insert(payload).execute()
        if res.data:
            log_audit(created_by, "contractor_create", {"contractor_id": res.data[0]["id"]})
            return res.data[0]
    except Exception as e:
        log_error(str(e), details=payload, endpoint="create_contractor")
    return None

def update_contractor(contractor_id, updates, updated_by):
    if not SUPABASE_AVAILABLE:
        for c in _mem("contractors_memory"):
            if c["id"] == contractor_id:
                c.update(updates)
                return True
        return False
    try:
        res = supabase.table("contractors").update(updates).eq("id", contractor_id).execute()
        if not res.data:
            return False
        log_audit(updated_by, "contractor_update", {"contractor_id": contractor_id})
        return True
    except Exception as e:
        log_error(str(e), endpoint="update_contractor")
        return False

def contractor_compliance_status(contractor):
    """Returns (label, is_blocking). Expired induction/insurance should gate site access."""
    today = datetime.now().date()
    problems = []
    for field, label in (("induction_expiry", "Induction"), ("insurance_expiry", "Insurance")):
        val = contractor.get(field)
        if not val:
            problems.append(f"{label} missing")
            continue
        try:
            exp = datetime.fromisoformat(str(val).split("T")[0]).date()
            if exp < today:
                problems.append(f"{label} EXPIRED")
            elif (exp - today).days <= 30:
                problems.append(f"{label} expires in {(exp - today).days}d")
        except Exception:
            problems.append(f"{label} unreadable")
    if not problems:
        return "Compliant", False
    # Fail CLOSED: expired, missing, or unreadable all block site access.
    # An unverifiable record is not a passing record — treating it as
    # non-blocking would let a bad date silently grant access.
    blocking = any(("EXPIRED" in p) or ("missing" in p) or ("unreadable" in p)
                   for p in problems)
    return "; ".join(problems), blocking

# -------------------------------
# 20H. METER READING TIME SERIES
# -------------------------------
def fetch_meter_readings(asset_id, limit=200):
    if not SUPABASE_AVAILABLE:
        rows = [r for r in _mem("meter_readings_memory") if r.get("asset_id") == asset_id]
        return sorted(rows, key=lambda x: x.get("recorded_at", ""))[-limit:]
    try:
        res = (supabase.table("meter_readings").select("*")
               .eq("asset_id", asset_id).order("recorded_at", desc=False)
               .limit(limit).execute())
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_meter_readings")
        return []

def log_meter_reading(asset_id, reading, meter_unit, recorded_by, notes=None):
    payload = {
        "asset_id": asset_id, "reading": reading, "meter_unit": meter_unit,
        "recorded_by": recorded_by, "notes": notes,
        "recorded_at": datetime.now().isoformat(),
    }
    if not SUPABASE_AVAILABLE:
        _mem_insert("meter_readings_memory", payload, recorded_by, "meter_reading")
    else:
        try:
            res = supabase.table("meter_readings").insert(payload).execute()
            if not res.data:
                log_error("meter_readings insert affected 0 rows — likely RLS blocking writes",
                         details=payload, endpoint="log_meter_reading")
                return False
            log_audit(recorded_by, "meter_reading", {"asset_id": asset_id, "reading": reading})
        except Exception as e:
            log_error(str(e), details=payload, endpoint="log_meter_reading")
            return False
    # Keep the asset's denormalised current reading in step. If THIS part
    # fails, the reading is still safely recorded in meter_readings (which
    # is what usage-rate/forecast calculations actually read from) — only
    # the asset card's displayed "current reading" would lag, not the
    # underlying history, so this doesn't need to fail the whole call.
    if not update_asset(asset_id, {"current_meter": reading}, recorded_by):
        log_error("Reading recorded, but failed to sync assets.current_meter",
                 details=payload, endpoint="log_meter_reading")
    return True

def meter_usage_rate(asset_id, readings=None):
    """Average units consumed per day, from the reading history.
    Returns None until there are at least two readings spanning time.

    Pass `readings` if you already fetched them — the asset expander
    renders a chart from the same data, and without this the list was
    queried twice per asset on every rerun.
    """
    if readings is None:
        readings = fetch_meter_readings(asset_id)
    if len(readings) < 2:
        return None
    try:
        first, last = readings[0], readings[-1]
        t0 = datetime.fromisoformat(str(first["recorded_at"]).split("+")[0])
        t1 = datetime.fromisoformat(str(last["recorded_at"]).split("+")[0])
        days = (t1 - t0).total_seconds() / 86400.0
        delta = float(last["reading"]) - float(first["reading"])
        if days <= 0 or delta < 0:
            return None
        return delta / days
    except Exception:
        return None

def forecast_meter_due_date(asset_id, current_meter, next_service_meter):
    """Projects when an asset will hit its next meter-based service.
    This is straight-line extrapolation from observed usage — it is a
    planning aid, not a failure prediction model."""
    rate = meter_usage_rate(asset_id)
    if not rate or rate <= 0 or next_service_meter is None:
        return None, None
    remaining = float(next_service_meter) - float(current_meter or 0)
    if remaining <= 0:
        return datetime.now(), rate
    days_out = remaining / rate
    return datetime.now() + timedelta(days=days_out), rate

# -------------------------------
# 20I. WORK ORDER COSTING
# -------------------------------
def task_parts_cost(task_id, parts_lookup):
    total = 0.0
    for tp in fetch_task_parts(task_id):
        part = parts_lookup.get(tp.get("part_id"))
        if part:
            total += float(part.get("unit_cost", 0) or 0) * float(tp.get("quantity_used", 0) or 0)
    return total

def task_total_cost(task, parts_lookup):
    labour = float(task.get("labour_hours", 0) or 0) * float(task.get("labour_rate", 0) or 0)
    return labour + task_parts_cost(task["id"], parts_lookup)

def cost_by_asset(tasks, assets, parts_lookup):
    totals = {}
    for t in tasks:
        aid = t.get("asset_id")
        if aid:
            totals[aid] = totals.get(aid, 0.0) + task_total_cost(t, parts_lookup)
    lookup = {a["id"]: a["name"] for a in assets}
    return sorted(((lookup.get(k, f"Asset #{k}"), v) for k, v in totals.items()),
                  key=lambda x: x[1], reverse=True)


def cost_by_category(tasks, parts_lookup):
    """Spend broken down by work type (Reactive/Preventive/Planned/
    Predictive/Improvement), each split into parts vs labour —
    reuses task_parts_cost() and the same labour_hours*labour_rate
    calculation task_total_cost() uses, rather than a separate
    cost formula that could drift from what Cost/Budget Center show.

    Ties directly into the existing planned_vs_reactive() percentage
    metric — that shows the WORK SPLIT, this shows the COST behind
    it, e.g. "70% of work is reactive, but reactive work is only 40%
    of spend" is a genuinely different (and useful) finding than
    either number alone.

    Returns a list of dicts sorted by total spend descending, each
    with category, parts_cost, labour_cost, total_cost.
    """
    by_type = {}
    for t in tasks:
        category = t.get("work_type") or "Unspecified"
        parts_cost = task_parts_cost(t["id"], parts_lookup)
        labour_cost = float(t.get("labour_hours", 0) or 0) * float(t.get("labour_rate", 0) or 0)
        if category not in by_type:
            by_type[category] = {"category": category, "parts_cost": 0.0, "labour_cost": 0.0, "total_cost": 0.0}
        by_type[category]["parts_cost"] += parts_cost
        by_type[category]["labour_cost"] += labour_cost
        by_type[category]["total_cost"] += parts_cost + labour_cost
    return sorted(by_type.values(), key=lambda x: x["total_cost"], reverse=True)


def get_electrical_subsection_workload(tasks):
    """Open/overdue/completed task counts for each Electrical
    Department subsection (Electrical Workshop, Carbonate Plant, Auto
    Electricals) — built specifically to address poor visibility into
    how work is distributed across the three areas, the actual stated
    problem this feature exists to solve (not a general metric added
    for its own sake).

    Tasks with no subsection set (the vast majority of tasks in this
    app, which spans the whole mine, not just Electrical) are excluded
    entirely, not lumped into an "Unspecified" bucket the way
    cost_by_category() handles a missing work_type — an unset
    subsection here just means "not Electrical Dept work," which
    isn't a meaningful category to show at all in this specific view.

    Returns a dict keyed by subsection name, each with open/overdue/
    completed_last_30d counts — always all 3 known subsections, even
    ones with zero tasks, so a supervisor can see an idle subsection
    as clearly as a busy one, not have it silently disappear from the view.
    """
    subsections = ["Electrical Workshop", "Carbonate Plant", "Auto Electricals"]
    result = {s: {"open": 0, "overdue": 0, "completed_last_30d": 0} for s in subsections}
    thirty_days_ago = datetime.now() - timedelta(days=30)
    for t2 in tasks:
        sub = t2.get("subsection")
        if sub not in subsections:
            continue
        if t2.get("status") == "Complete":
            completed_at = _parse_dt(t2.get("completed_at"))
            if completed_at and completed_at >= thirty_days_ago:
                result[sub]["completed_last_30d"] += 1
        else:
            result[sub]["open"] += 1
            due = _parse_dt(t2.get("due_date"))
            if due and due < datetime.now():
                result[sub]["overdue"] += 1
    return result


ELECTRICAL_COMPONENT_FAILURE_CODES = {"ALT": "Alternator", "STARTER": "Starter", "BATT": "Battery"}


def get_heavy_equipment_electrical_health(tasks, assets, top_n=10):
    """Ranks assets by count of alternator/starter/battery failures —
    the "Top 10 breakdown liabilities" this feature is named for.
    Only counts tasks with one of the 3 specific component failure
    codes (not the generic "ELEC" code, which doesn't say WHICH
    component failed and so can't inform a targeted preventative swap).

    Returns a list of dicts sorted by total failures descending, each
    with asset_id, asset_name, and per-component counts (alt, starter,
    batt) — the per-component breakdown matters as much as the total,
    since "this machine has 5 electrical failures" is far less
    actionable than "this machine has had 5 alternator failures
    specifically," which is what actually tells you what to swap.
    """
    asset_lookup = {a["id"]: a for a in assets}
    by_asset = {}
    for t2 in tasks:
        code = t2.get("failure_code")
        if code not in ELECTRICAL_COMPONENT_FAILURE_CODES:
            continue
        aid = t2.get("asset_id")
        if aid is None:
            continue
        if aid not in by_asset:
            asset = asset_lookup.get(aid, {})
            by_asset[aid] = {"asset_id": aid, "asset_name": asset.get("name", f"Asset #{aid}"),
                            "alt": 0, "starter": 0, "batt": 0}
        key = {"ALT": "alt", "STARTER": "starter", "BATT": "batt"}[code]
        by_asset[aid][key] += 1

    ranked = list(by_asset.values())
    for r in ranked:
        r["total"] = r["alt"] + r["starter"] + r["batt"]
    ranked.sort(key=lambda r: r["total"], reverse=True)
    return ranked[:top_n]


def get_electrical_failure_trends_by_category(tasks, assets):
    """Groups electrical component failures by asset CATEGORY (e.g.
    "Loader", "Haul Truck") rather than by individual machine — this
    is what surfaces a trend like "all alternator failures are on
    Loaders" that get_heavy_equipment_electrical_health()'s per-
    machine ranking can't show on its own (that view can tell you
    WHICH machine is the worst offender, but not whether the failure
    pattern is specific to that one machine or endemic to its whole
    equipment class).

    Returns a dict keyed by (category, component) tuples with failure
    counts — deliberately not pre-filtered to "trends only," since
    deciding what counts as a meaningful trend (2 failures? 5?) is a
    judgment call for whoever's reading this, not a threshold to bake
    into the data itself.
    """
    asset_lookup = {a["id"]: a for a in assets}
    counts = {}
    for t2 in tasks:
        code = t2.get("failure_code")
        if code not in ELECTRICAL_COMPONENT_FAILURE_CODES:
            continue
        aid = t2.get("asset_id")
        if aid is None:
            continue
        category = asset_lookup.get(aid, {}).get("category") or "Uncategorised"
        component = ELECTRICAL_COMPONENT_FAILURE_CODES[code]
        key = (category, component)
        counts[key] = counts.get(key, 0) + 1
    return counts


def get_low_stock_electrical_parts(parts):
    """Electrical-category parts at or below their reorder point —
    the detection half of "Electrical Critical Spares Auto-
    Replenishment." Reuses the exact same reorder_point comparison
    already used throughout Inventory (Stock Levels, the low-stock
    banners), not a separate threshold calculation, so this can't
    disagree with what Inventory itself already shows as low stock.

    Scoped to category == "Electrical" specifically — the general
    Inventory low-stock view already covers every other category;
    this exists to surface the electrical-specific subset in the
    places an Electrical Dept. supervisor actually looks (Task
    Dashboard banner, this dedicated view) rather than make them
    filter the full parts list themselves every time.
    """
    return [p for p in parts if (p.get("category") or "").strip().lower() == "electrical"
           and p.get("quantity_on_hand", 0) <= p.get("reorder_point", 0)]

# -------------------------------
# 20M. EMERGENCY RESPONSE / OUTAGE COMMANDER
# -------------------------------
def create_outage_runbook_template(template_name, steps, created_by):
    """steps is an ordered list of plain strings — each the site's own
    team's own words for a response step. This app never authors or
    suggests the CONTENT of these steps; it only tracks progress
    through whatever a qualified person has already written here.
    """
    if not steps:
        return None
    if not SUPABASE_AVAILABLE:
        templates = st.session_state.get("outage_templates_memory", [])
        new_id = max([t["id"] for t in templates], default=0) + 1
        new_template = {"id": new_id, "template_name": template_name, "steps": steps,
                        "created_by": created_by, "created_at": datetime.now().isoformat()}
        templates.append(new_template)
        st.session_state.outage_templates_memory = templates
        return new_template
    try:
        res = supabase.table("outage_runbook_templates").insert({
            "template_name": template_name, "steps": steps, "created_by": created_by,
        }).execute()
        if res.data:
            log_audit(created_by, "outage_runbook_created", {"template_name": template_name})
            return res.data[0]
        log_error("outage_runbook_templates insert affected 0 rows — likely RLS blocking writes.",
                 endpoint="create_outage_runbook_template")
        return None
    except Exception as e:
        log_error(str(e), endpoint="create_outage_runbook_template")
        return None


def fetch_outage_runbook_templates():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("outage_templates_memory", [])
    try:
        res = supabase.table("outage_runbook_templates").select("*").order("template_name").execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_outage_runbook_templates")
        return []


def start_outage_event(template_id, outage_commander, description, location, started_by):
    """Begins tracking a live outage against a pre-written runbook.
    current_step_index starts at 0 — the FIRST step of whatever
    procedure the site's own team already defined for this template.
    """
    if not SUPABASE_AVAILABLE:
        events = st.session_state.get("outage_events_memory", [])
        new_id = max([e["id"] for e in events], default=0) + 1
        new_event = {
            "id": new_id, "template_id": template_id, "outage_commander": outage_commander,
            "description": description, "location": location, "current_step_index": 0,
            "step_log": [], "status": "Active", "started_by": started_by,
            "started_at": datetime.now().isoformat(), "resolved_at": None,
        }
        events.append(new_event)
        st.session_state.outage_events_memory = events
        return new_event
    try:
        res = supabase.table("outage_events").insert({
            "template_id": template_id, "outage_commander": outage_commander,
            "description": description, "location": location, "started_by": started_by,
        }).execute()
        if res.data:
            log_audit(started_by, "outage_started", {"outage_commander": outage_commander, "location": location})
            return res.data[0]
        log_error("outage_events insert affected 0 rows — likely RLS blocking writes.",
                 endpoint="start_outage_event")
        return None
    except Exception as e:
        log_error(str(e), endpoint="start_outage_event")
        return None


def fetch_outage_events(active_only=True):
    if not SUPABASE_AVAILABLE:
        events = st.session_state.get("outage_events_memory", [])
        return [e for e in events if e["status"] == "Active"] if active_only else events
    try:
        query = supabase.table("outage_events").select("*")
        if active_only:
            query = query.eq("status", "Active")
        res = query.order("started_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_outage_events")
        return []


def advance_outage_step(event_id, step_text, completed_by, notes=None):
    """Marks the CURRENT step done and moves to the next one in the
    runbook. Appends to step_log rather than overwrite it, so the
    full timestamped sequence survives for post-incident review —
    the whole point of tracking this at all.
    """
    if not SUPABASE_AVAILABLE:
        events = st.session_state.get("outage_events_memory", [])
        event = next((e for e in events if e["id"] == event_id), None)
        if not event or event["status"] != "Active":
            return False
        event["step_log"].append({
            "step_index": event["current_step_index"], "step_text": step_text,
            "completed_at": datetime.now().isoformat(), "completed_by": completed_by, "notes": notes,
        })
        event["current_step_index"] += 1
        st.session_state.outage_events_memory = events
        return True
    try:
        res = supabase.table("outage_events").select("*").eq("id", event_id).execute()
        if not res.data or res.data[0]["status"] != "Active":
            return False
        event = res.data[0]
        new_log = list(event.get("step_log") or [])
        new_log.append({
            "step_index": event["current_step_index"], "step_text": step_text,
            "completed_at": datetime.now().isoformat(), "completed_by": completed_by, "notes": notes,
        })
        update_res = supabase.table("outage_events").update({
            "step_log": new_log, "current_step_index": event["current_step_index"] + 1,
        }).eq("id", event_id).execute()
        if update_res.data:
            log_audit(completed_by, "outage_step_completed", {"event_id": event_id, "step_text": step_text})
            return True
        return False
    except Exception as e:
        log_error(str(e), endpoint="advance_outage_step")
        return False


def resolve_outage_event(event_id, resolved_by):
    if not SUPABASE_AVAILABLE:
        events = st.session_state.get("outage_events_memory", [])
        for e in events:
            if e["id"] == event_id:
                e["status"] = "Resolved"
                e["resolved_at"] = datetime.now().isoformat()
        st.session_state.outage_events_memory = events
        return True
    try:
        res = supabase.table("outage_events").update({
            "status": "Resolved", "resolved_at": datetime.now().isoformat(),
        }).eq("id", event_id).execute()
        if res.data:
            log_audit(resolved_by, "outage_resolved", {"event_id": event_id})
            return True
        return False
    except Exception as e:
        log_error(str(e), endpoint="resolve_outage_event")
        return False

# -------------------------------
# 20N. TRANSFORMER HEALTH DASHBOARD (DGA TRACKING)
# -------------------------------
# Reference thresholds sourced from the "Condition 1-4" dissolved-gas
# table used in transformer diagnostics guidance citing IEEE C57.104
# (values as published in US Bureau of Reclamation FIST 3-31,
# "Transformer Diagnostics"). This is the older, simpler condition-
# level framework — the 2019 revision of C57.104 moved to a more
# complex statistical method using age- and equipment-type-specific
# 90th-percentile norms, which this app does not implement (that
# level of nuance genuinely needs a qualified engineer applying the
# actual standard, not a fixed lookup table).
#
# These thresholds are a STARTING REFERENCE POINT for flagging, not a
# diagnosis. A flagged reading means "compare this against the
# published guidance and get a qualified read," never "this
# transformer has fault X" — the app has no ability to actually
# diagnose a fault type, only to say a gas level exceeds a commonly-
# cited threshold. Values below are DEFAULTS ONLY — editable per the
# structure below if a site's own engineers use different limits
# (e.g. the newer statistical method, or their own utility's internal
# standard).
DGA_CONDITION_THRESHOLDS = {
    # gas_key: [(condition_1_max, condition_2_max, condition_3_max), ...] — anything above condition_3_max is Condition 4
    "hydrogen_h2": (100, 700, 1800),
    "methane_ch4": (120, 400, 1000),
    "ethane_c2h6": (65, 100, 150),
    "ethylene_c2h4": (50, 100, 200),
    "acetylene_c2h2": (35, 50, 80),
    "carbon_monoxide_co": (350, 570, 1400),
    "carbon_dioxide_co2": (2500, 4000, 10000),
}
DGA_GAS_LABELS = {
    "hydrogen_h2": "Hydrogen (H₂)", "methane_ch4": "Methane (CH₄)", "ethane_c2h6": "Ethane (C₂H₆)",
    "ethylene_c2h4": "Ethylene (C₂H₄)", "acetylene_c2h2": "Acetylene (C₂H₂)",
    "carbon_monoxide_co": "Carbon Monoxide (CO)", "carbon_dioxide_co2": "Carbon Dioxide (CO₂)",
}


def classify_dga_reading(gas_key, value):
    """Returns (condition_number, label) for a single gas reading
    against the reference thresholds above, or (None, "No data") if
    the value wasn't recorded. Condition 1 = normal, 4 = requires
    immediate qualified investigation per the cited guidance.
    """
    if value is None:
        return None, "No data"
    thresholds = DGA_CONDITION_THRESHOLDS.get(gas_key)
    if not thresholds:
        return None, "No reference threshold for this measurement"
    c1, c2, c3 = thresholds
    if value <= c1:
        return 1, "Condition 1 (Normal)"
    elif value <= c2:
        return 2, "Condition 2 (Caution)"
    elif value <= c3:
        return 3, "Condition 3 (Warning)"
    else:
        return 4, "Condition 4 (Critical — qualified review needed)"


def worst_dga_condition(test_record):
    """The single worst (highest) condition number across all gases
    in one test, plus which gas(es) drove it — a transformer's
    overall status should reflect its worst reading, not an average
    that could mask one genuinely concerning gas among several normal
    ones.
    """
    worst = 0
    worst_gases = []
    for gas_key in DGA_CONDITION_THRESHOLDS:
        condition, _ = classify_dga_reading(gas_key, test_record.get(gas_key))
        if condition and condition > worst:
            worst = condition
            worst_gases = [gas_key]
        elif condition and condition == worst and condition > 0:
            worst_gases.append(gas_key)
    return worst, worst_gases


def _maybe_create_task_for_condition4_dga(new_test, created_by):
    """If this test's worst reading is Condition 4, creates a Critical
    task for investigation — but only if one doesn't already exist and
    open for this transformer. Without that check, a transformer that
    stays at Condition 4 across several follow-up tests (which is
    exactly the situation genuinely needing attention) would spawn a
    fresh duplicate task every single time instead of one task someone
    can actually track to resolution.
    """
    worst, worst_gases = worst_dga_condition(new_test)
    if worst != 4:
        return
    _tag = new_test.get("transformer_tag", "")
    _marker = f"[Auto] Transformer {_tag} — Condition 4 DGA"
    _existing_open = [t2 for t2 in st.session_state.get("tasks", [])
                      if t2.get("status") != "Complete" and t2.get("title", "").startswith(_marker)]
    if _existing_open:
        return
    _gas_names = ", ".join(DGA_GAS_LABELS.get(g, g) for g in worst_gases)
    create_task(
        title=_marker, location=_tag, priority="Critical", loto=False, jsa=False,
        created_by=created_by, work_type="Reactive", asset_id=new_test.get("asset_id"),
        description=f"Automatically flagged — Condition 4 (Critical) DGA reading, driven by: "
                    f"{_gas_names}. Requires qualified engineer review; see Transformer Health "
                    f"for full readings and the reference thresholds used.",
    )


def create_dga_test(transformer_tag, test_date, gas_values, created_by, asset_id=None,
                     moisture_ppm=None, other_oil_test_notes=None, lab_name=None):
    """gas_values is a dict keyed by the DGA_CONDITION_THRESHOLDS keys."""
    if not SUPABASE_AVAILABLE:
        tests = st.session_state.get("dga_tests_memory", [])
        new_id = max([t["id"] for t in tests], default=0) + 1
        new_test = {
            "id": new_id, "asset_id": asset_id, "transformer_tag": transformer_tag,
            "test_date": test_date.isoformat(), "moisture_ppm": moisture_ppm,
            "other_oil_test_notes": other_oil_test_notes, "lab_name": lab_name,
            "created_by": created_by, "created_at": datetime.now().isoformat(),
            **gas_values,
        }
        tests.append(new_test)
        st.session_state.dga_tests_memory = tests
        _maybe_create_task_for_condition4_dga(new_test, created_by)
        return new_test
    try:
        payload = {
            "asset_id": asset_id, "transformer_tag": transformer_tag, "test_date": test_date.isoformat(),
            "moisture_ppm": moisture_ppm, "other_oil_test_notes": other_oil_test_notes,
            "lab_name": lab_name, "created_by": created_by, **gas_values,
        }
        res = supabase.table("transformer_dga_tests").insert(payload).execute()
        if res.data:
            log_audit(created_by, "dga_test_logged", {"transformer_tag": transformer_tag})
            _maybe_create_task_for_condition4_dga(res.data[0], created_by)
            return res.data[0]
        log_error("transformer_dga_tests insert affected 0 rows — likely RLS blocking writes.",
                 endpoint="create_dga_test")
        return None
    except Exception as e:
        log_error(str(e), endpoint="create_dga_test")
        return None


def fetch_dga_tests(transformer_tag=None):
    if not SUPABASE_AVAILABLE:
        tests = st.session_state.get("dga_tests_memory", [])
        return [t for t in tests if transformer_tag is None or t["transformer_tag"] == transformer_tag]
    try:
        query = supabase.table("transformer_dga_tests").select("*")
        if transformer_tag:
            query = query.eq("transformer_tag", transformer_tag)
        res = query.order("test_date", desc=True).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_dga_tests")
        return []

# -------------------------------
# 20O. FAULT & DISTURBANCE RECORDER (structured event log)
# -------------------------------
FAULT_TYPES = ["Single Line-to-Ground", "Line-to-Line", "Double Line-to-Ground",
               "Three-Phase", "Overload / Overcurrent", "Other"]


def _maybe_create_task_for_repeated_trips(feeder, created_by, threshold=5):
    """If this feeder has now reached the trip-count threshold (same
    5-trip threshold already used for the Fault Recorder's visual
    'bottleneck' warning, kept consistent rather than introducing a
    second, different number), creates an investigation task — but
    only once per feeder while a task for it is still open. Without
    that check, a feeder that keeps tripping past the threshold would
    spawn a new duplicate task on every single subsequent trip.
    """
    _trends = get_fault_trends_by_feeder(fetch_fault_events(), top_n=1000)
    _this_feeder = next((t2 for t2 in _trends if t2["feeder"] == feeder), None)
    if not _this_feeder or _this_feeder["total"] < threshold:
        return
    _marker = f"[Auto] {feeder} — repeated trips"
    _existing_open = [t2 for t2 in st.session_state.get("tasks", [])
                      if t2.get("status") != "Complete" and t2.get("title", "").startswith(_marker)]
    if _existing_open:
        return
    _type_breakdown = ", ".join(f"{v} {k}" for k, v in sorted(_this_feeder["by_type"].items(), key=lambda x: -x[1]))
    create_task(
        title=_marker, location=feeder, priority="High", loto=False, jsa=False,
        created_by=created_by, work_type="Reactive",
        description=f"Automatically flagged — {_this_feeder['total']} trip(s) recorded for this "
                    f"feeder ({_type_breakdown}). See Fault Recorder for full event history.",
    )


def create_fault_event(event_datetime, feeder, protection_device, fault_type, cause, created_by, notes=None):
    if not SUPABASE_AVAILABLE:
        events = st.session_state.get("fault_events_memory", [])
        new_id = max([e["id"] for e in events], default=0) + 1
        new_event = {
            "id": new_id, "event_datetime": event_datetime.isoformat(), "feeder": feeder,
            "protection_device": protection_device, "fault_type": fault_type, "cause": cause,
            "notes": notes, "created_by": created_by, "created_at": datetime.now().isoformat(),
        }
        events.append(new_event)
        st.session_state.fault_events_memory = events
        _maybe_create_task_for_repeated_trips(feeder, created_by)
        return new_event
    try:
        res = supabase.table("fault_events").insert({
            "event_datetime": event_datetime.isoformat(), "feeder": feeder,
            "protection_device": protection_device, "fault_type": fault_type,
            "cause": cause, "notes": notes, "created_by": created_by,
        }).execute()
        if res.data:
            log_audit(created_by, "fault_event_logged", {"feeder": feeder, "fault_type": fault_type})
            _maybe_create_task_for_repeated_trips(feeder, created_by)
            return res.data[0]
        log_error("fault_events insert affected 0 rows — likely RLS blocking writes.",
                 endpoint="create_fault_event")
        return None
    except Exception as e:
        log_error(str(e), endpoint="create_fault_event")
        return None


def fetch_fault_events():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("fault_events_memory", [])
    try:
        res = supabase.table("fault_events").select("*").order("event_datetime", desc=True).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_fault_events")
        return []


def get_fault_trends_by_feeder(events, top_n=10):
    """Trip counts per feeder, sorted worst-first — the actual stated
    goal of this feature ("this feeder trips way more than others").
    Also breaks each feeder's total down by fault type, since a
    feeder tripping repeatedly from the SAME fault type points to a
    specific, fixable problem, while a mix of unrelated fault types
    doesn't tell the same story even at the same total trip count.
    """
    by_feeder = {}
    for e in events:
        feeder = e.get("feeder") or "Unspecified"
        if feeder not in by_feeder:
            by_feeder[feeder] = {"feeder": feeder, "total": 0, "by_type": {}}
        by_feeder[feeder]["total"] += 1
        ftype = e.get("fault_type") or "Unspecified"
        by_feeder[feeder]["by_type"][ftype] = by_feeder[feeder]["by_type"].get(ftype, 0) + 1
    ranked = sorted(by_feeder.values(), key=lambda x: x["total"], reverse=True)
    return ranked[:top_n]

# -------------------------------
# 20P. HV SWITCHING SCHEDULE
# -------------------------------
def create_switching_order(title, feeder_circuit, scheduled_datetime, steps, created_by,
                            designated_approver, switching_officer=None):
    """Creates a switching order in Draft status — steps are the
    site's own team's own words, same reasoning as the Outage
    Commander runbook: this app tracks progress through a procedure,
    it never authors the actual switching sequence content.

    designated_approver is required and checked against created_by
    right here at creation — separation of duties is enforced at the
    moment the order is written, not left to be caught later only if
    someone remembers to check at authorization time.
    """
    if not steps:
        return None
    if not designated_approver or designated_approver.strip().lower() == (created_by or "").strip().lower():
        return None
    if not SUPABASE_AVAILABLE:
        orders = st.session_state.get("switching_orders_memory", [])
        new_id = max([o["id"] for o in orders], default=0) + 1
        new_order = {
            "id": new_id, "title": title, "feeder_circuit": feeder_circuit,
            "scheduled_datetime": scheduled_datetime.isoformat(), "switching_officer": switching_officer,
            "designated_approver": designated_approver,
            "steps": steps, "status": "Draft", "authorized_by": None, "authorized_at": None,
            "current_step_index": 0, "step_log": [], "created_by": created_by,
            "created_at": datetime.now().isoformat(), "completed_at": None,
        }
        orders.append(new_order)
        st.session_state.switching_orders_memory = orders
        return new_order
    try:
        res = supabase.table("hv_switching_orders").insert({
            "title": title, "feeder_circuit": feeder_circuit,
            "scheduled_datetime": scheduled_datetime.isoformat(), "switching_officer": switching_officer,
            "designated_approver": designated_approver,
            "steps": steps, "created_by": created_by,
        }).execute()
        if res.data:
            log_audit(created_by, "switching_order_created", {"title": title, "feeder_circuit": feeder_circuit})
            return res.data[0]
        log_error("hv_switching_orders insert affected 0 rows — likely RLS blocking writes.",
                 endpoint="create_switching_order")
        return None
    except Exception as e:
        log_error(str(e), endpoint="create_switching_order")
        return None


def fetch_switching_orders(status=None):
    if not SUPABASE_AVAILABLE:
        orders = st.session_state.get("switching_orders_memory", [])
        return [o for o in orders if status is None or o["status"] == status]
    try:
        query = supabase.table("hv_switching_orders").select("*")
        if status:
            query = query.eq("status", status)
        res = query.order("scheduled_datetime", desc=False).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_switching_orders")
        return []


def authorize_switching_order(order_id, authorized_by):
    """The sign-off gate — the pre-designated approver (set at order
    creation, and already checked there to differ from the creator)
    must be the one authorizing, checked again here at the data layer
    so this can't be bypassed by calling this function directly with
    an arbitrary name, even if a UI-level check were somehow skipped.

    Only transitions Draft -> Authorized; authorizing an order that
    isn't in Draft (e.g. already Authorized, or Completed) is
    rejected rather than silently re-stamped, since a second
    authorization on an already-moving order isn't a meaningful action.
    """
    if not SUPABASE_AVAILABLE:
        orders = st.session_state.get("switching_orders_memory", [])
        order = next((o for o in orders if o["id"] == order_id), None)
        if not order or order["status"] != "Draft":
            return False
        if (authorized_by or "").strip().lower() != (order.get("designated_approver") or "").strip().lower():
            return False
        order["status"] = "Authorized"
        order["authorized_by"] = authorized_by
        order["authorized_at"] = datetime.now().isoformat()
        st.session_state.switching_orders_memory = orders
        return True
    try:
        res = supabase.table("hv_switching_orders").select("*").eq("id", order_id).execute()
        if not res.data or res.data[0]["status"] != "Draft":
            return False
        if (authorized_by or "").strip().lower() != (res.data[0].get("designated_approver") or "").strip().lower():
            return False
        update_res = supabase.table("hv_switching_orders").update({
            "status": "Authorized", "authorized_by": authorized_by, "authorized_at": datetime.now().isoformat(),
        }).eq("id", order_id).execute()
        if update_res.data:
            log_audit(authorized_by, "switching_order_authorized", {"order_id": order_id})
            return True
        return False
    except Exception as e:
        log_error(str(e), endpoint="authorize_switching_order")
        return False


def advance_switching_step(order_id, step_text, completed_by, notes=None):
    """Marks the current step done and advances — only permitted on
    an Authorized or In Progress order. A Draft order (not yet
    signed off) or a Completed one cannot have steps advanced,
    enforcing the authorization gate at the data layer, not just in
    the UI (a UI-only gate is trivially bypassed by calling this
    function directly).
    """
    if not SUPABASE_AVAILABLE:
        orders = st.session_state.get("switching_orders_memory", [])
        order = next((o for o in orders if o["id"] == order_id), None)
        if not order or order["status"] not in ("Authorized", "In Progress"):
            return False
        order["status"] = "In Progress"
        order["step_log"].append({
            "step_index": order["current_step_index"], "step_text": step_text,
            "completed_at": datetime.now().isoformat(), "completed_by": completed_by, "notes": notes,
        })
        order["current_step_index"] += 1
        if order["current_step_index"] >= len(order["steps"]):
            order["status"] = "Completed"
            order["completed_at"] = datetime.now().isoformat()
        st.session_state.switching_orders_memory = orders
        return True
    try:
        res = supabase.table("hv_switching_orders").select("*").eq("id", order_id).execute()
        if not res.data or res.data[0]["status"] not in ("Authorized", "In Progress"):
            return False
        order = res.data[0]
        new_log = list(order.get("step_log") or [])
        new_log.append({
            "step_index": order["current_step_index"], "step_text": step_text,
            "completed_at": datetime.now().isoformat(), "completed_by": completed_by, "notes": notes,
        })
        new_index = order["current_step_index"] + 1
        updates = {"step_log": new_log, "current_step_index": new_index, "status": "In Progress"}
        if new_index >= len(order["steps"]):
            updates["status"] = "Completed"
            updates["completed_at"] = datetime.now().isoformat()
        update_res = supabase.table("hv_switching_orders").update(updates).eq("id", order_id).execute()
        if update_res.data:
            log_audit(completed_by, "switching_step_completed", {"order_id": order_id, "step_text": step_text})
            return True
        return False
    except Exception as e:
        log_error(str(e), endpoint="advance_switching_step")
        return False

# -------------------------------
# 20Q. RELAY SETTINGS DATABASE
# -------------------------------
RELAY_RECORD_TYPES = ["Baseline", "As-Found", "As-Left"]


def create_relay_setting_record(relay_tag, feeder, relay_model, record_type, settings,
                                  test_date, tested_by, notes=None):
    """settings is a dict of parameter_name: value — deliberately
    unstructured/flexible rather than fixed columns, since relay
    parameter sets vary by manufacturer and function (an overcurrent
    relay's settings look nothing like a distance relay's).
    """
    if not settings:
        return None
    if not SUPABASE_AVAILABLE:
        records = st.session_state.get("relay_records_memory", [])
        new_id = max([r["id"] for r in records], default=0) + 1
        new_record = {
            "id": new_id, "relay_tag": relay_tag, "feeder": feeder, "relay_model": relay_model,
            "record_type": record_type, "settings": settings, "test_date": test_date.isoformat(),
            "tested_by": tested_by, "notes": notes, "created_at": datetime.now().isoformat(),
        }
        records.append(new_record)
        st.session_state.relay_records_memory = records
        return new_record
    try:
        res = supabase.table("relay_setting_records").insert({
            "relay_tag": relay_tag, "feeder": feeder, "relay_model": relay_model,
            "record_type": record_type, "settings": settings, "test_date": test_date.isoformat(),
            "tested_by": tested_by, "notes": notes,
        }).execute()
        if res.data:
            log_audit(tested_by, "relay_setting_recorded", {"relay_tag": relay_tag, "record_type": record_type})
            return res.data[0]
        log_error("relay_setting_records insert affected 0 rows — likely RLS blocking writes.",
                 endpoint="create_relay_setting_record")
        return None
    except Exception as e:
        log_error(str(e), endpoint="create_relay_setting_record")
        return None


def fetch_relay_setting_records(relay_tag=None):
    if not SUPABASE_AVAILABLE:
        records = st.session_state.get("relay_records_memory", [])
        return [r for r in records if relay_tag is None or r["relay_tag"] == relay_tag]
    try:
        query = supabase.table("relay_setting_records").select("*")
        if relay_tag:
            query = query.eq("relay_tag", relay_tag)
        res = query.order("test_date", desc=True).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_relay_setting_records")
        return []


def compare_relay_settings(as_found, as_left):
    """Mechanical key-by-key comparison of two settings dicts —
    exactly what was scoped: tracking/comparison only, no engineering
    judgment about whether a difference matters. Returns a list of
    {parameter, as_found_value, as_left_value, changed} for every
    parameter present in EITHER record, so a parameter dropped
    entirely (present in one record, absent in the other) is visible
    too, not silently skipped just because it isn't in both.
    """
    as_found_settings = (as_found or {}).get("settings", {}) or {}
    as_left_settings = (as_left or {}).get("settings", {}) or {}
    all_params = sorted(set(as_found_settings.keys()) | set(as_left_settings.keys()))
    comparison = []
    for param in all_params:
        found_val = as_found_settings.get(param)
        left_val = as_left_settings.get(param)
        comparison.append({
            "parameter": param, "as_found_value": found_val, "as_left_value": left_val,
            "changed": str(found_val) != str(left_val),
        })
    return comparison

# -------------------------------
# 20R. ARC FLASH STUDY / LABEL CURRENCY TRACKING
# -------------------------------
def create_arc_flash_study(equipment_tag, location, study_date, performed_by_engineer, created_by,
                             asset_id=None, incident_energy=None, ppe_category=None,
                             arc_flash_boundary=None, notes=None):
    """Records an arc flash study/label event. Values like incident
    energy and PPE category are recorded exactly as the qualified
    engineer/firm who performed the study reported them — this app
    never calculates these itself (that requires IEEE 1584 or
    equivalent validated methods and full system data this app
    doesn't have), only tracks when the study was done and flags
    when a review is due per NFPA 70E.
    """
    if not SUPABASE_AVAILABLE:
        studies = st.session_state.get("arc_flash_studies_memory", [])
        new_id = max([s["id"] for s in studies], default=0) + 1
        new_study = {
            "id": new_id, "equipment_tag": equipment_tag, "location": location, "asset_id": asset_id,
            "study_date": study_date.isoformat(), "incident_energy_cal_cm2": incident_energy,
            "ppe_category": ppe_category, "arc_flash_boundary": arc_flash_boundary,
            "performed_by": performed_by_engineer, "notes": notes, "created_by": created_by,
            "created_at": datetime.now().isoformat(),
        }
        studies.append(new_study)
        st.session_state.arc_flash_studies_memory = studies
        return new_study
    try:
        res = supabase.table("arc_flash_studies").insert({
            "equipment_tag": equipment_tag, "location": location, "asset_id": asset_id,
            "study_date": study_date.isoformat(), "incident_energy_cal_cm2": incident_energy,
            "ppe_category": ppe_category, "arc_flash_boundary": arc_flash_boundary,
            "performed_by": performed_by_engineer, "notes": notes, "created_by": created_by,
        }).execute()
        if res.data:
            log_audit(created_by, "arc_flash_study_logged", {"equipment_tag": equipment_tag})
            return res.data[0]
        log_error("arc_flash_studies insert affected 0 rows — likely RLS blocking writes.",
                 endpoint="create_arc_flash_study")
        return None
    except Exception as e:
        log_error(str(e), endpoint="create_arc_flash_study")
        return None


def fetch_arc_flash_studies():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("arc_flash_studies_memory", [])
    try:
        res = supabase.table("arc_flash_studies").select("*").order("study_date", desc=True).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_arc_flash_studies")
        return []


def arc_flash_study_status(study, warn_days=90, review_years=5):
    """Returns (next_review_date, days_until_due, status_label).

    review_years defaults to 5 — NFPA 70E Article 130.5 requires the
    data supporting an arc flash label to be reviewed for accuracy at
    intervals not to exceed 5 years, verified directly against the
    current standard before using it as this default rather than
    relied on from memory. This is the REGULATORY MAXIMUM, not a
    recommended cadence — the standard also requires immediate review
    after any major system modification (new equipment, transformer
    or breaker changes, utility fault current changes) regardless of
    where a site is in its 5-year cycle; this app has no way to know
    when such a modification happened, so that trigger is on the
    site's own team to act on, not something flagged here.

    Same fail-closed reasoning as instrument_calibration_status(): an
    unreadable study date must never be treated as "recently
    reviewed" — that's the same false-safety risk as a stale
    instrument reading, just for arc flash PPE guidance instead.
    """
    try:
        last_study = datetime.fromisoformat(str(study["study_date"]).split("T")[0]).date()
    except Exception:
        return None, None, "overdue"
    try:
        next_review = last_study.replace(year=last_study.year + review_years)
    except ValueError:
        # last_study was a leap day (Feb 29) and the target year isn't
        # a leap year — falls back to Feb 28, the standard convention
        # for a leap-day anniversary landing on a non-leap year.
        next_review = last_study.replace(year=last_study.year + review_years, day=28)
    today = datetime.now().date()
    days_until = (next_review - today).days
    if days_until < 0:
        status = "overdue"
    elif days_until <= warn_days:
        status = "due_soon"
    else:
        status = "ok"
    return next_review, days_until, status

# -------------------------------
# 20S. TECHNICIAN COMPETENCY / CERTIFICATION TRACKING
# -------------------------------
CERTIFICATION_TYPES = ["HV Switching Authorization", "Arc Flash / Electrical Safety Training",
                       "Confined Space Entry", "Working at Heights", "First Aid / CPR", "Other"]


def create_technician_certification(technician_name, certification_type, issued_date, created_by,
                                      username=None, expiry_date=None, issuing_body=None,
                                      certificate_number=None, notes=None):
    if not SUPABASE_AVAILABLE:
        certs = st.session_state.get("technician_certs_memory", [])
        new_id = max([c["id"] for c in certs], default=0) + 1
        new_cert = {
            "id": new_id, "technician_name": technician_name, "username": username,
            "certification_type": certification_type, "issued_date": issued_date.isoformat(),
            "expiry_date": expiry_date.isoformat() if expiry_date else None,
            "issuing_body": issuing_body, "certificate_number": certificate_number,
            "notes": notes, "created_by": created_by, "created_at": datetime.now().isoformat(),
        }
        certs.append(new_cert)
        st.session_state.technician_certs_memory = certs
        return new_cert
    try:
        res = supabase.table("technician_certifications").insert({
            "technician_name": technician_name, "username": username,
            "certification_type": certification_type, "issued_date": issued_date.isoformat(),
            "expiry_date": expiry_date.isoformat() if expiry_date else None,
            "issuing_body": issuing_body, "certificate_number": certificate_number,
            "notes": notes, "created_by": created_by,
        }).execute()
        if res.data:
            log_audit(created_by, "technician_cert_logged",
                     {"technician_name": technician_name, "certification_type": certification_type})
            return res.data[0]
        log_error("technician_certifications insert affected 0 rows — likely RLS blocking writes.",
                 endpoint="create_technician_certification")
        return None
    except Exception as e:
        log_error(str(e), endpoint="create_technician_certification")
        return None


def fetch_technician_certifications(technician_name=None):
    if not SUPABASE_AVAILABLE:
        certs = st.session_state.get("technician_certs_memory", [])
        return [c for c in certs if technician_name is None or c["technician_name"] == technician_name]
    try:
        query = supabase.table("technician_certifications").select("*")
        if technician_name:
            query = query.eq("technician_name", technician_name)
        res = query.order("technician_name").execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_technician_certifications")
        return []


def technician_certification_status(cert, warn_days=30):
    """Returns (days_until_due, status_label). Certifications with no
    expiry_date at all (some certs, like a one-time First Aid course
    completion record, genuinely don't expire) return "no_expiry" —
    distinct from "ok", so a UI can choose to show these differently
    rather than implying they were checked against a date that was
    never actually set.

    Same fail-closed reasoning as every other expiry check in this
    app: an unreadable expiry date must never be treated as valid —
    getting this wrong here specifically risks someone being treated
    as currently authorized for HV switching or confined space entry
    when their actual certification status is genuinely unknown.
    """
    if not cert.get("expiry_date"):
        return None, "no_expiry"
    try:
        expiry = datetime.fromisoformat(str(cert["expiry_date"]).split("T")[0]).date()
    except Exception:
        return None, "overdue"
    today = datetime.now().date()
    days_until = (expiry - today).days
    if days_until < 0:
        status = "overdue"
    elif days_until <= warn_days:
        status = "due_soon"
    else:
        status = "ok"
    return days_until, status

# -------------------------------
# 20L. INSTRUMENT CALIBRATION & DRIFT TRACKER (Carbonate Plant)
# -------------------------------
INSTRUMENT_TYPES = ["Pressure Transmitter", "Level Sensor", "Weigh Feeder"]


def create_instrument_calibration(instrument_tag, instrument_type, location, last_calibrated_date,
                                   calibration_interval_days, created_by, notes=None):
    """Records a calibration event. Same memory-mode/Supabase-mode
    split as create_task(). next_due is computed on read (in
    instrument_calibration_status), not stored — storing a derived
    date risks it silently going stale if last_calibrated_date or
    the interval is ever edited without also updating the stored due
    date; computing it fresh is the same reasoning as MTBF/cost
    metrics elsewhere in this app never being cached.
    """
    if not SUPABASE_AVAILABLE:
        cals = st.session_state.get("instrument_calibrations_memory", [])
        new_id = max([c["id"] for c in cals], default=0) + 1
        new_cal = {
            "id": new_id, "instrument_tag": instrument_tag, "instrument_type": instrument_type,
            "location": location, "last_calibrated_date": last_calibrated_date.isoformat(),
            "calibration_interval_days": calibration_interval_days, "notes": notes,
            "created_by": created_by, "created_at": datetime.now().isoformat(),
        }
        cals.append(new_cal)
        st.session_state.instrument_calibrations_memory = cals
        return new_cal
    try:
        payload = {
            "instrument_tag": instrument_tag, "instrument_type": instrument_type, "location": location,
            "last_calibrated_date": last_calibrated_date.isoformat(),
            "calibration_interval_days": calibration_interval_days, "notes": notes, "created_by": created_by,
        }
        res = supabase.table("instrument_calibrations").insert(payload).execute()
        if res.data:
            log_audit(created_by, "instrument_calibration_logged", {"instrument_tag": instrument_tag})
            return res.data[0]
        log_error("instrument_calibrations insert affected 0 rows — likely RLS blocking writes. "
                 "Run the RLS fix in schema_additions.sql (Phase 33), then try again.",
                 details={"instrument_tag": instrument_tag}, endpoint="create_instrument_calibration")
        return None
    except Exception as e:
        log_error(str(e), endpoint="create_instrument_calibration")
        return None


def fetch_instrument_calibrations():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("instrument_calibrations_memory", [])
    try:
        res = supabase.table("instrument_calibrations").select("*").order("instrument_tag").execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_instrument_calibrations")
        return []


def instrument_calibration_status(calibration, warn_days=7):
    """Returns (next_due_date, days_until_due, status_label) for a
    single instrument. status_label is one of "overdue", "due_soon"
    (within warn_days), or "ok" — same 3-tier shape as the meter/cost
    anomaly checks elsewhere, so an owner scanning several different
    alert types in this app sees a consistent vocabulary rather than
    a different one per feature.

    Fails toward "overdue" on unreadable data (matching
    contractor_compliance_status's fail-closed reasoning): a
    calibration record this app can't parse is not the same claim as
    "recently calibrated," and treating it as fine would risk exactly
    the false-reading-shuts-down-the-plant scenario this feature
    exists to prevent.
    """
    try:
        last_cal = datetime.fromisoformat(str(calibration["last_calibrated_date"]).split("T")[0]).date()
    except Exception:
        return None, None, "overdue"
    interval = calibration.get("calibration_interval_days") or 90
    next_due = last_cal + timedelta(days=interval)
    today = datetime.now().date()
    days_until = (next_due - today).days
    if days_until < 0:
        status = "overdue"
    elif days_until <= warn_days:
        status = "due_soon"
    else:
        status = "ok"
    return next_due, days_until, status

# -------------------------------
# 20K. MOTOR REWIND KANBAN BOARD (Electrical Workshop)
# -------------------------------
MOTOR_REWIND_STAGES = ["Stripping", "Winding", "Impregnating", "Assembly", "Testing", "QC"]


def create_motor_rewind(motor_tag, description, created_by, asset_id=None):
    """Starts a new motor rewind job at the first stage (Stripping).
    Same memory-mode/Supabase-mode split as create_task()."""
    if not SUPABASE_AVAILABLE:
        rewinds = st.session_state.get("motor_rewinds_memory", [])
        new_id = max([r["id"] for r in rewinds], default=0) + 1
        new_rewind = {
            "id": new_id, "motor_tag": motor_tag, "description": description,
            "stage": MOTOR_REWIND_STAGES[0], "asset_id": asset_id, "assigned_to": None,
            "notes": None, "created_by": created_by,
            "created_at": datetime.now().isoformat(), "stage_updated_at": datetime.now().isoformat(),
            "completed_at": None,
        }
        rewinds.append(new_rewind)
        st.session_state.motor_rewinds_memory = rewinds
        return new_rewind
    try:
        payload = {
            "motor_tag": motor_tag, "description": description, "stage": MOTOR_REWIND_STAGES[0],
            "asset_id": asset_id, "created_by": created_by,
        }
        res = supabase.table("motor_rewinds").insert(payload).execute()
        if res.data:
            log_audit(created_by, "motor_rewind_started", {"motor_tag": motor_tag})
            return res.data[0]
        log_error("motor_rewinds insert affected 0 rows — likely RLS blocking writes. "
                 "Run the RLS fix in schema_additions.sql (Phase 32), then try again.",
                 details={"motor_tag": motor_tag}, endpoint="create_motor_rewind")
        return None
    except Exception as e:
        log_error(str(e), endpoint="create_motor_rewind")
        return None


def fetch_motor_rewinds(include_completed=False):
    """Active (or all, if include_completed) motor rewind jobs."""
    if not SUPABASE_AVAILABLE:
        rewinds = st.session_state.get("motor_rewinds_memory", [])
        return rewinds if include_completed else [r for r in rewinds if not r.get("completed_at")]
    try:
        query = supabase.table("motor_rewinds").select("*")
        if not include_completed:
            query = query.is_("completed_at", "null")
        res = query.order("created_at", desc=False).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_motor_rewinds")
        return []


def move_motor_rewind_stage(rewind_id, direction, updated_by, test_values=None):
    """Moves a motor rewind one stage forward or backward.
    direction is +1 (advance) or -1 (move back — e.g. a QC failure
    sending it back to Winding). Moving forward past the final stage
    (QC) marks the job completed rather than looping or erroring.

    test_values, if given, is a dict of test certificate fields
    (test_no_load_current, test_resistance, test_insulation_megger,
    test_hipot_result, tested_by) — only ever merged into the update
    when this specific call is the one completing the job. Passing it
    on any other stage transition would silently attach test results
    recorded at, say, Winding to the wrong point in the job's history.
    """
    current = None
    if not SUPABASE_AVAILABLE:
        rewinds = st.session_state.get("motor_rewinds_memory", [])
        current = next((r for r in rewinds if r["id"] == rewind_id), None)
    else:
        try:
            res = supabase.table("motor_rewinds").select("*").eq("id", rewind_id).execute()
            current = res.data[0] if res.data else None
        except Exception as e:
            log_error(str(e), endpoint="move_motor_rewind_stage_fetch")
            return False

    if not current or current.get("completed_at"):
        return False

    try:
        current_index = MOTOR_REWIND_STAGES.index(current["stage"])
    except ValueError:
        current_index = 0
    new_index = current_index + direction

    if new_index < 0:
        return False  # already at the first stage, nothing to move back to
    if new_index >= len(MOTOR_REWIND_STAGES):
        # Advancing past QC completes the job rather than erroring.
        updates = {"completed_at": datetime.now().isoformat(), "stage_updated_at": datetime.now().isoformat()}
        if test_values:
            updates.update(test_values)
    else:
        updates = {"stage": MOTOR_REWIND_STAGES[new_index], "stage_updated_at": datetime.now().isoformat()}

    if not SUPABASE_AVAILABLE:
        rewinds = st.session_state.get("motor_rewinds_memory", [])
        for r in rewinds:
            if r["id"] == rewind_id:
                r.update(updates)
        st.session_state.motor_rewinds_memory = rewinds
        return True
    try:
        res = supabase.table("motor_rewinds").update(updates).eq("id", rewind_id).execute()
        if res.data:
            log_audit(updated_by, "motor_rewind_stage_change",
                     {"rewind_id": rewind_id, "motor_tag": current.get("motor_tag"),
                      "from_stage": current["stage"], "to": updates.get("stage", "Completed")})
            return True
        return False
    except Exception as e:
        log_error(str(e), endpoint="move_motor_rewind_stage_update")
        return False

# 20J. TRUSTWORTHY MAINTENANCE ANALYTICS
# -------------------------------
def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00").split("+")[0])
    except Exception:
        return None


# =====================================================================
# FEEDBACK / SUGGESTIONS BOARD
# =====================================================================
FEEDBACK_CATEGORIES = ["Feature Request", "Bug Report", "UI/UX Improvement", "Performance", "Other"]
FEEDBACK_STATUSES = ["New", "Under Review", "Planned", "Implemented", "Declined"]


# =====================================================================
# BRANDING / COMPANY LOGO
# =====================================================================
def fetch_branding():
    """Returns the current logo URL, or None if none has been set."""
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("branding_logo_url")
    try:
        res = supabase.table("app_branding").select("*").order("id", desc=True).limit(1).execute()
        if res.data:
            return res.data[0].get("logo_url")
        return None
    except Exception as e:
        log_error(str(e), endpoint="fetch_branding")
        return None


def upload_logo(file_bytes, filename, uploaded_by):
    """Upload a company logo. Reuses validate_image (same rules as
    task proof-of-work photos) since a logo is an image, not a generic
    attachment. Stored in the public 'branding' bucket — logos aren't
    sensitive, same reasoning already applied to task photos."""
    valid, msg = validate_image(file_bytes, filename)
    if not valid:
        st.error(msg)
        return False

    if not SUPABASE_AVAILABLE:
        st.session_state["branding_logo_url"] = f"memory://{filename}"
        log_audit(uploaded_by, "logo_upload_memory", {"filename": filename})
        return True

    try:
        ext = filename.split(".")[-1].lower()
        safe_name = f"logo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(file_bytes).hexdigest()[:8]}.{ext}"
        storage_res = supabase.storage.from_("branding").upload(safe_name, file_bytes)
        if not storage_res:
            log_error("Storage upload returned a falsy result", endpoint="upload_logo")
            return False
        public_url = supabase.storage.from_("branding").get_public_url(safe_name)

        res = supabase.table("app_branding").insert({
            "logo_url": public_url,
            "uploaded_by": uploaded_by,
        }).execute()
        if not res.data:
            log_error("app_branding insert affected 0 rows — likely RLS blocking writes. "
                     "The file reached Storage but has no metadata row.",
                     endpoint="upload_logo")
            return False
        log_audit(uploaded_by, "logo_upload", {"url": public_url})
        return True
    except Exception as e:
        log_error(str(e), endpoint="upload_logo")
        return False


def remove_logo(removed_by):
    """Clears the logo by inserting a row with logo_url=None — keeps
    history (who uploaded/removed what, when) rather than deleting
    rows, consistent with how this app treats audit trails elsewhere."""
    if not SUPABASE_AVAILABLE:
        st.session_state["branding_logo_url"] = None
        return True
    try:
        res = supabase.table("app_branding").insert({
            "logo_url": None,
            "uploaded_by": removed_by,
        }).execute()
        if not res.data:
            return False
        log_audit(removed_by, "logo_remove", {})
        return True
    except Exception as e:
        log_error(str(e), endpoint="remove_logo")
        return False


# =====================================================================
# FEATURE FLAGS
# =====================================================================
# Which nav sections can actually be toggled — deliberately excludes
# Task Dashboard, Admin, and Profile. Task Dashboard is the core
# reason this app exists; Admin is where these toggles themselves
# live, so disabling it would lock the Owner out of turning anything
# back on; Profile is where anyone changes their own password.
TOGGLEABLE_MODULES = {
    "Assets": "Equipment register and meter readings.",
    "Permits": "Permit to Work / LOTO isolation records.",
    "Inventory": "Spare parts stock and reorder tracking.",
    "Incidents": "Hazard, near-miss, and injury reporting.",
    "Handover": "Shift handover logging.",
    "Contractors": "Contractor induction/insurance compliance tracking.",
    "Analytics": "KPI dashboards (MTTR, MTBF, PM compliance, etc).",
    "Chat": "Global, supervisor, and private chat.",
    "Feedback": "The internal suggestion board.",
    "Timeline": "Personal activity timeline.",
}


def fetch_feature_flags():
    """Returns {flag_key: enabled_bool} for every toggleable module.
    Fail-open by design: any module never explicitly set defaults to
    enabled, so introducing this system can never silently hide a
    feature that was already live — an admin has to deliberately turn
    something off, nothing goes dark on its own."""
    flags = {key: True for key in TOGGLEABLE_MODULES}  # fail-open defaults
    if not SUPABASE_AVAILABLE:
        flags.update(st.session_state.get("feature_flags_memory", {}))
        return flags
    try:
        res = supabase.table("app_feature_flags").select("*").execute()
        for row in (res.data or []):
            if row["flag_key"] in flags:
                flags[row["flag_key"]] = row["enabled"]
    except Exception as e:
        log_error(str(e), endpoint="fetch_feature_flags")
        # Fails open here too — a read error means every module stays
        # enabled (today's behavior), not a mysteriously empty nav bar.
    return flags


# =====================================================================
# GLOBAL SEARCH
# =====================================================================
# Two genuinely different things live under one search box: finding a
# PAGE/FEATURE (a static, curated index — no data, no permission
# concerns) and finding a RECORD (an actual live query against
# real data, which MUST respect the exact same per-role and per-row
# visibility rules each section already enforces on its own — this is
# not a shortcut around those rules, it's the same rules applied here
# too. Getting this wrong would mean a Worker could search their way
# into seeing another person's incident or task, which the app
# elsewhere goes out of its way to prevent.
FEATURE_INDEX = [
    # (keywords, display label, icon, target nav section)
    ("task dashboard my tasks assign work order", "Task Dashboard", "fa-list-check", "Task Dashboard"),
    ("assets equipment register meter reading", "Assets", "fa-server", "Assets"),
    ("permit to work loto isolation lock tag", "Permits", "fa-lock", "Permits"),
    ("inventory parts spare stock reorder bin", "Inventory", "fa-boxes-stacked", "Inventory"),
    ("incidents hazard near miss injury safety report", "Incidents", "fa-triangle-exclamation", "Incidents"),
    ("shift handover outgoing incoming supervisor", "Handover", "fa-right-left", "Handover"),
    ("contractors induction insurance compliance", "Contractors", "fa-user-group", "Contractors"),
    ("analytics kpi mttr mtbf reports dashboard", "Analytics", "fa-chart-line", "Analytics"),
    ("chat message global private supervisor", "Chat", "fa-comments", "Chat"),
    ("feedback suggestion idea vote", "Feedback", "fa-lightbulb", "Feedback"),
    ("profile change password avatar account settings", "Profile", "fa-circle-user", "Profile"),
    ("timeline activity log recent actions", "Timeline", "fa-clock-rotate-left", "Timeline"),
    ("about policy statement how it works help roles", "About", "fa-circle-info", "About"),
    ("production tracking shift output tonnes ore material", "Production", "fa-industry", "Production"),
    ("haulage logistics shipment truck rail port delay tracking", "Haulage", "fa-truck", "Haulage"),
    ("wallboard live overview screen display kanban", "Wallboard", "fa-tv", "Wallboard"),
    ("crew clock punch in out time clock hours", "Crew Clock", "fa-clock", "Crew Clock"),
    ("jsa library job safety analysis swp safe work procedure", "JSA Library", "fa-file-alt", "JSA Library"),
    ("job plans templates apply work order recurring bom", "Job Plans", "fa-cubes", "Job Plans"),
    ("locations hierarchy site area zone digital twin", "Locations", "fa-sitemap", "Locations"),
    ("admin access requests approve deny new users", "Admin — Access Requests", "fa-user-plus", "Admin"),
    ("admin access policies auto approve registration", "Admin — Access Policies", "fa-shield-halved", "Admin"),
    ("admin active users manage roles suspend", "Admin — Active Users", "fa-users-gear", "Admin"),
    ("admin decision history audit approvals", "Admin — Decision History", "fa-clock-rotate-left", "Admin"),
    ("admin auth migration supabase phase provision", "Admin — Auth Migration", "fa-key", "Admin"),
    ("admin feature toggles enable disable modules", "Admin — Feature Toggles", "fa-toggle-on", "Admin"),
    ("admin settings company logo announcement ticker poster slideshow branding",
    "Admin — Settings", "fa-gears", "Admin"),
    ("owner console branding migration feature toggles key",
    "Owner Console", "fa-key", "Owner Console"),
    ("electrical overview department status alerts summary landing",
    "Electrical Overview", "fa-bolt", "Electrical Overview"),
    ("motor rewind kanban board stripping winding impregnating assembly testing qc",
    "Motor Rewinds", "fa-wrench", "Motor Rewinds"),
    ("instrument calibration drift pressure transmitter level sensor weigh feeder",
    "Instrument Calibration", "fa-gauge", "Instrument Calibration"),
    ("outage commander emergency response runbook blackout template",
    "Outage Commander", "fa-triangle-exclamation", "Outage Commander"),
    ("transformer health dga dissolved gas analysis oil test condition",
    "Transformer Health", "fa-bolt", "Transformer Health"),
    ("fault recorder disturbance trip feeder relay breakdown trend",
    "Fault Recorder", "fa-chart-column", "Fault Recorder"),
    ("hv switching schedule authorization designated approver order feeder",
    "HV Switching Schedule", "fa-toggle-on", "HV Switching Schedule"),
    ("relay settings database as-found as-left comparison protection",
    "Relay Settings", "fa-sliders", "Relay Settings"),
    ("arc flash study label incident energy ppe boundary nfpa",
    "Arc Flash Studies", "fa-triangle-exclamation", "Arc Flash Studies"),
    ("technician certification competency hv authorization training expiry",
    "Technician Certifications", "fa-award", "Technician Certifications"),
]


# =====================================================================
# HOW IT WORKS GUIDE — plain-language explanations of every feature,
# organized by category. Built as a reliable, always-available
# foundation (works for every user, no AI key required) — the
# Maintenance Assistant chatbot draws on this same content when
# answering "how do I..." questions, so the two never disagree about
# what a feature does.
# =====================================================================
HOW_IT_WORKS_GUIDE = {
    "Core Maintenance": {
        "Task Dashboard": "Where work gets created, assigned, and tracked. Supervisors create tasks "
            "and assign them to workers; workers see their assigned tasks and mark them in progress "
            "or complete. Tasks can require LOTO isolation and JSA sign-off before starting, link to "
            "a specific asset, and be set to recur on a schedule (daily/weekly/monthly, or "
            "meter-based — auto-triggered when an asset's logged meter reading crosses an interval).",
        "Assets": "The equipment register — every machine, vehicle, and piece of infrastructure "
            "being maintained. Tracks status, meter readings (with automatic anomaly flagging if a "
            "new reading is statistically unusual), and links to the tasks performed on it.",
        "Permits": "Lock-Out/Tag-Out (LOTO) permit workflow for isolating equipment before work. A "
            "permit is issued, then must be separately accepted before a task requiring it can "
            "proceed — this two-step gate is enforced in the app's logic, not just suggested.",
        "Inventory": "Parts and stock tracking, including Purchase Orders. Parts below their reorder "
            "point are flagged automatically; electrical-category parts specifically also trigger a "
            "banner and a one-click 'pre-fill PO' action.",
        "Job Plans": "Reusable work order templates — write the steps once, apply them repeatedly. A "
            "Job Plan can also be set to meter-based recurrence, auto-creating its next task when a "
            "linked asset's meter reading crosses the configured interval.",
        "Production": "Logs shift output — material type, quantity, location — building the data "
            "behind the production-vs-target metrics shown elsewhere in the app.",
        "Haulage": "Tracks logistics: shipments, trucks, rail, port movements, and delays.",
        "Crew Clock": "Punch in/out for a shift. Punching out from a task-linked shift prompts you "
            "to select which task the hours should be applied to — this is what drives automatic "
            "labour cost tracking on tasks.",
        "Locations": "Defines your site's physical hierarchy (Site → Area → Zone → Equipment) — once "
            "set up, this powers the location dropdowns used when creating tasks and incidents "
            "elsewhere in the app.",
    },
    "Safety & Compliance": {
        "Incidents": "Report near-misses, injuries, hazards, and equipment failures. Optionally get "
            "an AI severity suggestion (if AI features are configured) before choosing severity "
            "yourself — the suggestion is never auto-applied, you always confirm it.",
        "JSA Library": "Job Safety Analyses / Safe Work Procedures — upload and organize the "
            "documents that get referenced when creating tasks requiring one.",
        "Contractors": "Tracks contractor induction and insurance compliance, with expiry alerts "
            "before either lapses.",
        "Technician Certifications": "Same compliance-tracking idea as Contractors, but for your own "
            "in-house staff — HV switching authorization, arc flash training, confined space entry, "
            "etc., each with an expiry alert.",
    },
    "Analytics & Reporting": {
        "Analytics": "Multiple tabs: Overview (quick summary), Reliability (MTBF/MTTR), Utilization, "
            "Backlog & Compliance, Failure Pareto, Cost (including anomaly detection and budget "
            "tracking), Safety, and Electrical Health (alternator/starter/battery failure trends by "
            "machine). The Cost tab can also auto-generate an Executive Monthly Report PDF.",
        "Timeline": "A chronological log of recent actions across all tasks.",
        "Wallboard": "A read-only, live overview screen — meant to be left open on a shared display, "
            "not something you interact with directly.",
    },
    "Electrical Department": {
        "Electrical Overview": "A single landing page pulling status from all 7 Electrical "
            "Department sections at once — active outages, pending switching authorizations, "
            "overdue calibrations, worst transformer condition, low-stock spares, and more — so you "
            "don't have to check each section individually.",
        "Motor Rewinds": "A visual board tracking motors through Stripping → Winding → Impregnating "
            "→ Assembly → Testing → QC. Move a motor forward or back a stage with the ◀/▶ buttons on "
            "its card. Completing the final QC stage opens a form for test values (No-load Current, "
            "Resistance, Insulation Megger, Hi-Pot), then generates a downloadable PDF test "
            "certificate.",
        "Instrument Calibration": "Tracks pressure transmitters, level sensors, and weigh feeders, "
            "alerting 7 days before a calibration is due to expire.",
        "Outage Commander": "For live outage response. Your own team writes a runbook (an ordered "
            "list of response steps) once, in advance; during a real outage, the app tracks progress "
            "through it — current step, who completed each one, and when. It never generates or "
            "suggests the actual response steps itself.",
        "Transformer Health": "Logs Dissolved Gas Analysis (DGA) test results and flags readings "
            "against a published reference table (the 'Condition 1-4' framework, sourced from "
            "guidance citing IEEE C57.104). A flag means 'get a qualified engineer's read,' never a "
            "standalone diagnosis. A Condition 4 reading automatically creates a Critical task.",
        "Fault Recorder": "A structured log of trip/fault events — feeder, protection device, fault "
            "type, cause — ranked by feeder to spot patterns (e.g. one feeder tripping repeatedly on "
            "the same fault type). A feeder reaching 5+ trips automatically creates a task.",
        "HV Switching Schedule": "Scheduled switching operations requiring sign-off. Your team writes "
            "the switching sequence; a separate, pre-designated approver (never the same person who "
            "created it) must authorize before any step can be executed — enforced by checking who's "
            "actually logged in, not a typed name.",
        "Relay Settings": "A searchable record of what's configured on each protection relay, plus "
            "As-Found/As-Left comparison during testing to catch unintended setting changes. Tracking "
            "and mechanical comparison only — no coordination analysis or engineering judgment.",
        "Arc Flash Studies": "Tracks when each panel's arc flash study was last done and flags when a "
            "review is due (defaulting to NFPA 70E's 5-year maximum interval). Incident energy, PPE "
            "category, and boundary values are recorded exactly as your engineer reported them.",
    },
    "Communication & Admin": {
        "Handover": "Structured shift handover notes between outgoing and incoming supervisors.",
        "Chat": "Global, Supervisor-only, and private messaging, plus an AI Maintenance Assistant "
            "room (if AI features are configured) that answers questions about current app data.",
        "Feedback": "Submit and vote on ideas for the app itself.",
        "Profile": "Change your password, avatar, and language preference.",
        "Admin / Owner Console": "User approval, access policies, feature toggles, and site branding "
            "— visible only to Owners and Superintendents.",
        "About": "The app's policy statement, role explanations, and general background.",
    },
}


# =====================================================================
# LANGUAGE / TRANSLATIONS
# =====================================================================
# Deliberately scoped to the highest-visibility strings (navigation,
# common actions, headers) rather than an attempt at translating every
# string in the app. With 8,600+ lines and thousands of scattered
# strings, a full pass in one sitting would mean rushed, unreviewed
# translations across 5 languages on a safety-critical app — a real
# quality risk, not just a shortcut. This is a genuine, working
# foundation, built to be extended, not a shallow pass at everything.
#
# These translations were written carefully, not machine-generated in
# bulk, but they have not been reviewed by a native speaker of each
# language. Worth a native-speaker pass before being treated as final,
# especially for anything safety-critical that gets added to this
# dictionary later.
SUPPORTED_LANGUAGES = {
    "en": "English", "fr": "Français", "es": "Español",
    "pt": "Português", "zh": "中文", "hi": "हिन्दी",
}

TRANSLATIONS = {
    "en": {
        "nav.Task Dashboard": "Task Dashboard", "nav.Help": "Help", "nav.Assets": "Assets",
        "nav.Permits": "Permits", "nav.Inventory": "Inventory",
        "nav.Incidents": "Incidents", "nav.Handover": "Handover",
        "nav.Contractors": "Contractors", "nav.Analytics": "Analytics",
        "nav.Chat": "Chat", "nav.Feedback": "Feedback", "nav.Admin": "Admin",
        "nav.Profile": "Profile", "nav.Timeline": "Timeline", "nav.About": "About",
        "nav.Production": "Production",
        "nav.Haulage": "Haulage",
        "nav.Wallboard": "Wallboard", "nav.Crew Clock": "Crew Clock",
        "nav.JSA Library": "JSA Library", "nav.Job Plans": "Job Plans", "nav.Locations": "Locations", "nav.Electrical Overview": "Electrical Overview", "nav.Motor Rewinds": "Motor Rewinds", "nav.Instrument Calibration": "Instrument Calibration", "nav.Outage Commander": "Outage Commander", "nav.Transformer Health": "Transformer Health", "nav.Fault Recorder": "Fault Recorder", "nav.HV Switching Schedule": "HV Switching Schedule", "nav.Relay Settings": "Relay Settings", "nav.Arc Flash Studies": "Arc Flash Studies", "nav.Technician Certifications": "Technician Certifications",
        'incidents.title': '🚨 Incident & Safety Reporting',
        'incidents.tab_all': 'All Incidents',
        'incidents.tab_report': 'Report Incident',
        'incidents.tab_my_reports': 'My Reports',
        'incidents.empty_title': 'No incidents reported yet',
        'incidents.empty_desc': "That's a good sign — this is where hazard and near-miss reports will appear.",
        'incidents.export_csv': '📥 Export Incidents as CSV',
        'incidents.download_csv': 'Download CSV',
        'incidents.search_placeholder': '🔍 Search by type, location, or description',
        'incidents.reported_by': 'Reported by {name}',
        'incidents.id_no': 'ID {no}',
        'incidents.paper_ref': 'Paper ref #{no}',
        'incidents.field_immediate_action': 'Immediate action',
        'incidents.field_reporter_suggestion': "Reporter's suggestion",
        'incidents.field_root_cause': 'Root cause',
        'incidents.field_corrective_action': 'Corrective action',
        'incidents.acknowledged_by': 'Acknowledged by {name} at {time}',
        'incidents.acknowledge_btn': '✋ Acknowledge receipt — #{id}',
        'incidents.acknowledged_success': "Acknowledged. You're now the owner of this report.",
        'incidents.update_failed': 'Update failed. If this keeps happening, Row Level Security may be blocking writes to the incidents table — see schema_additions.sql.',
        'incidents.investigate_expander': '⚙️ Investigate #{id}',
        'incidents.status_label': 'Status',
        'incidents.root_cause_label': 'Root Cause',
        'incidents.corrective_action_label': 'Corrective Action',
        'incidents.save_investigation': '💾 Save Investigation',
        'incidents.updated_success': 'Incident updated.',
        'incidents.submit_new_heading': 'Submit New Incident Report',
        'incidents.submit_caption': 'Report near-misses, injuries, and hazards as soon as possible. All Critical/High severity reports notify supervisors immediately.',
        'incidents.report_details_heading': 'Report details',
        'incidents.type_label': 'Type',
        'incidents.severity_label': 'Severity',
        'incidents.department_label': 'Department',
        'incidents.shift_label': 'Shift',
        'incidents.your_id_label': 'Your ID No.',
        'incidents.related_asset_label': 'Related Asset (optional)',
        'incidents.none_option': 'None',
        'incidents.witnesses_label': 'Witnesses (optional)',
        'incidents.paper_ref_label': 'Paper book ref. no. (optional)',
        'incidents.paper_ref_placeholder': 'e.g. 0000651',
        'incidents.paper_ref_help': 'If this was first written up in the paper hazard/near-miss book, record its number here so both copies can be cross-referenced.',
        'incidents.location_label': 'Location / Area *',
        'incidents.description_label': 'Description *',
        'incidents.description_placeholder': 'What happened? Be specific.',
        'incidents.immediate_action_label': 'Immediate Action Taken',
        'incidents.immediate_action_placeholder': 'What was done right away?',
        'incidents.suggestion_label': 'My suggestion / corrective action',
        'incidents.suggestion_placeholder': 'What do you think should be done to stop this happening again?',
        'incidents.suggestion_help': 'Your own suggestion at the time of reporting — separate from whatever the investigating supervisor decides later.',
        'incidents.confirm_checkbox': 'I confirm the details above are accurate to the best of my knowledge',
        'incidents.confirm_help': 'The digital equivalent of signing the paper report.',
        'incidents.submit_btn': '🚨 Submit Report',
        'incidents.err_required': 'Location and Description are required.',
        'incidents.err_confirm': 'Please confirm the details are accurate before submitting.',
        'incidents.success_reported': 'Incident reported. Thank you for keeping the site safe.',
        'incidents.warn_flagged': 'This has been flagged for immediate supervisor attention.',
        'incidents.err_submit_failed': 'Failed to submit report.',
        'permits.title': '🔐 Permit to Work / LOTO Register',
        'permits.caption': 'A permit must be issued, then accepted by the person doing the work, and signed back on completion. This register is the auditable record of that chain.',
        'permits.tab_active': 'Active Permits',
        'permits.tab_issue': 'Issue Permit',
        'permits.tab_history': 'Permit History',
        'permits.field_task': 'Task',
        'permits.field_lock_tags': 'Lock tags',
        'permits.field_isolation_points': 'Isolation points',
        'permits.field_hazards': 'Hazards',
        'permits.issued_by': 'Issued by {name}',
        'permits.accepted_by': 'Accepted by {name}',
        'permits.signed_back_by': 'Signed back by {name}',
        'permits.valid_until': 'Valid until {time}',
        'permits.step_issued': 'Issued',
        'permits.step_accepted': 'Accepted',
        'permits.step_signed_back': 'Signed Back',
        'permits.expired_badge': 'EXPIRED',
        'permits.accept_btn': '✍️ Accept Isolation',
        'permits.accept_success': 'Permit accepted. You are now the responsible person.',
        'permits.accept_failed': 'Accept failed — the permit was not updated. Check Row Level Security on the permits table before assuming isolation is in place.',
        'permits.signback_btn': '✅ Sign Back',
        'permits.signback_success': 'Permit signed back and closed.',
        'permits.signback_failed': 'Sign-back failed — the permit is still showing as Active.',
        'permits.cancel_btn': '🚫 Cancel',
        'permits.cancel_failed': 'Cancel failed — the permit was not updated.',
        'permits.empty_title': 'No open permits',
        'permits.empty_desc': 'Permit to Work / LOTO records will show here once one is issued.',
        'permits.expired_warning': '⚠️ {n} open permit(s) are past their validity window and must be reviewed or cancelled.',
        'permits.search_placeholder': '🔍 Search by permit type or lock tag',
        'permits.issue_new_heading': 'Issue New Permit',
        'permits.no_open_tasks': 'No open tasks to attach a permit to.',
        'permits.task_label': 'Task requiring the permit *',
        'permits.type_label': 'Permit Type',
        'permits.lock_tag_label': 'Lock / Tag Numbers *',
        'permits.lock_tag_placeholder': 'e.g. LT-1042, LT-1043',
        'permits.isolation_points_label': 'Isolation Points *',
        'permits.isolation_points_placeholder': 'List each energy source isolated',
        'permits.hazards_label': 'Hazards Identified *',
        'permits.hazards_placeholder': 'Stored energy, residual pressure, etc.',
        'permits.valid_hours_label': 'Valid for (hours)',
        'permits.confirm_checkbox': 'I confirm isolation has been physically verified at each point listed above.',
        'permits.issue_btn': '🔐 Issue Permit',
        'permits.err_required': 'Lock tags, isolation points, and hazards are all required.',
        'permits.err_confirm': 'You must confirm physical verification of isolation before a permit can be issued.',
        'permits.issue_success': 'Permit #{id} issued. It must now be accepted by the person performing the work.',
        'permits.issue_failed': 'Failed to issue permit.',
        'permits.no_closed': 'No closed permits yet.',
        'contractors.title': '👷 Contractor Management',
        'contractors.caption': 'Induction and insurance expiry are tracked because they commonly gate site access. Expired or missing records are flagged as blocking.',
        'contractors.tab_all': 'All Contractors',
        'contractors.tab_add': 'Add Contractor',
        'contractors.blocking_warning': '🚫 {n} contractor(s) have expired or missing compliance records and should not be granted site access.',
        'contractors.empty_title': 'No contractors registered yet',
        'contractors.empty_desc': 'Add a contractor to start tracking induction and insurance compliance.',
        'contractors.search_placeholder': '🔍 Search by company or contact name',
        'contractors.not_set': 'Not set',
        'contractors.field_induction_expires': 'Induction expires',
        'contractors.field_insurance_expires': 'Insurance expires',
        'contractors.field_competencies': 'Competencies',
        'contractors.update_expander': '⚙️ Update {name}',
        'contractors.induction_expiry_label': 'Induction expiry',
        'contractors.insurance_expiry_label': 'Insurance expiry',
        'contractors.save_btn': '💾 Save',
        'contractors.update_success': 'Contractor updated.',
        'contractors.save_failed': "Save failed — compliance dates were NOT updated. Check Row Level Security on the contractors table before assuming this contractor's status is current.",
        'contractors.company_name_label': 'Company Name *',
        'contractors.contact_person_label': 'Contact Person',
        'contractors.contact_email_label': 'Contact Email',
        'contractors.contact_phone_label': 'Contact Phone',
        'contractors.induction_date_label': 'Induction Date',
        'contractors.induction_expiry_cap_label': 'Induction Expiry',
        'contractors.insurance_expiry_cap_label': 'Insurance Expiry',
        'contractors.competencies_label': 'Competencies / Certifications',
        'contractors.competencies_placeholder': 'e.g. Confined space, EWP licence, HV switching',
        'contractors.notes_label': 'Notes',
        'contractors.add_btn': '➕ Add Contractor',
        'contractors.add_success': "Contractor '{name}' added.",
        'contractors.add_failed': 'Failed to add contractor.',
        'contractors.err_name_required': 'Company Name is required.',
        "nav.Owner Console": "Owner Console",
        "common.save": "Save", "common.cancel": "Cancel", "common.submit": "Submit",
        "common.delete": "Delete", "common.edit": "Edit", "common.search": "Search",
        "common.close": "Close", "common.back": "Back", "common.yes": "Yes",
        "common.no": "No", "common.welcome": "Welcome",
        "task.btn_post_comment": "Post Comment",
        "task.btn_upload_attachment": "Upload Attachment",
        "task.btn_upload": "Upload",
        "task.btn_export_csv": "📥 Export Tasks as CSV",
        "task.caption_full_breakdowns": "Full breakdowns, Pareto analysis, and cost reporting are in the **Analytics** section.",
        "task.caption_no_attachments": "No attachments.",
        "task.caption_no_broadcasts": "No broadcasts yet.",
        "task.caption_no_comments": "No comments yet.",
        "task.chk_recurring": "Recurring Task (Preventive Maintenance)",
        "task.chk_requires_jsa": "Requires JSA",
        "task.chk_requires_loto": "Requires LOTO",
        "task.chk_jsa_signed": "📋 JSA Signed",
        "task.share_link_label": "Share Link",
        "task.chk_loto_isolated": "🔒 LOTO Isolated",
        "task.err_cannot_move_progress": "Cannot move to In Progress without an accepted permit.",
        "task.err_delete_failed": "Delete failed. If this keeps happening, Row Level Security may be blocking writes to the tasks table.",
        "task.err_create_failed": "Failed to create task.",
        "task.err_comment_failed": "Failed to post comment.",
        "task.err_title_location_required": "Title and Location are required.",
        "task.err_upload_failed": "Upload failed.",
        "task.err_safety_forms_required": "🔒 Safety isolation forms are required before proceeding.",
        "task.err_permit_required": "🚫 **This task requires an accepted Permit to Work.** No live permit is recorded against it. Ask your supervisor to issue one, then accept it in the Permits section before starting work.",
        "task.info_no_active_users": "No active users yet.",
        "task.info_no_data": "No data to display.",
        "task.info_no_messages": "No messages sent yet.",
        "task.info_no_tasks_assigned": "No tasks assigned to you.",
        "task.info_no_tasks_found": "No tasks found.",
        "task.info_no_tasks_manage": "No tasks to manage.",
        "task.info_readonly_directory": "This is a read-only directory. Access approvals, role changes, and suspensions are handled by the account owner.",
        "task.info_owner_note": "You are the owner — approvals and role changes are in **Owner Console → Access Requests**.",
        "task.info_latest_broadcasts": "📢 Latest Broadcasts:",
        "task.hdr_all_broadcasts": "All Broadcast Messages",
        "task.hdr_all_tasks": "All Maintenance Tasks",
        "task.hdr_dispatch_new": "Dispatch New Work Ticket",
        "task.hdr_full_control": "Full Task Control",
        "task.hdr_recent_broadcasts": "Recent Broadcasts",
        "task.hdr_user_directory": "👥 User Directory",
        "task.hdr_task_analytics": "📊 Task Analytics",
        "task.hdr_active_users": "Active users",
        "task.hdr_suspended": "Suspended",
        "task.hdr_kpis": "🎯 Key Performance Indicators",
        "task.txt_closeout_details": "**Close-out details** — these feed the reliability and cost reports.",
        "task.txt_already_uploaded": "**📸 Already uploaded:**",
        "task.field_failure_code": "Failure code (for breakdown work)",
        "task.field_linked_asset": "Linked Asset (optional)",
        "task.field_priority": "Priority",
        "task.field_recurrence": "Recurrence Type",
        "task.field_update_status": "Update Status",
        "task.field_work_type": "Work Type",
        "task.success_attachment": "Attachment uploaded!",
        "task.success_photo": "Photo uploaded!",
        "task.success_safety_checks": "✅ Safety checks passed.",
        "task.success_no_unassigned": "🎉 No unassigned tasks at the moment.",
        "task.field_add_comment": "Add comment",
        "task.field_location": "Location / Area *",
        "task.field_task_title": "Task Title *",
        "task.warn_plotly": "Plotly or pandas not installed. Please run: pip install plotly pandas",
    },
    "fr": {
        "nav.Task Dashboard": "Tableau des tâches", "nav.Help": "Aide", "nav.Assets": "Actifs",
        "nav.Permits": "Permis", "nav.Inventory": "Inventaire",
        "nav.Incidents": "Incidents", "nav.Handover": "Passation de service",
        "nav.Contractors": "Sous-traitants", "nav.Analytics": "Analytique",
        "nav.Chat": "Discussion", "nav.Feedback": "Retours", "nav.Admin": "Administration",
        "nav.Profile": "Profil", "nav.Timeline": "Chronologie", "nav.About": "À propos",
        "nav.Production": "Production",
        "nav.Haulage": "Transport",
        "nav.Wallboard": "Tableau mural", "nav.Crew Clock": "Pointeuse",
        "nav.JSA Library": "Bibliothèque JSA", "nav.Job Plans": "Plans de travail", "nav.Locations": "Emplacements", "nav.Electrical Overview": "Aperçu électrique", "nav.Motor Rewinds": "Rebobinages de moteurs", "nav.Instrument Calibration": "Étalonnage des instruments", "nav.Outage Commander": "Commandant de panne", "nav.Transformer Health": "Santé du transformateur", "nav.Fault Recorder": "Enregistreur de défauts", "nav.HV Switching Schedule": "Programme de manœuvres HT", "nav.Relay Settings": "Réglages des relais", "nav.Arc Flash Studies": "Études d'arc électrique", "nav.Technician Certifications": "Certifications des techniciens",
        'incidents.title': "🚨 Signalement d'incidents et sécurité",
        'incidents.tab_all': 'Tous les incidents',
        'incidents.tab_report': 'Signaler un incident',
        'incidents.tab_my_reports': 'Mes signalements',
        'incidents.empty_title': 'Aucun incident signalé pour le moment',
        'incidents.empty_desc': "C'est bon signe — les dangers et quasi-accidents apparaîtront ici.",
        'incidents.export_csv': '📥 Exporter les incidents en CSV',
        'incidents.download_csv': 'Télécharger le CSV',
        'incidents.search_placeholder': '🔍 Rechercher par type, lieu ou description',
        'incidents.reported_by': 'Signalé par {name}',
        'incidents.id_no': 'ID {no}',
        'incidents.paper_ref': 'Réf. papier n° {no}',
        'incidents.field_immediate_action': 'Action immédiate',
        'incidents.field_reporter_suggestion': 'Suggestion du déclarant',
        'incidents.field_root_cause': 'Cause première',
        'incidents.field_corrective_action': 'Action corrective',
        'incidents.acknowledged_by': 'Pris en compte par {name} à {time}',
        'incidents.acknowledge_btn': '✋ Accuser réception — n° {id}',
        'incidents.acknowledged_success': 'Accusé de réception effectué. Vous êtes désormais responsable de ce rapport.',
        'incidents.update_failed': 'Échec de la mise à jour. Si cela persiste, la sécurité au niveau des lignes (RLS) bloque peut-être les écritures — voir schema_additions.sql.',
        'incidents.investigate_expander': '⚙️ Enquêter — n° {id}',
        'incidents.status_label': 'Statut',
        'incidents.root_cause_label': 'Cause première',
        'incidents.corrective_action_label': 'Action corrective',
        'incidents.save_investigation': "💾 Enregistrer l'enquête",
        'incidents.updated_success': 'Incident mis à jour.',
        'incidents.submit_new_heading': "Soumettre un nouveau rapport d'incident",
        'incidents.submit_caption': 'Signalez les quasi-accidents, blessures et dangers dès que possible. Les rapports de gravité critique/élevée alertent immédiatement les superviseurs.',
        'incidents.report_details_heading': 'Détails du rapport',
        'incidents.type_label': 'Type',
        'incidents.severity_label': 'Gravité',
        'incidents.department_label': 'Département',
        'incidents.shift_label': 'Quart',
        'incidents.your_id_label': "Votre n° d'identification",
        'incidents.related_asset_label': 'Équipement concerné (facultatif)',
        'incidents.none_option': 'Aucun',
        'incidents.witnesses_label': 'Témoins (facultatif)',
        'incidents.paper_ref_label': 'N° de réf. du registre papier (facultatif)',
        'incidents.paper_ref_placeholder': 'ex. 0000651',
        'incidents.paper_ref_help': "Si cela a d'abord été consigné dans le registre papier des dangers/quasi-accidents, notez son numéro ici afin que les deux copies puissent être recoupées.",
        'incidents.location_label': 'Lieu / Zone *',
        'incidents.description_label': 'Description *',
        'incidents.description_placeholder': "Que s'est-il passé ? Soyez précis.",
        'incidents.immediate_action_label': 'Action immédiate entreprise',
        'incidents.immediate_action_placeholder': "Qu'a-t-on fait immédiatement ?",
        'incidents.suggestion_label': 'Ma suggestion / action corrective',
        'incidents.suggestion_placeholder': "Que pensez-vous qu'il faille faire pour éviter que cela se reproduise ?",
        'incidents.suggestion_help': "Votre propre suggestion au moment du signalement — distincte de ce que décidera ensuite le superviseur chargé de l'enquête.",
        'incidents.confirm_checkbox': 'Je confirme que les détails ci-dessus sont exacts au mieux de ma connaissance',
        'incidents.confirm_help': "L'équivalent numérique de la signature du rapport papier.",
        'incidents.submit_btn': '🚨 Soumettre le rapport',
        'incidents.err_required': 'Le lieu et la description sont obligatoires.',
        'incidents.err_confirm': "Veuillez confirmer l'exactitude des détails avant de soumettre.",
        'incidents.success_reported': 'Incident signalé. Merci de contribuer à la sécurité du site.',
        'incidents.warn_flagged': "Ceci a été signalé pour l'attention immédiate d'un superviseur.",
        'incidents.err_submit_failed': 'Échec de la soumission du rapport.',
        'permits.title': '🔐 Registre des permis de travail / LOTO',
        'permits.caption': "Un permis doit être émis, puis accepté par la personne effectuant le travail, et signé à la clôture. Ce registre constitue l'enregistrement vérifiable de cette chaîne.",
        'permits.tab_active': 'Permis actifs',
        'permits.tab_issue': 'Émettre un permis',
        'permits.tab_history': 'Historique des permis',
        'permits.field_task': 'Tâche',
        'permits.field_lock_tags': 'Cadenas / étiquettes',
        'permits.field_isolation_points': "Points d'isolation",
        'permits.field_hazards': 'Dangers',
        'permits.issued_by': 'Émis par {name}',
        'permits.accepted_by': 'Accepté par {name}',
        'permits.signed_back_by': 'Clôturé par {name}',
        'permits.valid_until': "Valide jusqu'à {time}",
        'permits.step_issued': 'Émis',
        'permits.step_accepted': 'Accepté',
        'permits.step_signed_back': 'Clôturé',
        'permits.expired_badge': 'EXPIRÉ',
        'permits.accept_btn': "✍️ Accepter l'isolation",
        'permits.accept_success': 'Permis accepté. Vous êtes désormais la personne responsable.',
        'permits.accept_failed': "Échec de l'acceptation — le permis n'a pas été mis à jour. Vérifiez la sécurité au niveau des lignes (RLS) avant de considérer l'isolation comme en place.",
        'permits.signback_btn': '✅ Clôturer',
        'permits.signback_success': 'Permis clôturé et fermé.',
        'permits.signback_failed': 'Échec de la clôture — le permis apparaît toujours comme actif.',
        'permits.cancel_btn': '🚫 Annuler',
        'permits.cancel_failed': "Échec de l'annulation — le permis n'a pas été mis à jour.",
        'permits.empty_title': 'Aucun permis ouvert',
        'permits.empty_desc': 'Les permis de travail / LOTO apparaîtront ici une fois émis.',
        'permits.expired_warning': '⚠️ {n} permis ouvert(s) ont dépassé leur période de validité et doivent être examinés ou annulés.',
        'permits.search_placeholder': '🔍 Rechercher par type de permis ou étiquette',
        'permits.issue_new_heading': 'Émettre un nouveau permis',
        'permits.no_open_tasks': 'Aucune tâche ouverte à laquelle rattacher un permis.',
        'permits.task_label': 'Tâche nécessitant le permis *',
        'permits.type_label': 'Type de permis',
        'permits.lock_tag_label': 'Numéros de cadenas / étiquettes *',
        'permits.lock_tag_placeholder': 'ex. LT-1042, LT-1043',
        'permits.isolation_points_label': "Points d'isolation *",
        'permits.isolation_points_placeholder': "Listez chaque source d'énergie isolée",
        'permits.hazards_label': 'Dangers identifiés *',
        'permits.hazards_placeholder': 'Énergie emmagasinée, pression résiduelle, etc.',
        'permits.valid_hours_label': 'Valide pendant (heures)',
        'permits.confirm_checkbox': "Je confirme que l'isolation a été physiquement vérifiée à chaque point listé ci-dessus.",
        'permits.issue_btn': '🔐 Émettre le permis',
        'permits.err_required': "Les cadenas/étiquettes, points d'isolation et dangers sont tous obligatoires.",
        'permits.err_confirm': "Vous devez confirmer la vérification physique de l'isolation avant qu'un permis puisse être émis.",
        'permits.issue_success': 'Permis n° {id} émis. Il doit maintenant être accepté par la personne effectuant le travail.',
        'permits.issue_failed': "Échec de l'émission du permis.",
        'permits.no_closed': 'Aucun permis clôturé pour le moment.',
        'contractors.title': '👷 Gestion des sous-traitants',
        'contractors.caption': "L'expiration de l'induction et de l'assurance est suivie car elles conditionnent généralement l'accès au site. Les dossiers expirés ou manquants sont signalés comme bloquants.",
        'contractors.tab_all': 'Tous les sous-traitants',
        'contractors.tab_add': 'Ajouter un sous-traitant',
        'contractors.blocking_warning': "🚫 {n} sous-traitant(s) ont des dossiers de conformité expirés ou manquants et ne devraient pas se voir accorder l'accès au site.",
        'contractors.empty_title': 'Aucun sous-traitant enregistré pour le moment',
        'contractors.empty_desc': "Ajoutez un sous-traitant pour commencer à suivre la conformité de l'induction et de l'assurance.",
        'contractors.search_placeholder': '🔍 Rechercher par entreprise ou nom de contact',
        'contractors.not_set': 'Non défini',
        'contractors.field_induction_expires': 'Induction expire',
        'contractors.field_insurance_expires': 'Assurance expire',
        'contractors.field_competencies': 'Compétences',
        'contractors.update_expander': '⚙️ Mettre à jour {name}',
        'contractors.induction_expiry_label': "Expiration de l'induction",
        'contractors.insurance_expiry_label': "Expiration de l'assurance",
        'contractors.save_btn': '💾 Enregistrer',
        'contractors.update_success': 'Sous-traitant mis à jour.',
        'contractors.save_failed': "Échec de l'enregistrement — les dates de conformité n'ont PAS été mises à jour. Vérifiez la sécurité au niveau des lignes (RLS) sur la table des sous-traitants avant de considérer son statut comme à jour.",
        'contractors.company_name_label': "Nom de l'entreprise *",
        'contractors.contact_person_label': 'Personne de contact',
        'contractors.contact_email_label': 'E-mail de contact',
        'contractors.contact_phone_label': 'Téléphone de contact',
        'contractors.induction_date_label': "Date d'induction",
        'contractors.induction_expiry_cap_label': "Expiration de l'induction",
        'contractors.insurance_expiry_cap_label': "Expiration de l'assurance",
        'contractors.competencies_label': 'Compétences / Certifications',
        'contractors.competencies_placeholder': 'ex. Espace confiné, permis PEMP, manœuvre HT',
        'contractors.notes_label': 'Notes',
        'contractors.add_btn': '➕ Ajouter un sous-traitant',
        'contractors.add_success': 'Sous-traitant « {name} » ajouté.',
        'contractors.add_failed': "Échec de l'ajout du sous-traitant.",
        'contractors.err_name_required': "Le nom de l'entreprise est obligatoire.",
        "nav.Owner Console": "Console propriétaire",
        "common.save": "Enregistrer", "common.cancel": "Annuler", "common.submit": "Soumettre",
        "common.delete": "Supprimer", "common.edit": "Modifier", "common.search": "Rechercher",
        "common.close": "Fermer", "common.back": "Retour", "common.yes": "Oui",
        "common.no": "Non", "common.welcome": "Bienvenue",
        "task.btn_post_comment": "Publier le commentaire",
        "task.btn_upload_attachment": "Téléverser une pièce jointe",
        "task.btn_upload": "Téléverser",
        "task.btn_export_csv": "📥 Exporter les tâches en CSV",
        "task.caption_full_breakdowns": "Les analyses complètes, l'analyse de Pareto et les rapports de coûts se trouvent dans la section **Analytique**.",
        "task.caption_no_attachments": "Aucune pièce jointe.",
        "task.caption_no_broadcasts": "Aucune diffusion pour le moment.",
        "task.caption_no_comments": "Aucun commentaire pour le moment.",
        "task.chk_recurring": "Tâche récurrente (maintenance préventive)",
        "task.chk_requires_jsa": "Nécessite une AST",
        "task.chk_requires_loto": "Nécessite une consignation LOTO",
        "task.chk_jsa_signed": "📋 AST signée",
        "task.share_link_label": "Lien de partage",
        "task.chk_loto_isolated": "🔒 Consignation LOTO effectuée",
        "task.err_cannot_move_progress": "Impossible de passer à « En cours » sans permis accepté.",
        "task.err_delete_failed": "Échec de la suppression. Si cela persiste, la sécurité au niveau des lignes (RLS) bloque peut-être les écritures sur la table des tâches.",
        "task.err_create_failed": "Échec de la création de la tâche.",
        "task.err_comment_failed": "Échec de la publication du commentaire.",
        "task.err_title_location_required": "Le titre et le lieu sont requis.",
        "task.err_upload_failed": "Échec du téléversement.",
        "task.err_safety_forms_required": "🔒 Les formulaires de consignation de sécurité sont requis avant de continuer.",
        "task.err_permit_required": "🚫 **Cette tâche nécessite un permis de travail accepté.** Aucun permis actif n'est enregistré. Demandez à votre superviseur d'en émettre un, puis acceptez-le dans la section Permis avant de commencer le travail.",
        "task.info_no_active_users": "Aucun utilisateur actif pour le moment.",
        "task.info_no_data": "Aucune donnée à afficher.",
        "task.info_no_messages": "Aucun message envoyé pour le moment.",
        "task.info_no_tasks_assigned": "Aucune tâche ne vous est assignée.",
        "task.info_no_tasks_found": "Aucune tâche trouvée.",
        "task.info_no_tasks_manage": "Aucune tâche à gérer.",
        "task.info_readonly_directory": "Ceci est un répertoire en lecture seule. Les approbations d'accès, les changements de rôle et les suspensions sont gérés par le propriétaire du compte.",
        "task.info_owner_note": "Vous êtes le propriétaire — les approbations et les changements de rôle se trouvent dans **Console propriétaire → Demandes d'accès**.",
        "task.info_latest_broadcasts": "📢 Dernières diffusions :",
        "task.hdr_all_broadcasts": "Tous les messages diffusés",
        "task.hdr_all_tasks": "Toutes les tâches de maintenance",
        "task.hdr_dispatch_new": "Créer un nouveau bon de travail",
        "task.hdr_full_control": "Contrôle complet des tâches",
        "task.hdr_recent_broadcasts": "Diffusions récentes",
        "task.hdr_user_directory": "👥 Répertoire des utilisateurs",
        "task.hdr_task_analytics": "📊 Analytique des tâches",
        "task.hdr_active_users": "Utilisateurs actifs",
        "task.hdr_suspended": "Suspendu",
        "task.hdr_kpis": "🎯 Indicateurs clés de performance",
        "task.txt_closeout_details": "**Détails de clôture** — ces informations alimentent les rapports de fiabilité et de coûts.",
        "task.txt_already_uploaded": "**📸 Déjà téléversé :**",
        "task.field_failure_code": "Code de défaillance (pour panne)",
        "task.field_linked_asset": "Actif lié (facultatif)",
        "task.field_priority": "Priorité",
        "task.field_recurrence": "Type de récurrence",
        "task.field_update_status": "Mettre à jour le statut",
        "task.field_work_type": "Type de travail",
        "task.success_attachment": "Pièce jointe téléversée !",
        "task.success_photo": "Photo téléversée !",
        "task.success_safety_checks": "✅ Vérifications de sécurité réussies.",
        "task.success_no_unassigned": "🎉 Aucune tâche non assignée pour le moment.",
        "task.field_add_comment": "Ajouter un commentaire",
        "task.field_location": "Emplacement / Zone *",
        "task.field_task_title": "Titre de la tâche *",
        "task.warn_plotly": "Plotly ou pandas non installés. Veuillez exécuter : pip install plotly pandas",
    },
    "es": {
        "nav.Task Dashboard": "Panel de tareas", "nav.Help": "Ayuda", "nav.Assets": "Activos",
        "nav.Permits": "Permisos", "nav.Inventory": "Inventario",
        "nav.Incidents": "Incidentes", "nav.Handover": "Entrega de turno",
        "nav.Contractors": "Contratistas", "nav.Analytics": "Analítica",
        "nav.Chat": "Chat", "nav.Feedback": "Comentarios", "nav.Admin": "Administración",
        "nav.Profile": "Perfil", "nav.Timeline": "Cronología", "nav.About": "Acerca de",
        "nav.Production": "Producción",
        "nav.Haulage": "Transporte",
        "nav.Wallboard": "Tablero", "nav.Crew Clock": "Reloj de turno",
        "nav.JSA Library": "Biblioteca JSA", "nav.Job Plans": "Planes de trabajo", "nav.Locations": "Ubicaciones", "nav.Electrical Overview": "Resumen eléctrico", "nav.Motor Rewinds": "Rebobinados de motores", "nav.Instrument Calibration": "Calibración de instrumentos", "nav.Outage Commander": "Comandante de apagón", "nav.Transformer Health": "Salud del transformador", "nav.Fault Recorder": "Registrador de fallas", "nav.HV Switching Schedule": "Programa de maniobras AT", "nav.Relay Settings": "Ajustes de relés", "nav.Arc Flash Studies": "Estudios de arco eléctrico", "nav.Technician Certifications": "Certificaciones de técnicos",
        'incidents.title': '🚨 Reporte de incidentes y seguridad',
        'incidents.tab_all': 'Todos los incidentes',
        'incidents.tab_report': 'Reportar incidente',
        'incidents.tab_my_reports': 'Mis reportes',
        'incidents.empty_title': 'Aún no se han reportado incidentes',
        'incidents.empty_desc': 'Buena señal — aquí aparecerán los peligros y cuasi accidentes.',
        'incidents.export_csv': '📥 Exportar incidentes como CSV',
        'incidents.download_csv': 'Descargar CSV',
        'incidents.search_placeholder': '🔍 Buscar por tipo, ubicación o descripción',
        'incidents.reported_by': 'Reportado por {name}',
        'incidents.id_no': 'ID {no}',
        'incidents.paper_ref': 'Ref. papel n.º {no}',
        'incidents.field_immediate_action': 'Acción inmediata',
        'incidents.field_reporter_suggestion': 'Sugerencia del reportante',
        'incidents.field_root_cause': 'Causa raíz',
        'incidents.field_corrective_action': 'Acción correctiva',
        'incidents.acknowledged_by': 'Reconocido por {name} a las {time}',
        'incidents.acknowledge_btn': '✋ Acusar recibo — n.º {id}',
        'incidents.acknowledged_success': 'Recibo confirmado. Ahora eres responsable de este reporte.',
        'incidents.update_failed': 'Error al actualizar. Si esto persiste, la seguridad a nivel de fila (RLS) podría estar bloqueando las escrituras — ver schema_additions.sql.',
        'incidents.investigate_expander': '⚙️ Investigar — n.º {id}',
        'incidents.status_label': 'Estado',
        'incidents.root_cause_label': 'Causa raíz',
        'incidents.corrective_action_label': 'Acción correctiva',
        'incidents.save_investigation': '💾 Guardar investigación',
        'incidents.updated_success': 'Incidente actualizado.',
        'incidents.submit_new_heading': 'Enviar nuevo reporte de incidente',
        'incidents.submit_caption': 'Reporte cuasi accidentes, lesiones y peligros lo antes posible. Los reportes de gravedad crítica/alta notifican de inmediato a los supervisores.',
        'incidents.report_details_heading': 'Detalles del reporte',
        'incidents.type_label': 'Tipo',
        'incidents.severity_label': 'Gravedad',
        'incidents.department_label': 'Departamento',
        'incidents.shift_label': 'Turno',
        'incidents.your_id_label': 'Su n.º de identificación',
        'incidents.related_asset_label': 'Activo relacionado (opcional)',
        'incidents.none_option': 'Ninguno',
        'incidents.witnesses_label': 'Testigos (opcional)',
        'incidents.paper_ref_label': 'N.º de ref. del libro en papel (opcional)',
        'incidents.paper_ref_placeholder': 'ej. 0000651',
        'incidents.paper_ref_help': 'Si esto se registró primero en el libro de papel de peligros/cuasi accidentes, anote aquí su número para poder cruzar ambas copias.',
        'incidents.location_label': 'Ubicación / Área *',
        'incidents.description_label': 'Descripción *',
        'incidents.description_placeholder': '¿Qué sucedió? Sea específico.',
        'incidents.immediate_action_label': 'Acción inmediata tomada',
        'incidents.immediate_action_placeholder': '¿Qué se hizo de inmediato?',
        'incidents.suggestion_label': 'Mi sugerencia / acción correctiva',
        'incidents.suggestion_placeholder': '¿Qué cree que se debería hacer para evitar que esto vuelva a ocurrir?',
        'incidents.suggestion_help': 'Su propia sugerencia al momento de reportar — independiente de lo que decida después el supervisor a cargo de la investigación.',
        'incidents.confirm_checkbox': 'Confirmo que los detalles anteriores son precisos según mi mejor conocimiento',
        'incidents.confirm_help': 'El equivalente digital de firmar el reporte en papel.',
        'incidents.submit_btn': '🚨 Enviar reporte',
        'incidents.err_required': 'La ubicación y la descripción son obligatorias.',
        'incidents.err_confirm': 'Confirme que los detalles son precisos antes de enviar.',
        'incidents.success_reported': 'Incidente reportado. Gracias por ayudar a mantener el sitio seguro.',
        'incidents.warn_flagged': 'Esto ha sido marcado para atención inmediata del supervisor.',
        'incidents.err_submit_failed': 'Error al enviar el reporte.',
        'permits.title': '🔐 Registro de permisos de trabajo / LOTO',
        'permits.caption': 'Un permiso debe emitirse, luego ser aceptado por quien realiza el trabajo, y firmado al finalizar. Este registro es el rastro auditable de esa cadena.',
        'permits.tab_active': 'Permisos activos',
        'permits.tab_issue': 'Emitir permiso',
        'permits.tab_history': 'Historial de permisos',
        'permits.field_task': 'Tarea',
        'permits.field_lock_tags': 'Candados / etiquetas',
        'permits.field_isolation_points': 'Puntos de aislamiento',
        'permits.field_hazards': 'Peligros',
        'permits.issued_by': 'Emitido por {name}',
        'permits.accepted_by': 'Aceptado por {name}',
        'permits.signed_back_by': 'Cerrado por {name}',
        'permits.valid_until': 'Válido hasta {time}',
        'permits.step_issued': 'Emitido',
        'permits.step_accepted': 'Aceptado',
        'permits.step_signed_back': 'Cerrado',
        'permits.expired_badge': 'VENCIDO',
        'permits.accept_btn': '✍️ Aceptar aislamiento',
        'permits.accept_success': 'Permiso aceptado. Ahora usted es la persona responsable.',
        'permits.accept_failed': 'Error al aceptar — el permiso no se actualizó. Verifique la seguridad a nivel de fila (RLS) antes de asumir que el aislamiento está en su lugar.',
        'permits.signback_btn': '✅ Firmar cierre',
        'permits.signback_success': 'Permiso cerrado y finalizado.',
        'permits.signback_failed': 'Error al cerrar — el permiso aún aparece como activo.',
        'permits.cancel_btn': '🚫 Cancelar',
        'permits.cancel_failed': 'Error al cancelar — el permiso no se actualizó.',
        'permits.empty_title': 'No hay permisos abiertos',
        'permits.empty_desc': 'Los registros de permiso de trabajo / LOTO aparecerán aquí una vez emitidos.',
        'permits.expired_warning': '⚠️ {n} permiso(s) abierto(s) han superado su período de validez y deben revisarse o cancelarse.',
        'permits.search_placeholder': '🔍 Buscar por tipo de permiso o etiqueta',
        'permits.issue_new_heading': 'Emitir nuevo permiso',
        'permits.no_open_tasks': 'No hay tareas abiertas a las cuales asociar un permiso.',
        'permits.task_label': 'Tarea que requiere el permiso *',
        'permits.type_label': 'Tipo de permiso',
        'permits.lock_tag_label': 'Números de candado / etiqueta *',
        'permits.lock_tag_placeholder': 'ej. LT-1042, LT-1043',
        'permits.isolation_points_label': 'Puntos de aislamiento *',
        'permits.isolation_points_placeholder': 'Enumere cada fuente de energía aislada',
        'permits.hazards_label': 'Peligros identificados *',
        'permits.hazards_placeholder': 'Energía almacenada, presión residual, etc.',
        'permits.valid_hours_label': 'Válido por (horas)',
        'permits.confirm_checkbox': 'Confirmo que el aislamiento ha sido verificado físicamente en cada punto indicado arriba.',
        'permits.issue_btn': '🔐 Emitir permiso',
        'permits.err_required': 'Los candados/etiquetas, puntos de aislamiento y peligros son obligatorios.',
        'permits.err_confirm': 'Debe confirmar la verificación física del aislamiento antes de poder emitir un permiso.',
        'permits.issue_success': 'Permiso #{id} emitido. Ahora debe ser aceptado por la persona que realiza el trabajo.',
        'permits.issue_failed': 'Error al emitir el permiso.',
        'permits.no_closed': 'Aún no hay permisos cerrados.',
        'contractors.title': '👷 Gestión de contratistas',
        'contractors.caption': 'El vencimiento de inducción y seguro se rastrea porque comúnmente condicionan el acceso al sitio. Los registros vencidos o faltantes se marcan como bloqueantes.',
        'contractors.tab_all': 'Todos los contratistas',
        'contractors.tab_add': 'Agregar contratista',
        'contractors.blocking_warning': '🚫 {n} contratista(s) tienen registros de cumplimiento vencidos o faltantes y no deberían recibir acceso al sitio.',
        'contractors.empty_title': 'Aún no hay contratistas registrados',
        'contractors.empty_desc': 'Agregue un contratista para comenzar a rastrear el cumplimiento de inducción y seguro.',
        'contractors.search_placeholder': '🔍 Buscar por empresa o nombre de contacto',
        'contractors.not_set': 'No establecido',
        'contractors.field_induction_expires': 'Vence inducción',
        'contractors.field_insurance_expires': 'Vence seguro',
        'contractors.field_competencies': 'Competencias',
        'contractors.update_expander': '⚙️ Actualizar {name}',
        'contractors.induction_expiry_label': 'Vencimiento de inducción',
        'contractors.insurance_expiry_label': 'Vencimiento de seguro',
        'contractors.save_btn': '💾 Guardar',
        'contractors.update_success': 'Contratista actualizado.',
        'contractors.save_failed': 'Error al guardar — las fechas de cumplimiento NO se actualizaron. Verifique la seguridad a nivel de fila (RLS) en la tabla de contratistas antes de asumir que su estado está al día.',
        'contractors.company_name_label': 'Nombre de la empresa *',
        'contractors.contact_person_label': 'Persona de contacto',
        'contractors.contact_email_label': 'Correo de contacto',
        'contractors.contact_phone_label': 'Teléfono de contacto',
        'contractors.induction_date_label': 'Fecha de inducción',
        'contractors.induction_expiry_cap_label': 'Vencimiento de inducción',
        'contractors.insurance_expiry_cap_label': 'Vencimiento de seguro',
        'contractors.competencies_label': 'Competencias / Certificaciones',
        'contractors.competencies_placeholder': 'ej. Espacio confinado, licencia PEMP, maniobra de alta tensión',
        'contractors.notes_label': 'Notas',
        'contractors.add_btn': '➕ Agregar contratista',
        'contractors.add_success': "Contratista '{name}' agregado.",
        'contractors.add_failed': 'Error al agregar el contratista.',
        'contractors.err_name_required': 'El nombre de la empresa es obligatorio.',
        "nav.Owner Console": "Consola del propietario",
        "common.save": "Guardar", "common.cancel": "Cancelar", "common.submit": "Enviar",
        "common.delete": "Eliminar", "common.edit": "Editar", "common.search": "Buscar",
        "common.close": "Cerrar", "common.back": "Atrás", "common.yes": "Sí",
        "common.no": "No", "common.welcome": "Bienvenido",
        "task.btn_post_comment": "Publicar comentario",
        "task.btn_upload_attachment": "Subir archivo adjunto",
        "task.btn_upload": "Subir",
        "task.btn_export_csv": "📥 Exportar tareas como CSV",
        "task.caption_full_breakdowns": "Los desgloses completos, el análisis de Pareto y los informes de costos están en la sección **Analítica**.",
        "task.caption_no_attachments": "Sin archivos adjuntos.",
        "task.caption_no_broadcasts": "Aún no hay difusiones.",
        "task.caption_no_comments": "Aún no hay comentarios.",
        "task.chk_recurring": "Tarea recurrente (mantenimiento preventivo)",
        "task.chk_requires_jsa": "Requiere AST",
        "task.chk_requires_loto": "Requiere bloqueo LOTO",
        "task.chk_jsa_signed": "📋 AST firmado",
        "task.share_link_label": "Enlace para compartir",
        "task.chk_loto_isolated": "🔒 Bloqueo LOTO realizado",
        "task.err_cannot_move_progress": "No se puede pasar a «En curso» sin un permiso aceptado.",
        "task.err_delete_failed": "Error al eliminar. Si esto continúa, la seguridad a nivel de fila (RLS) podría estar bloqueando las escrituras en la tabla de tareas.",
        "task.err_create_failed": "Error al crear la tarea.",
        "task.err_comment_failed": "Error al publicar el comentario.",
        "task.err_title_location_required": "Se requieren el título y la ubicación.",
        "task.err_upload_failed": "Error al subir el archivo.",
        "task.err_safety_forms_required": "🔒 Se requieren los formularios de bloqueo de seguridad antes de continuar.",
        "task.err_permit_required": "🚫 **Esta tarea requiere un permiso de trabajo aceptado.** No hay ningún permiso activo registrado. Pida a su supervisor que emita uno y luego acéptelo en la sección Permisos antes de comenzar el trabajo.",
        "task.info_no_active_users": "Aún no hay usuarios activos.",
        "task.info_no_data": "No hay datos para mostrar.",
        "task.info_no_messages": "Aún no se han enviado mensajes.",
        "task.info_no_tasks_assigned": "No tiene tareas asignadas.",
        "task.info_no_tasks_found": "No se encontraron tareas.",
        "task.info_no_tasks_manage": "No hay tareas que gestionar.",
        "task.info_readonly_directory": "Este es un directorio de solo lectura. Las aprobaciones de acceso, los cambios de rol y las suspensiones las gestiona el propietario de la cuenta.",
        "task.info_owner_note": "Usted es el propietario — las aprobaciones y los cambios de rol están en **Consola del propietario → Solicitudes de acceso**.",
        "task.info_latest_broadcasts": "📢 Últimas difusiones:",
        "task.hdr_all_broadcasts": "Todos los mensajes difundidos",
        "task.hdr_all_tasks": "Todas las tareas de mantenimiento",
        "task.hdr_dispatch_new": "Crear nueva orden de trabajo",
        "task.hdr_full_control": "Control total de tareas",
        "task.hdr_recent_broadcasts": "Difusiones recientes",
        "task.hdr_user_directory": "👥 Directorio de usuarios",
        "task.hdr_task_analytics": "📊 Analítica de tareas",
        "task.hdr_active_users": "Usuarios activos",
        "task.hdr_suspended": "Suspendido",
        "task.hdr_kpis": "🎯 Indicadores clave de rendimiento",
        "task.txt_closeout_details": "**Detalles de cierre** — esta información alimenta los informes de fiabilidad y costos.",
        "task.txt_already_uploaded": "**📸 Ya subido:**",
        "task.field_failure_code": "Código de falla (para averías)",
        "task.field_linked_asset": "Activo vinculado (opcional)",
        "task.field_priority": "Prioridad",
        "task.field_recurrence": "Tipo de recurrencia",
        "task.field_update_status": "Actualizar estado",
        "task.field_work_type": "Tipo de trabajo",
        "task.success_attachment": "¡Archivo adjunto subido!",
        "task.success_photo": "¡Foto subida!",
        "task.success_safety_checks": "✅ Verificaciones de seguridad superadas.",
        "task.success_no_unassigned": "🎉 No hay tareas sin asignar por el momento.",
        "task.field_add_comment": "Agregar comentario",
        "task.field_location": "Ubicación / Área *",
        "task.field_task_title": "Título de la tarea *",
        "task.warn_plotly": "Plotly o pandas no están instalados. Ejecute: pip install plotly pandas",
    },
    "pt": {
        "nav.Task Dashboard": "Painel de tarefas", "nav.Help": "Ajuda", "nav.Assets": "Ativos",
        "nav.Permits": "Permissões", "nav.Inventory": "Inventário",
        "nav.Incidents": "Incidentes", "nav.Handover": "Passagem de turno",
        "nav.Contractors": "Empreiteiros", "nav.Analytics": "Análises",
        "nav.Chat": "Chat", "nav.Feedback": "Feedback", "nav.Admin": "Administração",
        "nav.Profile": "Perfil", "nav.Timeline": "Linha do tempo", "nav.About": "Sobre",
        "nav.Production": "Produção",
        "nav.Haulage": "Transporte",
        "nav.Wallboard": "Painel", "nav.Crew Clock": "Relógio de Turno",
        "nav.JSA Library": "Biblioteca JSA", "nav.Job Plans": "Planos de Trabalho", "nav.Locations": "Localizações", "nav.Electrical Overview": "Visão Geral Elétrica", "nav.Motor Rewinds": "Rebobinagens de Motores", "nav.Instrument Calibration": "Calibração de Instrumentos", "nav.Outage Commander": "Comandante de Interrupção", "nav.Transformer Health": "Saúde do Transformador", "nav.Fault Recorder": "Registrador de Falhas", "nav.HV Switching Schedule": "Programa de Manobras AT", "nav.Relay Settings": "Ajustes de Relés", "nav.Arc Flash Studies": "Estudos de Arco Elétrico", "nav.Technician Certifications": "Certificações de Técnicos",
        'incidents.title': '🚨 Relato de incidentes e segurança',
        'incidents.tab_all': 'Todos os incidentes',
        'incidents.tab_report': 'Relatar incidente',
        'incidents.tab_my_reports': 'Meus relatos',
        'incidents.empty_title': 'Nenhum incidente relatado ainda',
        'incidents.empty_desc': 'Bom sinal — os riscos e quase acidentes aparecerão aqui.',
        'incidents.export_csv': '📥 Exportar incidentes como CSV',
        'incidents.download_csv': 'Baixar CSV',
        'incidents.search_placeholder': '🔍 Buscar por tipo, local ou descrição',
        'incidents.reported_by': 'Relatado por {name}',
        'incidents.id_no': 'ID {no}',
        'incidents.paper_ref': 'Ref. papel n.º {no}',
        'incidents.field_immediate_action': 'Ação imediata',
        'incidents.field_reporter_suggestion': 'Sugestão do relator',
        'incidents.field_root_cause': 'Causa raiz',
        'incidents.field_corrective_action': 'Ação corretiva',
        'incidents.acknowledged_by': 'Reconhecido por {name} às {time}',
        'incidents.acknowledge_btn': '✋ Confirmar recebimento — n.º {id}',
        'incidents.acknowledged_success': 'Recebimento confirmado. Agora você é responsável por este relato.',
        'incidents.update_failed': 'Falha na atualização. Se isso persistir, a Segurança em Nível de Linha (RLS) pode estar bloqueando as gravações — ver schema_additions.sql.',
        'incidents.investigate_expander': '⚙️ Investigar — n.º {id}',
        'incidents.status_label': 'Status',
        'incidents.root_cause_label': 'Causa raiz',
        'incidents.corrective_action_label': 'Ação corretiva',
        'incidents.save_investigation': '💾 Salvar investigação',
        'incidents.updated_success': 'Incidente atualizado.',
        'incidents.submit_new_heading': 'Enviar novo relato de incidente',
        'incidents.submit_caption': 'Relate quase acidentes, lesões e riscos assim que possível. Relatos de gravidade crítica/alta notificam supervisores imediatamente.',
        'incidents.report_details_heading': 'Detalhes do relato',
        'incidents.type_label': 'Tipo',
        'incidents.severity_label': 'Gravidade',
        'incidents.department_label': 'Departamento',
        'incidents.shift_label': 'Turno',
        'incidents.your_id_label': 'Seu n.º de identificação',
        'incidents.related_asset_label': 'Ativo relacionado (opcional)',
        'incidents.none_option': 'Nenhum',
        'incidents.witnesses_label': 'Testemunhas (opcional)',
        'incidents.paper_ref_label': 'N.º de ref. do livro em papel (opcional)',
        'incidents.paper_ref_placeholder': 'ex. 0000651',
        'incidents.paper_ref_help': 'Se isso foi registrado primeiro no livro em papel de riscos/quase acidentes, anote o número aqui para que ambas as cópias possam ser cruzadas.',
        'incidents.location_label': 'Local / Área *',
        'incidents.description_label': 'Descrição *',
        'incidents.description_placeholder': 'O que aconteceu? Seja específico.',
        'incidents.immediate_action_label': 'Ação imediata tomada',
        'incidents.immediate_action_placeholder': 'O que foi feito imediatamente?',
        'incidents.suggestion_label': 'Minha sugestão / ação corretiva',
        'incidents.suggestion_placeholder': 'O que você acha que deveria ser feito para evitar que isso aconteça novamente?',
        'incidents.suggestion_help': 'Sua própria sugestão no momento do relato — separada do que o supervisor responsável pela investigação decidir depois.',
        'incidents.confirm_checkbox': 'Confirmo que os detalhes acima são precisos, segundo meu melhor conhecimento',
        'incidents.confirm_help': 'O equivalente digital de assinar o relato em papel.',
        'incidents.submit_btn': '🚨 Enviar relato',
        'incidents.err_required': 'Local e descrição são obrigatórios.',
        'incidents.err_confirm': 'Confirme que os detalhes estão corretos antes de enviar.',
        'incidents.success_reported': 'Incidente relatado. Obrigado por ajudar a manter o local seguro.',
        'incidents.warn_flagged': 'Isso foi sinalizado para atenção imediata do supervisor.',
        'incidents.err_submit_failed': 'Falha ao enviar o relato.',
        'permits.title': '🔐 Registro de Permissão de Trabalho / LOTO',
        'permits.caption': 'Uma permissão deve ser emitida, depois aceita pela pessoa que realiza o trabalho, e assinada na conclusão. Este registro é o rastro auditável dessa cadeia.',
        'permits.tab_active': 'Permissões ativas',
        'permits.tab_issue': 'Emitir permissão',
        'permits.tab_history': 'Histórico de permissões',
        'permits.field_task': 'Tarefa',
        'permits.field_lock_tags': 'Cadeados / etiquetas',
        'permits.field_isolation_points': 'Pontos de isolamento',
        'permits.field_hazards': 'Riscos',
        'permits.issued_by': 'Emitido por {name}',
        'permits.accepted_by': 'Aceito por {name}',
        'permits.signed_back_by': 'Encerrado por {name}',
        'permits.valid_until': 'Válido até {time}',
        'permits.step_issued': 'Emitido',
        'permits.step_accepted': 'Aceito',
        'permits.step_signed_back': 'Encerrado',
        'permits.expired_badge': 'EXPIRADO',
        'permits.accept_btn': '✍️ Aceitar isolamento',
        'permits.accept_success': 'Permissão aceita. Agora você é o responsável.',
        'permits.accept_failed': 'Falha ao aceitar — a permissão não foi atualizada. Verifique a Segurança em Nível de Linha (RLS) antes de considerar o isolamento em vigor.',
        'permits.signback_btn': '✅ Encerrar',
        'permits.signback_success': 'Permissão encerrada e fechada.',
        'permits.signback_failed': 'Falha ao encerrar — a permissão ainda aparece como ativa.',
        'permits.cancel_btn': '🚫 Cancelar',
        'permits.cancel_failed': 'Falha ao cancelar — a permissão não foi atualizada.',
        'permits.empty_title': 'Nenhuma permissão aberta',
        'permits.empty_desc': 'Os registros de Permissão de Trabalho / LOTO aparecerão aqui assim que uma for emitida.',
        'permits.expired_warning': '⚠️ {n} permissão(ões) aberta(s) ultrapassaram seu período de validade e devem ser revisadas ou canceladas.',
        'permits.search_placeholder': '🔍 Buscar por tipo de permissão ou etiqueta',
        'permits.issue_new_heading': 'Emitir nova permissão',
        'permits.no_open_tasks': 'Nenhuma tarefa aberta para associar a uma permissão.',
        'permits.task_label': 'Tarefa que requer a permissão *',
        'permits.type_label': 'Tipo de permissão',
        'permits.lock_tag_label': 'Números de cadeado / etiqueta *',
        'permits.lock_tag_placeholder': 'ex. LT-1042, LT-1043',
        'permits.isolation_points_label': 'Pontos de isolamento *',
        'permits.isolation_points_placeholder': 'Liste cada fonte de energia isolada',
        'permits.hazards_label': 'Riscos identificados *',
        'permits.hazards_placeholder': 'Energia armazenada, pressão residual, etc.',
        'permits.valid_hours_label': 'Válido por (horas)',
        'permits.confirm_checkbox': 'Confirmo que o isolamento foi verificado fisicamente em cada ponto listado acima.',
        'permits.issue_btn': '🔐 Emitir permissão',
        'permits.err_required': 'Cadeados/etiquetas, pontos de isolamento e riscos são todos obrigatórios.',
        'permits.err_confirm': 'Você deve confirmar a verificação física do isolamento antes que uma permissão possa ser emitida.',
        'permits.issue_success': 'Permissão #{id} emitida. Agora deve ser aceita pela pessoa que realiza o trabalho.',
        'permits.issue_failed': 'Falha ao emitir a permissão.',
        'permits.no_closed': 'Ainda não há permissões encerradas.',
        'contractors.title': '👷 Gestão de Contratados',
        'contractors.caption': 'O vencimento de indução e seguro é monitorado porque geralmente condicionam o acesso ao local. Registros vencidos ou ausentes são sinalizados como bloqueadores.',
        'contractors.tab_all': 'Todos os contratados',
        'contractors.tab_add': 'Adicionar contratado',
        'contractors.blocking_warning': '🚫 {n} contratado(s) têm registros de conformidade vencidos ou ausentes e não devem receber acesso ao local.',
        'contractors.empty_title': 'Nenhum contratado registrado ainda',
        'contractors.empty_desc': 'Adicione um contratado para começar a monitorar a conformidade de indução e seguro.',
        'contractors.search_placeholder': '🔍 Buscar por empresa ou nome de contato',
        'contractors.not_set': 'Não definido',
        'contractors.field_induction_expires': 'Indução vence',
        'contractors.field_insurance_expires': 'Seguro vence',
        'contractors.field_competencies': 'Competências',
        'contractors.update_expander': '⚙️ Atualizar {name}',
        'contractors.induction_expiry_label': 'Vencimento da indução',
        'contractors.insurance_expiry_label': 'Vencimento do seguro',
        'contractors.save_btn': '💾 Salvar',
        'contractors.update_success': 'Contratado atualizado.',
        'contractors.save_failed': 'Falha ao salvar — as datas de conformidade NÃO foram atualizadas. Verifique a Segurança em Nível de Linha (RLS) na tabela de contratados antes de considerar o status atualizado.',
        'contractors.company_name_label': 'Nome da empresa *',
        'contractors.contact_person_label': 'Pessoa de contato',
        'contractors.contact_email_label': 'E-mail de contato',
        'contractors.contact_phone_label': 'Telefone de contato',
        'contractors.induction_date_label': 'Data de indução',
        'contractors.induction_expiry_cap_label': 'Vencimento da indução',
        'contractors.insurance_expiry_cap_label': 'Vencimento do seguro',
        'contractors.competencies_label': 'Competências / Certificações',
        'contractors.competencies_placeholder': 'ex. Espaço confinado, licença PTA, manobra de alta tensão',
        'contractors.notes_label': 'Notas',
        'contractors.add_btn': '➕ Adicionar contratado',
        'contractors.add_success': "Contratado '{name}' adicionado.",
        'contractors.add_failed': 'Falha ao adicionar o contratado.',
        'contractors.err_name_required': 'O nome da empresa é obrigatório.',
        "nav.Owner Console": "Console do Proprietário",
        "common.save": "Salvar", "common.cancel": "Cancelar", "common.submit": "Enviar",
        "common.delete": "Excluir", "common.edit": "Editar", "common.search": "Pesquisar",
        "common.close": "Fechar", "common.back": "Voltar", "common.yes": "Sim",
        "common.no": "Não", "common.welcome": "Bem-vindo",
        "task.btn_post_comment": "Publicar comentário",
        "task.btn_upload_attachment": "Enviar anexo",
        "task.btn_upload": "Enviar",
        "task.btn_export_csv": "📥 Exportar tarefas como CSV",
        "task.caption_full_breakdowns": "As análises completas, análise de Pareto e relatórios de custos estão na seção **Análises**.",
        "task.caption_no_attachments": "Sem anexos.",
        "task.caption_no_broadcasts": "Ainda não há transmissões.",
        "task.caption_no_comments": "Ainda não há comentários.",
        "task.chk_recurring": "Tarefa recorrente (manutenção preventiva)",
        "task.chk_requires_jsa": "Requer AST",
        "task.chk_requires_loto": "Requer bloqueio LOTO",
        "task.chk_jsa_signed": "📋 AST assinada",
        "task.share_link_label": "Link para compartilhar",
        "task.chk_loto_isolated": "🔒 Bloqueio LOTO realizado",
        "task.err_cannot_move_progress": "Não é possível mover para \"Em andamento\" sem uma licença aceita.",
        "task.err_delete_failed": "Falha ao excluir. Se isso continuar, a Segurança em Nível de Linha (RLS) pode estar bloqueando gravações na tabela de tarefas.",
        "task.err_create_failed": "Falha ao criar a tarefa.",
        "task.err_comment_failed": "Falha ao publicar o comentário.",
        "task.err_title_location_required": "Título e localização são obrigatórios.",
        "task.err_upload_failed": "Falha no envio.",
        "task.err_safety_forms_required": "🔒 Os formulários de bloqueio de segurança são obrigatórios antes de continuar.",
        "task.err_permit_required": "🚫 **Esta tarefa requer uma licença de trabalho aceita.** Nenhuma licença ativa está registrada. Peça ao seu supervisor para emitir uma e depois aceite-a na seção Licenças antes de iniciar o trabalho.",
        "task.info_no_active_users": "Ainda não há usuários ativos.",
        "task.info_no_data": "Sem dados para exibir.",
        "task.info_no_messages": "Ainda não foram enviadas mensagens.",
        "task.info_no_tasks_assigned": "Nenhuma tarefa atribuída a você.",
        "task.info_no_tasks_found": "Nenhuma tarefa encontrada.",
        "task.info_no_tasks_manage": "Nenhuma tarefa para gerenciar.",
        "task.info_readonly_directory": "Este é um diretório somente leitura. Aprovações de acesso, mudanças de função e suspensões são gerenciadas pelo proprietário da conta.",
        "task.info_owner_note": "Você é o proprietário — aprovações e mudanças de função estão em **Console do Proprietário → Solicitações de Acesso**.",
        "task.info_latest_broadcasts": "📢 Últimas transmissões:",
        "task.hdr_all_broadcasts": "Todas as mensagens transmitidas",
        "task.hdr_all_tasks": "Todas as tarefas de manutenção",
        "task.hdr_dispatch_new": "Criar nova ordem de serviço",
        "task.hdr_full_control": "Controle total de tarefas",
        "task.hdr_recent_broadcasts": "Transmissões recentes",
        "task.hdr_user_directory": "👥 Diretório de usuários",
        "task.hdr_task_analytics": "📊 Análises de tarefas",
        "task.hdr_active_users": "Usuários ativos",
        "task.hdr_suspended": "Suspenso",
        "task.hdr_kpis": "🎯 Indicadores-chave de desempenho",
        "task.txt_closeout_details": "**Detalhes de encerramento** — essas informações alimentam os relatórios de confiabilidade e custos.",
        "task.txt_already_uploaded": "**📸 Já enviado:**",
        "task.field_failure_code": "Código de falha (para quebras)",
        "task.field_linked_asset": "Ativo vinculado (opcional)",
        "task.field_priority": "Prioridade",
        "task.field_recurrence": "Tipo de recorrência",
        "task.field_update_status": "Atualizar status",
        "task.field_work_type": "Tipo de trabalho",
        "task.success_attachment": "Anexo enviado!",
        "task.success_photo": "Foto enviada!",
        "task.success_safety_checks": "✅ Verificações de segurança aprovadas.",
        "task.success_no_unassigned": "🎉 Nenhuma tarefa não atribuída no momento.",
        "task.field_add_comment": "Adicionar comentário",
        "task.field_location": "Local / Área *",
        "task.field_task_title": "Título da tarefa *",
        "task.warn_plotly": "Plotly ou pandas não instalados. Execute: pip install plotly pandas",
    },
    "zh": {
        "nav.Task Dashboard": "任务看板", "nav.Help": "帮助", "nav.Assets": "资产",
        "nav.Permits": "许可证", "nav.Inventory": "库存",
        "nav.Incidents": "事故", "nav.Handover": "交接",
        "nav.Contractors": "承包商", "nav.Analytics": "分析",
        "nav.Chat": "聊天", "nav.Feedback": "反馈", "nav.Admin": "管理",
        "nav.Profile": "个人资料", "nav.Timeline": "时间线", "nav.About": "关于",
        "nav.Production": "产量",
        "nav.Haulage": "运输",
        "nav.Wallboard": "看板", "nav.Crew Clock": "打卡",
        "nav.JSA Library": "JSA库", "nav.Job Plans": "工作计划", "nav.Locations": "位置", "nav.Electrical Overview": "电气部门概览", "nav.Motor Rewinds": "电机重绕", "nav.Instrument Calibration": "仪表校准", "nav.Outage Commander": "停电指挥", "nav.Transformer Health": "变压器健康", "nav.Fault Recorder": "故障记录仪", "nav.HV Switching Schedule": "高压开关计划", "nav.Relay Settings": "继电器设置", "nav.Arc Flash Studies": "电弧闪光研究", "nav.Technician Certifications": "技术员认证",
        'incidents.title': '🚨 事故与安全报告',
        'incidents.tab_all': '所有事故',
        'incidents.tab_report': '报告事故',
        'incidents.tab_my_reports': '我的报告',
        'incidents.empty_title': '尚未报告任何事故',
        'incidents.empty_desc': '这是个好现象——危险和未遂事故将显示在这里。',
        'incidents.export_csv': '📥 导出事故为CSV',
        'incidents.download_csv': '下载CSV',
        'incidents.search_placeholder': '🔍 按类型、地点或描述搜索',
        'incidents.reported_by': '报告人：{name}',
        'incidents.id_no': '编号 {no}',
        'incidents.paper_ref': '纸质编号 #{no}',
        'incidents.field_immediate_action': '立即采取的行动',
        'incidents.field_reporter_suggestion': '报告人建议',
        'incidents.field_root_cause': '根本原因',
        'incidents.field_corrective_action': '纠正措施',
        'incidents.acknowledged_by': '由 {name} 于 {time} 确认',
        'incidents.acknowledge_btn': '✋ 确认接收 — #{id}',
        'incidents.acknowledged_success': '已确认。您现在是此报告的负责人。',
        'incidents.update_failed': '更新失败。如果持续发生，行级安全策略（RLS）可能阻止了写入 — 请参阅 schema_additions.sql。',
        'incidents.investigate_expander': '⚙️ 调查 — #{id}',
        'incidents.status_label': '状态',
        'incidents.root_cause_label': '根本原因',
        'incidents.corrective_action_label': '纠正措施',
        'incidents.save_investigation': '💾 保存调查',
        'incidents.updated_success': '事故已更新。',
        'incidents.submit_new_heading': '提交新事故报告',
        'incidents.submit_caption': '请尽快报告未遂事故、伤害和危险。严重/高级别报告将立即通知主管。',
        'incidents.report_details_heading': '报告详情',
        'incidents.type_label': '类型',
        'incidents.severity_label': '严重程度',
        'incidents.department_label': '部门',
        'incidents.shift_label': '班次',
        'incidents.your_id_label': '您的工号',
        'incidents.related_asset_label': '相关设备（可选）',
        'incidents.none_option': '无',
        'incidents.witnesses_label': '证人（可选）',
        'incidents.paper_ref_label': '纸质记录编号（可选）',
        'incidents.paper_ref_placeholder': '例如 0000651',
        'incidents.paper_ref_help': '如果最初记录在纸质危险/未遂事故登记簿中，请在此处记录其编号，以便两份记录相互对照。',
        'incidents.location_label': '地点/区域 *',
        'incidents.description_label': '描述 *',
        'incidents.description_placeholder': '发生了什么？请具体说明。',
        'incidents.immediate_action_label': '已采取的紧急行动',
        'incidents.immediate_action_placeholder': '当时立即做了什么？',
        'incidents.suggestion_label': '我的建议/纠正措施',
        'incidents.suggestion_placeholder': '您认为应该怎么做才能防止再次发生？',
        'incidents.suggestion_help': '您在报告时的个人建议——与调查主管之后的决定无关。',
        'incidents.confirm_checkbox': '我确认以上详情据我所知准确无误',
        'incidents.confirm_help': '相当于在纸质报告上签名的数字等效方式。',
        'incidents.submit_btn': '🚨 提交报告',
        'incidents.err_required': '地点和描述为必填项。',
        'incidents.err_confirm': '请在提交前确认详情准确无误。',
        'incidents.success_reported': '事故已报告。感谢您为现场安全做出的贡献。',
        'incidents.warn_flagged': '此事故已标记，需主管立即关注。',
        'incidents.err_submit_failed': '报告提交失败。',
        'permits.title': '🔐 工作许可证 / LOTO 登记册',
        'permits.caption': '许可证必须先签发，再由实际作业人员接受，完成后签回。此登记册是该流程的可审计记录。',
        'permits.tab_active': '有效许可证',
        'permits.tab_issue': '签发许可证',
        'permits.tab_history': '许可证历史',
        'permits.field_task': '任务',
        'permits.field_lock_tags': '锁具标签',
        'permits.field_isolation_points': '隔离点',
        'permits.field_hazards': '危险源',
        'permits.issued_by': '签发人：{name}',
        'permits.accepted_by': '接受人：{name}',
        'permits.signed_back_by': '签回人：{name}',
        'permits.valid_until': '有效期至 {time}',
        'permits.step_issued': '已签发',
        'permits.step_accepted': '已接受',
        'permits.step_signed_back': '已签回',
        'permits.expired_badge': '已过期',
        'permits.accept_btn': '✍️ 接受隔离',
        'permits.accept_success': '许可证已接受。您现在是责任人。',
        'permits.accept_failed': '接受失败——许可证未更新。在假定隔离已到位之前，请检查许可证表的行级安全策略（RLS）。',
        'permits.signback_btn': '✅ 签回',
        'permits.signback_success': '许可证已签回并关闭。',
        'permits.signback_failed': '签回失败——许可证仍显示为有效状态。',
        'permits.cancel_btn': '🚫 取消',
        'permits.cancel_failed': '取消失败——许可证未更新。',
        'permits.empty_title': '暂无有效许可证',
        'permits.empty_desc': '工作许可证 / LOTO 记录将在签发后显示在此处。',
        'permits.expired_warning': '⚠️ 有 {n} 个有效许可证已超过其有效期，必须审查或取消。',
        'permits.search_placeholder': '🔍 按许可证类型或锁具标签搜索',
        'permits.issue_new_heading': '签发新许可证',
        'permits.no_open_tasks': '没有可关联许可证的未完成任务。',
        'permits.task_label': '需要许可证的任务 *',
        'permits.type_label': '许可证类型',
        'permits.lock_tag_label': '锁具/标签编号 *',
        'permits.lock_tag_placeholder': '例如 LT-1042, LT-1043',
        'permits.isolation_points_label': '隔离点 *',
        'permits.isolation_points_placeholder': '列出每个已隔离的能源',
        'permits.hazards_label': '已识别的危险 *',
        'permits.hazards_placeholder': '储存的能量、残余压力等。',
        'permits.valid_hours_label': '有效期（小时）',
        'permits.confirm_checkbox': '我确认已对上述每个隔离点进行了实地核实。',
        'permits.issue_btn': '🔐 签发许可证',
        'permits.err_required': '锁具标签、隔离点和危险源均为必填项。',
        'permits.err_confirm': '签发许可证前，您必须确认已对隔离进行实地核实。',
        'permits.issue_success': '许可证 #{id} 已签发。现在必须由实际作业人员接受。',
        'permits.issue_failed': '许可证签发失败。',
        'permits.no_closed': '暂无已关闭的许可证。',
        'contractors.title': '👷 承包商管理',
        'contractors.caption': '由于入场培训和保险到期通常决定现场准入资格，因此会对其进行跟踪。已过期或缺失的记录将被标记为阻塞项。',
        'contractors.tab_all': '所有承包商',
        'contractors.tab_add': '添加承包商',
        'contractors.blocking_warning': '🚫 有 {n} 个承包商的合规记录已过期或缺失，不应被授予现场准入权限。',
        'contractors.empty_title': '尚未注册任何承包商',
        'contractors.empty_desc': '添加承包商以开始跟踪入场培训和保险合规情况。',
        'contractors.search_placeholder': '🔍 按公司或联系人姓名搜索',
        'contractors.not_set': '未设置',
        'contractors.field_induction_expires': '入场培训到期',
        'contractors.field_insurance_expires': '保险到期',
        'contractors.field_competencies': '资质能力',
        'contractors.update_expander': '⚙️ 更新 {name}',
        'contractors.induction_expiry_label': '入场培训到期日',
        'contractors.insurance_expiry_label': '保险到期日',
        'contractors.save_btn': '💾 保存',
        'contractors.update_success': '承包商信息已更新。',
        'contractors.save_failed': '保存失败——合规日期未更新。在假定该承包商状态为最新之前，请检查承包商表的行级安全策略（RLS）。',
        'contractors.company_name_label': '公司名称 *',
        'contractors.contact_person_label': '联系人',
        'contractors.contact_email_label': '联系邮箱',
        'contractors.contact_phone_label': '联系电话',
        'contractors.induction_date_label': '入场培训日期',
        'contractors.induction_expiry_cap_label': '入场培训到期日',
        'contractors.insurance_expiry_cap_label': '保险到期日',
        'contractors.competencies_label': '资质能力 / 认证',
        'contractors.competencies_placeholder': '例如：密闭空间、高空作业平台执照、高压switching',
        'contractors.notes_label': '备注',
        'contractors.add_btn': '➕ 添加承包商',
        'contractors.add_success': "承包商 '{name}' 已添加。",
        'contractors.add_failed': '添加承包商失败。',
        'contractors.err_name_required': '公司名称为必填项。',
        "nav.Owner Console": "所有者控制台",
        "common.save": "保存", "common.cancel": "取消", "common.submit": "提交",
        "common.delete": "删除", "common.edit": "编辑", "common.search": "搜索",
        "common.close": "关闭", "common.back": "返回", "common.yes": "是",
        "common.no": "否", "common.welcome": "欢迎",
        "task.btn_post_comment": "发布评论",
        "task.btn_upload_attachment": "上传附件",
        "task.btn_upload": "上传",
        "task.btn_export_csv": "📥 导出任务为CSV",
        "task.caption_full_breakdowns": "完整明细、帕累托分析和成本报告请见**分析**部分。",
        "task.caption_no_attachments": "暂无附件。",
        "task.caption_no_broadcasts": "暂无广播消息。",
        "task.caption_no_comments": "暂无评论。",
        "task.chk_recurring": "周期性任务（预防性维护）",
        "task.chk_requires_jsa": "需要工作安全分析（JSA）",
        "task.chk_requires_loto": "需要上锁挂牌（LOTO）",
        "task.chk_jsa_signed": "📋 工作安全分析已签署",
        "task.share_link_label": "分享链接",
        "task.chk_loto_isolated": "🔒 已完成上锁挂牌隔离",
        "task.err_cannot_move_progress": "没有已批准的许可证，无法移至“进行中”。",
        "task.err_delete_failed": "删除失败。如果持续出现此问题，可能是行级安全策略（RLS）阻止了对任务表的写入。",
        "task.err_create_failed": "创建任务失败。",
        "task.err_comment_failed": "发布评论失败。",
        "task.err_title_location_required": "标题和位置为必填项。",
        "task.err_upload_failed": "上传失败。",
        "task.err_safety_forms_required": "🔒 继续之前需要填写安全隔离表格。",
        "task.err_permit_required": "🚫 **此任务需要已批准的工作许可证。** 目前没有有效的许可证记录。请让您的主管签发许可证，然后在“许可证”部分接受后再开始工作。",
        "task.info_no_active_users": "暂无活跃用户。",
        "task.info_no_data": "暂无数据可显示。",
        "task.info_no_messages": "暂未发送任何消息。",
        "task.info_no_tasks_assigned": "没有分配给您的任务。",
        "task.info_no_tasks_found": "未找到任务。",
        "task.info_no_tasks_manage": "没有需要管理的任务。",
        "task.info_readonly_directory": "这是一个只读目录。访问审批、角色变更和账户暂停由账户所有者管理。",
        "task.info_owner_note": "您是所有者——审批和角色变更请前往 **所有者控制台 → 访问请求**。",
        "task.info_latest_broadcasts": "📢 最新广播：",
        "task.hdr_all_broadcasts": "所有广播消息",
        "task.hdr_all_tasks": "所有维护任务",
        "task.hdr_dispatch_new": "创建新工单",
        "task.hdr_full_control": "任务完全控制",
        "task.hdr_recent_broadcasts": "近期广播",
        "task.hdr_user_directory": "👥 用户目录",
        "task.hdr_task_analytics": "📊 任务分析",
        "task.hdr_active_users": "活跃用户",
        "task.hdr_suspended": "已暂停",
        "task.hdr_kpis": "🎯 关键绩效指标",
        "task.txt_closeout_details": "**结案详情** —— 这些信息将用于可靠性和成本报告。",
        "task.txt_already_uploaded": "**📸 已上传：**",
        "task.field_failure_code": "故障代码（用于故障维修）",
        "task.field_linked_asset": "关联资产（可选）",
        "task.field_priority": "优先级",
        "task.field_recurrence": "重复类型",
        "task.field_update_status": "更新状态",
        "task.field_work_type": "工作类型",
        "task.success_attachment": "附件已上传！",
        "task.success_photo": "照片已上传！",
        "task.success_safety_checks": "✅ 安全检查已通过。",
        "task.success_no_unassigned": "🎉 目前没有未分配的任务。",
        "task.field_add_comment": "添加评论",
        "task.field_location": "位置/区域 *",
        "task.field_task_title": "任务标题 *",
        "task.warn_plotly": "未安装 Plotly 或 pandas。请运行：pip install plotly pandas",
    },
    "hi": {
        "nav.Task Dashboard": "कार्य डैशबोर्ड", "nav.Help": "सहायता", "nav.Assets": "संपत्ति",
        "nav.Permits": "परमिट", "nav.Inventory": "इन्वेंटरी",
        "nav.Incidents": "घटनाएं", "nav.Handover": "पाली हस्तांतरण",
        "nav.Contractors": "ठेकेदार", "nav.Analytics": "विश्लेषण",
        "nav.Chat": "चैट", "nav.Feedback": "प्रतिक्रिया", "nav.Admin": "व्यवस्थापक",
        "nav.Profile": "प्रोफ़ाइल", "nav.Timeline": "समयरेखा", "nav.About": "के बारे में",
        "nav.Production": "उत्पादन",
        "nav.Haulage": "परिवहन",
        "nav.Wallboard": "वॉलबोर्ड", "nav.Crew Clock": "क्रू क्लॉक",
        "nav.JSA Library": "जेएसए लाइब्रेरी", "nav.Job Plans": "जॉब प्लान", "nav.Locations": "स्थान", "nav.Electrical Overview": "विद्युत अवलोकन", "nav.Motor Rewinds": "मोटर रिवाइंडिंग", "nav.Instrument Calibration": "उपकरण अंशांकन", "nav.Outage Commander": "आउटेज कमांडर", "nav.Transformer Health": "ट्रांसफार्मर स्वास्थ्य", "nav.Fault Recorder": "फॉल्ट रिकॉर्डर", "nav.HV Switching Schedule": "एचवी स्विचिंग शेड्यूल", "nav.Relay Settings": "रिले सेटिंग्स", "nav.Arc Flash Studies": "आर्क फ्लैश अध्ययन", "nav.Technician Certifications": "तकनीशियन प्रमाणन",
        'incidents.title': '🚨 घटना और सुरक्षा रिपोर्टिंग',
        'incidents.tab_all': 'सभी घटनाएं',
        'incidents.tab_report': 'घटना रिपोर्ट करें',
        'incidents.tab_my_reports': 'मेरी रिपोर्ट्स',
        'incidents.empty_title': 'अभी तक कोई घटना रिपोर्ट नहीं की गई',
        'incidents.empty_desc': 'यह अच्छा संकेत है — खतरे और निकट-चूक यहां दिखाई देंगे।',
        'incidents.export_csv': '📥 घटनाओं को CSV के रूप में निर्यात करें',
        'incidents.download_csv': 'CSV डाउनलोड करें',
        'incidents.search_placeholder': '🔍 प्रकार, स्थान या विवरण से खोजें',
        'incidents.reported_by': 'रिपोर्ट किया गया: {name}',
        'incidents.id_no': 'आईडी {no}',
        'incidents.paper_ref': 'पेपर संदर्भ #{no}',
        'incidents.field_immediate_action': 'तत्काल कार्रवाई',
        'incidents.field_reporter_suggestion': 'रिपोर्टर का सुझाव',
        'incidents.field_root_cause': 'मूल कारण',
        'incidents.field_corrective_action': 'सुधारात्मक कार्रवाई',
        'incidents.acknowledged_by': '{name} द्वारा {time} पर स्वीकार किया गया',
        'incidents.acknowledge_btn': '✋ प्राप्ति स्वीकार करें — #{id}',
        'incidents.acknowledged_success': 'स्वीकार किया गया। अब आप इस रिपोर्ट के जिम्मेदार व्यक्ति हैं।',
        'incidents.update_failed': 'अपडेट विफल रहा। यदि यह जारी रहता है, तो Row Level Security लेखन को रोक रही हो सकती है — schema_additions.sql देखें।',
        'incidents.investigate_expander': '⚙️ जांच करें — #{id}',
        'incidents.status_label': 'स्थिति',
        'incidents.root_cause_label': 'मूल कारण',
        'incidents.corrective_action_label': 'सुधारात्मक कार्रवाई',
        'incidents.save_investigation': '💾 जांच सहेजें',
        'incidents.updated_success': 'घटना अपडेट की गई।',
        'incidents.submit_new_heading': 'नई घटना रिपोर्ट सबमिट करें',
        'incidents.submit_caption': 'निकट-चूक, चोटों और खतरों की रिपोर्ट जल्द से जल्द करें। गंभीर/उच्च स्तर की रिपोर्ट तुरंत पर्यवेक्षकों को सूचित करती हैं।',
        'incidents.report_details_heading': 'रिपोर्ट विवरण',
        'incidents.type_label': 'प्रकार',
        'incidents.severity_label': 'गंभीरता',
        'incidents.department_label': 'विभाग',
        'incidents.shift_label': 'शिफ्ट',
        'incidents.your_id_label': 'आपका आईडी नंबर',
        'incidents.related_asset_label': 'संबंधित संपत्ति (वैकल्पिक)',
        'incidents.none_option': 'कोई नहीं',
        'incidents.witnesses_label': 'गवाह (वैकल्पिक)',
        'incidents.paper_ref_label': 'पेपर बुक संदर्भ संख्या (वैकल्पिक)',
        'incidents.paper_ref_placeholder': 'जैसे 0000651',
        'incidents.paper_ref_help': 'यदि इसे पहले पेपर खतरा/निकट-चूक बुक में लिखा गया था, तो यहां उसकी संख्या दर्ज करें ताकि दोनों प्रतियों को मिलाया जा सके।',
        'incidents.location_label': 'स्थान / क्षेत्र *',
        'incidents.description_label': 'विवरण *',
        'incidents.description_placeholder': 'क्या हुआ? विशिष्ट रहें।',
        'incidents.immediate_action_label': 'तुरंत की गई कार्रवाई',
        'incidents.immediate_action_placeholder': 'तुरंत क्या किया गया?',
        'incidents.suggestion_label': 'मेरा सुझाव / सुधारात्मक कार्रवाई',
        'incidents.suggestion_placeholder': 'आपको क्या लगता है कि इसे दोबारा होने से रोकने के लिए क्या किया जाना चाहिए?',
        'incidents.suggestion_help': 'रिपोर्टिंग के समय आपका अपना सुझाव — जांच करने वाले पर्यवेक्षक के बाद के निर्णय से अलग।',
        'incidents.confirm_checkbox': 'मैं पुष्टि करता/करती हूं कि उपरोक्त विवरण मेरी सर्वोत्तम जानकारी के अनुसार सटीक हैं',
        'incidents.confirm_help': 'पेपर रिपोर्ट पर हस्ताक्षर करने के डिजिटल बराबर।',
        'incidents.submit_btn': '🚨 रिपोर्ट सबमिट करें',
        'incidents.err_required': 'स्थान और विवरण आवश्यक हैं।',
        'incidents.err_confirm': 'सबमिट करने से पहले कृपया विवरण की सटीकता की पुष्टि करें।',
        'incidents.success_reported': 'घटना रिपोर्ट की गई। साइट को सुरक्षित रखने में मदद के लिए धन्यवाद।',
        'incidents.warn_flagged': 'इसे पर्यवेक्षक के तत्काल ध्यान के लिए चिह्नित किया गया है।',
        'incidents.err_submit_failed': 'रिपोर्ट सबमिट करने में विफल।',
        'permits.title': '🔐 कार्य परमिट / LOTO रजिस्टर',
        'permits.caption': 'एक परमिट जारी किया जाना चाहिए, फिर काम करने वाले व्यक्ति द्वारा स्वीकार किया जाना चाहिए, और पूरा होने पर हस्ताक्षरित होना चाहिए। यह रजिस्टर उस श्रृंखला का ऑडिट योग्य रिकॉर्ड है।',
        'permits.tab_active': 'सक्रिय परमिट',
        'permits.tab_issue': 'परमिट जारी करें',
        'permits.tab_history': 'परमिट इतिहास',
        'permits.field_task': 'कार्य',
        'permits.field_lock_tags': 'लॉक टैग',
        'permits.field_isolation_points': 'आइसोलेशन पॉइंट्स',
        'permits.field_hazards': 'खतरे',
        'permits.issued_by': 'जारीकर्ता: {name}',
        'permits.accepted_by': 'स्वीकर्ता: {name}',
        'permits.signed_back_by': 'हस्ताक्षरकर्ता: {name}',
        'permits.valid_until': '{time} तक मान्य',
        'permits.step_issued': 'जारी किया गया',
        'permits.step_accepted': 'स्वीकृत',
        'permits.step_signed_back': 'हस्ताक्षरित',
        'permits.expired_badge': 'समाप्त',
        'permits.accept_btn': '✍️ आइसोलेशन स्वीकार करें',
        'permits.accept_success': 'परमिट स्वीकृत। अब आप जिम्मेदार व्यक्ति हैं।',
        'permits.accept_failed': 'स्वीकृति विफल — परमिट अपडेट नहीं हुआ। आइसोलेशन को सही मानने से पहले Row Level Security जांचें।',
        'permits.signback_btn': '✅ साइन बैक करें',
        'permits.signback_success': 'परमिट साइन बैक और बंद कर दिया गया।',
        'permits.signback_failed': 'साइन-बैक विफल — परमिट अभी भी सक्रिय दिखा रहा है।',
        'permits.cancel_btn': '🚫 रद्द करें',
        'permits.cancel_failed': 'रद्द करना विफल — परमिट अपडेट नहीं हुआ।',
        'permits.empty_title': 'कोई खुला परमिट नहीं',
        'permits.empty_desc': 'कार्य परमिट / LOTO रिकॉर्ड जारी होने पर यहां दिखाई देंगे।',
        'permits.expired_warning': '⚠️ {n} खुले परमिट अपनी वैधता अवधि पार कर चुके हैं और उनकी समीक्षा या रद्द किया जाना आवश्यक है।',
        'permits.search_placeholder': '🔍 परमिट प्रकार या लॉक टैग से खोजें',
        'permits.issue_new_heading': 'नया परमिट जारी करें',
        'permits.no_open_tasks': 'परमिट जोड़ने के लिए कोई खुला कार्य नहीं है।',
        'permits.task_label': 'परमिट की आवश्यकता वाला कार्य *',
        'permits.type_label': 'परमिट प्रकार',
        'permits.lock_tag_label': 'लॉक / टैग नंबर *',
        'permits.lock_tag_placeholder': 'जैसे LT-1042, LT-1043',
        'permits.isolation_points_label': 'आइसोलेशन पॉइंट्स *',
        'permits.isolation_points_placeholder': 'प्रत्येक आइसोलेटेड ऊर्जा स्रोत सूचीबद्ध करें',
        'permits.hazards_label': 'पहचाने गए खतरे *',
        'permits.hazards_placeholder': 'संग्रहीत ऊर्जा, अवशिष्ट दबाव, आदि।',
        'permits.valid_hours_label': 'के लिए मान्य (घंटे)',
        'permits.confirm_checkbox': 'मैं पुष्टि करता/करती हूं कि ऊपर सूचीबद्ध प्रत्येक बिंदु पर आइसोलेशन की भौतिक रूप से पुष्टि की गई है।',
        'permits.issue_btn': '🔐 परमिट जारी करें',
        'permits.err_required': 'लॉक टैग, आइसोलेशन पॉइंट्स और खतरे — सभी आवश्यक हैं।',
        'permits.err_confirm': 'परमिट जारी करने से पहले आपको आइसोलेशन की भौतिक पुष्टि करनी होगी।',
        'permits.issue_success': 'परमिट #{id} जारी किया गया। अब इसे काम करने वाले व्यक्ति द्वारा स्वीकार किया जाना चाहिए।',
        'permits.issue_failed': 'परमिट जारी करने में विफल।',
        'permits.no_closed': 'अभी तक कोई परमिट बंद नहीं हुआ है।',
        'contractors.title': '👷 ठेकेदार प्रबंधन',
        'contractors.caption': 'इंडक्शन और बीमा समाप्ति को ट्रैक किया जाता है क्योंकि वे आमतौर पर साइट पहुंच को नियंत्रित करते हैं। समाप्त या अनुपलब्ध रिकॉर्ड को अवरोधक के रूप में चिह्नित किया जाता है।',
        'contractors.tab_all': 'सभी ठेकेदार',
        'contractors.tab_add': 'ठेकेदार जोड़ें',
        'contractors.blocking_warning': '🚫 {n} ठेकेदार(रों) के अनुपालन रिकॉर्ड समाप्त हो गए हैं या अनुपलब्ध हैं और उन्हें साइट पहुंच नहीं दी जानी चाहिए।',
        'contractors.empty_title': 'अभी तक कोई ठेकेदार पंजीकृत नहीं है',
        'contractors.empty_desc': 'इंडक्शन और बीमा अनुपालन ट्रैक करना शुरू करने के लिए एक ठेकेदार जोड़ें।',
        'contractors.search_placeholder': '🔍 कंपनी या संपर्क नाम से खोजें',
        'contractors.not_set': 'सेट नहीं है',
        'contractors.field_induction_expires': 'इंडक्शन समाप्ति',
        'contractors.field_insurance_expires': 'बीमा समाप्ति',
        'contractors.field_competencies': 'योग्यताएं',
        'contractors.update_expander': '⚙️ अपडेट करें {name}',
        'contractors.induction_expiry_label': 'इंडक्शन समाप्ति तिथि',
        'contractors.insurance_expiry_label': 'बीमा समाप्ति तिथि',
        'contractors.save_btn': '💾 सहेजें',
        'contractors.update_success': 'ठेकेदार अपडेट किया गया।',
        'contractors.save_failed': 'सहेजना विफल — अनुपालन तिथियां अपडेट नहीं हुईं। इस ठेकेदार की स्थिति को वर्तमान मानने से पहले Row Level Security जांचें।',
        'contractors.company_name_label': 'कंपनी का नाम *',
        'contractors.contact_person_label': 'संपर्क व्यक्ति',
        'contractors.contact_email_label': 'संपर्क ईमेल',
        'contractors.contact_phone_label': 'संपर्क फोन',
        'contractors.induction_date_label': 'इंडक्शन तिथि',
        'contractors.induction_expiry_cap_label': 'इंडक्शन समाप्ति',
        'contractors.insurance_expiry_cap_label': 'बीमा समाप्ति',
        'contractors.competencies_label': 'योग्यताएं / प्रमाणपत्र',
        'contractors.competencies_placeholder': 'जैसे सीमित स्थान, EWP लाइसेंस, HV स्विचिंग',
        'contractors.notes_label': 'टिप्पणियां',
        'contractors.add_btn': '➕ ठेकेदार जोड़ें',
        'contractors.add_success': "ठेकेदार '{name}' जोड़ा गया।",
        'contractors.add_failed': 'ठेकेदार जोड़ने में विफल।',
        'contractors.err_name_required': 'कंपनी का नाम आवश्यक है।',
        "nav.Owner Console": "स्वामी कंसोल",
        "common.save": "सहेजें", "common.cancel": "रद्द करें", "common.submit": "जमा करें",
        "common.delete": "हटाएं", "common.edit": "संपादित करें", "common.search": "खोजें",
        "common.close": "बंद करें", "common.back": "वापस", "common.yes": "हाँ",
        "common.no": "नहीं", "common.welcome": "स्वागत है",
        "task.btn_post_comment": "टिप्पणी पोस्ट करें",
        "task.btn_upload_attachment": "अटैचमेंट अपलोड करें",
        "task.btn_upload": "अपलोड करें",
        "task.btn_export_csv": "📥 कार्यों को CSV के रूप में निर्यात करें",
        "task.caption_full_breakdowns": "पूर्ण विवरण, पैरेटो विश्लेषण और लागत रिपोर्टिंग **विश्लेषण** सेक्शन में हैं।",
        "task.caption_no_attachments": "कोई अटैचमेंट नहीं।",
        "task.caption_no_broadcasts": "अभी तक कोई प्रसारण नहीं।",
        "task.caption_no_comments": "अभी तक कोई टिप्पणी नहीं।",
        "task.chk_recurring": "आवर्ती कार्य (निवारक रखरखाव)",
        "task.chk_requires_jsa": "JSA आवश्यक है",
        "task.chk_requires_loto": "LOTO आवश्यक है",
        "task.chk_jsa_signed": "📋 JSA पर हस्ताक्षर किए गए",
        "task.share_link_label": "साझा लिंक",
        "task.chk_loto_isolated": "🔒 LOTO आइसोलेशन पूर्ण",
        "task.err_cannot_move_progress": "स्वीकृत परमिट के बिना 'प्रगति पर' में स्थानांतरित नहीं किया जा सकता।",
        "task.err_delete_failed": "हटाना विफल रहा। यदि यह बार-बार हो रहा है, तो हो सकता है कि Row Level Security (RLS) tasks टेबल में लेखन को रोक रही हो।",
        "task.err_create_failed": "कार्य बनाने में विफल।",
        "task.err_comment_failed": "टिप्पणी पोस्ट करने में विफल।",
        "task.err_title_location_required": "शीर्षक और स्थान आवश्यक हैं।",
        "task.err_upload_failed": "अपलोड विफल रहा।",
        "task.err_safety_forms_required": "🔒 आगे बढ़ने से पहले सुरक्षा आइसोलेशन फॉर्म आवश्यक हैं।",
        "task.err_permit_required": "🚫 **इस कार्य के लिए स्वीकृत वर्क परमिट आवश्यक है।** इसके विरुद्ध कोई सक्रिय परमिट दर्ज नहीं है। अपने सुपरवाइज़र से परमिट जारी करने के लिए कहें, फिर काम शुरू करने से पहले परमिट सेक्शन में उसे स्वीकार करें।",
        "task.info_no_active_users": "अभी तक कोई सक्रिय उपयोगकर्ता नहीं।",
        "task.info_no_data": "दिखाने के लिए कोई डेटा नहीं।",
        "task.info_no_messages": "अभी तक कोई संदेश नहीं भेजा गया।",
        "task.info_no_tasks_assigned": "आपको कोई कार्य नहीं सौंपा गया है।",
        "task.info_no_tasks_found": "कोई कार्य नहीं मिला।",
        "task.info_no_tasks_manage": "प्रबंधित करने के लिए कोई कार्य नहीं।",
        "task.info_readonly_directory": "यह केवल पढ़ने योग्य निर्देशिका है। एक्सेस अनुमोदन, भूमिका परिवर्तन और निलंबन खाता स्वामी द्वारा संभाले जाते हैं।",
        "task.info_owner_note": "आप स्वामी हैं — अनुमोदन और भूमिका परिवर्तन **स्वामी कंसोल → एक्सेस अनुरोध** में हैं।",
        "task.info_latest_broadcasts": "📢 नवीनतम प्रसारण:",
        "task.hdr_all_broadcasts": "सभी प्रसारण संदेश",
        "task.hdr_all_tasks": "सभी रखरखाव कार्य",
        "task.hdr_dispatch_new": "नया कार्य आदेश भेजें",
        "task.hdr_full_control": "पूर्ण कार्य नियंत्रण",
        "task.hdr_recent_broadcasts": "हाल के प्रसारण",
        "task.hdr_user_directory": "👥 उपयोगकर्ता निर्देशिका",
        "task.hdr_task_analytics": "📊 कार्य विश्लेषण",
        "task.hdr_active_users": "सक्रिय उपयोगकर्ता",
        "task.hdr_suspended": "निलंबित",
        "task.hdr_kpis": "🎯 प्रमुख प्रदर्शन संकेतक",
        "task.txt_closeout_details": "**समापन विवरण** — यह जानकारी विश्वसनीयता और लागत रिपोर्ट में उपयोग होती है।",
        "task.txt_already_uploaded": "**📸 पहले से अपलोड किया गया:**",
        "task.field_failure_code": "विफलता कोड (खराबी के काम के लिए)",
        "task.field_linked_asset": "जुड़ी हुई संपत्ति (वैकल्पिक)",
        "task.field_priority": "प्राथमिकता",
        "task.field_recurrence": "पुनरावृत्ति प्रकार",
        "task.field_update_status": "स्थिति अपडेट करें",
        "task.field_work_type": "कार्य प्रकार",
        "task.success_attachment": "अटैचमेंट अपलोड हो गया!",
        "task.success_photo": "फोटो अपलोड हो गई!",
        "task.success_safety_checks": "✅ सुरक्षा जांच पास हो गई।",
        "task.success_no_unassigned": "🎉 फिलहाल कोई अनसाइन्ड कार्य नहीं है।",
        "task.field_add_comment": "टिप्पणी जोड़ें",
        "task.field_location": "स्थान / क्षेत्र *",
        "task.field_task_title": "कार्य शीर्षक *",
        "task.warn_plotly": "Plotly या pandas इंस्टॉल नहीं है। कृपया चलाएँ: pip install plotly pandas",
    },
}


def get_user_language():
    """Session-cached, falls back to English for anything unexpected —
    an unrecognized or missing language code should never break the
    app, just silently show English."""
    lang = st.session_state.get("user_language", "en")
    return lang if lang in SUPPORTED_LANGUAGES else "en"


def t(key):
    """Translation lookup with a safe fallback chain: current language
    -> English -> the key itself. The last step matters — it means a
    key that was never translated at all still shows SOMETHING
    readable-ish rather than crashing or showing blank text."""
    lang = get_user_language()
    return TRANSLATIONS.get(lang, {}).get(key) or TRANSLATIONS["en"].get(key) or key


def set_user_language(lang_code, username):
    """Persists the choice to the database (so it survives future
    logins, not just this session) and updates the session immediately
    either way — the UI should feel instant even if the database write
    is slow or fails."""
    st.session_state["user_language"] = lang_code
    if SUPABASE_AVAILABLE:
        try:
            supabase.table("facility_users").update(
                {"preferred_language": lang_code}
            ).eq("username", username).execute()
        except Exception as e:
            log_error(str(e), endpoint="set_user_language")
            # Deliberately not surfaced as an error to the user — the
            # session-level change above already took effect, so their
            # immediate experience is correct even if persistence
            # across future logins silently didn't save this time.


# Registry of available "My Dashboard" widgets — a curated set of
# EXISTING analytics functions already built and proven elsewhere in
# this app, not a general-purpose widget framework. Each entry is
# (label, icon, render_function) — render_function takes the same
# (tasks, assets, incidents, parts_lookup) bundle every widget needs,
# even if a given widget only uses some of them, so the calling code
# doesn't need per-widget special-casing for which arguments to pass.
def _dash_widget_mtbf(tasks, assets, incidents, parts_lookup):
    mtbf, mtbf_n = compute_mtbf_hours(tasks)
    st.metric("MTBF (hours)", f"{mtbf:.1f}" if mtbf is not None else "No data", f"{mtbf_n} interval(s)")

def _dash_widget_cost_by_category(tasks, assets, incidents, parts_lookup):
    cats = cost_by_category(tasks, parts_lookup)
    if not cats:
        st.info("No cost data yet.")
    else:
        for c in cats[:5]:
            st.write(f"**{c['category']}**: {c['total_cost']:,.2f}")

def _dash_widget_predictive_alerts(tasks, assets, incidents, parts_lookup):
    alerts = get_predictive_failure_alerts(tasks, assets)
    if not alerts:
        st.info("No assets currently approaching their typical failure window.")
    else:
        for a in alerts[:3]:
            st.warning(f"**{a['asset_name']}** — {a['pct_of_window']:.0%} of typical interval between failures")

def _dash_widget_open_tasks(tasks, assets, incidents, parts_lookup):
    open_t = [t2 for t2 in tasks if t2.get("status") != "Complete"]
    overdue = [t2 for t2 in open_t if t2.get("due_date") and (_parse_dt(t2["due_date"]) or datetime.max) < datetime.now()]
    c1, c2 = st.columns(2)
    c1.metric("Open Tasks", len(open_t))
    c2.metric("Overdue", len(overdue))

def _dash_widget_safety_snapshot(tasks, assets, incidents, parts_lookup):
    si = safety_leading_indicators(incidents, tasks)
    c1, c2 = st.columns(2)
    c1.metric("Incidents (30d)", si["last_30_days"])
    c2.metric("Proactive Reports", si["proactive_reports"])

def _dash_widget_cost_anomalies(tasks, assets, incidents, parts_lookup):
    anomalies = detect_cost_anomalies(tasks, parts_lookup)
    if not anomalies:
        st.info("No cost anomalies detected.")
    else:
        for a in anomalies[:3]:
            st.warning(f"**#{a['task_id']} {a['title']}** — {a['cost']:,.2f} (typical: {a['category_mean']:,.2f})")

def _dash_widget_electrical_subsections(tasks, assets, incidents, parts_lookup):
    workload = get_electrical_subsection_workload(tasks)
    for sub, counts in workload.items():
        st.write(f"**{sub}**: {counts['open']} open ({counts['overdue']} overdue), "
                f"{counts['completed_last_30d']} completed (30d)")

def _dash_widget_active_outages(tasks, assets, incidents, parts_lookup):
    outages = fetch_outage_events(active_only=True)
    if not outages:
        st.info("No active outages.")
    else:
        for e in outages:
            st.error(f"**{e.get('location') or 'Location not set'}** — Commander: {e['outage_commander']}")

def _dash_widget_transformer_status(tasks, assets, incidents, parts_lookup):
    dga_tests = fetch_dga_tests()
    transformer_tags = sorted(set(t["transformer_tag"] for t in dga_tests))
    if not transformer_tags:
        st.info("No transformers tracked yet.")
        return
    worst_transformer = None
    for tag in transformer_tags:
        latest = max((t for t in dga_tests if t["transformer_tag"] == tag), key=lambda t: t["test_date"])
        worst, worst_gases = worst_dga_condition(latest)
        if worst_transformer is None or worst > worst_transformer[1]:
            worst_transformer = (tag, worst, worst_gases)
    _sev = {0: "info", 1: "success", 2: "warning", 3: "warning", 4: "error"}[worst_transformer[1]]
    getattr(st, _sev)(f"Worst: **{worst_transformer[0]}** — Condition {worst_transformer[1] or 'N/A'}")

def _dash_widget_pending_switching(tasks, assets, incidents, parts_lookup):
    pending = fetch_switching_orders(status="Draft")
    if not pending:
        st.info("No switching orders awaiting authorization.")
    else:
        for o in pending[:3]:
            st.warning(f"**{o['title']}** — awaiting {o.get('designated_approver') or 'approval'}")

def _dash_widget_calibration_alerts(tasks, assets, incidents, parts_lookup):
    overdue, due_soon = [], []
    for c in fetch_instrument_calibrations():
        _, _, status = instrument_calibration_status(c)
        if status == "overdue":
            overdue.append(c)
        elif status == "due_soon":
            due_soon.append(c)
    if not overdue and not due_soon:
        st.info("No calibrations overdue or due soon.")
    else:
        if overdue:
            st.error(f"{len(overdue)} overdue")
        if due_soon:
            st.warning(f"{len(due_soon)} due within 7 days")

DASHBOARD_WIDGET_REGISTRY = {
    "mtbf": ("Reliability (MTBF)", "fa-gears", _dash_widget_mtbf),
    "cost_by_category": ("Cost by Category", "fa-sack-dollar", _dash_widget_cost_by_category),
    "predictive_alerts": ("Predictive Failure Alerts", "fa-triangle-exclamation", _dash_widget_predictive_alerts),
    "open_tasks": ("Open Tasks Snapshot", "fa-clipboard-list", _dash_widget_open_tasks),
    "safety_snapshot": ("Safety Snapshot", "fa-shield-heart", _dash_widget_safety_snapshot),
    "cost_anomalies": ("Cost Anomalies", "fa-magnifying-glass-dollar", _dash_widget_cost_anomalies),
    "electrical_subsections": ("Electrical Dept. Workload", "fa-bolt", _dash_widget_electrical_subsections),
    "active_outages": ("Active Outages", "fa-triangle-exclamation", _dash_widget_active_outages),
    "transformer_status": ("Transformer Status", "fa-bolt", _dash_widget_transformer_status),
    "pending_switching": ("Pending Switching Authorizations", "fa-toggle-on", _dash_widget_pending_switching),
    "calibration_alerts": ("Calibration Alerts", "fa-gauge", _dash_widget_calibration_alerts),
}
DEFAULT_DASHBOARD_WIDGETS = ["open_tasks", "mtbf"]


def get_user_dashboard_widgets(username):
    """Returns the list of widget keys this user has chosen for My
    Dashboard — from session_state if already loaded this session,
    otherwise the database, otherwise DEFAULT_DASHBOARD_WIDGETS.
    Invalid/removed widget keys are filtered out silently rather than
    crashing the dashboard if the registry ever changes.
    """
    if "_dashboard_widgets" in st.session_state:
        return st.session_state["_dashboard_widgets"]
    widgets = DEFAULT_DASHBOARD_WIDGETS
    if SUPABASE_AVAILABLE:
        try:
            res = supabase.table("facility_users").select("dashboard_widgets").eq("username", username).execute()
            if res.data and res.data[0].get("dashboard_widgets"):
                saved = json.loads(res.data[0]["dashboard_widgets"])
                widgets = [w for w in saved if w in DASHBOARD_WIDGET_REGISTRY] or DEFAULT_DASHBOARD_WIDGETS
        except Exception as e:
            log_error(str(e), endpoint="get_user_dashboard_widgets")
    st.session_state["_dashboard_widgets"] = widgets
    return widgets


def set_user_dashboard_widgets(widget_keys, username):
    """Persists the widget selection — same immediate-session-update-
    regardless-of-database-outcome pattern as set_user_language."""
    st.session_state["_dashboard_widgets"] = widget_keys
    if SUPABASE_AVAILABLE:
        try:
            supabase.table("facility_users").update(
                {"dashboard_widgets": json.dumps(widget_keys)}
            ).eq("username", username).execute()
        except Exception as e:
            log_error(str(e), endpoint="set_user_dashboard_widgets")


def mark_welcome_seen(username):
    """Persists that this account has dismissed the first-login
    welcome, so it genuinely shows once ever, not once per session —
    same reasoning and same pattern as set_user_language above."""
    st.session_state["_show_welcome"] = False
    if SUPABASE_AVAILABLE:
        try:
            supabase.table("facility_users").update(
                {"has_seen_welcome": True}
            ).eq("username", username).execute()
        except Exception as e:
            log_error(str(e), endpoint="mark_welcome_seen")


def search_features(query, nav_options):
    """Static keyword match against the curated page/feature index,
    filtered to what the current user can actually reach — the index
    itself has no concept of roles, but the SAME nav_options already
    used to build the real navigation (respecting role permissions
    and Feature Toggles) is the source of truth for who can go where.
    Without this filter, a Worker searching "branding" would get a
    search result suggesting Owner Console, which does nothing for
    them since it was never in their real nav in the first place —
    a genuine correctness gap, not just an unhelpful result."""
    q = query.lower().strip()
    if not q:
        return []
    return [(label, icon, section) for keywords, label, icon, section in FEATURE_INDEX
           if (q in keywords.lower() or q in label.lower()) and section in nav_options]


def search_records(query, role, full_name):
    """Live search across real data — deliberately mirrors the exact
    visibility rules each section already applies on its own, table by
    table, rather than a single generic 'search everything' query that
    would bypass them. Returns a list of (table_label, title,
    subtitle, target_section) tuples. Best-effort: a failure on any
    one table is logged and skipped rather than breaking the whole
    search for the other tables."""
    q = f"%{query.strip()}%"
    if not query.strip() or not SUPABASE_AVAILABLE:
        return []
    results = []

    try:
        res = supabase.table("tasks").select("id,title,location,assigned_to") \
            .or_(f"title.ilike.{q},location.ilike.{q}").limit(15).execute()
        rows = res.data or []
        if role.lower().strip() == "worker":  # exact same check the Task Dashboard
            # section itself uses (`if role == "worker":`) — not a capability
            # proxy, since tasks are gated by a direct role comparison, not
            # a capability in ROLE_PERMISSIONS
            rows = [r for r in rows if r.get("assigned_to") == full_name]
        for r in rows:
            results.append(("Task", r.get("title"), r.get("location"), "Task Dashboard", r.get("id")))
    except Exception as e:
        log_error(str(e), endpoint="search_records:tasks")

    try:
        res = supabase.table("incidents").select("id,incident_type,description,reported_by") \
            .or_(f"incident_type.ilike.{q},description.ilike.{q}").limit(15).execute()
        rows = res.data or []
        if not can(role, "incident.investigate"):
            rows = [r for r in rows if r.get("reported_by") == full_name]
        for r in rows:
            results.append(("Incident", r.get("incident_type"),
                           (r.get("description") or "")[:60], "Incidents", r.get("id")))
    except Exception as e:
        log_error(str(e), endpoint="search_records:incidents")

    try:
        res = supabase.table("app_feedback").select("id,title,description,submitted_by") \
            .or_(f"title.ilike.{q},description.ilike.{q}").limit(15).execute()
        rows = res.data or []
        if not can(role, "feedback.manage"):
            rows = [r for r in rows if r.get("submitted_by") == full_name]
        for r in rows:
            results.append(("Feedback", r.get("title"),
                           (r.get("description") or "")[:60], "Feedback", r.get("id")))
    except Exception as e:
        log_error(str(e), endpoint="search_records:feedback")

    try:
        res = supabase.table("assets").select("id,name,asset_tag,location") \
            .or_(f"name.ilike.{q},asset_tag.ilike.{q}").limit(15).execute()
        for r in (res.data or []):
            results.append(("Asset", r.get("name"), r.get("location"), "Assets", r.get("id")))
    except Exception as e:
        log_error(str(e), endpoint="search_records:assets")

    try:
        res = supabase.table("inventory_parts").select("id,part_name,part_number,bin_location") \
            .or_(f"part_name.ilike.{q},part_number.ilike.{q}").limit(15).execute()
        for r in (res.data or []):
            results.append(("Part", r.get("part_name"), r.get("part_number"), "Inventory", r.get("id")))
    except Exception as e:
        log_error(str(e), endpoint="search_records:inventory")

    if can(role, "contractor.view"):
        try:
            res = supabase.table("contractors").select("id,company_name,contact_person") \
                .ilike("company_name", q).limit(15).execute()
            for r in (res.data or []):
                results.append(("Contractor", r.get("company_name"), r.get("contact_person"), "Contractors", r.get("id")))
        except Exception as e:
            log_error(str(e), endpoint="search_records:contractors")

    if can(role, "permit.view"):
        try:
            res = supabase.table("permits").select("id,permit_type,lock_tag_numbers") \
                .or_(f"permit_type.ilike.{q},lock_tag_numbers.ilike.{q}").limit(15).execute()
            for r in (res.data or []):
                results.append(("Permit", r.get("permit_type"), r.get("lock_tag_numbers"), "Permits", r.get("id")))
        except Exception as e:
            log_error(str(e), endpoint="search_records:permits")

    return results


def get_cached_feature_flags(ttl_seconds=30):
    """Fetches feature flags at most once per ttl_seconds and reuses
    that result in between — Streamlit re-executes the whole script on
    almost every interaction, so with no caching at all, every single
    click would trigger a fresh database read just to decide which nav
    items to show.

    The TTL matters for a reason beyond performance: each user's
    session cache is independent, so without SOME expiry, a module the
    Owner just disabled would stay visible to everyone else until
    their individual session happened to reset on its own — which
    could be a very long time. 30 seconds keeps database load low
    while still making a toggle take effect for everyone within a
    reasonably short window, not just the person who flipped it.
    """
    cached = st.session_state.get("_feature_flags_cache")
    cached_at = st.session_state.get("_feature_flags_cache_at")
    now = datetime.now()
    if cached is not None and cached_at is not None and (now - cached_at).total_seconds() < ttl_seconds:
        return cached
    flags = fetch_feature_flags()
    st.session_state["_feature_flags_cache"] = flags
    st.session_state["_feature_flags_cache_at"] = now
    return flags


def set_feature_flag(flag_key, enabled, updated_by):
    if flag_key not in TOGGLEABLE_MODULES:
        return False
    if not SUPABASE_AVAILABLE:
        st.session_state.setdefault("feature_flags_memory", {})[flag_key] = enabled
        st.session_state.pop("_feature_flags_cache", None)
        st.session_state.pop("_feature_flags_cache_at", None)
        return True
    try:
        res = supabase.table("app_feature_flags").upsert({
            "flag_key": flag_key, "enabled": enabled, "updated_by": updated_by,
            "updated_at": datetime.now().isoformat(),
        }).execute()
        if not res.data:
            return False
        log_audit(updated_by, "feature_flag_toggle", {"flag": flag_key, "enabled": enabled})
        st.session_state.pop("_feature_flags_cache", None)  # force a fresh read next time
        st.session_state.pop("_feature_flags_cache_at", None)
        return True
    except Exception as e:
        log_error(str(e), endpoint="set_feature_flag")
        return False


# =====================================================================
# ACCESS POLICIES
# =====================================================================
# Deliberately a SEPARATE system from feature flags above, not the
# same list with more entries. Feature flags hide/show UI sections —
# turning one off is low-stakes and easily reversible. These change
# actual security behavior: who gets into the app at all, and
# whether a human ever looks at that decision. They're stored in the
# same app_feature_flags table (still just a key-value store) but
# under their own key prefix and, critically, with the OPPOSITE
# default philosophy: feature flags fail OPEN (never set = enabled,
# since an unset UI toggle should never silently vanish a working
# feature). Access policies fail CLOSED (never set = OFF, i.e.
# approval IS required) — an unset security policy should never
# silently become the more permissive option just because a read
# failed or the row doesn't exist yet.
ACCESS_POLICIES = {
    "auto_approve_registration": (
        "Auto-approve new registrations",
        "New sign-ups get immediate Worker-level access with no Owner/Superintendent "
        "review. They still can't self-grant a higher role — that part of the security "
        "design is untouched — but nobody looks at WHO is signing up before they're in. "
        "Off by default, and meant to stay off unless you have a specific reason (e.g. "
        "a closed network only your own people can reach) that makes the review step "
        "genuinely redundant for your situation."
    ),
}


def fetch_access_policies():
    """Returns {policy_key: enabled_bool}. Fails closed: anything
    never explicitly set, or any read error, resolves to False (the
    restrictive, safer behavior) — the opposite default direction
    from fetch_feature_flags() above, and deliberately so."""
    policies = {key: False for key in ACCESS_POLICIES}
    if not SUPABASE_AVAILABLE:
        policies.update(st.session_state.get("access_policies_memory", {}))
        return policies
    try:
        res = supabase.table("app_feature_flags").select("*").execute()
        for row in (res.data or []):
            if row["flag_key"] in policies:
                policies[row["flag_key"]] = row["enabled"]
    except Exception as e:
        log_error(str(e), endpoint="fetch_access_policies")
        # Fails closed here too — a read error means every policy
        # resolves to "off" (requiring approval), never silently to
        # the more permissive option.
    return policies


def set_access_policy(policy_key, enabled, updated_by):
    if policy_key not in ACCESS_POLICIES:
        return False
    if not SUPABASE_AVAILABLE:
        st.session_state.setdefault("access_policies_memory", {})[policy_key] = enabled
        return True
    try:
        res = supabase.table("app_feature_flags").upsert({
            "flag_key": policy_key, "enabled": enabled, "updated_by": updated_by,
            "updated_at": datetime.now().isoformat(),
        }).execute()
        if not res.data:
            return False
        # A distinct, clearly-named audit action from feature_flag_toggle —
        # this is the kind of change worth being able to find quickly in
        # the audit log later, not blended in with routine UI toggles.
        log_audit(updated_by, "access_policy_change", {"policy": policy_key, "enabled": enabled})
        return True
    except Exception as e:
        log_error(str(e), endpoint="set_access_policy")
        return False


def render_logo_bar():
    """A slim bar above the main header showing the company logo, if
    one is configured. Renders nothing at all when no logo is set, so
    it doesn't add empty visual clutter before anyone uploads one.

    Sticky, at the same clearance point main-header itself uses — it's
    now the topmost sticky element on screen, and this also sets
    --header-top-offset so main-header shifts down to stack beneath
    it rather than overlap at the same position. Only applied when a
    logo is actually present: with no logo bar, main-header keeps its
    default 60px offset from the base CSS rule, no override needed.
    """
    logo_url = fetch_branding()
    if not logo_url or logo_url.startswith("memory://"):
        return
    st.markdown(
        f'<style>:root {{ --header-top-offset: {60 + LOGO_BAR_HEIGHT}px; }}</style>'
        f'<div class="logo-bar"><img src="{esc(logo_url)}" alt="Company logo"></div>',
        unsafe_allow_html=True,
    )


def fetch_active_posters():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("posters_memory", [])
    try:
        res = (supabase.table("app_posters").select("*")
              .eq("is_active", True).order("display_order", desc=False).execute())
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_active_posters")
        return []


def fetch_all_posters():
    """Includes inactive ones too — for the management list."""
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("posters_memory", [])
    try:
        res = supabase.table("app_posters").select("*").order("display_order", desc=False).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_all_posters")
        return []


def upload_poster(file_bytes, filename, uploaded_by):
    """Upload a promotional poster image. Same validation and storage
    pattern as upload_logo — public 'posters' bucket, since these are
    marketing material, not sensitive data."""
    valid, msg = validate_image(file_bytes, filename)
    if not valid:
        st.error(msg)
        return False
    if not SUPABASE_AVAILABLE:
        rows = st.session_state.setdefault("posters_memory", [])
        rows.append({"id": max([r.get("id", 0) for r in rows], default=0) + 1,
                    "image_url": f"memory://{filename}", "is_active": True,
                    "display_order": len(rows)})
        return True
    try:
        ext = filename.split(".")[-1].lower()
        safe_name = f"poster_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(file_bytes).hexdigest()[:8]}.{ext}"
        storage_res = supabase.storage.from_("posters").upload(safe_name, file_bytes)
        if not storage_res:
            log_error("Storage upload returned a falsy result", endpoint="upload_poster")
            return False
        public_url = supabase.storage.from_("posters").get_public_url(safe_name)
        existing = fetch_all_posters()
        next_order = max([p.get("display_order", 0) for p in existing], default=-1) + 1
        res = supabase.table("app_posters").insert({
            "image_url": public_url, "uploaded_by": uploaded_by,
            "display_order": next_order,
        }).execute()
        if not res.data:
            log_error("app_posters insert affected 0 rows — likely RLS blocking writes. "
                     "The file reached Storage but has no metadata row.",
                     endpoint="upload_poster")
            return False
        log_audit(uploaded_by, "poster_upload", {"url": public_url})
        return True
    except Exception as e:
        log_error(str(e), endpoint="upload_poster")
        return False


def set_poster_active(poster_id, active, updated_by):
    if not SUPABASE_AVAILABLE:
        for r in st.session_state.get("posters_memory", []):
            if r["id"] == poster_id:
                r["is_active"] = active
        return True
    try:
        res = supabase.table("app_posters").update({"is_active": active}).eq("id", poster_id).execute()
        if not res.data:
            return False
        log_audit(updated_by, "poster_toggle", {"id": poster_id, "active": active})
        return True
    except Exception as e:
        log_error(str(e), endpoint="set_poster_active")
        return False


def delete_poster(poster_id, deleted_by):
    if not SUPABASE_AVAILABLE:
        st.session_state["posters_memory"] = [
            r for r in st.session_state.get("posters_memory", []) if r["id"] != poster_id]
        return True
    try:
        res = supabase.table("app_posters").delete().eq("id", poster_id).execute()
        if not res.data:
            return False
        log_audit(deleted_by, "poster_delete", {"id": poster_id})
        return True
    except Exception as e:
        log_error(str(e), endpoint="delete_poster")
        return False


def render_poster_slideshow(seconds_per_slide=5):
    """Auto-advancing crossfade slideshow, no JavaScript — pure CSS,
    same reliability reasoning as everything else built this session
    (no external dependency that can fail to load). Renders nothing
    when there are 0 or 1 active posters (a single image needs no
    slideshow machinery at all — just show it).

    The crossfade timing is DYNAMICALLY GENERATED per render rather
    than a fixed set of keyframes, because the percentage breakpoints
    for a smooth N-image cycle depend on how many images there
    actually are — this can't be hardcoded in the CSS body the way
    the ticker's fixed two-keyframe animation could.

    Scrolls normally with the page — see render_logo_bar for why this
    is no longer fixed to the viewport.
    """
    posters = fetch_active_posters()
    posters = [p for p in posters if p.get("image_url") and not p["image_url"].startswith("memory://")]
    if len(posters) == 0:
        return
    if len(posters) == 1:
        st.markdown(
            f'<div class="poster-slideshow"><img class="poster-slide poster-slide-solo" '
            f'src="{esc(posters[0]["image_url"])}" alt="Poster"></div>',
            unsafe_allow_html=True,
        )
        return

    n = len(posters)
    cycle_seconds = seconds_per_slide * n
    # Each slide gets an equal-length slot: visible for most of its
    # slot, with a short crossfade into the next at the boundary.
    slot_pct = 100 / n
    fade_pct = min(slot_pct * 0.15, 4)  # crossfade duration, capped so it never eats a whole slot

    style_parts = [f'<style>.poster-slide{{opacity:0;animation:{cycle_seconds}s linear infinite;}}']
    imgs = []
    for i, p in enumerate(posters):
        start_pct = i * slot_pct
        end_pct = start_pct + slot_pct
        kf_name = f"poster-fade-{i}"
        if i == 0:
            # Slide 0's fade-IN happens at the END of the cycle
            # (wrapping to its start at 0%), not partway through —
            # it must already be opacity 1 AT 0% for the loop restart
            # to be seamless, fade out at its own end like any other
            # slide, then fade back in during the cycle's final
            # stretch so it's ready for the next loop. Verified by
            # simulating rendered opacity at every point in the cycle
            # before shipping — a naive version of this (no fade-in
            # keyframe at the wraparound point) left slide 0 popping
            # into view abruptly instead of fading like every other
            # slide does at its own start.
            pts = [(0, 1), (end_pct - fade_pct, 1), (end_pct, 0),
                  (100 - fade_pct, 0), (100, 1)]
        else:
            pts = [(start_pct - fade_pct, 0), (start_pct, 1), (end_pct - fade_pct, 1),
                  (end_pct if i < n - 1 else 100, 0)]
        kf_body = "".join(f"{pct:.2f}%{{opacity:{op}}}" for pct, op in pts)
        style_parts.append(f'@keyframes {kf_name}{{{kf_body}}}')
        style_parts.append(f'.poster-slide-{i}{{animation-name:{kf_name};animation-duration:{cycle_seconds}s;}}')
        imgs.append(f'<img class="poster-slide poster-slide-{i}" src="{esc(p["image_url"])}" alt="Poster {i+1}">')
    style_parts.append('@media (prefers-reduced-motion:reduce){.poster-slide{animation:none!important;opacity:1!important;}}')
    style_parts.append('</style>')

    st.markdown(
        "".join(style_parts) + f'<div class="poster-slideshow">{"".join(imgs)}</div>',
        unsafe_allow_html=True,
    )


def fetch_active_announcements():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("announcements_memory", [])
    try:
        res = (supabase.table("app_announcements").select("*")
              .eq("is_active", True).order("id", desc=False).execute())
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_active_announcements")
        return []


def fetch_all_announcements():
    """Includes inactive ones too — for the management list, so an
    admin can see and reactivate something they turned off earlier."""
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("announcements_memory", [])
    try:
        res = supabase.table("app_announcements").select("*").order("id", desc=True).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_all_announcements")
        return []


def create_announcement(message, created_by):
    if not message or not message.strip():
        return False, "Message can't be empty."
    if not SUPABASE_AVAILABLE:
        rows = st.session_state.setdefault("announcements_memory", [])
        rows.append({"id": max([r.get("id", 0) for r in rows], default=0) + 1,
                    "message": message.strip(), "is_active": True})
        return True, ""
    try:
        res = supabase.table("app_announcements").insert({
            "message": message.strip(), "is_active": True, "created_by": created_by,
        }).execute()
        if not res.data:
            return False, ("Saved but nothing was created — Row Level Security is likely "
                          "blocking writes to app_announcements. Run schema_additions.sql Phase 11.")
        log_audit(created_by, "announcement_create", {"message": message.strip()[:80]})
        return True, ""
    except Exception as e:
        log_error(str(e), endpoint="create_announcement")
        return False, str(e)


def set_announcement_active(announcement_id, active, updated_by):
    if not SUPABASE_AVAILABLE:
        for r in st.session_state.get("announcements_memory", []):
            if r["id"] == announcement_id:
                r["is_active"] = active
        return True
    try:
        res = (supabase.table("app_announcements").update({"is_active": active})
              .eq("id", announcement_id).execute())
        if not res.data:
            return False
        log_audit(updated_by, "announcement_toggle", {"id": announcement_id, "active": active})
        return True
    except Exception as e:
        log_error(str(e), endpoint="set_announcement_active")
        return False


def delete_announcement(announcement_id, deleted_by):
    if not SUPABASE_AVAILABLE:
        st.session_state["announcements_memory"] = [
            r for r in st.session_state.get("announcements_memory", []) if r["id"] != announcement_id]
        return True
    try:
        res = supabase.table("app_announcements").delete().eq("id", announcement_id).execute()
        if not res.data:
            return False
        log_audit(deleted_by, "announcement_delete", {"id": announcement_id})
        return True
    except Exception as e:
        log_error(str(e), endpoint="delete_announcement")
        return False


def render_ticker_bar():
    """Continuously scrolling announcement strip between the logo bar
    and the main header. Multiple active announcements join into one
    line separated by a bullet, so they scroll as a single strip
    rather than needing separate rotation logic. Renders nothing when
    there are no active announcements, same convention as the logo bar.

    Scrolls normally with the page — see render_logo_bar for why this
    is no longer fixed to the viewport.
    """
    items = fetch_active_announcements()
    if not items:
        return
    joined = "   •   ".join(esc(i["message"]) for i in items if i.get("message"))
    if not joined:
        return
    st.markdown(
        f'<div class="ticker-bar"><div class="ticker-content">{joined}</div></div>',
        unsafe_allow_html=True,
    )


def fetch_all_feedback():
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("feedback_memory", [])
    try:
        res = supabase.table("app_feedback").select("*").order("id", desc=True).execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_all_feedback")
        return st.session_state.get("feedback_memory", [])


def fetch_all_feedback_votes():
    """All votes, fetched once and aggregated in Python — consistent
    with how the rest of this app joins related tables (task_parts,
    meter_readings, etc.) rather than relying on PostgREST joins."""
    if not SUPABASE_AVAILABLE:
        return st.session_state.get("feedback_votes_memory", [])
    try:
        res = supabase.table("app_feedback_votes").select("*").execute()
        return res.data or []
    except Exception as e:
        log_error(str(e), endpoint="fetch_all_feedback_votes")
        return st.session_state.get("feedback_votes_memory", [])


def submit_feedback(title, description, category, submitted_by):
    if not title or not title.strip():
        return False, "Title is required.", None
    payload = {
        "submitted_by": submitted_by,
        "title": title.strip(),
        "description": description,
        "category": category,
        "status": "New",
    }
    if not SUPABASE_AVAILABLE:
        rows = st.session_state.setdefault("feedback_memory", [])
        payload["id"] = max([r.get("id", 0) for r in rows], default=0) + 1
        payload["created_at"] = datetime.now().isoformat()
        rows.append(payload)
        log_audit(submitted_by, "feedback_submit_memory", {"title": title})
        return True, "", payload
    try:
        res = supabase.table("app_feedback").insert(payload).execute()
        if not res.data:
            return False, ("Submitted but nothing was saved — Row Level Security is likely "
                          "blocking writes to app_feedback. Run schema_additions.sql Phase 8."), None
        log_audit(submitted_by, "feedback_submit", {"title": title})
        return True, "", res.data[0]
    except Exception as e:
        log_error(str(e), details={"title": title}, endpoint="submit_feedback")
        return False, str(e), None


def toggle_feedback_vote(feedback_id, voted_by, currently_voted):
    """Adds or removes this person's vote. The UNIQUE(feedback_id,
    voted_by) constraint is what actually prevents double-voting, even
    under a race — this function just decides which direction to go
    based on what the UI already knows about the current state."""
    if not SUPABASE_AVAILABLE:
        votes = st.session_state.setdefault("feedback_votes_memory", [])
        if currently_voted:
            st.session_state.feedback_votes_memory = [
                v for v in votes if not (v["feedback_id"] == feedback_id and v["voted_by"] == voted_by)]
        else:
            votes.append({"feedback_id": feedback_id, "voted_by": voted_by,
                         "created_at": datetime.now().isoformat()})
        return True
    try:
        if currently_voted:
            res = (supabase.table("app_feedback_votes").delete()
                  .eq("feedback_id", feedback_id).eq("voted_by", voted_by).execute())
            return bool(res.data)
        else:
            res = (supabase.table("app_feedback_votes")
                  .insert({"feedback_id": feedback_id, "voted_by": voted_by}).execute())
            return bool(res.data)
    except Exception as e:
        # A 409/unique-violation here means a duplicate vote attempt —
        # not a real failure worth alarming over, just log it quietly.
        log_error(str(e), details={"feedback_id": feedback_id, "voted_by": voted_by},
                 endpoint="toggle_feedback_vote")
        return False


def update_feedback_status(feedback_id, status, admin_response, responded_by):
    updates = {
        "status": status,
        "admin_response": admin_response,
        "responded_by": responded_by,
        "responded_at": datetime.now().isoformat(),
    }
    if not SUPABASE_AVAILABLE:
        for f in st.session_state.get("feedback_memory", []):
            if f["id"] == feedback_id:
                f.update(updates)
                return True
        return False
    try:
        res = supabase.table("app_feedback").update(updates).eq("id", feedback_id).execute()
        if not res.data:
            return False
        log_audit(responded_by, "feedback_status_change", {"feedback_id": feedback_id, "status": status})
        return True
    except Exception as e:
        log_error(str(e), details={"feedback_id": feedback_id}, endpoint="update_feedback_status")
        return False



def compute_mttr_hours_v2(tasks):
    """Mean Time To Repair using REAL timestamps.

    Measures failure_start (or created_at) -> completed_at. Returns
    (hours, sample_size) so the UI can show how much data backs the
    number instead of presenting a confident figure from 2 tasks.
    """
    durations = []
    for t in tasks:
        if t.get("status") != "Complete":
            continue
        end = _parse_dt(t.get("completed_at"))
        start = _parse_dt(t.get("failure_start")) or _parse_dt(t.get("created_at"))
        if not end or not start:
            continue
        hours = (end - start).total_seconds() / 3600.0
        if hours >= 0:
            durations.append(hours)
    if not durations:
        return None, 0
    return sum(durations) / len(durations), len(durations)

def get_predictive_failure_alerts(tasks, assets, threshold_pct=0.8):
    """Assets approaching their typical failure window, based on
    historical MTBF (mean time between failures) — reuses
    compute_mtbf_hours() rather than a separate calculation, so this
    stays consistent with the same MTBF already shown elsewhere in
    Analytics rather than risking two numbers disagreeing.

    For each asset with enough failure history: find the average gap
    between past failures (MTBF) and the time since its most recent
    failure. If that elapsed time has reached threshold_pct of the
    MTBF, the asset is "approaching" its typical failure window —
    the whole point being to flag it BEFORE the failure, not after.

    Requires at least 3 failures per asset (2 gaps), not 2 — a
    single gap is one data point with zero information about whether
    it's typical or a fluke; two gaps is the minimum for an actual
    average to mean anything.

    Returns a list of dicts, worst (soonest relative to their own
    typical window) first, each with asset_id, asset_name, mtbf_hours,
    hours_since_last_failure, pct_of_window, and num_failures.
    """
    now = datetime.now()
    asset_lookup = {a['id']: a for a in assets}
    alerts = []

    # Group failures by asset first, so MTBF and "most recent failure"
    # both come from the exact same underlying data — computing them
    # via two separate passes over `tasks` risked one seeing a task
    # the other didn't (e.g. a task inserted between the two passes).
    failures_by_asset = {}
    for t2 in tasks:
        if t2.get("work_type") and t2["work_type"] != "Reactive":
            continue
        aid = t2.get("asset_id")
        if aid is None:
            continue
        ts = _parse_dt(t2.get("failure_start")) or _parse_dt(t2.get("created_at"))
        if ts:
            failures_by_asset.setdefault(aid, []).append(ts)

    for asset_id, timestamps in failures_by_asset.items():
        if len(timestamps) < 3:
            continue
        timestamps.sort()
        gaps = [(timestamps[i] - timestamps[i - 1]).total_seconds() / 3600.0
               for i in range(1, len(timestamps)) if (timestamps[i] - timestamps[i - 1]).total_seconds() > 0]
        if not gaps:
            continue
        mtbf_hours = sum(gaps) / len(gaps)
        if mtbf_hours <= 0:
            continue
        hours_since_last = (now - timestamps[-1]).total_seconds() / 3600.0
        pct_of_window = hours_since_last / mtbf_hours
        if pct_of_window >= threshold_pct:
            asset = asset_lookup.get(asset_id, {})
            alerts.append({
                "asset_id": asset_id,
                "asset_name": asset.get("name", f"Asset #{asset_id}"),
                "mtbf_hours": mtbf_hours,
                "hours_since_last_failure": hours_since_last,
                "pct_of_window": pct_of_window,
                "num_failures": len(timestamps),
            })

    alerts.sort(key=lambda a: a["pct_of_window"], reverse=True)
    return alerts


def compute_mtbf_hours(tasks, asset_id=None):
    """Mean Time Between Failures for reactive/breakdown work.

    Uses the gaps between consecutive failures on an asset. Needs at
    least two failures on the same asset to mean anything.
    """
    failures = []
    for t in tasks:
        if t.get("work_type") and t["work_type"] != "Reactive":
            continue
        if asset_id is not None and t.get("asset_id") != asset_id:
            continue
        ts = _parse_dt(t.get("failure_start")) or _parse_dt(t.get("created_at"))
        if ts:
            failures.append((t.get("asset_id"), ts))
    by_asset = {}
    for aid, ts in failures:
        by_asset.setdefault(aid, []).append(ts)
    gaps = []
    for aid, times in by_asset.items():
        times.sort()
        for i in range(1, len(times)):
            gap = (times[i] - times[i - 1]).total_seconds() / 3600.0
            if gap > 0:
                gaps.append(gap)
    if not gaps:
        return None, 0
    return sum(gaps) / len(gaps), len(gaps)

def compute_pm_compliance_v2(tasks):
    """PM compliance = PM tasks completed on or before due date / all
    PM tasks that have come due. Unlike the earlier version this
    actually checks the completion date against the due date."""
    due_pm = []
    now = datetime.now()
    for t in tasks:
        if not t.get("is_recurring"):
            continue
        due = _parse_dt(t.get("due_date"))
        if due and due <= now:
            due_pm.append(t)
    if not due_pm:
        return None, 0
    on_time = 0
    for t in due_pm:
        completed = _parse_dt(t.get("completed_at"))
        due = _parse_dt(t.get("due_date"))
        if completed and due and completed <= due:
            on_time += 1
    return round((on_time / len(due_pm)) * 100, 1), len(due_pm)

def planned_vs_reactive(tasks):
    """The benchmark most maintenance organisations are measured on.
    World class is generally cited as ~80% planned / 20% reactive."""
    planned = sum(1 for t in tasks if t.get("work_type") in ("Preventive", "Planned", "Predictive") or t.get("is_recurring"))
    reactive = sum(1 for t in tasks if not (t.get("work_type") in ("Preventive", "Planned", "Predictive") or t.get("is_recurring")))
    total = planned + reactive
    if total == 0:
        return None, None, 0
    return round(planned / total * 100, 1), round(reactive / total * 100, 1), total

def backlog_aging(tasks):
    """Buckets open work by age — the standard backlog health view."""
    buckets = {"0-7 days": 0, "8-30 days": 0, "31-90 days": 0, "90+ days": 0}
    now = datetime.now()
    for t in tasks:
        if t.get("status") in ("Complete",):
            continue
        created = _parse_dt(t.get("created_at"))
        if not created:
            continue
        age = (now - created).days
        if age <= 7:
            buckets["0-7 days"] += 1
        elif age <= 30:
            buckets["8-30 days"] += 1
        elif age <= 90:
            buckets["31-90 days"] += 1
        else:
            buckets["90+ days"] += 1
    return buckets

def failure_pareto(tasks):
    """Failure counts by code, descending — drives root-cause effort."""
    counts = {}
    for t in tasks:
        code = t.get("failure_code")
        if code:
            counts[code] = counts.get(code, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return [(FAILURE_CODES.get(c, c), c, n) for c, n in ranked]

def safety_leading_indicators(incidents, tasks):
    """Leading (not just lagging) safety metrics.

    Near-miss reporting rate is a LEADING indicator: a rising rate
    usually means better reporting culture, not a less safe site.
    Read it alongside the overdue-corrective-action count.
    """
    total = len(incidents)
    near_misses = sum(1 for i in incidents if i.get("incident_type") == "Near Miss")
    hazard_obs = sum(1 for i in incidents if i.get("incident_type") == "Hazard Observation")
    injuries = sum(1 for i in incidents if i.get("incident_type") == "Injury")
    open_actions = sum(1 for i in incidents
                       if i.get("status") in ("Open", "Investigating")
                       and not (i.get("corrective_action") or "").strip())
    thirty_days_ago = datetime.now() - timedelta(days=30)
    recent = [i for i in incidents if (_parse_dt(i.get("created_at")) or datetime.min) >= thirty_days_ago]
    return {
        "total_incidents": total,
        "near_misses": near_misses,
        "hazard_observations": hazard_obs,
        "injuries": injuries,
        "proactive_reports": near_misses + hazard_obs,
        "open_without_action": open_actions,
        "last_30_days": len(recent),
        "near_miss_ratio": round(near_misses / total * 100, 1) if total else None,
    }


def compute_hours_worked(start_date, end_date):
    """Total hours actually worked in a date range, from Crew Clock
    punch records — the same underlying data Auto-Costing (Crew Clock)
    already uses, so this can't disagree with what that feature counts
    as a shift. Excludes still-open punches (the OPEN_SHIFT_SENTINEL
    far-future date would otherwise make an open shift look like it
    lasted thousands of hours).
    """
    if not SUPABASE_AVAILABLE:
        return 0.0
    try:
        res = supabase.table("shift_rosters").select("shift_start,shift_end") \
            .eq("crew_name", "Clock") \
            .neq("shift_end", "9999-12-31 23:59:59") \
            .gte("shift_start", start_date.isoformat()) \
            .lte("shift_start", end_date.isoformat()) \
            .execute()
        total = 0.0
        for r in (res.data or []):
            s = _parse_dt(r.get("shift_start"))
            e = _parse_dt(r.get("shift_end"))
            if s and e and e > s:
                total += (e - s).total_seconds() / 3600.0
        return total
    except Exception as e:
        log_error(str(e), endpoint="compute_hours_worked")
        return 0.0


def compute_trifr(incidents, total_hours_worked):
    """Total Recordable Injury Frequency Rate — the standard safety
    industry formula: (recordable injuries × 1,000,000) / hours worked.
    Returns None (not 0) when there's no hours data, since a TRIFR of
    0 asserts "zero injury rate," which is a very different claim from
    "we don't have enough data to compute a rate at all."
    """
    if not total_hours_worked or total_hours_worked <= 0:
        return None
    recordable = sum(1 for i in incidents if i.get("incident_type") == "Injury")
    return round((recordable * 1_000_000) / total_hours_worked, 2)


def compute_monthly_production_vs_target(month_start=None):
    """Ore production this month against KPI_MONTHLY_PRODUCTION_TONNES —
    extracted from the inline calculation already used in Analytics'
    KPI Targets section, so the Executive Report and the on-screen
    metric can't drift apart into two different numbers for the same
    thing. Ore-only, matching that same established convention
    (ore and waste rock are never summed together elsewhere in this app).
    """
    if not month_start:
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    records = fetch_production_records(limit=2000)
    ore_this_month = sum(
        r.get("quantity") or 0 for r in records
        if "ore" in (r.get("material_type") or "").lower()
        and (_parse_dt(r.get("production_date")) or datetime.min) >= month_start
    )
    pct = (ore_this_month / KPI_MONTHLY_PRODUCTION_TONNES * 100) if KPI_MONTHLY_PRODUCTION_TONNES else None
    return ore_this_month, KPI_MONTHLY_PRODUCTION_TONNES, pct


def top_cost_drivers(assets, tasks, parts_lookup, top_n=5):
    """Ranks assets by actual spend (parts + labour), reusing
    actual_spend_for_asset() per asset rather than a separate cost
    calculation — the same function already driving the Cost tab and
    Budget Center, so this ranking can't disagree with those numbers.
    """
    ranked = []
    for a in assets:
        spend = actual_spend_for_asset(a["id"], tasks, parts_lookup)
        if spend and spend > 0:
            ranked.append({"asset_id": a["id"], "asset_name": a.get("name", f"Asset #{a['id']}"), "spend": spend})
    ranked.sort(key=lambda x: x["spend"], reverse=True)
    return ranked[:top_n]


# -------------------------------
# 21. SESSION STATE INIT
# -------------------------------
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_payload' not in st.session_state:
    st.session_state.user_payload = None
if 'chat_room' not in st.session_state:
    st.session_state.chat_room = "global"
if 'chat_partner' not in st.session_state:
    st.session_state.chat_partner = None
if 'broadcast_messages' not in st.session_state:
    st.session_state.broadcast_messages = []
if 'tasks_memory' not in st.session_state:
    st.session_state.tasks_memory = []
if 'chat_messages_memory' not in st.session_state:
    st.session_state.chat_messages_memory = []
if 'chat_input_value' not in st.session_state:
    st.session_state.chat_input_value = ""
if 'photos_memory' not in st.session_state:
    st.session_state.photos_memory = []
if 'last_activity' not in st.session_state:
    st.session_state.last_activity = datetime.now()
if 'chat_channel' not in st.session_state:
    st.session_state.chat_channel = None
if 'chat_messages_cache' not in st.session_state:
    st.session_state.chat_messages_cache = []
if 'attachments_memory' not in st.session_state:
    st.session_state.attachments_memory = []
if 'comments_memory' not in st.session_state:
    st.session_state.comments_memory = []
if 'activity_memory' not in st.session_state:
    st.session_state.activity_memory = []
if 'notifications_cache' not in st.session_state:
    st.session_state.notifications_cache = []
if 'oauth_token' not in st.session_state:
    st.session_state.oauth_token = None
if 'assets_memory' not in st.session_state:
    st.session_state.assets_memory = []
if 'inventory_memory' not in st.session_state:
    st.session_state.inventory_memory = []
if 'incidents_memory' not in st.session_state:
    st.session_state.incidents_memory = []
if 'task_parts_memory' not in st.session_state:
    st.session_state.task_parts_memory = []
if 'permits_memory' not in st.session_state:
    st.session_state.permits_memory = []
if 'handovers_memory' not in st.session_state:
    st.session_state.handovers_memory = []
if 'contractors_memory' not in st.session_state:
    st.session_state.contractors_memory = []
if 'meter_readings_memory' not in st.session_state:
    st.session_state.meter_readings_memory = []
if 'feedback_memory' not in st.session_state:
    st.session_state.feedback_memory = []
if 'feedback_votes_memory' not in st.session_state:
    st.session_state.feedback_votes_memory = []
if 'branding_logo_url' not in st.session_state:
    st.session_state.branding_logo_url = None
if 'announcements_memory' not in st.session_state:
    st.session_state.announcements_memory = []
if 'posters_memory' not in st.session_state:
    st.session_state.posters_memory = []
if 'feature_flags_memory' not in st.session_state:
    st.session_state.feature_flags_memory = {}
if 'user_language' not in st.session_state:
    st.session_state.user_language = "en"

# -------------------------------
# 22. SESSION TIMEOUT CHECK
# -------------------------------
def check_timeout():
    if st.session_state.authenticated:
        if datetime.now() - st.session_state.last_activity > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
            _timeout_token = st.query_params.get("session")
            if _timeout_token:
                invalidate_session_token(_timeout_token)
                del st.query_params["session"]
            st.session_state.authenticated = False
            st.session_state.user_payload = None
            st.warning("Session expired due to inactivity. Please log in again.")
            st.rerun()
        else:
            st.session_state.last_activity = datetime.now()

# -------------------------------
# 23. OAUTH LOGIN (Google) - placeholder
# -------------------------------
def google_oauth():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        st.error("Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in secrets.")
        return None
    st.info("OAuth login is available but requires setup of a callback endpoint. Please use the regular login for now.")
    return None

# -------------------------------
# 24. AUTHENTICATION GATEWAY
# -------------------------------
# Restores login from a session token in the URL, if present — this
# is what lets a hard refresh (which genuinely resets session_state,
# a Streamlit platform limitation, not a bug in this app) skip
# straight back to where the person was instead of dropping them to
# the login screen. Guarded to run once per fresh session so it
# doesn't re-hit the database on every single rerun afterward.
if not st.session_state.authenticated and not st.session_state.get("_session_token_checked"):
    st.session_state["_session_token_checked"] = True
    _restore_token = st.query_params.get("session")
    if _restore_token:
        _restored_username = validate_session_token(_restore_token)
        if _restored_username:
            try:
                _restored_users = fetch_all_users_from_db()
                _restored_user = next((u for u in _restored_users if u.get("username") == _restored_username), None)
            except Exception as e:
                log_error(str(e), endpoint="session_token_restore")
                _restored_user = None
            if _restored_user and _restored_user.get("is_approved") and not _restored_user.get("is_suspended", False):
                # Mirrors the exact fields the normal login success path
                # sets, so a token-restored session is indistinguishable
                # from a freshly-logged-in one to the rest of the app.
                st.session_state.user_payload = {
                    "name": _restored_user.get("full_name", _restored_user.get("username")),
                    "role": _restored_user.get("role", "Worker"),
                    "username": _restored_user.get("username"),
                    "email": _restored_user.get("email", None),
                    "avatar_url": _restored_user.get("avatar_url", None),
                    "must_change_password": _restored_user.get("must_change_password", False),
                }
                st.session_state["user_language"] = _restored_user.get("preferred_language") or "en"
                st.session_state["_show_welcome"] = False  # already seen it in the original session
                st.session_state.authenticated = True
                st.session_state.last_activity = datetime.now()
            else:
                # A token that no longer maps to a valid, approved,
                # non-suspended account — clear it from the URL rather
                # than leave a dead token sitting there indefinitely.
                del st.query_params["session"]
        else:
            del st.query_params["session"]

if "_pre_login_welcome_dismissed" not in st.session_state:
    st.session_state["_pre_login_welcome_dismissed"] = False

if not st.session_state.authenticated and not st.session_state["_pre_login_welcome_dismissed"]:
    # Wrapped defensively — this is the very first thing every user
    # sees, so it must never be able to crash or loop. Any exception
    # anywhere in its render (a bad fetch, a malformed value, anything
    # unforeseen) now skips straight to the login form — the simpler,
    # already-proven-stable path — rather than risk repeating the
    # crash-and-Cloud-auto-restart cycle that caused the earlier
    # continuous-reload issue.
    try:
        render_logo_bar()
        st.markdown('''
        <div class="landing-hero">
            <i class="fas fa-hard-hat landing-icon"></i>
            <h1>Mine & Workshop Digital Tracker</h1>
            <p>Replacing paper task boards, incident report books, and permit logs with one
            system — tasks, permits, incidents, and shift handovers, all in one place,
            accessible from your phone.</p>
        </div>
        ''', unsafe_allow_html=True)

        st.markdown("#### What's inside")
        _landing_features = [
            ("fa-clipboard-list", "Task & Maintenance Tracking",
            "Dispatch work tickets, track repairs, and keep a full maintenance history per asset."),
            ("fa-shield-heart", "Safety & Incident Reporting",
            "Log hazards and near-misses from the field, with permit-to-work and JSA tracking built in."),
            ("fa-chart-line", "Production & Analytics",
            "Real reliability metrics, cost tracking, and an executive dashboard leadership can trust."),
            ("fa-language", "Built for the Whole Crew",
            "Available in English, French, Spanish, Portuguese, Chinese, and Hindi."),
        ]
        _lcol1, _lcol2 = st.columns(2)
        for _i, (_icon, _title, _desc) in enumerate(_landing_features):
            with (_lcol1 if _i % 2 == 0 else _lcol2):
                st.markdown(f'''
                <div class="landing-feature-card">
                    <i class="fas {_icon} landing-feature-icon"></i>
                    <h4>{esc(_title)}</h4>
                    <p>{esc(_desc)}</p>
                </div>
                ''', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### Get Started")
        st.caption("Choose your role to continue to login — same login form either way, this "
                  "just points you in the right direction.")
        _role_cards = [
            {"icon": "fa-helmet-safety", "title": "Worker", "desc": "Field tasks & incident reporting", "tone": "info"},
            {"icon": "fa-user-gear", "title": "Supervisor", "desc": "Crew, tasks & shift handovers", "tone": "ok"},
            {"icon": "fa-shield-halved", "title": "Superintendent", "desc": "Site oversight & analytics", "tone": "warn"},
        ]
        _rcol1, _rcol2, _rcol3 = st.columns(3)
        for _rcol, _rcard in zip([_rcol1, _rcol2, _rcol3], _role_cards):
            with _rcol:
                st.markdown(render_action_cards([_rcard]), unsafe_allow_html=True)
                if st.button(f"Continue as {_rcard['title']}", key=f"_role_landing_{_rcard['title']}",
                            use_container_width=True):
                    st.session_state["_pre_login_welcome_dismissed"] = True
                    st.rerun()

        # Deliberately NOT given the same card treatment as the three
        # above — this isn't a security boundary (the real check happens
        # at login, same as every other role), just not something to
        # visually advertise alongside the three main roles.
        st.markdown('<div style="text-align:center; margin-top:0.8rem;">', unsafe_allow_html=True)
        if st.button("Admin", key="_admin_landing_link", type="tertiary"):
            st.session_state["_pre_login_welcome_dismissed"] = True
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    except Exception as e:
        log_error(str(e), endpoint="landing_page_render")
        st.session_state["_pre_login_welcome_dismissed"] = True
        st.rerun()

elif not st.session_state.authenticated:
    render_logo_bar()
    render_poster_slideshow()
    render_ticker_bar()
    st.markdown('''
    <div class="main-header">
        <i class="fas fa-hard-hat"></i> Mine & Workshop Digital Tracker
        <small>Smart Maintenance Management System</small>
    </div>
    ''', unsafe_allow_html=True)
    st.markdown('<div class="main-header-spacer"></div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header"><i class="fas fa-shield-alt"></i> Secure Login Gateway</div>', unsafe_allow_html=True)

    # --- Owner not configured -------------------------------------------
    if SUPABASE_AVAILABLE and not owner_is_configured():
        st.error(
            "⚠️ **No owner configured.** Add `OWNER_USERNAME = \"your-username\"` to "
            "`.streamlit/secrets.toml` and restart. Until then the Owner Console is "
            "unreachable and nobody can approve access requests."
        )

    # --- Demo mode notice -------------------------------------------------
    if not SUPABASE_AVAILABLE:
        st.info(
            "**Demo mode — no database connected.** Nothing you enter will be saved. "
            "Sign in with `superintendent1` / `boss000`, `supervisor1` / `super789`, "
            "or `worker1` / `worker123`. These accounts exist ONLY in demo mode and "
            "disappear automatically once Supabase is connected."
        )

    # --- First-run administrator bootstrap --------------------------------
    # Without this, connecting a fresh database would leave nobody able to
    # log in: the demo accounts are gone, and self-registration requires an
    # existing Superintendent to approve it.
    elif not has_any_admin():
        st.warning("**First-run setup.** The database has no administrator yet. "
                   "Create one now — this form disappears permanently once an "
                   "administrator exists.")
        with st.form("bootstrap_admin", clear_on_submit=True):
            st.markdown("#### Create the first Superintendent account")
            _bs_user = st.text_input("Username", placeholder="e.g. amoses").strip().lower()
            _bs_name = st.text_input("Full Name", placeholder="Your full name")
            _bs_email = st.text_input("Email (optional)")
            _bs_p1 = st.text_input("Password", type="password")
            _bs_p2 = st.text_input("Confirm Password", type="password")
            _bs_go = st.form_submit_button("🚀 Create Administrator", use_container_width=True)
            if _bs_go:
                if not (_bs_user and _bs_name and _bs_p1):
                    st.error("Username, full name, and password are required.")
                elif _bs_p1 != _bs_p2:
                    st.error("Passwords do not match.")
                else:
                    _ok, _err = create_first_admin(_bs_user, _bs_name, _bs_p1, _bs_email or None)
                    if _ok:
                        st.success("Administrator created. You can now log in below.")
                        st.rerun()
                    else:
                        st.error(_err)
        st.markdown("---")

    # Check for reset token
    reset_token = st.query_params.get("reset_token")
    if reset_token:
        users = fetch_all_users_from_db()
        found = False
        for u in users:
            if u.get("password_reset_token") == reset_token:
                # Same timezone-safe parser as everywhere else in this
                # file — a raw datetime.fromisoformat() here crashed the
                # UNAUTHENTICATED login page (no surrounding try/except)
                # for anyone whose reset_token_expiry came back with a
                # UTC offset. A broken password-reset link is worse than
                # most instances of this bug since there's no other path
                # back into the app for that user.
                expiry = _parse_dt(u.get("reset_token_expiry")) or datetime.now()
                if expiry > datetime.now():
                    with st.form("reset_password_form", clear_on_submit=True):
                        st.markdown("### Reset Your Password")
                        new_pass = st.text_input("New Password", type="password")
                        if st.form_submit_button("Reset Password"):
                            strong, msg = is_strong_password(new_pass)
                            if strong:
                                hashed = hash_password(new_pass)
                                if update_user_profile(u["username"], {
                                    "password_hash": hashed,
                                    "password_reset_token": None,
                                    "reset_token_expiry": None
                                }):
                                    st.success("Password updated! Please log in.")
                                    st.query_params.clear()
                                    st.rerun()
                                else:
                                    st.error("Failed to update password.")
                            else:
                                st.error(msg)
                else:
                    st.error("Reset link expired.")
                found = True
                break
        if not found:
            st.error("Invalid reset token.")

    # Normal login form
    with st.form("login_form", clear_on_submit=True):
        user_in = st.text_input("Username", placeholder="Enter your username").strip().lower()
        pass_in = st.text_input("Password", type="password", placeholder="Enter your password")
        login_submitted = st.form_submit_button('🔐 Authenticate Profile', use_container_width=True)

    if login_submitted:
        locked, seconds_left = is_login_locked(user_in)
        if locked:
            mins = max(1, seconds_left // 60)
            st.error(f"🔒 Too many failed attempts. This account is locked for about {mins} more minute(s).")
        else:
            matched_user, status = authenticate_user(user_in, pass_in)
            if matched_user:
                clear_login_failures(user_in)
                st.session_state.user_payload = {
                    "name": matched_user.get("full_name", matched_user.get("username")),
                    "role": matched_user.get("role", "Worker"),
                    "username": matched_user.get("username"),
                    "email": matched_user.get("email", None),
                    "avatar_url": matched_user.get("avatar_url", None),
                    "must_change_password": matched_user.get("must_change_password", False),
                }
                # Restores their saved language choice — without this,
                # switching languages in Profile would only last for
                # that one session, defeating the point of persisting
                # it to the database at all.
                st.session_state["user_language"] = matched_user.get("preferred_language") or "en"
                st.session_state["_show_welcome"] = not matched_user.get("has_seen_welcome", False)
                st.session_state.authenticated = True
                st.session_state.last_activity = datetime.now()
                log_audit(matched_user.get("full_name"), "login")
                # Lets login survive a hard refresh — session_state is
                # tied to the live browser connection and is genuinely
                # lost on one. Best-effort: a failure here means the
                # person just won't stay logged in across a refresh,
                # not that login itself should fail.
                _new_session_token = create_session_token(matched_user.get("username"))
                if _new_session_token:
                    st.query_params["session"] = _new_session_token
                # last_login exists in the schema but nothing wrote to it
                # until now — best-effort, since a failure here shouldn't
                # block someone from actually logging in.
                update_user_profile(matched_user.get("username"),
                                    {"last_login": datetime.now().isoformat()})
                st.rerun()
            elif status == "pending_approval":
                st.info("⏳ **Your access request is pending.** The administrator has "
                        "not yet reviewed it. You'll be able to sign in once approved.")
            elif status == "suspended":
                st.error("🚫 **This account is suspended.** Contact the administrator "
                         "if you believe this is a mistake.")
            elif status == "denied":
                st.error("🚫 **Your access request was declined.** Contact the "
                         "administrator for details.")
            else:
                record_login_failure(user_in)
                attempts = _login_state().get(str(user_in).lower(), {}).get("count", 0)
                remaining = max(0, LOGIN_MAX_ATTEMPTS - attempts)
                if remaining > 0:
                    st.error(f"Invalid credentials. {remaining} attempt(s) remaining before lockout.")
                else:
                    st.error(f"🔒 Too many failed attempts. Account locked for {LOGIN_LOCKOUT_MINUTES} minutes.")

    # Forgot password link
    with st.expander("Forgot Password?"):
        with st.form("reset_form", clear_on_submit=True):
            reset_email = st.text_input("Enter your registered email", placeholder="email@example.com")
            if st.form_submit_button("Send Reset Link"):
                if not reset_email or "@" not in reset_email:
                    st.error("Enter a valid email address.")
                else:
                    _locked, _secs = is_login_locked(f"reset:{reset_email.lower()}")
                    if _locked:
                        st.error(f"Too many reset requests for this address. "
                                 f"Try again in about {max(1, _secs // 60)} minute(s).")
                    else:
                        record_login_failure(f"reset:{reset_email.lower()}")
                        users = fetch_all_users_from_db()
                        _matched = next((u for u in users if u.get("email") == reset_email), None)
                        if _matched:
                            generate_reset_token(_matched["username"], reset_email)
                        # SECURITY: identical response whether or not the email exists.
                        # Previously this branched to "Email not found" for unregistered
                        # addresses, which let anyone enumerate the worker roster by
                        # trying emails one at a time. If SMTP itself isn't configured,
                        # that's an operator problem visible in the Owner Console health
                        # check, not something to reveal to whoever is at this form.
                        st.success("If that email is registered, a reset link has been sent.")

    if AUTH_AVAILABLE and GOOGLE_CLIENT_ID:
        if st.button("🔑 Login with Google", use_container_width=True):
            st.info("OAuth login will redirect to Google. (Integration in progress)")

    st.markdown("---")
    st.markdown('<div class="sub-header"><i class="fas fa-user-plus"></i> Create Account Profile</div>', unsafe_allow_html=True)

    with st.form("register_form", clear_on_submit=True):
        st.caption("Submitting this creates an **access request**. An administrator "
                   "reviews it and decides your role — selecting a role below is a "
                   "request, not a grant.")
        _rc1, _rc2 = st.columns(2)
        with _rc1:
            reg_user = st.text_input("Choose Username", placeholder="Pick a unique username").strip().lower()
            reg_name = st.text_input("Full Name *", placeholder="Your full name")
            reg_email = st.text_input("Work Email", placeholder="email@company.com")
            reg_pass = st.text_input("Set Password *", type="password",
                                     placeholder="8+ chars, upper, lower, digit, symbol")
        with _rc2:
            reg_empid = st.text_input("Employee / Contractor ID",
                                      placeholder="Helps the admin verify you")
            reg_title = st.text_input("Job Title", placeholder="e.g. Fitter, Electrician")
            reg_dept = st.text_input("Department / Crew", placeholder="e.g. Fixed Plant")
            reg_role = st.selectbox("Requested Access Level",
                                    ["Worker", "Supervisor", "Superintendent"])
        register_submitted = st.form_submit_button('📨 Request Access', use_container_width=True)

    if register_submitted:
        if not SUPABASE_AVAILABLE:
            st.error("Cannot register in demo mode — no database is connected.")
        elif reg_user and reg_name and reg_pass:
            users = fetch_all_users_from_db()
            if any(u["username"].lower() == reg_user for u in users):
                st.error("That username is taken. Please choose another.")
            else:
                ok, err = register_user_to_db(
                    reg_user, reg_name, reg_role, reg_pass, reg_email or None,
                    job_title=reg_title or None, department=reg_dept or None,
                    employee_id=reg_empid or None)
                if ok:
                    st.success("✅ Access request submitted. You'll be able to sign in "
                               "once an administrator approves it.")
                else:
                    st.error(err or "Registration failed.")
        else:
            st.error("Username, full name, and password are required.")
    st.stop()
else:
    check_timeout()

    # --- Forced password change gate ------------------------------------
    # Blocks EVERYTHING else in the app until satisfied. This is the
    # enforcement side of admin_reset_password(): a temp password alone
    # is not enough, since the person who set it (the admin) would
    # otherwise still know the account's live password afterward.
    if st.session_state.user_payload.get("must_change_password"):
        render_logo_bar()
        render_poster_slideshow()
        render_ticker_bar()
        st.markdown('''
        <div class="main-header">
            <i class="fas fa-key"></i> Password Change Required
        </div>
        ''', unsafe_allow_html=True)
        st.markdown('<div class="main-header-spacer"></div>', unsafe_allow_html=True)
        st.warning("An administrator reset your password. Choose a new one to continue — "
                  "you won't be able to use the app until this is done.")
        with st.form("forced_password_change", clear_on_submit=True):
            _fp1 = st.text_input("New Password", type="password")
            _fp2 = st.text_input("Confirm New Password", type="password")
            _fp_go = st.form_submit_button("Set New Password", use_container_width=True)
            if _fp_go:
                if _fp1 != _fp2:
                    st.error("Passwords do not match.")
                else:
                    _strong, _msg = is_strong_password(_fp1)
                    if not _strong:
                        st.error(_msg)
                    elif update_user_profile(st.session_state.user_payload.get("username"), {
                        "password_hash": hash_password(_fp1),
                        "must_change_password": False,
                    }):
                        st.session_state.user_payload["must_change_password"] = False
                        log_audit(st.session_state.user_payload.get("name", "unknown"),
                                 "forced_password_change_completed", {})
                        st.success("Password updated.")
                        st.rerun()
                    else:
                        st.error("Failed to update password. Try again.")
        st.stop()

# -------------------------------
# 25. PWA MANIFEST & SERVICE WORKER
# -------------------------------
# Rewritten — the previous version linked to /static/manifest.json and
# /static/sw.js, but neither file existed anywhere in the project and
# even if they had, that isn't the correct URL path for how Streamlit
# actually serves static files. It never worked.
#
# The manifest and icons below are embedded directly as data: URIs —
# this makes "Add to Home Screen" installability work on a fresh
# deploy with ZERO configuration, regardless of Streamlit version or
# whether static file serving is set up. The one thing that genuinely
# needs real static file hosting is the service worker (browsers
# refuse to register a service worker from a data: URI — that's a
# security restriction, not a Streamlit limitation), so that part is
# wrapped to fail silently if it's not available. See
# PWA_SETUP.md for how to enable it.
_PWA_MANIFEST_B64 = "eyJuYW1lIjogIk1pbmUgJiBXb3Jrc2hvcCBEaWdpdGFsIFRyYWNrZXIgU3lzdGVtIiwgInNob3J0X25hbWUiOiAiTVdEVFMiLCAiZGVzY3JpcHRpb24iOiAiQ01NUyBtYWludGVuYW5jZSwgc2FmZXR5LCBhbmQgaW5jaWRlbnQgdHJhY2tpbmcgZm9yIG1pbmUgYW5kIHdvcmtzaG9wIG9wZXJhdGlvbnMuIiwgInN0YXJ0X3VybCI6ICIuIiwgImRpc3BsYXkiOiAic3RhbmRhbG9uZSIsICJiYWNrZ3JvdW5kX2NvbG9yIjogIiNlZWYxZjYiLCAidGhlbWVfY29sb3IiOiAiIzE2MjEzZSIsICJvcmllbnRhdGlvbiI6ICJhbnkiLCAiaWNvbnMiOiBbeyJzcmMiOiAiZGF0YTppbWFnZS9wbmc7YmFzZTY0LGlWQk9SdzBLR2dvQUFBQU5TVWhFVWdBQUFNQUFBQURBQ0FZQUFBQlMzR3dIQUFBRm5VbEVRVlI0bk8zZHZZN2JSaFNHNFJtQlJTNWdGNUpkV0JzZ2lMZHk2WjhnVFlvRWRwZExUUmNrVldKdi91NGdCbUx0dWdvRjMwQTZwVkRreUxKRVVkUU16NXo1M2dkUVpVQ2t5ZlB4ekNHbFZieC8vMUV3c0xMWUtGeUlZMjZzR2FrU0tYajB0VnNyV1FQUlpIeHZpaDRwYk5kUjhqQ2tEZ0JGajV5U2g2RkpHQ3FLSDJOYWhRVEZtNklEVVBpd3NxbTl3VUdZSk5vQndOTGdPaHphQVNoOGxHWlFOMmhDUExsN1VQd28yVW16d2FsTElJb2ZIdlN1MDFNQ1FQSERrMTcxMmpjQUZEODhPbHEzZlo0RFVQendySE1tT05ZQktIN1U0R0Fkbi9zY0FIQ3Q2VmdCY2ZWSFRmWXVoUTdOQUJRL2F2UlJDRmdDUWRxK0w4Unc5VWZOUHVnQ3V4MkE0b2VDOTNXZTh2c0FnRHZNQUpDMkhRQ1dQMUN5Q3FIN09RQlFQV1lBU05zc2dWaitRTkdLSVJqU1dBSkJHaDBBMGlhQjlUK0VjUnNVMHBnQk12cjc3Ui9KM3V2ZS9FbXk5OEwvNHV6Qlk1WkFBNlVzOEhNUmtHRUlRRThsRlh0ZmhPSTRBdERCWTlFZlFoajJpOU1IVHdqQWY5cTN2MXZ2d21obTg2Zld1MUFFK1FBb0ZmMGh5bUdJMDdsbUFObzdDbi9YN0VvdkNGSUJvT2o3VXdsRG5NNmZWaCtBOXU0MzYxMXdhM2IxekhvWHNxbzZBQlIrT3JVR29kb1B3MUg4YWRWNlBLdnJBTFdlcUpMVTFBM2lkUDZzaWdDMGQ3OWE3NEtjMmRVWDFydHd0aXFXUUJTL2pScU9lNXhlK2UwQTdhMy9FMUNMMmFjK3U0SGJEa0R4bDhYcitaaXN2dy9nNitYMVlOZHVmVjdzNitPVWw3c08wTjcrWXIwTDZPRHQvTGdLZ0xlRHE4clRlWEt6QlBKMFVMRUpnWDNkVkxFRWFtOXZySGNCQTNnNGI1TUNRdGo1OG5BUWNWaDdlMk5lUTEydnlTcXMvekJRaWE5MlFmSFhvRjNjbU5mU29WZXhNOENTNHEvSytuemExOVh1cThnWllMbDRaYjBMeUtERTgxcGtBSUN4RkJlQUVxOFNTS2UwODF2VURGRGF3VUVlNi9Oc1gyL0Z6Z0RBV0lwNURyQmN2TXorbjBVNWxvdVg1alVYWW9FekFEQ21JbWFBNVJ1dS9vclc1OTIyOXVnQWtFWUFJTTA4QU1zM1AxdnZBZ3habjM5K0lna0ZzS3RCZmlRUDlneHIwSFFKdFB6cko4dk5veENXZFdBK0F3Q1dtaFZySUJUQXFnN3BBSkJHQUNDTjI2QW9oRTBkeHN2UHZuTDd4M0dCYzdFRWdqUUNBR25NQUpCR0I0QTBBZ0JwQkFEU21BRWdqWTlEUXhwTElFZ2pBSkRHREFCcGRBQklJd0NRMXZCUlVDaHJRaHh2Qm5qMytzZlJ0Z1hmTGg5K004cDI0c1huWDJkdkFoUStoc29kaE93QjZDcitiMi8reWJscE9QTGRsNThjL0xlY0ljZzZCSFBsUndvNTY0am5BSEFpVDUxbTZ3RHZYditRNjYwaEtGYzk4UndBMGthOURRcWNKVU90MGdFZ2pRQkFXcllBWEY0L3ovWFdFSlNybnJnTkNpZWMzUVlOSVlUTDZ4YzUzeDRpY3RaUnZIajRQUDluZ2Y3OFB2Y21VS25jRjlGUkFyQkJFTkRYV0t1SGVISDlncThFUUJaZmlJRTBuZ05BR2dHQU5KNERRQm9kQU5JSUFLVHh4M0VoalJrQTBsZ0NRUm9CZ0RRQ0FHbk1BSkJHQjRBMEFnQnBQQWVBTkdZQVNHTUpCR2tFQU5LYUZVc2dDS01EUUJvQmdEUnVnMElhdDBFaGpTVVFwQkVBU0NNQWtNWU1BR2wwQUVqak5paWswUUVnalJrQTB1Z0FrRVlBSUkwQVFCb3pBS1R4RTBtUXhuTUFTR01HZ0RSbUFFaWpBMEFhQVlBMGxrQ1FSZ2VBTkc2RFFob2RBTktZQVNDTkRnQnBCQURTQ0FDa01RTkFHaDBBMG5nT0FHbDBBRWpqSjVJZ2pRNEFhUVFBMGdnQXBQRWNBTks0RFFwcGswQUxnREJtQUVoakJvQTBPZ0NrYlFKQUc0Q2l5QklJMHJnTkNtbmJNd0JSZ0pJWUFrTXd4REVEUU5wdUJ5QU5VUEMrenZmOVJGSU1JZkRMU2FqVkJ4ZDVaZ0JJT3pRRDBBVlFvNCtLdmVzNUFDRkFUZlpXT2tzZ1NEc1dBTzRLb1FZSDY3alBjd0NXUXZDc3M4RDdMb0hvQlBEb2FOMmVNZ01RQW5qU3ExNVBIWUlKQVR6b1hhZE5pQ2ZYTkRNQlNuWlNRVGRuYm9RZ29CU0RWaWZuUGdkZ1NZUVNESzdEb1IxZzM4YnBCaGpiMlJmZ2xOOEhZRGJBbUpJVWJvb09zRzE3cHdnRFVrdSs1RTRkZ0cyRUFTbGtuVFAvQmRQUlNBRkVDd1E4QUFBQUFFbEZUa1N1UW1DQyIsICJzaXplcyI6ICIxOTJ4MTkyIiwgInR5cGUiOiAiaW1hZ2UvcG5nIiwgInB1cnBvc2UiOiAiYW55In0sIHsic3JjIjogImRhdGE6aW1hZ2UvcG5nO2Jhc2U2NCxpVkJPUncwS0dnb0FBQUFOU1VoRVVnQUFBZ0FBQUFJQUNBWUFBQUQwZU5UNkFBQVB0RWxFUVZSNG5PM2N1M0lrWnhuSDRlNnREcmdBcnlVNzhPN2FGSFpFaUk5VTRRREtaRndxR1FVSkJzenBEbkNWajVFbDlnYklSTENlM1pFMGt1YlEzZC9oL3p4Vm03cmFzenY5L3ZSMjZ4dmZmUFBuQTdPNUtuMEJBQUhHMGhmUWc4bkVPcGlQREtDcysrN0Q0bUJQVStrTHFKeGhEOUNXWGZkdFViQ0RBTGpPd0Fmb3o4MTd1eUFZQk1Bd0dQb0FhYmJ2KzdFeGtCb0FoajRBd3hBY0Eya0JZUEFEY0pmTmpJZ0lnWVFBTVBRQk9FVEVWcURuQURENEFUaFZ0MXVCSGdQQTRBZGdidDJGUUU4QllQQURzTFJ1UW1EcTRQL0I0QWRnYmMySFFNc2JBSU1mZ05LYURZRkhwUy9nU0lZL0FEVnBiaTYxdGdGbzdnTUdJRVpUMjRCV0FzRGdCNkFWVFlSQUM0OEFESDhBV2xUMS9LbzlBS3IrOEFEZ0FkWE9zVm9mQVZUN2dRSEFnYXA4SkZEakJzRHdCNkJIVmMyM3FhNGVxZXZEQVlDWlhRMlZiQUpxT1FuUTRBY2dSUldQQkdwNEJHRDRBNUNvNlB3ckhRQ0dQd0RKaXMzQmtnRmcrQU5Bb1hsWUtnQU1md0I0WmZXNVdDSUFESDhBdUczVitiaDJBQmorQUhDMzFlYmttZ0ZnK0FQQXcxYVpsMnNGZ09FUEFQdGJmRzZ1RVFDR1B3QWNidEg1dWZSSmdJWS9BQnh2c2FPRGw5d0FHUDRBY0xwRjV1bFNBV0Q0QThCOFpwK3JwWThDQmdBS1dDSUEvUFFQQVBPYmRiN09IUUNHUHdBc1o3WTVPMmNBR1A0QXNMeFo1cTEzQUFBZzBGd0I0S2QvQUZqUHlYTjNtdUY0QWNNZkFOWjMwaUZCcDU0RWFQZ0RRRGxIUjRCM0FBQWcwQ2tCNEtkL0FDanZxSGxzQXdBQWdZNE5BRC85QTBBOURwN0x4d1NBNFE4QTlUbG9QayttT1FEa09YUURvQmNBb0Y1N3oya3ZBUUpBb0VNQ3dFLy9BRkMvdmVhMURRQUFCTnIzS0dBLy9RTkFPeDQ4SXRnR0FBQUM3Uk1BZnZvSGdQYmNPNzl0QUFBZzBFTUI0S2QvQUdqWG5YUGNCZ0FBQWdrQUFBaDBYd0JZL3dOQSszYk84Mm0vWXdBQWdKN2N0UUh3MHo4QTlPUFdYTi8zSkVBQW9DTmVBZ1NBUUxzQ3dQb2ZBUHB6YmI3YkFBQkFJQUVBQUlGdUJvRDFQd0QwNitXY3R3RUFnRUFDQUFBQ0NRQUFDTFFkQUo3L0EwRC9yb2JCU1lBQUVNa2pBQUFJSkFBQUlKQUFBSUJBbXdEd0FpQUE1TGl5QVFDQVFBSUFBQUpOZmdzUUFQTFlBQUJBSUFFQUFJR2NCQWdOKytIN2Y1ZStoT0dOSisrWHZnVGdDT1A1Vzcvd0s0QlFpUm9HK3RJRUE5UkJBTUNLRWdiOHFRUUNyRU1Bd0FJTSt2a0pBNWlYQUlBVEdQVGxDUU00amdDQVBSbjI3UkFGOERBQkFEc1k5djBSQlhDZEFJREJ3RThrQ0VnbkFJaGs0SE9USUNDTkFDQ0dvYysreEFBSkJBRGRNdkNaaXlDZ1IrUDVXKzhMQUxyeHcvZi9LbjBKZE82Tkp4K1V2Z1NZeFhnbUFHamNoYUZQSWVkaWdJWUpBSnBrNkZNYk1VQnJCQUROTVBScGhSaWdCUUtBNmhuOHRFb0lVRE1CUUpVTWZYb2pCcWpOZVBaRUFGQ0hpKzhNZlRLY1B4VURsQ2NBS003Z0o1VVFvQ1FCUURFR1A3d2dCQ2hCQUxBNmd4OTJFd0tzYVR4NzhvRUFZSEVYMy8yejlDVkFVODZmZmxqNkV1aWNBR0JSQmorY1JnaXdGQUhBSWd4K21KY1FZRzRDZ0ZrWi9MQXNJY0JjQkFDek1QaGhYVUtBVXowcWZRRzB6L0NIOWZuZWNTb2JBSTdtQmdSMXNBM2dHQUtBZ3huOFVDY2h3Q0VFQUhzeitLRU5Rb0I5ZUFlQXZSaiswQTdmVi9ZeG5qMzUwQWFBTzExODk0L1Nsd0NjNFB6cFI2VXZnVW9KQUhZeStLRXZRb0NiUEFMZ0ZzTWYrdU43elUwMkFMemtCZ0VaYkFNWUJoc0FmbVQ0UXc3ZmQ0YkJCaUNlR3dGa3N3M0lOWjQ5RlFDcExyNDEvSUZoT0g4bUFoSjVCQkRLOEFjMjNBOHkyUUNFOFVVSDdtTWJrTU1HSUlqaER6ekVmU0xIZVBiMEl4dUFBQmZmL3IzMEpRQU5PWC8yY2VsTFlHRTJBQUVNZitCUTdodjlzd0hvbUM4d01BZmJnRDdaQUhUSzhBZm00bjdTSndIUUlWOVdZRzd1Sy8wUkFKM3hKUVdXNHY3U0Z3SFFFVjlPWUdudU0vMFFBSjN3cFFUVzRuN1RCd0hRQVY5R1lHM3VPKzBUQUkzekpRUktjZjlwbXdCb21DOGZVSnI3VUx2R3M2Y2ZPd2lvUVJmZmZsSDZFZ0JlT24vMlNlbEw0RUEyQUEweS9JSGF1QysxUndBMHhwY01xSlg3VTFzRVFFTjh1WURhdVUrMVl6eDc1aDJBRmx4ODQwc0Z0T1A4YmU4RTFNNEdvQUdHUDlBYTk2MzZqYS9iQUZUdDBwY0lhTmlaVFVDMWJBQXFadmdEclhNZnE1Y0FxSlF2RGRBTDk3TTZDUUFBQ0RTKy91d1Q3d0JVNXZLYnY1VytCSURabmIzOXk5S1h3QlliZ01vWS9rQ3YzTi9xSWdBcTRzc0I5TTU5cmg0Q29CSytGRUFLOTdzNkNBQUFDQ1FBS3FDR2dUVHVlK1VKZ01KOENZQlU3bjlsQ1FBQUNDUUFDbEsvUURyM3dYSUVRQ0grMFFPODRINVl4alFNWStsckFDQ2VXYlEyRzRBQ0xyLzVhK2xMQUtpSysrTDZCQUFBQkJJQUsxTzVBTHU1UDY1cjh0Z0ZnR3FZU2F1eEFWalI1ZGZxRnVBKzdwUHJFUUFBRUVnQXJFVFZBdXpIL1hJZEFnQUFBZ21BRmFoWmdNTzRieTdQU1lBQVZNcDhXcElOd01JdXYvNUw2VXNBYUpMNzU3SUVBQUFFRWdBTFVxOEFwM0VmWFk0QUFJQkFBZ0FBQWdtQWhWaGJBY3pEL1hRWkFnQUFBZ2tBQUFna0FCWmdYUVV3TC9mVitRa0FBQWprS0dBQUdtRmV6Y2tHWUdhWFgzOWUraElBdXVUK09pOEJBQUNCSmhzVkFKcGhaczNHQmdBQUFna0FBQWdrQUdaMCtkWG5wUzhCb0d2dXMvTVJBQUFRU0FBQVFDQUJBQUNCbkFRSVFHUE1yVG5ZQUFCQW9QSHhPNys2S24wUlBmanZWMzh1ZlFrQU1WNy82YWVsTDZGNU5nQUFFRWdBQUVBZ0FRQUFnUVFBQUFRU0FBQVFTQUFBUUNBQkFBQ0JuQVFJUUlQTXJsT05qOS81MUVGQUFCQm1FbEVBa01jN0FBQVFTQUFBUUNBQkFBQ0JCQUFBQkJJQUFCQklBQUJBSUFFQUFJR2NCQWdBZ1d3QUFDQ1FBQUNBUUFJQUFBSUpBQUFJSkFBQUlKQUFBSUJBQWdBQUFna0FBQWdrQUFBZ2tBQUFnRUNPQWdhQVFKUDVEd0I1UEFJQWdFQUNBQUFDQ1FBQUNDUUFBQ0NRQUFDQVFBSUFBQUlKQUFBSUpBQUFJSkNUQUFFZ2tBMEFBQVFTQUFBUVNBQUFRQ0FCQUFDQkJBQUFCQklBQUJCb3VpcDlCUURBNm13QUFDQ1FBQUNBUUU0Q0JJQkFrL2wvdCtkZi9xbjBKUUJ3b3Nmdi9xYjBKVlJwZk8xbnYvWWU0QlpESDZCZll1QVZBZkFqZ3g4Z2h4RHdFdUF3RElZL1FCcjMvZkFOZ0g4QUFLUnVBMkkzQUlZL0FNT1FPdzhpTndCTC9HWC83b3YvemY3ZkJHQzMzMy95azluL20ybWJnTGdOUUdycEFYQy90UGtRRndBQXdEQThlbkVTWU1hZnRMb0Q0REF2NWtUNWViWEduNWdOd1BNdi8xajZFZ0JvUU1xOGlBa0FBT0NWaUFCSXFUa0E1cEV3TnlJQ0FBQzRUZ0FBUUtEdUF5QmhqUVBBL0hxZkg5MEhBQUJ3bXdBQWdFQUNBQUFDVGNNNGxyNEdBS2hUeHpQU0JnQUFBZ2tBQUFna0FBQWdrQUFBZ0VEZEI4RGo5ejRyZlFrQU5LajMrZEY5QUFBQXR3a0FBQWdVRVFDOXIzRUFtRmZDM0lnSUFBRGd1cGdBU0tnNUFFNlhNaThlRGNNNHBQeDUvTjV2NS9yY0FPalFpemxSZmw2dDhTZG1Bd0FBdkJJWEFMWUFBT3lTTmgvRzE5Nzk3S3IwUlpUdy9EOS9LSDBKQUZRaWJmZ1BRK0FHWUNQeEx4dUEyMUxuUWV3R1lKdHRBRUNlMU1HL0Vic0IySmIrandBZ2pmdStEY0F0dGdFQS9UTDRYeEVBOXhBREFPMHo5SGNiWDN0UEFBQkFtdW5GaVVBQVFCSXZBUUpBSUFFQUFJRW1Md0FBUUI0YkFBQUlKQUFBSUpBQUFJQkFBZ0FBQWdrQUFBZ2tBQUFna0pNQUFTQ1FEUUFBQkJJQUFCQklBQUJBSUFFQUFJRUVBQUFFRWdBQUVFZ0FBRUFnQVFBQWdTYm5BQUZBSGljQkFrQWdqd0FBSUpBQUFJQkFBZ0FBQWdrQUFBZ2tBQUFna0FBQWdFQUNBQUFDQ1FBQUNDUUFBQ0NRQUFDQVFJNENCb0JBTmdBQUVFZ0FBRUFnQVFBQWdRUUFBQVFTQUFBUVNBQUFRQ0FCQUFDQkpzY0FBRUFlR3dBQUNPUWtRQUFJWkFNQUFJRUVBQUFFRWdBQUVFZ0FBRUFnQVFBQWdRUUFBQVFTQUFBUWFMb3FmUVVBd09wc0FBQWdrSk1BQVNDUURRQUFCQklBQUJCSUFBQkFJQUVBQUlFRUFBQUVFZ0FBRUdqeVc0QUFrTWNHQUFBQ0NRQUFDT1FrUUFBSVpBTUFBSUVFQUFBRUVnQUFFRWdBQUVBZ0FRQUFnUVFBQUFRU0FBQVFTQUFBUUNBQkFBQ0JCQUFBQkhJVU1BQUVzZ0VBZ0VBQ0FBQUNDUUFBQ0NRQUFDQ1FBQUNBUUpOZkFnQ0FQRFlBQUJCSUFBQkFJQUVBQUlHY0JBZ0FnV3dBQUNDUUFBQ0FRQUlBQUFJSkFBQUlKQUFBSUpBQUFJQkFBZ0FBQWdrQUFBZ2tBQUFna0pNQUFTQ1FEUUFBQkJJQUFCQklBQUJBb09tcTlCVUFBS3V6QVFDQVFKTmZBZ0NBUERZQUFCQklBQUJBSUFFQUFJR2NCQWdBZ1d3QUFDQ1FBQUNBUUFJQUFBSUpBQUFJSkFBQUlKQUFBSUJBQWdBQUFna0FBQWdrQUFBZ2tBQUFnRUNPQWdhQVFEWUFBQkJJQUFCQUlBRUFBSUVtcndBQVFCNGJBQUFJSkFBQUlKQUFBSUJBQWdBQUFna0FBQWprSkVBQUNHUURBQUNCQkFBQUJCSUFBQkJJQUFCQUlBRUFBSUVFQUFBRUVnQUFFRWdBQUVBZ0FRQUFnWndFQ0FDQmJBQUFJSkFBQUlCQUFnQUFBazFlQVFDQVBEWUFBQkJJQUFCQUlBRUFBSUVFQUFBRW1xNUtYd0VBc0RvbkFRSkFJSThBQUNDUUFBQ0FRQUlBQUFJSkFBQUlKQUFBSUpBQUFJQkFBZ0FBQWdrQUFBZ2tBQUFnMEtQQlVZQUFFTWRSd0FBUXlDTUFBQWdrQUFBZzBPUUpBQURrc1FFQWdFQUNBQUFDYlFMQWd3QUF5REhhQUFCQUlBRUFBSUVFQUFBRWNoSWdBQVRhM2dBb0FRRG8zemdNSGdFQVFDUUJBQUNCQkFBQUJMb1pBTjREQUlCK3ZaenpOZ0FBRUVnQUFFQ2dYUUhnTVFBQTlPZmFmTGNCQUlCQVRnSUVnRUIzYlFCVUFRRDA0OVpjbjR4NkFNaHozenNBMGdBQTJyZHpubnNKRUFBQ0NRQUFDUFJRQUhnTUFBRHR1bk9PMndBQVFLQjlBc0FXQUFEYWMrLzh0Z0VBZ0VEN25nUTREc053dGZDMUFBRHplSEM0MndBQVFLQkRBc0M3QUFCUXY3M210UTBBQUFRNk5BQnNBUUNnWG52UDZjbWJmUUNRNTVoSEFMWUFBRkNmZytienNlOEFpQUFBcU1mQmM5bExnQUFRNkpRQXNBVUFnUEtPbXNjMkFBQVFhTitqZ08vaWlHQUFLT2ZvSVQ3TnNNZ1hBUUN3dnBNbStGeVBBTHdQQUFEck9YbnVlZ2NBQUFMTkdRQzJBQUN3dkZubTdkd2JBQkVBQU11WmJjNHU4UWhBQkFEQS9HYWRyOTRCQUlCQVN3V0FMUUFBekdmMnVicmtCa0FFQU1EcEZwbW5wNTRFK0JDSEJBSEE4UlliMG11OEEyQVRBQUNIVzNSK3J2VVNvQWdBZ1AwdFBqZlgvQzBBRVFBQUQxdGxYcTc5YTRBaUFBRHV0dHFjTEhFT2dBZ0FnTnRXblkrbERnSVNBUUR3eXVwenNlUkpnQ0lBQUFyTnc5SkhBWXNBQUpJVm00T2xBMkFZUkFBQW1Zck92NlZQQXR6WDVpS2NHZ2hBNzZvWXZGTWRsL0dTbzRNQjZGazFVN2VHUndBM1ZmUGhBTUNNcXBwdlUra0x1SU5IQWdEMG9xckJ2MUhqQm1CYmxSOGFBT3lwMmpsV2V3QU1ROFVmSGdEY28rcjVWZXNqZ0pzOEVnQ2dGVlVQL28xV0FtQkRDQUJRcXlZRy8wWUxqd0IyYWVwREJxQjd6YzJsMWpZQTIyd0RBQ2l0dWNHL1VjdEpnS2NRQWdDc3JmbmgyZklHNENZaEFNRFNtaC84R3owRndJWVFBR0J1M1F6K2pSNERZRU1JQUhDcTdnYi9SczhCc0xIOWx5Y0dBSGhJdDBOL1cwSUFiTE1WQU9BdUVZTi9JeTBBTm13RkFCaUdzS0cvTFRVQXRva0JnQ3l4UTMrYkFManU1ajhLUVFEUVBnTi9Cd0Z3djEzL2FFUUJRTDBNK3ozOUh5RFFZd2ZRYXMxOUFBQUFBRWxGVGtTdVFtQ0MiLCAic2l6ZXMiOiAiNTEyeDUxMiIsICJ0eXBlIjogImltYWdlL3BuZyIsICJwdXJwb3NlIjogImFueSJ9LCB7InNyYyI6ICJkYXRhOmltYWdlL3BuZztiYXNlNjQsaVZCT1J3MEtHZ29BQUFBTlNVaEVVZ0FBQWdBQUFBSUFDQVlBQUFEMGVOVDZBQUFNUTBsRVFWUjRuTzNjelk0Y1Z4bUE0ZTZvRmx4QTdMR3lpZjlFc21KTkVnY1JKRkRZY2Fuc0VDd2dRSUJiSUpKL3NweUpiNERkWklHY2lPRDRaN3FxVGxlOXozTUJuclBvT3VmMVY5M24rTjU3UDdzK0FBQXBrOU1mQUhyZUdiMEFBR0I5QWdBQWdnUUFBQVFKQUFBSUVnQUFFQ1FBQUNCSUFBQkFrQUFBZ0NBQkFBQkIwK0Z3SEwwR0FHQmxKZ0FBRUNRQUFDQklBQUJBa0FBQWdDQUJBQUJCQWdBQWdnUUFBQVFKQUFBSW10d0RCQUE5YmdJRWdDQ3ZBQUFnU0FBQVFKQUFBSUFnQVFBQVFRSUFBSUlFQUFBRUNRQUFDQklBQUJBa0FBQWd5RTJBQUJCa0FnQUFRUUlBQUlJRUFBQUVDUUFBQ0JJQUFCQWtBQUFnU0FBQVFKQUFBSUNneVQxQUFORGpKa0FBQ1BJS0FBQ0NCQUFBQkFrQUFBZ1NBQUFRSkFBQUlHaTZIcjBDQUdCMUpnQUFFQ1FBQUNCSUFBQkFrQUFBZ0NCWEFRTkFrQWtBQUFRSkFBQUlFZ0FBRUNRQUFDQklBQUJBa0FBQWdDQUJBQUJCazJzQUFLREhCQUFBZ3R3RUNBQkJKZ0FBRUNRQUFDQklBQUJBa0FBQWdDQUJBQUJCQWdBQWdnUUFBQVFKQUFBSUVnQUFFT1FtUUFBSU1nRUFnQ0FCQUFCQkFnQUFnZ1FBQUFRSkFBQUlFZ0FBRURUNUZTQUE5SmdBQUVDUUFBQ0FJRGNCQWtDUUNRQUFCQWtBQUFnU0FBQVFKQUFBSUVnQUFFQ1FBQUNBSUFFQUFFRUNBQUNDQkFBQUJBa0FBQWh5RlRBQUJFM1hvMWNBQUt6T0t3QUFDQklBQUJBa0FBQWdTQUFBUU5Ea1J3QUEwR01DQUFCQkFnQUFnZ1FBQUFTNUNSQTI3dkxyZnczNzIzZnVmalRzYndPbk9WNjgvM09YQWNLWkdYbW9MMFVzd0hrUkFEREFIZy80VXdrRVdKY0FnQVU1NkU4bkRHQVpBZ0JtNHJCZmp5aUEwd2tBdUFHSC9ma1JCZkIyQkFDOEFRZis5Z2dDZURVQkFDL2h3TjhmUVFEL1N3REF3WUZmSkFpb0V3QmtPZlI1UVF4UWRMeDQveU1CUU1ibDEvOGN2UVRPM0oyN0g0OWVBcXhDQUxCN0RuMXVTZ3l3WndLQVhYTG9NemN4d040SUFIYkRvYzlheEFCN0lBRFlQQWMvb3dnQnRrd0FzRWtPZmM2TkdHQnJqaGQzQlFEYmNmbk13Yzk1dTNOUENMQU5Bb0JOY1BDek5VS0FjeWNBT0ZzT2ZmWkNESENPQkFCbng4SFBYZ2tCenNueDR1N0hBb0N6Y1Buc0g2T1hBS3U0YysrVDBVc0FBY0I0RG42cWhBQWpDUUNHY2ZERGZ3a0JSbmhuOUFKb2N2akQ5endQakdBQ3dLcHNkUEJxcGdHc1JRQ3dDZ2MvdkIwaHdOSUVBSXR5OE1OcGhBQkw4UjBBRnVQd2g5TjVqbGlLQ1FDenMySEJNa3dEbUpNSkFMTnkrTU55UEYvTXlRU0FXZGlZWUYybUFaenFlSEgzRXdIQVNTNmZmVGw2Q1pCMDU5NmowVXRnd3dRQU4rYmdoL01nQkxnSjN3SGdSaHorY0Q0OGo5eUVDUUJ2eFVZRDU4MDBnRGQxdkxnbkFIZ3psMDhkL3JBRmQrNkxBRjdQS3dEZWlNTWZ0c1B6eXBzNDNqWUI0RFd1YkNhd1NSY21BYnlDQU9CSE9maGhINFFBTCtNVkFDL2w4SWY5OER6ek1nS0EvMk96Z1AzeFhQTkR4OXYzSG5rRndIZXVudjU5OUJLQUJWM2MvM1QwRWpnVEpnQjh4K0VQKytjNTV3VUJ3T0Z3c0NsQWllZWR3MEVBY0xBWlFKSG5IZ0VRWnhPQUxzOS9td0FJOC9BRDlvRXVBUkRsb1FkZXNCODBDWUFnRHp2d1EvYUZIZ0VRNHlFSGZvejlvVVVBaEhpNGdkZXhUM1FjYjkvNzFFMkFBVmRQL3paNkNjQ0dYTnoveGVnbHNEQVRnQUNIUC9DMjdCdjdKd0FBSUVnQTdKeUtCMjdLL3JGdng5djNmUWRncjY2ZWVIaUIwMTA4OEgyQVBUSUIyQ21IUHpBWCs4aytDWUFkOHJBQ2M3T3Y3SThBQUlBZ0FiQXpLaDFZaXYxbFh3VEFqbmc0Z2FYWlovWmpPaHlPbzljQXdLWTROL2JBQkdBbnJwNzhkZlFTZ0FqN3pUNElnQjN3TUFKcnMrOXNud0FBZ0NBQnNIRXFIQmpGL3JOdEFnQUFnZ1RBaHFsdllEVDcwSFlKQUFBSUVnQWJwYnFCYzJFLzJpWUJBQUJCQW1DRDFEWndidXhMMitNcVlBQm00anpaRWhPQWpibDY4c1hvSlFDOGxQMXBXd1FBQUFSTkpqWUF6TWFac2hrbUFCdHk5ZmlMMFVzQWVDWDcxSFlJQUFBSUVnQWJvYXFCcmJCZmJZTUFBSUFnQVFBQVFRSUFBSUtPdHgvODhucjBJbmkxcThkL0diMEVnTGQyOGZDejBVdmdGVXdBQUNCbzh0OS9BSmJnZkRsdkpnQUFFQ1FBenR3MzN2OERHMlgvT204Q0FBQ0NCQUFBQkFrQUFBZ1NBQUFRSkFBQUlPaDQ2OEZuZnFwNXByNTUvT2ZSU3dBNDJlMkh2eHE5QkY3Q0JBQUFncWJEY2ZRU0FOZzE1OHhaTWdFQWdDQUJBQUJCQWdBQWdnUUFBQVFKQUFBSU90NTY2QjRBQUtneEFRQ0FvTWtQTkFHZ3h3UUFBSUlFQUFBRUNRQUFDQklBQUJBa0FBQWdTQUFBUUpBQUFJQWdBUUFBUVFJQUFJSUVBQUFFdVFvWUFJSW01ejhBOUhnRkFBQkJBZ0FBZ2dRQUFBUUpBQUFJRWdBQUVDUUFBQ0JJQUFCQWtBQUFnQ0EzQVFKQWtBa0FBQVFKQUFBSUVnQUFFQ1FBQUNCSUFBQkFrQUFBZ0tEcGV2UUtBSURWbVFBQVFKQUFBSUFnTndFQ1FORGsvQWVBSHE4QUFDQklBQUJBMERSNkFWWFB2L3JUNkNVQW5JMWJIL3htOUJKeWp1Lys5TmV1QWxpSlF4L2c5Y1RBT2dUQUNoejhBRzlQQ0N6TGR3QVc1dkFIdUJuNzU3Sk1BQll5eHdmM2QxLytaNGFWQUl6MSswYy9PZm5mTUEyWW53bkFBbFFyd0x6c3EvTnpFeUFBRytHOG1wTUp3TXllZi9YSDBVc0EyQ1g3Njd3RXdJeDhPQUdXWlorZGp3QUFnQ0FCTUJOVkNyQU8rKzA4QkFBQUJBa0FBQWdTQURNd2pnSllsMzMzZEFJQUFJSUVBQUFFVFllam01VUEyQ0RuMTBsTUFBQWdTQUFBUUpBQUFJQWdBVENEV3g5K1Bub0pBQ24yM2RNSkFBQUlFZ0FBRUNRQVptSWNCYkFPKyswOEJBQUFCQW1BR2FsU2dHWFpaK2NqQUdibXd3bXdEUHZydktiRHdWV0tBR3lCODJwT0pnQUx1UFhoYjBjdkFXQlg3S3Z6Tzc3N3dlZlhveGV4WjgvLy9ZZlJTd0RZTEFmL2Nrd0FGdWJEQzNBejlzOWxtUUNzeURRQTRQVWMvT3NRQUlPSUFZRHZPZlRYSndBQUlNaDNBQUFnU0FBQVFORGtYZ1VBNkhFVElBQUVlUVVBQUVFQ0FBQ0NKcjhCQklBZUV3QUFDQklBQUJBa0FBQWdTQUFBUUpBQUFJQWdBUUFBUVc0Q0JJQWdFd0FBQ0JJQUFCQWtBQUFnU0FBQVFKQUFBSUFnQVFBQVFRSUFBSUlFQUFBRVRlNEJBb0FlTndFQ1FKQlhBQUFRSkFBQUlFZ0FBRUNRQUFDQUlBRUFBRUVDQUFDQ0JBQUFCQWtBQUFnU0FBQVFKQUFBSU1oVndBQVFaQUlBQUVFQ0FBQ0NCQUFBQkFrQUFBZ1NBQUFRSkFBQUlFZ0FBRURRNUJvQUFPZ3hBUUNBSURjQkFrQ1FDUUFBQkFrQUFBZ1NBQUFRSkFBQUlFZ0FBRUNRQUFDQUlBRUFBRUhUOWVnVkFBQ3JNd0VBZ0NBM0FRSkFrQWtBQUFRSkFBQUlFZ0FBRUNRQUFDQklBQUJBa0FBQWdLREpyd0FCb01jRUFBQ0NCQUFBQkxrSkVBQ0NUQUFBSUVnQUFFQ1FBQUNBSUFFQUFFRUNBQUNDQkFBQUJBa0FBQWdTQUFBUUpBQUFJRWdBQUVDUXE0QUJJTWdFQUFDQ0JBQUFCQWtBQUFnU0FBQVFKQUFBSUdqeUl3QUE2REVCQUlBZ0FRQUFRUUlBQUlMY0JBZ0FRU1lBQUJBa0FBQWdTQUFBUUpBQUFJQWdBUUFBUVFJQUFJSUVBQUFFQ1FBQUNCSUFBQkRrSmtBQUNESUJBSUFnQVFBQVFRSUFBSUttNjlFckFBQldad0lBQUVHVEh3RUFRSThKQUFBRUNRQUFDQklBQUJEa0prQUFDRElCQUlBZ0FRQUFRUUlBQUlJRUFBQUVDUUFBQ0JJQUFCQWtBQUFnU0FBQVFKQUFBSUFnQVFBQVFhNENCb0FnRXdBQUNCSUFBQkFrQUFBZ2FQSVZBQURvTVFFQWdDQUJBQUJCQWdBQWdnUUFBQVFKQUFBSWNoTWdBQVNaQUFCQWtBQUFnQ0FCQUFCQkFnQUFnZ1FBQUFRSkFBQUlFZ0FBRUNRQUFDQklBQUJBa0pzQUFTRElCQUFBZ2dRQUFBUUpBQUFJbW53RkFBQjZUQUFBSUVnQUFFQ1FBQUNBSUFFQUFFSFQ5ZWdWQUFDcmN4TWdBQVI1QlFBQVFRSUFBSUlFQUFBRUNRQUFDQklBQUJBa0FBQWdTQUFBUUpBQUFJQWdBUUFBUVFJQUFJSmNCUXdBUVNZQUFCQWtBQUFnYVBJR0FBQjZUQUFBSUVnQUFFQ1FBQUNBSUFFQUFFRUNBQUNDQkFBQUJMa0pFQUNDVEFBQUlFZ0FBRUNRQUFDQUlBRUFBRUVDQUFDQ0JBQUFCQWtBQUFnU0FBQVFKQUFBSU1oTmdBQVFaQUlBQUVHVEFRQUE5SmdBQUVDUUFBQ0FJQUVBQUVFQ0FBQ0NCQUFBQkFrQUFBZ1NBQUFRNUNaQUFBZ3lBUUNBSUFFQUFFRUNBQUNDQkFBQUJFM1hvMWNBQUt6T0JBQUFnZ1FBQUFRSkFBQUlFZ0FBRUNRQUFDRElWY0FBRURRNS93R2d4eXNBQUFnU0FBQVFKQUFBSUVnQUFFQ1FBQUNBSUFFQUFFRUNBQUNDQkFBQUJMa0pFQUNDVEFBQUlFZ0FBRUNRQUFDQUlBRUFBRUVDQUFDQ0JBQUFCQWtBQUFnU0FBQVFKQUFBSU1oTmdBQVFORG4vQWFESEt3QUFDQklBQUJBa0FBQWdTQUFBUUpBQUFJQWdBUUFBUVFJQUFJSUVBQUFFdVFrUUFJSk1BQUFnU0FBQVFKQUFBSUFnQVFBQVFRSUFBSUlFQUFBRUNRQUFDQklBQUJBa0FBQWc2RnZIUTZiM3B0L205QUFBQUFCSlJVNUVya0pnZ2c9PSIsICJzaXplcyI6ICI1MTJ4NTEyIiwgInR5cGUiOiAiaW1hZ2UvcG5nIiwgInB1cnBvc2UiOiAibWFza2FibGUifV19"
_PWA_ICON192_B64 = "iVBORw0KGgoAAAANSUhEUgAAAMAAAADACAYAAABS3GwHAAAFnUlEQVR4nO3dvY7bRhSG4RmBRS5gF5JdWBsgiLdy6Z8gTYoEdpdLTRckVWJv/u4gBmLtugoF30A6pVDkyLJEUdQMz5z53gdQZUCkyfPxzCGlVbx//1EwsLLYKFyIY26sGakSKXj0tVsrWQPRZHxvih4pbNdR8jCkDgBFj5ySh6FJGCqKH2NahQTFm6IDUPiwsqm9wUGYJNoBwNLgOhzaASh8lGZQN2hCPLl7UPwo2UmzwalLIIofHvSu01MCQPHDk1712jcAFD88Olq3fZ4DUPzwrHMmONYBKH7U4GAdn/scAHCt6VgBcfVHTfYuhQ7NABQ/avRRCFgCQdq+L8Rw9UfNPugCux2A4oeC93We8vsAgDvMAJC2HQCWP1CyCqH7OQBQPWYASNssgVj+QNGKIRjSWAJBGh0A0iaB9T+EcRsU0pgBMvr77R/J3uve/Emy98L/4uzBY5ZAA6Us8HMRkGEIQE8lFXtfhOI4AtDBY9EfQhj2i9MHTwjAf9q3v1vvwmhm86fWu1AE+QAoFf0hymGI07lmANo7Cn/X7EovCFIBoOj7UwlDnM6fVh+A9u43611wa3b1zHoXsqo6ABR+OrUGodoPw1H8adV6PKvrALWeqJLU1A3idP6sigC0d79a74Kc2dUX1rtwtiqWQBS/jRqOe5xe+e0A7a3/E1CL2ac+u4HbDkDxl8Xr+Zisvw/g6+X1YNdufV7s6+OUl7sO0N7+Yr0L6ODt/LgKgLeDq8rTeXKzBPJ0ULEJgX3dVLEEam9vrHcBA3g4b5MCQtj58nAQcVh7e2NeQ12vySqs/zBQia92QfHXoF3cmNfSoVexM8CS4q/K+nza19Xuq8gZYLl4Zb0LyKDE81pkAICxFBeAEq8SSKe081vUDFDawUEe6/NsX2/FzgDAWIp5DrBcvMz+n0U5louX5jUXYoEzADCmImaA5Ruu/orW59229ugAkEYAIM08AMs3P1vvAgxZn39+IgkFsKtBfiQP9gxr0HQJtPzrJ8vNoxCWdWA+AwCWmhVrIBTAqg7pAJBGACCN26AohE0dxsvPvnL7x3GBc7EEgjQCAGnMAJBGB4A0AgBpBADSmAEgjY9DQxpLIEgjAJDGDABpdABIIwCQ1vBRUChrQhxvBnj3+sfRtgXfLh9+M8p24sXnX2dvAhQ+hsodhOwB6Cr+b2/+yblpOPLdl58c/LecIcg6BHPlRwo564jnAHAiT51m6wDvXv+Q660hKFc98RwA0ka9DQqcJUOt0gEgjQBAWrYAXF4/z/XWEJSrnrgNCiec3QYNIYTL6xc53x4ictZRvHj4PP9ngf78PvcmUKncF9FRArBBENDXWKuHeHH9gq8EQBZfiIE0ngNAGgGANJ4DQBodANIIAKTxx3EhjRkA0lgCQRoBgDQCAGnMAJBGB4A0AgBpPAeANGYASGMJBGkEANKaFUsgCKMDQBoBgDRug0Iat0EhjSUQpBEASCMAkMYMAGl0AEjjNiik0QEgjRkA0ugAkEYAII0AQBozAKTxE0mQxnMASGMGgDRmAEijA0AaAYA0lkCQRgeANG6DQhodANKYASCNDgBpBADSCACkMQNAGh0A0ngOAGl0AEjjJ5IgjQ4AaQQA0ggApPEcANK4DQppk0ALgDBmAEhjBoA0OgCkbQJAG4CiyBII0rgNCmnbMwBRgJIYAkMwxDEDQNpuByANUPC+zvf9RFIMIfDLSajVBxd5ZgBIOzQD0AVQo4+Kves5ACFATfZWOksgSDsWAO4KoQYH67jPcwCWQvCss8D7LoHoBPDoaN2eMgMQAnjSq15PHYIJATzoXadNiCfXNDMBSnZSQTdnboQgoBSDVifnPgdgSYQSDK7DoR1g38bpBhjb2RfglN8HYDbAmJIUbooOsG17pwgDUku+5E4dgG2EASlknTP/BdPRSAFECwQ8AAAAAElFTkSuQmCC"
_PWA_APPLE_ICON_B64 = "iVBORw0KGgoAAAANSUhEUgAAAgAAAAIACAYAAAD0eNT6AAAMQ0lEQVR4nO3czY4cVxmA4e6oFlxA7LGyif9EsmJNEgcRJFDYcansECwgQIBbIJJ/spyJb4DdZIGciOD4Z7qqTle9z3MBnrPoOuf1V93n+N57P7s+AAApk9MfAHreGb0AAGB9AgAAggQAAAQJAAAIEgAAECQAACBIAABAkAAAgCABAABB0+FwHL0GAGBlJgAAECQAACBIAABAkAAAgCABAABBAgAAggQAAAQJAAAImtwDBAA9bgIEgCCvAAAgSAAAQJAAAIAgAQAAQQIAAIIEAAAECQAACBIAABAkAAAgyE2AABBkAgAAQQIAAIIEAAAECQAACBIAABAkAAAgSAAAQJAAAICgyT1AANDjJkAACPIKAACCBAAABAkAAAgSAAAQJAAAIGi6Hr0CAGB1JgAAECQAACBIAABAkAAAgCBXAQNAkAkAAAQJAAAIEgAAECQAACBIAABAkAAAgCABAABBk2sAAKDHBAAAgtwECABBJgAAECQAACBIAABAkAAAgCABAABBAgAAggQAAAQJAAAIEgAAEOQmQAAIMgEAgCABAABBAgAAggQAAAQJAAAIEgAAEDT5FSAA9JgAAECQAACAIDcBAkCQCQAABAkAAAgSAAAQJAAAIEgAAECQAACAIAEAAEECAACCBAAABAkAAAhyFTAABE3Xo1cAAKzOKwAACBIAABAkAAAgSAAAQNDkRwAA0GMCAABBAgAAggQAAAS5CRA27vLrfw3723fufjTsbwOnOV68/3OXAcKZGXmoL0UswHkRADDAHg/4UwkEWJcAgAU56E8nDGAZAgBm4rBfjyiA0wkAuAGH/fkRBfB2BAC8AQf+9ggCeDUBAC/hwN8fQQD/SwDAwYFfJAioEwBkOfR5QQxQdLx4/yMBQMbl1/8cvQTO3J27H49eAqxCALB7Dn1uSgywZwKAXXLoMzcxwN4IAHbDoc9axAB7IADYPAc/owgBtkwAsEkOfc6NGGBrjhd3BQDbcfnMwc95u3NPCLANAoBNcPCzNUKAcycAOFsOffZCDHCOBABnx8HPXgkBzsnx4u7HAoCzcPnsH6OXAKu4c++T0UsAAcB4Dn6qhAAjCQCGcfDDfwkBRnhn9AJocvjD9zwPjGACwKpsdPBqpgGsRQCwCgc/vB0hwNIEAIty8MNphABL8R0AFuPwh9N5jliKCQCzs2HBMkwDmJMJALNy+MNyPF/MyQSAWdiYYF2mAZzqeHH3EwHASS6ffTl6CZB0596j0UtgwwQAN+bgh/MgBLgJ3wHgRhz+cD48j9yECQBvxUYD5800gDd1vLgnAHgzl08d/rAFd+6LAF7PKwDeiMMftsPzyps43jYB4DWubCawSRcmAbyCAOBHOfhhH4QAL+MVAC/l8If98DzzMgKA/2OzgP3xXPNDx9v3HnkFwHeunv599BKABV3c/3T0EjgTJgB8x+EP++c55wUBwOFwsClAieedw0EAcLAZQJHnHgEQZxOALs9/mwAI8/AD9oEuARDloQdesB80CYAgDzvwQ/aFHgEQ4yEHfoz9oUUAhHi4gdexT3Qcb9/71E2AAVdP/zZ6CcCGXNz/xeglsDATgACHP/C27Bv7JwAAIEgA7JyKB27K/rFvx9v3fQdgr66eeHiB01088H2APTIB2CmHPzAX+8k+CYAd8rACc7Ov7I8AAIAgAbAzKh1Yiv1lXwTAjng4gaXZZ/ZjOhyOo9cAwKY4N/bABGAnrp78dfQSgAj7zT4IgB3wMAJrs+9snwAAgCABsHEqHBjF/rNtAgAAggTAhqlvYDT70HYJAAAIEgAbpbqBc2E/2iYBAABBAmCD1DZwbuxL2+MqYABm4jzZEhOAjbl68sXoJQC8lP1pWwQAAARNJjYAzMaZshkmABty9fiL0UsAeCX71HYIAAAIEgAboaqBrbBfbYMAAIAgAQAAQQIAAIKOtx/88nr0Ini1q8d/Gb0EgLd28fCz0UvgFUwAACBo8t9/AJbgfDlvJgAAECQAztw33v8DG2X/Om8CAACCBAAABAkAAAgSAAAQJAAAIOh468Fnfqp5pr55/OfRSwA42e2Hvxq9BF7CBAAAgqbDcfQSANg158xZMgEAgCABAABBAgAAggQAAAQJAAAIOt566B4AAKgxAQCAoMkPNAGgxwQAAIIEAAAECQAACBIAABAkAAAgSAAAQJAAAIAgAQAAQQIAAIIEAAAEuQoYAIIm5z8A9HgFAABBAgAAggQAAAQJAAAIEgAAECQAACBIAABAkAAAgCA3AQJAkAkAAAQJAAAIEgAAECQAACBIAABAkAAAgKDpevQKAIDVmQAAQJAAAIAgNwECQNDk/AeAHq8AACBIAABA0DR6AVXPv/rT6CUAnI1bH/xm9BJyju/+9NeuAliJQx/g9cTAOgTAChz8AG9PCCzLdwAW5vAHuBn757JMABYyxwf3d1/+Z4aVAIz1+0c/OfnfMA2YnwnAAlQrwLzsq/NzEyAAG+G8mpMJwMyef/XH0UsA2CX767wEwIx8OAGWZZ+djwAAgCABMBNVCrAO++08BAAABAkAAAgSADMwjgJYl333dAIAAIIEAAAETYejm5UA2CDn10lMAAAgSAAAQJAAAIAgATCDWx9+PnoJACn23dMJAAAIEgAAECQAZmIcBbAO++08BAAABAmAGalSgGXZZ+cjAGbmwwmwDPvrvKbDwVWKAGyB82pOJgALuPXhb0cvAWBX7KvzO777wefXoxexZ8///YfRSwDYLAf/ckwAFubDC3Az9s9lmQCsyDQA4PUc/OsQAIOIAYDvOfTXJwAAIMh3AAAgSAAAQNDkXgUA6HETIAAEeQUAAEECAACCJr8BBIAeEwAACBIAABAkAAAgSAAAQJAAAIAgAQAAQW4CBIAgEwAACBIAABAkAAAgSAAAQJAAAIAgAQAAQQIAAIIEAAAETe4BAoAeNwECQJBXAAAQJAAAIEgAAECQAACAIAEAAEECAACCBAAABAkAAAgSAAAQJAAAIMhVwAAQZAIAAEECAACCBAAABAkAAAgSAAAQJAAAIEgAAEDQ5BoAAOgxAQCAIDcBAkCQCQAABAkAAAgSAAAQJAAAIEgAAECQAACAIAEAAEHT9egVAACrMwEAgCA3AQJAkAkAAAQJAAAIEgAAECQAACBIAABAkAAAgKDJrwABoMcEAACCBAAABLkJEACCTAAAIEgAAECQAACAIAEAAEECAACCBAAABAkAAAgSAAAQJAAAIEgAAECQq4ABIMgEAACCBAAABAkAAAgSAAAQJAAAIGjyIwAA6DEBAIAgAQAAQQIAAILcBAgAQSYAABAkAAAgSAAAQJAAAIAgAQAAQQIAAIIEAAAECQAACBIAABDkJkAACDIBAIAgAQAAQQIAAIKm69ErAABWZwIAAEGTHwEAQI8JAAAECQAACBIAABDkJkAACDIBAIAgAQAAQQIAAIIEAAAECQAACBIAABAkAAAgSAAAQJAAAIAgAQAAQa4CBoAgEwAACBIAABAkAAAgaPIVAADoMQEAgCABAABBAgAAggQAAAQJAAAIchMgAASZAABAkAAAgCABAABBAgAAggQAAAQJAAAIEgAAECQAACBIAABAkJsAASDIBAAAggQAAAQJAAAImnwFAAB6TAAAIEgAAECQAACAIAEAAEHT9egVAACrcxMgAAR5BQAAQQIAAIIEAAAECQAACBIAABAkAAAgSAAAQJAAAIAgAQAAQQIAAIJcBQwAQSYAABAkAAAgaPIGAAB6TAAAIEgAAECQAACAIAEAAEECAACCBAAABLkJEACCTAAAIEgAAECQAACAIAEAAEECAACCBAAABAkAAAgSAAAQJAAAIMhNgAAQZAIAAEGTAQAA9JgAAECQAACAIAEAAEECAACCBAAABAkAAAgSAAAQ5CZAAAgyAQCAIAEAAEECAACCBAAABE3Xo1cAAKzOBAAAggQAAAQJAAAIEgAAECQAACDIVcAAEDQ5/wGgxysAAAgSAAAQJAAAIEgAAECQAACAIAEAAEECAACCBAAABLkJEACCTAAAIEgAAECQAACAIAEAAEECAACCBAAABAkAAAgSAAAQJAAAIMhNgAAQNDn/AaDHKwAACBIAABAkAAAgSAAAQJAAAIAgAQAAQQIAAIIEAAAEuQkQAIJMAAAgSAAAQJAAAIAgAQAAQQIAAIIEAAAECQAACBIAABAkAAAg6FvHQ6b3pt/m9AAAAABJRU5ErkJggg=="

st.markdown(
    "<script>"
    "(function() {"
    "  document.querySelectorAll('link[rel=\"manifest\"]').forEach(function(el) { el.remove(); });"
    "  var manifestLink = document.createElement('link');"
    "  manifestLink.rel = 'manifest';"
    "  manifestLink.href = 'data:application/manifest+json;base64," + _PWA_MANIFEST_B64 + "';"
    "  document.head.appendChild(manifestLink);"
    "  var iconLink = document.createElement('link');"
    "  iconLink.rel = 'icon';"
    "  iconLink.type = 'image/png';"
    "  iconLink.href = 'data:image/png;base64," + _PWA_ICON192_B64 + "';"
    "  document.head.appendChild(iconLink);"
    "  var appleIconLink = document.createElement('link');"
    "  appleIconLink.rel = 'apple-touch-icon';"
    "  appleIconLink.href = 'data:image/png;base64," + _PWA_APPLE_ICON_B64 + "';"
    "  document.head.appendChild(appleIconLink);"
    "  var metaTags = ["
    "    ['theme-color', '#16213e'],"
    "    ['apple-mobile-web-app-capable', 'yes'],"
    "    ['apple-mobile-web-app-status-bar-style', 'black-translucent'],"
    "    ['apple-mobile-web-app-title', 'MWDTS']"
    "  ];"
    "  metaTags.forEach(function(pair) {"
    "    var m = document.createElement('meta');"
    "    m.name = pair[0];"
    "    m.content = pair[1];"
    "    document.head.appendChild(m);"
    "  });"
    "})();"
    "if ('serviceWorker' in navigator) {"
    "  navigator.serviceWorker.register('./app/static/sw.js').catch(function() {});"
    "}"
    "</script>",
    unsafe_allow_html=True,
)

# -------------------------------
# 26. HANDLE RECURRING TASKS
# -------------------------------
handle_recurring_tasks()

# -------------------------------
# 27. MAIN APP
# -------------------------------
# Defensive: authenticated=True should always mean user_payload is a
# complete dict (login sets both together, see the login success
# block above) — but a stale browser tab left open from before a
# code deploy, or any other edge case that leaves these two out of
# sync, would otherwise crash here with an unhandled KeyError the
# moment the app tries to read a field that isn't there. Reset to a
# clean logged-out state instead, so the person sees a normal
# "please log in again" experience rather than a hard error page.
if not st.session_state.user_payload or "name" not in st.session_state.user_payload:
    _broken_session_token = st.query_params.get("session")
    if _broken_session_token:
        invalidate_session_token(_broken_session_token)
        del st.query_params["session"]
    st.session_state.authenticated = False
    st.session_state.user_payload = None
    st.warning("Your session couldn't be verified — please log in again.")
    st.rerun()

user = st.session_state.user_payload
full_name = user['name']
username = user['username']
role = user['role'].strip().lower()
user_email = user.get('email', None)
avatar_url = user.get('avatar_url', None)

# Modern header
render_logo_bar()
render_poster_slideshow()
render_ticker_bar()
st.markdown('''
<div class="main-header">
    <i class="fas fa-hard-hat"></i> Mine & Workshop Digital Tracker
    <small>Smart Maintenance Management System</small>
</div>
''', unsafe_allow_html=True)
st.markdown('<div class="main-header-spacer"></div>', unsafe_allow_html=True)

# Sidebar
st.markdown('<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">', unsafe_allow_html=True)

try:
    from streamlit_option_menu import option_menu
except ImportError:
    st.error("streamlit-option-menu not installed. Please run: pip install streamlit-option-menu")
    st.stop()

nav_options = ["Task Dashboard", "Help", "Production", "Haulage", "Assets", "Permits", "Inventory", "Incidents",
               "Handover", "Contractors", "Analytics", "Chat", "Feedback", "Admin", "Profile",
               "Timeline", "About", "Wallboard", "Crew Clock", "JSA Library", "Job Plans", "Locations",
               "Electrical Overview", "Motor Rewinds", "Instrument Calibration", "Outage Commander",
               "Transformer Health", "Fault Recorder", "HV Switching Schedule", "Relay Settings",
               "Arc Flash Studies", "Technician Certifications"]
nav_icons = ["list-task", "question-circle-fill", "bar-chart-fill", "truck", "hdd-stack-fill", "shield-lock-fill", "box-seam-fill",
             "exclamation-triangle-fill", "arrow-left-right", "people-fill",
             "graph-up-arrow", "chat-dots-fill", "lightbulb-fill", "gear-fill", "person-circle",
             "clock-history", "info-circle-fill", "tv-fill", "clock-fill", "file-earmark-text-fill",
             "diagram-3-fill", "geo-alt-fill", "bolt-fill", "kanban-fill", "speedometer2", "cone-striped", "lightning-charge-fill",
             "activity", "toggle-on", "sliders", "exclamation-octagon-fill", "award-fill"]

# Hide sections the role has no capability for, so the menu reflects
# actual permissions rather than showing dead ends.
_nav_caps = {
    "Permits": "permit.view",
    "Contractors": "contractor.view",
    "Handover": "handover.view",
    "Analytics": "analytics.view",
    "Admin": "audit.view",
}
_role_lower = st.session_state.user_payload['role'].strip().lower()
_filtered = [(o, i) for o, i in zip(nav_options, nav_icons)
             if o not in _nav_caps or can(_role_lower, _nav_caps[o])]
nav_options = [o for o, _ in _filtered]
nav_icons = [i for _, i in _filtered]

# Feature-flag filtering — separate from the role check above. A
# module can be hidden from EVERYONE (regardless of role) via Owner
# Console -> Admin -> Feature Toggles, without touching any code.
# Applied after the role filter so a disabled module stays hidden
# even from roles that would otherwise see it.
_active_flags = get_cached_feature_flags()
_flag_filtered = [(o, i) for o, i in zip(nav_options, nav_icons)
                  if o not in TOGGLEABLE_MODULES or _active_flags.get(o, True)]
nav_options = [o for o, _ in _flag_filtered]
nav_icons = [i for _, i in _flag_filtered]

# Owner Console — visible ONLY to the configured owner account, and
# gated again inside the section itself. Hiding a menu item is a UX
# nicety, not a security control; the real check is is_owner() below.
_IS_OWNER = is_owner(st.session_state.user_payload.get('username'))
if _IS_OWNER:
    nav_options.insert(1, "Owner Console")
    nav_icons.insert(1, "key-fill")

# REVERTED to option_menu on the person's explicit, informed choice —
# they were told this reintroduces the third-party component's network
# dependency (the exact cause of the "trouble loading the component"
# error from before) and chose the original icon set over the
# guaranteed-reliable native nav anyway. If that error resurfaces, this
# is why, and st.radio (see git history / earlier version of this file)
# is the fix that was in place before this revert.
# Defensive: if a module gets toggled off while someone currently has
# it selected, their persisted nav widget state ("main_nav" in
# session_state) would point at a value no longer in nav_options.
# option_menu's behavior with a stale/invalid persisted value isn't
# something to gamble on, so reset it to the default before it
# renders, rather than find out the hard way.
#
# Display labels are translated per the user's language choice; the
# actual VALUES returned by the widget stay in English (nav_options
# itself is never translated) — every "elif selected_section == "X":"
# check throughout this whole file compares against the English
# canonical name, so translating the underlying values instead of just
# the on-screen labels would break navigation entirely for anyone not
# using English. _label_to_section maps the translated text the widget
# actually returns back to that canonical English value. Built here,
# before the guard below, because "main_nav" in session_state holds
# whatever the widget last returned — a TRANSLATED label, not an
# English one — so the guard has to check against the translated list,
# not the English one, or it would misfire on every render for anyone
# not using English.
_nav_display_labels = [t(f"nav.{section}") for section in nav_options]
_label_to_section = dict(zip(_nav_display_labels, nav_options))

if st.session_state.get("main_nav") not in _nav_display_labels:
    st.session_state.pop("main_nav", None)


with st.sidebar:
    _manual_select = (nav_options.index(st.session_state["_nav_jump_to"])
                      if st.session_state.get("_nav_jump_to") in nav_options else None)
    try:
        _selected_label = option_menu(
            menu_title=None,
            options=_nav_display_labels,
            icons=nav_icons,
            orientation="vertical",
            default_index=0,
            manual_select=_manual_select,
            styles=menu_styles(orientation="vertical"),
            key="main_nav",
        )
    except TypeError:
        # Older streamlit-option-menu versions (pre ~0.3) don't have
        # manual_select. Degrade to the un-jumpable behavior rather than
        # crash the whole app over a nav convenience — upgrade the package
        # (pip install -U streamlit-option-menu) to restore programmatic
        # navigation from sidebar buttons.
        _selected_label = option_menu(
            menu_title=None,
            options=_nav_display_labels,
            icons=nav_icons,
            orientation="vertical",
            default_index=0,
            styles=menu_styles(orientation="vertical"),
            key="main_nav",
        )
    selected_section = _label_to_section.get(_selected_label, _selected_label)
    # Clear immediately after use — this should only force a jump ONCE,
    # not keep overriding every future click within the nav itself.
    st.session_state.pop("_nav_jump_to", None)
    st.markdown("---")

    st.markdown(f"""
    <div class="sidebar-user">
        <i class="fas fa-user-circle user-icon"></i>
        <div class="user-name">{esc(full_name)}</div>
        <div class="user-role">
            <i class="fas fa-id-badge"></i> {user['role']}
            <span class="verified-badge">VERIFIED</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if USING_HARDCODED:
        st.caption('⚠️ Using hardcoded Supabase – set secrets.toml for production')

    # Notifications
    if SUPABASE_AVAILABLE:
        notifications = fetch_notifications(username)
        unread = sum(1 for n in notifications if not n['is_read'])
        if unread > 0:
            st.warning(f"🔔 {unread} unread notification(s)")
            for n in notifications[:3]:
                if not n['is_read']:
                    st.info(f"**{n['title']}**\n{n['body']}")
                    if st.button("Mark as read", key=f"read_{n['id']}"):
                        mark_notification_read(n['id'])
                        st.rerun()

    if st.button("🌓 Toggle Theme", use_container_width=True):
        st.session_state.dark_mode = not st.session_state.dark_mode
        st.rerun()

    _glove_label = "🧤 Glove Mode: ON" if st.session_state.glove_mode else "🧤 Glove Mode: OFF"
    if st.button(_glove_label, use_container_width=True,
                help="Enlarges buttons, inputs, and checkboxes for use with gloves or in low-light conditions."):
        st.session_state.glove_mode = not st.session_state.glove_mode
        st.rerun()

    if can(role, "broadcast.send"):
        st.markdown("---")
        st.markdown("📢 **Send Broadcast**")
        broadcast_msg = st.text_area("Message to all Workers", placeholder="Type your broadcast...")
        if st.button("📤 Send Broadcast", use_container_width=True):
            if broadcast_msg:
                st.session_state.broadcast_messages.append({
                    "sender": full_name,
                    "role": user['role'],
                    "message": broadcast_msg,
                    "timestamp": datetime.now().strftime("%H:%M")
                })
                log_audit(full_name, "broadcast", {"message": broadcast_msg[:50]})
                all_users = fetch_all_users_from_db()
                worker_emails = [u.get('email') for u in all_users if u['role'].strip().lower() == 'worker' and u.get('email')]
                _sent = sum(1 for email in worker_emails
                           if send_email_notification(email, f"Broadcast from {full_name}",
                                                       broadcast_msg.replace('\n', '<br>')))
                send_push_notification("New Broadcast", broadcast_msg[:100])
                if worker_emails and _sent < len(worker_emails):
                    st.warning(f"Broadcast posted, but only {_sent}/{len(worker_emails)} "
                              "emails sent. Check Owner Console → Settings → email health.")
                else:
                    st.success("Broadcast sent!")
                st.rerun()
            else:
                st.error("Message cannot be empty.")

    st.markdown("---")
    st.markdown("💬 **Chat Rooms**")
    if st.button("🌍 Global Chat", use_container_width=True):
        st.session_state.chat_room = "global"
        navigate_to("Chat")
        st.rerun()
    if can(role, "chat.supervisor_room"):
        if st.button("🔒 Supervisor Room", use_container_width=True):
            st.session_state.chat_room = "supervisor"
            navigate_to("Chat")
            st.rerun()

    st.markdown("👤 **Private Chat**")
    all_users = fetch_all_users_from_db()
    other_users = [u["full_name"] for u in all_users if u["full_name"] != full_name and u.get("is_approved", False)]
    if other_users:
        selected_user = st.selectbox("Choose contact", other_users)
        if st.button("🔐 Open Private Chat", use_container_width=True):
            sorted_names = sorted([full_name, selected_user])
            room_name = f"private:{sorted_names[0]}_{sorted_names[1]}"
            st.session_state.chat_room = room_name
            st.session_state.chat_partner = selected_user
            navigate_to("Chat")
            st.rerun()
    else:
        st.info("No other approved users available.")

    st.markdown("---")
    st.markdown("👤 **Profile**")
    if st.button("👤 My Profile", use_container_width=True):
        navigate_to("Profile")
        st.rerun()

    if st.button("🚪 Logout", use_container_width=True):
        log_audit(full_name, "logout")
        _logout_token = st.query_params.get("session")
        if _logout_token:
            invalidate_session_token(_logout_token)
            del st.query_params["session"]
        st.session_state.authenticated = False
        st.session_state.user_payload = None
        st.session_state.chat_room = "global"
        if st.session_state.chat_channel:
            try:
                supabase.remove_channel(st.session_state.chat_channel)
            except:
                pass
            st.session_state.chat_channel = None
        st.rerun()

    st.markdown("---")
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()

if 'profile_tab' not in st.session_state:
    st.session_state.profile_tab = False

db_tasks = fetch_all_tasks()
if db_tasks:
    st.session_state.tasks = db_tasks
else:
    st.session_state.tasks = st.session_state.tasks_memory

# -------------------------------
# 28. TOP-LEVEL NAVIGATION (icon menu)
# -------------------------------
# --- Global search: find a page or a record without hunting through
# every section manually. Deliberately placed above the nav so it's
# reachable from anywhere, on every page, not buried inside one. ---
with st.expander("🔍 Search the app", expanded=False):
    _search_q = st.text_input("Find a page or a record", key="_global_search_q",
                              placeholder="e.g. \"logo\", \"conveyor belt\", or a contractor's name",
                              label_visibility="collapsed")
    if _search_q.strip():
        _feature_hits = search_features(_search_q, nav_options)
        _record_hits = search_records(_search_q, role, full_name)

        if _feature_hits:
            st.caption("Pages")
            for _label, _icon, _target in _feature_hits[:8]:
                if st.button(f"→ {_label}", key=f"search_page_{_target}_{_label}"):
                    navigate_to(_target)
                    st.rerun()

        if _record_hits:
            st.caption("Records")
            for _kind, _title, _subtitle, _target, _rec_id in _record_hits[:15]:
                _btn_label = f"{_kind}: {_title or '(untitled)'}" + (f" — {_subtitle}" if _subtitle else "")
                if st.button(f"→ {_btn_label}", key=f"search_rec_{_kind}_{_rec_id}"):
                    navigate_to(_target)
                    st.rerun()

        if not _feature_hits and not _record_hits:
            st.caption("No matches — try a different word, or check the section directly.")

# Main navigation now renders inside the sidebar (see below) — this
# used to be a horizontal bar here with its own collapse-on-click
# logic, but Streamlit's sidebar already collapses to a hamburger on
# mobile and stays visible on desktop natively, making that whole
# state machine redundant once the nav lives there instead.

st.markdown(
    f'<div class="breadcrumb-bar">'
    f'<div class="crumbs"><i class="fas fa-hard-hat"></i> MWDTS &nbsp;/&nbsp; '
    f'<span class="current">{esc(t(f"nav.{selected_section}"))}</span></div>'
    f'<div class="welcome">Welcome, <b>{esc(full_name)}</b></div>'
    f'</div>',
    unsafe_allow_html=True,
)

# Deep Linking — a URL like ?task=142 jumps directly to that task on
# Task Dashboard, highlighted. st.query_params is the current, stable
# API (available since Streamlit 1.30.0) — verified before using it
# that the older st.experimental_get_query_params is genuinely removed
# in recent Streamlit versions, not just discouraged.
#
# Processed once per session via the _deep_link_processed flag — a
# fresh click on a shared link opens a genuinely new browser
# session/tab (fresh session_state), so this doesn't block a NEW deep
# link from working; it only stops the SAME session from re-triggering
# the jump on every subsequent rerun after the first one already
# handled it.
_deep_link_task = st.query_params.get("task")
if _deep_link_task and not st.session_state.get("_deep_link_processed"):
    st.session_state["_deep_link_processed"] = True
    try:
        _deep_link_task_id = int(_deep_link_task)
        st.session_state["_highlight_task_id"] = _deep_link_task_id
        # Removes just this key, not query_params.clear() — leaves any
        # other query param this app might use in the future untouched.
        del st.query_params["task"]
        if selected_section != "Task Dashboard":
            navigate_to("Task Dashboard")
            st.rerun()
    except (TypeError, ValueError):
        pass

# Single-step back-navigation — remembers only the ONE section you
# were just on, not a full history stack. That's a deliberate choice:
# it correctly handles the actual use case (clicked a Quick Action
# card, want to return to Task Dashboard) without the added
# complexity and edge cases of a real undo-history (cycles, stale
# entries after a role change, etc). Updated only when the section
# actually changes between runs, not on every rerun.
_section_actually_changed = False
if "_last_known_section" not in st.session_state:
    st.session_state["_last_known_section"] = selected_section
elif st.session_state["_last_known_section"] != selected_section:
    st.session_state["previous_section"] = st.session_state["_last_known_section"]
    st.session_state["_last_known_section"] = selected_section
    _section_actually_changed = True

# Dedicated flag, set from TWO places: the generic detection just
# above, and explicitly inside the Back button's own click handler
# below. Needed because Back proactively sets _last_known_section
# itself (to avoid a separate ping-pong bug), which means the generic
# detection above never fires for a Back click — without its own
# explicit flag, Back would silently never scroll to top while every
# other navigation path did.
if _section_actually_changed:
    st.session_state["_scroll_to_top_pending"] = True

if st.session_state.pop("_scroll_to_top_pending", False):
    # Streamlit reruns the whole script on navigation but does NOT
    # reset scroll position — if someone was scrolled down reading
    # the task list and then clicked a Quick Action card, the new
    # section renders while the browser stays scrolled to that same
    # spot, making the new content look like it's stuck "below the
    # tabs" rather than a clean page change. Fires only on an actual
    # section change (this exact flag, not every rerun) — scrolling
    # to top on every interaction within the SAME section, like
    # submitting a form, would be actively annoying, not helpful.
    #
    # components.html(), not st.markdown() — a raw <script> tag inside
    # st.markdown() is NOT reliably executed by Streamlit (confirmed
    # by a report on Streamlit's own community forum of this exact
    # scrollTo-via-markdown approach silently not working). components.html()
    # genuinely runs its JS, but in its own iframe, so window.scrollTo()
    # would scroll that iframe, not the actual page — window.top reaches
    # the outermost window regardless of nesting depth, the same fix
    # already proven for the push-notification postMessage broadcast
    # earlier in this app (which had the same iframe-nesting problem).
    components.html(
        "<script>window.top.scrollTo({top: 0, behavior: 'instant'});</script>",
        height=0,
    )

_prev = st.session_state.get("previous_section")
if _prev and _prev != selected_section and _prev in nav_options:
    if st.button(f"← Back to {t(f'nav.{_prev}')}", key="back_button"):
        navigate_to(_prev)
        st.session_state.pop("previous_section", None)
        st.session_state["_scroll_to_top_pending"] = True
        # Also updated here, not just popped — otherwise the tracking
        # logic above would see selected_section change (to _prev) on
        # the next run and immediately create a NEW previous_section
        # pointing back to where the user just left, turning a clean
        # "go back and you're done" button into an unwanted ping-pong
        # toggle between the two pages.
        st.session_state["_last_known_section"] = _prev
        st.rerun()

# Load shared datasets used across the new modules. Wrapped in a
# spinner deliberately — this runs on every single page load, and
# without an explicit loading state, the moment between "old content
# gone" and "new content ready" can look like a jarring flash rather
# than an intentional, calm loading state. This covers the actual
# data-fetch delay; it can't fully eliminate every visual reset
# Streamlit's rerun-on-every-interaction model produces, since that's
# inherent to the platform's architecture, not something app code can
# switch off — but it replaces the specific gap that was worst.
with st.spinner("Loading…"):
    db_assets = fetch_all_assets()
    st.session_state.assets = db_assets if db_assets else st.session_state.assets_memory
    db_parts = fetch_all_parts()
    st.session_state.parts = db_parts if db_parts else st.session_state.inventory_memory
    db_incidents = fetch_all_incidents()
    st.session_state.incidents = db_incidents if db_incidents else st.session_state.incidents_memory

# ---- TASK DASHBOARD ----
if selected_section == "Task Dashboard":
    # Once-per-session automatic escalation check — NOT a true
    # schedule (Streamlit has no background scheduler), just "runs
    # once when a Superintendent/Owner happens to open this page,"
    # which is the closest honest approximation available without
    # infrastructure outside this app entirely. See Owner Console ->
    # Automation for the manual trigger and the full explanation.
    if (role == "superintendent" or is_owner(username)) and not st.session_state.get("_escalations_checked"):
        st.session_state["_escalations_checked"] = True
        if SUPABASE_AVAILABLE:
            run_escalations(st.session_state.tasks, fetch_permits(), full_name)

    # Active Outage banner — deliberately NOT role-gated like the
    # alerts below (weather, predictive failure, calibration, low
    # stock): an active outage affects everyone on site, not just
    # supervisors, so everyone should see it the moment they open the
    # dashboard, not only people with elevated roles.
    _active_outage_events = fetch_outage_events(active_only=True)
    if _active_outage_events:
        st.error(f"🚧 **{len(_active_outage_events)} active outage(s) in progress** — "
                f"Commander: {', '.join(e['outage_commander'] for e in _active_outage_events)}. "
                f"Go to Outage Commander for the live response.")

    if WEATHER_CONFIGURED:
        _forecast = fetch_weather_forecast()
        _at_risk = weather_sensitive_tasks_at_risk(st.session_state.tasks, _forecast)
        if _at_risk:
            _risk_dates = sorted(set(day["date"] for _, day in _at_risk))
            _risk_task_count = len(set(t["id"] for t, _ in _at_risk))
            st.warning(
                f"🌧️ Rain is forecast with high probability on {', '.join(_risk_dates)} — "
                f"{_risk_task_count} weather-sensitive task(s) may need rescheduling. "
                f"Check Task Dashboard for details."
            )

    # Predictive Failure Alerts — supervisor/superintendent-facing, same
    # role gate as the escalations check above, since this is the same
    # "someone with authority to act on it should see this" audience.
    if role in ("supervisor", "superintendent") or is_owner(username):
        _failure_alerts = get_predictive_failure_alerts(st.session_state.tasks, st.session_state.get("assets", []))
        if _failure_alerts:
            _worst = _failure_alerts[0]
            st.warning(
                f"🔧 **Predictive alert**: {len(_failure_alerts)} asset(s) are approaching their "
                f"typical failure window based on past breakdown history — "
                f"**{esc(_worst['asset_name'])}** is at {_worst['pct_of_window']:.0%} of its usual "
                f"{_worst['mtbf_hours']/24:.0f}-day interval between failures. "
                f"Check Analytics → Reliability for the full list."
            )

        # Instrument Calibration alerts — the entire point of a 7-day
        # warning window is that it's seen without someone having to
        # remember to check the Instrument Calibration page, so this
        # surfaces here too, not only there.
        _cal_overdue = []
        _cal_due_soon = []
        for _c in fetch_instrument_calibrations():
            _, _cal_days, _cal_status = instrument_calibration_status(_c)
            if _cal_status == "overdue":
                _cal_overdue.append(_c)
            elif _cal_status == "due_soon":
                _cal_due_soon.append(_c)
        if _cal_overdue:
            st.error(f"🔴 **{len(_cal_overdue)} instrument(s) overdue for calibration** — "
                    f"check Instrument Calibration for details.")
        if _cal_due_soon:
            st.warning(f"📏 **{len(_cal_due_soon)} instrument(s) due for calibration within 7 days** — "
                      f"check Instrument Calibration for details.")

        # Electrical Critical Spares — same "should be seen without
        # hunting for it" reasoning as the calibration alerts above.
        _low_elec_parts = get_low_stock_electrical_parts(st.session_state.get("parts", []))
        if _low_elec_parts:
            st.warning(f"⚡ **{len(_low_elec_parts)} electrical critical spare(s) at or below reorder "
                      f"point** — check Inventory → Purchase Orders to reorder.")

    if st.session_state.get("_show_welcome"):
        st.markdown(f"""
        <div class="empty-state" style="border-style: solid; border-color: var(--accent); text-align: left;">
            <div style="display: flex; align-items: flex-start; gap: 1rem;">
                <div class="empty-icon" style="margin: 0; flex-shrink: 0;"><i class="fas fa-hand-sparkles"></i></div>
                <div>
                    <div class="empty-title">Welcome to MWDTS, {esc(full_name.split(' ')[0] if full_name else 'there')}</div>
                    <div class="empty-sub">
                        This replaces the paper task boards, incident report books, and permit logs
                        with one system — tasks, permits, incidents, and shift handovers, all in one place.
                        The <b>About</b> page has a full walkthrough whenever you want it.
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Got it, thanks", key="dismiss_welcome"):
            mark_welcome_seen(username)
            st.rerun()

    # My Dashboard (Custom Dashboards) — a curated widget picker, not a
    # general drag-and-drop builder. Deliberately scoped this way:
    # every widget here is an EXISTING analytics function already
    # proven elsewhere in this app (MTBF, cost breakdown, predictive
    # alerts, etc.), not new calculations built just for this feature.
    with st.expander("📊 My Dashboard"):
        _my_widgets = get_user_dashboard_widgets(username)
        _widget_choices = {key: label for key, (label, icon, fn) in DASHBOARD_WIDGET_REGISTRY.items()}
        _selected_labels = st.multiselect(
            "Choose what to show here",
            list(_widget_choices.values()),
            default=[_widget_choices[k] for k in _my_widgets if k in _widget_choices],
            key="dashboard_widget_picker",
        )
        if st.button("💾 Save My Dashboard", key="save_dashboard_widgets"):
            _label_to_key = {v: k for k, v in _widget_choices.items()}
            _new_selection = [_label_to_key[label] for label in _selected_labels]
            set_user_dashboard_widgets(_new_selection, username)
            st.success("Dashboard updated.")
            st.rerun()

        if not _my_widgets:
            st.caption("No widgets selected — choose some above.")
        else:
            _dash_cols = st.columns(2)
            _parts_for_dashboard = {p['id']: p for p in st.session_state.get("parts", [])}
            for _i, _wkey in enumerate(_my_widgets):
                if _wkey not in DASHBOARD_WIDGET_REGISTRY:
                    continue  # a widget removed from the registry since this was saved — skip quietly
                _label, _icon, _render_fn = DASHBOARD_WIDGET_REGISTRY[_wkey]
                with _dash_cols[_i % 2]:
                    st.markdown(f"**{_label}**")
                    _render_fn(st.session_state.tasks, st.session_state.get("assets", []),
                              st.session_state.incidents, _parts_for_dashboard)

    # Quick Actions — the highest-traffic page in the app. Built
    # dynamically from the ACTUAL filtered nav_options (already
    # respects role permissions and Feature Toggles) rather than a
    # hardcoded list — a Worker never sees a shortcut card for Admin
    # or Contractors just because a fixed list included it; whatever
    # already doesn't show in the real nav doesn't show here either.
    _qa_meta = {
        "Production": ("fa-industry", "Log shift output", "ok"),
        "Haulage": ("fa-truck", "Shipments & delivery delays", "warn"),
        "Wallboard": ("fa-tv", "Live site overview", "info"),
        "Crew Clock": ("fa-clock", "Punch in / out for your shift", "ok"),
        "JSA Library": ("fa-file-alt", "Safe work procedures & JSAs", "warn"),
        "Job Plans": ("fa-cubes", "Pre-built work order templates", "info"),
        "Locations": ("fa-sitemap", "Site structure hierarchy", "neutral"),
        "Assets": ("fa-server", "Equipment register & meter readings", "info"),
        "Permits": ("fa-lock", "Permit to Work / LOTO", "warn"),
        "Inventory": ("fa-boxes-stacked", "Spare parts & stock levels", "info"),
        "Incidents": ("fa-triangle-exclamation", "Log a hazard or near-miss", "danger"),
        "Handover": ("fa-right-left", "Shift handover log", "neutral"),
        "Contractors": ("fa-user-group", "Induction & insurance compliance", "info"),
        "Analytics": ("fa-chart-line", "KPIs & performance reports", "ok"),
        "Chat": ("fa-comments", "Message your team", "ok"),
        "Feedback": ("fa-lightbulb", "Suggest an improvement", "info"),
        "Admin": ("fa-gear", "Access, users, and settings", "neutral"),
        "Owner Console": ("fa-key", "Branding, migration, feature toggles", "warn"),
        "Profile": ("fa-circle-user", "Your account & language", "neutral"),
        "Timeline": ("fa-clock-rotate-left", "Recent activity across all tasks", "neutral"),
        "About": ("fa-circle-info", "Policy statement & how it works", "neutral"),
    }
    _quick_actions = [
        {"icon": icon, "title": t(f"nav.{section}"), "desc": desc, "tone": tone, "target": section}
        for section in nav_options
        if section != "Task Dashboard" and section in _qa_meta
        for icon, desc, tone in [_qa_meta[section]]
    ]
    _qa_col1, _qa_col2 = st.columns(2)
    for _i, _qa in enumerate(_quick_actions):
        with (_qa_col1 if _i % 2 == 0 else _qa_col2):
            st.markdown(render_action_cards([_qa]), unsafe_allow_html=True)
            if st.button(f"Open {_qa['title']}", key=f"quick_action_{_qa['target']}", use_container_width=True):
                navigate_to(_qa["target"])
                st.rerun()

    if role == "worker":
        st.markdown('<div class="sub-header"><i class="fas fa-hard-hat"></i> Field Worker Workspace</div>', unsafe_allow_html=True)
        if st.session_state.broadcast_messages:
            st.info(t("task.info_latest_broadcasts"))
            for msg in reversed(st.session_state.broadcast_messages[-5:]):
                st.warning(f"**{msg['sender']}** ({msg['role']}) at {msg['timestamp']}: {msg['message']}")

        worker_sub = option_menu(
            menu_title=None,
            options=["My Assigned Tasks", "Unassigned Board"],
            icons=["clipboard-check", "inbox"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )

        if worker_sub == "My Assigned Tasks":
            my_tasks = [t for t in st.session_state.tasks if t['assigned_to'] == full_name]
            # Fetch permits ONCE for the whole loop instead of per task.
            _all_permits = fetch_permits() if any(t.get('loto') for t in my_tasks) else []
            # Same one-fetch-for-the-whole-loop pattern for linked JSAs —
            # avoids an N+1 query fetching one document per task card.
            _jsa_lookup = {}
            if JSA_LIBRARY_MODULE_AVAILABLE and any(t.get('jsa_document_id') for t in my_tasks):
                _jsa_lookup = {d["id"]: d for d in jsa_library.fetch_jsa_documents()}
            if not my_tasks:
                st.info(t("task.info_no_tasks_assigned"))
            else:
                for idx, task in enumerate(my_tasks):
                    priority_class = f"priority-{task['priority']}"
                    status_class = f"status-{task['status'].replace(' ', '')}"
                    overdue = False
                    if task.get('due_date'):
                        due = _parse_dt(task['due_date'])
                        if due and datetime.now() > due:
                            overdue = True
                    overdue_badge = '<span class="overdue-badge">OVERDUE</span>' if overdue else ''
                    _jsa_doc = _jsa_lookup.get(task.get('jsa_document_id'))
                    _jsa_link_html = (
                        f'<span><i class="fas fa-file-alt"></i> '
                        f'<a href="{esc(_jsa_doc["file_url"])}" target="_blank">{esc(_jsa_doc["title"])}</a></span>'
                        if _jsa_doc else ''
                    )
                    _is_highlighted = st.session_state.get("_highlight_task_id") == task['id']
                    st.markdown(f"""
                    <div class="task-card{' task-card-highlighted' if _is_highlighted else ''}" style="border-top: 4px solid { '#dc2626' if overdue else '#0f3460' };">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                            <div>
                                <div class="task-title">#{task['id']} {esc(task['title'])} {overdue_badge}</div>
                                {f'<p style="margin: 0.3rem 0; color: var(--text-secondary);">{esc(task["description"])}</p>' if task.get('description') else ''}
                                <div class="task-meta">
                                    <span><i class="fas fa-map-marker-alt"></i> {esc(task['location'])}</span>
                                    <span><i class="fas fa-tag"></i> <span class="priority-badge {priority_class}">{task['priority']}</span></span>
                                    <span><i class="fas fa-circle" style="color: #3b82f6;"></i> <span class="status-badge {status_class}">{task['status']}</span></span>
                                    {f'<span><i class="fas fa-calendar-alt"></i> Due: {_fmt_log_time(task["due_date"])}</span>' if task.get('due_date') else ''}
                                    {_jsa_link_html}
                                </div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    with st.expander(f"🔗 {t('task.share_link_label')}"):
                        if APP_URL:
                            st.code(f"{APP_URL}/?task={task['id']}", language=None)
                        else:
                            st.caption("Set `APP_URL` in secrets.toml (Owner Console → deployment settings) "
                                      "to generate a working shareable link.")

                    # Permit gate: if this task requires LOTO, there must be a
                    # live accepted permit before work can be marked in progress.
                    requires_permit = task.get('loto', False)
                    has_permit = task_has_active_permit(task['id'], _all_permits) if requires_permit else True

                    col1, col2 = st.columns([2, 3])
                    with col1:
                        loto = st.checkbox(t("task.chk_loto_isolated"), value=task.get('loto', False), key=f"loto_{task['id']}_{idx}")
                        jsa = st.checkbox(t("task.chk_jsa_signed"), value=task.get('jsa', False), key=f"jsa_{task['id']}_{idx}")
                    with col2:
                        status_options = ["In Progress", "Pending QA", "Blocked", "Complete"]
                        current_idx = status_options.index(task['status']) if task['status'] in status_options else 0
                        new_status = st.selectbox(t("task.field_update_status"), status_options, index=current_idx, key=f"stat_{task['id']}_{idx}")

                    if loto != task.get('loto') or jsa != task.get('jsa'):
                        update_task(task['id'], {"loto": loto, "jsa": jsa}, full_name)
                        st.rerun()

                    if requires_permit and not has_permit:
                        st.error(t("task.err_permit_required"))
                    elif not loto or not jsa:
                        st.error(t("task.err_safety_forms_required"))
                    else:
                        st.success(t("task.success_safety_checks"))

                    # Closing out work: capture the data the analytics depend on.
                    if new_status != task['status']:
                        if new_status == "Complete":
                            with st.form(f"close_out_{task['id']}_{idx}", clear_on_submit=True):
                                st.markdown(t("task.txt_closeout_details"))
                                fc_options = ["(none)"] + [f"{k} — {v}" for k, v in FAILURE_CODES.items()]
                                fc_sel = st.selectbox(t("task.field_failure_code"), fc_options)
                                lh = st.number_input("Labour hours spent", min_value=0.0, value=0.0, step=0.5)
                                confirm_close = st.form_submit_button("✅ Complete Task")
                                if confirm_close:
                                    closing = {"status": new_status, "labour_hours": lh}
                                    if fc_sel != "(none)":
                                        closing["failure_code"] = fc_sel.split(" — ")[0]
                                    update_task(task['id'], closing, full_name)
                                    log_audit(full_name, "task_status_change",
                                              {"task_id": task['id'], "new_status": new_status})
                                    st.rerun()
                        else:
                            if requires_permit and not has_permit and new_status == "In Progress":
                                st.error(t("task.err_cannot_move_progress"))
                            else:
                                update_task(task['id'], {"status": new_status}, full_name)
                                log_audit(full_name, "task_status_change",
                                          {"task_id": task['id'], "new_status": new_status})
                                st.rerun()

                    with st.expander("💬 Comments"):
                        comments = fetch_comments(task['id'])
                        if comments:
                            for c in comments:
                                st.markdown(f"**{c['posted_by']}** ({_fmt_log_time(c['posted_at'])}): {c['comment']}")
                        else:
                            st.caption(t("task.caption_no_comments"))
                        _comment_val_key = f"_comment_val_{task['id']}_{idx}"
                        if _comment_val_key not in st.session_state:
                            st.session_state[_comment_val_key] = ""
                        new_comment = st.text_area(t("task.field_add_comment"), key=f"comment_{task['id']}_{idx}",
                                                   value=st.session_state[_comment_val_key],
                                                   placeholder="Write comment...")
                        if st.button(t("task.btn_post_comment"), key=f"post_comment_{task['id']}_{idx}"):
                            if new_comment.strip():
                                if add_comment(task['id'], new_comment, full_name):
                                    st.session_state[_comment_val_key] = ""
                                    st.rerun()
                                else:
                                    st.error(t("task.err_comment_failed"))

                    with st.expander("📎 Attachments"):
                        attachments = fetch_attachments(task['id'])
                        if attachments:
                            for a in attachments:
                                st.markdown(f"[{a['file_name']}]({a['file_url']}) (uploaded by {a['uploaded_by']})")
                        else:
                            st.caption(t("task.caption_no_attachments"))
                        uploaded_file = st.file_uploader("Upload attachment (PDF, DOC, etc.)", type=ALLOWED_ATTACHMENT_EXTENSIONS, key=f"attach_{task['id']}_{idx}")
                        if uploaded_file is not None:
                            if st.button(t("task.btn_upload_attachment"), key=f"attach_btn_{task['id']}_{idx}"):
                                bytes_data = uploaded_file.getvalue()
                                if upload_attachment(task['id'], bytes_data, uploaded_file.name, full_name):
                                    st.success(t("task.success_attachment"))
                                    st.rerun()

                    st.markdown("---")
                    st.markdown('<i class="fas fa-camera"></i> **Upload Proof Photo**', unsafe_allow_html=True)
                    uploaded_file = st.file_uploader(f"Choose an image for task #{task['id']}", type=["jpg", "jpeg", "png", "gif", "webp", "bmp"], key=f"upload_{task['id']}_{idx}")
                    if uploaded_file is not None:
                        if st.button(f"📤 Upload for Task #{task['id']}", key=f"upload_btn_{task['id']}_{idx}"):
                            bytes_data = uploaded_file.getvalue()
                            success = upload_photo(task['id'], bytes_data, uploaded_file.name, full_name)
                            if success:
                                st.success(t("task.success_photo"))
                                st.rerun()
                            else:
                                st.error(t("task.err_upload_failed"))
                    photos = fetch_photos(task['id'])
                    if photos:
                        st.markdown(t("task.txt_already_uploaded"))
                        cols = st.columns(min(4, len(photos)))
                        for pic_idx, photo in enumerate(photos):
                            with cols[pic_idx % len(cols)]:
                                img_url = photo.get('photo_url', '')
                                if img_url.startswith('memory://'):
                                    st.info(f"📷 {photo.get('uploaded_by', 'Unknown')} uploaded a photo")
                                else:
                                    st.image(img_url, width=120, use_container_width=True)
                                st.caption(f"By {photo.get('uploaded_by', 'Unknown')}")
                    st.markdown("---")

        elif worker_sub == "Unassigned Board":
            unassigned = [t for t in st.session_state.tasks if t['assigned_to'] == "Unassigned" or t['status'] == "Unassigned"]
            if not unassigned:
                st.success(t("task.success_no_unassigned"))
            else:
                for task in unassigned:
                    priority_class = f"priority-{task['priority']}"
                    overdue = False
                    if task.get('due_date'):
                        due = _parse_dt(task['due_date'])
                        if due and datetime.now() > due:
                            overdue = True
                    overdue_badge = '<span class="overdue-badge">OVERDUE</span>' if overdue else ''
                    _is_highlighted = st.session_state.get("_highlight_task_id") == task['id']
                    st.markdown(f"""
                    <div class="task-card{' task-card-highlighted' if _is_highlighted else ''}" style="border-top: 4px solid { '#dc2626' if overdue else '#0f3460' };">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <div class="task-title">#{task['id']} {esc(task['title'])} {overdue_badge}</div>
                                <div class="task-meta">
                                    <span><i class="fas fa-map-marker-alt"></i> {esc(task['location'])}</span>
                                    <span><i class="fas fa-tag"></i> <span class="priority-badge {priority_class}">{task['priority']}</span></span>
                                    {f'<span><i class="fas fa-calendar-alt"></i> Due: {_fmt_log_time(task["due_date"])}</span>' if task.get('due_date') else ''}
                                </div>
                            </div>
                            <div>
                                <span class="status-badge status-Unassigned">Unassigned</span>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

    elif role == "supervisor":
        st.markdown('<div class="sub-header"><i class="fas fa-clipboard"></i> Supervisor Operations Desk</div>', unsafe_allow_html=True)
        supervisor_sub = option_menu(
            menu_title=None,
            options=["Manage All Tasks", "Create New Task", "Dashboard"],
            icons=["list-check", "plus-circle", "pie-chart-fill"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )
        if supervisor_sub == "Manage All Tasks":
            st.markdown(f"### {t('task.hdr_all_tasks')}")
            all_users = fetch_all_users_from_db()
            worker_names = ["Unassigned"] + [u["full_name"] for u in all_users if u["role"].strip().lower() == "worker" and u.get("is_approved", False)]

            _subsection_filter = st.selectbox(
                "Filter by Electrical Dept. subsection",
                ["All", "Electrical Workshop", "Carbonate Plant", "Auto Electricals"],
                key="task_mgmt_subsection_filter")
            _tasks_to_show = st.session_state.tasks
            if _subsection_filter != "All":
                _tasks_to_show = [t2 for t2 in _tasks_to_show if t2.get("subsection") == _subsection_filter]

            if not _tasks_to_show:
                st.info(t("task.info_no_tasks_found"))
            for task in _tasks_to_show:
                priority_class = f"priority-{task['priority']}"
                status_class = f"status-{task['status'].replace(' ', '')}"
                overdue = False
                if task.get('due_date'):
                    due = _parse_dt(task['due_date'])
                    if due and datetime.now() > due:
                        overdue = True
                overdue_badge = '<span class="overdue-badge">OVERDUE</span>' if overdue else ''
                _mgmt_task_chips = render_meta_chips([
                    ("fa-map-marker-alt", task.get('location'), "neutral"),
                    ("fa-calendar-alt", _fmt_log_time(task['due_date']) if task.get('due_date') else None,
                    "danger" if overdue else "neutral"),
                    ("fa-bolt", task.get('subsection'), "info"),
                ])
                st.markdown(f"""
                <div class="custom-card" style="border-left-color: { '#dc2626' if overdue else '#0f3460' };">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>#{task['id']}: {esc(task['title'])} {overdue_badge}</strong>
                            <span class="status-badge {status_class}">{task['status']}</span>
                            <span class="priority-badge {priority_class}">{task['priority']}</span>
                            {_mgmt_task_chips}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                cols = st.columns([3, 1, 1])
                current_assign = task['assigned_to'] if task['assigned_to'] in worker_names else "Unassigned"
                new_assign = cols[0].selectbox("Assign to:", worker_names,
                                               index=worker_names.index(current_assign),
                                               key=f"assign_{task['id']}")
                if new_assign != task['assigned_to']:
                    update_task(task['id'], {"assigned_to": new_assign}, full_name)
                    if task['status'] == "Unassigned" and new_assign != "Unassigned":
                        update_task(task['id'], {"status": "In Progress"}, full_name)
                    log_audit(full_name, "task_assign", {"task_id": task['id'], "assigned_to": new_assign})
                    if new_assign != "Unassigned":
                        worker_email = next((u.get('email') for u in all_users if u['full_name'] == new_assign), None)
                        if worker_email:
                            subject = f"New Task Assigned: #{task['id']} - {task['title']}"
                            body = f"Hello {new_assign},<br><br>You have been assigned task <b>#{task['id']}</b>: {task['title']}.<br>Location: {task['location']}<br>Priority: {task['priority']}<br>Due: {task.get('due_date', 'No due date')}<br><br>Please log in to the tracker for details.<br>Regards,<br>Supervisor"
                            send_email_notification(worker_email, subject, body)
                        send_push_notification("New Task Assigned", f"Task #{task['id']}: {task['title']}")
                        send_notification(new_assign, "Task Assigned", f"Task #{task['id']}: {task['title']}")
                    st.rerun()
                if task['status'] == "Pending QA":
                    if cols[1].button("✅ Approve & Close", key=f"approve_{task['id']}"):
                        update_task(task['id'], {"status": "Complete"}, full_name)
                        log_audit(full_name, "task_approve", {"task_id": task['id']})
                        st.rerun()
                with st.expander("💬 Comments"):
                    comments = fetch_comments(task['id'])
                    if comments:
                        for c in comments:
                            st.markdown(f"**{c['posted_by']}** ({_fmt_log_time(c['posted_at'])}): {c['comment']}")
                    else:
                        st.caption(t("task.caption_no_comments"))
                    _comment_val_key = f"_comment_val_sup_{task['id']}"
                    if _comment_val_key not in st.session_state:
                        st.session_state[_comment_val_key] = ""
                    new_comment = st.text_area(t("task.field_add_comment"), key=f"comment_sup_{task['id']}",
                                               value=st.session_state[_comment_val_key],
                                               placeholder="Write comment...")
                    if st.button(t("task.btn_post_comment"), key=f"post_comment_sup_{task['id']}"):
                        if new_comment.strip():
                            if add_comment(task['id'], new_comment, full_name):
                                st.session_state[_comment_val_key] = ""
                                st.rerun()
                            else:
                                st.error(t("task.err_comment_failed"))
                with st.expander("📎 Attachments"):
                    attachments = fetch_attachments(task['id'])
                    if attachments:
                        for a in attachments:
                            st.markdown(f"[{a['file_name']}]({a['file_url']}) (by {a['uploaded_by']})")
                    else:
                        st.caption(t("task.caption_no_attachments"))
                    uploaded_file = st.file_uploader("Upload attachment", type=ALLOWED_ATTACHMENT_EXTENSIONS, key=f"attach_sup_{task['id']}")
                    if uploaded_file is not None:
                        if st.button(t("task.btn_upload"), key=f"attach_btn_sup_{task['id']}"):
                            bytes_data = uploaded_file.getvalue()
                            if upload_attachment(task['id'], bytes_data, uploaded_file.name, full_name):
                                st.success(t("task.success_attachment"))
                                st.rerun()
                photos = fetch_photos(task['id'])
                if photos:
                    with st.expander(f"📸 Photos for Task #{task['id']}"):
                        cols = st.columns(min(4, len(photos)))
                        for idx, photo in enumerate(photos):
                            with cols[idx % len(cols)]:
                                img_url = photo.get('photo_url', '')
                                if img_url.startswith('memory://'):
                                    st.info(f"📷 {photo.get('uploaded_by', 'Unknown')} uploaded a photo")
                                else:
                                    st.image(img_url, width=120)
                                st.caption(f"By {photo.get('uploaded_by', 'Unknown')}")

        elif supervisor_sub == "Create New Task":
            st.markdown(f"### {t('task.hdr_dispatch_new')}")

            # Outside the form deliberately — st.form() only reruns on
            # its own submit button, so an "Expand with AI" click INSIDE
            # the form couldn't show its result until the whole form was
            # submitted, defeating the point of previewing it first.
            if AI_FEATURES_AVAILABLE:
                with st.expander("✨ Smart Work Order Description (optional)"):
                    st.caption("Type a brief, rough note — AI will expand it into a clearer description "
                              "you can review and edit below before creating the task.")
                    _brief_notes = st.text_input("Brief notes", key="smart_desc_brief")
                    if st.button("✨ Expand with AI", key="smart_desc_expand_btn"):
                        if _brief_notes.strip():
                            with st.spinner("Generating description..."):
                                _expanded = generate_smart_work_order_description(_brief_notes)
                            if _expanded:
                                st.session_state["_smart_description_result"] = _expanded
                                st.rerun()
                            else:
                                st.error("Couldn't generate a description right now — you can still write "
                                         "one directly in the Description field below.")
                        else:
                            st.warning("Enter some brief notes first.")

            _location_options = get_location_path_options()
            with st.form("new_task_form", clear_on_submit=True):
                title = st.text_input(t("task.field_task_title"), max_chars=100)
                description = st.text_area(
                    "Description (optional)",
                    value=st.session_state.pop("_smart_description_result", ""),
                    help="A fuller description of the work — the AI expander above can help draft this.")
                if _location_options:
                    location = selectbox_with_other(t("task.field_location"), _location_options,
                                                    key_prefix="task_location")
                else:
                    location = st.text_input(t("task.field_location"), max_chars=100)
                priority = st.selectbox(t("task.field_priority"), ["Low", "Medium", "High", "Critical"])
                due_date = st.date_input("Due Date", value=datetime.now() + timedelta(days=7))
                asset_options = ["None"] + [f"#{a['id']} {a['name']}" for a in st.session_state.get("assets", [])]
                selected_asset = st.selectbox(t("task.field_linked_asset"), asset_options)
                work_type = st.selectbox(t("task.field_work_type"), ["Reactive", "Preventive", "Planned", "Predictive", "Improvement"],
                                          help="Drives the planned-vs-reactive benchmark. Reactive = breakdown response.")
                subsection = st.selectbox(
                    "Electrical Dept. Subsection (optional)",
                    ["None", "Electrical Workshop", "Carbonate Plant", "Auto Electricals"],
                    help="Only relevant for Electrical Department work — leave as None for tasks "
                        "elsewhere on site. Lets the team see workload split across the three areas.")
                labour_rate = st.number_input("Labour rate (per hour, for costing)", min_value=0.0, value=0.0, step=1.0)
                is_recurring = st.checkbox(t("task.chk_recurring"))
                recurrence_type = st.selectbox(t("task.field_recurrence"), ["daily", "weekly", "monthly", "meter-based"], disabled=not is_recurring)
                recurrence_end_date = st.date_input("End Date (optional)", value=datetime.now() + timedelta(days=30), disabled=not is_recurring)
                meter_interval = st.number_input("Meter Interval (e.g. every N hours, only if meter-based)", min_value=0, value=0, disabled=not is_recurring)
                loto = st.checkbox(t("task.chk_requires_loto"))
                jsa = st.checkbox(t("task.chk_requires_jsa"))
                weather_sensitive_flag = st.checkbox("🌧️ Weather-sensitive (flag if adverse weather is forecast)")
                jsa_document_id = None
                if JSA_LIBRARY_MODULE_AVAILABLE:
                    _jsa_docs = jsa_library.fetch_jsa_documents()
                    if _jsa_docs:
                        _jsa_choices = {"None": None}
                        _jsa_choices.update({d["title"]: d["id"] for d in _jsa_docs})
                        _jsa_pick = st.selectbox(
                            "📄 Link a specific JSA/SWP (optional)", list(_jsa_choices.keys()),
                            help="Workers see this exact document on the task, instead of guessing "
                                "which paper file applies.")
                        jsa_document_id = _jsa_choices[_jsa_pick]
                    else:
                        st.caption("No JSA documents in the library yet — add one under JSA Library first.")
                submitted = st.form_submit_button('➕ Create Work Ticket')
                if submitted:
                    if title and location:
                        asset_id = None
                        if selected_asset != "None":
                            asset_id = int(selected_asset.split(" ")[0].replace("#", ""))
                        new_task = create_task(
                            title, location, priority, loto, jsa, full_name,
                            due_date=due_date,
                            is_recurring=is_recurring,
                            recurrence_type=recurrence_type if is_recurring else None,
                            recurrence_end_date=recurrence_end_date if is_recurring else None,
                            asset_id=asset_id,
                            meter_interval=meter_interval if (is_recurring and recurrence_type == "meter-based") else None,
                            work_type=work_type,
                            labour_rate=labour_rate,
                            weather_sensitive=weather_sensitive_flag,
                            jsa_document_id=jsa_document_id,
                            description=description.strip() if description and description.strip() else None,
                            subsection=subsection if subsection != "None" else None,
                        )
                        if new_task:
                            st.success(f"Task #{new_task['id']} created!")
                            st.rerun()
                        elif st.session_state.pop("_last_error_was_connectivity", False):
                            st.error(friendly_db_error("connection timeout"))
                        else:
                            st.error(t("task.err_create_failed"))
                    else:
                        st.error(t("task.err_title_location_required"))

        elif supervisor_sub == "Dashboard":
            st.markdown(f"### {t('task.hdr_task_analytics')}")
            tasks = st.session_state.tasks
            st.markdown(f"#### {t('task.hdr_kpis')}")
            kcol1, kcol2, kcol3, kcol4 = st.columns(4)
            mttr, mttr_n = compute_mttr_hours_v2(tasks)
            kcol1.metric("MTTR (avg hrs)", f"{mttr:.1f}" if mttr is not None else "No data")
            pm_compliance, pm_n = compute_pm_compliance_v2(tasks)
            kcol2.metric("PM Compliance", f"{pm_compliance}%" if pm_compliance is not None else "No data")
            open_incidents = sum(1 for i in st.session_state.get("incidents", []) if i.get("status") in ("Open", "Investigating"))
            kcol3.metric("Open Incidents", open_incidents)
            low_stock_count = sum(1 for p in st.session_state.get("parts", []) if p.get('quantity_on_hand', 0) <= p.get('reorder_point', 0))
            kcol4.metric("Low Stock Parts", low_stock_count)
            if mttr_n and mttr_n < 10:
                st.caption(f"⚠️ MTTR is based on only {mttr_n} completed task(s) — indicative, not yet reliable.")
            st.caption(t("task.caption_full_breakdowns"))
            st.markdown("---")
            if tasks and PANDAS_AVAILABLE and PLOTLY_AVAILABLE:
                df = pd.DataFrame(tasks)
                fig1 = px.pie(df, names='status', title='Tasks by Status', color_discrete_sequence=GMC_CHART_COLORS)
                st.plotly_chart(fig1, use_container_width=True)
                fig2 = px.bar(df, x='priority', color='status', title='Tasks by Priority and Status', color_discrete_sequence=GMC_CHART_COLORS)
                st.plotly_chart(fig2, use_container_width=True)
                if 'created_at' in df.columns:
                    df['created_at'] = pd.to_datetime(df['created_at'])
                    df['day'] = df['created_at'].dt.date
                    fig3 = px.line(df.groupby('day').size().reset_index(name='count'), x='day', y='count', title='Tasks Created Per Day', color_discrete_sequence=GMC_CHART_COLORS)
                    st.plotly_chart(fig3, use_container_width=True)
            elif not PANDAS_AVAILABLE or not PLOTLY_AVAILABLE:
                st.warning(t("task.warn_plotly"))
            else:
                st.info(t("task.info_no_data"))
            if st.button(t("task.btn_export_csv")):
                csv = export_tasks_csv(st.session_state.tasks)
                if csv:
                    st.download_button("Download CSV", data=csv, file_name="tasks_export.csv", mime="text/csv")

    elif role == "superintendent":
        st.markdown('<div class="sub-header"><i class="fas fa-hard-hat"></i> Superintendent Control Centre</div>', unsafe_allow_html=True)
        superintendent_sub = option_menu(
            menu_title=None,
            options=["Overview", "Manage Tasks", "Broadcast Log", "Dashboard", "User Management"],
            icons=["pie-chart-fill", "list-check", "megaphone-fill", "graph-up-arrow", "people-fill"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )
        if superintendent_sub == "Overview":
            total = len(st.session_state.tasks)
            completed = sum(1 for t in st.session_state.tasks if t['status'] == "Complete")
            in_progress = sum(1 for t in st.session_state.tasks if t['status'] == "In Progress")
            unassigned = sum(1 for t in st.session_state.tasks if t['assigned_to'] == "Unassigned" or t['status'] == "Unassigned")
            blocked = sum(1 for t in st.session_state.tasks if t['status'] == "Blocked")
            render_stat_cards([
                {"icon": "fa-clipboard-list", "label": "Total Tasks", "value": total, "tone": "info"},
                {"icon": "fa-circle-check", "label": "Completed", "value": completed, "tone": "ok"},
                {"icon": "fa-gears", "label": "In Progress", "value": in_progress, "tone": "info"},
                {"icon": "fa-inbox", "label": "Unassigned", "value": unassigned, "tone": "neutral"},
                {"icon": "fa-ban", "label": "Blocked", "value": blocked, "tone": "danger"},
            ])

            down_assets = sum(1 for a in st.session_state.get("assets", []) if a.get('status') == 'Down')
            low_stock_count = sum(1 for p in st.session_state.get("parts", []) if p.get('quantity_on_hand', 0) <= p.get('reorder_point', 0))
            open_incidents = sum(1 for i in st.session_state.get("incidents", []) if i.get("status") in ("Open", "Investigating"))
            render_stat_cards([
                {"icon": "fa-hard-hat", "label": "Registered Assets", "value": len(st.session_state.get("assets", [])), "tone": "neutral"},
                {"icon": "fa-triangle-exclamation", "label": "Assets Down", "value": down_assets, "tone": "danger"},
                {"icon": "fa-boxes-stacked", "label": "Low Stock Parts", "value": low_stock_count, "tone": "danger"},
                {"icon": "fa-bell", "label": "Open Incidents", "value": open_incidents, "tone": "warn"},
            ])

            st.markdown(f"### {t('task.hdr_recent_broadcasts')}")
            if st.session_state.broadcast_messages:
                for msg in reversed(st.session_state.broadcast_messages[-3:]):
                    st.info(f"**{msg['sender']}** at {msg['timestamp']}: {msg['message']}")
            else:
                st.caption(t("task.caption_no_broadcasts"))

        elif superintendent_sub == "Manage Tasks":
            st.markdown(f"### {t('task.hdr_full_control')}")
            all_users = fetch_all_users_from_db()
            worker_names = ["Unassigned"] + [u["full_name"] for u in all_users if u["role"].strip().lower() == "worker" and u.get("is_approved", False)]
            if not st.session_state.tasks:
                st.info(t("task.info_no_tasks_manage"))
            for task in st.session_state.tasks:
                priority_class = f"priority-{task['priority']}"
                status_class = f"status-{task['status'].replace(' ', '')}"
                overdue = False
                if task.get('due_date'):
                    due = _parse_dt(task['due_date'])
                    if due and datetime.now() > due:
                        overdue = True
                overdue_badge = '<span class="overdue-badge">OVERDUE</span>' if overdue else ''
                _mgmt_task_chips = render_meta_chips([
                    ("fa-map-marker-alt", task.get('location'), "neutral"),
                    ("fa-calendar-alt", _fmt_log_time(task['due_date']) if task.get('due_date') else None,
                    "danger" if overdue else "neutral"),
                ])
                st.markdown(f"""
                <div class="custom-card" style="border-left-color: { '#dc2626' if overdue else '#0f3460' };">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>#{task['id']}: {esc(task['title'])} {overdue_badge}</strong>
                            <span class="status-badge {status_class}">{task['status']}</span>
                            <span class="priority-badge {priority_class}">{task['priority']}</span>
                            {_mgmt_task_chips}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                cols = st.columns([2, 1, 1, 1])
                current_assign = task['assigned_to'] if task['assigned_to'] in worker_names else "Unassigned"
                new_assign = cols[0].selectbox("Assign", worker_names,
                                               index=worker_names.index(current_assign),
                                               key=f"sup_assign_{task['id']}")
                if new_assign != task['assigned_to']:
                    update_task(task['id'], {"assigned_to": new_assign}, full_name)
                    if task['status'] == "Unassigned" and new_assign != "Unassigned":
                        update_task(task['id'], {"status": "In Progress"}, full_name)
                    log_audit(full_name, "task_assign", {"task_id": task['id'], "assigned_to": new_assign})
                    if new_assign != "Unassigned":
                        worker_email = next((u.get('email') for u in all_users if u['full_name'] == new_assign), None)
                        if worker_email:
                            subject = f"New Task Assigned: #{task['id']} - {task['title']}"
                            body = f"Hello {new_assign},<br><br>You have been assigned task <b>#{task['id']}</b>: {task['title']}.<br>Location: {task['location']}<br>Priority: {task['priority']}<br>Due: {task.get('due_date', 'No due date')}<br><br>Please log in to the tracker for details.<br>Regards,<br>Superintendent"
                            send_email_notification(worker_email, subject, body)
                        send_push_notification("New Task Assigned", f"Task #{task['id']}: {task['title']}")
                        send_notification(new_assign, "Task Assigned", f"Task #{task['id']}: {task['title']}")
                    st.rerun()
                status_opts = ["Unassigned", "In Progress", "Pending QA", "Blocked", "Complete"]
                curr_stat_idx = status_opts.index(task['status']) if task['status'] in status_opts else 0
                new_stat = cols[1].selectbox("Status", status_opts, index=curr_stat_idx, key=f"stat_ovr_{task['id']}")
                if new_stat != task['status']:
                    update_task(task['id'], {"status": new_stat}, full_name)
                    log_audit(full_name, "task_status_change", {"task_id": task['id'], "new_status": new_stat})
                    st.rerun()
                if cols[2].button('🗑️ Delete', key=f"del_{task['id']}"):
                    if delete_task(task['id'], full_name):
                        st.rerun()
                    else:
                        st.error(t("task.err_delete_failed"))
                with st.expander("💬 Comments"):
                    comments = fetch_comments(task['id'])
                    if comments:
                        for c in comments:
                            st.markdown(f"**{c['posted_by']}** ({_fmt_log_time(c['posted_at'])}): {c['comment']}")
                    else:
                        st.caption(t("task.caption_no_comments"))
                    _comment_val_key = f"_comment_val_sup_{task['id']}"
                    if _comment_val_key not in st.session_state:
                        st.session_state[_comment_val_key] = ""
                    new_comment = st.text_area(t("task.field_add_comment"), key=f"comment_sup_{task['id']}",
                                               value=st.session_state[_comment_val_key],
                                               placeholder="Write comment...")
                    if st.button(t("task.btn_post_comment"), key=f"post_comment_sup_{task['id']}"):
                        if new_comment.strip():
                            if add_comment(task['id'], new_comment, full_name):
                                st.session_state[_comment_val_key] = ""
                                st.rerun()
                            else:
                                st.error(t("task.err_comment_failed"))
                with st.expander("📎 Attachments"):
                    attachments = fetch_attachments(task['id'])
                    if attachments:
                        for a in attachments:
                            st.markdown(f"[{a['file_name']}]({a['file_url']}) (by {a['uploaded_by']})")
                    else:
                        st.caption(t("task.caption_no_attachments"))
                    uploaded_file = st.file_uploader("Upload attachment", type=ALLOWED_ATTACHMENT_EXTENSIONS, key=f"attach_sup_{task['id']}")
                    if uploaded_file is not None:
                        if st.button(t("task.btn_upload"), key=f"attach_btn_sup_{task['id']}"):
                            bytes_data = uploaded_file.getvalue()
                            if upload_attachment(task['id'], bytes_data, uploaded_file.name, full_name):
                                st.success(t("task.success_attachment"))
                                st.rerun()
                photos = fetch_photos(task['id'])
                if photos:
                    with st.expander(f"📸 Photos for Task #{task['id']}"):
                        cols = st.columns(min(4, len(photos)))
                        for idx, photo in enumerate(photos):
                            with cols[idx % len(cols)]:
                                img_url = photo.get('photo_url', '')
                                if img_url.startswith('memory://'):
                                    st.info(f"📷 {photo.get('uploaded_by', 'Unknown')} uploaded a photo")
                                else:
                                    st.image(img_url, width=120)
                                st.caption(f"By {photo.get('uploaded_by', 'Unknown')}")

        elif superintendent_sub == "Broadcast Log":
            st.markdown(f"### {t('task.hdr_all_broadcasts')}")
            if st.session_state.broadcast_messages:
                for msg in reversed(st.session_state.broadcast_messages):
                    st.write(f"**{msg['sender']}** ({msg['role']}) at {msg['timestamp']}: {msg['message']}")
            else:
                st.info(t("task.info_no_messages"))

        elif superintendent_sub == "Dashboard":
            st.markdown(f"### {t('task.hdr_task_analytics')}")
            tasks = st.session_state.tasks
            st.markdown(f"#### {t('task.hdr_kpis')}")
            kcol1, kcol2, kcol3, kcol4 = st.columns(4)
            mttr, mttr_n = compute_mttr_hours_v2(tasks)
            kcol1.metric("MTTR (avg hrs)", f"{mttr:.1f}" if mttr is not None else "No data")
            pm_compliance, pm_n = compute_pm_compliance_v2(tasks)
            kcol2.metric("PM Compliance", f"{pm_compliance}%" if pm_compliance is not None else "No data")
            open_incidents = sum(1 for i in st.session_state.get("incidents", []) if i.get("status") in ("Open", "Investigating"))
            kcol3.metric("Open Incidents", open_incidents)
            low_stock_count = sum(1 for p in st.session_state.get("parts", []) if p.get('quantity_on_hand', 0) <= p.get('reorder_point', 0))
            kcol4.metric("Low Stock Parts", low_stock_count)
            if mttr_n and mttr_n < 10:
                st.caption(f"⚠️ MTTR is based on only {mttr_n} completed task(s) — indicative, not yet reliable.")
            st.caption(t("task.caption_full_breakdowns"))
            st.markdown("---")
            if tasks and PANDAS_AVAILABLE and PLOTLY_AVAILABLE:
                df = pd.DataFrame(tasks)
                fig1 = px.pie(df, names='status', title='Tasks by Status', color_discrete_sequence=GMC_CHART_COLORS)
                st.plotly_chart(fig1, use_container_width=True)
                fig2 = px.bar(df, x='priority', color='status', title='Tasks by Priority and Status', color_discrete_sequence=GMC_CHART_COLORS)
                st.plotly_chart(fig2, use_container_width=True)
                if 'created_at' in df.columns:
                    df['created_at'] = pd.to_datetime(df['created_at'])
                    df['day'] = df['created_at'].dt.date
                    fig3 = px.line(df.groupby('day').size().reset_index(name='count'), x='day', y='count', title='Tasks Created Per Day', color_discrete_sequence=GMC_CHART_COLORS)
                    st.plotly_chart(fig3, use_container_width=True)
            elif not PANDAS_AVAILABLE or not PLOTLY_AVAILABLE:
                st.warning(t("task.warn_plotly"))
            else:
                st.info(t("task.info_no_data"))
            if st.button(t("task.btn_export_csv")):
                csv = export_tasks_csv(st.session_state.tasks)
                if csv:
                    st.download_button("Download CSV", data=csv, file_name="tasks_export.csv", mime="text/csv")

        elif superintendent_sub == "User Management":
            st.markdown(f"### {t('task.hdr_user_directory')}")
            # Access decisions moved to the owner-only console. Granting
            # roles is the most privilege-sensitive action in the app, so
            # it sits with one accountable person rather than with every
            # Superintendent.
            if is_owner(username):
                st.info(t("task.info_owner_note"))
            else:
                st.info(t("task.info_readonly_directory"))

            all_users = fetch_all_users_from_db()
            pending_users = [u for u in all_users if not u.get("is_approved", False)
                             and not u.get("is_suspended", False)]
            approved_users = [u for u in all_users if u.get("is_approved", False)
                              and not u.get("is_suspended", False)]
            suspended_users = [u for u in all_users if u.get("is_suspended", False)]

            _uc1, _uc2, _uc3 = st.columns(3)
            _uc1.metric("Active users", len(approved_users))
            _uc2.metric("Pending approval", len(pending_users))
            _uc3.metric("Suspended", len(suspended_users))

            if pending_users:
                st.warning(f"⏳ {len(pending_users)} request(s) awaiting the owner's decision.")

            st.markdown(f"#### {t('task.hdr_active_users')}")
            if approved_users:
                st.dataframe([{
                    "Name": u.get("full_name"),
                    "Username": u.get("username"),
                    "Role": u.get("role"),
                    "Job Title": u.get("job_title") or "—",
                    "Department": u.get("department") or "—",
                } for u in approved_users], use_container_width=True)
            else:
                st.info(t("task.info_no_active_users"))

            if suspended_users:
                st.markdown(f"#### {t('task.hdr_suspended')}")
                for u in suspended_users:
                    st.write(f"- {esc(u.get('full_name'))} (`{esc(u.get('username'))}`)")


# ---- ASSET REGISTER ----
elif selected_section == "Production":
    st.subheader("🏭 Production Tracking")
    st.caption("Shift-by-shift output — logged by supervisors, visible to everyone.")
    can_log_production = can(role, "handover.create")

    _prod_tabs = ["Recent Shifts", "Summary"]
    if can_log_production:
        _prod_tabs.append("Log Production")
    prod_sub = option_menu(
        menu_title=None, options=_prod_tabs,
        icons=["clock-history", "bar-chart-fill", "plus-circle"][:len(_prod_tabs)],
        orientation="horizontal", default_index=0, styles=menu_styles(),
    )

    if prod_sub == "Recent Shifts":
        _prod_records = fetch_production_records(limit=100)
        if not _prod_records:
            render_empty_state("fa-industry", "No production logged yet",
                              "Shift output will show here once a supervisor logs the first record.")
        else:
            _prod_search = st.text_input("🔍 Search by material or location", "", key="prod_search")
            _prod_display = quick_filter(_prod_records, _prod_search, ["material_type", "location"])
            for _pr in _prod_display:
                with st.container(border=True):
                    _pcol1, _pcol2 = st.columns([5, 1])
                    with _pcol1:
                        st.markdown(f"**{_pr.get('material_type')}** — "
                                   f"{_pr.get('quantity'):,.1f} {_pr.get('unit')}")
                        st.markdown(render_meta_chips([
                            ("fa-calendar", _pr.get("production_date"), "neutral"),
                            ("fa-clock", _pr.get("shift"), "info"),
                            ("fa-map-marker-alt", _pr.get("location"), "neutral"),
                            ("fa-user", _pr.get("recorded_by"), "neutral"),
                        ]), unsafe_allow_html=True)
                        if _pr.get("notes"):
                            st.caption(_pr["notes"])
                    with _pcol2:
                        if can_log_production and st.button("🗑️", key=f"del_prod_{_pr['id']}"):
                            if delete_production_record(_pr["id"], full_name):
                                st.rerun()

    elif prod_sub == "Summary":
        _summary_records = fetch_production_records(limit=500)
        if not _summary_records:
            st.info("No production data yet to summarize.")
        else:
            _totals = production_totals_by_date(_summary_records)
            _material_totals = {}
            for _date_totals in _totals.values():
                for (_mat, _unit), _qty in _date_totals.items():
                    _key = f"{_mat} ({_unit})"
                    _material_totals[_key] = _material_totals.get(_key, 0) + _qty
            st.markdown("#### Total by material")
            _mcols = st.columns(min(len(_material_totals), 4) or 1)
            for _i, (_mat_label, _qty) in enumerate(_material_totals.items()):
                _mcols[_i % len(_mcols)].metric(_mat_label, f"{_qty:,.1f}")

            if PANDAS_AVAILABLE and PLOTLY_AVAILABLE:
                _chart_rows = []
                for _date, _mats in _totals.items():
                    for (_mat, _unit), _qty in _mats.items():
                        _chart_rows.append({"Date": _date, "Material": _mat, "Quantity": _qty})
                if _chart_rows:
                    _dfp = pd.DataFrame(_chart_rows)
                    st.plotly_chart(px.bar(_dfp, x="Date", y="Quantity", color="Material",
                                          title="Daily production by material",
                                          color_discrete_sequence=GMC_CHART_COLORS),
                                    use_container_width=True)

    elif prod_sub == "Log Production":
        st.markdown("### Log Shift Production")
        with st.form("log_production_form", clear_on_submit=True):
            _prod_date = st.date_input("Production date", datetime.now().date())
            _prod_shift = st.selectbox("Shift", ["Day Shift", "Night Shift", "Swing Shift",
                                                 "Weekend Day", "Weekend Night"])
            _prod_location = st.text_input("Location / Pit")
            _prod_material = st.text_input("Material type *", placeholder="e.g. Manganese Ore, Waste Rock")
            _pcol1, _pcol2 = st.columns(2)
            with _pcol1:
                _prod_qty = st.number_input("Quantity *", min_value=0.0, value=0.0, step=1.0)
            with _pcol2:
                _prod_unit = st.selectbox("Unit", ["tonnes", "m³", "loads"])
            _prod_notes = st.text_area("Notes")
            _prod_grade = st.number_input(
                "Ore grade % (optional — leave at 0 if not applicable, e.g. for waste rock)",
                min_value=0.0, max_value=100.0, value=0.0, step=0.1)
            if st.form_submit_button("📝 Log production"):
                if not _prod_material.strip():
                    st.error("Material type is required.")
                elif _prod_qty <= 0:
                    st.error("Quantity must be greater than zero.")
                elif log_production(_prod_date, _prod_shift, _prod_location, _prod_material.strip(),
                                   _prod_qty, _prod_unit, _prod_notes, full_name,
                                   ore_grade_pct=(_prod_grade if _prod_grade > 0 else None)):
                    st.success("Production logged.")
                    st.rerun()
                else:
                    st.error("Failed to log production — check the error log.")

elif selected_section == "Haulage":
    st.subheader("🚚 Haulage & Logistics")
    st.caption("Shipment tracking from mine to port/railway — flags delays by comparing "
              "actual arrival against what was expected, not by guesswork.")
    can_manage_haulage = can(role, "handover.create")

    _haul_tabs = ["Active Shipments", "Delivered"]
    if can_manage_haulage:
        _haul_tabs.append("New Shipment")
    haul_sub = option_menu(
        menu_title=None, options=_haul_tabs,
        icons=["truck", "check-circle", "plus-circle"][:len(_haul_tabs)],
        orientation="horizontal", default_index=0, styles=menu_styles(),
    )

    if haul_sub == "Active Shipments":
        _active_shipments = [s for s in fetch_shipments() if s.get("status") in ("Scheduled", "In Transit")]
        if not _active_shipments:
            render_empty_state("fa-truck", "No active shipments",
                              "Scheduled and in-transit shipments will show here.")
        else:
            for _s in _active_shipments:
                with st.container(border=True):
                    _scol1, _scol2 = st.columns([4, 2])
                    with _scol1:
                        st.markdown(f"**{_s['shipment_ref']}** — {_s.get('material_type')} "
                                   f"({_s.get('quantity'):,.1f} {_s.get('unit')})")
                        st.markdown(render_meta_chips([
                            ("fa-route", _s.get("destination"), "neutral"),
                            ("fa-truck-moving", _s.get("transport_mode"), "info"),
                            ("fa-building", _s.get("carrier"), "neutral"),
                            ("fa-clock", f"Expected {_fmt_log_time(_s['expected_arrival'])}"
                            if _s.get("expected_arrival") else None, "warn"),
                        ]), unsafe_allow_html=True)
                        _s_status_tone = "info" if _s["status"] == "In Transit" else "neutral"
                        st.markdown(f"<span class='status-badge' style='background:var(--tone-{_s_status_tone});'>"
                                   f"{esc(_s['status'])}</span>", unsafe_allow_html=True)
                    with _scol2:
                        if can_manage_haulage:
                            if _s["status"] == "Scheduled" and st.button("🚛 Mark departed", key=f"depart_{_s['id']}"):
                                if mark_shipment_departed(_s["id"], full_name):
                                    st.rerun()
                            if _s["status"] == "In Transit":
                                _delay_note = st.text_input("Delay reason (if any)", key=f"delay_note_{_s['id']}",
                                                            label_visibility="collapsed",
                                                            placeholder="Leave blank if on time")
                                if st.button("✅ Mark arrived", key=f"arrive_{_s['id']}"):
                                    if mark_shipment_arrived(_s["id"], _delay_note, full_name):
                                        st.rerun()

    elif haul_sub == "Delivered":
        _delivered = [s for s in fetch_shipments(status="Delivered") if s]
        if not _delivered:
            st.info("No delivered shipments logged yet.")
        else:
            _avg_delay = average_delay_hours(_delivered)
            if _avg_delay is not None:
                _dcol1, _dcol2 = st.columns(2)
                _dcol1.metric("Average delay", f"{_avg_delay:+.1f} hours",
                             help="Positive = late on average, negative = early on average.")
                _late_count = sum(1 for s in _delivered if (shipment_delay_hours(s) or 0) > 0)
                _dcol2.metric("Late shipments", f"{_late_count} / {len(_delivered)}")
            for _s in _delivered:
                _delay = shipment_delay_hours(_s)
                with st.container(border=True):
                    st.markdown(f"**{_s['shipment_ref']}** — {_s.get('material_type')} "
                               f"({_s.get('quantity'):,.1f} {_s.get('unit')})")
                    st.markdown(render_meta_chips([
                        ("fa-route", _s.get("destination"), "neutral"),
                        ("fa-clock", f"Arrived {_fmt_log_time(_s['actual_arrival'])}"
                        if _s.get("actual_arrival") else None, "neutral"),
                        ("fa-hourglass-half", f"{_delay:+.1f}h vs expected" if _delay is not None else None,
                        "danger" if (_delay or 0) > 0 else "ok"),
                    ]), unsafe_allow_html=True)
                    if _s.get("delay_reason"):
                        st.caption(f"Note: {_s['delay_reason']}")

    elif haul_sub == "New Shipment":
        st.markdown("### Schedule a Shipment")
        with st.form("new_shipment_form", clear_on_submit=True):
            _sh_material = st.text_input("Material type *", placeholder="e.g. Manganese Ore")
            _scol1, _scol2 = st.columns(2)
            with _scol1:
                _sh_qty = st.number_input("Quantity *", min_value=0.0, value=0.0, step=1.0)
            with _scol2:
                _sh_unit = st.selectbox("Unit", ["tonnes", "m³", "loads"])
            _sh_mode = st.selectbox("Transport mode", ["Truck", "Rail"])
            _sh_destination = st.text_input("Destination *", placeholder="e.g. Takoradi Port")
            _sh_carrier = st.text_input("Carrier / operator")
            _sh_expected = st.date_input("Expected arrival date")
            _sh_expected_time = st.time_input("Expected arrival time")
            if st.form_submit_button("📦 Schedule shipment"):
                if not _sh_material.strip() or not _sh_destination.strip():
                    st.error("Material type and destination are required.")
                elif _sh_qty <= 0:
                    st.error("Quantity must be greater than zero.")
                else:
                    _expected_dt = datetime.combine(_sh_expected, _sh_expected_time)
                    _new_shipment = create_shipment(_sh_material.strip(), _sh_qty, _sh_unit, _sh_mode,
                                                   _sh_destination.strip(), _sh_carrier, _expected_dt, full_name)
                    if _new_shipment:
                        st.success(f"Shipment {_new_shipment['shipment_ref']} scheduled.")
                        st.rerun()
                    else:
                        st.error("Failed to schedule shipment — check the error log.")

elif selected_section == "Assets":
    st.subheader("🏭 Asset Register")
    can_manage_assets = can(role, "asset.edit")

    _asset_sub_options = ["All Assets"]
    _asset_sub_icons = ["hdd-stack-fill"]
    if QR_SCANNING_AVAILABLE:
        _asset_sub_options.append("📷 Scan Asset")
        _asset_sub_icons.append("qr-code-scan")
    _asset_sub_options.append("📁 Document Library")
    _asset_sub_icons.append("folder-fill")
    if can_manage_assets:
        _asset_sub_options.append("Add Asset")
        _asset_sub_icons.append("plus-circle")

    if len(_asset_sub_options) > 1:
        asset_sub = option_menu(
            menu_title=None,
            options=_asset_sub_options,
            icons=_asset_sub_icons,
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )
    else:
        asset_sub = "All Assets"

    if asset_sub == "📷 Scan Asset":
        st.caption("Take a photo of an asset's printed QR label to jump straight to its record.")
        _scan_photo = st.camera_input("Scan QR label", label_visibility="collapsed")
        if _scan_photo is not None:
            _decoded_id = decode_asset_qr(_scan_photo.getvalue())
            if _decoded_id is None:
                st.error("No MWDTS asset label found in that photo — try holding the camera "
                        "steadier and closer to the label, with good lighting.")
            else:
                _matched = next((a for a in st.session_state.assets if a.get("id") == _decoded_id), None)
                if _matched is None:
                    st.error(f"Scanned a valid label (asset #{_decoded_id}), but no asset with "
                            "that ID exists anymore — it may have been deleted.")
                else:
                    st.success(f"Found: {_matched.get('name')}")
                    st.markdown(render_meta_chips([
                        ("fa-tag", f"Tag: {_matched['asset_tag']}" if _matched.get('asset_tag') else None, "neutral"),
                        ("fa-map-marker-alt", _matched.get('location'), "neutral"),
                        ("fa-flag", f"Status: {_matched.get('status', 'Operational')}", "info"),
                    ]), unsafe_allow_html=True)

    elif asset_sub == "📁 Document Library":
        st.markdown("### 📁 Document Library")
        st.caption("SOPs, manuals, and asset documentation — viewable by everyone.")

        _doc_search = st.text_input("🔍 Search by title or description", "", key="doc_search")
        _docs = search_documents(_doc_search) if _doc_search.strip() else fetch_all_documents()

        if not _docs:
            render_empty_state("fa-folder-open", "No documents yet",
                              "Upload SOPs, manuals, or asset documentation to build the library.")
        else:
            _asset_lookup_docs = {a["id"]: a.get("name") for a in st.session_state.assets}
            for _doc in _docs:
                with st.container(border=True):
                    st.markdown(f"**{esc(_doc.get('title'))}** — v{_doc.get('version', 1)}")
                    st.markdown(render_meta_chips([
                        ("fa-server", _asset_lookup_docs.get(_doc.get("asset_id")), "neutral"),
                        ("fa-user", _doc.get("uploaded_by"), "neutral"),
                        ("fa-clock", _fmt_log_time(_doc["created_at"]) if _doc.get("created_at") else None, "neutral"),
                    ]), unsafe_allow_html=True)
                    if _doc.get("description"):
                        st.caption(_doc["description"])
                    st.markdown(f"[📄 Open document]({_doc['file_url']})")

        if can_manage_assets:
            with st.expander("⬆️ Upload a document"):
                with st.form("upload_doc_form", clear_on_submit=True):
                    _doc_title = st.text_input("Title *")
                    _doc_desc = st.text_area("Description")
                    _doc_asset_choices = {"None (general document)": None}
                    _doc_asset_choices.update({a["name"]: a["id"] for a in st.session_state.assets})
                    _doc_asset_label = st.selectbox("Linked asset (optional)", list(_doc_asset_choices.keys()))
                    _doc_file = st.file_uploader("File", type=["pdf", "docx", "doc", "png", "jpg", "jpeg"])
                    if st.form_submit_button("Upload"):
                        if not _doc_title.strip():
                            st.error("Title is required.")
                        elif not _doc_file:
                            st.error("Please choose a file.")
                        elif upload_document(_doc_file.getvalue(), _doc_file.name, _doc_title.strip(),
                                            _doc_desc, _doc_asset_choices[_doc_asset_label], full_name):
                            st.success("Document uploaded.")
                            st.rerun()
                        else:
                            st.error("Upload failed — check the error log.")

    elif asset_sub == "All Assets":
        assets = st.session_state.assets
        if not assets:
            render_empty_state("fa-server", "No assets registered yet", "Add your first asset to start tracking maintenance history and meter readings.")
        else:
            search = st.text_input("🔍 Search by name, tag, or location", "")
            filtered = assets
            if search:
                s = search.lower()
                filtered = [a for a in assets if s in str(a.get('name', '')).lower()
                            or s in str(a.get('asset_tag', '')).lower()
                            or s in str(a.get('location', '')).lower()]
            for a in filtered:
                status_class = f"asset-status-{a.get('status', 'Operational').replace(' ', '')}"
                _asset_chips = render_meta_chips([
                    ("fa-tag", f"Tag: {a['asset_tag']}" if a.get('asset_tag') else None, "neutral"),
                    ("fa-map-marker-alt", a.get('location'), "neutral"),
                    ("fa-industry", f"{a.get('manufacturer', '')} {a.get('model_number', '')}".strip() or None, "info"),
                    ("fa-tachometer-alt", f"Meter: {a.get('current_meter', 0)} {a.get('meter_unit', '')}".strip()
                    if a.get('current_meter') is not None else None, "info"),
                ])
                st.markdown(f"""
                <div class="custom-card">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>#{a['id']}: {esc(a.get('name'))}</strong>
                            <span class="asset-status-badge {status_class}">{esc(a.get('status', 'Operational'))}</span>
                            <span class="priority-badge priority-{esc(a.get('criticality', 'Medium'))}">{esc(a.get('criticality', 'Medium'))}</span>
                            {_asset_chips}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if QR_GENERATION_AVAILABLE:
                    with st.expander(f"🔲 Print QR Label — {a.get('name')}"):
                        st.caption("Print this and attach it to the physical equipment. Scanning "
                                  "it later (Assets → Scan Asset) jumps straight to this record.")
                        _qr_img = generate_asset_qr(a['id'])
                        if _qr_img is not None:
                            st.image(_qr_img, width=200)
                            _qr_buf = BytesIO()
                            _qr_img.save(_qr_buf, format="PNG")
                            st.download_button("⬇ Download label", data=_qr_buf.getvalue(),
                                              file_name=f"asset_{a['id']}_qr.png", mime="image/png",
                                              key=f"qr_dl_{a['id']}")
                if can_manage_assets:
                    with st.expander(f"⚙️ Manage #{a['id']} {a.get('name')}"):
                        cols = st.columns(4)
                        new_status = cols[0].selectbox("Status", ["Operational", "Down", "Maintenance", "Retired"],
                                                        index=["Operational", "Down", "Maintenance", "Retired"].index(a.get('status', 'Operational')) if a.get('status') in ["Operational", "Down", "Maintenance", "Retired"] else 0,
                                                        key=f"asset_stat_{a['id']}")
                        new_meter = cols[1].number_input("Current Meter Reading", value=float(a.get('current_meter', 0) or 0), key=f"asset_meter_{a['id']}")
                        if cols[2].button("💾 Save", key=f"asset_save_{a['id']}"):
                            update_asset(a['id'], {"status": new_status, "current_meter": new_meter}, full_name)
                            st.success("Asset updated.")
                            st.rerun()
                        if can(role, "asset.delete") and cols[3].button("🗑️ Delete", key=f"asset_del_{a['id']}"):
                            delete_asset(a['id'], full_name)
                            st.rerun()
                        related_tasks = [t for t in st.session_state.tasks if t.get('asset_id') == a['id']]
                        st.caption(f"📋 {len(related_tasks)} maintenance task(s) linked to this asset.")

                        st.markdown("**📈 Meter Reading History**")
                        readings = fetch_meter_readings(a['id'])
                        rate = meter_usage_rate(a['id'], readings)
                        if rate is not None:
                            st.caption(f"Observed usage: **{rate:.1f} {a.get('meter_unit','units')}/day** "
                                       f"(from {len(readings)} readings)")
                        elif len(readings) < 2:
                            st.caption("Log at least two readings over time to calculate a usage rate.")
                        if detect_meter_anomaly(a["id"]):
                            st.warning("⚠️ The latest meter reading is a statistical outlier compared to "
                                      "recent history — worth double-checking it was entered correctly, "
                                      "or investigating whether something genuinely changed with this asset.")
                        if readings and PANDAS_AVAILABLE and PLOTLY_AVAILABLE:
                            dfm = pd.DataFrame(readings)
                            dfm['recorded_at'] = pd.to_datetime(dfm['recorded_at'], errors='coerce')
                            st.plotly_chart(px.line(dfm, x='recorded_at', y='reading',
                                                     title=f"Meter trend — {a.get('name')}",
                                                     color_discrete_sequence=GMC_CHART_COLORS),
                                            use_container_width=True, key=f"meter_chart_{a['id']}")
                        mr_cols = st.columns([2, 2, 1])
                        new_reading = mr_cols[0].number_input(
                            f"New reading ({a.get('meter_unit','units')})",
                            value=float(a.get('current_meter', 0) or 0),
                            key=f"mr_val_{a['id']}")
                        mr_note = mr_cols[1].text_input("Note (optional)", key=f"mr_note_{a['id']}")
                        if mr_cols[2].button("📝 Log", key=f"mr_btn_{a['id']}"):
                            if new_reading < float(a.get('current_meter', 0) or 0):
                                st.error("New reading is lower than the current reading. "
                                         "Meters normally only increase — correct the value, or note a meter replacement.")
                            else:
                                if log_meter_reading(a['id'], new_reading, a.get('meter_unit'), full_name, mr_note):
                                    st.success("Reading logged.")
                                    st.rerun()
                                else:
                                    st.error("Failed to log reading. Check Row Level Security "
                                            "on the meter_readings table.")
                        meter_tasks = [t for t in related_tasks if t.get('meter_interval')]
                        for mt in meter_tasks:
                            interval = mt.get('meter_interval', 0)
                            current = a.get('current_meter', 0) or 0
                            if interval and current and (current % interval) >= (interval * 0.9):
                                st.warning(f"⏰ '{mt['title']}' is meter-based (every {interval} {a.get('meter_unit', '')}) and is approaching its next service interval.")

    # PM compliance quick view for managers
    if can_manage_assets and st.session_state.assets:
        st.markdown("---")
        if st.button("📥 Export Assets as CSV"):
            csv = export_assets_csv(st.session_state.assets)
            if csv:
                st.download_button("Download CSV", data=csv, file_name="assets_export.csv", mime="text/csv", key="dl_assets_csv")

        st.markdown("#### 📊 Asset Task Frequency (proxy for downtime)")
        ranking = compute_asset_downtime_ranking(st.session_state.tasks, st.session_state.assets)
        if ranking:
            for name, count in ranking[:10]:
                st.write(f"- **{esc(name)}**: {count} maintenance task(s)")
        else:
            st.caption("No tasks linked to assets yet.")

    elif asset_sub == "Add Asset":
        st.markdown("### Register New Asset")
        with st.form("new_asset_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Asset Name *", max_chars=100)
                asset_tag = st.text_input("Asset Tag / ID *", max_chars=50)
                category = selectbox_with_other("Category",
                    ["Heavy Equipment", "Fixed Plant", "Vehicle", "Electrical",
                     "Hydraulic", "Conveyor", "Pump"], key_prefix="asset_category")
                location = st.text_input("Location / Area *", max_chars=100)
                criticality = st.selectbox("Criticality", ["Low", "Medium", "High", "Critical"])
            with c2:
                manufacturer = st.text_input("Manufacturer", max_chars=100)
                model_number = st.text_input("Model Number", max_chars=100)
                serial_number = st.text_input("Serial Number", max_chars=100)
                install_date = st.date_input("Install Date", value=datetime.now())
                status = st.selectbox("Status", ["Operational", "Down", "Maintenance", "Retired"])
            colm1, colm2 = st.columns(2)
            current_meter = colm1.number_input("Current Meter Reading", value=0.0)
            meter_unit = colm2.selectbox("Meter Unit", ["hours", "km", "cycles", "N/A"])
            submitted = st.form_submit_button("➕ Register Asset")
            if submitted:
                if name and asset_tag and location:
                    new_asset = create_asset(name, asset_tag, category, location, manufacturer, model_number,
                                              serial_number, install_date, status, criticality,
                                              current_meter, meter_unit, full_name)
                    if new_asset:
                        st.success(f"Asset '{name}' registered!")
                        st.rerun()
                    else:
                        st.error("Failed to register asset.")
                else:
                    st.error("Asset Name, Tag, and Location are required.")

# ---- INVENTORY ----
elif selected_section == "Inventory":
    st.subheader("📦 Inventory & Parts Management")
    can_manage_inventory = can(role, "inventory.adjust")

    if can_manage_inventory:
        inv_sub = option_menu(
            menu_title=None,
            options=["Stock Levels", "Add Part", "Record Usage", "Purchase Orders", "Bill of Materials"],
            icons=["box-seam-fill", "plus-circle", "dash-circle", "cart-check", "list-check"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )
    else:
        inv_sub = "Stock Levels"

    parts = st.session_state.parts

    if inv_sub == "Stock Levels":
        low_stock = [p for p in parts if p.get('quantity_on_hand', 0) <= p.get('reorder_point', 0)]
        if low_stock:
            st.warning(f"⚠️ {len(low_stock)} part(s) at or below reorder point.")
        if can_manage_inventory and parts and st.button("📥 Export Inventory as CSV"):
            csv = export_inventory_csv(parts)
            if csv:
                st.download_button("Download CSV", data=csv, file_name="inventory_export.csv", mime="text/csv", key="dl_inventory_csv")
        if not parts:
            render_empty_state("fa-boxes-stacked", "No parts in inventory yet", "Add spare parts to track stock levels and set reorder points.")
        else:
            _inv_search = st.text_input("🔍 Search by part name, number, or bin location", "", key="inv_search")
            parts = quick_filter(parts, _inv_search, ["part_name", "part_number", "bin_location"])
        for p in parts:
            is_low = p.get('quantity_on_hand', 0) <= p.get('reorder_point', 0)
            stock_class = "stock-low" if is_low else "stock-ok"
            stock_label = "LOW STOCK" if is_low else "IN STOCK"
            _part_chips = render_meta_chips([
                ("fa-cubes", f"Qty on hand: {p.get('quantity_on_hand', 0)}", "danger" if is_low else "ok"),
                ("fa-bell", f"Reorder at: {p.get('reorder_point', 0)}", "neutral"),
                ("fa-map-marker-alt", f"Bin: {p['bin_location']}" if p.get('bin_location') else None, "neutral"),
                ("fa-truck", p.get('supplier'), "info"),
                ("fa-dollar-sign", f"Unit cost: {p['unit_cost']}" if p.get('unit_cost') is not None else None, "info"),
            ])
            st.markdown(f"""
            <div class="custom-card">
                <strong>{esc(p.get('part_name'))}</strong> ({esc(p.get('part_number', 'N/A'))})
                <span class="stock-badge {stock_class}">{stock_label}</span>
                {_part_chips}
            </div>
            """, unsafe_allow_html=True)
            if can_manage_inventory:
                cols = st.columns(4)
                restock_qty = cols[0].number_input("Restock qty", min_value=0, value=0, key=f"restock_{p['id']}")
                if cols[1].button("📥 Restock", key=f"restock_btn_{p['id']}"):
                    if restock_qty > 0:
                        adjust_part_quantity(p['id'], restock_qty, full_name, reason="restock")
                        st.success("Stock updated.")
                        st.rerun()
                if can(role, "inventory.delete") and cols[2].button("🗑️ Delete", key=f"part_del_{p['id']}"):
                    delete_part(p['id'], full_name)
                    st.rerun()

    elif inv_sub == "Add Part":
        st.markdown("### Add New Part to Inventory")
        with st.form("new_part_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                part_name = st.text_input("Part Name *", max_chars=100)
                part_number = st.text_input("Part Number", max_chars=50)
                category = selectbox_with_other("Category",
                    ["Bearings", "Belts", "Filters", "Hydraulic", "Electrical",
                     "Fasteners", "Seals", "Lubricants"], key_prefix="part_category")
                supplier = st.text_input("Supplier", max_chars=100)
            with c2:
                quantity_on_hand = st.number_input("Starting Quantity", min_value=0, value=0)
                reorder_point = st.number_input("Reorder Point", min_value=0, value=5)
                reorder_qty = st.number_input("Reorder Quantity", min_value=0, value=10)
                unit_cost = st.number_input("Unit Cost", min_value=0.0, value=0.0, format="%.2f")
            bin_location = st.text_input("Bin / Shelf Location", max_chars=50)
            submitted = st.form_submit_button("➕ Add Part")
            if submitted:
                if part_name:
                    new_part = create_part(part_name, part_number, category, quantity_on_hand, reorder_point,
                                            reorder_qty, unit_cost, supplier, bin_location, full_name)
                    if new_part:
                        st.success(f"Part '{part_name}' added to inventory!")
                        st.rerun()
                    else:
                        st.error("Failed to add part.")
                else:
                    st.error("Part Name is required.")

    elif inv_sub == "Record Usage":
        st.markdown("### Record Parts Used on a Task")
        if not parts:
            st.info("No parts available. Add parts to inventory first.")
        elif not st.session_state.tasks:
            st.info("No tasks available to link parts to.")
        else:
            with st.form("use_part_form", clear_on_submit=True):
                part_names = {f"{p['part_name']} ({p.get('part_number', 'N/A')}) - {p.get('quantity_on_hand', 0)} in stock": p['id'] for p in parts}
                task_titles = {f"#{t['id']} {t['title']}": t['id'] for t in st.session_state.tasks}
                selected_part_label = st.selectbox("Part", list(part_names.keys()))
                selected_task_label = st.selectbox("Task / Work Order", list(task_titles.keys()))
                qty_used = st.number_input("Quantity Used", min_value=1, value=1)
                submitted = st.form_submit_button("✅ Record Usage")
                if submitted:
                    part_id = part_names[selected_part_label]
                    task_id = task_titles[selected_task_label]
                    if link_part_to_task(task_id, part_id, qty_used, full_name):
                        st.success("Parts usage recorded and stock updated.")
                        st.rerun()
                    else:
                        st.error("Failed to record usage.")

    elif inv_sub == "Purchase Orders":
        st.markdown("### 📑 Purchase Orders")
        suppliers = fetch_suppliers()

        _low_elec = get_low_stock_electrical_parts(st.session_state.get("parts", []))
        if _low_elec:
            st.warning(f"⚡ **{len(_low_elec)} electrical critical spare(s) at or below reorder point**: " +
                      ", ".join(p["part_name"] for p in _low_elec))
            if suppliers and st.button("🛒 Pre-fill PO with these parts"):
                # Populates the SAME line-item mechanism the manual form
                # below already uses — not a separate, parallel PO
                # creation path — so this always goes through the same
                # human review/edit/submit step, never bypasses it.
                if "po_line_items" not in st.session_state:
                    st.session_state.po_line_items = []
                _supplier_by_name = {s["company_name"].strip().lower(): s["id"] for s in suppliers}
                for p in _low_elec:
                    st.session_state.po_line_items.append({
                        "part_id": p["id"],
                        "part_label": f"{p['part_name']} ({p.get('part_number', 'N/A')})",
                        "quantity": p.get("reorder_qty") or 1,
                        "unit_price": p.get("unit_cost") or 0.0,
                    })
                    # Only pre-selects a supplier when the part's free-text
                    # supplier name exactly matches a real supplier record —
                    # guessing at a close-but-not-exact match risks silently
                    # ordering from the wrong supplier, which a human
                    # reviewing the form before submitting would catch but
                    # an unattended auto-match could get wrong.
                    _part_supplier = (p.get("supplier") or "").strip().lower()
                    if _part_supplier in _supplier_by_name:
                        st.session_state["po_supplier_select"] = next(
                            s["company_name"] for s in suppliers
                            if s["company_name"].strip().lower() == _part_supplier)
                st.success(f"{len(_low_elec)} part(s) added to the line items below — review "
                          "quantities and prices, confirm the supplier, then create the order.")
                st.rerun()

        with st.expander("➕ Add a new supplier"):
            with st.form("add_supplier_form", clear_on_submit=True):
                _s_name = st.text_input("Company name *")
                _s_contact = st.text_input("Contact person")
                _s_email = st.text_input("Email")
                _s_phone = st.text_input("Phone")
                if st.form_submit_button("Add supplier"):
                    if not _s_name.strip():
                        st.error("Company name is required.")
                    elif create_supplier(_s_name.strip(), _s_contact, _s_email, _s_phone, full_name):
                        st.success(f"Supplier '{_s_name}' added.")
                        st.rerun()
                    else:
                        st.error("Failed to add supplier.")

        st.markdown("#### Existing Purchase Orders")
        pos = get_purchase_orders()
        if not pos:
            st.info("No purchase orders yet.")
        else:
            for po in pos:
                _supplier_name = (po.get("suppliers") or {}).get("company_name", "Unknown supplier")
                with st.expander(f"{po['po_number']} — {_supplier_name} — {po['status']} — "
                                f"GHS {po.get('total_cost', 0):.2f}"):
                    lines = get_po_line_items(po["id"])
                    for li in lines:
                        _part = (li.get("inventory_parts") or {})
                        st.markdown(render_meta_chips([
                            ("fa-box", _part.get("part_name"), "neutral"),
                            ("fa-hashtag", _part.get("part_number"), "neutral"),
                            ("fa-cubes", f"Ordered: {li.get('quantity_ordered', 0)}", "info"),
                            ("fa-check", f"Received: {li.get('quantity_received', 0)}",
                            "ok" if li.get("quantity_received", 0) >= li.get("quantity_ordered", 0) else "warn"),
                        ]), unsafe_allow_html=True)
                    if po["status"] == "Sent" and st.button(f"📦 Mark as Received", key=f"recv_po_{po['id']}"):
                        _receive_items = [{"part_id": li["part_id"],
                                          "quantity_received": li["quantity_ordered"]} for li in lines]
                        if receive_purchase_order(po["id"], _receive_items, full_name):
                            st.success("PO received — stock levels updated.")
                            st.rerun()
                        else:
                            st.error("Some items failed to update — check the error log before "
                                    "assuming stock is fully correct.")

        st.markdown("#### Create New Purchase Order")
        if not suppliers:
            st.warning("Add a supplier above before creating a purchase order.")
        elif not parts:
            st.warning("Add parts to inventory before creating a purchase order.")
        else:
            if "po_line_items" not in st.session_state:
                st.session_state.po_line_items = []

            supplier_choices = {s["company_name"]: s["id"] for s in suppliers}
            _po_supplier = st.selectbox("Supplier", list(supplier_choices.keys()), key="po_supplier_select")

            part_choices = {f"{p['part_name']} ({p.get('part_number', 'N/A')})": p["id"] for p in parts}
            _pcol1, _pcol2, _pcol3, _pcol4 = st.columns([3, 1, 1, 1])
            with _pcol1:
                _po_part_label = st.selectbox("Part", list(part_choices.keys()), key="po_part_select")
            with _pcol2:
                _po_qty = st.number_input("Qty", min_value=1, value=1, key="po_qty_input")
            with _pcol3:
                _po_price = st.number_input("Unit price", min_value=0.0, value=0.0, step=0.01, key="po_price_input")
            with _pcol4:
                st.markdown("&nbsp;")
                if st.button("➕ Add"):
                    st.session_state.po_line_items.append({
                        "part_id": part_choices[_po_part_label],
                        "part_label": _po_part_label,
                        "quantity": _po_qty,
                        "unit_price": _po_price,
                    })
                    st.rerun()

            if st.session_state.po_line_items:
                st.markdown("**Line items:**")
                _running_total = 0.0
                for _idx, _item in enumerate(st.session_state.po_line_items):
                    _line_total = _item["quantity"] * _item["unit_price"]
                    _running_total += _line_total
                    _lcol1, _lcol2 = st.columns([5, 1])
                    with _lcol1:
                        st.write(f"{_item['part_label']} — Qty {_item['quantity']} × "
                                f"GHS {_item['unit_price']:.2f} = GHS {_line_total:.2f}")
                    with _lcol2:
                        if st.button("🗑️", key=f"remove_po_line_{_idx}"):
                            st.session_state.po_line_items.pop(_idx)
                            st.rerun()
                st.markdown(f"**Total: GHS {_running_total:.2f}**")

                if st.button("💾 Create Purchase Order", type="primary"):
                    _po = create_purchase_order(
                        supplier_choices[_po_supplier],
                        [{"part_id": i["part_id"], "quantity": i["quantity"], "unit_price": i["unit_price"]}
                         for i in st.session_state.po_line_items],
                        full_name,
                    )
                    if _po:
                        st.success(f"Purchase order {_po['po_number']} created.")
                        st.session_state.po_line_items = []
                        st.rerun()
                    else:
                        st.error("Failed to create purchase order — check the error log.")
            else:
                st.caption("Add at least one line item above to create a purchase order.")

    elif inv_sub == "Bill of Materials":
        st.markdown("### 📋 Bill of Materials")
        st.caption("Link a recurring (PM) task template to the parts it typically needs — "
                  "a reference list, not a live stock reservation.")
        pm_tasks = [t for t in st.session_state.tasks if t.get("is_recurring")]
        if not pm_tasks:
            st.info("No recurring tasks found. Create a recurring task first (Task Dashboard → "
                    "Dispatch New Work Ticket → check 'Recurring Task').")
        elif not parts:
            st.info("No parts in inventory yet. Add parts first.")
        else:
            _bom_task_choices = {f"#{t['id']} {t['title']}": t["id"] for t in pm_tasks}
            _bom_task_label = st.selectbox("Recurring task template", list(_bom_task_choices.keys()))
            _bom_task_id = _bom_task_choices[_bom_task_label]

            _bom_items = get_bom_for_task(_bom_task_id)
            if _bom_items:
                st.markdown("**Current parts list:**")
                for _bi in _bom_items:
                    _bi_part = _bi.get("inventory_parts") or {}
                    _bcol1, _bcol2 = st.columns([5, 1])
                    with _bcol1:
                        st.write(f"{_bi_part.get('part_name', 'Unknown part')} — "
                                f"{_bi.get('quantity_required', 0)} required")
                    with _bcol2:
                        if st.button("🗑️", key=f"remove_bom_{_bi['id']}"):
                            if remove_bom_item(_bi["id"], full_name):
                                st.rerun()
            else:
                st.caption("No parts linked to this task yet.")

            st.markdown("**Add a part:**")
            _bom_part_choices = {f"{p['part_name']} ({p.get('part_number', 'N/A')})": p["id"] for p in parts}
            _acol1, _acol2, _acol3 = st.columns([3, 1, 1])
            with _acol1:
                _bom_part_label = st.selectbox("Part", list(_bom_part_choices.keys()), key="bom_part_select")
            with _acol2:
                _bom_qty = st.number_input("Qty required", min_value=0.1, value=1.0, step=0.5, key="bom_qty_input")
            with _acol3:
                st.markdown("&nbsp;")
                if st.button("➕ Add to BOM"):
                    if add_bom_item(_bom_task_id, _bom_part_choices[_bom_part_label], _bom_qty, full_name):
                        st.success("Added.")
                        st.rerun()
                    else:
                        st.error("Failed to add — check the error log.")

# ---- INCIDENT REPORTS ----
elif selected_section == "Incidents":
    st.subheader(t("incidents.title"))
    can_manage_incidents = can(role, "incident.investigate")

    # Sub-nav uses translated labels for DISPLAY, but routes on the
    # canonical English value — same reasoning as the main nav's
    # _label_to_section mapping. Translating "Report Incident" itself
    # and then comparing inc_sub == "Report Incident" would silently
    # break routing for every non-English user, since inc_sub would
    # hold the translated text, not the English the code checks for.
    if can_manage_incidents:
        _inc_tab_map = {t("incidents.tab_all"): "All Incidents", t("incidents.tab_report"): "Report Incident"}
        _inc_selected_label = option_menu(
            menu_title=None,
            options=list(_inc_tab_map.keys()),
            icons=["exclamation-triangle-fill", "plus-circle"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )
    else:
        _inc_tab_map = {t("incidents.tab_my_reports"): "My Reports", t("incidents.tab_report"): "Report Incident"}
        _inc_selected_label = option_menu(
            menu_title=None,
            options=list(_inc_tab_map.keys()),
            icons=["file-earmark-text", "plus-circle"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )
    inc_sub = _inc_tab_map[_inc_selected_label]

    incidents = st.session_state.incidents

    if inc_sub in ("All Incidents", "My Reports"):
        visible = incidents if can_manage_incidents else [i for i in incidents if i.get('reported_by') == full_name]
        if not visible:
            render_empty_state("fa-shield-heart", t("incidents.empty_title"), t("incidents.empty_desc"))
        if can_manage_incidents and visible and st.button(t("incidents.export_csv")):
            csv = export_incidents_csv(visible)
            if csv:
                st.download_button(t("incidents.download_csv"), data=csv, file_name="incidents_export.csv", mime="text/csv", key="dl_incidents_csv")
        _inc_display = visible
        if visible:
            _inc_search = st.text_input(t("incidents.search_placeholder"), "", key="inc_search")
            # Deliberately filters a SEPARATE variable, not `visible` itself —
            # the export button above uses `visible` on purpose, so a quick
            # search to find one incident on screen doesn't also silently
            # narrow what gets exported to just that one result.
            _inc_display = quick_filter(visible, _inc_search, ["incident_type", "location", "description"])
        for inc in _inc_display:
            sev_class = f"severity-{inc.get('severity', 'Low')}"
            _meta_chips_html = render_meta_chips([
                ("fa-map-marker-alt", inc.get('location'), "neutral"),
                ("fa-user", t("incidents.reported_by").format(name=inc.get('reported_by')) if inc.get('reported_by') else None, "info"),
                ("fa-clock", _fmt_log_time(inc.get('created_at')), "neutral"),
                ("fa-building", inc.get('department'), "info"),
                ("fa-clock-rotate-left", inc.get('shift'), "neutral"),
                ("fa-id-card", t("incidents.id_no").format(no=inc['reporter_id_no']) if inc.get('reporter_id_no') else None, "info"),
                ("fa-book", t("incidents.paper_ref").format(no=inc['paper_ref_no']) if inc.get('paper_ref_no') else None, "neutral"),
            ])
            _inc_fields = render_field_grid([
                ("fa-bolt", t("incidents.field_immediate_action"), inc.get('immediate_action'), "warn"),
                ("fa-lightbulb", t("incidents.field_reporter_suggestion"), inc.get('reporter_suggestion'), "info"),
                ("fa-magnifying-glass", t("incidents.field_root_cause"), inc.get('root_cause'), "neutral"),
                ("fa-check", t("incidents.field_corrective_action"), inc.get('corrective_action'), "ok"),
            ])
            st.markdown(f"""
            <div class="custom-card" style="border-left-color: #dc2626;">
                <strong>#{inc['id']}: {esc(inc.get('incident_type'))}</strong>
                <span class="severity-badge {sev_class}">{esc(inc.get('severity', 'Low'))}</span>
                <span class="status-badge status-{esc(inc.get('status', 'Open')).replace(' ', '')}">{esc(inc.get('status', 'Open'))}</span>
                {_meta_chips_html}
                <p>{esc(inc.get('description'))}</p>
                {_inc_fields}
                {f"<p><small>{esc(t('incidents.acknowledged_by').format(name=inc.get('acknowledged_by'), time=_fmt_log_time(inc.get('acknowledged_at'))))}</small></p>" if inc.get('acknowledged_by') else ""}
            </div>
            """, unsafe_allow_html=True)
            if can_manage_incidents:
                if not inc.get('acknowledged_by'):
                    if st.button(t("incidents.acknowledge_btn").format(id=inc['id']), key=f"inc_ack_{inc['id']}"):
                        if acknowledge_incident(inc['id'], full_name):
                            st.success(t("incidents.acknowledged_success"))
                            st.rerun()
                        else:
                            st.error(t("incidents.update_failed"))
                with st.expander(t("incidents.investigate_expander").format(id=inc['id'])):
                    new_status = st.selectbox(t("incidents.status_label"), ["Open", "Investigating", "Resolved", "Closed"],
                                               index=["Open", "Investigating", "Resolved", "Closed"].index(inc.get('status', 'Open')) if inc.get('status') in ["Open", "Investigating", "Resolved", "Closed"] else 0,
                                               key=f"inc_stat_{inc['id']}")
                    root_cause = st.text_area(t("incidents.root_cause_label"), value=inc.get('root_cause') or '', key=f"inc_root_{inc['id']}")
                    corrective_action = st.text_area(t("incidents.corrective_action_label"), value=inc.get('corrective_action') or '', key=f"inc_corr_{inc['id']}")
                    if st.button(t("incidents.save_investigation"), key=f"inc_save_{inc['id']}"):
                        if update_incident(inc['id'], {
                            "status": new_status,
                            "root_cause": root_cause,
                            "corrective_action": corrective_action
                        }, full_name):
                            st.success(t("incidents.updated_success"))
                            st.rerun()
                        else:
                            st.error(t("incidents.update_failed"))

    elif inc_sub == "Report Incident":
        st.markdown(f"### {t('incidents.submit_new_heading')}")
        st.caption(t("incidents.submit_caption"))

        # Same reasoning as Smart Work Order Descriptions — outside the
        # form because st.form() only reruns on its own submit button,
        # and the real Description field comes later in the same form
        # (can't yet reference what's typed there while this section
        # renders). A separate quick-summary input here suggests a
        # severity that pre-selects the dropdown inside the form; the
        # reporter still confirms or overrides it there — never
        # auto-applied without their review.
        if AI_FEATURES_AVAILABLE:
            with st.expander("🔮 AI Severity Helper (optional)"):
                st.caption("Briefly describe what happened — AI will suggest a severity level "
                          "below, which you can confirm or change in the form.")
                _severity_summary = st.text_input("What happened?", key="severity_helper_summary")
                _severity_type_hint = st.selectbox(
                    "Incident type", ["Near Miss", "Injury", "Property Damage", "Equipment Failure",
                                     "Environmental", "Hazard Observation"], key="severity_helper_type")
                if st.button("🔮 Suggest Severity", key="severity_suggest_btn"):
                    if _severity_summary.strip():
                        with st.spinner("Analyzing..."):
                            _suggested = predict_incident_severity(_severity_type_hint, _severity_summary)
                        if _suggested:
                            st.session_state["_severity_suggestion"] = _suggested
                            st.success(f"Suggested severity: **{_suggested}** — pre-selected below, "
                                      "review and adjust if needed.")
                            st.rerun()
                        else:
                            st.warning("Couldn't generate a suggestion right now — please select "
                                      "severity directly in the form below.")
                    else:
                        st.warning("Describe what happened first.")

        # Prefill department/employee ID from the reporter's own profile
        # (set at registration — see Owner Console access requests) so
        # they don't have to retype what the app already knows, matching
        # what the paper form pre-knows about a regular reporter. Both
        # remain editable, since the incident might be filed for a
        # different department than the reporter's home one.
        _my_profile = next((u for u in fetch_all_users_from_db() if u.get("username") == username), {})

        _incident_location_options = get_location_path_options()
        with st.form("new_incident_form", clear_on_submit=True):
            st.markdown(f"#### {t('incidents.report_details_heading')}")
            _rc1, _rc2 = st.columns(2)
            with _rc1:
                # These option values are stored directly in the database
                # (incident_type, severity, shift) — kept in English
                # deliberately, not translated, since translating them
                # would mean a non-English user's selection gets stored
                # as that language's text instead of the canonical value
                # other code (e.g. safety_leading_indicators) checks for.
                incident_type = selectbox_with_other(t("incidents.type_label"),
                    ["Near Miss", "Injury", "Property Damage", "Equipment Failure",
                     "Environmental", "Hazard Observation"], key_prefix="incident_type")
                _severity_options = ["Low", "Medium", "High", "Critical"]
                _suggested_severity = st.session_state.pop("_severity_suggestion", None)
                _severity_default_index = _severity_options.index(_suggested_severity) if _suggested_severity in _severity_options else 0
                severity = st.selectbox(t("incidents.severity_label"), _severity_options, index=_severity_default_index)
                department = st.text_input(t("incidents.department_label"), value=_my_profile.get("department") or "",
                                           max_chars=100)
                shift = st.selectbox(t("incidents.shift_label"), ["Day Shift", "Night Shift", "Swing Shift",
                                               "Weekend Day", "Weekend Night"])
            with _rc2:
                reporter_id_no = st.text_input(t("incidents.your_id_label"), value=_my_profile.get("employee_id") or "",
                                               max_chars=50)
                assets_list = st.session_state.get("assets", [])
                asset_options = [t("incidents.none_option")] + [f"#{a['id']} {a['name']}" for a in assets_list]
                selected_asset = st.selectbox(t("incidents.related_asset_label"), asset_options)
                witnesses = st.text_input(t("incidents.witnesses_label"), max_chars=200)
                paper_ref_no = st.text_input(t("incidents.paper_ref_label"), max_chars=50,
                                             placeholder=t("incidents.paper_ref_placeholder"),
                                             help=t("incidents.paper_ref_help"))

            if _incident_location_options:
                location = selectbox_with_other(t("incidents.location_label"), _incident_location_options,
                                                key_prefix="incident_location")
            else:
                location = st.text_input(t("incidents.location_label"), max_chars=100)
            description = st.text_area(t("incidents.description_label"), placeholder=t("incidents.description_placeholder"))
            immediate_action = st.text_area(t("incidents.immediate_action_label"), placeholder=t("incidents.immediate_action_placeholder"))
            reporter_suggestion = st.text_area(
                t("incidents.suggestion_label"),
                placeholder=t("incidents.suggestion_placeholder"),
                help=t("incidents.suggestion_help"))

            confirm_accurate = st.checkbox(
                t("incidents.confirm_checkbox"),
                help=t("incidents.confirm_help"))

            submitted = st.form_submit_button(t("incidents.submit_btn"))
            if submitted:
                if not (location and description):
                    st.error(t("incidents.err_required"))
                elif not confirm_accurate:
                    st.error(t("incidents.err_confirm"))
                else:
                    asset_id = None
                    if selected_asset != t("incidents.none_option"):
                        asset_id = int(selected_asset.split(" ")[0].replace("#", ""))
                    new_incident = create_incident(
                        incident_type, severity, location, description, full_name,
                        asset_id=asset_id, witnesses=witnesses, immediate_action=immediate_action,
                        paper_ref_no=paper_ref_no or None, reporter_id_no=reporter_id_no or None,
                        department=department or None, shift=shift,
                        reporter_suggestion=reporter_suggestion or None)
                    if new_incident:
                        st.success(t("incidents.success_reported"))
                        if severity in ("Critical", "High"):
                            st.warning(t("incidents.warn_flagged"))
                        st.rerun()
                    elif st.session_state.pop("_last_error_was_connectivity", False):
                        st.error(friendly_db_error("connection timeout"))
                    else:
                        st.error(t("incidents.err_submit_failed"))

# ---- CHAT ROOM ----
elif selected_section == "Permits":
    st.subheader(t("permits.title"))
    st.caption(t("permits.caption"))

    # Same display-label/routing-value separation as Incidents' sub-nav —
    # permit_sub gets compared against canonical English values below,
    # so the tabs shown to the user and the values routing depends on
    # must stay decoupled.
    _permit_tab_map = {t("permits.tab_active"): "Active Permits"}
    if can(role, "permit.issue"):
        _permit_tab_map[t("permits.tab_issue")] = "Issue Permit"
    _permit_tab_map[t("permits.tab_history")] = "Permit History"

    _permit_selected_label = option_menu(
        menu_title=None, options=list(_permit_tab_map.keys()),
        icons=["shield-check", "plus-circle", "clock-history"][:len(_permit_tab_map)],
        orientation="horizontal", default_index=0, styles=menu_styles(),
    )
    permit_sub = _permit_tab_map[_permit_selected_label]

    all_permits = fetch_permits()
    task_lookup = {t2['id']: t2 for t2 in st.session_state.tasks}

    def _render_permit(p, allow_actions=True):
        status = p.get('status', 'Issued')
        colour = {"Issued": "#f59e0b", "Active": "#10b981", "Closed": "#94a3b8", "Cancelled": "#dc2626"}.get(status, "#0f3460")
        expired = False
        if p.get('valid_until'):
            vu = _parse_dt(p['valid_until'])
            if vu and vu < datetime.now() and status in ("Issued", "Active"):
                expired = True
        linked = task_lookup.get(p.get('task_id'))

        _permit_fields = render_field_grid([
            ("fa-clipboard-list", t("permits.field_task"), linked['title'] if linked else None, "neutral"),
            ("fa-lock", t("permits.field_lock_tags"), p.get('lock_tag_numbers'), "warn"),
            ("fa-power-off", t("permits.field_isolation_points"), p.get('isolation_points'), "warn"),
            ("fa-exclamation-triangle", t("permits.field_hazards"), p.get('hazards_identified'), "danger"),
        ])
        _permit_chips = render_meta_chips([
            ("fa-user-check", t("permits.issued_by").format(name=p.get('issued_by')) if p.get('issued_by') else None, "info"),
            ("fa-clock", _fmt_log_time(p['issued_at']) if p.get('issued_at') else None, "neutral"),
            ("fa-signature", t("permits.accepted_by").format(name=p['accepted_by']) if p.get('accepted_by') else None, "info"),
            ("fa-clock", _fmt_log_time(p['accepted_at']) if p.get('accepted_at') else None, "neutral"),
            ("fa-check-double", t("permits.signed_back_by").format(name=p['signed_back_by']) if p.get('signed_back_by') else None, "ok"),
            ("fa-clock", _fmt_log_time(p['signed_back_at']) if p.get('signed_back_at') else None, "neutral"),
            ("fa-hourglass-end", t("permits.valid_until").format(time=_fmt_log_time(p['valid_until'])) if p.get('valid_until') else None,
            "danger" if expired else "neutral"),
        ])
        _permit_step_map = {"Issued": 0, "Active": 1, "Closed": 2, "Cancelled": 1}
        _permit_steps_html = render_progress_steps(
            [t("permits.step_issued"), t("permits.step_accepted"), t("permits.step_signed_back")],
            _permit_step_map.get(status, 0),
            cancelled=(status == "Cancelled"),
        )
        st.markdown(f"""
        <div class="custom-card" style="border-left-color: {colour};">
            <strong>Permit #{p['id']} — {esc(p.get('permit_type'))}</strong>
            <span class="status-badge" style="background:{colour};">{esc(status)}</span>
            {f'<span class="overdue-badge">{esc(t("permits.expired_badge"))}</span>' if expired else ''}
            {_permit_steps_html}
            {_permit_chips}
            {_permit_fields}
        </div>
        """, unsafe_allow_html=True)

        if not allow_actions:
            return
        acols = st.columns(3)
        if status == "Issued" and can(role, "permit.accept"):
            if acols[0].button(t("permits.accept_btn"), key=f"permit_acc_{p['id']}"):
                if accept_permit(p['id'], full_name):
                    st.success(t("permits.accept_success"))
                    st.rerun()
                elif st.session_state.pop("_last_error_was_connectivity", False):
                    st.error(friendly_db_error("connection timeout"))
                else:
                    st.error(t("permits.accept_failed"))
        if status == "Active" and can(role, "permit.sign_back"):
            if acols[1].button(t("permits.signback_btn"), key=f"permit_sb_{p['id']}"):
                if sign_back_permit(p['id'], full_name):
                    st.success(t("permits.signback_success"))
                    st.rerun()
                elif st.session_state.pop("_last_error_was_connectivity", False):
                    st.error(friendly_db_error("connection timeout"))
                else:
                    st.error(t("permits.signback_failed"))
        if status in ("Issued", "Active") and can(role, "permit.cancel"):
            if acols[2].button(t("permits.cancel_btn"), key=f"permit_can_{p['id']}"):
                if cancel_permit(p['id'], full_name):
                    st.rerun()
                elif st.session_state.pop("_last_error_was_connectivity", False):
                    st.error(friendly_db_error("connection timeout"))
                else:
                    st.error(t("permits.cancel_failed"))

    if permit_sub == "Active Permits":
        live = [p for p in all_permits if p.get('status') in ("Issued", "Active")]
        if not live:
            render_empty_state("fa-lock", t("permits.empty_title"), t("permits.empty_desc"))
        else:
            expired_live = [p for p in live if (_parse_dt(p.get('valid_until')) or datetime.max) < datetime.now()]
            if expired_live:
                st.error(t("permits.expired_warning").format(n=len(expired_live)))
            # Deliberately checked against the full `live` list above, not
            # the search-filtered one below — a permit that's overdue for
            # review shouldn't disappear from that warning just because
            # someone typed a search term to find something else.
            _permit_search = st.text_input(t("permits.search_placeholder"), "", key="permit_search")
            for p in quick_filter(live, _permit_search, ["permit_type", "lock_tag_numbers"]):
                _render_permit(p)

    elif permit_sub == "Issue Permit":
        if require(role, "permit.issue"):
            st.markdown(f"### {t('permits.issue_new_heading')}")
            open_tasks = [t2 for t2 in st.session_state.tasks if t2.get('status') != 'Complete']
            if not open_tasks:
                st.info(t("permits.no_open_tasks"))
            else:
                with st.form("issue_permit_form", clear_on_submit=True):
                    task_map = {f"#{t2['id']} {t2['title']}": t2['id'] for t2 in open_tasks}
                    sel_task = st.selectbox(t("permits.task_label"), list(task_map.keys()))
                    # permit_type options are stored directly in the
                    # database — kept in English deliberately, same
                    # reasoning as Incidents' type/severity/shift fields.
                    permit_type = selectbox_with_other(t("permits.type_label"), [
                        "General Work Permit", "LOTO / Isolation", "Hot Work", "Confined Space",
                        "Working at Height", "Excavation", "Electrical Isolation", "Live Line"],
                        key_prefix="permit_type")
                    lock_tags = st.text_input(t("permits.lock_tag_label"), placeholder=t("permits.lock_tag_placeholder"))
                    isolation_points = st.text_area(t("permits.isolation_points_label"), placeholder=t("permits.isolation_points_placeholder"))
                    hazards = st.text_area(t("permits.hazards_label"), placeholder=t("permits.hazards_placeholder"))
                    valid_hours = st.number_input(t("permits.valid_hours_label"), min_value=1, max_value=72, value=12)
                    confirm = st.checkbox(t("permits.confirm_checkbox"))
                    submitted = st.form_submit_button(t("permits.issue_btn"))
                    if submitted:
                        if not (lock_tags and isolation_points and hazards):
                            st.error(t("permits.err_required"))
                        elif not confirm:
                            st.error(t("permits.err_confirm"))
                        else:
                            tid = task_map[sel_task]
                            linked_task = task_lookup.get(tid, {})
                            permit = issue_permit(
                                tid, linked_task.get('asset_id'), permit_type, lock_tags,
                                isolation_points, hazards, full_name,
                                datetime.now() + timedelta(hours=valid_hours))
                            if permit:
                                st.success(t("permits.issue_success").format(id=permit['id']))
                                st.rerun()
                            else:
                                st.error(t("permits.issue_failed"))

    elif permit_sub == "Permit History":
        closed = [p for p in all_permits if p.get('status') in ("Closed", "Cancelled")]
        if not closed:
            st.info(t("permits.no_closed"))
        else:
            _permit_hist_search = st.text_input(t("permits.search_placeholder"), "", key="permit_hist_search")
            closed = quick_filter(closed, _permit_hist_search, ["permit_type", "lock_tag_numbers"])
        for p in closed[:50]:
            _render_permit(p, allow_actions=False)

elif selected_section == "Handover":
    st.subheader("🔄 Shift Handover Log")
    st.caption("Structured handover between shifts. Lost context between crews is a recognised contributor to incidents, "
               "so outstanding work and safety concerns are captured explicitly.")

    handover_tabs = ["Recent Handovers"]
    if can(role, "handover.create"):
        handover_tabs.append("New Handover")
        handover_tabs.append("Shift Roster")
    handover_sub = option_menu(
        menu_title=None, options=handover_tabs,
        icons=["journal-text", "plus-circle", "calendar-week"][:len(handover_tabs)],
        orientation="horizontal", default_index=0, styles=menu_styles(),
    )

    handovers = fetch_handovers()

    if handover_sub == "Recent Handovers":
        unack = [h for h in handovers if not h.get('acknowledged')]
        if unack:
            st.warning(f"📋 {len(unack)} handover(s) not yet acknowledged by the incoming supervisor.")
        if not handovers:
            render_empty_state("fa-right-left", "No handovers logged yet", "Shift handover records will appear here.")
        for h in handovers:
            ack_badge = ('<span class="verified-badge">ACKNOWLEDGED</span>' if h.get('acknowledged')
                         else '<span class="pending-badge">AWAITING ACK</span>')
            has_safety = bool((h.get('safety_concerns') or '').strip())
            _ho_meta_chips = render_meta_chips([
                ("fa-sign-out-alt", f"Out: {h.get('outgoing_supervisor')}" if h.get('outgoing_supervisor') else None, "info"),
                ("fa-sign-in-alt", f"In: {h.get('incoming_supervisor')}" if h.get('incoming_supervisor') else "In: TBA", "info"),
                ("fa-clock", _fmt_log_time(h.get('created_at')), "neutral"),
            ])
            _ho_fields = render_field_grid([
                ("fa-check", "Completed", h.get('work_completed') or "—", "ok"),
                ("fa-hourglass-half", "Outstanding", h.get('work_outstanding') or "—", "warn"),
                ("fa-triangle-exclamation", "Safety concerns", h.get('safety_concerns'), "danger"),
                ("fa-screwdriver-wrench", "Equipment status", h.get('equipment_status') or "—", "neutral"),
            ])
            st.markdown(f"""
            <div class="custom-card" style="border-left-color: {'#dc2626' if has_safety else '#0f3460'};">
                <strong>{esc(h.get('shift'))} — {esc(h.get('crew') or 'No crew')}</strong> {ack_badge}
                {_ho_meta_chips}
                {_ho_fields}
                {f"<small>Acknowledged by {esc(h.get('acknowledged_by'))} at {_fmt_log_time(h.get('acknowledged_at'))}</small>" if h.get('acknowledged') else ""}
            </div>
            """, unsafe_allow_html=True)
            if not h.get('acknowledged') and can(role, "handover.acknowledge"):
                if st.button("✅ Acknowledge Handover", key=f"ack_ho_{h['id']}"):
                    if acknowledge_handover(h['id'], full_name):
                        st.success("Handover acknowledged.")
                        st.rerun()
                    else:
                        st.error("Failed to acknowledge. Check Row Level Security "
                                "on the shift_handovers table.")

    elif handover_sub == "New Handover":
        if require(role, "handover.create"):
            st.markdown("### Log Shift Handover")
            all_users_ho = fetch_all_users_from_db()
            supervisor_names = [u['full_name'] for u in all_users_ho
                                if u['role'].strip().lower() in ('supervisor', 'superintendent')
                                and u.get('is_approved') and u['full_name'] != full_name]
            with st.form("handover_form", clear_on_submit=True):
                shift = st.selectbox("Shift", ["Day Shift", "Night Shift", "Swing Shift", "Weekend Day", "Weekend Night"])
                crew = st.text_input("Crew / Team", max_chars=100)
                incoming = st.selectbox("Incoming Supervisor", ["TBA"] + supervisor_names)
                work_completed = st.text_area("Work Completed This Shift *")
                work_outstanding = st.text_area("Work Outstanding / Handed Over *")
                safety_concerns = st.text_area("Safety Concerns", placeholder="Leave blank if none. Anything entered here triggers a notification.")
                equipment_status = st.text_area("Equipment Status / Defects")
                submitted = st.form_submit_button("📤 Submit Handover")
                if submitted:
                    if work_completed and work_outstanding:
                        h = create_handover(shift, crew, full_name,
                                            None if incoming == "TBA" else incoming,
                                            work_completed, work_outstanding,
                                            safety_concerns, equipment_status)
                        if h:
                            st.success("Handover logged.")
                            st.rerun()
                        else:
                            st.error("Failed to log handover.")
                    else:
                        st.error("Work completed and work outstanding are both required.")

    elif handover_sub == "Shift Roster":
        st.markdown("### 🗓️ Shift Roster")
        all_users_roster = fetch_all_users_from_db()
        worker_names = [u["full_name"] for u in all_users_roster
                        if u.get("is_approved") and u["full_name"]]
        if not worker_names:
            st.info("No approved users found.")
        else:
            with st.form("shift_roster_form", clear_on_submit=True):
                _roster_worker = st.selectbox("Worker", worker_names)
                _rcol1, _rcol2 = st.columns(2)
                with _rcol1:
                    _start_date = st.date_input("Shift start date", datetime.now().date())
                    _start_time = st.time_input("Shift start time", datetime.now().time())
                with _rcol2:
                    _end_date = st.date_input("Shift end date", datetime.now().date())
                    _end_time = st.time_input("Shift end time",
                                              (datetime.now() + timedelta(hours=8)).time())
                _crew_name = st.text_input("Crew name (optional)")
                if st.form_submit_button("Assign shift"):
                    _shift_start = datetime.combine(_start_date, _start_time)
                    _shift_end = datetime.combine(_end_date, _end_time)
                    if _shift_end <= _shift_start:
                        st.error("Shift end must be after shift start.")
                    elif assign_shift(_roster_worker, _shift_start, _shift_end, _crew_name, full_name):
                        st.success(f"Shift assigned to {_roster_worker}.")
                        st.rerun()
                    else:
                        st.error("Failed to assign shift — check the error log.")

        st.markdown("#### Currently on shift")
        _on_shift_now = get_workers_on_shift()
        if not _on_shift_now:
            st.caption("No one is currently rostered on.")
        else:
            for _s in _on_shift_now:
                st.markdown(render_meta_chips([
                    ("fa-user", _s.get("username"), "ok"),
                    ("fa-users", _s.get("crew_name"), "neutral"),
                    ("fa-clock", f"Until {_fmt_log_time(_s['shift_end'])}" if _s.get("shift_end") else None, "neutral"),
                ]), unsafe_allow_html=True)

        st.markdown("#### Upcoming shifts")
        _upcoming = fetch_upcoming_shifts()
        if not _upcoming:
            st.caption("No upcoming shifts scheduled.")
        else:
            for _u in _upcoming:
                _ucol1, _ucol2 = st.columns([5, 1])
                with _ucol1:
                    st.write(f"{_u.get('username')} — "
                            f"{_fmt_log_time(_u.get('shift_start'))} to {_fmt_log_time(_u.get('shift_end'))}"
                            + (f" ({_u['crew_name']})" if _u.get('crew_name') else ""))
                with _ucol2:
                    if st.button("🗑️", key=f"del_shift_{_u['id']}"):
                        if delete_shift(_u["id"], full_name):
                            st.rerun()

elif selected_section == "Contractors":
    st.subheader(t("contractors.title"))
    st.caption(t("contractors.caption"))

    if require(role, "contractor.view"):
        _contractor_tab_map = {t("contractors.tab_all"): "All Contractors"}
        if can(role, "contractor.manage"):
            _contractor_tab_map[t("contractors.tab_add")] = "Add Contractor"
        _contractor_selected_label = option_menu(
            menu_title=None, options=list(_contractor_tab_map.keys()),
            icons=["people", "plus-circle"][:len(_contractor_tab_map)],
            orientation="horizontal", default_index=0, styles=menu_styles(),
        )
        contractor_sub = _contractor_tab_map[_contractor_selected_label]

        contractors = fetch_contractors()

        if contractor_sub == "All Contractors":
            blocked = []
            for c in contractors:
                label, is_blocking = contractor_compliance_status(c)
                if is_blocking:
                    blocked.append(c)
            if blocked:
                st.error(t("contractors.blocking_warning").format(n=len(blocked)))
            if not contractors:
                render_empty_state("fa-user-group", t("contractors.empty_title"), t("contractors.empty_desc"))
            else:
                _contractor_search = st.text_input(t("contractors.search_placeholder"), "", key="contractor_search")
                contractors = quick_filter(contractors, _contractor_search, ["company_name", "contact_person"])

            def _fmt_date_only(value):
                # induction_expiry/insurance_expiry are dates, not
                # timestamps — _fmt_log_time always shows a time
                # component, which would misleadingly show 00:00
                # for every one of these. A plain date format is
                # the honest representation of what's actually stored.
                dt = _parse_dt(value)
                return dt.strftime("%b %d, %Y") if dt else t("contractors.not_set")

            for c in contractors:
                label, is_blocking = contractor_compliance_status(c)
                badge_colour = "#dc2626" if is_blocking else ("#f59e0b" if label != "Compliant" else "#10b981")

                _contractor_chips = render_meta_chips([
                    ("fa-user", c.get('contact_person'), "info"),
                    ("fa-envelope", c.get('contact_email'), "info"),
                    ("fa-phone", c.get('contact_phone'), "info"),
                ])
                _contractor_fields = render_field_grid([
                    ("fa-id-card", t("contractors.field_induction_expires"), _fmt_date_only(c.get('induction_expiry')), "neutral"),
                    ("fa-file-contract", t("contractors.field_insurance_expires"), _fmt_date_only(c.get('insurance_expiry')), "neutral"),
                    ("fa-tools", t("contractors.field_competencies"), c.get('competencies'), "info"),
                ])
                st.markdown(f"""
                <div class="custom-card" style="border-left-color: {badge_colour};">
                    <strong>{esc(c.get('company_name'))}</strong>
                    <span class="status-badge" style="background:{badge_colour};">{esc(label)}</span>
                    {_contractor_chips}
                    {_contractor_fields}
                </div>
                """, unsafe_allow_html=True)
                if can(role, "contractor.manage"):
                    with st.expander(t("contractors.update_expander").format(name=c.get('company_name'))):
                        ccols = st.columns(3)
                        new_ind = ccols[0].date_input(t("contractors.induction_expiry_label"), key=f"ind_{c['id']}")
                        new_ins = ccols[1].date_input(t("contractors.insurance_expiry_label"), key=f"ins_{c['id']}")
                        if ccols[2].button(t("contractors.save_btn"), key=f"csave_{c['id']}"):
                            if update_contractor(c['id'], {
                                "induction_expiry": new_ind.isoformat(),
                                "insurance_expiry": new_ins.isoformat(),
                            }, full_name):
                                st.success(t("contractors.update_success"))
                                st.rerun()
                            else:
                                st.error(t("contractors.save_failed"))

        elif contractor_sub == "Add Contractor":
            if require(role, "contractor.manage"):
                with st.form("contractor_form", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        company_name = st.text_input(t("contractors.company_name_label"), max_chars=150)
                        contact_person = st.text_input(t("contractors.contact_person_label"), max_chars=100)
                        contact_email = st.text_input(t("contractors.contact_email_label"), max_chars=150)
                        contact_phone = st.text_input(t("contractors.contact_phone_label"), max_chars=50)
                    with c2:
                        induction_date = st.date_input(t("contractors.induction_date_label"), value=datetime.now())
                        induction_expiry = st.date_input(t("contractors.induction_expiry_cap_label"), value=datetime.now() + timedelta(days=365))
                        insurance_expiry = st.date_input(t("contractors.insurance_expiry_cap_label"), value=datetime.now() + timedelta(days=365))
                    competencies = st.text_area(t("contractors.competencies_label"),
                                                 placeholder=t("contractors.competencies_placeholder"))
                    notes = st.text_area(t("contractors.notes_label"))
                    submitted = st.form_submit_button(t("contractors.add_btn"))
                    if submitted:
                        if company_name:
                            c = create_contractor(company_name, contact_person, contact_email,
                                                   contact_phone, induction_date, induction_expiry,
                                                   insurance_expiry, competencies, notes, full_name)
                            if c:
                                st.success(t("contractors.add_success").format(name=company_name))
                                st.rerun()
                            else:
                                st.error(t("contractors.add_failed"))
                        else:
                            st.error(t("contractors.err_name_required"))

elif selected_section == "Analytics":
    if require(role, "analytics.view"):
        st.subheader("📈 Maintenance & Safety Analytics")
        tasks = st.session_state.tasks
        assets = st.session_state.get("assets", [])
        parts = st.session_state.get("parts", [])
        incidents = st.session_state.get("incidents", [])
        parts_lookup = {p['id']: p for p in parts}

        analytics_sub = option_menu(
            menu_title=None,
            options=["Overview", "Reliability", "Utilization", "Backlog & Compliance", "Failure Pareto", "Cost", "Safety", "Electrical Health"],
            icons=["grid-1x2-fill", "speedometer2", "clock-fill", "list-check", "bar-chart-fill", "cash-coin", "shield-fill-check"],
            orientation="horizontal", default_index=0, styles=menu_styles(),
        )

        if analytics_sub == "Overview":
            st.markdown("#### At a Glance")
            st.caption("A simpler summary, built for a quick check rather than a deep dive — the "
                      "detailed operational metrics (MTTR, MTBF, cost breakdowns) live in the tabs "
                      "next to this one.")

            st.markdown("##### ⚡ Electrical Department Workload")
            st.caption("Open, overdue, and recently completed work across the three subsections — "
                      "built to make workload distribution visible at a glance, not something you "
                      "have to dig through the full task list to piece together.")
            _elec_workload = get_electrical_subsection_workload(tasks)
            _elec_cols = st.columns(3)
            for _i, (_sub, _counts) in enumerate(_elec_workload.items()):
                with _elec_cols[_i]:
                    _tone_colour = "#dc2626" if _counts["overdue"] > 0 else "#0f3460"
                    st.markdown(f"""
                    <div class="custom-card" style="border-left-color: {_tone_colour};">
                        <strong>{esc(_sub)}</strong>
                        <p>Open: {_counts['open']} &nbsp;|&nbsp; Overdue: {_counts['overdue']} &nbsp;|&nbsp;
                        Completed (30d): {_counts['completed_last_30d']}</p>
                    </div>
                    """, unsafe_allow_html=True)

            _now = datetime.now()
            _this_month_incidents = [i for i in incidents if i.get("created_at") and
                                     _parse_dt(i["created_at"]) and
                                     _parse_dt(i["created_at"]).month == _now.month and
                                     _parse_dt(i["created_at"]).year == _now.year]
            _last_month = (_now.month - 1) or 12
            _last_month_year = _now.year if _now.month > 1 else _now.year - 1
            _last_month_incidents = [i for i in incidents if i.get("created_at") and
                                     _parse_dt(i["created_at"]) and
                                     _parse_dt(i["created_at"]).month == _last_month and
                                     _parse_dt(i["created_at"]).year == _last_month_year]
            _incident_trend = len(_this_month_incidents) - len(_last_month_incidents)

            _completed_this_month = sum(1 for t in tasks if t.get("status") == "Complete"
                                        and t.get("completed_at") and _parse_dt(t["completed_at"])
                                        and _parse_dt(t["completed_at"]).month == _now.month
                                        and _parse_dt(t["completed_at"]).year == _now.year)
            _overdue_tasks = sum(1 for t in tasks if t.get("due_date") and _parse_dt(t["due_date"])
                                 and _parse_dt(t["due_date"]) < _now and t.get("status") != "Complete")

            _asset_operational = sum(1 for a in assets if a.get("status", "Operational") == "Operational")
            _asset_down = sum(1 for a in assets if a.get("status") == "Down")
            _asset_total = len(assets) or 1

            _all_permits = fetch_permits()
            _active_permits = sum(1 for p in _all_permits if p.get("status") in ("Issued", "Active"))
            _expired_permits = 0
            for p in _all_permits:
                if p.get("status") in ("Issued", "Active") and p.get("valid_until"):
                    _vu = _parse_dt(p["valid_until"])
                    if _vu and _vu < _now:
                        _expired_permits += 1

            st.markdown(render_stat_cards([
                {"icon": "fa-triangle-exclamation", "label": "Incidents This Month",
                "value": len(_this_month_incidents),
                "tone": "danger" if _incident_trend > 0 else ("ok" if _incident_trend < 0 else "neutral")},
                {"icon": "fa-check-circle", "label": "Tasks Completed This Month",
                "value": _completed_this_month, "tone": "ok"},
                {"icon": "fa-clock", "label": "Tasks Overdue Right Now",
                "value": _overdue_tasks, "tone": "danger" if _overdue_tasks > 0 else "ok"},
                {"icon": "fa-server", "label": "Assets Operational",
                "value": f"{_asset_operational}/{len(assets)}" if assets else "No data",
                "tone": "ok" if _asset_down == 0 else ("danger" if _asset_down > _asset_total * 0.2 else "warn")},
                {"icon": "fa-lock", "label": "Active Permits", "value": _active_permits,
                "tone": "danger" if _expired_permits > 0 else "info"},
            ]), unsafe_allow_html=True)

            # ---- New for this executive pass: Production, Utilization, Budget, Haulage ----
            _prod_this_month = [r for r in fetch_production_records(limit=500)
                                if r.get("production_date", "").startswith(_now.strftime("%Y-%m"))]
            _prod_by_material = {}
            for _r in _prod_this_month:
                _key = (_r.get("material_type"), _r.get("unit"))
                _prod_by_material[_key] = _prod_by_material.get(_key, 0) + (_r.get("quantity") or 0)
            if _prod_by_material:
                _top_material = max(_prod_by_material.items(), key=lambda kv: kv[1])
                _prod_label = f"{_top_material[0][0]}"
                _prod_value = f"{_top_material[1]:,.0f} {_top_material[0][1]}"
                if len(_prod_by_material) > 1:
                    _prod_value += f" (+{len(_prod_by_material) - 1} more)"
            else:
                _prod_label, _prod_value = "Production This Month", "No data"

            _fleet_util, _util_counted, _util_total = fleet_average_utilization(
                assets, _now - timedelta(days=30), _now) if assets else (None, 0, 0)

            _all_budgets = fetch_budgets()
            _budget_status = "No data"
            _budget_tone = "neutral"
            if _all_budgets:
                _total_allocated = sum(b.get("allocated_amount", 0) or 0 for b in _all_budgets)
                _total_spent = sum(actual_spend_for_asset(b.get("asset_id"), tasks, parts_lookup)
                                  for b in _all_budgets)
                if _total_allocated > 0:
                    _budget_pct = _total_spent / _total_allocated * 100
                    _budget_status = f"{_budget_pct:.0f}% of allocated"
                    _budget_tone = "danger" if _total_spent > _total_allocated else "ok"

            _recent_shipments = fetch_shipments(status="Delivered", limit=50)
            _avg_delay = average_delay_hours(_recent_shipments)
            _delay_label = f"{_avg_delay:+.1f} hrs avg" if _avg_delay is not None else "No data"
            _delay_tone = "danger" if (_avg_delay or 0) > 0 else ("ok" if _avg_delay is not None else "neutral")

            st.markdown(render_stat_cards([
                {"icon": "fa-industry", "label": _prod_label if _prod_by_material else "Production This Month",
                "value": _prod_value, "tone": "ok" if _prod_by_material else "neutral"},
                {"icon": "fa-gauge-high", "label": "Fleet Utilization (30d)",
                "value": f"{_fleet_util:.0f}%" if _fleet_util is not None else "No data",
                "tone": "ok" if (_fleet_util or 0) >= 70 else ("warn" if _fleet_util is not None else "neutral")},
                {"icon": "fa-coins", "label": "Budget Status", "value": _budget_status, "tone": _budget_tone},
                {"icon": "fa-truck", "label": "Haulage Delay (recent)", "value": _delay_label, "tone": _delay_tone},
            ]), unsafe_allow_html=True)
            if assets and _util_total > _util_counted:
                st.caption(f"Fleet utilization based on {_util_counted} of {_util_total} assets — "
                          f"the rest have no status history logged yet.")

            st.markdown("---")
            st.markdown("#### 🎯 KPI Targets")
            _ore_materials = {k: v for k, v in _prod_by_material.items() if "ore" in k[0].lower()}
            _ore_this_month = sum(_ore_materials.values()) if _ore_materials else None
            _ytd_records = [r for r in fetch_production_records(limit=2000)
                            if r.get("production_date", "").startswith(str(_now.year))
                            and "ore" in (r.get("material_type") or "").lower()]
            _ore_ytd = sum(r.get("quantity") or 0 for r in _ytd_records) if _ytd_records else None

            _kcol1, _kcol2, _kcol3 = st.columns(3)
            with _kcol1:
                if _ore_this_month is not None:
                    _monthly_pct = _ore_this_month / KPI_MONTHLY_PRODUCTION_TONNES * 100
                    st.metric("Monthly Production vs Target", f"{_monthly_pct:.0f}%",
                             f"{_ore_this_month:,.0f} / {KPI_MONTHLY_PRODUCTION_TONNES:,.0f} t")
                else:
                    st.metric("Monthly Production vs Target", "No ore data")
                if _ore_ytd is not None:
                    _annual_pct = _ore_ytd / KPI_ANNUAL_PRODUCTION_TONNES * 100
                    st.caption(f"Year to date: {_ore_ytd:,.0f} / {KPI_ANNUAL_PRODUCTION_TONNES:,.0f} t "
                              f"({_annual_pct:.0f}% of annual target)")
            with _kcol2:
                if _fleet_util is not None:
                    _avail_delta = _fleet_util - KPI_EQUIPMENT_AVAILABILITY_PCT
                    st.metric("Equipment Availability", f"{_fleet_util:.0f}%",
                             f"{_avail_delta:+.0f} pts vs {KPI_EQUIPMENT_AVAILABILITY_PCT}% target")
                else:
                    st.metric("Equipment Availability", "No data")
            with _kcol3:
                _mttr_this, _mttr_this_n, _mttr_last, _mttr_last_n = mttr_trend(tasks, now=_now)
                if _mttr_this is not None:
                    if _mttr_last is not None:
                        _mttr_delta = _mttr_this - _mttr_last
                        st.metric("MTTR This Month", f"{_mttr_this:.1f}h",
                                 f"{_mttr_delta:+.1f}h vs last month", delta_color="inverse")
                    else:
                        st.metric("MTTR This Month", f"{_mttr_this:.1f}h", "No prior month to compare")
                else:
                    st.metric("MTTR This Month", "No data")

            _grade_this_month, _grade_n = average_ore_grade(_prod_this_month)
            if _grade_this_month is not None:
                _grade_progress = (_grade_this_month - KPI_ORE_GRADE_BASELINE_PCT) / \
                                  (KPI_ORE_GRADE_TARGET_PCT - KPI_ORE_GRADE_BASELINE_PCT) * 100
                st.metric(f"Average Ore Grade ({_grade_n} shift(s) logged)",
                         f"{_grade_this_month:.1f}%",
                         f"{_grade_progress:.0f}% of the way from {KPI_ORE_GRADE_BASELINE_PCT}% "
                         f"baseline to {KPI_ORE_GRADE_TARGET_PCT}% refinery target")
            else:
                st.caption(f"Ore grade — no shifts have logged a grade yet this month. It's an "
                          f"optional field on Production → Log Production (leave at 0 to skip); "
                          f"the {KPI_ORE_GRADE_BASELINE_PCT}%→{KPI_ORE_GRADE_TARGET_PCT}% refinery "
                          f"upgrade target needs that data to track progress against.")

            if WEATHER_CONFIGURED:
                # 90-day lookback, minus a 6-day buffer for ERA5's
                # ~5-day processing delay — requesting dates the
                # dataset doesn't have yet would just come back empty
                # for the most recent few days, so this avoids
                # querying for data that can't exist yet.
                _hist_end = _now - timedelta(days=6)
                _hist_start = _hist_end - timedelta(days=90)
                _historical = fetch_historical_weather(_hist_start, _hist_end)
                _rain_comparison = rainy_vs_dry_production(fetch_production_records(limit=2000), _historical)
                if _rain_comparison["pct_loss_on_rainy_days"] is not None:
                    st.metric("Rainy-Day Production Loss (90d)",
                             f"{_rain_comparison['pct_loss_on_rainy_days']:.0f}%",
                             f"{_rain_comparison['rainy_avg_tonnes']:,.0f} t/day rainy vs "
                             f"{_rain_comparison['dry_avg_tonnes']:,.0f} t/day dry "
                             f"({_rain_comparison['rainy_days']} rainy, {_rain_comparison['dry_days']} dry days)")
                else:
                    st.caption("Rainy-vs-dry-season comparison — not enough overlapping production and "
                              "weather data yet in the last 90 days to compute this honestly.")
            else:
                st.caption("Rainy-vs-dry-season production loss needs site coordinates configured "
                          "(same MINE_LATITUDE/MINE_LONGITUDE setup as the weather planning warnings).")

            if _incident_trend > 0:
                st.caption(f"📈 {_incident_trend} more incident(s) reported than the same point last "
                          "month — worth noting this could reflect either more hazards or better "
                          "reporting; it isn't possible to tell which from the count alone.")
            if _expired_permits > 0:
                st.warning(f"⚠️ {_expired_permits} permit(s) show as active but past their valid-until "
                          "date — worth a direct check with whoever's holding them.")
            if _overdue_tasks > 0:
                st.caption(f"{_overdue_tasks} task(s) are currently past their due date and not yet complete.")

        elif analytics_sub == "Reliability":
            st.markdown("#### Reliability Metrics")
            mttr, mttr_n = compute_mttr_hours_v2(tasks)
            mtbf, mtbf_n = compute_mtbf_hours(tasks)
            c1, c2 = st.columns(2)
            c1.metric("MTTR (hours)", f"{mttr:.1f}" if mttr is not None else "No data",
                      help="Mean Time To Repair — failure start to completion.")
            c1.caption(f"Based on {mttr_n} completed task(s).")
            c2.metric("MTBF (hours)", f"{mtbf:.1f}" if mtbf is not None else "No data",
                      help="Mean Time Between Failures — gaps between reactive failures on the same asset.")
            c2.caption(f"Based on {mtbf_n} failure interval(s).")

            if (mttr_n and mttr_n < 10) or (mtbf_n and mtbf_n < 10):
                st.warning("⚠️ **Small sample.** These figures are computed from very few data points and will "
                           "swing widely as more work is completed. Treat them as indicative only until you have "
                           "a few months of history — don't set targets or report them upward yet.")
            if mttr is None and mtbf is None:
                st.info("No reliability data yet. These metrics populate as tasks are completed with "
                        "recorded completion timestamps and work types.")

            st.markdown("#### 🔧 Predictive Failure Alerts")
            st.caption("Assets nearing their typical time-between-failures, based on their own history — "
                      "flagged before the failure, not after. Needs at least 3 past failures on an asset "
                      "before its average is trusted enough to alert on.")
            _all_failure_alerts = get_predictive_failure_alerts(tasks, assets)
            if not _all_failure_alerts:
                st.info("No assets currently approaching their typical failure window.")
            else:
                for _fa in _all_failure_alerts:
                    _severity_colour = "#dc2626" if _fa["pct_of_window"] >= 1.0 else "#f59e0b"
                    st.markdown(f"""
                    <div class="custom-card" style="border-left-color: {_severity_colour};">
                        <strong>{esc(_fa['asset_name'])}</strong>
                        <span class="status-badge" style="background:{_severity_colour};">
                            {_fa['pct_of_window']:.0%} of typical interval
                        </span>
                        <p>Last failure {_fa['hours_since_last_failure']/24:.0f} days ago — typically fails every
                        {_fa['mtbf_hours']/24:.0f} days, based on {_fa['num_failures']} recorded failures.</p>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("#### Asset Task Frequency")
            ranking = compute_asset_downtime_ranking(tasks, assets)
            if ranking and PANDAS_AVAILABLE and PLOTLY_AVAILABLE:
                dfr = pd.DataFrame(ranking[:15], columns=["Asset", "Tasks"])
                st.plotly_chart(px.bar(dfr, x="Asset", y="Tasks",
                                        title="Maintenance tasks per asset (proxy for downtime frequency)",
                                        color_discrete_sequence=GMC_CHART_COLORS),
                                use_container_width=True)
            elif ranking:
                for name, cnt in ranking[:15]:
                    st.write(f"- **{esc(name)}**: {cnt}")
            else:
                st.caption("No tasks linked to assets yet.")

        elif analytics_sub == "Utilization":
            st.markdown("#### Equipment Utilization & Downtime")
            st.caption(
                "Computed from actual logged status changes, not estimated. This is genuinely "
                "new data — it only captures transitions from when this feature was deployed "
                "onward, so there's no way to reconstruct downtime that happened before that. "
                "The more days that pass with status changes being logged, the more complete "
                "this picture becomes."
            )
            if not assets:
                st.info("No assets registered yet.")
            else:
                _util_asset_choices = {a["name"]: a["id"] for a in assets}
                _util_asset_label = st.selectbox("Asset", list(_util_asset_choices.keys()))
                _util_asset_id = _util_asset_choices[_util_asset_label]
                _util_days = st.select_slider("Look back", options=[7, 14, 30, 60, 90], value=30)
                _window_end = datetime.now()
                _window_start = _window_end - timedelta(days=_util_days)

                _utilization, _coverage_start = compute_asset_utilization(_util_asset_id, _window_start, _window_end)
                _downtime_hrs, _ = compute_asset_downtime(_util_asset_id, _window_start, _window_end)

                if _utilization is None:
                    st.info("No status changes logged yet for this asset in this window — nothing "
                            "to compute. Changing an asset's status (Assets → Manage) will start "
                            "building this history.")
                else:
                    _ucol1, _ucol2 = st.columns(2)
                    _ucol1.metric("Utilization", f"{_utilization:.1f}%")
                    _ucol2.metric("Downtime", f"{_downtime_hrs:.1f} hours")
                    if _coverage_start and _coverage_start > _window_start:
                        st.caption(f"Data available from {_fmt_log_time(_coverage_start.isoformat())} "
                                  f"onward — earlier than that within this window isn't covered yet, "
                                  f"so this reflects a shorter period than the full {_util_days} days requested.")

        elif analytics_sub == "Backlog & Compliance":
            pm_pct, pm_n = compute_pm_compliance_v2(tasks)
            planned_pct, reactive_pct, wt_total = planned_vs_reactive(tasks)
            c1, c2, c3 = st.columns(3)
            c1.metric("PM Compliance", f"{pm_pct}%" if pm_pct is not None else "No data",
                      help="PM tasks completed on or before their due date.")
            c1.caption(f"{pm_n} PM task(s) have come due.")
            c2.metric("Planned Work", f"{planned_pct}%" if planned_pct is not None else "No data")
            c3.metric("Reactive Work", f"{reactive_pct}%" if reactive_pct is not None else "No data")
            if planned_pct is not None:
                st.caption("A commonly cited maintenance benchmark is roughly 80% planned / 20% reactive, though the "
                           "right target varies by operation and equipment age — treat it as a direction, not a rule.")

            st.markdown("#### Backlog Aging")
            buckets = backlog_aging(tasks)
            if sum(buckets.values()) == 0:
                st.success("No open backlog.")
            else:
                bcols = st.columns(len(buckets))
                for i, (label, count) in enumerate(buckets.items()):
                    bcols[i].metric(label, count)
                if buckets["90+ days"] > 0:
                    st.warning(f"⚠️ {buckets['90+ days']} task(s) have been open over 90 days. "
                               "Long-aged backlog usually means the work is either not resourced or no longer valid — worth reviewing.")
                if PANDAS_AVAILABLE and PLOTLY_AVAILABLE:
                    dfb = pd.DataFrame(list(buckets.items()), columns=["Age", "Open tasks"])
                    st.plotly_chart(px.bar(dfb, x="Age", y="Open tasks", title="Open work by age",
                                          color_discrete_sequence=GMC_CHART_COLORS),
                                    use_container_width=True)

        elif analytics_sub == "Failure Pareto":
            st.markdown("#### Failure Modes (Pareto)")
            pareto = failure_pareto(tasks)
            if not pareto:
                st.info("No failure codes recorded yet. Assign a failure code when closing reactive work "
                        "and this becomes your root-cause priority list.")
            else:
                total = sum(n for _, _, n in pareto)
                cumulative = 0
                rows = []
                for desc, code, n in pareto:
                    cumulative += n
                    rows.append({"Failure Mode": desc, "Code": code, "Count": n,
                                 "Cumulative %": round(cumulative / total * 100, 1)})
                if PANDAS_AVAILABLE:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)
                    if PLOTLY_AVAILABLE:
                        dfp = pd.DataFrame(rows)
                        st.plotly_chart(px.bar(dfp, x="Failure Mode", y="Count",
                                                title="Failure modes by frequency",
                                                color_discrete_sequence=GMC_CHART_COLORS),
                                        use_container_width=True)
                else:
                    for r in rows:
                        st.write(f"- **{r['Failure Mode']}** ({r['Code']}): {r['Count']} — cumulative {r['Cumulative %']}%")
                st.caption("The Pareto principle suggests a small number of failure modes usually drive most of your "
                           "downtime. Focus root-cause work at the top of this list.")

        elif analytics_sub == "Cost":
            st.markdown("#### Maintenance Cost by Asset")
            costs = cost_by_asset(tasks, assets, parts_lookup)
            if not costs or all(v == 0 for _, v in costs):
                st.info("No cost data yet. Cost accumulates from labour hours × rate on each task, "
                        "plus the unit cost of parts recorded against it.")
            else:
                total_cost = sum(v for _, v in costs)
                st.metric("Total recorded maintenance cost", f"{total_cost:,.2f}")
                if PANDAS_AVAILABLE:
                    dfc = pd.DataFrame(costs, columns=["Asset", "Cost"])
                    st.dataframe(dfc, use_container_width=True)
                    if PLOTLY_AVAILABLE:
                        st.plotly_chart(px.bar(dfc.head(15), x="Asset", y="Cost",
                                                title="Cost by asset", color_discrete_sequence=GMC_CHART_COLORS),
                                        use_container_width=True)
                st.caption("Currency is whatever you enter — the app does not assume or convert units.")

            st.markdown("---")
            st.markdown("#### Cost Breakdown by Category")
            st.caption("Same underlying cost data, split by work type instead of by asset — shows what "
                      "KIND of work is driving spend, not just which asset.")
            category_costs = cost_by_category(tasks, parts_lookup)
            if not category_costs or all(c["total_cost"] == 0 for c in category_costs):
                st.info("No cost data yet.")
            else:
                if PANDAS_AVAILABLE:
                    dfcat = pd.DataFrame(category_costs)
                    dfcat_display = dfcat.rename(columns={
                        "category": "Work Type", "parts_cost": "Parts Cost",
                        "labour_cost": "Labour Cost", "total_cost": "Total Cost"})
                    st.dataframe(dfcat_display, use_container_width=True, hide_index=True)
                    if PLOTLY_AVAILABLE:
                        _stacked = dfcat.melt(id_vars=["category"], value_vars=["parts_cost", "labour_cost"],
                                              var_name="Component", value_name="Cost")
                        _stacked["Component"] = _stacked["Component"].map(
                            {"parts_cost": "Parts", "labour_cost": "Labour"})
                        st.plotly_chart(
                            px.bar(_stacked, x="category", y="Cost", color="Component", barmode="stack",
                                  title="Cost by work type (parts vs labour)",
                                  color_discrete_sequence=GMC_CHART_COLORS),
                            use_container_width=True)
                else:
                    for c in category_costs:
                        st.write(f"**{c['category']}**: {c['total_cost']:,.2f} "
                                f"(Parts: {c['parts_cost']:,.2f}, Labour: {c['labour_cost']:,.2f})")

            st.markdown("---")
            st.markdown("#### ⚠️ Cost Anomaly Detection")
            st.caption("Completed tasks whose cost is more than 2 standard deviations from the typical "
                      "cost for their work type — a simple statistical check, not a trained model, so "
                      "it's inspectable and its false-positive rate is predictable. Needs at least 6 "
                      "completed tasks in a category before flagging anything in it.")
            _cost_anomalies = detect_cost_anomalies(tasks, parts_lookup)
            if not _cost_anomalies:
                st.info("No cost anomalies detected.")
            else:
                for a in _cost_anomalies:
                    st.markdown(f"""
                    <div class="custom-card" style="border-left-color: #dc2626;">
                        <strong>#{a['task_id']}: {esc(a['title'])}</strong>
                        <span class="status-badge" style="background:#dc2626;">{esc(a['work_type'])}</span>
                        <p>Cost: {a['cost']:,.2f} — typical for {esc(a['work_type'])} tasks is around {a['category_mean']:,.2f}</p>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("#### 💰 Budget Center")
            _budgets = fetch_budgets()
            if not _budgets:
                st.caption("No budgets set yet.")
            else:
                for _b in _budgets:
                    _b_asset_name = (_b.get("assets") or {}).get("name", "Unknown asset")
                    _b_spent = actual_spend_for_asset(_b.get("asset_id"), tasks, parts_lookup)
                    _b_allocated = _b.get("allocated_amount", 0) or 0
                    _b_pct = (_b_spent / _b_allocated * 100) if _b_allocated > 0 else None
                    with st.container(border=True):
                        _bcol1, _bcol2 = st.columns([5, 1])
                        with _bcol1:
                            st.markdown(f"**{_b_asset_name}** — {_b.get('period_label')}")
                            st.progress(min(_b_spent / _b_allocated, 1.0) if _b_allocated > 0 else 0)
                            _over = _b_spent > _b_allocated
                            st.markdown(
                                f"{_b_spent:,.2f} of {_b_allocated:,.2f} spent"
                                + (f" ({_b_pct:.0f}%)" if _b_pct is not None else "")
                                + (" — **over budget**" if _over else "")
                            )
                        with _bcol2:
                            if st.button("🗑️", key=f"del_budget_{_b['id']}"):
                                if delete_budget(_b["id"], full_name):
                                    st.rerun()

            with st.expander("➕ Set a new budget"):
                if not assets:
                    st.caption("Add an asset first.")
                else:
                    with st.form("new_budget_form", clear_on_submit=True):
                        _budget_asset_choices = {a["name"]: a["id"] for a in assets}
                        _budget_asset_label = st.selectbox("Asset", list(_budget_asset_choices.keys()))
                        _budget_period = st.text_input("Period label", placeholder="e.g. 2026 Q3, FY2026")
                        _budget_amount = st.number_input("Allocated amount", min_value=0.0, value=0.0, step=100.0)
                        if st.form_submit_button("Set budget"):
                            if not _budget_period.strip():
                                st.error("Period label is required.")
                            elif create_budget(_budget_asset_choices[_budget_asset_label],
                                              _budget_period.strip(), _budget_amount, full_name):
                                st.success("Budget set.")
                                st.rerun()
                            else:
                                st.error("Failed to set budget — check the error log.")

        elif analytics_sub == "Safety":
            st.markdown("#### Safety Indicators")
            si = safety_leading_indicators(incidents, tasks)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Incidents", si["total_incidents"])
            c2.metric("Proactive Reports", si["proactive_reports"],
                      help="Near misses + hazard observations. A LEADING indicator.")
            c3.metric("Injuries", si["injuries"])
            c4.metric("Last 30 Days", si["last_30_days"])

            c5, c6 = st.columns(2)
            c5.metric("Near-miss share", f"{si['near_miss_ratio']}%" if si['near_miss_ratio'] is not None else "No data")
            c6.metric("Open, no corrective action", si["open_without_action"])

            if si["open_without_action"] > 0:
                st.warning(f"⚠️ {si['open_without_action']} open incident(s) have no corrective action recorded. "
                           "Unclosed corrective actions are a common audit finding.")
            st.info("**Reading these correctly matters.** A *rising* near-miss and hazard-report count usually means "
                    "reporting culture is improving, not that the site became more dangerous. The metric to worry about "
                    "is proactive reports falling while injuries hold steady — that pattern suggests under-reporting. "
                    "Don't set targets that reward fewer reports.")

            if incidents and PANDAS_AVAILABLE and PLOTLY_AVAILABLE:
                dfi = pd.DataFrame(incidents)
                if 'severity' in dfi.columns:
                    st.plotly_chart(px.pie(dfi, names='severity', title='Incidents by severity',
                                          color_discrete_sequence=GMC_CHART_COLORS),
                                    use_container_width=True)
                if 'incident_type' in dfi.columns:
                    st.plotly_chart(px.bar(dfi.groupby('incident_type').size().reset_index(name='count'),
                                            x='incident_type', y='count', title='Incidents by type',
                                            color_discrete_sequence=GMC_CHART_COLORS),
                                    use_container_width=True)

        if can(role, "analytics.export"):
            st.markdown("---")
            st.markdown("#### Exports")
            ecols = st.columns(5 if PDF_REPORT_AVAILABLE else 4)
            if ecols[0].button("📥 Tasks"):
                c = export_tasks_csv(tasks)
                if c:
                    st.download_button("Download", c, "tasks_export.csv", "text/csv", key="an_dl_tasks")
            if ecols[1].button("📥 Assets"):
                c = export_assets_csv(assets)
                if c:
                    st.download_button("Download", c, "assets_export.csv", "text/csv", key="an_dl_assets")
            if ecols[2].button("📥 Inventory"):
                c = export_inventory_csv(parts)
                if c:
                    st.download_button("Download", c, "inventory_export.csv", "text/csv", key="an_dl_inv")
            if ecols[3].button("📥 Incidents"):
                c = export_incidents_csv(incidents)
                if c:
                    st.download_button("Download", c, "incidents_export.csv", "text/csv", key="an_dl_inc")
            if PDF_REPORT_AVAILABLE and ecols[4].button("📄 PDF Report"):
                pdf_bytes = generate_pdf_report(tasks, assets, incidents)
                if pdf_bytes:
                    st.download_button("Download", pdf_bytes,
                                      f"mwdts_safety_report_{datetime.now().strftime('%Y%m%d')}.pdf",
                                      "application/pdf", key="an_dl_pdf")
                else:
                    st.error("Report generation failed — check the app's error log.")

            if PDF_REPORT_AVAILABLE and (role in ("supervisor", "superintendent") or is_owner(username)):
                st.markdown("---")
                st.markdown("#### 📊 Executive Monthly Report")
                st.caption("Board-ready summary: Safety (TRIFR), Production vs Target, Top 5 Cost Drivers. "
                          "Generated on demand — see the note below about automatic monthly emailing.")
                if st.button("📄 Generate Executive Report"):
                    exec_pdf = generate_executive_monthly_report(tasks, assets, incidents, parts_lookup)
                    if exec_pdf:
                        st.download_button("Download", exec_pdf,
                                          f"mwdts_executive_report_{datetime.now().strftime('%Y%m')}.pdf",
                                          "application/pdf", key="an_dl_exec_pdf")
                    else:
                        st.error("Report generation failed — check the app's error log.")
                st.caption("ℹ️ Automatically emailing this on the 1st of every month isn't something this app "
                          "can do on its own — Streamlit has no built-in background scheduler, only code that "
                          "runs while someone has the app open. Reaching that would need an external scheduler "
                          "(e.g. a scheduled script) calling this same report generator and emailing the result.")

        elif analytics_sub == "Electrical Health":
            st.markdown("#### ⚡ Heavy Equipment Electrical Health")
            st.caption("Alternator, starter, and battery failures by machine — built to enable a "
                      "targeted preventative swap before a haul truck dies in the pit, not just a "
                      "record of what already broke.")

            _elec_health = get_heavy_equipment_electrical_health(tasks, assets)
            if not _elec_health:
                st.info("No alternator, starter, or battery failures recorded yet. These are tracked "
                       "via the specific failure code selected when closing out a task — the general "
                       "\"Electrical fault\" code doesn't count here, since it doesn't say which "
                       "component actually failed.")
            else:
                st.markdown("##### Top Breakdown Liabilities")
                for r in _elec_health:
                    _parts_list = []
                    if r["alt"]: _parts_list.append(f"{r['alt']} alternator")
                    if r["starter"]: _parts_list.append(f"{r['starter']} starter")
                    if r["batt"]: _parts_list.append(f"{r['batt']} battery")
                    st.markdown(f"""
                    <div class="custom-card" style="border-left-color: #dc2626;">
                        <strong>{esc(r['asset_name'])}</strong>
                        <span class="status-badge" style="background:#dc2626;">{r['total']} failure(s)</span>
                        <p>{', '.join(_parts_list)}</p>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("##### Trends by Equipment Category")
                st.caption("Spots patterns a per-machine view can't — e.g. a failure type endemic to "
                          "one equipment class, not just one unlucky machine.")
                _trends = get_electrical_failure_trends_by_category(tasks, assets)
                if not _trends:
                    st.info("Not enough data yet to show category trends.")
                else:
                    _trend_rows = sorted(_trends.items(), key=lambda x: x[1], reverse=True)
                    for (category, component), count in _trend_rows:
                        st.write(f"**{esc(category)}** — {component}: {count} failure(s)")

elif selected_section == "Owner Console":
    # HARD GATE. The menu item is hidden for non-owners, but hiding a
    # menu is not access control — this check is the actual barrier.
    if not is_owner(username):
        st.error("🚫 This area is restricted to the account owner.")
        log_audit(full_name, "owner_console_denied", {"username": username})
        st.stop()

    st.subheader("🔑 Owner Console")
    st.caption(f"Signed in as the owner (`{esc(username)}`). Owner status is set by "
               "`OWNER_USERNAME` in secrets.toml and cannot be granted from inside "
               "the app.")

    if not SUPABASE_AVAILABLE:
        st.warning("No database connected — access management is unavailable in demo mode.")
        st.stop()

    owner_sub = option_menu(
        menu_title=None,
        options=["Access Requests", "Access Policies", "Active Users", "Decision History",
                "Auth Migration", "Feature Toggles", "Automation", "Settings"],
        icons=["person-plus-fill", "shield-exclamation", "people-fill", "journal-text",
              "shield-lock-fill", "toggles", "robot", "sliders"],
        orientation="horizontal", default_index=0, styles=menu_styles(),
    )

    _all = fetch_all_users_from_db()
    _pending = [u for u in _all if not u.get("is_approved") and not u.get("is_suspended")]
    _active = [u for u in _all if u.get("is_approved") and not u.get("is_suspended")]
    _blocked = [u for u in _all if u.get("is_suspended")]

    # ---------- ACCESS REQUESTS ----------
    if owner_sub == "Access Requests":
        _m1, _m2, _m3 = st.columns(3)
        _m1.metric("Pending", len(_pending))
        _m2.metric("Active", len(_active))
        _m3.metric("Suspended / Denied", len(_blocked))

        if not _pending:
            st.success("✅ No pending access requests.")
        else:
            st.markdown("### Requests awaiting your decision")
            st.caption("You choose the role that is granted. What the applicant "
                       "selected is only a request.")
            for u in _pending:
                with st.container(border=True):
                    _c1, _c2 = st.columns([3, 2])
                    with _c1:
                        st.markdown(f"**{esc(u.get('full_name'))}**  `{esc(u.get('username'))}`")
                        st.markdown(render_meta_chips([
                            ("fa-briefcase", u.get('job_title'), "neutral"),
                            ("fa-users", u.get('department'), "neutral"),
                            ("fa-id-card", f"ID: {u['employee_id']}" if u.get('employee_id') else None, "neutral"),
                            ("fa-envelope", u.get('email'), "neutral"),
                            ("fa-clock", f"Requested {_fmt_log_time(u['requested_at'])}" if u.get('requested_at') else None, "info"),
                        ]), unsafe_allow_html=True)
                        _req = u.get('requested_role') or 'Worker'
                        st.markdown(f"Requested access level: "
                                    f"<span class='priority-badge priority-"
                                    f"{'Critical' if _req == 'Superintendent' else 'Medium' if _req == 'Supervisor' else 'Low'}'>"
                                    f"{esc(_req)}</span>", unsafe_allow_html=True)
                        if _req == "Superintendent":
                            st.warning("⚠️ Superintendent grants delete rights, user "
                                       "management, and audit access. Verify this "
                                       "person's identity before approving.")
                    with _c2:
                        _grant = st.selectbox(
                            "Grant role", ["Worker", "Supervisor", "Superintendent"],
                            index=["Worker", "Supervisor", "Superintendent"].index(_req)
                            if _req in ("Worker", "Supervisor", "Superintendent") else 0,
                            key=f"grant_{u['username']}")
                        _note = st.text_input("Note (optional)", key=f"note_{u['username']}",
                                              placeholder="e.g. verified with HR")

                        _has_email = bool(u.get("email"))
                        _provision = False
                        if not _has_email:
                            if workspace_provisioning_configured():
                                _provision = st.checkbox(
                                    "📧 Create a real Workspace mailbox for them",
                                    key=f"provision_{u['username']}",
                                    help="Creates an actual, working mailbox via Google "
                                         "Workspace — not a placeholder value. Needed "
                                         "for self-service password reset to work; "
                                         "without it they'll rely on admin reset.")
                            else:
                                st.caption("No email on file. Workspace auto-provisioning "
                                          "isn't configured — see GOOGLE_WORKSPACE_SETUP.md, "
                                          "or leave this and use admin password reset later.")

                        _b1, _b2 = st.columns(2)
                        if _b1.button("✅ Approve", key=f"appr_{u['username']}",
                                      use_container_width=True):
                            _provisioned_email = None
                            if _provision:
                                _existing_locals = {
                                    e.split("@")[0] for a_u in _all
                                    if (e := a_u.get("email")) and "@" in e
                                }
                                _pok, _perr, _pemail, _ppass = provision_workspace_mailbox(
                                    u.get("full_name"), _grant, full_name, _existing_locals)
                                if _pok:
                                    _provisioned_email = _pemail
                                    st.session_state[f"_ws_created_{u['username']}"] = (_pemail, _ppass)
                                else:
                                    st.error(f"Mailbox creation failed: {_perr}. "
                                            "Approving without email — you can retry "
                                            "provisioning or use admin password reset later.")
                                    log_error(_perr, details={"username": u['username']},
                                             endpoint="owner_console_provision")

                            ok, err = approve_access(u['username'], _grant, full_name, _note or None)
                            if ok:
                                if _provisioned_email:
                                    _sync_res = supabase.table("facility_users").update({
                                        "email": _provisioned_email,
                                        "email_auto_provisioned": True,
                                        "workspace_provision_error": None,
                                    }).eq("username", u['username']).execute()
                                    if not _sync_res.data:
                                        # The Workspace mailbox WAS created (a real, billed
                                        # seat) — only the app's record of its address failed
                                        # to save. Losing track of that is worse than most
                                        # instances of this bug class, since undoing it means
                                        # manually checking the Workspace Admin Console.
                                        st.error(f"⚠️ A Workspace mailbox was created at "
                                                f"{_provisioned_email}, but saving that address "
                                                f"to their profile failed (Row Level Security?). "
                                                f"Check Workspace Admin Console — the mailbox "
                                                f"exists even though it's not recorded here.")
                                st.success(f"{u.get('full_name')} approved as {_grant}.")
                                st.rerun()
                            else:
                                st.error(friendly_db_error(err))
                        if _b2.button("🚫 Decline", key=f"deny_{u['username']}",
                                      use_container_width=True):
                            if not _note:
                                st.error("Please give a reason before declining — it is "
                                         "recorded and shown in the history.")
                            else:
                                ok, err = deny_access(u['username'], full_name, _note)
                                if ok:
                                    st.success("Request declined.")
                                    st.rerun()
                                else:
                                    st.error(friendly_db_error(err))

    # ---------- ACCESS POLICIES ----------
    elif owner_sub == "Access Policies":
        st.markdown("### 🛡️ Access Policies")
        st.caption(
            "Different in kind from Feature Toggles — those hide UI sections and are "
            "easily reversible. These change actual security behavior: who gets into "
            "the app at all, and whether a human ever looks at that decision."
        )

        if not SUPABASE_AVAILABLE:
            st.warning("No database connected — changes here work for this session only "
                      "and won't persist in demo mode.")

        _policies = fetch_access_policies()
        for _pol_key, (_pol_title, _pol_desc) in ACCESS_POLICIES.items():
            _cur = _policies[_pol_key]
            st.markdown(f"#### {_pol_title}")
            st.markdown(_pol_desc)
            if _cur:
                st.success("Currently **ON** — new sign-ups get immediate access, no review.")
            else:
                st.info("Currently **OFF** (default) — every new sign-up waits in "
                       "Access Requests until an Owner/Superintendent approves it.")

            if not _cur:
                if st.button("Turn ON — allow sign-in without approval", key=f"pol_on_{_pol_key}"):
                    st.session_state[f"_confirm_pol_{_pol_key}"] = True
                if st.session_state.get(f"_confirm_pol_{_pol_key}"):
                    st.warning("Anyone who reaches your sign-up page will get Worker-level "
                             "access immediately, with nobody reviewing who they are first. "
                             "Confirm you actually want this.")
                    _cc1, _cc2 = st.columns(2)
                    if _cc1.button("Yes, turn it on", key=f"pol_confirm_{_pol_key}", type="primary"):
                        if set_access_policy(_pol_key, True, full_name):
                            st.session_state.pop(f"_confirm_pol_{_pol_key}", None)
                            st.success("Turned on.")
                            st.rerun()
                        else:
                            st.error("Failed to update — check Row Level Security on app_feature_flags.")
                    if _cc2.button("Cancel", key=f"pol_cancel_{_pol_key}"):
                        st.session_state.pop(f"_confirm_pol_{_pol_key}", None)
                        st.rerun()
            else:
                if st.button("Turn OFF — require approval again", key=f"pol_off_{_pol_key}"):
                    if set_access_policy(_pol_key, False, full_name):
                        st.success("Turned off. New sign-ups will wait for approval again.")
                        st.rerun()
                    else:
                        st.error("Failed to update — check Row Level Security on app_feature_flags.")
            st.markdown("---")

    # ---------- ACTIVE USERS ----------
    elif owner_sub == "Active Users":
        st.markdown("### Who currently has access")
        _q = st.text_input("🔍 Filter by name, username, or role", "")
        _rows = _active + _blocked
        if _q:
            _ql = _q.lower()
            _rows = [u for u in _rows
                     if _ql in str(u.get('full_name', '')).lower()
                     or _ql in str(u.get('username', '')).lower()
                     or _ql in str(u.get('role', '')).lower()]
        if not _rows:
            st.info("No users match.")
        for u in _rows:
            _suspended = u.get("is_suspended", False)
            _owner_row = is_owner(u.get("username"))
            _colour = "#4b5563" if _suspended else "#15803d"
            with st.container(border=True):
                _owner_badge = " <span class='verified-badge'>OWNER</span>" if _owner_row else ""
                st.markdown(
                    f"**{esc(u.get('full_name'))}** `{esc(u.get('username'))}` "
                    f"<span class='status-badge' style='background:{_colour};'>"
                    f"{'SUSPENDED' if _suspended else esc(u.get('role', 'Worker'))}</span>"
                    f"{_owner_badge}",
                    unsafe_allow_html=True)
                st.markdown(
                    f"<small>{esc(u.get('job_title') or '—')} · "
                    f"{esc(u.get('department') or '—')} · "
                    f"{esc(u.get('email') or 'no email')}"
                    f"{' · approved by ' + esc(u.get('decision_by')) if u.get('decision_by') else ''}"
                    f"{' · last login ' + esc(_fmt_log_time(u.get('last_login'))) if u.get('last_login') else ' · never logged in'}"
                    f"</small>", unsafe_allow_html=True)
                if u.get("denial_reason"):
                    st.caption(f"Reason on file: {esc(u['denial_reason'])}")
                if u.get("email_auto_provisioned"):
                    st.caption("📧 This mailbox was auto-created by the app.")

                _ws_new = st.session_state.get(f"_ws_created_{u['username']}")
                if _ws_new:
                    _ws_email, _ws_pass = _ws_new
                    st.warning(f"⚠️ New Workspace mailbox created: **{esc(_ws_email)}** — "
                              "credentials shown once below. Relay both to them in person "
                              "along with their app password.")
                    st.code(f"Email:    {_ws_email}\nPassword: {_ws_pass}", language="text")
                    st.caption("They'll be asked to set a new Workspace password on first "
                              "Gmail login — that's separate from their app password.")
                    if st.button("I've recorded this — clear it from screen",
                                 key=f"clearws_{u['username']}"):
                        del st.session_state[f"_ws_created_{u['username']}"]
                        st.rerun()

                if _owner_row:
                    st.caption("🔒 The owner account cannot be modified from here. "
                               "Change OWNER_USERNAME in secrets.toml to hand over.")
                    continue

                with st.expander("Manage this user"):
                    _mc1, _mc2, _mc3 = st.columns(3)
                    _newrole = _mc1.selectbox(
                        "Role", ["Worker", "Supervisor", "Superintendent"],
                        index=["Worker", "Supervisor", "Superintendent"].index(u.get('role'))
                        if u.get('role') in ("Worker", "Supervisor", "Superintendent") else 0,
                        key=f"role_{u['username']}")
                    _reason = _mc2.text_input("Reason", key=f"reason_{u['username']}")
                    if _mc3.button("💾 Change role", key=f"chrole_{u['username']}"):
                        ok, err = set_user_role(u['username'], _newrole, full_name, _reason or None)
                        if ok:
                            st.success("Role updated.")
                            st.rerun()
                        else:
                            st.error(friendly_db_error(err))

                    _sc1, _sc2 = st.columns(2)
                    if _suspended:
                        if _sc1.button("♻️ Reinstate", key=f"reinst_{u['username']}",
                                       use_container_width=True):
                            ok, err = set_user_suspended(u['username'], False, full_name, _reason or None)
                            if ok:
                                st.success("Reinstated.")
                                st.rerun()
                            else:
                                st.error(friendly_db_error(err))
                    else:
                        if _sc1.button("⏸️ Suspend", key=f"susp_{u['username']}",
                                       use_container_width=True):
                            ok, err = set_user_suspended(u['username'], True, full_name, _reason or None)
                            if ok:
                                st.success("Suspended. They can no longer sign in.")
                                st.rerun()
                            else:
                                st.error(friendly_db_error(err))
                    _confirm = _sc2.checkbox("I understand removal is permanent",
                                             key=f"delok_{u['username']}")

                    st.markdown("---")
                    st.markdown("**🔑 Password reset**")
                    st.caption("Use this when self-service reset can't work — no email "
                              "on file, or SMTP isn't set up. Shown once; write it down "
                              "or relay it in person. They'll be forced to set a real "
                              "password on their next login.")
                    if st.button("🔑 Generate temporary password",
                                 key=f"pwreset_{u['username']}"):
                        ok, err, temp_pw = admin_reset_password(u['username'], full_name)
                        if ok:
                            st.session_state[f"_temp_pw_{u['username']}"] = temp_pw
                        else:
                            st.error(friendly_db_error(err))
                    _shown_pw = st.session_state.get(f"_temp_pw_{u['username']}")
                    if _shown_pw:
                        st.warning("⚠️ Shown once. It will not be retrievable after you "
                                  "leave this page.")
                        st.code(_shown_pw, language="text")
                        if st.button("I've recorded this — clear it from screen",
                                     key=f"clearpw_{u['username']}"):
                            del st.session_state[f"_temp_pw_{u['username']}"]
                            st.rerun()

                    st.markdown("---")
                    if st.button("🗑️ Remove permanently", key=f"del_{u['username']}",
                                 use_container_width=True, disabled=not _confirm):
                        ok, err = remove_user(u['username'], full_name, _reason or None)
                        if ok:
                            st.success("User removed.")
                            st.rerun()
                        else:
                            st.error(friendly_db_error(err))
                    st.caption("Prefer **Suspend** over Remove. Suspension blocks sign-in "
                               "but keeps the person's history attached to the work orders "
                               "and incidents they touched.")

    # ---------- DECISION HISTORY ----------
    elif owner_sub == "Decision History":
        st.markdown("### Every access decision ever made")
        st.caption("Append-only. Records survive user deletion, so you can still show "
                   "who granted access to whom after an incident.")
        _dec = fetch_access_decisions(200)
        if not _dec:
            st.info("No decisions recorded yet.")
        else:
            _icons = {"approved": "✅", "denied": "🚫", "suspended": "⏸️",
                      "reinstated": "♻️", "role_changed": "🔄", "removed": "🗑️",
                      "password_reset_by_admin": "🔑"}
            for d in _dec:
                _ic = _icons.get(d.get("action"), "•")
                _detail = ""
                if d.get("action") == "role_changed":
                    _detail = f" ({esc(d.get('old_role'))} → {esc(d.get('new_role'))})"
                elif d.get("new_role"):
                    _detail = f" as {esc(d.get('new_role'))}"
                st.markdown(
                    f"{_ic} **{esc(d.get('target_full_name') or d.get('target_username'))}** "
                    f"— {esc(d.get('action'))}{_detail} by **{esc(d.get('decided_by'))}** "
                    f"<small>{_fmt_log_time(d.get('decided_at'))}</small>",
                    unsafe_allow_html=True)
                if d.get("reason"):
                    st.caption(f"↳ {esc(d['reason'])}")
            if PANDAS_AVAILABLE and st.button("📥 Export decision history"):
                _df = pd.DataFrame(_dec)
                st.download_button("Download CSV", _df.to_csv(index=False),
                                   "access_decisions.csv", "text/csv", key="dl_decisions")

    # ---------- AUTH MIGRATION ----------
    elif owner_sub == "Auth Migration":
        st.markdown("### 🔐 Supabase Auth Migration — Step 1: Email Mapping")
        st.info(
            "**This step is safe and non-disruptive.** It only computes and stores the "
            "email each account will use for Supabase Auth later — it does NOT change how "
            "anyone logs in today. Nothing here affects the live app until a later step "
            "explicitly switches login over, which will be done separately and deliberately."
        )
        st.caption(
            "Why this exists: Supabase Auth identifies people by email, not username, and "
            "many workers here don't have one. Accounts without a real email get an internal "
            "placeholder — never shown or emailed to anyone, it exists only because Supabase "
            "Auth requires *some* email per account."
        )

        _all_users = fetch_all_users_from_db()
        _already = sum(1 for u in _all_users if u.get("auth_email"))
        _mcol1, _mcol2, _mcol3 = st.columns(3)
        _mcol1.metric("Total accounts", len(_all_users))
        _mcol2.metric("Already mapped", _already)
        _mcol3.metric("Remaining", len(_all_users) - _already)

        if st.button("🔍 Preview email mapping (computes nothing to the database)"):
            rows, duplicates = preview_auth_email_backfill()
            st.session_state["_auth_preview_rows"] = rows
            st.session_state["_auth_preview_duplicates"] = duplicates

        rows = st.session_state.get("_auth_preview_rows")
        duplicates = st.session_state.get("_auth_preview_duplicates")

        if rows is not None:
            if duplicates:
                st.error(
                    f"⚠️ **{len(duplicates)} real email(s) are shared by more than one "
                    f"account** — Supabase Auth requires unique emails, so these need "
                    f"resolving manually before they can be migrated. These accounts are "
                    f"excluded from the selection below until fixed."
                )
                for email, usernames in duplicates.items():
                    st.markdown(f"- `{esc(email)}` used by: {', '.join(f'`{esc(u)}`' for u in usernames)}")

            if PANDAS_AVAILABLE:
                _df = pd.DataFrame(rows)[["username", "full_name", "current_email",
                                          "computed_auth_email", "is_placeholder", "email_already_mapped"]]
                st.dataframe(_df, use_container_width=True, hide_index=True)
            else:
                for r in rows:
                    st.write(f"`{r['username']}` → `{r['computed_auth_email']}`"
                            f"{' (placeholder)' if r['is_placeholder'] else ''}"
                            f"{' ✓ email mapped' if r['email_already_mapped'] else ''}")

            _dup_usernames = {u for usernames in duplicates.values() for u in usernames} if duplicates else set()
            _eligible = [r["username"] for r in rows
                        if not r["email_already_mapped"] and r["username"] not in _dup_usernames]

            if _eligible:
                st.markdown("---")
                _selected = st.multiselect(
                    "Select accounts to migrate now",
                    options=_eligible, default=_eligible,
                    help="Defaults to everyone eligible. Remove anyone you want to hold back.",
                )
                if st.button(f"✅ Write email mapping for {len(_selected)} account(s)", type="primary"):
                    if not _selected:
                        st.warning("Nothing selected.")
                    else:
                        success, failures = run_auth_email_backfill(_selected, full_name)
                        if success:
                            st.success(f"Mapped {success} account(s).")
                        if failures:
                            st.error(f"{len(failures)} failed:")
                            for uname, reason in failures:
                                st.write(f"- `{uname}`: {reason}")
                        # Clear the stale preview so the numbers above reflect reality
                        st.session_state.pop("_auth_preview_rows", None)
                        st.session_state.pop("_auth_preview_duplicates", None)
                        st.rerun()
            elif rows and not duplicates:
                st.success("Every account is already mapped. Step 1 is complete.")

        st.markdown("---")
        st.markdown("### 🔐 Step 2: Provision Real Supabase Auth Accounts")
        st.info(
            "**Still non-disruptive.** This creates real Supabase Auth accounts in "
            "parallel with the existing login — nobody is forced onto anything new "
            "yet, and today's username/password login keeps working exactly as it "
            "does now. That switch is a separate, later, deliberate step (Phase 4)."
        )

        if not SUPABASE_ADMIN_AVAILABLE:
            st.warning(
                "**Not available yet.** This step needs a second, more powerful "
                "credential — your project's `service_role` key (called the "
                "**secret key** in newer Supabase projects) — added to your app's "
                "secrets as `SUPABASE_SERVICE_ROLE_KEY`. This is deliberately a "
                "*different* key from the one the rest of the app uses: it bypasses "
                "Row Level Security entirely and can create or delete accounts, so "
                "treat it with the same care as a root password — never share it, "
                "never commit it, and it should never be the same key used for "
                "anything client-facing.\n\n"
                "Find it in Supabase Dashboard → Project Settings → API "
                "(under **Project API keys** → `service_role`, or under **Secret "
                "keys** on newer projects)."
            )
        else:
            _prov_candidates = preview_auth_provisioning()
            _pc1, _pc2 = st.columns(2)
            _pc1.metric("Ready to provision", len(_prov_candidates))
            _already_provisioned = sum(1 for u in fetch_all_users_from_db() if u.get("auth_user_id"))
            _pc2.metric("Already provisioned", _already_provisioned)

            if not _prov_candidates:
                st.caption("Nobody is waiting on this step — either everyone's already "
                          "provisioned, or Step 1's email mapping hasn't run for them yet.")
            else:
                _prov_email_by_username = {u["username"]: u["auth_email"] for u in _prov_candidates}
                _prov_selected = st.multiselect(
                    "Select accounts to provision now",
                    options=[u["username"] for u in _prov_candidates],
                    default=[u["username"] for u in _prov_candidates],
                    help="Defaults to everyone eligible. Remove anyone you want to hold back.",
                    format_func=lambda uname: f"{uname} → {_prov_email_by_username.get(uname, '?')}",
                )
                if st.button(f"🔑 Create {len(_prov_selected)} Supabase Auth account(s)", type="primary"):
                    if not _prov_selected:
                        st.warning("Nothing selected.")
                    else:
                        with st.spinner("Creating accounts via the Supabase Admin API..."):
                            p_success, p_failures = provision_auth_accounts(_prov_selected, full_name)
                        if p_success:
                            st.success(f"Provisioned {p_success} account(s). Each is set to force a "
                                      f"password change on first sign-in, once Phase 4 is live.")
                        if p_failures:
                            st.error(f"{len(p_failures)} did not complete:")
                            for uname, reason in p_failures:
                                st.write(f"- `{uname}`: {reason}")
                        st.rerun()

    # ---------- FEATURE TOGGLES ----------
    elif owner_sub == "Feature Toggles":
        st.markdown("### 🎛️ Feature Toggles")
        st.caption(
            "Turn whole sections of the app on or off for everyone, instantly — no code "
            "change, no redeploy, no waiting on a fix. A toggle takes effect the moment "
            "you flip it; anyone currently on a section you turn off will find it gone "
            "from their navigation the next time the app reruns (their next click)."
        )
        st.info(
            "Task Dashboard, Admin, and Profile are deliberately not toggleable here — "
            "Task Dashboard is the core reason this app exists, and Admin is where this "
            "screen itself lives, so disabling it could lock out the only way to turn "
            "things back on."
        )

        if not SUPABASE_AVAILABLE:
            st.warning("No database connected — toggles work for this session only and "
                      "won't persist in demo mode.")

        _current_flags = fetch_feature_flags()  # fresh read, not the cached one, so this
                                                  # screen always shows true current state
        for _mod_name, _mod_desc in TOGGLEABLE_MODULES.items():
            _tcol1, _tcol2 = st.columns([5, 1])
            with _tcol1:
                st.markdown(f"**{_mod_name}**")
                st.caption(_mod_desc)
            with _tcol2:
                _new_val = st.toggle("Enabled", value=_current_flags[_mod_name],
                                     key=f"flag_toggle_{_mod_name}", label_visibility="collapsed")
            if _new_val != _current_flags[_mod_name]:
                if set_feature_flag(_mod_name, _new_val, full_name):
                    st.rerun()
                else:
                    st.error(f"Failed to update — check Row Level Security on app_feature_flags.")
            st.markdown("---")

    # ---------- AUTOMATION ----------
    elif owner_sub == "Automation":
        st.markdown("### 🤖 Escalations")
        st.caption(
            "Checks for overdue tasks and permits expiring within the hour, and notifies "
            "every Superintendent (for overdue tasks) or the issuing supervisor (for expiring "
            "permits). **This is not a scheduled background job** — Streamlit has no true "
            "scheduler, so this only runs when triggered here, or automatically once per "
            "session when a Superintendent or Owner opens Task Dashboard. Something expiring "
            "at 3am with nobody using the app won't be caught until someone next opens it. "
            "Genuine round-the-clock automation would need something outside this app "
            "entirely — a scheduled GitHub Action or Supabase Edge Function hitting a "
            "dedicated trigger, not something a Streamlit page can promise on its own."
        )
        if st.button("▶️ Run escalation check now"):
            _esc_result = run_escalations(st.session_state.tasks, fetch_permits(), full_name)
            st.success(f"Checked. {_esc_result['overdue_notified']} overdue task(s) and "
                      f"{_esc_result['permits_notified']} soon-expiring permit(s) triggered a notification.")

    # ---------- SETTINGS ----------
    elif owner_sub == "Settings":
        st.markdown("### 🔍 Secrets Diagnostics")
        st.caption("Shows which secret NAMES this app can actually see right now — never the "
                  "values themselves. Useful for confirming a key you just added in Streamlit "
                  "Cloud's Secrets settings is actually being read, without exposing it here.")
        if _diag.get("secrets_readable"):
            st.success("✅ secrets.toml is readable.")
            _found_keys = _diag.get("secret_keys_found", [])
            if _found_keys:
                st.write("**Detected secret names:**")
                for k in _found_keys:
                    st.write(f"- `{k}`")
            else:
                st.warning("No secrets are configured at all yet.")
            st.markdown("---")
            st.write("**AI provider keys specifically:**")
            for _key_name, _key_val in [("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY),
                                        ("OPENAI_API_KEY", OPENAI_API_KEY),
                                        ("GEMINI_API_KEY", GEMINI_API_KEY)]:
                if _key_val:
                    st.success(f"✅ `{_key_name}` is set ({len(_key_val)} characters).")
                else:
                    st.info(f"⬜ `{_key_name}` is not set.")
            st.caption(f"AI features currently: {'✅ enabled' if AI_FEATURES_AVAILABLE else '❌ disabled'} "
                      "— this must show enabled for the Assistant room to appear in Chat.")
        else:
            st.error(f"❌ secrets.toml could not be read: {_diag.get('secrets_error', 'unknown error')}")

        st.markdown("---")
        st.markdown("### 🐞 Recent Error Log")
        st.caption("The specific exception behind a generic failure message elsewhere in the app "
                  "— e.g. why an AI call actually failed, not just that it did.")
        if SUPABASE_AVAILABLE:
            try:
                _ai_only = st.checkbox("Show AI-related errors only", value=True, key="err_log_ai_filter")
                _err_query = supabase.table("app_errors").select("*").order("created_at", desc=True).limit(30)
                if _ai_only:
                    _err_query = _err_query.like("endpoint", "generate_smart_text%")
                _err_res = _err_query.execute()
                _recent_errors = _err_res.data or []
                if not _recent_errors:
                    st.info("No matching errors logged." if _ai_only else "No errors logged yet.")
                else:
                    for err in _recent_errors:
                        with st.expander(f"{err.get('endpoint', 'unknown')} — {_fmt_log_time(err.get('created_at'))}"):
                            st.code(err.get("error_message", ""), language=None)
                            if err.get("error_details"):
                                st.caption(f"Details: {err['error_details']}")
            except Exception as e:
                st.error(f"Couldn't load error log: {e}")
        st.markdown("### 🏢 Company Logo")
        st.caption("Shown as a bar above the header on every screen, including the login page. "
                  "Leave empty and nothing extra is shown — the app looks exactly as it does now.")

        if not SUPABASE_AVAILABLE:
            st.warning("No database connected — a logo can be uploaded here but won't actually "
                      "persist or display, since there's nowhere real to store the file in demo mode.")

        _current_logo = fetch_branding()
        if _current_logo and not _current_logo.startswith("memory://"):
            st.image(_current_logo, width=240, caption="Current logo")
            if st.button("🗑️ Remove logo"):
                if remove_logo(full_name):
                    st.success("Logo removed.")
                    st.rerun()
                else:
                    st.error("Failed to remove logo. Check Row Level Security on app_branding.")
        else:
            st.caption("No logo set yet.")

        _logo_file = st.file_uploader("Upload a logo", type=["jpg", "jpeg", "png", "gif", "webp"],
                                      key="logo_uploader")
        if _logo_file is not None:
            if st.button("📤 Set as company logo"):
                _bytes = _logo_file.getvalue()
                if upload_logo(_bytes, _logo_file.name, full_name):
                    st.success("Logo updated.")
                    st.rerun()
                else:
                    st.error("Upload failed.")

        st.markdown("---")
        st.markdown("### 📢 Announcement Ticker")
        st.caption("A scrolling strip between the logo and the header, shown on every screen. "
                  "Multiple active announcements join into one continuous strip. Leave none "
                  "active and nothing extra is shown.")

        if not SUPABASE_AVAILABLE:
            st.warning("No database connected — announcements can be added here but won't "
                      "persist in demo mode.")

        _all_announcements = fetch_all_announcements()
        if _all_announcements:
            for _a in _all_announcements:
                _acol1, _acol2, _acol3 = st.columns([6, 1, 1])
                _acol1.write(("🟢 " if _a.get("is_active") else "⚪ ") + str(_a.get("message", "")))
                _toggle_label = "Deactivate" if _a.get("is_active") else "Activate"
                if _acol2.button(_toggle_label, key=f"ann_toggle_{_a['id']}"):
                    if set_announcement_active(_a['id'], not _a.get("is_active"), full_name):
                        st.rerun()
                    else:
                        st.error("Update failed — check Row Level Security on app_announcements.")
                if _acol3.button("🗑️", key=f"ann_del_{_a['id']}"):
                    if delete_announcement(_a['id'], full_name):
                        st.rerun()
                    else:
                        st.error("Delete failed.")
        else:
            st.caption("No announcements yet.")

        with st.form("new_announcement_form", clear_on_submit=True):
            _new_ann = st.text_input("New announcement", max_chars=200,
                                     placeholder="e.g. 'Toolbox talk today at 2pm — Workshop B'")
            if st.form_submit_button("➕ Add announcement"):
                ok, err = create_announcement(_new_ann, full_name)
                if ok:
                    st.success("Added.")
                    st.rerun()
                else:
                    st.error(err or "Failed to add announcement.")

        st.markdown("---")
        st.markdown("### 🖼️ Poster Slideshow")
        st.caption(
            "A large auto-advancing image banner between the logo and the ticker, shown "
            "on every screen. No hard limit on how many you can add — each one gets an "
            "equal slot in the rotation, 5 seconds by default, so more posters means a "
            "longer full cycle before it repeats. 3–6 tends to feel right; a couple dozen "
            "would still work correctly, just take a while to loop back around. One poster "
            "shows as a static image with no rotation at all."
        )

        if not SUPABASE_AVAILABLE:
            st.warning("No database connected — posters can be uploaded here but won't "
                      "actually persist or display in demo mode.")

        _all_posters = fetch_all_posters()
        if _all_posters:
            for _p in _all_posters:
                _pcol1, _pcol2, _pcol3 = st.columns([5, 1, 1])
                with _pcol1:
                    st.image(_p["image_url"], width=160)
                    st.caption(("🟢 Active" if _p.get("is_active") else "⚪ Inactive"))
                _toggle_label = "Deactivate" if _p.get("is_active") else "Activate"
                if _pcol2.button(_toggle_label, key=f"poster_toggle_{_p['id']}"):
                    if set_poster_active(_p['id'], not _p.get("is_active"), full_name):
                        st.rerun()
                    else:
                        st.error("Update failed — check Row Level Security on app_posters.")
                if _pcol3.button("🗑️", key=f"poster_del_{_p['id']}"):
                    if delete_poster(_p['id'], full_name):
                        st.rerun()
                    else:
                        st.error("Delete failed.")
        else:
            st.caption("No posters yet.")

        _poster_file = st.file_uploader("Upload a poster", type=["jpg", "jpeg", "png", "webp"],
                                        key="poster_uploader")
        if _poster_file is not None:
            if st.button("📤 Add poster"):
                if upload_poster(_poster_file.getvalue(), _poster_file.name, full_name):
                    st.success("Added.")
                    st.rerun()
                else:
                    st.error("Failed to add poster.")

        st.markdown("---")
        st.markdown("### Ownership")
        st.info(f"Owner account: **`{esc(OWNER_USERNAME)}`**\n\n"
                "This is read from `OWNER_USERNAME` in `.streamlit/secrets.toml`. "
                "It is deliberately **not** editable here — if it were, anyone who "
                "reached this screen could take ownership. To hand over, edit "
                "secrets.toml and restart the app.")

        st.markdown("### Access summary")
        _s1, _s2, _s3, _s4 = st.columns(4)
        _s1.metric("Total accounts", len(_all))
        _s2.metric("Active", len(_active))
        _s3.metric("Pending", len(_pending))
        _s4.metric("Suspended", len(_blocked))

        _supers = [u for u in _active if str(u.get('role', '')).lower() == 'superintendent']
        st.markdown(f"**Superintendents ({len(_supers)})** — these accounts can delete "
                    "records and read the audit log:")
        for u in _supers:
            st.write(f"- {esc(u.get('full_name'))} (`{esc(u.get('username'))}`)"
                     f"{' — owner' if is_owner(u.get('username')) else ''}")
        if len(_supers) > 3:
            st.warning("More Superintendents than most sites need. Each one can delete "
                       "work orders and view the audit log — worth reviewing whether "
                       "they all still require that level.")

        st.markdown("---")
        st.markdown("### 📧 Email delivery health")
        _smtp_configured = bool(_secret_get("SMTP_SERVER") and _secret_get("SMTP_USER")
                                and _secret_get("SMTP_PASSWORD"))
        if not _smtp_configured:
            st.warning("SMTP is not configured. Password resets, task assignment emails, "
                      "and broadcast emails are all silently skipped — nothing errors, "
                      "they just never send. Add SMTP_SERVER / SMTP_USER / SMTP_PASSWORD "
                      "to secrets.toml to enable them.")
        else:
            st.success(f"SMTP configured: `{esc(_secret_get('SMTP_SERVER'))}` as "
                      f"`{esc(_secret_get('SMTP_USER'))}`.")
            with st.form("email_health_check", clear_on_submit=True):
                _test_to = st.text_input("Send a test email to",
                                        value=_secret_get("SMTP_FROM", ""))
                _test_go = st.form_submit_button("📤 Send test email")
                if _test_go:
                    if not _test_to or "@" not in _test_to:
                        st.error("Enter a valid email address.")
                    else:
                        _ok, _err = send_email_notification(
                            _test_to, "Mine & Workshop Tracker — test email",
                            "<p>This confirms SMTP delivery is working from your "
                            "Mine & Workshop Tracker deployment.</p>"
                            f"<p>Sent by {esc(full_name)} via the Owner Console.</p>",
                            _return_error=True)
                        if _ok:
                            st.success("Sent. Check the inbox (and spam folder).")
                        else:
                            st.error(f"Failed: {_err}")

        st.markdown("---")
        st.markdown("### 💬 Slack / Teams Notifications")
        st.caption("Automatically sent on task status changes, task deletion, incident reports, "
                  "and shift handover safety concerns.")
        if not SLACK_WEBHOOK and not TEAMS_WEBHOOK:
            st.info("Neither is configured. Add `SLACK_WEBHOOK` and/or `TEAMS_WEBHOOK` to secrets.toml "
                   "(each is independent — configure one, both, or neither).")
        else:
            if SLACK_WEBHOOK:
                st.success("Slack webhook configured.")
            if TEAMS_WEBHOOK:
                st.success("Teams webhook configured.")
                st.caption("⚠️ If this webhook URL was set up before mid-2026, it may be using Microsoft's "
                          "old \"Office 365 Connector\" style, which was retired in a rollout completing "
                          "May 22, 2026. If test messages below fail, the fix is generating a NEW webhook "
                          "URL via Teams' Workflows app (search \"Workflows\" in Teams → \"When a Teams "
                          "webhook request is received\" template) — the message format this app sends "
                          "hasn't changed, only how that URL is obtained has.")
            if st.button("📤 Send test notification"):
                _test_msg = f"Test notification from Mine & Workshop Tracker, sent by {full_name} via Owner Console."
                if SLACK_WEBHOOK:
                    _s_ok, _s_err = send_slack_notification(_test_msg, _return_error=True)
                    if _s_ok:
                        st.success("Slack: sent.")
                    else:
                        st.error(f"Slack failed: {_s_err}")
                if TEAMS_WEBHOOK:
                    _t_ok, _t_err = send_teams_notification(_test_msg, _return_error=True)
                    if _t_ok:
                        st.success("Teams: sent.")
                    else:
                        st.error(f"Teams failed: {_t_err}")

        st.markdown("---")
        st.markdown("---")
        st.markdown("### 📧 Google Workspace mailbox provisioning")
        if not GOOGLE_WORKSPACE_LIB_AVAILABLE:
            st.warning("`google-api-python-client` and `google-auth` are not installed. "
                      "Add them to requirements.txt: `pip install google-api-python-client "
                      "google-auth`. Until then, mailbox auto-creation is unavailable and "
                      "the checkbox won't appear on access requests.")
        elif not workspace_provisioning_configured():
            st.info("Not configured. Applicants without email fall back to admin password "
                    "reset. See **GOOGLE_WORKSPACE_SETUP.md** to enable real mailbox "
                    "creation via Google Workspace.")
        else:
            st.success(f"Configured. New mailboxes are created on "
                      f"`{esc(_secret_get('GOOGLE_WORKSPACE_DOMAIN', 'gmc.com'))}`, "
                      f"impersonating `{esc(_secret_get('GOOGLE_WORKSPACE_ADMIN_EMAIL'))}`.")
            _provisioned_count = sum(1 for u in _all if u.get("email_auto_provisioned"))
            st.metric("Mailboxes auto-created by this app", _provisioned_count)
            with st.form("workspace_health_check", clear_on_submit=True):
                st.caption("Verifies the service account can authenticate and call the "
                          "Directory API — does NOT create a test mailbox.")
                _wc_go = st.form_submit_button("🔎 Test Workspace connection")
                if _wc_go:
                    _svc, _svcerr = _get_workspace_directory_service()
                    if _svc:
                        try:
                            _svc.users().list(customer="my_customer", maxResults=1).execute()
                            st.success("Connected. The service account can reach the "
                                      "Directory API with the configured delegation.")
                        except Exception as _e:
                            st.error(f"Authenticated, but the API call failed: "
                                    f"{type(_e).__name__}: {_e}")
                    else:
                        st.error(f"Could not authenticate: {_svcerr}")


        st.caption("Session-based lockout — resets if the app restarts or the "
                  "attacker opens a new session. It slows casual attempts, not a "
                  "determined one. Treat it as a speed bump, not a control.")
        _lockstate = st.session_state.get("login_attempts", {})
        _locked_now = [k for k in _lockstate
                      if is_login_locked(k)[0] and not k.startswith("reset:")]
        if _locked_now:
            st.warning(f"Currently locked out: {', '.join(_locked_now)}")
        else:
            st.info("No accounts currently locked out (this session).")

elif selected_section == "Chat":
    st.subheader("💬 Real‑time Chat")

    room = st.session_state.chat_room

    # In-page room switcher, so common room changes don't require going
    # back to the sidebar. Directly changing chat_room + rerun is safe
    # here (unlike the sidebar buttons) because we're already inside
    # the Chat section for this run — the nav widget's own key keeps it
    # pointed at "Chat" on the next rerun without needing navigate_to().
    _switch_cols = st.columns([1, 1, 1, 1]) if AI_FEATURES_AVAILABLE else st.columns([1, 1, 2])
    if _switch_cols[0].button("🌍 Global", use_container_width=True,
                              disabled=(room == "global")):
        st.session_state.chat_room = "global"
        st.rerun()
    if can(role, "chat.supervisor_room"):
        if _switch_cols[1].button("🔒 Supervisor", use_container_width=True,
                                  disabled=(room == "supervisor")):
            st.session_state.chat_room = "supervisor"
            st.rerun()
    if AI_FEATURES_AVAILABLE:
        if _switch_cols[2].button("🤖 Assistant", use_container_width=True,
                                  disabled=(room == "ai_assistant")):
            st.session_state.chat_room = "ai_assistant"
            st.rerun()

    if room == "global":
        st.markdown(
            '<div class="chat-room-header"><div class="chat-room-icon">'
            '<i class="fas fa-earth-americas"></i></div><div>'
            '<div class="chat-room-title">Global Chat</div>'
            '<div class="chat-room-sub">Visible to everyone with access to this app</div>'
            '</div></div>', unsafe_allow_html=True)
    elif room == "supervisor":
        if not can(role, "chat.supervisor_room"):
            st.error("You don't have permission to view the Supervisor room.")
            st.stop()
        st.markdown(
            '<div class="chat-room-header"><div class="chat-room-icon">'
            '<i class="fas fa-user-shield"></i></div><div>'
            '<div class="chat-room-title">Supervisor Room</div>'
            '<div class="chat-room-sub">Supervisors and Superintendent only</div>'
            '</div></div>', unsafe_allow_html=True)
    elif room == "ai_assistant":
        st.markdown(
            '<div class="chat-room-header"><div class="chat-room-icon">'
            '<i class="fas fa-robot"></i></div><div>'
            '<div class="chat-room-title">Maintenance Assistant</div>'
            '<div class="chat-room-sub">Answers grounded in this app\'s current data — not a general-purpose chatbot</div>'
            '</div></div>', unsafe_allow_html=True)

        if "_ai_assistant_history" not in st.session_state:
            st.session_state["_ai_assistant_history"] = []

        for _msg in st.session_state["_ai_assistant_history"]:
            if _msg["role"] == "user":
                # Only the part after "Question: " is shown — the full
                # message sent to the AI also carries the system
                # context/data summary prefix, which would be noisy and
                # repetitive to show back to the person who just typed
                # a short question.
                _display_text = _msg["content"].split("Question: ", 1)[-1]
                st.markdown(
                    f"<div class='chat-message self'>{render_avatar_html('You')}"
                    f"<div class='chat-body'><span class='sender'>You</span>"
                    f"<div class='chat-text'>{esc(_display_text)}</div></div></div>",
                    unsafe_allow_html=True)
            else:
                st.markdown(
                    f"<div class='chat-message'>{render_avatar_html('Assistant')}"
                    f"<div class='chat-body'><span class='sender'>🤖 Assistant</span>"
                    f"<div class='chat-text'>{esc(_msg['content'])}</div></div></div>",
                    unsafe_allow_html=True)

        _ai_question = st.text_input("Ask about tasks, assets, incidents, or costs...", key="ai_assistant_input")
        if st.button("Send", key="ai_assistant_send"):
            if _ai_question.strip():
                with st.spinner("Thinking..."):
                    _ai_parts_lookup = {p['id']: p for p in st.session_state.get("parts", [])}
                    _context = get_app_context_summary(st.session_state.tasks, st.session_state.get("assets", []),
                                                        st.session_state.incidents, _ai_parts_lookup)
                    _answer = ask_maintenance_assistant(
                        _ai_question, _context, st.session_state["_ai_assistant_history"])
                if _answer:
                    # Both turns appended together — keeps the history
                    # list always holding complete user/assistant PAIRS,
                    # never a dangling question with no answer if
                    # something failed partway through.
                    st.session_state["_ai_assistant_history"].append(
                        {"role": "user", "content": f"Question: {_ai_question}"})
                    st.session_state["_ai_assistant_history"].append(
                        {"role": "assistant", "content": _answer})
                    st.rerun()
                else:
                    st.error("Couldn't get an answer right now — check the AI provider configuration in Owner Console.")
        if st.session_state["_ai_assistant_history"] and st.button("Clear conversation", key="ai_assistant_clear"):
            st.session_state["_ai_assistant_history"] = []
            st.rerun()

    elif room.startswith("private:"):
        partner = st.session_state.chat_partner
        st.markdown(
            f'<div class="chat-room-header">{render_avatar_html(partner)}<div>'
            f'<div class="chat-room-title">Private — {esc(partner)}</div>'
            f'<div class="chat-room-sub">Only visible to you and {esc(partner)}</div>'
            f'</div></div>', unsafe_allow_html=True)
        st.warning(
            "⚠️ **Not end-to-end encrypted.** Messages here are obfuscated, not securely encrypted: "
            "the key is derived from the two usernames plus a fixed salt, so anyone who knows both "
            "usernames — or who can read the app's source — can decrypt them. Server administrators "
            "can also read them. **Do not use this channel for anything confidential** "
            "(personnel matters, incident specifics, credentials)."
        )
    else:
        st.warning("Unknown room. Switching to Global.")
        st.session_state.chat_room = "global"
        st.rerun()

    if not st.session_state.chat_messages_cache:
        st.session_state.chat_messages_cache = fetch_messages(room=room, limit=200)

    if SUPABASE_AVAILABLE:
        channel_name = f"chat_{room.replace(':', '_').replace('@', '_')}"
        try:
            if st.session_state.chat_channel:
                try:
                    supabase.remove_channel(st.session_state.chat_channel)
                except:
                    pass
                st.session_state.chat_channel = None

            channel = supabase.channel(channel_name)
            def on_insert(payload):
                new_msg = payload['new']
                if not any(m.get('id') == new_msg.get('id') for m in st.session_state.chat_messages_cache):
                    st.session_state.chat_messages_cache.insert(0, new_msg)
                    st.session_state.chat_messages_cache = st.session_state.chat_messages_cache[:200]
                    st.rerun()
            channel.on('postgres_changes', event='INSERT', schema='public', table='chat_messages', callback=on_insert)
            channel.subscribe()
            st.session_state.chat_channel = channel
        except Exception:
            pass

    messages = [m for m in st.session_state.chat_messages_cache if m['room'] == room]
    if messages:
        st.caption(f"{len(messages)} message{'s' if len(messages) != 1 else ''} in this room")
        _last_date = None
        for msg in reversed(messages):
            sender = msg['sender']
            is_encrypted = msg.get('is_encrypted', False)
            content = msg['message']
            # _parse_dt is the same timezone-safe parser used everywhere
            # else in this file — handles both 'Z' and '+00:00' suffixed
            # timestamps and never raises, unlike the raw
            # datetime.fromisoformat() this replaced.
            msg_dt = _parse_dt(msg.get('created_at'))
            timestamp = msg_dt.strftime("%H:%M") if msg_dt else "??:??"

            if msg_dt:
                msg_date = msg_dt.date()
                if msg_date != _last_date:
                    _today = datetime.now().date()
                    if msg_date == _today:
                        date_label = "Today"
                    elif (_today - msg_date).days == 1:
                        date_label = "Yesterday"
                    else:
                        date_label = msg_dt.strftime("%B %d, %Y")
                    st.markdown(f'<div class="chat-date-sep">{esc(date_label)}</div>',
                               unsafe_allow_html=True)
                    _last_date = msg_date

            if room.startswith("private:") and is_encrypted:
                parts = room.split(":")[1].split("_")
                key = derive_key(parts[0], parts[1])
                try:
                    content = decrypt_message(content, key)
                except Exception:
                    content = "🔒 [Decryption failed]"

            col_text, col_delete = st.columns([5, 1])
            with col_text:
                if sender == full_name:
                    st.markdown(
                        f"<div class='chat-message self'>{render_avatar_html('You')}"
                        f"<div class='chat-body'><span class='sender'>You</span> "
                        f"<span class='timestamp'>{timestamp}</span>"
                        f"<div class='chat-text'>{esc(content)}</div></div></div>",
                        unsafe_allow_html=True)
                else:
                    st.markdown(
                        f"<div class='chat-message'>{render_avatar_html(sender)}"
                        f"<div class='chat-body'><span class='sender'>{esc(sender)}</span> "
                        f"<span class='timestamp'>{timestamp}</span>"
                        f"<div class='chat-text'>{esc(content)}</div></div></div>",
                        unsafe_allow_html=True)
            with col_delete:
                if sender == full_name:
                    if st.button("🗑️", key=f"del_msg_{msg['id']}"):
                        if delete_message(msg['id'], full_name):
                            st.success("Message deleted!")
                            st.session_state.chat_messages_cache = [m for m in st.session_state.chat_messages_cache if m['id'] != msg['id']]
                            st.rerun()
                        else:
                            st.error("Failed to delete message.")
    else:
        if room == "global":
            st.info("💬 No messages yet — be the first to say something to everyone.")
        elif room == "supervisor":
            st.info("💬 No messages yet in the Supervisor room.")
        elif room.startswith("private:"):
            st.info(f"💬 No messages yet with {st.session_state.chat_partner} — say hello.")
        else:
            render_empty_state("fa-comments", "No messages yet", "Start the conversation.")

    with st.container():
        st.markdown("---")
        msg_input = st.text_area("Message", height=100, key="chat_input_text",
                                 value=st.session_state.chat_input_value,
                                 placeholder="Write a message…")
        col_send, col_clear = st.columns([1, 5])
        with col_send:
            if st.button('📤 Send', use_container_width=True):
                if msg_input.strip():
                    encrypted = False
                    final_msg = msg_input
                    if room.startswith("private:"):
                        parts = room.split(":")[1].split("_")
                        key = derive_key(parts[0], parts[1])
                        final_msg = encrypt_message(msg_input, key)
                        encrypted = True
                    success = send_message(
                        sender=full_name,
                        receiver=st.session_state.chat_partner if room.startswith("private:") else None,
                        room=room,
                        message=final_msg,
                        encrypted=encrypted
                    )
                    if success:
                        st.success("Message sent!")
                        st.session_state.chat_input_value = ""
                        st.session_state.chat_messages_cache = fetch_messages(room=room, limit=200)
                        st.rerun()
                    else:
                        st.error("Failed to send message. Check database or ensure table exists.")
                else:
                    st.warning("Message cannot be empty.")
        with col_clear:
            if st.button('🧹 Clear input', use_container_width=True):
                st.session_state.chat_input_value = ""
                st.rerun()

# ---- FEEDBACK / SUGGESTIONS BOARD ----
elif selected_section == "Feedback":
    st.subheader("💡 App Feedback & Suggestions")
    can_manage_feedback = can(role, "feedback.manage")

    if can_manage_feedback:
        st.caption("Submit ideas for improving this app, and upvote the ones you want built next.")
        feedback_tabs = ["All Suggestions", "Submit Suggestion"]
        fb_icons = ["lightbulb", "plus-circle"]
    else:
        st.caption("Submit ideas for improving this app. Suggestions are reviewed by the "
                  "site administrator — you can see the status of your own submissions here, "
                  "but not what others have submitted.")
        feedback_tabs = ["My Suggestions", "Submit Suggestion"]
        fb_icons = ["file-earmark-text", "plus-circle"]

    fb_sub = option_menu(
        menu_title=None, options=feedback_tabs,
        icons=fb_icons,
        orientation="horizontal", default_index=0, styles=menu_styles(),
    )

    all_feedback = fetch_all_feedback()
    all_votes = fetch_all_feedback_votes()
    _vote_counts = {}
    _my_votes = set()
    for v in all_votes:
        fid = v.get("feedback_id")
        _vote_counts[fid] = _vote_counts.get(fid, 0) + 1
        if v.get("voted_by") == full_name:
            _my_votes.add(fid)

    if fb_sub in ("All Suggestions", "My Suggestions"):
        # Admins see every submission; everyone else sees only their own —
        # this is the actual visibility restriction. It mirrors the same
        # "All Incidents" vs "My Reports" split already used for Incident
        # Reports, rather than inventing a new pattern for this screen.
        visible_feedback = all_feedback if can_manage_feedback else \
            [f for f in all_feedback if f.get("submitted_by") == full_name]

        if fb_sub == "All Suggestions":
            _fcol1, _fcol2, _fcol3 = st.columns(3)
            _sort_by = _fcol1.selectbox("Sort by", ["Most Voted", "Newest"])
            _status_filter = _fcol2.selectbox("Status", ["All"] + FEEDBACK_STATUSES)
            _category_filter = _fcol3.selectbox("Category", ["All"] + FEEDBACK_CATEGORIES)
            if _status_filter != "All":
                visible_feedback = [f for f in visible_feedback if f.get("status") == _status_filter]
            if _category_filter != "All":
                visible_feedback = [f for f in visible_feedback if f.get("category") == _category_filter]
            if _sort_by == "Most Voted":
                visible_feedback = sorted(visible_feedback, key=lambda f: _vote_counts.get(f["id"], 0), reverse=True)
            # "Newest" is already the default fetch order (desc by id)

        if not visible_feedback:
            st.info("No suggestions match these filters yet." if (all_feedback) else
                    "No suggestions yet — be the first to submit one.")

        if can_manage_feedback and all_feedback and st.button("📥 Export all suggestions as CSV"):
            _csv = export_feedback_csv(all_feedback, _vote_counts)
            if _csv:
                st.download_button("Download CSV", _csv, "feedback_export.csv", "text/csv",
                                  key="dl_feedback_csv")

        _status_tone = {"New": "info", "Under Review": "warn", "Planned": "info",
                        "Implemented": "ok", "Declined": "neutral"}

        for f in visible_feedback:
            fid = f["id"]
            count = _vote_counts.get(fid, 0)
            already_voted = fid in _my_votes
            tone = _status_tone.get(f.get("status", "New"), "neutral")

            _vcol, _bcol = st.columns([1, 8])
            with _vcol:
                st.markdown('<div class="vote-btn-wrap">', unsafe_allow_html=True)
                _label = f"▲ {count}"
                if st.button(_label, key=f"vote_{fid}",
                            help="Remove your upvote" if already_voted else "Upvote this idea",
                            type="primary" if already_voted else "secondary",
                            use_container_width=True):
                    if toggle_feedback_vote(fid, full_name, already_voted):
                        st.rerun()
                    else:
                        st.error("Vote didn't register — check Row Level Security "
                                "on app_feedback_votes.")
                st.markdown('</div>', unsafe_allow_html=True)
            with _bcol:
                _fb_chips = render_meta_chips([
                    ("fa-user", f.get('submitted_by'), "neutral"),
                    ("fa-clock", _fmt_log_time(f['created_at']) if f.get('created_at') else None, "neutral"),
                ])
                st.markdown(f"""
                <div class="custom-card" style="border-left-color: var(--tone-{tone});">
                    <strong>{esc(f.get('title'))}</strong>
                    <span class="priority-badge" style="background:var(--tone-{tone});">{esc(f.get('status', 'New'))}</span>
                    {f'<span class="priority-badge" style="background:var(--tone-neutral);">{esc(f["category"])}</span>' if f.get('category') else ''}
                    {_fb_chips}
                    {f'<p>{esc(f.get("description"))}</p>' if f.get('description') else ''}
                    {f'<div class="feedback-response"><i class="fas fa-reply"></i> <b>{esc(f.get("responded_by"))}:</b> {esc(f.get("admin_response"))}</div>' if f.get('admin_response') else ''}
                </div>
                """, unsafe_allow_html=True)

                if can(role, "feedback.manage"):
                    with st.expander(f"⚙️ Manage #{fid}"):
                        _new_status = st.selectbox("Status", FEEDBACK_STATUSES,
                                                   index=FEEDBACK_STATUSES.index(f.get('status', 'New'))
                                                   if f.get('status') in FEEDBACK_STATUSES else 0,
                                                   key=f"fb_status_{fid}")
                        _response = st.text_area("Response (optional)",
                                                 value=f.get('admin_response') or '',
                                                 key=f"fb_resp_{fid}",
                                                 placeholder="e.g. 'Good idea — added to next sprint' "
                                                            "or 'Not planned because...'")
                        if st.button("💾 Save", key=f"fb_save_{fid}"):
                            if update_feedback_status(fid, _new_status, _response or None, full_name):
                                st.success("Updated.")
                                st.rerun()
                            else:
                                st.error("Save failed — check Row Level Security on app_feedback.")

    elif fb_sub == "Submit Suggestion":
        st.markdown("### Submit a New Suggestion")
        with st.form("new_feedback_form", clear_on_submit=True):
            fb_title = st.text_input("Title *", max_chars=150,
                                     placeholder="e.g. 'Add offline mode for underground areas'")
            fb_category = selectbox_with_other("Category", FEEDBACK_CATEGORIES,
                                               key_prefix="feedback_category")
            fb_description = st.text_area("Description",
                                          placeholder="What would this improve, and why does it matter to you?")
            fb_submitted = st.form_submit_button("💡 Submit Suggestion")
            if fb_submitted:
                ok, err, new_item = submit_feedback(fb_title, fb_description, fb_category, full_name)
                if ok:
                    st.success("Thanks — your suggestion has been posted.")
                    st.rerun()
                else:
                    st.error(err or "Failed to submit suggestion.")

# ---- ADMIN PANEL ----
elif selected_section == "Admin":
    if not can(role, "audit.view"):
        st.warning("You do not have admin privileges.")
    else:
        st.subheader("⚙️ Admin Panel")
        st.markdown("### Manage Users")
        all_users = fetch_all_users_from_db()
        if all_users:
            rows = ['<table class="user-table"><thead><tr>'
                   '<th>User</th><th>Role</th><th>Email</th><th>Status</th>'
                   '</tr></thead><tbody>']
            role_tone = {"superintendent": "danger", "supervisor": "warn", "worker": "info"}
            for u in all_users:
                r = str(u.get("role", "")).lower()
                tone = role_tone.get(r, "neutral")
                approved = u.get("is_approved", False)
                status_html = ('<span class="stock-badge stock-ok">Approved</span>' if approved
                               else '<span class="stock-badge stock-low">Pending</span>')
                rows.append(
                    '<tr><td>'
                    f'<div class="u-name">{esc(u.get("full_name"))}</div>'
                    f'<div class="u-mono">{esc(u.get("username"))}</div>'
                    '</td>'
                    f'<td><span class="priority-badge" style="background:var(--tone-{tone});">'
                    f'{esc(u.get("role"))}</span></td>'
                    f'<td class="u-mono">{esc(u.get("email") or "Not set")}</td>'
                    f'<td>{status_html}</td></tr>'
                )
            rows.append('</tbody></table>')
            st.markdown("".join(rows), unsafe_allow_html=True)
        else:
            st.info("No users found in database.")

        if SUPABASE_AVAILABLE:
            st.markdown("### 🔍 Audit Trail Viewer")
            try:
                # Fetches a bounded recent batch once (last 90 days, capped
                # at 1000 rows), then filters client-side — simpler than
                # building a dynamic Supabase query per filter combination,
                # and matches the quick_filter() pattern already used
                # throughout the rest of the app for this same kind of
                # "narrow down what's on screen" interaction.
                _audit_cutoff = (datetime.now() - timedelta(days=90)).isoformat()
                _audit_res = supabase.table("audit_log").select("*") \
                    .gte("created_at", _audit_cutoff) \
                    .order("created_at", desc=True).limit(1000).execute()
                _all_logs = _audit_res.data or []

                _acol1, _acol2, _acol3 = st.columns(3)
                with _acol1:
                    _audit_users = ["All Users"] + sorted(set(l.get("user_name") for l in _all_logs if l.get("user_name")))
                    _audit_user_filter = st.selectbox("Filter by user", _audit_users, key="audit_user_filter")
                with _acol2:
                    _audit_actions = ["All Actions"] + sorted(set(l.get("action") for l in _all_logs if l.get("action")))
                    _audit_action_filter = st.selectbox("Filter by action type", _audit_actions, key="audit_action_filter")
                with _acol3:
                    _audit_range = st.selectbox("Date range", ["Last 7 days", "Last 30 days", "Last 90 days"],
                                                index=1, key="audit_range_filter")

                _range_days = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}[_audit_range]
                _range_cutoff = datetime.now() - timedelta(days=_range_days)

                _filtered_logs = [
                    l for l in _all_logs
                    if (_audit_user_filter == "All Users" or l.get("user_name") == _audit_user_filter)
                    and (_audit_action_filter == "All Actions" or l.get("action") == _audit_action_filter)
                    and (_parse_dt(l.get("created_at")) or datetime.min) >= _range_cutoff
                ]

                st.caption(f"Showing {len(_filtered_logs)} of {len(_all_logs)} entries from the last 90 days.")
                if st.button("📥 Export Filtered as CSV", key="audit_export_csv") and _filtered_logs:
                    _audit_csv_rows = ["user_name,action,details,created_at"]
                    for l in _filtered_logs:
                        _d = (l.get("details") or "").replace('"', '""')
                        _audit_csv_rows.append(
                            f'"{l.get("user_name", "")}","{l.get("action", "")}","{_d}","{l.get("created_at", "")}"')
                    st.download_button("Download", "\n".join(_audit_csv_rows),
                                      f"audit_trail_{datetime.now().strftime('%Y%m%d')}.csv",
                                      "text/csv", key="audit_dl_csv")

                render_log_entries(_filtered_logs)
            except Exception as e:
                log_error(str(e), endpoint="audit_trail_viewer")
                st.info("Audit log unavailable.")
        else:
            st.info("Audit log not available (Supabase not connected).")

# ---- PROFILE TAB ----
elif selected_section == "Profile":
    st.subheader("👤 User Profile")
    st.markdown(render_meta_chips([
        ("fa-user", f"Username: {username}", "neutral"),
        ("fa-id-badge", f"Full name: {full_name}", "neutral"),
        ("fa-user-tag", f"Role: {user['role']}", "info"),
        ("fa-envelope", f"Email: {user_email}" if user_email else "Email: Not set", "neutral"),
    ]), unsafe_allow_html=True)

    st.markdown("### 🌐 Language")
    st.caption(
        "Translates navigation, common buttons, and headers. Most of the app's detailed "
        "content still shows in English for now — this is a genuine foundation, not a "
        "complete translation, and it's worth knowing that going in."
    )
    _lang_codes = list(SUPPORTED_LANGUAGES.keys())
    _lang_names = list(SUPPORTED_LANGUAGES.values())
    _current_lang = get_user_language()
    _new_lang_name = st.selectbox(
        "Preferred language", _lang_names,
        index=_lang_codes.index(_current_lang) if _current_lang in _lang_codes else 0,
        label_visibility="collapsed",
    )
    _new_lang_code = _lang_codes[_lang_names.index(_new_lang_name)]
    if _new_lang_code != _current_lang:
        set_user_language(_new_lang_code, username)
        st.rerun()

    st.markdown("### 🔔 Notifications")
    # Always broadcast the current username to the TOP-LEVEL window via
    # postMessage — harmless whether or not this is actually embedded
    # in the wrapper site's iframe (if accessed directly, window.top
    # is just window itself, so this only ever messages its own page).
    # window.top specifically, not window.parent: components.html()
    # renders this in its OWN nested iframe, so the actual structure is
    # wrapper page -> iframe -> Streamlit app -> another iframe (this
    # one) -> this code. window.parent from here only reaches the
    # Streamlit app's own window, one level up — never the wrapper
    # page two levels up. window.top always reaches the outermost
    # window regardless of how many iframe layers sit in between,
    # which is what actually gets this message where it needs to go.
    # This is what lets the WRAPPER SITE know who's logged in, since
    # it has no login of its own — the wrapper is what actually
    # registers the push subscription now, not this app directly. See
    # PUSH_NOTIFICATIONS_SETUP.md for why this moved.
    _uname_js = username.replace("'", "\\'")
    components.html(
        "<script>"
        f"try {{ window.top.postMessage({{type: 'mwdts-user', username: '{_uname_js}'}}, '*'); }} catch (e) {{}}"
        "</script>",
        height=0,
    )

    if not PUSH_CONFIGURED:
        st.caption("Not set up yet on this deployment — see PUSH_NOTIFICATIONS_SETUP.md.")
    else:
        st.info(
            "**Enable notifications from the app's install link, not from here.** "
            "Streamlit Community Cloud serves .js files in a way that a Service Worker "
            "can't register from — this isn't a setup mistake, it's a documented platform "
            "limitation. The install link (mwdts-app on GitHub Pages) doesn't have that "
            "restriction, so that's where the real toggle lives now. If you don't have "
            "that link, ask whoever manages the deployment."
        )

    uploaded_avatar = st.file_uploader("Upload Avatar", type=["jpg", "jpeg", "png", "gif", "webp"], key="avatar_upload")
    if uploaded_avatar is not None:
        if st.button("Update Avatar"):
            st.success("Avatar updated! (feature in development - will store to Supabase Storage)")
            st.session_state.user_payload['avatar_url'] = "https://via.placeholder.com/150"
            st.rerun()

    st.markdown("### Change Password")
    old_pass = st.text_input("Current Password", type="password")
    new_pass1 = st.text_input("New Password", type="password")
    new_pass2 = st.text_input("Confirm New Password", type="password")
    if st.button("Update Password"):
        if old_pass and new_pass1 and new_pass2:
            if new_pass1 == new_pass2:
                users = fetch_all_users_from_db()
                for u in users:
                    if u["username"] == username:
                        if verify_password(old_pass, u["password_hash"]):
                            new_hash = hash_password(new_pass1)
                            if update_user_profile(username, {"password_hash": new_hash}):
                                st.success("Password updated!")
                                st.rerun()
                            else:
                                st.error("Failed to update password.")
                        else:
                            st.error("Current password is incorrect.")
                        break
            else:
                st.error("New passwords do not match.")
        else:
            st.error("All fields are required.")

    st.markdown("### Update Email")
    new_email = st.text_input("New Email", value=user_email if user_email else "")
    if st.button("Update Email"):
        if new_email:
            if update_user_profile(username, {"email": new_email}):
                st.session_state.user_payload['email'] = new_email
                st.success("Email updated!")
                st.rerun()
            else:
                st.error("Failed to update email.")

# ---- ACTIVITY TIMELINE ----
elif selected_section == "About":
    st.subheader("ℹ️ About MWDTS")
    _about_tab1, _about_tab2 = st.tabs(["📋 App Policy Statement", "🧭 How the App Works"])

    with _about_tab1:
        st.caption(
            "This is a starting draft grounded in how the app actually works today — "
            "not a finished legal document. It's worth review by the Owner (and legal "
            "counsel, if the organization wants one) before being treated as official policy."
        )
        st.markdown("""
#### Purpose
MWDTS (Mine & Workshop Digital Tracker System) exists to replace paper-based
maintenance, safety, and incident tracking with a single digital system —
task management, permit-to-work / LOTO isolation records, hazard and
incident reporting, shift handover, and equipment/inventory tracking.

#### Accounts and access
- Each person uses their own individual account. Sharing login credentials
  defeats the purpose of the audit trail this system keeps, and should be
  treated as a policy violation, not a minor convenience.
- Access is role-based (Worker, Supervisor, Superintendent, Owner). What a
  role can see and do is enforced by the system itself, not left to
  individual discretion.
- New accounts require approval from a Supervisor or above before they can
  be used, unless an Owner has deliberately enabled auto-approval for this
  deployment.

#### What data this system holds
Task records, permits, incident and hazard reports, shift handovers,
contractor compliance records, asset and inventory data, internal chat
messages, and an audit trail of consequential actions (approvals, role
changes, deletions). This data is used for operational and safety
purposes — tracking work, investigating incidents, and demonstrating due
diligence — not for anything beyond that scope.

#### A safety-critical disclaimer worth stating plainly
**This system supports safety processes; it does not replace them.**
A Permit to Work or LOTO record existing in this app is not a substitute
for physically verifying isolation, following site safety procedures, or
using required PPE. Treat the app as a record-keeping and enforcement aid
alongside physical safety practice — never as a reason to skip a
verification step because "the system already shows it as done."

#### Expected use
Reports and records entered into this system are expected to be accurate
and timely. Deliberately false incident reports, task records, or permit
sign-offs undermine both safety and the audit trail this system exists to
provide.

#### Questions or concerns
Use the Feedback section for suggestions and non-urgent issues. For
anything safety-critical, follow the site's normal safety escalation
process — this app is a tool alongside that process, not a replacement
reporting channel for emergencies.
""")

    with _about_tab2:
        st.markdown("""
#### What this app actually is
A maintenance and safety tracking system for mine and workshop operations —
think of it as replacing several paper logbooks (task boards, incident
report books, permit-to-work logs, shift handover sheets) with one system
everyone uses from their phone or a computer.

#### Roles — what each one can do
""")
        st.markdown(render_field_grid([
            ("fa-user", "Worker",
            "Sees and updates their own assigned tasks, reports incidents, files shift "
            "handovers, uses chat, submits feedback.", "neutral"),
            ("fa-user-tie", "Supervisor",
            "Everything a Worker can do, plus assigning tasks, managing assets/inventory/"
            "permits/contractors, investigating incidents, viewing analytics.", "info"),
            ("fa-user-shield", "Superintendent",
            "Everything a Supervisor can do, plus approving or denying new accounts, "
            "managing existing accounts, and viewing the audit log.", "info"),
            ("fa-crown", "Owner",
            "A single designated account with exclusive access to company branding, "
            "the announcement ticker, feature toggles, and migration tools.", "ok"),
        ]), unsafe_allow_html=True)

        st.markdown("""
#### A quick tour of the main sections
- **Task Dashboard** — create, assign, and track maintenance work. Tasks
  requiring LOTO isolation are blocked from starting until an accepted
  permit exists for that task — a real safety gate, not just a checkbox.
- **Assets** — the equipment register, with meter readings feeding a
  forecast of when the next preventive maintenance is due.
- **Permits** — Permit to Work / LOTO records, with a full
  issue → accept → sign-back lifecycle.
- **Inventory** — spare parts stock levels, with low-stock flagging.
- **Incidents** — hazard, near-miss, and injury reporting, matching the
  site's own physical paper form.
- **Handover** — structured shift handover between outgoing and incoming
  supervisors.
- **Contractors** — third-party induction and insurance compliance
  tracking.
- **Analytics** — KPI dashboards: mean time to repair, PM compliance,
  planned-vs-reactive work, safety leading indicators.
- **Chat** — global, supervisor-only, and private messaging.
- **Feedback** — suggest changes or improvements to the app itself.
- **Timeline** — a running log of recent activity across all tasks.

#### If something seems wrong
Use Feedback for anything about the app itself — a confusing screen, a
feature that isn't working as expected, or an idea for something new.
""")


elif selected_section == "Wallboard":
    if WALLBOARD_MODULE_AVAILABLE:
        wallboard.render_wallboard()
    else:
        st.error("The Wallboard module file (wallboard.py) isn't present in this deployment — "
                "it needs to sit alongside app.py for this section to work.")

elif selected_section == "Crew Clock":
    if CREW_CLOCK_MODULE_AVAILABLE:
        crew_clock.render_crew_clock()
    else:
        st.error("The Crew Clock module file (crew_clock.py) isn't present in this deployment — "
                "it needs to sit alongside app.py for this section to work.")

elif selected_section == "JSA Library":
    if JSA_LIBRARY_MODULE_AVAILABLE:
        jsa_library.render_jsa_library()
    else:
        st.error("The JSA Library module file (jsa_library.py) isn't present in this deployment — "
                "it needs to sit alongside app.py for this section to work.")

elif selected_section == "Job Plans":
    if JOB_PLANS_MODULE_AVAILABLE:
        job_plans.render_job_plans()
    else:
        st.error("The Job Plans module file (job_plans.py) isn't present in this deployment — "
                "it needs to sit alongside app.py for this section to work.")

elif selected_section == "Locations":
    if LOCATION_HIERARCHY_MODULE_AVAILABLE:
        location_hierarchy.render_location_hierarchy()
    else:
        st.error("The Locations module file (location_hierarchy.py) isn't present in this deployment — "
                "it needs to sit alongside app.py for this section to work.")


elif selected_section == "Electrical Overview":
    st.subheader("⚡ Electrical Department Overview")
    st.caption("One landing page pulling status from all 7 Electrical Department sections, "
              "so you don't have to click through each one to know if anything needs attention.")

    _eo_any_alert = False

    # --- Active Outages (Outage Commander) ---
    _eo_outages = fetch_outage_events(active_only=True)
    if _eo_outages:
        _eo_any_alert = True
        st.error(f"🚧 **{len(_eo_outages)} active outage(s)** — "
                f"Commander: {', '.join(e['outage_commander'] for e in _eo_outages)}. "
                f"Go to Outage Commander.")

    # --- Pending Switching Authorizations (HV Switching Schedule) ---
    _eo_pending_switch = fetch_switching_orders(status="Draft")
    if _eo_pending_switch:
        _eo_any_alert = True
        st.warning(f"📝 **{len(_eo_pending_switch)} switching order(s) awaiting authorization** — "
                  f"Go to HV Switching Schedule.")

    # --- Overdue / Due-Soon Calibrations (Instrument Calibration) ---
    _eo_cal_overdue, _eo_cal_due_soon = [], []
    for c in fetch_instrument_calibrations():
        _, _, _eo_cal_status = instrument_calibration_status(c)
        if _eo_cal_status == "overdue":
            _eo_cal_overdue.append(c)
        elif _eo_cal_status == "due_soon":
            _eo_cal_due_soon.append(c)
    if _eo_cal_overdue:
        _eo_any_alert = True
        st.error(f"🔴 **{len(_eo_cal_overdue)} instrument(s) overdue for calibration** — "
                f"Go to Instrument Calibration.")
    if _eo_cal_due_soon:
        _eo_any_alert = True
        st.warning(f"📏 **{len(_eo_cal_due_soon)} instrument(s) due within 7 days** — "
                  f"Go to Instrument Calibration.")

    # --- Worst Transformer Condition (Transformer Health) ---
    _eo_dga_tests = fetch_dga_tests()
    _eo_transformer_tags = sorted(set(t["transformer_tag"] for t in _eo_dga_tests))
    _eo_worst_transformer = None
    for tag in _eo_transformer_tags:
        _latest = max((t for t in _eo_dga_tests if t["transformer_tag"] == tag), key=lambda t: t["test_date"])
        _worst, _worst_gases = worst_dga_condition(_latest)
        if _eo_worst_transformer is None or _worst > _eo_worst_transformer[1]:
            _eo_worst_transformer = (tag, _worst, _worst_gases)
    if _eo_worst_transformer and _eo_worst_transformer[1] >= 3:
        _eo_any_alert = True
        _eo_sev = "error" if _eo_worst_transformer[1] == 4 else "warning"
        getattr(st, _eo_sev)(f"⚡ **{esc(_eo_worst_transformer[0])} is at Condition {_eo_worst_transformer[1]}** "
                            f"(DGA) — Go to Transformer Health.")

    # --- Low-Stock Electrical Critical Spares ---
    _eo_low_stock = get_low_stock_electrical_parts(st.session_state.get("parts", []))
    if _eo_low_stock:
        _eo_any_alert = True
        st.warning(f"🔩 **{len(_eo_low_stock)} electrical critical spare(s) at or below reorder point** — "
                  f"Go to Inventory → Purchase Orders.")

    # --- Motor Rewind Bottlenecks ---
    _eo_rewinds = fetch_motor_rewinds()
    _eo_stage_counts = {}
    for r in _eo_rewinds:
        _eo_stage_counts[r["stage"]] = _eo_stage_counts.get(r["stage"], 0) + 1
    _eo_busiest = max(_eo_stage_counts, key=_eo_stage_counts.get) if _eo_stage_counts else None
    if _eo_busiest and _eo_stage_counts[_eo_busiest] >= 5:
        _eo_any_alert = True
        st.warning(f"🔧 **{_eo_stage_counts[_eo_busiest]} motors stuck in {_eo_busiest}** — "
                  f"Go to Motor Rewinds.")

    # --- Fault Recorder Trends ---
    _eo_fault_trends = get_fault_trends_by_feeder(fetch_fault_events(), top_n=1)
    if _eo_fault_trends and _eo_fault_trends[0]["total"] >= 5:
        _eo_any_alert = True
        st.warning(f"📊 **{esc(_eo_fault_trends[0]['feeder'])} has tripped {_eo_fault_trends[0]['total']} time(s)** — "
                  f"Go to Fault Recorder.")

    if not _eo_any_alert:
        st.success("✅ Nothing needs immediate attention across the Electrical Department right now.")

    st.markdown("---")
    st.markdown("#### At a Glance")
    _eo_col1, _eo_col2, _eo_col3, _eo_col4 = st.columns(4)
    _eo_col1.metric("Active Outages", len(_eo_outages))
    _eo_col2.metric("Pending Authorizations", len(_eo_pending_switch))
    _eo_col3.metric("Calibrations Due/Overdue", len(_eo_cal_overdue) + len(_eo_cal_due_soon))
    _eo_col4.metric("Low-Stock Spares", len(_eo_low_stock))


elif selected_section == "Motor Rewinds":
    st.subheader("🔧 Motor Rewind Board")
    st.caption("Tracks each motor through Stripping → Winding → Impregnating → Assembly → Testing → QC. "
              "Built to make a stuck stage visible at a glance — no more \"where did that motor go?\"")

    with st.expander("➕ Start a new rewind"):
        with st.form("new_motor_rewind_form", clear_on_submit=True):
            _mr_tag = st.text_input("Motor Tag / ID *", max_chars=100)
            _mr_desc = st.text_input("Description (optional)", max_chars=200,
                                     placeholder="e.g. 75kW conveyor drive motor, Plant 1")
            _mr_asset_options = ["None"] + [f"#{a['id']} {a['name']}" for a in st.session_state.get("assets", [])]
            _mr_asset_choice = st.selectbox("Linked Asset (optional)", _mr_asset_options)
            if st.form_submit_button("🔧 Start Rewind"):
                if not _mr_tag.strip():
                    st.error("Motor Tag / ID is required.")
                else:
                    _mr_asset_id = None
                    if _mr_asset_choice != "None":
                        _mr_asset_id = int(_mr_asset_choice.split(" ")[0].replace("#", ""))
                    if create_motor_rewind(_mr_tag.strip(), _mr_desc.strip() or None, full_name, asset_id=_mr_asset_id):
                        st.success(f"Rewind started for {_mr_tag}.")
                        st.rerun()
                    else:
                        st.error("Failed to start rewind — this is most likely Row Level Security "
                               "blocking the write on a new table. Run the RLS fix in "
                               "schema_additions.sql (Phase 32) against your Supabase database, then try again.")

    _rewinds = fetch_motor_rewinds()
    if not _rewinds:
        render_empty_state("fa-bolt", "No active rewinds",
                          "Start one above to begin tracking it through the board.")
    else:
        # Bottleneck warning — the actual stated value of this feature
        # ("bottlenecks become visible instantly") only holds if a
        # supervisor doesn't have to manually count cards per column
        # to notice one — flagged explicitly, not just left for someone
        # to eyeball across 6 columns.
        _stage_counts = {s: 0 for s in MOTOR_REWIND_STAGES}
        for r in _rewinds:
            if r["stage"] in _stage_counts:
                _stage_counts[r["stage"]] += 1
        _busiest_stage = max(_stage_counts, key=_stage_counts.get)
        if _stage_counts[_busiest_stage] >= 5:
            st.warning(f"⚠️ **Bottleneck**: {_stage_counts[_busiest_stage]} motors are stuck in "
                      f"**{_busiest_stage}** — worth checking what's holding that stage up.")

        _mr_cols = st.columns(len(MOTOR_REWIND_STAGES))
        for _i, _stage in enumerate(MOTOR_REWIND_STAGES):
            with _mr_cols[_i]:
                st.markdown(f"**{_stage}** ({_stage_counts[_stage]})")
                for r in [x for x in _rewinds if x["stage"] == _stage]:
                    _days_in_stage = (datetime.now() - (_parse_dt(r.get("stage_updated_at")) or datetime.now())).days
                    _stall_flag = " 🔴" if _days_in_stage >= 3 else ""
                    st.markdown(f"""
                    <div class="custom-card" style="padding: 0.6rem; margin-bottom: 0.5rem;">
                        <strong>{esc(r['motor_tag'])}</strong>{_stall_flag}
                        <p style="font-size: 0.8rem; margin: 0.2rem 0;">{esc(r.get('description') or '')}</p>
                        <p style="font-size: 0.75rem; color: var(--text-secondary); margin: 0;">
                            {_days_in_stage}d in stage
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
                    _bcol1, _bcol2 = st.columns(2)
                    with _bcol1:
                        if _i > 0 and st.button("◀", key=f"mr_back_{r['id']}", help="Move back a stage"):
                            if move_motor_rewind_stage(r["id"], -1, full_name):
                                st.rerun()
                    with _bcol2:
                        if _i == len(MOTOR_REWIND_STAGES) - 1:
                            # Completing from QC needs test values first —
                            # sets a pending flag rather than completing
                            # immediately, so the certificate form below
                            # can render before the job is actually marked
                            # done (same two-step pattern as Crew Clock's
                            # punch-out, and for the same reason: the
                            # confirm step needs data that isn't available
                            # until this exact moment).
                            if st.button("✅", key=f"mr_fwd_{r['id']}", help="Complete"):
                                st.session_state["_pending_motor_completion"] = r["id"]
                                st.rerun()
                        else:
                            if st.button("▶", key=f"mr_fwd_{r['id']}", help="Advance to next stage"):
                                if move_motor_rewind_stage(r["id"], 1, full_name):
                                    st.rerun()

                    if st.session_state.get("_pending_motor_completion") == r["id"]:
                        with st.form(f"mr_complete_form_{r['id']}"):
                            st.markdown(f"**Complete {esc(r['motor_tag'])} — Test Certificate**")
                            _t_noload = st.text_input("No-load Current", key=f"mr_noload_{r['id']}")
                            _t_resist = st.text_input("Resistance", key=f"mr_resist_{r['id']}")
                            _t_megger = st.text_input("Insulation Megger", key=f"mr_megger_{r['id']}")
                            _t_hipot = st.text_input("Hi-Pot Result", key=f"mr_hipot_{r['id']}")
                            _t_confirm, _t_cancel = st.columns(2)
                            with _t_confirm:
                                if st.form_submit_button("✅ Complete & Generate Certificate"):
                                    _test_values = {
                                        "test_no_load_current": _t_noload or None,
                                        "test_resistance": _t_resist or None,
                                        "test_insulation_megger": _t_megger or None,
                                        "test_hipot_result": _t_hipot or None,
                                        "tested_by": full_name,
                                    }
                                    if move_motor_rewind_stage(r["id"], 1, full_name, test_values=_test_values):
                                        st.session_state.pop("_pending_motor_completion", None)
                                        st.session_state["_last_completed_rewind"] = r["id"]
                                        st.success(f"{r['motor_tag']} completed.")
                                        st.rerun()
                                    else:
                                        st.error("Failed to complete — please try again.")
                            with _t_cancel:
                                if st.form_submit_button("Cancel"):
                                    st.session_state.pop("_pending_motor_completion", None)
                                    st.rerun()

    # Certificate download — shown once, right after completing a job,
    # not attached inline to every card in every column (which would
    # mean re-fetching/re-rendering a download button for every
    # completed motor on every page load, most of which nobody's
    # about to download again).
    if st.session_state.get("_last_completed_rewind"):
        _completed_id = st.session_state["_last_completed_rewind"]
        _all_rewinds_incl = fetch_motor_rewinds(include_completed=True)
        _completed_rewind = next((x for x in _all_rewinds_incl if x["id"] == _completed_id), None)
        if _completed_rewind:
            _cert_pdf = generate_motor_test_certificate(_completed_rewind)
            if _cert_pdf:
                st.download_button(
                    f"📄 Download Test Certificate — {_completed_rewind['motor_tag']}",
                    _cert_pdf, f"test_certificate_{_completed_rewind['motor_tag']}.pdf",
                    "application/pdf", key="dl_motor_cert")
        if st.button("Dismiss", key="dismiss_cert_download"):
            st.session_state.pop("_last_completed_rewind", None)
            st.rerun()


elif selected_section == "Instrument Calibration":
    st.subheader("📏 Instrument Calibration Tracker")
    st.caption("Pressure transmitters, level sensors, and weigh feeders — alerted 7 days before a "
              "calibration expires, so a plant shutdown from a false reading never comes as a surprise.")

    _cals = fetch_instrument_calibrations()
    _due_soon = []
    _overdue = []
    for c in _cals:
        _next_due, _days_until, _status = instrument_calibration_status(c)
        if _status == "overdue":
            _overdue.append((c, _next_due, _days_until))
        elif _status == "due_soon":
            _due_soon.append((c, _next_due, _days_until))

    if _overdue:
        st.error(f"🔴 **{len(_overdue)} instrument(s) overdue for calibration**: " +
                 ", ".join(c["instrument_tag"] for c, _, _ in _overdue))
    if _due_soon:
        st.warning(f"⚠️ **{len(_due_soon)} instrument(s) due within 7 days**: " +
                   ", ".join(f"{c['instrument_tag']} ({d}d)" for c, _, d in _due_soon))

    with st.expander("➕ Log a calibration"):
        with st.form("new_calibration_form", clear_on_submit=True):
            _ic_tag = st.text_input("Instrument Tag / ID *", max_chars=100)
            _ic_type = st.selectbox("Instrument Type", INSTRUMENT_TYPES)
            _ic_location = st.text_input("Location (optional)", max_chars=150)
            _ic_date = st.date_input("Last Calibrated Date", value=datetime.now().date())
            _ic_interval = st.number_input("Calibration Interval (days)", min_value=1, value=90, step=1)
            _ic_notes = st.text_area("Notes (optional)", max_chars=300)
            if st.form_submit_button("📏 Log Calibration"):
                if not _ic_tag.strip():
                    st.error("Instrument Tag / ID is required.")
                else:
                    if create_instrument_calibration(_ic_tag.strip(), _ic_type, _ic_location.strip() or None,
                                                     _ic_date, _ic_interval, full_name, notes=_ic_notes.strip() or None):
                        st.success(f"Calibration logged for {_ic_tag}.")
                        st.rerun()
                    else:
                        st.error("Failed to log calibration — this is most likely Row Level Security "
                                "blocking the write on a new table. Run the RLS fix in "
                                "schema_additions.sql (Phase 33) against your Supabase database, then try again.")

    if not _cals:
        render_empty_state("fa-gauge", "No instruments tracked yet",
                          "Log a calibration above to start tracking its due date.")
    else:
        st.markdown("##### All Tracked Instruments")
        for c in _cals:
            _next_due, _days_until, _status = instrument_calibration_status(c)
            _colour = {"overdue": "#dc2626", "due_soon": "#f59e0b", "ok": "#16a34a"}[_status]
            _status_text = {"overdue": f"OVERDUE by {abs(_days_until)}d" if _days_until is not None else "OVERDUE (unreadable date)",
                           "due_soon": f"Due in {_days_until}d", "ok": f"Due in {_days_until}d"}[_status]
            st.markdown(f"""
            <div class="custom-card" style="border-left-color: {_colour};">
                <strong>{esc(c['instrument_tag'])}</strong> — {esc(c['instrument_type'])}
                <span class="status-badge" style="background:{_colour};">{_status_text}</span>
                <p>{esc(c.get('location') or '')} — last calibrated {esc(str(c.get('last_calibrated_date', ''))[:10])},
                every {c.get('calibration_interval_days', 90)} days</p>
            </div>
            """, unsafe_allow_html=True)


elif selected_section == "Outage Commander":
    st.subheader("🚧 Emergency Response / Outage Commander")
    st.caption("Tracks progress through YOUR site's own pre-written response procedure — this app "
              "does not generate or suggest electrical engineering guidance. The steps below are "
              "exactly what your own team wrote when the runbook was created.")

    _active_outages = fetch_outage_events(active_only=True)

    if _active_outages:
        st.error(f"🔴 {len(_active_outages)} active outage(s) in progress.")
        for event in _active_outages:
            _templates_lookup = {t["id"]: t for t in fetch_outage_runbook_templates()}
            _template = _templates_lookup.get(event.get("template_id"))
            _steps = _template.get("steps", []) if _template else []

            st.markdown(f"""
            <div class="custom-card" style="border-left-color: #dc2626;">
                <strong>{esc(event.get('location') or 'Location not specified')}</strong>
                <span class="status-badge" style="background:#dc2626;">ACTIVE</span>
                <p>Outage Commander: <strong>{esc(event['outage_commander'])}</strong></p>
                <p>{esc(event.get('description') or '')}</p>
                <p style="font-size: 0.8rem; color: var(--text-secondary);">
                    Started {_fmt_log_time(event.get('started_at'))} by {esc(event.get('started_by', ''))}
                </p>
            </div>
            """, unsafe_allow_html=True)

            _current_idx = event.get("current_step_index", 0)
            if _current_idx < len(_steps):
                st.markdown(f"**Current step ({_current_idx + 1} of {len(_steps)}):** {esc(_steps[_current_idx])}")
                with st.form(f"advance_outage_{event['id']}"):
                    _step_notes = st.text_input("Notes on completing this step (optional)", key=f"step_notes_{event['id']}")
                    if st.form_submit_button("✅ Mark Step Complete & Advance"):
                        if advance_outage_step(event["id"], _steps[_current_idx], full_name, notes=_step_notes or None):
                            st.rerun()
                        else:
                            st.error("Failed to advance — please try again.")
            else:
                st.success("All runbook steps completed.")
                if st.button("🏁 Resolve Outage", key=f"resolve_{event['id']}", type="primary"):
                    if resolve_outage_event(event["id"], full_name):
                        st.success("Outage marked resolved.")
                        st.rerun()

            if event.get("step_log"):
                with st.expander(f"📋 Timeline ({len(event['step_log'])} step(s) logged)"):
                    for log_entry in event["step_log"]:
                        st.write(f"✓ {esc(log_entry['step_text'])} — "
                                f"{_fmt_log_time(log_entry['completed_at'])} by {esc(log_entry['completed_by'])}"
                                + (f" — _{esc(log_entry['notes'])}_" if log_entry.get("notes") else ""))
            st.markdown("---")

    st.markdown("#### Start a New Outage Response")
    _templates = fetch_outage_runbook_templates()
    if not _templates:
        st.warning("No runbook templates exist yet — create one below before starting a response.")
    else:
        with st.form("start_outage_form"):
            _oc_template_choice = st.selectbox("Runbook Template", [t["template_name"] for t in _templates])
            _oc_commander = st.text_input("Outage Commander *", value=full_name)
            _oc_location = st.text_input("Location / Affected Area")
            _oc_description = st.text_area("Description")
            if st.form_submit_button("🚧 Start Outage Response", type="primary"):
                if not _oc_commander.strip():
                    st.error("Outage Commander is required.")
                else:
                    _selected_template = next(t for t in _templates if t["template_name"] == _oc_template_choice)
                    if start_outage_event(_selected_template["id"], _oc_commander.strip(),
                                         _oc_description.strip() or None, _oc_location.strip() or None, full_name):
                        st.success("Outage response started.")
                        st.rerun()
                    else:
                        st.error("Failed to start — this is most likely Row Level Security blocking "
                                "the write. Run the RLS fix in schema_additions.sql (Phase 34).")

    with st.expander("➕ Create a Runbook Template"):
        st.caption("Write out YOUR site's own response steps, in order — these are what will "
                  "guide the response during a real outage, so write them the way your own "
                  "qualified team would actually want them followed.")
        with st.form("new_runbook_template_form", clear_on_submit=True):
            _rb_name = st.text_input("Template Name *", placeholder="e.g. Main Substation Outage Response")
            _rb_steps_raw = st.text_area("Steps (one per line, in order) *", height=200,
                                        placeholder="Notify Duty Engineer\nConfirm isolation points\nIsolate faulted section\n...")
            if st.form_submit_button("💾 Save Runbook Template"):
                _rb_steps = [s.strip() for s in _rb_steps_raw.split("\n") if s.strip()]
                if not _rb_name.strip():
                    st.error("Template Name is required.")
                elif not _rb_steps:
                    st.error("At least one step is required.")
                else:
                    if create_outage_runbook_template(_rb_name.strip(), _rb_steps, full_name):
                        st.success(f"Runbook '{_rb_name}' saved with {len(_rb_steps)} step(s).")
                        st.rerun()
                    else:
                        st.error("Failed to save template.")

    if _templates:
        st.markdown("#### Existing Templates")
        for t in _templates:
            with st.expander(f"📄 {t['template_name']} ({len(t.get('steps', []))} steps)"):
                for i, step in enumerate(t.get("steps", []), 1):
                    st.write(f"{i}. {esc(step)}")


elif selected_section == "Transformer Health":
    st.subheader("⚡ Transformer Health Dashboard")
    st.caption("Dissolved Gas Analysis (DGA) history and condition flags — builds a record over time "
              "of your most expensive asset. Flags below are a reference-table comparison, not a "
              "diagnosis; treat any Condition 3 or 4 flag as a signal to get a qualified engineer's read.")
    with st.expander("ℹ️ About the thresholds used here"):
        st.markdown(
            "Reference values are the \"Condition 1–4\" dissolved-gas table as published in guidance "
            "citing IEEE C57.104 (values per US Bureau of Reclamation FIST 3-31, *Transformer "
            "Diagnostics*). This is the older, simpler condition-level framework — the 2019 revision "
            "of C57.104 moved to a more complex statistical method using age- and equipment-type-"
            "specific norms, which this app does not implement. **A flagged reading means "
            "\"compare this against published guidance and get a qualified read\" — never a "
            "standalone diagnosis of what's wrong with the transformer.**"
        )

    _all_dga_tests = fetch_dga_tests()
    _transformer_tags = sorted(set(t["transformer_tag"] for t in _all_dga_tests))

    if _transformer_tags:
        st.markdown("#### Fleet Summary")
        _fleet_rows = []
        for tag in _transformer_tags:
            _latest = max((t for t in _all_dga_tests if t["transformer_tag"] == tag),
                         key=lambda t: t["test_date"])
            _worst, _worst_gases = worst_dga_condition(_latest)
            _fleet_rows.append((tag, _worst, _worst_gases, _latest["test_date"]))
        # Worst condition first — a supervisor scanning this list should
        # see the transformer needing attention most at the top, not
        # buried alphabetically among ones that are fine.
        _fleet_rows.sort(key=lambda r: r[1], reverse=True)
        for tag, worst, worst_gases, test_date in _fleet_rows:
            _colour = {0: "#94a3b8", 1: "#16a34a", 2: "#f59e0b", 3: "#ea580c", 4: "#dc2626"}[worst]
            _label = {0: "No data", 1: "Condition 1", 2: "Condition 2", 3: "Condition 3", 4: "Condition 4"}[worst]
            _gas_names = ", ".join(DGA_GAS_LABELS.get(g, g) for g in worst_gases)
            st.markdown(f"""
            <div class="custom-card" style="border-left-color: {_colour};">
                <strong>{esc(tag)}</strong>
                <span class="status-badge" style="background:{_colour};">{_label}</span>
                <p>Last tested {esc(str(test_date)[:10])}{f' — driven by {esc(_gas_names)}' if worst_gases else ''}</p>
            </div>
            """, unsafe_allow_html=True)

    with st.expander("➕ Log a DGA Test"):
        with st.form("new_dga_test_form", clear_on_submit=True):
            _dga_tag = st.text_input("Transformer Tag / ID *", max_chars=100)
            _dga_asset_options = ["None"] + [f"#{a['id']} {a['name']}" for a in st.session_state.get("assets", [])]
            _dga_asset_choice = st.selectbox("Linked Asset (optional)", _dga_asset_options)
            _dga_date = st.date_input("Test Date", value=datetime.now().date())
            _dga_lab = st.text_input("Lab Name (optional)")
            st.markdown("**Gas Readings (ppm) — leave blank if not tested**")
            _gcol1, _gcol2 = st.columns(2)
            _gas_inputs = {}
            _gas_keys = list(DGA_CONDITION_THRESHOLDS.keys())
            for i, gas_key in enumerate(_gas_keys):
                with (_gcol1 if i % 2 == 0 else _gcol2):
                    _val = st.number_input(DGA_GAS_LABELS[gas_key], min_value=0.0, value=0.0, step=1.0, key=f"dga_{gas_key}")
                    _gas_inputs[gas_key] = _val if _val > 0 else None
            _dga_moisture = st.number_input("Moisture (ppm, optional)", min_value=0.0, value=0.0, step=1.0)
            _dga_other_notes = st.text_area("Other Oil Test Results / Notes (optional)", max_chars=500)
            if st.form_submit_button("💾 Log DGA Test"):
                if not _dga_tag.strip():
                    st.error("Transformer Tag / ID is required.")
                else:
                    _dga_asset_id = None
                    if _dga_asset_choice != "None":
                        _dga_asset_id = int(_dga_asset_choice.split(" ")[0].replace("#", ""))
                    if create_dga_test(_dga_tag.strip(), _dga_date, _gas_inputs, full_name,
                                      asset_id=_dga_asset_id,
                                      moisture_ppm=_dga_moisture if _dga_moisture > 0 else None,
                                      other_oil_test_notes=_dga_other_notes.strip() or None,
                                      lab_name=_dga_lab.strip() or None):
                        st.success(f"DGA test logged for {_dga_tag}.")
                        st.rerun()
                    else:
                        st.error("Failed to log test — this is most likely Row Level Security "
                                "blocking the write. Run the RLS fix in schema_additions.sql "
                                "(Phase 35) against your Supabase database, then try again.")

    if _transformer_tags:
        st.markdown("#### Test History by Transformer")
        _dga_selected_tag = st.selectbox("Select transformer", _transformer_tags, key="dga_history_select")
        _tests_for_tag = sorted([t for t in _all_dga_tests if t["transformer_tag"] == _dga_selected_tag],
                                key=lambda t: t["test_date"], reverse=True)
        for test in _tests_for_tag:
            worst, _ = worst_dga_condition(test)
            _colour = {0: "#94a3b8", 1: "#16a34a", 2: "#f59e0b", 3: "#ea580c", 4: "#dc2626"}[worst]
            with st.expander(f"{str(test['test_date'])[:10]} — Condition {worst if worst else 'N/A'}"):
                for gas_key in DGA_CONDITION_THRESHOLDS:
                    val = test.get(gas_key)
                    condition, label = classify_dga_reading(gas_key, val)
                    if val is not None:
                        st.write(f"**{DGA_GAS_LABELS[gas_key]}**: {val} ppm — {label}")
                if test.get("moisture_ppm"):
                    st.write(f"**Moisture**: {test['moisture_ppm']} ppm")
                if test.get("other_oil_test_notes"):
                    st.write(f"**Notes**: {esc(test['other_oil_test_notes'])}")
                if test.get("lab_name"):
                    st.caption(f"Tested by {esc(test['lab_name'])}")


elif selected_section == "Fault Recorder":
    st.subheader("📊 Fault & Disturbance Recorder")
    st.caption("A structured log of trip/fault events — which feeder tripped, what protection "
              "device operated, the fault type and cause. Built for root cause analysis and "
              "spotting patterns, not for reading raw waveform data (COMTRADE files) — that "
              "level of signal analysis needs your fault recorder's own dedicated software.")

    _fault_events = fetch_fault_events()

    if _fault_events:
        st.markdown("#### Trends by Feeder")
        st.caption("Sorted worst-first — a feeder tripping repeatedly on the SAME fault type "
                  "points to something specific and fixable; a mix of unrelated fault types "
                  "at the same total count tells a different story.")
        _trends = get_fault_trends_by_feeder(_fault_events)
        for t in _trends:
            _type_breakdown = ", ".join(f"{v} {k}" for k, v in sorted(t["by_type"].items(), key=lambda x: -x[1]))
            st.markdown(f"""
            <div class="custom-card" style="border-left-color: {'#dc2626' if t['total'] >= 5 else '#0f3460'};">
                <strong>{esc(t['feeder'])}</strong>
                <span class="status-badge" style="background:{'#dc2626' if t['total'] >= 5 else '#0f3460'};">{t['total']} trip(s)</span>
                <p>{esc(_type_breakdown)}</p>
            </div>
            """, unsafe_allow_html=True)

    with st.expander("➕ Log a Fault Event"):
        with st.form("new_fault_event_form", clear_on_submit=True):
            _fe_date = st.date_input("Event Date", value=datetime.now().date())
            _fe_time = st.time_input("Event Time", value=datetime.now().time())
            _fe_feeder = st.text_input("Feeder / Circuit *", placeholder="e.g. Feeder 3, 132kV Bus A")
            _fe_device = st.text_input("Protection Device That Operated", placeholder="e.g. Relay R1, CB-05")
            _fe_type = selectbox_with_other("Fault Type", FAULT_TYPES, key_prefix="fault_type")
            _fe_cause = st.text_input("Apparent Cause", placeholder="e.g. Vegetation contact, insulator failure")
            _fe_notes = st.text_area("Notes (optional)", max_chars=500)
            if st.form_submit_button("💾 Log Fault Event"):
                if not _fe_feeder.strip():
                    st.error("Feeder / Circuit is required.")
                else:
                    _fe_datetime = datetime.combine(_fe_date, _fe_time)
                    if create_fault_event(_fe_datetime, _fe_feeder.strip(), _fe_device.strip() or None,
                                         _fe_type, _fe_cause.strip() or None, full_name,
                                         notes=_fe_notes.strip() or None):
                        st.success("Fault event logged.")
                        st.rerun()
                    else:
                        st.error("Failed to log event — this is most likely Row Level Security "
                                "blocking the write. Run the RLS fix in schema_additions.sql "
                                "(Phase 37) against your Supabase database, then try again.")

    if not _fault_events:
        render_empty_state("fa-bolt", "No fault events logged yet",
                          "Log one above to start building your trip history.")
    else:
        st.markdown("#### Event History")
        _fe_search = st.text_input("🔍 Search by feeder, device, or cause", key="fault_event_search")
        _filtered_events = quick_filter(_fault_events, _fe_search, ["feeder", "protection_device", "cause"])
        for e in _filtered_events:
            with st.expander(f"{esc(e['feeder'])} — {esc(e.get('fault_type') or 'Unspecified')} — "
                            f"{_fmt_log_time(e.get('event_datetime'))}"):
                st.write(f"**Protection Device**: {esc(e.get('protection_device') or 'Not recorded')}")
                st.write(f"**Cause**: {esc(e.get('cause') or 'Not recorded')}")
                if e.get("notes"):
                    st.write(f"**Notes**: {esc(e['notes'])}")
                st.caption(f"Logged by {esc(e.get('created_by', ''))}")


elif selected_section == "HV Switching Schedule":
    st.subheader("🔀 HV Switching Schedule")
    st.caption("Scheduled switching operations, each requiring a named person's sign-off before any "
              "step can be executed. Same principle as Outage Commander: this app tracks progress "
              "through YOUR team's own switching order — it never authors or suggests the switching "
              "sequence itself.")

    _switching_orders = fetch_switching_orders()
    _draft_orders = [o for o in _switching_orders if o["status"] == "Draft"]
    _active_orders = [o for o in _switching_orders if o["status"] in ("Authorized", "In Progress")]
    _completed_orders = [o for o in _switching_orders if o["status"] == "Completed"]

    if _draft_orders:
        st.warning(f"📝 {len(_draft_orders)} switching order(s) awaiting authorization.")

    if _active_orders:
        st.markdown("#### Active Switching Orders")
        for order in _active_orders:
            _steps = order.get("steps", [])
            _cur_idx = order.get("current_step_index", 0)
            st.markdown(f"""
            <div class="custom-card" style="border-left-color: #f59e0b;">
                <strong>{esc(order['title'])}</strong>
                <span class="status-badge" style="background:#f59e0b;">{esc(order['status'])}</span>
                <p>{esc(order['feeder_circuit'])} — Scheduled {_fmt_log_time(order['scheduled_datetime'])}</p>
                <p>Authorized by <strong>{esc(order.get('authorized_by', ''))}</strong> at {_fmt_log_time(order.get('authorized_at'))}</p>
            </div>
            """, unsafe_allow_html=True)
            if _cur_idx < len(_steps):
                st.markdown(f"**Current step ({_cur_idx + 1} of {len(_steps)}):** {esc(_steps[_cur_idx])}")
                with st.form(f"advance_switch_{order['id']}"):
                    _sw_notes = st.text_input("Notes (optional)", key=f"sw_notes_{order['id']}")
                    if st.form_submit_button("✅ Mark Step Complete & Advance"):
                        if advance_switching_step(order["id"], _steps[_cur_idx], full_name, notes=_sw_notes or None):
                            st.rerun()
                        else:
                            st.error("Failed to advance — this order may not be authorized. Refresh and try again.")
            if order.get("step_log"):
                with st.expander(f"📋 Execution log ({len(order['step_log'])} step(s))"):
                    for log_entry in order["step_log"]:
                        st.write(f"✓ {esc(log_entry['step_text'])} — {_fmt_log_time(log_entry['completed_at'])} "
                                f"by {esc(log_entry['completed_by'])}"
                                + (f" — _{esc(log_entry['notes'])}_" if log_entry.get("notes") else ""))
            st.markdown("---")

    if _draft_orders:
        st.markdown("#### Awaiting Authorization")
        for order in _draft_orders:
            st.markdown(f"""
            <div class="custom-card" style="border-left-color: #94a3b8;">
                <strong>{esc(order['title'])}</strong>
                <span class="status-badge" style="background:#94a3b8;">DRAFT</span>
                <p>{esc(order['feeder_circuit'])} — Scheduled {_fmt_log_time(order['scheduled_datetime'])}</p>
                <p>{len(order.get('steps', []))} step(s) — created by {esc(order.get('created_by', ''))}</p>
                <p>Awaiting authorization from: <strong>{esc(order.get('designated_approver') or 'Not set')}</strong></p>
            </div>
            """, unsafe_allow_html=True)
            with st.expander("Review steps before authorizing"):
                for i, step in enumerate(order.get("steps", []), 1):
                    st.write(f"{i}. {esc(step)}")
            # Identity-based, not a free-text name field — the person
            # actually logged in must BE the designated approver.
            # A typed name proves nothing about who's really clicking
            # the button; the logged-in session does.
            _is_designated_approver = (order.get("designated_approver") or "").strip().lower() == full_name.strip().lower()
            if _is_designated_approver:
                if st.button(f"✅ Authorize as {full_name}", key=f"authorize_btn_{order['id']}", type="primary"):
                    if authorize_switching_order(order["id"], full_name):
                        st.success("Order authorized — steps can now be executed.")
                        st.rerun()
                    else:
                        st.error("Failed to authorize — please refresh and try again.")
            else:
                st.caption(f"🔒 Only {esc(order.get('designated_approver') or 'the designated approver')} "
                          "can authorize this order — they'll need to log in and do this themselves.")

    with st.expander("➕ Create a New Switching Order"):
        st.caption("Write your team's own switching sequence, in order — this becomes the exact "
                  "steps that get tracked and executed once authorized.")
        with st.form("new_switching_order_form", clear_on_submit=True):
            _sw_title = st.text_input("Title *", placeholder="e.g. Feeder 3 Bay Isolation for Maintenance")
            _sw_feeder = st.text_input("Feeder / Circuit *")
            _sw_date = st.date_input("Scheduled Date")
            _sw_time = st.time_input("Scheduled Time")
            _sw_officer = st.text_input("Switching Officer (optional)")
            _sw_approver = st.text_input("Designated Approver *",
                                        help="Must be a different person from you — they'll need to "
                                             "log in themselves and authorize this before any step can be executed.")
            _sw_steps_raw = st.text_area("Switching Steps (one per line, in order) *", height=200,
                                        placeholder="Confirm isolation points\nOpen CB-05\nApply earths at...\n...")
            if st.form_submit_button("💾 Save as Draft"):
                _sw_steps = [s.strip() for s in _sw_steps_raw.split("\n") if s.strip()]
                if not _sw_title.strip() or not _sw_feeder.strip():
                    st.error("Title and Feeder / Circuit are required.")
                elif not _sw_steps:
                    st.error("At least one switching step is required.")
                elif not _sw_approver.strip():
                    st.error("Designated Approver is required.")
                elif _sw_approver.strip().lower() == full_name.strip().lower():
                    st.error("The Designated Approver must be a different person from you — "
                            "self-authorization isn't permitted for switching orders.")
                else:
                    _sw_datetime = datetime.combine(_sw_date, _sw_time)
                    if create_switching_order(_sw_title.strip(), _sw_feeder.strip(), _sw_datetime, _sw_steps,
                                             full_name, _sw_approver.strip(),
                                             switching_officer=_sw_officer.strip() or None):
                        st.success("Switching order saved as Draft — awaiting authorization "
                                  f"from {_sw_approver.strip()}.")
                        st.rerun()
                    else:
                        st.error("Failed to save — this is most likely Row Level Security blocking "
                                "the write, or the schema is missing the designated_approver column "
                                "(Phase 39). Run schema_additions.sql against your Supabase database, "
                                "then try again.")

    if _completed_orders:
        st.markdown("#### Completed Switching Orders")
        for order in _completed_orders:
            with st.expander(f"{esc(order['title'])} — completed {_fmt_log_time(order.get('completed_at'))}"):
                st.write(f"**Feeder/Circuit**: {esc(order['feeder_circuit'])}")
                st.write(f"**Authorized by**: {esc(order.get('authorized_by', ''))}")
                for log_entry in order.get("step_log", []):
                    st.write(f"✓ {esc(log_entry['step_text'])} — {_fmt_log_time(log_entry['completed_at'])} "
                            f"by {esc(log_entry['completed_by'])}")


elif selected_section == "Relay Settings":
    st.subheader("🎛️ Relay Settings Database")
    st.caption("A searchable record of what's configured on each protection relay, plus as-found/"
              "as-left comparison during testing to catch unintended changes. This is tracking and "
              "mechanical comparison only — whether a difference actually matters, and any "
              "coordination judgment, is for your own qualified team to decide.")

    _relay_tags = sorted(set(r["relay_tag"] for r in fetch_relay_setting_records()))

    with st.expander("➕ Record Relay Settings"):
        st.caption("Add parameters as needed — relay parameter sets vary by manufacturer and "
                  "function, so this isn't a fixed form. Add a row per setting you're recording.")
        if "_relay_param_rows" not in st.session_state:
            st.session_state["_relay_param_rows"] = 1
        _rcol1, _rcol2 = st.columns(2)
        with _rcol1:
            if st.button("➕ Add another parameter row"):
                st.session_state["_relay_param_rows"] += 1
                st.rerun()
        with _rcol2:
            if st.session_state["_relay_param_rows"] > 1 and st.button("➖ Remove last row"):
                st.session_state["_relay_param_rows"] -= 1
                st.rerun()

        with st.form("new_relay_record_form", clear_on_submit=True):
            _rel_tag = st.text_input("Relay Tag / ID *", placeholder="e.g. R1, Feeder 3 Overcurrent Relay")
            _rel_feeder = st.text_input("Feeder / Circuit")
            _rel_model = st.text_input("Relay Model / Manufacturer")
            _rel_record_type = st.selectbox("Record Type", RELAY_RECORD_TYPES)
            _rel_date = st.date_input("Test/Record Date", value=datetime.now().date())
            st.markdown("**Settings**")
            _rel_params = {}
            for i in range(st.session_state["_relay_param_rows"]):
                _pcol1, _pcol2 = st.columns(2)
                with _pcol1:
                    _pname = st.text_input(f"Parameter {i+1}", key=f"relay_param_name_{i}",
                                          placeholder="e.g. Pickup Current")
                with _pcol2:
                    _pval = st.text_input(f"Value {i+1}", key=f"relay_param_val_{i}", placeholder="e.g. 400A")
                if _pname.strip():
                    _rel_params[_pname.strip()] = _pval.strip()
            _rel_notes = st.text_area("Notes (optional)", max_chars=500)
            if st.form_submit_button("💾 Save Relay Settings Record"):
                if not _rel_tag.strip():
                    st.error("Relay Tag / ID is required.")
                elif not _rel_params:
                    st.error("At least one parameter is required.")
                else:
                    if create_relay_setting_record(_rel_tag.strip(), _rel_feeder.strip() or None,
                                                   _rel_model.strip() or None, _rel_record_type,
                                                   _rel_params, _rel_date, full_name,
                                                   notes=_rel_notes.strip() or None):
                        st.success(f"Settings recorded for {_rel_tag}.")
                        st.rerun()
                    else:
                        st.error("Failed to save — this is most likely Row Level Security "
                                "blocking the write. Run the RLS fix in schema_additions.sql "
                                "(Phase 40) against your Supabase database, then try again.")

    if not _relay_tags:
        render_empty_state("fa-sliders", "No relay settings recorded yet",
                          "Add a record above to start building your relay settings history.")
    else:
        st.markdown("#### Relay History & As-Found/As-Left Comparison")
        _selected_relay = st.selectbox("Select relay", _relay_tags, key="relay_select")
        _relay_records = sorted(fetch_relay_setting_records(relay_tag=_selected_relay),
                                key=lambda r: r["test_date"], reverse=True)

        _as_found_records = [r for r in _relay_records if r["record_type"] == "As-Found"]
        _as_left_records = [r for r in _relay_records if r["record_type"] == "As-Left"]
        if _as_found_records and _as_left_records:
            st.markdown("##### Latest As-Found vs As-Left Comparison")
            _comparison = compare_relay_settings(_as_found_records[0], _as_left_records[0])
            _changed_count = sum(1 for c in _comparison if c["changed"])
            if _changed_count:
                st.warning(f"⚠️ {_changed_count} parameter(s) differ between As-Found and As-Left.")
            else:
                st.success("No differences between As-Found and As-Left.")
            for c in _comparison:
                _row_colour = "#dc2626" if c["changed"] else "#16a34a"
                st.markdown(f"""
                <div class="custom-card" style="border-left-color: {_row_colour}; padding: 0.6rem;">
                    <strong>{esc(c['parameter'])}</strong>
                    <p style="margin: 0.2rem 0; font-size: 0.85rem;">
                        As-Found: {esc(str(c['as_found_value']))} → As-Left: {esc(str(c['as_left_value']))}
                    </p>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("##### Full Record History")
        for r in _relay_records:
            with st.expander(f"{r['record_type']} — {str(r['test_date'])[:10]} by {esc(r['tested_by'])}"):
                for param, val in r.get("settings", {}).items():
                    st.write(f"**{esc(param)}**: {esc(str(val))}")
                if r.get("notes"):
                    st.write(f"**Notes**: {esc(r['notes'])}")


elif selected_section == "Arc Flash Studies":
    st.subheader("⚠️ Arc Flash Study / Label Currency Tracking")
    st.caption("Tracks when each panel's arc flash study was last done, and flags when a review "
              "is due. Incident energy, PPE category, and boundary values are recorded exactly as "
              "your engineer/firm reported them — this app doesn't calculate these itself.")
    with st.expander("ℹ️ About the 5-year default"):
        st.markdown(
            "NFPA 70E Article 130.5 requires the data supporting an arc flash label to be "
            "reviewed for accuracy at intervals **not to exceed 5 years** — that's the "
            "regulatory maximum used as the default below, not a recommended cadence. "
            "**The standard also requires immediate review after any major system modification** "
            "(new equipment, transformer or breaker changes, utility fault current changes) "
            "regardless of where you are in the 5-year cycle — this app has no way to know when "
            "such a change happened, so acting on that trigger is on your own team, not something "
            "this page can flag for you."
        )

    _af_studies = fetch_arc_flash_studies()
    _af_overdue = [s for s in _af_studies if arc_flash_study_status(s)[2] == "overdue"]
    _af_due_soon = [s for s in _af_studies if arc_flash_study_status(s)[2] == "due_soon"]
    if _af_overdue:
        st.error(f"🔴 **{len(_af_overdue)} panel(s) overdue for arc flash study review**: " +
                 ", ".join(s["equipment_tag"] for s in _af_overdue))
    if _af_due_soon:
        st.warning(f"⚠️ **{len(_af_due_soon)} panel(s) due for review within 90 days**: " +
                   ", ".join(s["equipment_tag"] for s in _af_due_soon))

    with st.expander("➕ Log an Arc Flash Study"):
        with st.form("new_arc_flash_form", clear_on_submit=True):
            _af_tag = st.text_input("Equipment Tag / Panel ID *", max_chars=100)
            _af_location = st.text_input("Location")
            _af_asset_options = ["None"] + [f"#{a['id']} {a['name']}" for a in st.session_state.get("assets", [])]
            _af_asset_choice = st.selectbox("Linked Asset (optional)", _af_asset_options)
            _af_date = st.date_input("Study Date", value=datetime.now().date())
            _af_energy = st.text_input("Incident Energy (cal/cm²)", placeholder="e.g. 8.2")
            _af_ppe = st.text_input("PPE Category", placeholder="e.g. Category 2")
            _af_boundary = st.text_input("Arc Flash Boundary", placeholder="e.g. 1.2 m")
            _af_engineer = st.text_input("Performed By (engineer/firm)")
            _af_notes = st.text_area("Notes (optional)", max_chars=500)
            if st.form_submit_button("💾 Save Arc Flash Study"):
                if not _af_tag.strip():
                    st.error("Equipment Tag / Panel ID is required.")
                else:
                    _af_asset_id = None
                    if _af_asset_choice != "None":
                        _af_asset_id = int(_af_asset_choice.split(" ")[0].replace("#", ""))
                    if create_arc_flash_study(_af_tag.strip(), _af_location.strip() or None, _af_date,
                                             _af_engineer.strip() or None, full_name, asset_id=_af_asset_id,
                                             incident_energy=_af_energy.strip() or None,
                                             ppe_category=_af_ppe.strip() or None,
                                             arc_flash_boundary=_af_boundary.strip() or None,
                                             notes=_af_notes.strip() or None):
                        st.success(f"Arc flash study logged for {_af_tag}.")
                        st.rerun()
                    else:
                        st.error("Failed to save — this is most likely Row Level Security "
                                "blocking the write. Run the RLS fix in schema_additions.sql "
                                "(Phase 41) against your Supabase database, then try again.")

    if not _af_studies:
        render_empty_state("fa-triangle-exclamation", "No arc flash studies recorded yet",
                          "Log one above to start tracking review dates.")
    else:
        st.markdown("#### All Tracked Panels")
        for s in sorted(_af_studies, key=lambda s: s["study_date"], reverse=True):
            _next_review, _days_until, _status = arc_flash_study_status(s)
            _colour = {"overdue": "#dc2626", "due_soon": "#f59e0b", "ok": "#16a34a"}[_status]
            with st.expander(f"{esc(s['equipment_tag'])} — {_status.replace('_', ' ').title()}"):
                st.markdown(f"""
                <div class="custom-card" style="border-left-color: {_colour}; padding: 0.6rem;">
                    <p>Studied {str(s['study_date'])[:10]} — next review due {_next_review}</p>
                </div>
                """, unsafe_allow_html=True)
                if s.get("incident_energy_cal_cm2"):
                    st.write(f"**Incident Energy**: {esc(s['incident_energy_cal_cm2'])} cal/cm²")
                if s.get("ppe_category"):
                    st.write(f"**PPE Category**: {esc(s['ppe_category'])}")
                if s.get("arc_flash_boundary"):
                    st.write(f"**Arc Flash Boundary**: {esc(s['arc_flash_boundary'])}")
                if s.get("performed_by"):
                    st.write(f"**Performed By**: {esc(s['performed_by'])}")
                if s.get("notes"):
                    st.write(f"**Notes**: {esc(s['notes'])}")


elif selected_section == "Technician Certifications":
    st.subheader("🎓 Technician Competency & Certification Tracking")
    st.caption("Who's currently qualified for HV switching, arc flash work, and other electrical "
              "safety-critical tasks — with expiry alerts, same pattern already used for contractor "
              "compliance, extended to your own in-house team.")

    _tc_all = fetch_technician_certifications()
    _tc_overdue, _tc_due_soon = [], []
    for c in _tc_all:
        _, _tc_status = technician_certification_status(c)
        if _tc_status == "overdue":
            _tc_overdue.append(c)
        elif _tc_status == "due_soon":
            _tc_due_soon.append(c)
    if _tc_overdue:
        st.error(f"🔴 **{len(_tc_overdue)} certification(s) expired**: " +
                 ", ".join(f"{c['technician_name']} ({c['certification_type']})" for c in _tc_overdue))
    if _tc_due_soon:
        st.warning(f"⚠️ **{len(_tc_due_soon)} certification(s) expiring within 30 days**: " +
                   ", ".join(f"{c['technician_name']} ({c['certification_type']})" for c in _tc_due_soon))

    with st.expander("➕ Log a Certification"):
        with st.form("new_tech_cert_form", clear_on_submit=True):
            _tc_name = st.text_input("Technician Name *", max_chars=100)
            _tc_type = selectbox_with_other("Certification Type", CERTIFICATION_TYPES, key_prefix="tech_cert_type")
            _tc_issued = st.date_input("Issued Date", value=datetime.now().date())
            _tc_has_expiry = st.checkbox("Has an expiry date", value=True)
            _tc_expiry = st.date_input("Expiry Date", value=datetime.now().date(), disabled=not _tc_has_expiry) if _tc_has_expiry else None
            _tc_body = st.text_input("Issuing Body (optional)")
            _tc_cert_num = st.text_input("Certificate Number (optional)")
            _tc_notes = st.text_area("Notes (optional)", max_chars=500)
            if st.form_submit_button("💾 Save Certification"):
                if not _tc_name.strip():
                    st.error("Technician Name is required.")
                else:
                    if create_technician_certification(_tc_name.strip(), _tc_type, _tc_issued, full_name,
                                                        expiry_date=_tc_expiry, issuing_body=_tc_body.strip() or None,
                                                        certificate_number=_tc_cert_num.strip() or None,
                                                        notes=_tc_notes.strip() or None):
                        st.success(f"Certification logged for {_tc_name}.")
                        st.rerun()
                    else:
                        st.error("Failed to save — this is most likely Row Level Security "
                                "blocking the write. Run the RLS fix in schema_additions.sql "
                                "(Phase 42) against your Supabase database, then try again.")

    if not _tc_all:
        render_empty_state("fa-award", "No certifications recorded yet",
                          "Log one above to start tracking who's qualified for what.")
    else:
        st.markdown("#### All Technicians")
        _tc_names = sorted(set(c["technician_name"] for c in _tc_all))
        _tc_search = st.text_input("🔍 Search by technician name", key="tech_cert_search")
        _tc_filtered_names = [n for n in _tc_names if _tc_search.lower() in n.lower()] if _tc_search else _tc_names
        for name in _tc_filtered_names:
            with st.expander(name):
                for c in [c for c in _tc_all if c["technician_name"] == name]:
                    _days_until, _status = technician_certification_status(c)
                    _colour = {"overdue": "#dc2626", "due_soon": "#f59e0b", "ok": "#16a34a", "no_expiry": "#94a3b8"}[_status]
                    _status_text = {"overdue": "EXPIRED", "due_soon": f"Expires in {_days_until}d",
                                   "ok": f"Valid ({_days_until}d remaining)", "no_expiry": "No expiry date set"}[_status]
                    st.markdown(f"""
                    <div class="custom-card" style="border-left-color: {_colour}; padding: 0.6rem;">
                        <strong>{esc(c['certification_type'])}</strong>
                        <span class="status-badge" style="background:{_colour};">{_status_text}</span>
                        <p>Issued {str(c['issued_date'])[:10]}
                        {f" — Expires {str(c['expiry_date'])[:10]}" if c.get('expiry_date') else ''}</p>
                    </div>
                    """, unsafe_allow_html=True)


elif selected_section == "Help":
    st.subheader("❓ Help / How It Works")
    st.caption("A plain-language guide to what each feature does and how to use it.")
    if AI_FEATURES_AVAILABLE:
        st.info("💬 Prefer to ask in your own words? The **🤖 Assistant** room in Chat can answer "
               "'how do I...' questions conversationally, using this same guide.")

    _help_search = st.text_input("🔍 Search for a feature", key="help_search",
                                 placeholder="e.g. permit, motor rewind, calibration")

    for category, features in HOW_IT_WORKS_GUIDE.items():
        _matching_features = {
            name: desc for name, desc in features.items()
            if not _help_search or _help_search.lower() in name.lower() or _help_search.lower() in desc.lower()
        }
        if not _matching_features:
            continue
        st.markdown(f"#### {category}")
        for name, desc in _matching_features.items():
            with st.expander(name):
                st.write(desc)

    if _help_search and not any(
        _help_search.lower() in name.lower() or _help_search.lower() in desc.lower()
        for features in HOW_IT_WORKS_GUIDE.values() for name, desc in features.items()
    ):
        st.info(f"No matches for \"{_help_search}\" — try a different term, or check Feedback "
               "if you think something's missing from this guide.")


elif selected_section == "Timeline":
    st.subheader("⏱️ Activity Timeline")
    st.markdown("Recent actions across all tasks (last 50)")

    if SUPABASE_AVAILABLE:
        try:
            activities = supabase.table("task_activity").select("*").order("created_at", desc=True).limit(50).execute()
            if activities.data:
                # Resolve each row's task_id to a title. Deduped via
                # _task_titles so a task with many log entries only
                # gets looked up once, not once per row — a small
                # improvement over the original one-query-per-row
                # version, not just a rendering change.
                _task_titles = {}
                for act in activities.data:
                    tid = act.get('task_id')
                    if tid not in _task_titles:
                        task = supabase.table("tasks").select("title").eq("id", tid).execute()
                        _task_titles[tid] = task.data[0]['title'] if task.data else f"Task #{tid}"

                def _activity_phrase(act):
                    verb = str(act.get('action', '')).replace('_', ' ')
                    return f"{verb} {_task_titles.get(act.get('task_id'), '')}"

                render_log_entries(activities.data, action_verb=_activity_phrase)
            else:
                st.info("No activity logs yet.")
        except Exception:
            st.info("Activity log unavailable.")
    else:
        st.info("Activity log not available (Supabase not connected).")

# Footer
st.markdown("""
<div class="footer">
    <i class="fas fa-hard-hat"></i> Mine & Workshop Digital Tracker v3.0 — CMMS Edition &nbsp;|&nbsp; Asset Register · Inventory · Incident Reporting · KPI Analytics &nbsp;|&nbsp; Powered by Streamlit & Supabase
</div>
""", unsafe_allow_html=True)
