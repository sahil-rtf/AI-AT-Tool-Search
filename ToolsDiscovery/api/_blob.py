"""
api/_blob.py
-------------
Thin wrapper around Vercel Blob for reading/writing JSON data.
Falls back to local JSON files when BLOB_READ_WRITE_TOKEN is not set (local dev).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_LOCAL_FALLBACK_DIR = Path(__file__).parent.parent / "ToolsDiscovery" / ".blob_store"


def _use_blob() -> bool:
    return bool(os.getenv("BLOB_READ_WRITE_TOKEN"))


def read_blob(filename: str) -> list | dict | None:
    """Read a JSON blob. Returns None if not found."""
    if _use_blob():
        try:
            import vercel_blob  # type: ignore
            token = os.getenv("BLOB_READ_WRITE_TOKEN", "")
            blobs = vercel_blob.list({"token": token})
            for blob in blobs.get("blobs", []):
                if blob["pathname"] == filename:
                    import urllib.request
                    with urllib.request.urlopen(blob["url"]) as resp:
                        return json.loads(resp.read().decode("utf-8"))
            return None
        except Exception:
            return None
    else:
        _LOCAL_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
        path = _LOCAL_FALLBACK_DIR / filename
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None


def write_blob(filename: str, data: list | dict) -> bool:
    """Write a JSON blob. Returns True on success."""
    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    if _use_blob():
        try:
            import vercel_blob  # type: ignore
            token = os.getenv("BLOB_READ_WRITE_TOKEN", "")
            vercel_blob.put(filename, content, {"access": "public", "token": token, "addRandomSuffix": False})
            return True
        except Exception:
            return False
    else:
        _LOCAL_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
        (_LOCAL_FALLBACK_DIR / filename).write_bytes(content)
        return True
