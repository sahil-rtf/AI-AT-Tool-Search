"""
refresh_token.py
-----------------
Decodes TOKEN_JSON_B64 from .env, forces a token refresh via Google OAuth,
then prints the new base64-encoded value to paste back into .env and Vercel.

Usage (from the LearnAndTry root):
    python refresh_token.py
"""

import base64
import json
import os
import sys
from pathlib import Path

# Load .env manually so we don't need python-dotenv installed globally
env_path = Path(__file__).parent / "ToolsDiscovery" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

token_b64 = os.environ.get("TOKEN_JSON_B64", "")
if not token_b64:
    print("ERROR: TOKEN_JSON_B64 not found in ToolsDiscovery/.env")
    sys.exit(1)

token_b64 = token_b64.strip()
token_b64 += "=" * (-len(token_b64) % 4)
token_data = json.loads(base64.b64decode(token_b64).decode("utf-8"))

print("Current token expiry:", token_data.get("expiry", "unknown"))
print("Attempting token refresh…")

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
except ImportError:
    print("ERROR: google-auth not installed. Run: pip install google-auth-oauthlib google-auth-httplib2")
    sys.exit(1)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_authorized_user_info(token_data, SCOPES)

if creds.valid:
    print("Token is still valid — no refresh needed.")
else:
    if not creds.refresh_token:
        print("ERROR: No refresh_token present. You must re-run the full OAuth flow.")
        print("       Run the original pipeline locally with credentials.json present.")
        sys.exit(1)
    try:
        creds.refresh(Request())
        print("Token refreshed successfully!")
    except Exception as exc:
        print(f"ERROR: Refresh failed: {exc}")
        print("The refresh_token may have been revoked. Re-run the OAuth flow locally.")
        sys.exit(1)

# Serialize refreshed credentials back to dict
refreshed = {
    "token":          creds.token,
    "refresh_token":  creds.refresh_token,
    "token_uri":      creds.token_uri,
    "client_id":      creds.client_id,
    "client_secret":  creds.client_secret,
    "scopes":         list(creds.scopes) if creds.scopes else [],
    "universe_domain": getattr(creds, "universe_domain", "googleapis.com"),
    "account":        "",
    "expiry":         creds.expiry.isoformat() + "Z" if creds.expiry else "",
}

new_b64 = base64.b64encode(json.dumps(refreshed, ensure_ascii=False).encode("utf-8")).decode("utf-8")

print("\n" + "=" * 60)
print("NEW TOKEN_JSON_B64 (copy the line below):")
print("=" * 60)
print(new_b64)
print("=" * 60)
print("\nUpdate ToolsDiscovery/.env  →  TOKEN_JSON_B64=<value above>")
print("Update Vercel dashboard     →  Settings → Environment Variables → TOKEN_JSON_B64")
