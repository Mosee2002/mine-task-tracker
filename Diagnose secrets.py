#!/usr/bin/env python3
"""
Diagnose why .streamlit/secrets.toml isn't being picked up.

Run it from the SAME directory where you run `streamlit run app.py`:

    python3 diagnose_secrets.py

It prints exactly what's wrong. It never prints your actual secret values.
"""
import os
import sys
import json
import base64
from pathlib import Path

OK, WARN, BAD, INFO = "  [OK]  ", "  [WARN]", "  [FAIL]", "  [info]"
issues = []


def hr(title):
    print("\n" + "=" * 62)
    print(title)
    print("=" * 62)


hr("1. WHERE AM I?")
cwd = Path.cwd()
print(f"{INFO} Current directory: {cwd}")
print(f"{INFO} Streamlit looks for: {cwd / '.streamlit' / 'secrets.toml'}")
print()
print("     If you launch streamlit from a DIFFERENT directory than this,")
print("     it will not find the file. That is the #1 cause.")

app_here = (cwd / "app.py").exists()
print(f"{OK if app_here else WARN} app.py in this directory: {app_here}")
if not app_here:
    found = list(cwd.rglob("app.py"))[:5]
    if found:
        print(f"{INFO} app.py found elsewhere:")
        for f in found:
            print(f"          {f}")
        print("     -> cd to that directory and re-run this script.")
    issues.append("Running from a directory with no app.py")

hr("2. DOES THE FILE EXIST?")
sdir = cwd / ".streamlit"
sfile = sdir / "secrets.toml"

if not sdir.exists():
    print(f"{BAD} .streamlit/ directory does NOT exist")
    print("     Fix:  mkdir -p .streamlit")
    issues.append(".streamlit/ directory missing")
else:
    print(f"{OK} .streamlit/ exists")
    contents = sorted(p.name for p in sdir.iterdir())
    print(f"{INFO} Contains: {contents or '(empty)'}")
    # Catch the classic typos
    for wrong in ("secret.toml", "secrets.TOML", "Secrets.toml", "secrets.tml", "secrets.toml.txt"):
        if (sdir / wrong).exists():
            print(f"{BAD} Found '{wrong}' — must be exactly 'secrets.toml'")
            print(f"     Fix:  mv .streamlit/{wrong} .streamlit/secrets.toml")
            issues.append(f"Misnamed file: {wrong}")

if not sfile.exists():
    print(f"{BAD} .streamlit/secrets.toml does NOT exist")
    issues.append("secrets.toml missing")
    print("\n" + "=" * 62)
    print("STOP: create the file first, then re-run this script.")
    print("=" * 62)
    sys.exit(1)

print(f"{OK} .streamlit/secrets.toml exists")
size = sfile.stat().st_size
print(f"{INFO} Size: {size} bytes")
if size == 0:
    print(f"{BAD} File is EMPTY")
    issues.append("secrets.toml is empty")

mode = oct(sfile.stat().st_mode)[-3:]
print(f"{OK if mode in ('600', '400') else WARN} Permissions: {mode}"
      f"{'' if mode in ('600','400') else '  (recommend: chmod 600)'}")

hr("3. IS THE TOML VALID?")
raw = sfile.read_text(encoding="utf-8", errors="replace")

if raw.startswith("\ufeff"):
    print(f"{BAD} File starts with a BOM (byte-order mark)")
    print("     Some editors add this. Re-save as 'UTF-8' not 'UTF-8 with BOM'.")
    issues.append("BOM at start of file")

data = None
try:
    try:
        import tomllib  # py3.11+
    except ImportError:
        import tomli as tomllib  # type: ignore
    data = tomllib.loads(raw.lstrip("\ufeff"))
    print(f"{OK} TOML parses correctly")
    print(f"{INFO} Keys found: {len(data)}")
except ModuleNotFoundError:
    print(f"{WARN} No tomllib/tomli available (Python < 3.11). Skipping parse check.")
except Exception as e:
    print(f"{BAD} TOML is INVALID: {e}")
    issues.append(f"TOML syntax error: {e}")
    print("\n     Most common causes:")
    print("       - value not in quotes:   SUPABASE_URL = https://...   (needs quotes)")
    print("       - smart/curly quotes from a word processor instead of \" \"")
    print("       - a trailing comma at the end of a line")
    print("       - the key pasted across multiple lines instead of one")

hr("4. ARE THE REQUIRED KEYS THERE?")
if data is None:
    print(f"{WARN} Skipped (TOML did not parse)")
else:
    for key in ("SUPABASE_URL", "SUPABASE_KEY"):
        if key in data:
            print(f"{OK} {key} present")
        else:
            print(f"{BAD} {key} MISSING — this is required")
            issues.append(f"{key} missing")

    url = data.get("SUPABASE_URL", "")
    if url:
        if not url.startswith("https://"):
            print(f"{BAD} SUPABASE_URL should start with https://")
            issues.append("SUPABASE_URL malformed")
        elif not url.endswith(".supabase.co"):
            print(f"{WARN} SUPABASE_URL doesn't end with .supabase.co (fine if self-hosted)")
        else:
            print(f"{OK} SUPABASE_URL format looks right")
        if url.rstrip("/") != url:
            print(f"{WARN} SUPABASE_URL has a trailing slash — remove it")

    hr("5. WHICH SUPABASE KEY IS IT?  (important)")
    key = data.get("SUPABASE_KEY", "")
    if not key:
        print(f"{WARN} No key to check")
    elif key.count(".") != 2:
        print(f"{BAD} SUPABASE_KEY is not a JWT (expected 3 dot-separated parts)")
        print(f"{INFO} Got {key.count('.') + 1} part(s), length {len(key)}")
        print("     Did you paste the Project URL or the password by mistake?")
        issues.append("SUPABASE_KEY is not a valid JWT")
    else:
        try:
            payload_b64 = key.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            role = payload.get("role", "unknown")
            if role == "anon":
                print(f"{OK} Key role is 'anon' — correct for this app")
            elif role == "service_role":
                print(f"{BAD} Key role is 'service_role' — DO NOT USE THIS")
                print("     service_role bypasses Row Level Security entirely.")
                print("     Replace it with the 'anon public' key immediately.")
                issues.append("Using service_role key (security risk)")
            else:
                print(f"{WARN} Unrecognised key role: {role}")

            import datetime as _dt
            if "exp" in payload:
                exp = _dt.datetime.fromtimestamp(payload["exp"])
                left = (exp - _dt.datetime.now()).days
                if left < 0:
                    print(f"{BAD} Key EXPIRED on {exp.date()}")
                    issues.append("Supabase key expired")
                else:
                    print(f"{OK} Key valid until {exp.date()} ({left} days)")
            ref = payload.get("ref")
            if ref and url and ref not in url:
                print(f"{BAD} Key belongs to project '{ref}' but URL points elsewhere")
                print("     The URL and key are from two different Supabase projects.")
                issues.append("URL/key project mismatch")
            elif ref:
                print(f"{OK} Key and URL are from the same project")
        except Exception as e:
            print(f"{WARN} Could not decode key payload: {e}")

    hr("6. OPTIONAL KEYS")
    optional = {
        "APP_URL": "password-reset links will point at a placeholder",
        "CHAT_KEY_SALT": "private chat uses the default public salt",
        "SESSION_TIMEOUT_MINUTES": "defaults to 60",
        "MAX_UPLOAD_SIZE_MB": "defaults to 5",
        "SLACK_WEBHOOK": "no Slack alerts",
        "TEAMS_WEBHOOK": "no Teams alerts",
        "SMTP_SERVER": "no email notifications",
        "GOOGLE_WORKSPACE_SA_JSON": "no mailbox auto-provisioning",
        "GOOGLE_WORKSPACE_ADMIN_EMAIL": "no mailbox auto-provisioning",
    }
    for k, consequence in optional.items():
        print(f"{OK if k in data else INFO} {k:26} {'set' if k in data else 'not set — ' + consequence}")

    hr("6B. OWNER_USERNAME  (important — not optional in practice)")
    if "OWNER_USERNAME" in data:
        print(f"{OK} OWNER_USERNAME is set")
    else:
        print(f"{BAD} OWNER_USERNAME is NOT set")
        print("     Without it, nobody can reach the Owner Console — access requests")
        print("     pile up with no one able to approve them. Set it to the exact")
        print("     username of the account that should be owner, then restart.")
        issues.append("OWNER_USERNAME not set")

    if isinstance(data.get("SMTP_PORT"), str):
        print(f"{WARN} SMTP_PORT is a string; use SMTP_PORT = 587 (no quotes)")

    for k in ("SESSION_TIMEOUT_MINUTES", "MAX_UPLOAD_SIZE_MB"):
        if isinstance(data.get(k), str):
            print(f"{WARN} {k} is a string; remove the quotes to make it a number")

    if data.get("CHAT_KEY_SALT") in ("set-a-long-random-value-here",
                                     "generate-your-own-see-below",
                                     "fixed_salt_for_demo"):
        print(f"{BAD} CHAT_KEY_SALT is still the placeholder value")
        issues.append("CHAT_KEY_SALT not changed from placeholder")

hr("7. IS IT GIT-IGNORED?")
if (cwd / ".git").exists():
    import subprocess
    try:
        r = subprocess.run(["git", "check-ignore", "-v", ".streamlit/secrets.toml"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            print(f"{OK} secrets.toml is git-ignored")
        else:
            print(f"{BAD} secrets.toml is NOT git-ignored — you could commit it")
            print("     Fix:  echo '.streamlit/secrets.toml' >> .gitignore")
            issues.append("secrets.toml not git-ignored")
        r2 = subprocess.run(["git", "log", "--oneline", "--", ".streamlit/secrets.toml"],
                            capture_output=True, text=True, timeout=5)
        if r2.stdout.strip():
            print(f"{BAD} secrets.toml EXISTS IN GIT HISTORY — rotate every key in it now")
            issues.append("secrets.toml was committed at some point")
    except Exception as e:
        print(f"{INFO} Could not run git checks: {e}")
else:
    print(f"{INFO} Not a git repository — skipping")

hr("8. THEME CONFIG")
cfg = sdir / "config.toml"
print(f"{OK if cfg.exists() else WARN} .streamlit/config.toml "
      f"{'exists' if cfg.exists() else 'MISSING — theme will look wrong until you add it'}")

hr("SUMMARY")
if not issues:
    print("  No problems found.\n")
    print("  If the app still shows the demo-mode banner, then streamlit is")
    print("  being launched from a different directory than this one.")
    print(f"  Launch it from here:  cd {cwd} && streamlit run app.py")
    print()
    print("  If you deploy on Streamlit Community Cloud, a local file is")
    print("  IGNORED — you must paste the TOML into:")
    print("     App -> Settings -> Secrets")
else:
    print(f"  {len(issues)} problem(s) found:\n")
    for i, p in enumerate(issues, 1):
        print(f"    {i}. {p}")
print()
