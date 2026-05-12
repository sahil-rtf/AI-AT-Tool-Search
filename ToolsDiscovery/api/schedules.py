"""
api/schedules.py
-----------------
GET /api/schedules     — list all schedules
POST /api/schedules    — create a schedule
DELETE /api/schedules  — delete a schedule (?id=<uuid>)
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).parent.parent / "ToolsDiscovery"))
from api._blob import read_blob, write_blob


def _cors(handler: BaseHTTPRequestHandler):
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")


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
        body = self.rfile.read(length)
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            self.send_response(400)
            self.end_headers()
            return

        schedules = read_blob("schedules.json") or []
        entry = {
            "id": str(uuid.uuid4()),
            "name": data.get("name", "Untitled"),
            "date": data.get("date", ""),
            "categories": data.get("categories", []),
            "platforms": data.get("platforms", []),
            "accessType": data.get("accessType", []),
            "pricing": data.get("pricing", []),
            "frequency": data.get("frequency", "weekly"),
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        schedules.insert(0, entry)
        write_blob("schedules.json", schedules)

        resp = json.dumps(entry).encode("utf-8")
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        _cors(self)
        self.end_headers()
        self.wfile.write(resp)

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
