"""
api/cron.py
-----------
GET /api/cron — invoked daily by Vercel Cron (0 9 * * *).
Finds all auto-schedules that are due and runs the full pipeline for each.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

_BASE_DIR = Path(__file__).parent.parent
_API_DIR  = Path(__file__).parent
for _p in (_BASE_DIR, _API_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from pipeline import step1_load_sheets, step2_gemini_search, step3_second_pass
from pipeline import step4_url_checker, step5_third_pass, step6_push_to_sheets
from _blob import read_blob, write_blob

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")

FREQ_DELTA: dict[str, timedelta] = {
    "daily":   timedelta(days=1),
    "weekly":  timedelta(weeks=1),
    "monthly": timedelta(days=30),
}


def _compute_next_run(base_iso: str, frequency: str) -> str:
    delta = FREQ_DELTA.get(frequency, timedelta(weeks=1))
    base = datetime.fromisoformat(base_iso)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return (base + delta).isoformat()


def _is_due(schedule: dict) -> bool:
    if schedule.get("type") != "schedule":
        return False
    next_run_str = schedule.get("nextRunAt") or schedule.get("date")
    if not next_run_str:
        return False
    try:
        next_run = datetime.fromisoformat(next_run_str)
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= next_run
    except Exception:
        return False


def _run_pipeline(config: dict, label: str) -> tuple[bool, list[str]]:
    """Run all 6 pipeline steps. Returns (success, log_lines)."""
    logs: list[str] = []

    def log(msg: str):
        logs.append(msg)
        print(f"[cron][{label}] {msg}", flush=True)

    steps = [
        (step1_load_sheets,    "Load Google Sheets database"),
        (step2_gemini_search,  "Gemini AI web search"),
        (step3_second_pass,    "Verify categories & descriptions"),
        (step4_url_checker,    "Check website URLs"),
        (step5_third_pass,     "Fill missing data fields"),
        (step6_push_to_sheets, "Score & push to AI_LEADS"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        for step_mod, step_label in steps:
            log(f"  Starting: {step_label}")
            try:
                ok = step_mod.run(config, log, base_dir)
            except Exception as exc:
                log(f"[ERROR] {step_label} raised: {exc}")
                ok = False
            if not ok:
                log(f"[ERROR] {step_label} failed — aborting pipeline.")
                return False, logs

    return True, logs


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        # Verify Vercel Cron secret (auto-injected by Vercel as CRON_SECRET)
        cron_secret = os.getenv("CRON_SECRET", "")
        if cron_secret:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {cron_secret}":
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"Unauthorized"}')
                return

        schedules = read_blob("schedules.json") or []
        due = [s for s in schedules if _is_due(s)]

        print(f"[cron] {len(schedules)} total schedules, {len(due)} due today.", flush=True)

        if not due:
            self._respond(200, {"ran": 0, "message": "No schedules due today."})
            return

        # Warn if multiple schedules are due on the same day (logged, not blocking)
        if len(due) > 1:
            names = [s.get("name", s.get("id")) for s in due]
            print(
                f"[cron] WARNING: {len(due)} schedules due today: {names}. "
                "Running sequentially — total runtime may approach the 300 s limit.",
                flush=True,
            )

        results = []
        for schedule in due:
            name = schedule.get("name", "Unnamed")
            sid  = schedule.get("id", "")
            print(f"[cron] Running schedule '{name}' …", flush=True)

            config = {
                "tools_per_category": schedule.get("counts", {}),
                "platforms_filter":   schedule.get("platforms", []),
                "access_type_filter": schedule.get("accessType", []),
                "pricing_filter":     schedule.get("pricing", []),
            }

            run_id     = str(uuid.uuid4())
            started_at = datetime.now(timezone.utc).isoformat()
            success, logs = _run_pipeline(config, name)
            finished_at   = datetime.now(timezone.utc).isoformat()

            # Update schedule timestamps in blob
            next_run = _compute_next_run(finished_at, schedule.get("frequency", "weekly"))
            try:
                all_schedules = read_blob("schedules.json") or []
                for i, s in enumerate(all_schedules):
                    if s.get("id") == sid:
                        all_schedules[i] = {**s, "lastRunAt": finished_at, "nextRunAt": next_run}
                        break
                write_blob("schedules.json", all_schedules)
            except Exception as exc:
                print(f"[cron] Failed to update schedule timestamps: {exc}", flush=True)

            # Append to run history
            try:
                history = read_blob("run_history.json") or []
                history.insert(0, {
                    "id":           run_id,
                    "startedAt":    started_at,
                    "finishedAt":   finished_at,
                    "status":       "done" if success else "error",
                    "params":       config,
                    "scheduleId":   sid,
                    "scheduleName": name,
                    "toolsFound":   0,
                    "sheetUrl":     (
                        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
                        if SPREADSHEET_ID else ""
                    ),
                    "source": "cron",
                    "logs":   logs[-100:],
                })
                write_blob("run_history.json", history[:50])
            except Exception as exc:
                print(f"[cron] Failed to save run history: {exc}", flush=True)

            results.append({
                "schedule":  name,
                "success":   success,
                "nextRunAt": next_run,
            })
            print(f"[cron] '{name}' done — success={success}, next={next_run}", flush=True)

        self._respond(200, {"ran": len(results), "results": results})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _respond(self, code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)
