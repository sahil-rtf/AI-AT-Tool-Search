"""
api/run.py
-----------
POST /api/run  — starts the pipeline and streams log lines as SSE.

Vercel routes this as a Python serverless function at /api/run.
The function streams the entire pipeline synchronously.
maxDuration is set to 800s in vercel.json.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# Allow importing pipeline modules and _blob from the project root
_BASE_DIR = Path(__file__).parent.parent   # /var/task  (= ToolsDiscovery/ root)
_API_DIR  = Path(__file__).parent           # /var/task/api
for _p in (_BASE_DIR, _API_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from pipeline import step1_load_sheets, step2_gemini_search, step3_second_pass
from pipeline import step4_url_checker, step5_third_pass, step6_push_to_sheets
from _blob import read_blob, write_blob

INTERMEDIATE_FILES = [
    "new_tools.csv", "new_tools_filtered.csv", "new_tools_final.csv",
    "new_tools_with_validation.csv", "new_tools_complete.csv",
]

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            config = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            config = {}

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc).isoformat()
        logs: list[str] = []
        tools_found = 0

        def send(msg: str):
            logs.append(msg)
            try:
                self.wfile.write(f"data: {msg}\n\n".encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Copy static assets needed by the pipeline
            src = Path(__file__).parent.parent / "ToolsDiscovery"
            for fname in ["active_tools.csv", "removed_tools.csv"]:
                src_file = src / fname
                if src_file.exists():
                    (base_dir / fname).write_bytes(src_file.read_bytes())

            send("STATUS:running")

            steps = [
                (step1_load_sheets, "Load Google Sheets database"),
                (step2_gemini_search, "Gemini AI web search"),
                (step3_second_pass, "Verify categories & descriptions"),
                (step4_url_checker, "Check website URLs"),
                (step5_third_pass, "Fill missing data fields"),
                (step6_push_to_sheets, "Score & push to AI_LEADS"),
            ]

            success = True
            for i, (step_mod, label) in enumerate(steps, start=1):
                send(f"\n{'─'*50}")
                send(f"  Step {i}  |  {label}")
                send(f"{'─'*50}")
                ok = step_mod.run(config, send, base_dir)
                if not ok:
                    send(f"[ERROR] Step {i} failed. Pipeline aborted.")
                    send("STATUS:error")
                    success = False
                    break

            if success:
                # Clean up intermediate files
                send(f"\n{'─'*50}")
                send("  Step 7  |  Cleaning up intermediate files")
                send(f"{'─'*50}")
                removed = []
                for fname in INTERMEDIATE_FILES:
                    fp = base_dir / fname
                    if fp.exists():
                        fp.unlink()
                        removed.append(fname)
                if removed:
                    send(f"  Removed: {', '.join(removed)}")

                # Count discovered tools
                import csv as _csv
                leads_preview = base_dir / "ai_leads_preview.csv"
                if leads_preview.exists():
                    with open(leads_preview, newline="", encoding="utf-8") as f:
                        tools_found = sum(1 for _ in _csv.reader(f)) - 1

                sheet_url = (
                    f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
                    if SPREADSHEET_ID else "https://docs.google.com/spreadsheets"
                )
                send("\n=== PIPELINE COMPLETE ===")
                send(f"SHEET_URL:{sheet_url}")
                send("STATUS:done")

        # Persist run history to Vercel Blob
        try:
            history = read_blob("run_history.json") or []
            history.insert(0, {
                "id": run_id,
                "startedAt": started_at,
                "finishedAt": datetime.now(timezone.utc).isoformat(),
                "status": "done" if success else "error",
                "params": config,
                "toolsFound": tools_found,
                "sheetUrl": (
                    f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
                    if SPREADSHEET_ID else ""
                ),
                "logs": logs[-100:],  # keep last 100 lines
            })
            write_blob("run_history.json", history[:50])  # keep last 50 runs
        except Exception:
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
