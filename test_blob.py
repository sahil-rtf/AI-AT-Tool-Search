"""
test_blob.py
-------------
Quick sanity-check for Vercel Blob read/write.
Run from the LearnAndTry root:
    python test_blob.py
"""
import os, sys
from pathlib import Path

# Load .env
env_path = Path(__file__).parent / "ToolsDiscovery" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# Add api/ to path so _blob imports work
sys.path.insert(0, str(Path(__file__).parent / "ToolsDiscovery" / "ui" / "api"))

from _blob import read_blob, write_blob, _token, _use_blob

token = _token()
print(f"BLOB_READ_WRITE_TOKEN present: {bool(token)}")
print(f"Token prefix: {token[:30]}..." if token else "  (not set)")
print(f"Using blob API: {_use_blob()}")
print()

if not _use_blob():
    print("BLOB_READ_WRITE_TOKEN not set — using local fallback, no remote test.")
    sys.exit(0)

TEST_FILE = "_test_blob.json"
TEST_DATA = {"hello": "world", "test": True}

print(f"Writing {TEST_FILE}...")
ok = write_blob(TEST_FILE, TEST_DATA)
print(f"  write_blob returned: {ok}")
print()

if ok:
    print(f"Reading {TEST_FILE}...")
    result = read_blob(TEST_FILE)
    print(f"  read_blob returned: {result}")
    if result == TEST_DATA:
        print("\n  BLOB READ/WRITE WORKS CORRECTLY")
    else:
        print(f"\n  MISMATCH — expected {TEST_DATA}, got {result}")
else:
    print("  Write failed — check stderr output above for details.")
