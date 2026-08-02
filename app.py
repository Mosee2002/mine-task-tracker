import streamlit as st
import requests
from datetime import datetime, timedelta
import hashlib
import base64
import os
import json
import time
import html as html_lib
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

# Theme toggle
if 'dark_mode' not in st.session_state:
    st.session_state.dark_mode = False

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

/* ---------- Header ---------- */
.main-header {
    background: linear-gradient(135deg, var(--brand-navy) 0%, #051d3f 55%, var(--brand-navy) 100%);
    color: #ffffff;
    padding: 1.25rem 1.6rem;
    border-radius: 14px;
    margin-bottom: 1.1rem;
    box-shadow: var(--shadow-md);
    font-size: 1.75rem;      /* was 2.5rem, which clipped its own text */
    font-weight: 800;
    line-height: 1.25;       /* the actual cause of the clipped title */
    letter-spacing: -0.01em;
    border-bottom: 3px solid var(--brand-lime);
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
    border-radius: 12px;
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
    clip-path: polygon(25% 4%, 75% 4%, 100% 50%, 75% 96%, 25% 96%, 0% 50%);
    background: var(--stat-bg, var(--accent-soft));
    color: var(--stat-color, var(--accent));
    font-size: 1rem;
}
.stat-body { min-width: 0; }
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
    "<style>" + _inline_css(_tokens, _CSS_BODY) + "</style>",
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
def menu_styles():
    """Styling for streamlit-option-menu.

    This component takes inline styles rather than CSS classes, so the
    theme tokens have to be mirrored here as literal values. Keep these
    in sync with LIGHT_TOKENS / DARK_TOKENS above.

    Note the icon colour: the old value (#4fc3f7) was a pale cyan that
    sat at roughly 1.9:1 against a white container — effectively
    invisible in light mode. Each theme now gets an icon colour that
    contrasts with its own container.
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
            "text-align": "center",
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

    Call this, then st.rerun(). The option_menu call reads and clears
    this flag via its manual_select parameter — the library's own
    documented mechanism for programmatic selection.
    """
    st.session_state["_nav_jump_to"] = section_name

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

# -------------------------------
# 3. ERROR LOGGING
# -------------------------------
def log_error(error_message, details=None, user_name=None, endpoint=None):
    """Log errors to the app_errors table for monitoring."""
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
def send_slack_notification(message):
    if not SLACK_WEBHOOK:
        return False
    try:
        payload = {"text": message}
        requests.post(SLACK_WEBHOOK, json=payload, timeout=5)
        return True
    except Exception as e:
        log_error(str(e), endpoint="slack")
        return False

def send_teams_notification(message):
    if not TEAMS_WEBHOOK:
        return False
    try:
        payload = {"text": message}
        requests.post(TEAMS_WEBHOOK, json=payload, timeout=5)
        return True
    except Exception as e:
        log_error(str(e), endpoint="teams")
        return False

def send_external_notifications(message):
    send_slack_notification(message)
    send_teams_notification(message)

# -------------------------------
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
            "already_migrated": bool(u.get("auth_email")),
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
        "role": "Worker",                 # lowest privilege until granted
        "requested_role": requested_role,  # what they asked for
        "password_hash": hash_password(password),
        "email": email,
        "auth_email": compute_auth_email(username, email),
        "job_title": job_title,
        "department": department,
        "employee_id": employee_id,
        "is_approved": False,
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

def create_task(title, location, priority, loto, jsa, created_by, due_date=None,
                is_recurring=False, recurrence_type=None, recurrence_end_date=None,
                asset_id=None, meter_interval=None, work_type="Reactive",
                failure_code=None, failure_start=None, labour_rate=0):
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
                recurrence_type = task.get('recurrence_type')
                if recurrence_type == 'daily':
                    next_due = due_date + timedelta(days=1)
                elif recurrence_type == 'weekly':
                    next_due = due_date + timedelta(weeks=1)
                elif recurrence_type == 'monthly':
                    next_due = due_date + timedelta(days=30)
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
    try:
        res = supabase.table("assets").update(updates).eq("id", asset_id).execute()
        if not res.data:
            return False
        log_audit(updated_by, "asset_update", {"asset_id": asset_id, "new": updates})
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
    "WEAR": "Normal wear and tear", "CORR": "Corrosion", "OTHER": "Other / uncategorised",
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

# -------------------------------
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


def render_logo_bar():
    """A slim bar above the main header showing the company logo, if
    one is configured. Renders nothing at all when no logo is set, so
    it doesn't add empty visual clutter before anyone uploads one."""
    logo_url = fetch_branding()
    if not logo_url or logo_url.startswith("memory://"):
        return
    st.markdown(
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
    there are no active announcements, same convention as the logo bar."""
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

# -------------------------------
# 22. SESSION TIMEOUT CHECK
# -------------------------------
def check_timeout():
    if st.session_state.authenticated:
        if datetime.now() - st.session_state.last_activity > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
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
if not st.session_state.authenticated:
    render_logo_bar()
    render_poster_slideshow()
    render_ticker_bar()
    st.markdown('''
    <div class="main-header">
        <i class="fas fa-hard-hat"></i> Mine & Workshop Digital Tracker
        <small>Smart Maintenance Management System</small>
    </div>
    ''', unsafe_allow_html=True)
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
                st.session_state.authenticated = True
                st.session_state.last_activity = datetime.now()
                log_audit(matched_user.get("full_name"), "login")
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
    '<link rel="manifest" href="data:application/manifest+json;base64,' + _PWA_MANIFEST_B64 + '">'
    '<link rel="icon" type="image/png" href="data:image/png;base64,' + _PWA_ICON192_B64 + '">'
    '<link rel="apple-touch-icon" href="data:image/png;base64,' + _PWA_APPLE_ICON_B64 + '">'
    '''<meta name="theme-color" content="#16213e">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="MWDTS">
<script>
  // Deliberately silent on failure — a missing service worker means
  // slightly slower repeat loads, not a broken app, so this should
  // never surface an error to the user or block anything.
  if (\'serviceWorker\' in navigator) {
    navigator.serviceWorker.register(\'./app/static/sw.js\').catch(function() {
      // Static serving not enabled, or sw.js not deployed yet — fine,
      // the app works normally without it. See PWA_SETUP.md.
    });
  }
</script>''',
    unsafe_allow_html=True,
)

# -------------------------------
# 26. HANDLE RECURRING TASKS
# -------------------------------
handle_recurring_tasks()

# -------------------------------
# 27. MAIN APP
# -------------------------------
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

# Sidebar
with st.sidebar:
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
st.markdown('<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">', unsafe_allow_html=True)

try:
    from streamlit_option_menu import option_menu
except ImportError:
    st.error("streamlit-option-menu not installed. Please run: pip install streamlit-option-menu")
    st.stop()

nav_options = ["Task Dashboard", "Assets", "Permits", "Inventory", "Incidents",
               "Handover", "Contractors", "Analytics", "Chat", "Feedback", "Admin", "Profile", "Timeline"]
nav_icons = ["list-task", "hdd-stack-fill", "shield-lock-fill", "box-seam-fill",
             "exclamation-triangle-fill", "arrow-left-right", "people-fill",
             "graph-up-arrow", "chat-dots-fill", "lightbulb-fill", "gear-fill", "person-circle", "clock-history"]

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
_manual_select = (nav_options.index(st.session_state["_nav_jump_to"])
                  if st.session_state.get("_nav_jump_to") in nav_options else None)
try:
    selected_section = option_menu(
        menu_title=None,
        options=nav_options,
        icons=nav_icons,
        orientation="horizontal",
        default_index=0,
        manual_select=_manual_select,
        styles=menu_styles(),
        key="main_nav",
    )
except TypeError:
    # Older streamlit-option-menu versions (pre ~0.3) don't have
    # manual_select. Degrade to the un-jumpable behavior rather than
    # crash the whole app over a nav convenience — upgrade the package
    # (pip install -U streamlit-option-menu) to restore programmatic
    # navigation from sidebar buttons.
    selected_section = option_menu(
        menu_title=None,
        options=nav_options,
        icons=nav_icons,
        orientation="horizontal",
        default_index=0,
        styles=menu_styles(),
        key="main_nav",
    )
# Clear immediately after use — this should only force a jump ONCE,
# not keep overriding every future click within the nav itself.
st.session_state.pop("_nav_jump_to", None)

# Load shared datasets used across the new modules
db_assets = fetch_all_assets()
st.session_state.assets = db_assets if db_assets else st.session_state.assets_memory
db_parts = fetch_all_parts()
st.session_state.parts = db_parts if db_parts else st.session_state.inventory_memory
db_incidents = fetch_all_incidents()
st.session_state.incidents = db_incidents if db_incidents else st.session_state.incidents_memory

# ---- TASK DASHBOARD ----
if selected_section == "Task Dashboard":
    if role == "worker":
        st.markdown('<div class="sub-header"><i class="fas fa-hard-hat"></i> Field Worker Workspace</div>', unsafe_allow_html=True)
        if st.session_state.broadcast_messages:
            st.info("📢 Latest Broadcasts:")
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
            if not my_tasks:
                st.info("No tasks assigned to you.")
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
                    st.markdown(f"""
                    <div class="task-card" style="border-top: 4px solid { '#dc2626' if overdue else '#0f3460' };">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                            <div>
                                <div class="task-title">#{task['id']} {esc(task['title'])} {overdue_badge}</div>
                                <div class="task-meta">
                                    <span><i class="fas fa-map-marker-alt"></i> {esc(task['location'])}</span>
                                    <span><i class="fas fa-tag"></i> <span class="priority-badge {priority_class}">{task['priority']}</span></span>
                                    <span><i class="fas fa-circle" style="color: #3b82f6;"></i> <span class="status-badge {status_class}">{task['status']}</span></span>
                                    {f'<span><i class="fas fa-calendar-alt"></i> Due: {task["due_date"][:10]}</span>' if task.get('due_date') else ''}
                                </div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Permit gate: if this task requires LOTO, there must be a
                    # live accepted permit before work can be marked in progress.
                    requires_permit = task.get('loto', False)
                    has_permit = task_has_active_permit(task['id'], _all_permits) if requires_permit else True

                    col1, col2 = st.columns([2, 3])
                    with col1:
                        loto = st.checkbox("🔒 LOTO Isolated", value=task.get('loto', False), key=f"loto_{task['id']}_{idx}")
                        jsa = st.checkbox("📋 JSA Signed", value=task.get('jsa', False), key=f"jsa_{task['id']}_{idx}")
                    with col2:
                        status_options = ["In Progress", "Pending QA", "Blocked", "Complete"]
                        current_idx = status_options.index(task['status']) if task['status'] in status_options else 0
                        new_status = st.selectbox("Update Status", status_options, index=current_idx, key=f"stat_{task['id']}_{idx}")

                    if loto != task.get('loto') or jsa != task.get('jsa'):
                        update_task(task['id'], {"loto": loto, "jsa": jsa}, full_name)
                        st.rerun()

                    if requires_permit and not has_permit:
                        st.error("🚫 **This task requires an accepted Permit to Work.** No live permit is recorded "
                                 "against it. Ask your supervisor to issue one, then accept it in the Permits section "
                                 "before starting work.")
                    elif not loto or not jsa:
                        st.error("🔒 Safety isolation forms are required before proceeding.")
                    else:
                        st.success("✅ Safety checks passed.")

                    # Closing out work: capture the data the analytics depend on.
                    if new_status != task['status']:
                        if new_status == "Complete":
                            with st.form(f"close_out_{task['id']}_{idx}", clear_on_submit=True):
                                st.markdown("**Close-out details** — these feed the reliability and cost reports.")
                                fc_options = ["(none)"] + [f"{k} — {v}" for k, v in FAILURE_CODES.items()]
                                fc_sel = st.selectbox("Failure code (for breakdown work)", fc_options)
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
                                st.error("Cannot move to In Progress without an accepted permit.")
                            else:
                                update_task(task['id'], {"status": new_status}, full_name)
                                log_audit(full_name, "task_status_change",
                                          {"task_id": task['id'], "new_status": new_status})
                                st.rerun()

                    with st.expander("💬 Comments"):
                        comments = fetch_comments(task['id'])
                        if comments:
                            for c in comments:
                                st.markdown(f"**{c['posted_by']}** ({c['posted_at'][:16]}): {c['comment']}")
                        else:
                            st.caption("No comments yet.")
                        _comment_val_key = f"_comment_val_{task['id']}_{idx}"
                        if _comment_val_key not in st.session_state:
                            st.session_state[_comment_val_key] = ""
                        new_comment = st.text_area("Add comment", key=f"comment_{task['id']}_{idx}",
                                                   value=st.session_state[_comment_val_key],
                                                   placeholder="Write comment...")
                        if st.button("Post Comment", key=f"post_comment_{task['id']}_{idx}"):
                            if new_comment.strip():
                                if add_comment(task['id'], new_comment, full_name):
                                    st.session_state[_comment_val_key] = ""
                                    st.rerun()
                                else:
                                    st.error("Failed to post comment.")

                    with st.expander("📎 Attachments"):
                        attachments = fetch_attachments(task['id'])
                        if attachments:
                            for a in attachments:
                                st.markdown(f"[{a['file_name']}]({a['file_url']}) (uploaded by {a['uploaded_by']})")
                        else:
                            st.caption("No attachments.")
                        uploaded_file = st.file_uploader("Upload attachment (PDF, DOC, etc.)", type=ALLOWED_ATTACHMENT_EXTENSIONS, key=f"attach_{task['id']}_{idx}")
                        if uploaded_file is not None:
                            if st.button("Upload Attachment", key=f"attach_btn_{task['id']}_{idx}"):
                                bytes_data = uploaded_file.getvalue()
                                if upload_attachment(task['id'], bytes_data, uploaded_file.name, full_name):
                                    st.success("Attachment uploaded!")
                                    st.rerun()

                    st.markdown("---")
                    st.markdown('<i class="fas fa-camera"></i> **Upload Proof Photo**', unsafe_allow_html=True)
                    uploaded_file = st.file_uploader(f"Choose an image for task #{task['id']}", type=["jpg", "jpeg", "png", "gif", "webp", "bmp"], key=f"upload_{task['id']}_{idx}")
                    if uploaded_file is not None:
                        if st.button(f"📤 Upload for Task #{task['id']}", key=f"upload_btn_{task['id']}_{idx}"):
                            bytes_data = uploaded_file.getvalue()
                            success = upload_photo(task['id'], bytes_data, uploaded_file.name, full_name)
                            if success:
                                st.success("Photo uploaded!")
                                st.rerun()
                            else:
                                st.error("Upload failed.")
                    photos = fetch_photos(task['id'])
                    if photos:
                        st.markdown("**📸 Already uploaded:**")
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
                st.success("🎉 No unassigned tasks at the moment.")
            else:
                for task in unassigned:
                    priority_class = f"priority-{task['priority']}"
                    overdue = False
                    if task.get('due_date'):
                        due = _parse_dt(task['due_date'])
                        if due and datetime.now() > due:
                            overdue = True
                    overdue_badge = '<span class="overdue-badge">OVERDUE</span>' if overdue else ''
                    st.markdown(f"""
                    <div class="task-card" style="border-top: 4px solid { '#dc2626' if overdue else '#0f3460' };">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <div class="task-title">#{task['id']} {esc(task['title'])} {overdue_badge}</div>
                                <div class="task-meta">
                                    <span><i class="fas fa-map-marker-alt"></i> {esc(task['location'])}</span>
                                    <span><i class="fas fa-tag"></i> <span class="priority-badge {priority_class}">{task['priority']}</span></span>
                                    {f'<span><i class="fas fa-calendar-alt"></i> Due: {task["due_date"][:10]}</span>' if task.get('due_date') else ''}
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
            st.markdown("### All Maintenance Tasks")
            all_users = fetch_all_users_from_db()
            worker_names = ["Unassigned"] + [u["full_name"] for u in all_users if u["role"].strip().lower() == "worker" and u.get("is_approved", False)]
            if not st.session_state.tasks:
                st.info("No tasks found.")
            for task in st.session_state.tasks:
                priority_class = f"priority-{task['priority']}"
                status_class = f"status-{task['status'].replace(' ', '')}"
                overdue = False
                if task.get('due_date'):
                    due = _parse_dt(task['due_date'])
                    if due and datetime.now() > due:
                        overdue = True
                overdue_badge = '<span class="overdue-badge">OVERDUE</span>' if overdue else ''
                st.markdown(f"""
                <div class="custom-card" style="border-left-color: { '#dc2626' if overdue else '#0f3460' };">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>#{task['id']}: {esc(task['title'])} {overdue_badge}</strong><br>
                            <i class="fas fa-map-marker-alt"></i> {esc(task['location'])}
                            <span class="status-badge {status_class}">{task['status']}</span>
                            <span class="priority-badge {priority_class}">{task['priority']}</span>
                            {f'<i class="fas fa-calendar-alt"></i> {task["due_date"][:10]}' if task.get('due_date') else ''}
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
                            st.markdown(f"**{c['posted_by']}** ({c['posted_at'][:16]}): {c['comment']}")
                    else:
                        st.caption("No comments yet.")
                    _comment_val_key = f"_comment_val_sup_{task['id']}"
                    if _comment_val_key not in st.session_state:
                        st.session_state[_comment_val_key] = ""
                    new_comment = st.text_area("Add comment", key=f"comment_sup_{task['id']}",
                                               value=st.session_state[_comment_val_key],
                                               placeholder="Write comment...")
                    if st.button("Post Comment", key=f"post_comment_sup_{task['id']}"):
                        if new_comment.strip():
                            if add_comment(task['id'], new_comment, full_name):
                                st.session_state[_comment_val_key] = ""
                                st.rerun()
                            else:
                                st.error("Failed to post comment.")
                with st.expander("📎 Attachments"):
                    attachments = fetch_attachments(task['id'])
                    if attachments:
                        for a in attachments:
                            st.markdown(f"[{a['file_name']}]({a['file_url']}) (by {a['uploaded_by']})")
                    else:
                        st.caption("No attachments.")
                    uploaded_file = st.file_uploader("Upload attachment", type=ALLOWED_ATTACHMENT_EXTENSIONS, key=f"attach_sup_{task['id']}")
                    if uploaded_file is not None:
                        if st.button("Upload", key=f"attach_btn_sup_{task['id']}"):
                            bytes_data = uploaded_file.getvalue()
                            if upload_attachment(task['id'], bytes_data, uploaded_file.name, full_name):
                                st.success("Attachment uploaded!")
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
            st.markdown("### Dispatch New Work Ticket")
            with st.form("new_task_form", clear_on_submit=True):
                title = st.text_input("Task Title *", max_chars=100)
                location = st.text_input("Location / Area *", max_chars=100)
                priority = st.selectbox("Priority", ["Low", "Medium", "High", "Critical"])
                due_date = st.date_input("Due Date", value=datetime.now() + timedelta(days=7))
                asset_options = ["None"] + [f"#{a['id']} {a['name']}" for a in st.session_state.get("assets", [])]
                selected_asset = st.selectbox("Linked Asset (optional)", asset_options)
                work_type = st.selectbox("Work Type", ["Reactive", "Preventive", "Planned", "Predictive", "Improvement"],
                                          help="Drives the planned-vs-reactive benchmark. Reactive = breakdown response.")
                labour_rate = st.number_input("Labour rate (per hour, for costing)", min_value=0.0, value=0.0, step=1.0)
                is_recurring = st.checkbox("Recurring Task (Preventive Maintenance)")
                recurrence_type = st.selectbox("Recurrence Type", ["daily", "weekly", "monthly", "meter-based"], disabled=not is_recurring)
                recurrence_end_date = st.date_input("End Date (optional)", value=datetime.now() + timedelta(days=30), disabled=not is_recurring)
                meter_interval = st.number_input("Meter Interval (e.g. every N hours, only if meter-based)", min_value=0, value=0, disabled=not is_recurring)
                loto = st.checkbox("Requires LOTO")
                jsa = st.checkbox("Requires JSA")
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
                            labour_rate=labour_rate
                        )
                        if new_task:
                            st.success(f"Task #{new_task['id']} created!")
                            st.rerun()
                        else:
                            st.error("Failed to create task.")
                    else:
                        st.error("Title and Location are required.")

        elif supervisor_sub == "Dashboard":
            st.markdown("### 📊 Task Analytics")
            tasks = st.session_state.tasks
            st.markdown("#### 🎯 Key Performance Indicators")
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
            st.caption("Full breakdowns, Pareto analysis, and cost reporting are in the **Analytics** section.")
            st.markdown("---")
            if tasks and PANDAS_AVAILABLE and PLOTLY_AVAILABLE:
                df = pd.DataFrame(tasks)
                fig1 = px.pie(df, names='status', title='Tasks by Status')
                st.plotly_chart(fig1, use_container_width=True)
                fig2 = px.bar(df, x='priority', color='status', title='Tasks by Priority and Status')
                st.plotly_chart(fig2, use_container_width=True)
                if 'created_at' in df.columns:
                    df['created_at'] = pd.to_datetime(df['created_at'])
                    df['day'] = df['created_at'].dt.date
                    fig3 = px.line(df.groupby('day').size().reset_index(name='count'), x='day', y='count', title='Tasks Created Per Day')
                    st.plotly_chart(fig3, use_container_width=True)
            elif not PANDAS_AVAILABLE or not PLOTLY_AVAILABLE:
                st.warning("Plotly or pandas not installed. Please run: pip install plotly pandas")
            else:
                st.info("No data to display.")
            if st.button("📥 Export Tasks as CSV"):
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

            st.markdown("### Recent Broadcasts")
            if st.session_state.broadcast_messages:
                for msg in reversed(st.session_state.broadcast_messages[-3:]):
                    st.info(f"**{msg['sender']}** at {msg['timestamp']}: {msg['message']}")
            else:
                st.caption("No broadcasts yet.")

        elif superintendent_sub == "Manage Tasks":
            st.markdown("### Full Task Control")
            all_users = fetch_all_users_from_db()
            worker_names = ["Unassigned"] + [u["full_name"] for u in all_users if u["role"].strip().lower() == "worker" and u.get("is_approved", False)]
            if not st.session_state.tasks:
                st.info("No tasks to manage.")
            for task in st.session_state.tasks:
                priority_class = f"priority-{task['priority']}"
                status_class = f"status-{task['status'].replace(' ', '')}"
                overdue = False
                if task.get('due_date'):
                    due = _parse_dt(task['due_date'])
                    if due and datetime.now() > due:
                        overdue = True
                overdue_badge = '<span class="overdue-badge">OVERDUE</span>' if overdue else ''
                st.markdown(f"""
                <div class="custom-card" style="border-left-color: { '#dc2626' if overdue else '#0f3460' };">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>#{task['id']}: {esc(task['title'])} {overdue_badge}</strong><br>
                            <i class="fas fa-map-marker-alt"></i> {esc(task['location'])}
                            <span class="status-badge {status_class}">{task['status']}</span>
                            <span class="priority-badge {priority_class}">{task['priority']}</span>
                            {f'<i class="fas fa-calendar-alt"></i> {task["due_date"][:10]}' if task.get('due_date') else ''}
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
                        st.error("Delete failed. If this keeps happening, Row Level Security "
                                "may be blocking writes to the tasks table.")
                with st.expander("💬 Comments"):
                    comments = fetch_comments(task['id'])
                    if comments:
                        for c in comments:
                            st.markdown(f"**{c['posted_by']}** ({c['posted_at'][:16]}): {c['comment']}")
                    else:
                        st.caption("No comments yet.")
                    _comment_val_key = f"_comment_val_sup_{task['id']}"
                    if _comment_val_key not in st.session_state:
                        st.session_state[_comment_val_key] = ""
                    new_comment = st.text_area("Add comment", key=f"comment_sup_{task['id']}",
                                               value=st.session_state[_comment_val_key],
                                               placeholder="Write comment...")
                    if st.button("Post Comment", key=f"post_comment_sup_{task['id']}"):
                        if new_comment.strip():
                            if add_comment(task['id'], new_comment, full_name):
                                st.session_state[_comment_val_key] = ""
                                st.rerun()
                            else:
                                st.error("Failed to post comment.")
                with st.expander("📎 Attachments"):
                    attachments = fetch_attachments(task['id'])
                    if attachments:
                        for a in attachments:
                            st.markdown(f"[{a['file_name']}]({a['file_url']}) (by {a['uploaded_by']})")
                    else:
                        st.caption("No attachments.")
                    uploaded_file = st.file_uploader("Upload attachment", type=ALLOWED_ATTACHMENT_EXTENSIONS, key=f"attach_sup_{task['id']}")
                    if uploaded_file is not None:
                        if st.button("Upload", key=f"attach_btn_sup_{task['id']}"):
                            bytes_data = uploaded_file.getvalue()
                            if upload_attachment(task['id'], bytes_data, uploaded_file.name, full_name):
                                st.success("Attachment uploaded!")
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
            st.markdown("### All Broadcast Messages")
            if st.session_state.broadcast_messages:
                for msg in reversed(st.session_state.broadcast_messages):
                    st.write(f"**{msg['sender']}** ({msg['role']}) at {msg['timestamp']}: {msg['message']}")
            else:
                st.info("No messages sent yet.")

        elif superintendent_sub == "Dashboard":
            st.markdown("### 📊 Task Analytics")
            tasks = st.session_state.tasks
            st.markdown("#### 🎯 Key Performance Indicators")
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
            st.caption("Full breakdowns, Pareto analysis, and cost reporting are in the **Analytics** section.")
            st.markdown("---")
            if tasks and PANDAS_AVAILABLE and PLOTLY_AVAILABLE:
                df = pd.DataFrame(tasks)
                fig1 = px.pie(df, names='status', title='Tasks by Status')
                st.plotly_chart(fig1, use_container_width=True)
                fig2 = px.bar(df, x='priority', color='status', title='Tasks by Priority and Status')
                st.plotly_chart(fig2, use_container_width=True)
                if 'created_at' in df.columns:
                    df['created_at'] = pd.to_datetime(df['created_at'])
                    df['day'] = df['created_at'].dt.date
                    fig3 = px.line(df.groupby('day').size().reset_index(name='count'), x='day', y='count', title='Tasks Created Per Day')
                    st.plotly_chart(fig3, use_container_width=True)
            elif not PANDAS_AVAILABLE or not PLOTLY_AVAILABLE:
                st.warning("Plotly or pandas not installed. Please run: pip install plotly pandas")
            else:
                st.info("No data to display.")
            if st.button("📥 Export Tasks as CSV"):
                csv = export_tasks_csv(st.session_state.tasks)
                if csv:
                    st.download_button("Download CSV", data=csv, file_name="tasks_export.csv", mime="text/csv")

        elif superintendent_sub == "User Management":
            st.markdown("### 👥 User Directory")
            # Access decisions moved to the owner-only console. Granting
            # roles is the most privilege-sensitive action in the app, so
            # it sits with one accountable person rather than with every
            # Superintendent.
            if is_owner(username):
                st.info("You are the owner — approvals and role changes are in "
                        "**Owner Console → Access Requests**.")
            else:
                st.info("This is a read-only directory. Access approvals, role "
                        "changes, and suspensions are handled by the account owner.")

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

            st.markdown("#### Active users")
            if approved_users:
                st.dataframe([{
                    "Name": u.get("full_name"),
                    "Username": u.get("username"),
                    "Role": u.get("role"),
                    "Job Title": u.get("job_title") or "—",
                    "Department": u.get("department") or "—",
                } for u in approved_users], use_container_width=True)
            else:
                st.info("No active users yet.")

            if suspended_users:
                st.markdown("#### Suspended")
                for u in suspended_users:
                    st.write(f"- {esc(u.get('full_name'))} (`{esc(u.get('username'))}`)")


# ---- ASSET REGISTER ----
elif selected_section == "Assets":
    st.subheader("🏭 Asset Register")
    can_manage_assets = can(role, "asset.edit")

    if can_manage_assets:
        asset_sub = option_menu(
            menu_title=None,
            options=["All Assets", "Add Asset"],
            icons=["hdd-stack-fill", "plus-circle"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )
    else:
        asset_sub = "All Assets"

    if asset_sub == "All Assets":
        assets = st.session_state.assets
        if not assets:
            st.info("No assets registered yet.")
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
                st.markdown(f"""
                <div class="custom-card">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>#{a['id']}: {esc(a.get('name'))}</strong>
                            <span class="asset-status-badge {status_class}">{esc(a.get('status', 'Operational'))}</span>
                            <span class="priority-badge priority-{esc(a.get('criticality', 'Medium'))}">{esc(a.get('criticality', 'Medium'))}</span><br>
                            <i class="fas fa-tag"></i> Tag: {esc(a.get('asset_tag', 'N/A'))} &nbsp;
                            <i class="fas fa-map-marker-alt"></i> {esc(a.get('location', 'N/A'))} &nbsp;
                            <i class="fas fa-industry"></i> {esc(a.get('manufacturer', 'N/A'))} {esc(a.get('model_number', ''))} &nbsp;
                            <i class="fas fa-tachometer-alt"></i> Meter: {a.get('current_meter', 0)} {esc(a.get('meter_unit', ''))}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
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
                        if readings and PANDAS_AVAILABLE and PLOTLY_AVAILABLE:
                            dfm = pd.DataFrame(readings)
                            dfm['recorded_at'] = pd.to_datetime(dfm['recorded_at'], errors='coerce')
                            st.plotly_chart(px.line(dfm, x='recorded_at', y='reading',
                                                     title=f"Meter trend — {a.get('name')}"),
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
            options=["Stock Levels", "Add Part", "Record Usage"],
            icons=["box-seam-fill", "plus-circle", "dash-circle"],
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
            st.info("No parts in inventory yet.")
        for p in parts:
            is_low = p.get('quantity_on_hand', 0) <= p.get('reorder_point', 0)
            stock_class = "stock-low" if is_low else "stock-ok"
            stock_label = "LOW STOCK" if is_low else "IN STOCK"
            st.markdown(f"""
            <div class="custom-card">
                <strong>{esc(p.get('part_name'))}</strong> ({esc(p.get('part_number', 'N/A'))})
                <span class="stock-badge {stock_class}">{stock_label}</span><br>
                <i class="fas fa-cubes"></i> Qty on hand: {p.get('quantity_on_hand', 0)} &nbsp;
                <i class="fas fa-bell"></i> Reorder at: {p.get('reorder_point', 0)} &nbsp;
                <i class="fas fa-map-marker-alt"></i> Bin: {esc(p.get('bin_location', 'N/A'))} &nbsp;
                <i class="fas fa-truck"></i> Supplier: {esc(p.get('supplier', 'N/A'))} &nbsp;
                <i class="fas fa-dollar-sign"></i> Unit cost: {p.get('unit_cost', 0)}
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

# ---- INCIDENT REPORTS ----
elif selected_section == "Incidents":
    st.subheader("🚨 Incident & Safety Reporting")
    can_manage_incidents = can(role, "incident.investigate")

    if can_manage_incidents:
        inc_sub = option_menu(
            menu_title=None,
            options=["All Incidents", "Report Incident"],
            icons=["exclamation-triangle-fill", "plus-circle"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )
    else:
        inc_sub = option_menu(
            menu_title=None,
            options=["My Reports", "Report Incident"],
            icons=["file-earmark-text", "plus-circle"],
            orientation="horizontal",
            default_index=0,
            styles=menu_styles(),
        )

    incidents = st.session_state.incidents

    if inc_sub in ("All Incidents", "My Reports"):
        visible = incidents if can_manage_incidents else [i for i in incidents if i.get('reported_by') == full_name]
        if not visible:
            st.info("No incidents reported yet.")
        if can_manage_incidents and visible and st.button("📥 Export Incidents as CSV"):
            csv = export_incidents_csv(visible)
            if csv:
                st.download_button("Download CSV", data=csv, file_name="incidents_export.csv", mime="text/csv", key="dl_incidents_csv")
        for inc in visible:
            sev_class = f"severity-{inc.get('severity', 'Low')}"
            _meta_chips_html = render_meta_chips([
                ("fa-map-marker-alt", inc.get('location'), "neutral"),
                ("fa-user", f"Reported by {inc.get('reported_by')}" if inc.get('reported_by') else None, "info"),
                ("fa-clock", _fmt_log_time(inc.get('created_at')), "neutral"),
                ("fa-building", inc.get('department'), "info"),
                ("fa-clock-rotate-left", inc.get('shift'), "neutral"),
                ("fa-id-card", f"ID {inc['reporter_id_no']}" if inc.get('reporter_id_no') else None, "info"),
                ("fa-book", f"Paper ref #{inc['paper_ref_no']}" if inc.get('paper_ref_no') else None, "neutral"),
            ])
            _inc_fields = render_field_grid([
                ("fa-bolt", "Immediate action", inc.get('immediate_action'), "warn"),
                ("fa-lightbulb", "Reporter's suggestion", inc.get('reporter_suggestion'), "info"),
                ("fa-magnifying-glass", "Root cause", inc.get('root_cause'), "neutral"),
                ("fa-check", "Corrective action", inc.get('corrective_action'), "ok"),
            ])
            st.markdown(f"""
            <div class="custom-card" style="border-left-color: #dc2626;">
                <strong>#{inc['id']}: {esc(inc.get('incident_type'))}</strong>
                <span class="severity-badge {sev_class}">{esc(inc.get('severity', 'Low'))}</span>
                <span class="status-badge status-{esc(inc.get('status', 'Open')).replace(' ', '')}">{esc(inc.get('status', 'Open'))}</span>
                {_meta_chips_html}
                <p>{esc(inc.get('description'))}</p>
                {_inc_fields}
                {f"<p><small>Acknowledged by {esc(inc.get('acknowledged_by'))} at {str(inc.get('acknowledged_at',''))[:16]}</small></p>" if inc.get('acknowledged_by') else ""}
            </div>
            """, unsafe_allow_html=True)
            if can_manage_incidents:
                if not inc.get('acknowledged_by'):
                    if st.button(f"✋ Acknowledge receipt — #{inc['id']}", key=f"inc_ack_{inc['id']}"):
                        if acknowledge_incident(inc['id'], full_name):
                            st.success("Acknowledged. You're now the owner of this report.")
                            st.rerun()
                        else:
                            st.error("Update failed. If this keeps happening, Row Level Security may be blocking writes to the incidents table — see schema_additions.sql.")
                with st.expander(f"⚙️ Investigate #{inc['id']}"):
                    new_status = st.selectbox("Status", ["Open", "Investigating", "Resolved", "Closed"],
                                               index=["Open", "Investigating", "Resolved", "Closed"].index(inc.get('status', 'Open')) if inc.get('status') in ["Open", "Investigating", "Resolved", "Closed"] else 0,
                                               key=f"inc_stat_{inc['id']}")
                    root_cause = st.text_area("Root Cause", value=inc.get('root_cause') or '', key=f"inc_root_{inc['id']}")
                    corrective_action = st.text_area("Corrective Action", value=inc.get('corrective_action') or '', key=f"inc_corr_{inc['id']}")
                    if st.button("💾 Save Investigation", key=f"inc_save_{inc['id']}"):
                        if update_incident(inc['id'], {
                            "status": new_status,
                            "root_cause": root_cause,
                            "corrective_action": corrective_action
                        }, full_name):
                            st.success("Incident updated.")
                            st.rerun()
                        else:
                            st.error("Update failed. If this keeps happening, Row Level Security may be blocking writes to the incidents table — see schema_additions.sql.")

    elif inc_sub == "Report Incident":
        st.markdown("### Submit New Incident Report")
        st.caption("Report near-misses, injuries, and hazards as soon as possible. All Critical/High severity reports notify supervisors immediately.")

        # Prefill department/employee ID from the reporter's own profile
        # (set at registration — see Owner Console access requests) so
        # they don't have to retype what the app already knows, matching
        # what the paper form pre-knows about a regular reporter. Both
        # remain editable, since the incident might be filed for a
        # different department than the reporter's home one.
        _my_profile = next((u for u in fetch_all_users_from_db() if u.get("username") == username), {})

        with st.form("new_incident_form", clear_on_submit=True):
            st.markdown("#### Report details")
            _rc1, _rc2 = st.columns(2)
            with _rc1:
                incident_type = selectbox_with_other("Type",
                    ["Near Miss", "Injury", "Property Damage", "Equipment Failure",
                     "Environmental", "Hazard Observation"], key_prefix="incident_type")
                severity = st.selectbox("Severity", ["Low", "Medium", "High", "Critical"])
                department = st.text_input("Department", value=_my_profile.get("department") or "",
                                           max_chars=100)
                shift = st.selectbox("Shift", ["Day Shift", "Night Shift", "Swing Shift",
                                               "Weekend Day", "Weekend Night"])
            with _rc2:
                reporter_id_no = st.text_input("Your ID No.", value=_my_profile.get("employee_id") or "",
                                               max_chars=50)
                assets_list = st.session_state.get("assets", [])
                asset_options = ["None"] + [f"#{a['id']} {a['name']}" for a in assets_list]
                selected_asset = st.selectbox("Related Asset (optional)", asset_options)
                witnesses = st.text_input("Witnesses (optional)", max_chars=200)
                paper_ref_no = st.text_input("Paper book ref. no. (optional)", max_chars=50,
                                             placeholder="e.g. 0000651",
                                             help="If this was first written up in the paper "
                                                  "hazard/near-miss book, record its number here "
                                                  "so both copies can be cross-referenced.")

            location = st.text_input("Location / Area *", max_chars=100)
            description = st.text_area("Description *", placeholder="What happened? Be specific.")
            immediate_action = st.text_area("Immediate Action Taken", placeholder="What was done right away?")
            reporter_suggestion = st.text_area(
                "My suggestion / corrective action",
                placeholder="What do you think should be done to stop this happening again?",
                help="Your own suggestion at the time of reporting — separate from whatever "
                     "the investigating supervisor decides later.")

            confirm_accurate = st.checkbox(
                "I confirm the details above are accurate to the best of my knowledge",
                help="The digital equivalent of signing the paper report.")

            submitted = st.form_submit_button("🚨 Submit Report")
            if submitted:
                if not (location and description):
                    st.error("Location and Description are required.")
                elif not confirm_accurate:
                    st.error("Please confirm the details are accurate before submitting.")
                else:
                    asset_id = None
                    if selected_asset != "None":
                        asset_id = int(selected_asset.split(" ")[0].replace("#", ""))
                    new_incident = create_incident(
                        incident_type, severity, location, description, full_name,
                        asset_id=asset_id, witnesses=witnesses, immediate_action=immediate_action,
                        paper_ref_no=paper_ref_no or None, reporter_id_no=reporter_id_no or None,
                        department=department or None, shift=shift,
                        reporter_suggestion=reporter_suggestion or None)
                    if new_incident:
                        st.success("Incident reported. Thank you for keeping the site safe.")
                        if severity in ("Critical", "High"):
                            st.warning("This has been flagged for immediate supervisor attention.")
                        st.rerun()
                    else:
                        st.error("Failed to submit report.")

# ---- CHAT ROOM ----
elif selected_section == "Permits":
    st.subheader("🔐 Permit to Work / LOTO Register")
    st.caption("A permit must be issued, then accepted by the person doing the work, and signed back on completion. "
               "This register is the auditable record of that chain.")

    permit_tabs = ["Active Permits"]
    if can(role, "permit.issue"):
        permit_tabs.append("Issue Permit")
    permit_tabs.append("Permit History")

    permit_sub = option_menu(
        menu_title=None, options=permit_tabs,
        icons=["shield-check", "plus-circle", "clock-history"][:len(permit_tabs)],
        orientation="horizontal", default_index=0, styles=menu_styles(),
    )

    all_permits = fetch_permits()
    task_lookup = {t['id']: t for t in st.session_state.tasks}

    def _render_permit(p, allow_actions=True):
        status = p.get('status', 'Issued')
        colour = {"Issued": "#f59e0b", "Active": "#10b981", "Closed": "#94a3b8", "Cancelled": "#dc2626"}.get(status, "#0f3460")
        expired = False
        if p.get('valid_until'):
            vu = _parse_dt(p['valid_until'])
            if vu and vu < datetime.now() and status in ("Issued", "Active"):
                expired = True
        linked = task_lookup.get(p.get('task_id'))
        st.markdown(f"""
        <div class="custom-card" style="border-left-color: {colour};">
            <strong>Permit #{p['id']} — {esc(p.get('permit_type'))}</strong>
            <span class="status-badge" style="background:{colour};">{esc(status)}</span>
            {'<span class="overdue-badge">EXPIRED</span>' if expired else ''}<br>
            <i class="fas fa-clipboard-list"></i> Task: {esc(linked['title']) if linked else 'N/A'}<br>
            <i class="fas fa-lock"></i> Lock tags: {esc(p.get('lock_tag_numbers') or 'N/A')}<br>
            <i class="fas fa-power-off"></i> Isolation points: {esc(p.get('isolation_points') or 'N/A')}<br>
            <i class="fas fa-exclamation-triangle"></i> Hazards: {esc(p.get('hazards_identified') or 'N/A')}<br>
            <small>
            Issued by {esc(p.get('issued_by'))} at {str(p.get('issued_at', ''))[:16]}
            {f" · Accepted by {esc(p.get('accepted_by'))} at {str(p.get('accepted_at',''))[:16]}" if p.get('accepted_by') else ""}
            {f" · Signed back by {esc(p.get('signed_back_by'))} at {str(p.get('signed_back_at',''))[:16]}" if p.get('signed_back_by') else ""}
            {f" · Valid until {str(p.get('valid_until',''))[:16]}" if p.get('valid_until') else ""}
            </small>
        </div>
        """, unsafe_allow_html=True)

        if not allow_actions:
            return
        acols = st.columns(3)
        if status == "Issued" and can(role, "permit.accept"):
            if acols[0].button("✍️ Accept Isolation", key=f"permit_acc_{p['id']}"):
                if accept_permit(p['id'], full_name):
                    st.success("Permit accepted. You are now the responsible person.")
                    st.rerun()
                else:
                    st.error("Accept failed — the permit was not updated. Check Row Level "
                             "Security on the permits table before assuming isolation is in place.")
        if status == "Active" and can(role, "permit.sign_back"):
            if acols[1].button("✅ Sign Back", key=f"permit_sb_{p['id']}"):
                if sign_back_permit(p['id'], full_name):
                    st.success("Permit signed back and closed.")
                    st.rerun()
                else:
                    st.error("Sign-back failed — the permit is still showing as Active.")
        if status in ("Issued", "Active") and can(role, "permit.cancel"):
            if acols[2].button("🚫 Cancel", key=f"permit_can_{p['id']}"):
                if cancel_permit(p['id'], full_name):
                    st.rerun()
                else:
                    st.error("Cancel failed — the permit was not updated.")

    if permit_sub == "Active Permits":
        live = [p for p in all_permits if p.get('status') in ("Issued", "Active")]
        if not live:
            st.info("No open permits.")
        else:
            expired_live = [p for p in live if (_parse_dt(p.get('valid_until')) or datetime.max) < datetime.now()]
            if expired_live:
                st.error(f"⚠️ {len(expired_live)} open permit(s) are past their validity window and must be reviewed or cancelled.")
            for p in live:
                _render_permit(p)

    elif permit_sub == "Issue Permit":
        if require(role, "permit.issue"):
            st.markdown("### Issue New Permit")
            open_tasks = [t for t in st.session_state.tasks if t.get('status') != 'Complete']
            if not open_tasks:
                st.info("No open tasks to attach a permit to.")
            else:
                with st.form("issue_permit_form", clear_on_submit=True):
                    task_map = {f"#{t['id']} {t['title']}": t['id'] for t in open_tasks}
                    sel_task = st.selectbox("Task requiring the permit *", list(task_map.keys()))
                    permit_type = selectbox_with_other("Permit Type", [
                        "General Work Permit", "LOTO / Isolation", "Hot Work", "Confined Space",
                        "Working at Height", "Excavation", "Electrical Isolation", "Live Line"],
                        key_prefix="permit_type")
                    lock_tags = st.text_input("Lock / Tag Numbers *", placeholder="e.g. LT-1042, LT-1043")
                    isolation_points = st.text_area("Isolation Points *", placeholder="List each energy source isolated")
                    hazards = st.text_area("Hazards Identified *", placeholder="Stored energy, residual pressure, etc.")
                    valid_hours = st.number_input("Valid for (hours)", min_value=1, max_value=72, value=12)
                    confirm = st.checkbox("I confirm isolation has been physically verified at each point listed above.")
                    submitted = st.form_submit_button("🔐 Issue Permit")
                    if submitted:
                        if not (lock_tags and isolation_points and hazards):
                            st.error("Lock tags, isolation points, and hazards are all required.")
                        elif not confirm:
                            st.error("You must confirm physical verification of isolation before a permit can be issued.")
                        else:
                            tid = task_map[sel_task]
                            linked_task = task_lookup.get(tid, {})
                            permit = issue_permit(
                                tid, linked_task.get('asset_id'), permit_type, lock_tags,
                                isolation_points, hazards, full_name,
                                datetime.now() + timedelta(hours=valid_hours))
                            if permit:
                                st.success(f"Permit #{permit['id']} issued. It must now be accepted by the person performing the work.")
                                st.rerun()
                            else:
                                st.error("Failed to issue permit.")

    elif permit_sub == "Permit History":
        closed = [p for p in all_permits if p.get('status') in ("Closed", "Cancelled")]
        if not closed:
            st.info("No closed permits yet.")
        for p in closed[:50]:
            _render_permit(p, allow_actions=False)

elif selected_section == "Handover":
    st.subheader("🔄 Shift Handover Log")
    st.caption("Structured handover between shifts. Lost context between crews is a recognised contributor to incidents, "
               "so outstanding work and safety concerns are captured explicitly.")

    handover_tabs = ["Recent Handovers"]
    if can(role, "handover.create"):
        handover_tabs.append("New Handover")
    handover_sub = option_menu(
        menu_title=None, options=handover_tabs,
        icons=["journal-text", "plus-circle"][:len(handover_tabs)],
        orientation="horizontal", default_index=0, styles=menu_styles(),
    )

    handovers = fetch_handovers()

    if handover_sub == "Recent Handovers":
        unack = [h for h in handovers if not h.get('acknowledged')]
        if unack:
            st.warning(f"📋 {len(unack)} handover(s) not yet acknowledged by the incoming supervisor.")
        if not handovers:
            st.info("No handovers logged yet.")
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
                {f"<small>Acknowledged by {esc(h.get('acknowledged_by'))} at {str(h.get('acknowledged_at',''))[:16]}</small>" if h.get('acknowledged') else ""}
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

elif selected_section == "Contractors":
    st.subheader("👷 Contractor Management")
    st.caption("Induction and insurance expiry are tracked because they commonly gate site access. "
               "Expired or missing records are flagged as blocking.")

    if require(role, "contractor.view"):
        contractor_tabs = ["All Contractors"]
        if can(role, "contractor.manage"):
            contractor_tabs.append("Add Contractor")
        contractor_sub = option_menu(
            menu_title=None, options=contractor_tabs,
            icons=["people", "plus-circle"][:len(contractor_tabs)],
            orientation="horizontal", default_index=0, styles=menu_styles(),
        )

        contractors = fetch_contractors()

        if contractor_sub == "All Contractors":
            blocked = []
            for c in contractors:
                label, is_blocking = contractor_compliance_status(c)
                if is_blocking:
                    blocked.append(c)
            if blocked:
                st.error(f"🚫 {len(blocked)} contractor(s) have expired or missing compliance records and should not be granted site access.")
            if not contractors:
                st.info("No contractors registered yet.")
            for c in contractors:
                label, is_blocking = contractor_compliance_status(c)
                badge_colour = "#dc2626" if is_blocking else ("#f59e0b" if label != "Compliant" else "#10b981")
                st.markdown(f"""
                <div class="custom-card" style="border-left-color: {badge_colour};">
                    <strong>{esc(c.get('company_name'))}</strong>
                    <span class="status-badge" style="background:{badge_colour};">{esc(label)}</span><br>
                    <i class="fas fa-user"></i> {esc(c.get('contact_person') or 'N/A')}
                    &nbsp;<i class="fas fa-envelope"></i> {esc(c.get('contact_email') or 'N/A')}
                    &nbsp;<i class="fas fa-phone"></i> {esc(c.get('contact_phone') or 'N/A')}<br>
                    <i class="fas fa-id-card"></i> Induction expires: {str(c.get('induction_expiry') or 'Not set')[:10]}
                    &nbsp;<i class="fas fa-file-contract"></i> Insurance expires: {str(c.get('insurance_expiry') or 'Not set')[:10]}<br>
                    <i class="fas fa-tools"></i> Competencies: {esc(c.get('competencies') or 'None recorded')}
                </div>
                """, unsafe_allow_html=True)
                if can(role, "contractor.manage"):
                    with st.expander(f"⚙️ Update {c.get('company_name')}"):
                        ccols = st.columns(3)
                        new_ind = ccols[0].date_input("Induction expiry", key=f"ind_{c['id']}")
                        new_ins = ccols[1].date_input("Insurance expiry", key=f"ins_{c['id']}")
                        if ccols[2].button("💾 Save", key=f"csave_{c['id']}"):
                            if update_contractor(c['id'], {
                                "induction_expiry": new_ind.isoformat(),
                                "insurance_expiry": new_ins.isoformat(),
                            }, full_name):
                                st.success("Contractor updated.")
                                st.rerun()
                            else:
                                st.error("Save failed — compliance dates were NOT updated. "
                                        "Check Row Level Security on the contractors table "
                                        "before assuming this contractor's status is current.")

        elif contractor_sub == "Add Contractor":
            if require(role, "contractor.manage"):
                with st.form("contractor_form", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        company_name = st.text_input("Company Name *", max_chars=150)
                        contact_person = st.text_input("Contact Person", max_chars=100)
                        contact_email = st.text_input("Contact Email", max_chars=150)
                        contact_phone = st.text_input("Contact Phone", max_chars=50)
                    with c2:
                        induction_date = st.date_input("Induction Date", value=datetime.now())
                        induction_expiry = st.date_input("Induction Expiry", value=datetime.now() + timedelta(days=365))
                        insurance_expiry = st.date_input("Insurance Expiry", value=datetime.now() + timedelta(days=365))
                    competencies = st.text_area("Competencies / Certifications",
                                                 placeholder="e.g. Confined space, EWP licence, HV switching")
                    notes = st.text_area("Notes")
                    submitted = st.form_submit_button("➕ Add Contractor")
                    if submitted:
                        if company_name:
                            c = create_contractor(company_name, contact_person, contact_email,
                                                   contact_phone, induction_date, induction_expiry,
                                                   insurance_expiry, competencies, notes, full_name)
                            if c:
                                st.success(f"Contractor '{company_name}' added.")
                                st.rerun()
                            else:
                                st.error("Failed to add contractor.")
                        else:
                            st.error("Company Name is required.")

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
            options=["Reliability", "Backlog & Compliance", "Failure Pareto", "Cost", "Safety"],
            icons=["speedometer2", "list-check", "bar-chart-fill", "cash-coin", "shield-fill-check"],
            orientation="horizontal", default_index=0, styles=menu_styles(),
        )

        if analytics_sub == "Reliability":
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

            st.markdown("#### Asset Task Frequency")
            ranking = compute_asset_downtime_ranking(tasks, assets)
            if ranking and PANDAS_AVAILABLE and PLOTLY_AVAILABLE:
                dfr = pd.DataFrame(ranking[:15], columns=["Asset", "Tasks"])
                st.plotly_chart(px.bar(dfr, x="Asset", y="Tasks",
                                        title="Maintenance tasks per asset (proxy for downtime frequency)"),
                                use_container_width=True)
            elif ranking:
                for name, cnt in ranking[:15]:
                    st.write(f"- **{esc(name)}**: {cnt}")
            else:
                st.caption("No tasks linked to assets yet.")

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
                    st.plotly_chart(px.bar(dfb, x="Age", y="Open tasks", title="Open work by age"),
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
                                                title="Failure modes by frequency"),
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
                                                title="Cost by asset"), use_container_width=True)
                st.caption("Currency is whatever you enter — the app does not assume or convert units.")

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
                    st.plotly_chart(px.pie(dfi, names='severity', title='Incidents by severity'),
                                    use_container_width=True)
                if 'incident_type' in dfi.columns:
                    st.plotly_chart(px.bar(dfi.groupby('incident_type').size().reset_index(name='count'),
                                            x='incident_type', y='count', title='Incidents by type'),
                                    use_container_width=True)

        if can(role, "analytics.export"):
            st.markdown("---")
            st.markdown("#### Exports")
            ecols = st.columns(4)
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
        options=["Access Requests", "Active Users", "Decision History", "Auth Migration", "Settings"],
        icons=["person-plus-fill", "people-fill", "journal-text", "shield-lock-fill", "sliders"],
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
                        st.markdown(
                            f"<small>"
                            f"<i class='fas fa-briefcase'></i> {esc(u.get('job_title') or 'No job title')} &nbsp;·&nbsp; "
                            f"<i class='fas fa-users'></i> {esc(u.get('department') or 'No department')}<br>"
                            f"<i class='fas fa-id-card'></i> ID: {esc(u.get('employee_id') or 'Not provided')} &nbsp;·&nbsp; "
                            f"<i class='fas fa-envelope'></i> {esc(u.get('email') or 'No email')}<br>"
                            f"<i class='fas fa-clock'></i> Requested {str(u.get('requested_at') or '')[:16]}"
                            f"</small>", unsafe_allow_html=True)
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
                st.markdown(
                    f"**{esc(u.get('full_name'))}** `{esc(u.get('username'))}` "
                    f"<span class='status-badge' style='background:{_colour};'>"
                    f"{'SUSPENDED' if _suspended else esc(u.get('role', 'Worker'))}</span>"
                    f"{' <span class=\"verified-badge\">OWNER</span>' if _owner_row else ''}",
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
                    f"<small>{str(d.get('decided_at',''))[:16]}</small>",
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
                                          "computed_auth_email", "is_placeholder", "already_migrated"]]
                st.dataframe(_df, use_container_width=True, hide_index=True)
            else:
                for r in rows:
                    st.write(f"`{r['username']}` → `{r['computed_auth_email']}`"
                            f"{' (placeholder)' if r['is_placeholder'] else ''}"
                            f"{' ✓ already mapped' if r['already_migrated'] else ''}")

            _dup_usernames = {u for usernames in duplicates.values() for u in usernames} if duplicates else set()
            _eligible = [r["username"] for r in rows
                        if not r["already_migrated"] and r["username"] not in _dup_usernames]

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

    # ---------- SETTINGS ----------
    elif owner_sub == "Settings":
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
    _switch_cols = st.columns([1, 1, 2])
    if _switch_cols[0].button("🌍 Global", use_container_width=True,
                              disabled=(room == "global")):
        st.session_state.chat_room = "global"
        st.rerun()
    if can(role, "chat.supervisor_room"):
        if _switch_cols[1].button("🔒 Supervisor", use_container_width=True,
                                  disabled=(room == "supervisor")):
            st.session_state.chat_room = "supervisor"
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
            st.info("No messages yet.")

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
                st.markdown(f"""
                <div class="custom-card" style="border-left-color: var(--tone-{tone});">
                    <strong>{esc(f.get('title'))}</strong>
                    <span class="priority-badge" style="background:var(--tone-{tone});">{esc(f.get('status', 'New'))}</span>
                    {f'<span class="priority-badge" style="background:var(--tone-neutral);">{esc(f["category"])}</span>' if f.get('category') else ''}
                    <br>
                    <small><i class="fas fa-user"></i> {esc(f.get('submitted_by'))} &nbsp;
                    <i class="fas fa-clock"></i> {str(f.get('created_at', ''))[:16]}</small>
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
            st.markdown("### Audit Log (last 50)")
            try:
                logs = supabase.table("audit_log").select("*").order("created_at", desc=True).limit(50).execute()
                render_log_entries(logs.data or [])
            except Exception:
                st.info("Audit log unavailable.")
        else:
            st.info("Audit log not available (Supabase not connected).")

# ---- PROFILE TAB ----
elif selected_section == "Profile":
    st.subheader("👤 User Profile")
    st.markdown(f"**Username:** {username}")
    st.markdown(f"**Full Name:** {full_name}")
    st.markdown(f"**Role:** {user['role']}")
    st.markdown(f"**Email:** {user_email if user_email else 'Not set'}")
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
