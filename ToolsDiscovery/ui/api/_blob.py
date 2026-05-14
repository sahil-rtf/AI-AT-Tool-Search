"""
api/_blob.py
-------------
Reads and writes JSON blobs via the Vercel Blob REST API.
Falls back to local files when BLOB_READ_WRITE_TOKEN is not set (local dev).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests

_LOCAL_FALLBACK_DIR = Path(__file__).parent.parent / ".blob_store"
_BLOB_API = "https://blob.vercel-storage.com"


def _token() -> str:
    return os.getenv("BLOB_READ_WRITE_TOKEN", "")


def _use_blob() -> bool:
    return bool(_token())


def read_blob(filename: str) -> list | dict | None:
    if not _use_blob():
        _LOCAL_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
        path = _LOCAL_FALLBACK_DIR / filename
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    try:
        headers = {"Authorization": f"Bearer {_token()}"}
        # List blobs with exact prefix to find ours
        resp = requests.get(
            _BLOB_API,
            params={"prefix": filename, "limit": 10},
            headers=headers,
            timeout=15,
        )
        if not resp.ok:
            return None
        blobs = resp.json().get("blobs", [])
        match = next((b for b in blobs if b.get("pathname") == filename), None)
        if not match:
            return None
        # Fetch the actual JSON content from the public URL
        content_resp = requests.get(match["url"], timeout=15)
        if content_resp.ok:
            return content_resp.json()
        return None
    except Exception:
        return None


def write_blob(filename: str, data: list | dict) -> bool:
    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    if not _use_blob():
        _LOCAL_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
        (_LOCAL_FALLBACK_DIR / filename).write_bytes(content)
        return True

    try:
        headers = {
            "Authorization": f"Bearer {_token()}",
            "content-type": "application/json",
            "x-add-random-suffix": "0",   # keep the same URL on every write
            "x-cache-control-max-age": "0",
        }
        resp = requests.put(
            f"{_BLOB_API}/{filename}",
            data=content,
            headers=headers,
            timeout=15,
        )
        return resp.ok
    except Exception:
        return False
