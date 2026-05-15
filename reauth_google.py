"""
reauth_google.py
-----------------
Runs the full Google OAuth 2.0 flow in your browser.
You need credentials.json (downloaded from Google Cloud Console) in the
same folder as this script OR in ToolsDiscovery/.

After you log in, it saves token.json and prints the new TOKEN_JSON_B64
value to paste into .env and Vercel.

Usage:
    1. Place credentials.json next to this file  (or in ToolsDiscovery/)
    2. python reauth_google.py
    3. Copy the printed TOKEN_JSON_B64 value
    4. Paste into ToolsDiscovery/.env  →  TOKEN_JSON_B64=<value>
    5. Paste into Vercel Settings → Environment Variables → TOKEN_JSON_B64
"""

import base64
import json
import sys
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Locate credentials.json
creds_path = None
for candidate in [
    Path(__file__).parent / "credentials.json",
    Path(__file__).parent / "ToolsDiscovery" / "credentials.json",
    Path(__file__).parent / "ToolsDiscovery" / "ui" / "credentials.json",
]:
    if candidate.exists():
        creds_path = candidate
        break

if creds_path is None:
    print("ERROR: credentials.json not found.")
    print("")
    print("Steps to get it:")
    print("  1. Go to https://console.cloud.google.com/apis/credentials")
    print("  2. Select your project (or create one)")
    print("  3. Click 'Create Credentials' → 'OAuth client ID'")
    print("  4. Application type: Desktop app")
    print("  5. Download the JSON → rename it credentials.json")
    print(f"  6. Place it at: {Path(__file__).parent / 'credentials.json'}")
    sys.exit(1)

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("ERROR: google-auth-oauthlib not installed.")
    print("Run:  pip install google-auth-oauthlib")
    sys.exit(1)

print(f"Using credentials from: {creds_path}")
print("Opening browser for Google login…")

flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
creds = flow.run_local_server(port=0)

token_path = Path(__file__).parent / "token.json"
token_path.write_text(creds.to_json(), encoding="utf-8")
print(f"token.json saved to: {token_path}")

encoded = base64.b64encode(token_path.read_bytes()).decode("utf-8")

print("\n" + "=" * 60)
print("NEW TOKEN_JSON_B64 (copy the line below):")
print("=" * 60)
print(encoded)
print("=" * 60)
print("\n1. Update ToolsDiscovery/.env  →  TOKEN_JSON_B64=<value above>")
print("2. Update Vercel dashboard     →  Settings → Environment Variables → TOKEN_JSON_B64")
print("   (Make sure to redeploy after updating Vercel env vars)")
