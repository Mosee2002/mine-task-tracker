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

# -------------------------------
# 0. PAGE CONFIG  (must be the very first Streamlit command)
# -------------------------------
# This MUST run before any other st.* call. Previously the credential
# warnings fired first, which raises StreamlitAPIException and can
# swallow the real connection error, making every failure look
# identical ("demo mode") regardless of its actual cause.
st.set_page_config(
    page_title="Mine & Workshop Tracker",
    page_icon="\U0001F6E0\uFE0F",
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

/* ---------- Header ---------- */
.main-header {
    background: linear-gradient(135deg, #16213e 0%, #1b2b52 55%, #143a63 100%);
    color: #ffffff;
    padding: 1.25rem 1.6rem;
    border-radius: 14px;
    margin-bottom: 1.1rem;
    box-shadow: var(--shadow-md);
    font-size: 1.75rem;      /* was 2.5rem, which clipped its own text */
    font-weight: 800;
    line-height: 1.25;       /* the actual cause of the clipped title */
    letter-spacing: -0.01em;
}
.main-header i { color: #7cb3ff; margin-right: 10px; }
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
    background: var(--bg-surface-2);
    color: var(--text-primary);
    border-left: 4px solid var(--accent);
    border-radius: 10px;
    padding: 0.55rem 0.9rem;
    margin: 0.25rem 0;
    line-height: 1.5;
}
.chat-message.self { background: var(--accent-soft); }
.chat-message .sender { font-weight: 800; color: var(--text-primary); }
.chat-message .timestamp {
    font-size: 0.72rem;
    color: var(--text-secondary);
    margin-left: 0.4rem;
}

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
def send_email_notification(recipient, subject, body):
    if not recipient:
        return False
    try:
        smtp_server = st.secrets.get("SMTP_SERVER")
        smtp_port = st.secrets.get("SMTP_PORT", 587)
        smtp_user = st.secrets.get("SMTP_USER")
        smtp_password = st.secrets.get("SMTP_PASSWORD")
        smtp_from = st.secrets.get("SMTP_FROM", smtp_user)
        if not all([smtp_server, smtp_user, smtp_password]):
            return False
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart()
        msg['From'] = smtp_from
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return True
    except Exception as e:
        log_error(str(e), endpoint="send_email")
        return False

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
        supabase.table("facility_users").update({
            "is_approved": True,
            "is_suspended": False,
            "role": granted_role,
            "decision_by": decided_by,
            "decision_at": datetime.now().isoformat(),
            "denial_reason": None,
        }).eq("username", username).execute()
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
        supabase.table("facility_users").update({
            "is_approved": False,
            "is_suspended": True,
            "decision_by": decided_by,
            "decision_at": datetime.now().isoformat(),
            "denial_reason": reason,
        }).eq("username", username).execute()
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
        supabase.table("facility_users").update({
            "role": new_role,
            "decision_by": decided_by,
            "decision_at": datetime.now().isoformat(),
        }).eq("username", username).execute()
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
        supabase.table("facility_users").update({
            "is_suspended": suspended,
            "is_approved": (not suspended) and target.data[0].get("is_approved", False),
            "decision_by": decided_by,
            "decision_at": datetime.now().isoformat(),
        }).eq("username", username).execute()
        action = "suspended" if suspended else "reinstated"
        log_access_decision(username, full_name, action, decided_by, reason=reason)
        log_audit(decided_by, f"access_{action}", {"username": username})
        return True, ""
    except Exception as e:
        log_error(str(e), endpoint="set_user_suspended")
        return False, str(e)


def remove_user(username, decided_by, reason=None):
    if not SUPABASE_AVAILABLE:
        return False, "No database connected."
    if is_owner(username):
        return False, "The owner account cannot be removed from inside the app."
    try:
        target = supabase.table("facility_users").select("*").eq("username", username).execute()
        full_name = target.data[0].get("full_name") if target.data else None
        old_role = target.data[0].get("role") if target.data else None
        supabase.table("facility_users").delete().eq("username", username).execute()
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
        supabase.table("facility_users").insert({
            "username": username,
            "full_name": full_name,
            "role": "Superintendent",
            "password_hash": hash_password(password),
            "email": email,
            "is_approved": True,
        }).execute()
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
    try:
        payload = {
            "username": username,
            "full_name": name,
            "role": "Worker",                 # lowest privilege until granted
            "requested_role": requested_role,  # what they asked for
            "password_hash": hash_password(password),
            "email": email,
            "job_title": job_title,
            "department": department,
            "employee_id": employee_id,
            "is_approved": False,
            "is_suspended": False,
            "requested_at": datetime.now().isoformat(),
        }
        supabase.table("facility_users").insert(payload).execute()
        log_audit(name, "access_request",
                  {"username": username, "requested_role": requested_role})
        # Tell the owner there is something to review.
        if OWNER_USERNAME:
            send_notification(OWNER_USERNAME, "New access request",
                              f"{name} ({username}) requested access as {requested_role}.")
        return True, ""
    except Exception as e:
        log_error(str(e), details={"username": username}, endpoint="register_user")
        return False, str(e)

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
        supabase.table("facility_users").update(updates).eq("username", username).execute()
        return True
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
    if not SUPABASE_AVAILABLE:
        return False
    token = secrets.token_urlsafe(32)
    expiry = datetime.now() + timedelta(hours=1)
    try:
        supabase.table("facility_users").update({
            "password_reset_token": token,
            "reset_token_expiry": expiry.isoformat()
        }).eq("username", username).eq("email", email).execute()
        reset_link = f"{APP_URL}/?reset_token={token}"
        body = f"Click the link to reset your password: <a href='{reset_link}'>Reset Password</a>"
        send_email_notification(email, "Password Reset Request", body)
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
        supabase.table("tasks").delete().eq("id", task_id).execute()
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
    st.session_state.setdefault("photos_memory", []).append({
        "task_id": task_id,
        "photo_url": f"memory://{filename}",
        "uploaded_by": uploaded_by,
        "uploaded_at": datetime.now().isoformat()
    })
    log_audit(uploaded_by, "photo_upload_memory", {"task_id": task_id, "filename": filename})
    if SUPABASE_AVAILABLE:
        try:
            valid, msg = validate_image(file_bytes, filename)
            if not valid:
                st.error(msg)
                return True
            ext = filename.split(".")[-1]
            safe_name = f"task_{task_id}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(file_bytes).hexdigest()[:8]}.{ext}"
            res = supabase.storage.from_("task_photos").upload(safe_name, file_bytes)
            if res:
                public_url = supabase.storage.from_("task_photos").get_public_url(safe_name)
                try:
                    data = {"task_id": task_id, "photo_url": public_url, "uploaded_by": uploaded_by}
                    supabase.table("task_photos").insert(data).execute()
                    log_audit(uploaded_by, "photo_upload", {"task_id": task_id, "url": public_url})
                except Exception as e:
                    log_error(str(e), endpoint="photo_insert")
        except Exception as e:
            log_error(str(e), endpoint="photo_upload")
            pass
    return True

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
            supabase.table("task_attachments").insert(data).execute()
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
        supabase.table("task_comments").insert(data).execute()
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
        supabase.table("chat_messages").insert(payload).execute()
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
            if msg.data:
                log_audit(deleted_by, "message_delete", {"message_id": message_id, "content": msg.data[0]["message"][:50]})
            supabase.table("chat_messages").delete().eq("id", message_id).execute()
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
    cols = ['id', 'incident_type', 'severity', 'location', 'status', 'reported_by',
            'description', 'root_cause', 'corrective_action', 'created_at']
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
            due_date = datetime.fromisoformat(task['due_date']) if task['due_date'] else None
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
                end_date = datetime.fromisoformat(task['recurrence_end_date']) if task.get('recurrence_end_date') else None
                if end_date and next_due > end_date:
                    supabase.table("tasks").update({"is_recurring": False}).eq("id", task["id"]).execute()
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
                supabase.table("tasks").insert(new_task).execute()
                supabase.table("tasks").update({"due_date": next_due.isoformat()}).eq("id", task["id"]).execute()
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
        supabase.table("assets").update(updates).eq("id", asset_id).execute()
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
        supabase.table("assets").delete().eq("id", asset_id).execute()
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
        supabase.table("inventory_parts").update({"quantity_on_hand": new_qty}).eq("id", part_id).execute()
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
        supabase.table("inventory_parts").delete().eq("id", part_id).execute()
        log_audit(deleted_by, "part_delete", {"part_id": part_id})
        return True
    except Exception as e:
        log_error(str(e), details={"part_id": part_id}, endpoint="delete_part")
        return False

def link_part_to_task(task_id, part_id, quantity_used, used_by):
    """Records parts consumption against a task/work order and decrements stock."""
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
            supabase.table("task_parts").insert(payload).execute()
        except Exception as e:
            log_error(str(e), details=payload, endpoint="link_part_to_task")
            return False
    adjust_part_quantity(part_id, -abs(quantity_used), used_by, reason=f"used on task #{task_id}")
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

def create_incident(incident_type, severity, location, description, reported_by, asset_id=None, witnesses=None, immediate_action=None):
    payload = {
        "incident_type": incident_type,
        "severity": severity,
        "location": location,
        "description": description,
        "reported_by": reported_by,
        "asset_id": asset_id,
        "witnesses": witnesses,
        "immediate_action": immediate_action,
        "status": "Open",
        "root_cause": None,
        "corrective_action": None,
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
        supabase.table("incidents").update(updates).eq("id", incident_id).execute()
        log_audit(updated_by, "incident_update", {"incident_id": incident_id, "new": updates})
        return True
    except Exception as e:
        log_error(str(e), details={"incident_id": incident_id, "updates": updates}, endpoint="update_incident")
        return False

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
        supabase.table("permits").update(updates).eq("id", permit_id).execute()
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
        supabase.table("shift_handovers").update(updates).eq("id", handover_id).execute()
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
        supabase.table("contractors").update(updates).eq("id", contractor_id).execute()
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
            supabase.table("meter_readings").insert(payload).execute()
            log_audit(recorded_by, "meter_reading", {"asset_id": asset_id, "reading": reading})
        except Exception as e:
            log_error(str(e), details=payload, endpoint="log_meter_reading")
            return False
    # Keep the asset's denormalised current reading in step
    update_asset(asset_id, {"current_meter": reading}, recorded_by)
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
        with st.form("bootstrap_admin"):
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
                expiry = datetime.fromisoformat(u["reset_token_expiry"]) if u.get("reset_token_expiry") else datetime.now()
                if expiry > datetime.now():
                    with st.form("reset_password_form"):
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
    with st.form("login_form"):
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
                    "avatar_url": matched_user.get("avatar_url", None)
                }
                st.session_state.authenticated = True
                st.session_state.last_activity = datetime.now()
                log_audit(matched_user.get("full_name"), "login")
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
        with st.form("reset_form"):
            reset_email = st.text_input("Enter your registered email", placeholder="email@example.com")
            if st.form_submit_button("Send Reset Link"):
                users = fetch_all_users_from_db()
                for u in users:
                    if u.get("email") == reset_email:
                        if generate_reset_token(u["username"], reset_email):
                            st.success("Reset link sent to your email.")
                        else:
                            st.error("Failed to send reset link.")
                        break
                else:
                    st.error("Email not found.")

    if AUTH_AVAILABLE and GOOGLE_CLIENT_ID:
        if st.button("🔑 Login with Google", use_container_width=True):
            st.info("OAuth login will redirect to Google. (Integration in progress)")

    st.markdown("---")
    st.markdown('<div class="sub-header"><i class="fas fa-user-plus"></i> Create Account Profile</div>', unsafe_allow_html=True)

    with st.form("register_form"):
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

# -------------------------------
# 25. PWA MANIFEST & SERVICE WORKER
# -------------------------------
st.markdown("""
<link rel="manifest" href="/static/manifest.json">
<script>
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js');
  }
</script>
""", unsafe_allow_html=True)

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
                for email in worker_emails:
                    send_email_notification(email, f"Broadcast from {full_name}", broadcast_msg.replace('\n', '<br>'))
                send_push_notification("New Broadcast", broadcast_msg[:100])
                st.success("Broadcast sent!")
                st.rerun()
            else:
                st.error("Message cannot be empty.")

    st.markdown("---")
    st.markdown("💬 **Chat Rooms**")
    if st.button("🌍 Global Chat", use_container_width=True):
        st.session_state.chat_room = "global"
        st.rerun()
    if can(role, "chat.supervisor_room"):
        if st.button("🔒 Supervisor Room", use_container_width=True):
            st.session_state.chat_room = "supervisor"
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
            st.rerun()
    else:
        st.info("No other approved users available.")

    st.markdown("---")
    st.markdown("👤 **Profile**")
    if st.button("👤 My Profile", use_container_width=True):
        st.session_state.active_tab = "profile"
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
               "Handover", "Contractors", "Analytics", "Chat", "Admin", "Profile", "Timeline"]
nav_icons = ["list-task", "hdd-stack-fill", "shield-lock-fill", "box-seam-fill",
             "exclamation-triangle-fill", "arrow-left-right", "people-fill",
             "graph-up-arrow", "chat-dots-fill", "gear-fill", "person-circle", "clock-history"]

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

selected_section = option_menu(
    menu_title=None,
    options=nav_options,
    icons=nav_icons,
    orientation="horizontal",
    default_index=0,
    styles=menu_styles(),
)

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
                        due = datetime.fromisoformat(task['due_date'])
                        if datetime.now() > due:
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
                            with st.form(f"close_out_{task['id']}_{idx}"):
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
                        new_comment = st.text_area("Add comment", key=f"comment_{task['id']}_{idx}", placeholder="Write comment...")
                        if st.button("Post Comment", key=f"post_comment_{task['id']}_{idx}"):
                            if new_comment.strip():
                                add_comment(task['id'], new_comment, full_name)
                                st.rerun()

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
                        due = datetime.fromisoformat(task['due_date'])
                        if datetime.now() > due:
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
                    due = datetime.fromisoformat(task['due_date'])
                    if datetime.now() > due:
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
                    new_comment = st.text_area("Add comment", key=f"comment_sup_{task['id']}", placeholder="Write comment...")
                    if st.button("Post Comment", key=f"post_comment_sup_{task['id']}"):
                        if new_comment.strip():
                            add_comment(task['id'], new_comment, full_name)
                            st.rerun()
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
            with st.form("new_task_form"):
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
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Total Tasks", total)
            col2.metric("Completed", completed)
            col3.metric("In Progress", in_progress)
            col4.metric("Unassigned", unassigned)
            col5.metric("Blocked", blocked)

            acol1, acol2, acol3, acol4 = st.columns(4)
            acol1.metric("Registered Assets", len(st.session_state.get("assets", [])))
            down_assets = sum(1 for a in st.session_state.get("assets", []) if a.get('status') == 'Down')
            acol2.metric("Assets Down", down_assets)
            low_stock_count = sum(1 for p in st.session_state.get("parts", []) if p.get('quantity_on_hand', 0) <= p.get('reorder_point', 0))
            acol3.metric("Low Stock Parts", low_stock_count)
            open_incidents = sum(1 for i in st.session_state.get("incidents", []) if i.get("status") in ("Open", "Investigating"))
            acol4.metric("Open Incidents", open_incidents)

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
                    due = datetime.fromisoformat(task['due_date'])
                    if datetime.now() > due:
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
                    delete_task(task['id'], full_name)
                    st.rerun()
                with st.expander("💬 Comments"):
                    comments = fetch_comments(task['id'])
                    if comments:
                        for c in comments:
                            st.markdown(f"**{c['posted_by']}** ({c['posted_at'][:16]}): {c['comment']}")
                    else:
                        st.caption("No comments yet.")
                    new_comment = st.text_area("Add comment", key=f"comment_sup_{task['id']}", placeholder="Write comment...")
                    if st.button("Post Comment", key=f"post_comment_sup_{task['id']}"):
                        if new_comment.strip():
                            add_comment(task['id'], new_comment, full_name)
                            st.rerun()
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
                                log_meter_reading(a['id'], new_reading, a.get('meter_unit'), full_name, mr_note)
                                st.success("Reading logged.")
                                st.rerun()
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
        with st.form("new_asset_form"):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Asset Name *", max_chars=100)
                asset_tag = st.text_input("Asset Tag / ID *", max_chars=50)
                category = st.selectbox("Category", ["Heavy Equipment", "Fixed Plant", "Vehicle", "Electrical", "Hydraulic", "Conveyor", "Pump", "Other"])
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
        with st.form("new_part_form"):
            c1, c2 = st.columns(2)
            with c1:
                part_name = st.text_input("Part Name *", max_chars=100)
                part_number = st.text_input("Part Number", max_chars=50)
                category = st.selectbox("Category", ["Bearings", "Belts", "Filters", "Hydraulic", "Electrical", "Fasteners", "Seals", "Lubricants", "Other"])
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
            with st.form("use_part_form"):
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
            st.markdown(f"""
            <div class="custom-card" style="border-left-color: #dc2626;">
                <strong>#{inc['id']}: {esc(inc.get('incident_type'))}</strong>
                <span class="severity-badge {sev_class}">{esc(inc.get('severity', 'Low'))}</span>
                <span class="status-badge status-{esc(inc.get('status', 'Open')).replace(' ', '')}">{esc(inc.get('status', 'Open'))}</span><br>
                <i class="fas fa-map-marker-alt"></i> {esc(inc.get('location'))} &nbsp;
                <i class="fas fa-user"></i> Reported by {esc(inc.get('reported_by'))} &nbsp;
                <i class="fas fa-clock"></i> {str(inc.get('created_at', ''))[:16]}<br>
                <p>{esc(inc.get('description'))}</p>
                {f"<p><i>Immediate action:</i> {esc(inc.get('immediate_action'))}</p>" if inc.get('immediate_action') else ""}
                {f"<p><i>Root cause:</i> {esc(inc.get('root_cause'))}</p>" if inc.get('root_cause') else ""}
                {f"<p><i>Corrective action:</i> {esc(inc.get('corrective_action'))}</p>" if inc.get('corrective_action') else ""}
            </div>
            """, unsafe_allow_html=True)
            if can_manage_incidents:
                with st.expander(f"⚙️ Investigate #{inc['id']}"):
                    new_status = st.selectbox("Status", ["Open", "Investigating", "Resolved", "Closed"],
                                               index=["Open", "Investigating", "Resolved", "Closed"].index(inc.get('status', 'Open')) if inc.get('status') in ["Open", "Investigating", "Resolved", "Closed"] else 0,
                                               key=f"inc_stat_{inc['id']}")
                    root_cause = st.text_area("Root Cause", value=inc.get('root_cause') or '', key=f"inc_root_{inc['id']}")
                    corrective_action = st.text_area("Corrective Action", value=inc.get('corrective_action') or '', key=f"inc_corr_{inc['id']}")
                    if st.button("💾 Save Investigation", key=f"inc_save_{inc['id']}"):
                        update_incident(inc['id'], {
                            "status": new_status,
                            "root_cause": root_cause,
                            "corrective_action": corrective_action
                        }, full_name)
                        st.success("Incident updated.")
                        st.rerun()

    elif inc_sub == "Report Incident":
        st.markdown("### Submit New Incident Report")
        st.caption("Report near-misses, injuries, and hazards as soon as possible. All Critical/High severity reports notify supervisors immediately.")
        with st.form("new_incident_form"):
            incident_type = st.selectbox("Incident Type", ["Near Miss", "Injury", "Property Damage", "Equipment Failure", "Environmental", "Hazard Observation", "Other"])
            severity = st.selectbox("Severity", ["Low", "Medium", "High", "Critical"])
            location = st.text_input("Location / Area *", max_chars=100)
            assets_list = st.session_state.get("assets", [])
            asset_options = ["None"] + [f"#{a['id']} {a['name']}" for a in assets_list]
            selected_asset = st.selectbox("Related Asset (optional)", asset_options)
            description = st.text_area("Description *", placeholder="What happened? Be specific.")
            immediate_action = st.text_area("Immediate Action Taken", placeholder="What was done right away?")
            witnesses = st.text_input("Witnesses (optional)", max_chars=200)
            submitted = st.form_submit_button("🚨 Submit Report")
            if submitted:
                if location and description:
                    asset_id = None
                    if selected_asset != "None":
                        asset_id = int(selected_asset.split(" ")[0].replace("#", ""))
                    new_incident = create_incident(incident_type, severity, location, description, full_name,
                                                    asset_id=asset_id, witnesses=witnesses, immediate_action=immediate_action)
                    if new_incident:
                        st.success("Incident reported. Thank you for keeping the site safe.")
                        if severity in ("Critical", "High"):
                            st.warning("This has been flagged for immediate supervisor attention.")
                        st.rerun()
                    else:
                        st.error("Failed to submit report.")
                else:
                    st.error("Location and Description are required.")

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
                accept_permit(p['id'], full_name)
                st.success("Permit accepted. You are now the responsible person.")
                st.rerun()
        if status == "Active" and can(role, "permit.sign_back"):
            if acols[1].button("✅ Sign Back", key=f"permit_sb_{p['id']}"):
                sign_back_permit(p['id'], full_name)
                st.success("Permit signed back and closed.")
                st.rerun()
        if status in ("Issued", "Active") and can(role, "permit.cancel"):
            if acols[2].button("🚫 Cancel", key=f"permit_can_{p['id']}"):
                cancel_permit(p['id'], full_name)
                st.rerun()

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
                with st.form("issue_permit_form"):
                    task_map = {f"#{t['id']} {t['title']}": t['id'] for t in open_tasks}
                    sel_task = st.selectbox("Task requiring the permit *", list(task_map.keys()))
                    permit_type = st.selectbox("Permit Type", [
                        "General Work Permit", "LOTO / Isolation", "Hot Work", "Confined Space",
                        "Working at Height", "Excavation", "Electrical Isolation", "Live Line"])
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
            st.markdown(f"""
            <div class="custom-card" style="border-left-color: {'#dc2626' if has_safety else '#0f3460'};">
                <strong>{esc(h.get('shift'))} — {esc(h.get('crew') or 'No crew')}</strong> {ack_badge}<br>
                <small><i class="fas fa-sign-out-alt"></i> Out: {esc(h.get('outgoing_supervisor'))}
                &nbsp;<i class="fas fa-sign-in-alt"></i> In: {esc(h.get('incoming_supervisor') or 'TBA')}
                &nbsp;<i class="fas fa-clock"></i> {str(h.get('created_at',''))[:16]}</small>
                <p><b>Completed:</b> {esc(h.get('work_completed') or '—')}</p>
                <p><b>Outstanding:</b> {esc(h.get('work_outstanding') or '—')}</p>
                {f"<p style='color:#dc2626;'><b>⚠️ Safety concerns:</b> {esc(h.get('safety_concerns'))}</p>" if has_safety else ""}
                <p><b>Equipment status:</b> {esc(h.get('equipment_status') or '—')}</p>
                {f"<small>Acknowledged by {esc(h.get('acknowledged_by'))} at {str(h.get('acknowledged_at',''))[:16]}</small>" if h.get('acknowledged') else ""}
            </div>
            """, unsafe_allow_html=True)
            if not h.get('acknowledged') and can(role, "handover.acknowledge"):
                if st.button("✅ Acknowledge Handover", key=f"ack_ho_{h['id']}"):
                    acknowledge_handover(h['id'], full_name)
                    st.success("Handover acknowledged.")
                    st.rerun()

    elif handover_sub == "New Handover":
        if require(role, "handover.create"):
            st.markdown("### Log Shift Handover")
            all_users_ho = fetch_all_users_from_db()
            supervisor_names = [u['full_name'] for u in all_users_ho
                                if u['role'].strip().lower() in ('supervisor', 'superintendent')
                                and u.get('is_approved') and u['full_name'] != full_name]
            with st.form("handover_form"):
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
                            update_contractor(c['id'], {
                                "induction_expiry": new_ind.isoformat(),
                                "insurance_expiry": new_ins.isoformat(),
                            }, full_name)
                            st.success("Contractor updated.")
                            st.rerun()

        elif contractor_sub == "Add Contractor":
            if require(role, "contractor.manage"):
                with st.form("contractor_form"):
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
        options=["Access Requests", "Active Users", "Decision History", "Settings"],
        icons=["person-plus-fill", "people-fill", "journal-text", "sliders"],
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
                        _b1, _b2 = st.columns(2)
                        if _b1.button("✅ Approve", key=f"appr_{u['username']}",
                                      use_container_width=True):
                            ok, err = approve_access(u['username'], _grant, full_name, _note or None)
                            if ok:
                                st.success(f"{u.get('full_name')} approved as {_grant}.")
                                st.rerun()
                            else:
                                st.error(err)
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
                                    st.error(err)

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
                    f"</small>", unsafe_allow_html=True)
                if u.get("denial_reason"):
                    st.caption(f"Reason on file: {esc(u['denial_reason'])}")

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
                            st.error(err)

                    _sc1, _sc2 = st.columns(2)
                    if _suspended:
                        if _sc1.button("♻️ Reinstate", key=f"reinst_{u['username']}",
                                       use_container_width=True):
                            ok, err = set_user_suspended(u['username'], False, full_name, _reason or None)
                            if ok:
                                st.success("Reinstated.")
                                st.rerun()
                            else:
                                st.error(err)
                    else:
                        if _sc1.button("⏸️ Suspend", key=f"susp_{u['username']}",
                                       use_container_width=True):
                            ok, err = set_user_suspended(u['username'], True, full_name, _reason or None)
                            if ok:
                                st.success("Suspended. They can no longer sign in.")
                                st.rerun()
                            else:
                                st.error(err)
                    _confirm = _sc2.checkbox("I understand this is permanent",
                                             key=f"delok_{u['username']}")
                    if _sc2.button("🗑️ Remove permanently", key=f"del_{u['username']}",
                                   use_container_width=True, disabled=not _confirm):
                        ok, err = remove_user(u['username'], full_name, _reason or None)
                        if ok:
                            st.success("User removed.")
                            st.rerun()
                        else:
                            st.error(err)
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
                      "reinstated": "♻️", "role_changed": "🔄", "removed": "🗑️"}
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

    # ---------- SETTINGS ----------
    elif owner_sub == "Settings":
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

elif selected_section == "Chat":
    st.subheader("💬 Real‑time Chat")

    room = st.session_state.chat_room
    if room == "global":
        st.markdown("### 🌍 Global Chat – all users")
    elif room == "supervisor":
        if not can(role, "chat.supervisor_room"):
            st.error("You don't have permission to view the Supervisor room.")
            st.stop()
        st.markdown("### 🔒 Supervisor Room – Supervisors & Superintendent only")
    elif room.startswith("private:"):
        partner = st.session_state.chat_partner
        st.markdown(f"### 💬 Private Chat with **{partner}**")
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
        for msg in reversed(messages):
            sender = msg['sender']
            is_encrypted = msg.get('is_encrypted', False)
            content = msg['message']
            if 'created_at' in msg and isinstance(msg['created_at'], str):
                try:
                    timestamp = datetime.fromisoformat(msg['created_at'].replace('Z', '+00:00')).strftime("%H:%M")
                except:
                    timestamp = "??:??"
            else:
                timestamp = "??:??"

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
                    st.markdown(f"<div class='chat-message self'><span class='sender'>You</span> <span class='timestamp'>{timestamp}</span><br>{esc(content)}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='chat-message'><span class='sender'>{esc(sender)}</span> <span class='timestamp'>{timestamp}</span><br>{esc(content)}</div>", unsafe_allow_html=True)
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
        st.info("No messages yet. Be the first to send!")

    with st.container():
        st.markdown("---")
        msg_input = st.text_area("Type your message", height=100, key="chat_input_text", value=st.session_state.chat_input_value)
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

# ---- ADMIN PANEL ----
elif selected_section == "Admin":
    if not can(role, "audit.view"):
        st.warning("You do not have admin privileges.")
    else:
        st.subheader("⚙️ Admin Panel")
        st.markdown("### Manage Users")
        all_users = fetch_all_users_from_db()
        if all_users:
            user_data = []
            for u in all_users:
                user_data.append({
                    "Username": u.get("username"),
                    "Full Name": u.get("full_name"),
                    "Role": u.get("role"),
                    "Email": u.get("email", "Not set"),
                    "Approved": u.get("is_approved", False)
                })
            st.dataframe(user_data, use_container_width=True)
        else:
            st.info("No users found in database.")

        if SUPABASE_AVAILABLE:
            st.markdown("### Audit Log (last 50)")
            try:
                logs = supabase.table("audit_log").select("*").order("created_at", desc=True).limit(50).execute()
                if logs.data:
                    for log in logs.data:
                        st.write(f"**{log['user_name']}** – {log['action']} at {log['created_at']}")
                        if log['details']:
                            st.caption(f"Details: {log['details']}")
                else:
                    st.info("No audit logs yet.")
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
                for act in activities.data:
                    task = supabase.table("tasks").select("title").eq("id", act['task_id']).execute()
                    task_title = task.data[0]['title'] if task.data else f"Task #{act['task_id']}"
                    st.write(f"**{act['user_name']}** {act['action']} **{task_title}** at {act['created_at']}")
                    if act['details']:
                        st.caption(f"Details: {act['details']}")
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
