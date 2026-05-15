"""
api/_blob.py
-------------
Reads and writes JSON blobs via the Vercel Blob REST API.
Falls back to local files when BLOB_READ_WRITE_TOKEN is not set (local dev).

Header/URL reference (from Vercel Blob TypeScript SDK source):
  - PUT  https://blob.vercel-storage.com/?pathname=<name>
  - Access header name is  x-vercel-blob-access  (NOT 'access')
  - List  GET https://blob.vercel-storage.com  with ?prefix=&limit=
  - Private blobs: use downloadUrl + auth header for content fetch
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

_LOCAL_FALLBACK_DIR = Path(__file__).parent.parent / ".blob_store"
_BLOB_API = "https://blob.vercel-storage.com"


def _token() -> str:
    return os.getenv("BLOB_READ_WRITE_TOKEN", "")


def _use_blob() -> bool:
    return bool(_token())


def _log_err(msg: str) -> None:
    print(f"[blob] {msg}", file=sys.stderr, flush=True)


def read_blob(filename: str) -> list | dict | None:
    if not _use_blob():
        _LOCAL_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
        path = _LOCAL_FALLBACK_DIR / filename
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    try:
        auth_headers = {"Authorization": f"Bearer {_token()}"}

        resp = requests.get(
            _BLOB_API,
            params={"prefix": filename, "limit": 10},
            headers=auth_headers,
            timeout=15,
        )
        if not resp.ok:
            _log_err(f"list failed {resp.status_code}: {resp.text[:200]}")
            return None

        blobs = resp.json().get("blobs", [])
        match = next((b for b in blobs if b.get("pathname") == filename), None)
        if not match:
            return None

        # Private blobs: use downloadUrl (requires auth), public blobs use url
        fetch_url = match.get("downloadUrl") or match.get("url")
        content_resp = requests.get(fetch_url, headers=auth_headers, timeout=15)
        if content_resp.ok:
            return content_resp.json()
        _log_err(f"fetch content failed {content_resp.status_code}: {content_resp.text[:200]}")
        return None
    except Exception as exc:
        _log_err(f"read_blob exception: {exc}")
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
            # Correct header name per Vercel Blob SDK source (put-helpers.ts):
            #   putOptionHeaderMap.access = 'x-vercel-blob-access'
            "x-vercel-blob-access": "private",
            "content-type": "application/json",
            "x-add-random-suffix": "0",
            "x-cache-control-max-age": "0",
        }
        # PUT URL: pathname goes in the URL path, not as a query param
        resp = requests.put(
            f"{_BLOB_API}/{filename}",
            data=content,
            headers=headers,
            timeout=15,
        )
        if not resp.ok:
            _log_err(f"write_blob PUT failed {resp.status_code}: {resp.text[:300]}")
            return False
        return True
    except Exception as exc:
        _log_err(f"write_blob exception: {exc}")
        return False
