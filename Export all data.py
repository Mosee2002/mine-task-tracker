#!/usr/bin/env python3
"""
MWDTS — Standalone Emergency Data Export
==========================================

Pulls every table out of Supabase directly, with no dependency on
Streamlit at all — not the Streamlit app, not Streamlit Cloud, not
even the `streamlit` Python package. If the app's website is ever
unreachable for any reason, this still works, because it talks
straight to Supabase's own REST API (the same database the app itself
uses, completely independent of the site that displays it).

WHY THIS EXISTS
---------------
The actual data was never inside Streamlit to begin with — it lives in
Supabase (PostgreSQL), a separate service. Streamlit Cloud going down
would take the *website* offline, not the data. This script exists so
that fact is something you can actually use, not just something true
in theory: a real, tested way to get every record out, runnable from
any machine with Python installed, with the app's UI completely out
of the picture.

REQUIREMENTS
------------
- Python 3.7+ (nothing else needs to be installed beyond the
  standard library plus the `requests` package, which is about as
  close to universally available as Python packages get:
      pip install requests

SETUP
-----
Set two environment variables before running (never hardcode these
directly into this file, and never commit them anywhere):

    export SUPABASE_URL="https://YOUR-PROJECT-REF.supabase.co"
    export SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"

This deliberately uses the service_role key, NOT the anon key the app
itself uses day to day — a real backup needs to see every row
regardless of Row Level Security policies, which is exactly what that
key is for. Treat it with the same care as a root password: this
script should live somewhere private, and the key should never be
shared or committed to version control.

USAGE
-----
    python3 export_all_data.py

Produces a timestamped folder (e.g. backup_2026-08-03_143022/)
containing one CSV and one JSON file per table, plus a summary report.
CSV for anyone who just needs to open something in Excel and see their
data; JSON as the more complete, lossless copy, in case data ever
needs to be reconstructed or migrated programmatically later.
"""

import os
import sys
import json
import csv
import time
from datetime import datetime

try:
    import requests
except ImportError:
    print("This script needs the 'requests' package. Install it with:")
    print("    pip install requests")
    sys.exit(1)


# Every table this app actually uses, pulled directly from the real
# codebase rather than reconstructed from memory — see the project's
# own table list for how this was verified.
ALL_TABLES = [
    "facility_users", "access_decisions",
    "tasks", "task_activity", "task_comments", "task_photos", "task_attachments", "task_parts",
    "assets", "meter_readings", "inventory_parts",
    "incidents", "permits", "shift_handovers", "contractors",
    "chat_messages", "notifications",
    "app_feedback", "app_feedback_votes",
    "app_branding", "app_announcements", "app_posters", "app_feature_flags",
    "app_errors", "audit_log",
]

PAGE_SIZE = 1000  # Supabase's REST API caps a single response — this
                   # script pages through every table fully rather
                   # than silently stopping at the first 1000 rows,
                   # which matters for anything that grows over time
                   # (audit_log, chat_messages, task_activity).


def get_config():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("Missing required environment variables.\n")
        print("Set these before running:")
        print('    export SUPABASE_URL="https://YOUR-PROJECT-REF.supabase.co"')
        print('    export SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"')
        print("\nFind both in Supabase Dashboard -> Project Settings -> API.")
        sys.exit(1)
    return url, key


def fetch_table(base_url, key, table_name):
    """Fetches every row from one table, paging through the full
    result set rather than trusting a single request to return
    everything. Returns (rows, error) — error is None on success, so
    a failure on one table can be reported clearly without crashing
    the whole export or silently skipping it."""
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    all_rows = []
    offset = 0
    while True:
        headers["Range"] = f"{offset}-{offset + PAGE_SIZE - 1}"
        try:
            resp = requests.get(
                f"{base_url}/rest/v1/{table_name}",
                headers=headers,
                params={"select": "*", "order": "id.asc" if table_name != "audit_log" else "created_at.asc"},
                timeout=30,
            )
        except requests.RequestException as e:
            return all_rows, f"Network error: {e}"

        if resp.status_code not in (200, 206):
            return all_rows, f"HTTP {resp.status_code}: {resp.text[:200]}"

        page = resp.json()
        all_rows.extend(page)

        if len(page) < PAGE_SIZE:
            break  # last page
        offset += PAGE_SIZE
        time.sleep(0.1)  # be polite to the API rather than hammer it

    return all_rows, None


def write_csv(rows, path):
    if not rows:
        with open(path, "w") as f:
            f.write("")  # empty table -> empty file, not an error
        return
    # Collect the full set of columns across all rows — different rows
    # can have different keys present (nullable fields), and a naive
    # first-row-only column list would silently drop data.
    fieldnames = []
    seen = set()
    for row in rows:
        for k in row.keys():
            if k not in seen:
                seen.add(k)
                fieldnames.append(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            # Flatten anything that isn't a plain scalar (nested JSON
            # columns, arrays) into a string, so it round-trips
            # cleanly through CSV instead of breaking the format.
            flat = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in row.items()}
            writer.writerow(flat)


def write_json(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, default=str)


def main():
    base_url, key = get_config()

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_dir = f"backup_{timestamp}"
    os.makedirs(out_dir, exist_ok=True)

    print(f"MWDTS Data Export — {timestamp}")
    print(f"Output folder: {out_dir}/\n")

    results = []
    for table in ALL_TABLES:
        print(f"  {table:24}", end="", flush=True)
        rows, error = fetch_table(base_url, key, table)
        if error:
            print(f"FAILED — {error}")
            results.append((table, 0, error))
            continue

        write_csv(rows, os.path.join(out_dir, f"{table}.csv"))
        write_json(rows, os.path.join(out_dir, f"{table}.json"))
        print(f"{len(rows)} rows")
        results.append((table, len(rows), None))

    # Summary report — written to disk too, not just printed, so the
    # backup folder itself documents what happened even if this
    # terminal output is long gone by the time anyone looks at it.
    summary_path = os.path.join(out_dir, "_SUMMARY.txt")
    with open(summary_path, "w") as f:
        f.write(f"MWDTS Data Export Summary\nRun at: {timestamp}\n\n")
        total_rows = 0
        failed = []
        for table, count, error in results:
            if error:
                f.write(f"  FAILED   {table:24} — {error}\n")
                failed.append(table)
            else:
                f.write(f"  OK       {table:24} {count:>8} rows\n")
                total_rows += count
        f.write(f"\nTotal rows exported: {total_rows}\n")
        if failed:
            f.write(f"Tables that FAILED and need attention: {', '.join(failed)}\n")
        else:
            f.write("All tables exported successfully.\n")

    print(f"\nDone. Summary written to {summary_path}")
    failed_count = sum(1 for _, _, e in results if e)
    if failed_count:
        print(f"\n⚠ {failed_count} table(s) failed — see {summary_path} for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
