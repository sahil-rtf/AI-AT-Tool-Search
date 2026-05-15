"""
setup_service_account.py
-------------------------
One-time helper: reads a Google service account JSON key file and prints
the base64-encoded value to paste into .env and Vercel as SERVICE_ACCOUNT_B64.

A service account key NEVER expires and needs no browser login — it is the
permanent replacement for OAuth user tokens that expire every 7 days.

═══════════════════════════════════════════════════════════════════════════════
  NOTE FOR WHOEVER IS MAINTAINING THIS AFTER THE ORIGINAL DEVELOPER LEAVES
═══════════════════════════════════════════════════════════════════════════════
  The service account key was created in a PERSONAL Google Cloud project.
  As long as that GCP project is not deleted, the key keeps working.

  When you eventually need to rotate or replace credentials (e.g. the original
  developer deletes their GCP project), do the following:

    1. Create a NEW GCP project at https://console.cloud.google.com
       (use a company Google account this time, if you have one)
    2. Enable the Google Sheets API on the new project
    3. Follow STEP 1 below to create a new service account
    4. Follow STEP 2 to share the spreadsheet with the new service account email
    5. Run this script, get the new SERVICE_ACCOUNT_B64, update .env + Vercel
    6. Redeploy

  That's the full handoff. No other credentials, tokens, or secrets are needed.
═══════════════════════════════════════════════════════════════════════════════

─────────────────────────────────────────────────────────────────────────────
STEP 1 — Create a service account in YOUR Google Cloud Console (one time)
─────────────────────────────────────────────────────────────────────────────
1. Go to https://console.cloud.google.com/iam-admin/serviceaccounts
   (You will land in your PERSONAL Google Cloud project — that is correct)
2. Click  "+ CREATE SERVICE ACCOUNT"
3. Name:  at-tool-search-bot  →  click CREATE AND CONTINUE
4. Skip the optional role step  →  click DONE
5. Click the new service account row  →  open the "KEYS" tab
6. Click  "ADD KEY"  →  "Create new key"  →  JSON  →  CREATE
   (A JSON file downloads automatically)
7. Save that file as  service_account.json  next to this script:
      C:/Users/proto/LearnAndTry/service_account.json

─────────────────────────────────────────────────────────────────────────────
STEP 2 — Share the Google Sheet with the service account
─────────────────────────────────────────────────────────────────────────────
After running this script (below), it prints a  client_email  like:
    at-tool-search-bot@your-project.iam.gserviceaccount.com

Open your Google Spreadsheet → Share → paste that email → Editor → Send.
If the sheet is in a company Google Workspace, ask an admin to share it or
use a shared account to do the sharing step.

─────────────────────────────────────────────────────────────────────────────
STEP 3 — Run this script
─────────────────────────────────────────────────────────────────────────────
    python setup_service_account.py

─────────────────────────────────────────────────────────────────────────────
STEP 4 — Update env vars (two places)
─────────────────────────────────────────────────────────────────────────────
  • ToolsDiscovery/.env       →  SERVICE_ACCOUNT_B64=<printed value>
  • Vercel Settings → Env Vars →  SERVICE_ACCOUNT_B64=<printed value>
    (Environment: Production + Preview + Development)
    Redeploy after saving in Vercel.

  Once confirmed working you can delete TOKEN_JSON_B64 from both places.

─────────────────────────────────────────────────────────────────────────────
HANDOFF CHECKLIST (fill this in before you leave)
─────────────────────────────────────────────────────────────────────────────
  [ ] service_account.json is saved somewhere secure (NOT committed to git)
  [ ] SERVICE_ACCOUNT_B64 is set in Vercel environment variables
  [ ] Google Sheet is shared with the service account email as Editor
  [ ] GCP project name / ID is documented below for the next maintainer:

  GCP project name : _______________________________________________
  GCP project ID   : _______________________________________________
  Service acct email: _______________________________________________
  Vercel project URL: https://vercel.com/____________/ai-at-tool-search
  Google Sheet URL  : https://docs.google.com/spreadsheets/d/____________
"""

import base64
import json
import sys
from pathlib import Path

# ── Locate service_account.json ───────────────────────────────────────────────
sa_path = None
for candidate in [
    Path(__file__).parent / "service_account.json",
    Path(__file__).parent / "ToolsDiscovery" / "service_account.json",
]:
    if candidate.exists():
        sa_path = candidate
        break

if sa_path is None:
    print("ERROR: service_account.json not found.")
    print("       Follow STEP 1 in the docstring above, then save the downloaded file as:")
    print(f"       {Path(__file__).parent / 'service_account.json'}")
    sys.exit(1)

sa_data = json.loads(sa_path.read_text(encoding="utf-8"))
client_email = sa_data.get("client_email", "unknown")
project_id   = sa_data.get("project_id",   "unknown")

print()
print(f"  GCP project ID      : {project_id}")
print(f"  Service acct email  : {client_email}")
print()
print("  ▶  Share your Google Spreadsheet with the email above (Editor access)")
print()

encoded = base64.b64encode(sa_path.read_bytes()).decode("utf-8")

print("=" * 64)
print("SERVICE_ACCOUNT_B64  (copy the value on the next line):")
print("=" * 64)
print(encoded)
print("=" * 64)
print()
print("1. Add to  ToolsDiscovery/.env:")
print("   SERVICE_ACCOUNT_B64=" + encoded[:40] + "…")
print()
print("2. Add to Vercel → Settings → Environment Variables:")
print("   Name:   SERVICE_ACCOUNT_B64")
print("   Value:  <full value above>")
print("   Env:    Production + Preview + Development")
print("   → Save → Redeploy")
print()
print("3. (Optional) Remove TOKEN_JSON_B64 once confirmed working.")
print()
print("─" * 64)
print("  Fill in the HANDOFF CHECKLIST at the top of this file")
print("  before you leave so the next person can take over easily.")
print("─" * 64)
