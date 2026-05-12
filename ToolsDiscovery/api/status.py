"""
api/status.py
--------------
GET /api/status  — returns pipeline running state.
On Vercel (stateless), always returns running: false.
The frontend relies on the SSE stream from /api/run for live status.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"running": False}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
