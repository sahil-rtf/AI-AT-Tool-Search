"""
api/schedules.py
-----------------
GET    /api/schedules       — list all saved configs + schedules
POST   /api/schedules       — create a config or schedule
PATCH  /api/schedules?id=X  — update timestamps or promote a config to a schedule
DELETE /api/schedules?id=X  — delete an entry
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).parent))
from _blob import read_blob, write_blob

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


def _cors(h: BaseHTTPRequestHandler):
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        schedules = read_blob("schedules.json") or []
        body = json.dumps(schedules).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        _cors(self)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            self.send_response(400)
            self.end_headers()
            return

        date      = data.get("date", "")
        frequency = data.get("frequency", "")
        # An entry is a "schedule" (auto-runs) only when both date AND frequency are provided
        is_schedule = bool(date and frequency)
        entry_type  = "schedule" if is_schedule else "config"
        next_run    = date if is_schedule else None   # first nextRunAt = start date

        entry = {
            "id":         str(uuid.uuid4()),
            "type":       entry_type,
            "name":       data.get("name", "Untitled"),
            "date":       date,
            "categories": data.get("categories", []),
            "counts":     data.get("counts", {}),
            "platforms":  data.get("platforms", []),
            "accessType": data.get("accessType", []),
            "pricing":    data.get("pricing", []),
            "frequency":  frequency,
            "createdAt":  datetime.now(timezone.utc).isoformat(),
            "lastRunAt":  None,
            "nextRunAt":  next_run,
        }

        schedules = read_blob("schedules.json") or []
        schedules.insert(0, entry)
        write_blob("schedules.json", schedules)

        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        _cors(self)
        self.end_headers()
        self.wfile.write(json.dumps(entry).encode("utf-8"))

    def do_PATCH(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        schedule_id = (params.get("id") or [""])[0]
        if not schedule_id:
            self.send_response(400)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            self.send_response(400)
            self.end_headers()
            return

        schedules = read_blob("schedules.json") or []
        updated = None
        for i, s in enumerate(schedules):
            if s.get("id") != schedule_id:
                continue

            # Update after a run: record timestamps
            if "lastRunAt" in data:
                s["lastRunAt"] = data["lastRunAt"]
                freq = s.get("frequency") or data.get("frequency", "weekly")
                s["nextRunAt"] = _compute_next_run(data["lastRunAt"], freq)

            # Promote config → schedule
            if data.get("promote"):
                date      = data.get("date", s.get("date", ""))
                frequency = data.get("frequency", s.get("frequency", "weekly"))
                s["type"]      = "schedule"
                s["date"]      = date
                s["frequency"] = frequency
                s["nextRunAt"] = s.get("lastRunAt") and _compute_next_run(s["lastRunAt"], frequency) or date

            schedules[i] = s
            updated = s
            break

        if updated is None:
            self.send_response(404)
            self.end_headers()
            return

        write_blob("schedules.json", schedules)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        _cors(self)
        self.end_headers()
        self.wfile.write(json.dumps(updated).encode("utf-8"))

    def do_DELETE(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        schedule_id = (params.get("id") or [""])[0]

        schedules = read_blob("schedules.json") or []
        schedules = [s for s in schedules if s.get("id") != schedule_id]
        write_blob("schedules.json", schedules)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        _cors(self)
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        _cors(self)
        self.end_headers()
