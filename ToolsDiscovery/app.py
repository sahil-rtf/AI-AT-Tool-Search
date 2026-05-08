"""
app.py  —  Web dashboard for the AT Tool Discovery pipeline.

Run:
    python app.py
Then open  http://localhost:5000  in your browser.
Or run the Next.js UI (ui/) with `npm run dev` and open http://localhost:3000.
"""

import os
import sys
import json
import queue
import threading
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, Response, render_template, request, jsonify
from flask_cors import CORS

load_dotenv()

BASE_DIR = Path(__file__).parent
app = Flask(__name__)

# Allow the Next.js dev server (port 3000) to call the Flask API
CORS(app, resources={r"/*": {"origins": ["http://localhost:3000", "http://127.0.0.1:3000"]}})

CATEGORIES = [
    "Vision",
    "Reading",
    "Cognitive",
    "Physical",
    "Hearing",
    "Speech/ Communication",
    "Training/ Therapy",
    "Executive Function",
]

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")

# ── Global pipeline state ─────────────────────────────────────────────────────

_pipeline_lock = threading.Lock()
_pipeline_running = False
_log_queue: queue.Queue = queue.Queue()


def _enqueue(msg: str):
    """Push a line into the SSE queue."""
    _log_queue.put(msg)


# ── Pipeline runner (runs in a background thread) ─────────────────────────────

PIPELINE_STEPS = [
    ("load_google_sheets_with_formatting.py", "Loading existing tools from Google Sheets"),
    ("gemini_search_with_web.py",             "Searching the web for new tools with Gemini AI"),
    ("second_pass.py",                        "Verifying categories and refining descriptions"),
    ("url_checker.py",                        "Checking tool website URLs"),
    ("third_pass.py",                         "Completing missing data fields"),
    ("push_to_ai_leads.py",                   "Scoring and pushing to AI_LEADS sheet"),
]

INTERMEDIATE_FILES = [
    "new_tools.csv",
    "new_tools_filtered.csv",
    "new_tools_final.csv",
    "new_tools_with_validation.csv",
    "new_tools_complete.csv",
    "pipeline_config.json",
]


def _stream_process(proc: subprocess.Popen):
    """Read stdout+stderr from a subprocess and push each line to the queue."""
    for line in iter(proc.stdout.readline, ""):
        _enqueue(line.rstrip("\n"))
    proc.wait()


def _run_pipeline(counts: dict):
    global _pipeline_running
    try:
        _enqueue("STATUS:running")
        _enqueue("=== AT Tool Discovery Pipeline ===")

        # Write config for gemini_search_with_web.py
        config_path = BASE_DIR / "pipeline_config.json"
        config_path.write_text(json.dumps({"tools_per_category": counts}, indent=2))
        _enqueue(f"Config written -> {config_path.name}")

        for step_num, (script, description) in enumerate(PIPELINE_STEPS, start=1):
            _enqueue(f"\n{'─'*55}")
            _enqueue(f"  Step {step_num}  |  {description}")
            _enqueue(f"{'─'*55}")

            script_path = BASE_DIR / script
            child_env = os.environ.copy()
            child_env["PYTHONIOENCODING"] = "utf-8"
            proc = subprocess.Popen(
                [sys.executable, str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1,
                cwd=str(BASE_DIR),
                env=child_env,
            )
            _stream_process(proc)

            if proc.returncode != 0:
                _enqueue(f"\n[ERROR] {script} exited with code {proc.returncode}.")
                _enqueue("Pipeline aborted. Fix the error above and re-run.")
                _enqueue("STATUS:error")
                return

        # Clean up
        _enqueue(f"\n{'─'*55}")
        _enqueue("  Step 7  |  Cleaning up intermediate files")
        _enqueue(f"{'─'*55}")
        removed = []
        for fname in INTERMEDIATE_FILES:
            fpath = BASE_DIR / fname
            if fpath.exists():
                fpath.unlink()
                removed.append(fname)
        if removed:
            _enqueue(f"  Removed: {', '.join(removed)}")
        else:
            _enqueue("  No intermediate files to clean up.")

        sheet_url = (
            f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
            if SPREADSHEET_ID else "https://docs.google.com/spreadsheets"
        )
        _enqueue("\n=== PIPELINE COMPLETE ===")
        _enqueue(f"SHEET_URL:{sheet_url}")
        _enqueue("STATUS:done")

    except Exception as exc:
        _enqueue(f"[FATAL] Unexpected error: {exc}")
        _enqueue("STATUS:error")
    finally:
        with _pipeline_lock:
            _pipeline_running = False


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(
        "index.html",
        categories=CATEGORIES,
        spreadsheet_id=SPREADSHEET_ID,
    )


@app.route("/run", methods=["POST"])
def run_pipeline():
    global _pipeline_running

    with _pipeline_lock:
        if _pipeline_running:
            return jsonify({"error": "Pipeline is already running."}), 409
        _pipeline_running = True

    data = request.get_json(force=True)
    counts = {cat: int(data.get(cat, 0)) for cat in CATEGORIES}

    # Clear any leftover messages
    while not _log_queue.empty():
        try:
            _log_queue.get_nowait()
        except queue.Empty:
            break

    thread = threading.Thread(target=_run_pipeline, args=(counts,), daemon=True)
    thread.start()
    return jsonify({"status": "started"})


@app.route("/stream")
def stream():
    """Server-Sent Events endpoint — streams log lines to the browser."""
    def event_gen():
        while True:
            try:
                msg = _log_queue.get(timeout=30)
                yield f"data: {msg}\n\n"
            except queue.Empty:
                # Keep-alive ping
                yield "data: \n\n"

    return Response(event_gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/status")
def status():
    with _pipeline_lock:
        running = _pipeline_running
    return jsonify({"running": running})


if __name__ == "__main__":
    print("Dashboard running → http://localhost:5000")
    app.run(debug=False, threaded=True, port=5000)
