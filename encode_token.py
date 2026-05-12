"""
encode_token.py
----------------
One-time helper: reads token.json and prints the base64-encoded value
to paste into Vercel as the TOKEN_JSON_B64 environment variable.

Usage:
    python encode_token.py
"""

import base64
import json
from pathlib import Path

token_path = Path(__file__).parent / "ToolsDiscovery" / "token.json"
if not token_path.exists():
    token_path = Path("token.json")

if not token_path.exists():
    print("ERROR: token.json not found. Run the pipeline locally once to generate it.")
else:
    raw = token_path.read_bytes()
    encoded = base64.b64encode(raw).decode("utf-8")
    print("Copy the value below and add it as TOKEN_JSON_B64 in Vercel → Settings → Environment Variables:\n")
    print(encoded)
