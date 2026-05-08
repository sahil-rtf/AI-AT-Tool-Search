"""
run_pipeline.py
----------------
Single end-to-end script for the AT Tool Discovery pipeline.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIRST-TIME SETUP  (do this once per machine)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Install Python 3.11+  →  https://www.python.org/downloads/
   Make sure "Add Python to PATH" is checked during install.

2. Install dependencies:
       pip install -r requirements.txt

3. Create your .env file:
   - Copy  .env.example  →  .env  (same folder)
   - Fill in your own Gemini API key
     (get one free at https://aistudio.google.com/app/apikey)
   - The SPREADSHEET_ID is already filled in — leave it as-is

4. Get the  credentials.json  file:
   - This file is already included in the repo (it is safe to commit
     for installed-app OAuth flows in a private repository)
   - If it is missing, ask the project owner for a copy and place it
     in the ToolsDiscovery/ folder alongside this script

5. First run — Google sign-in:
   - When you run  python run_pipeline.py  for the first time,
     a browser window will open asking you to sign in to Google.
   - Sign in with the Google account that has access to the database.
   - You will only be asked to sign in once; after that your token
     is saved locally as  token.json

   ⚠  If you see "Google hasn't verified this app" — click
      "Advanced" → "Go to AT Tool Discovery (unsafe)" to proceed.
      This warning appears because the app is internal and has not
      gone through Google's public verification process.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USAGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  python run_pipeline.py

After the pipeline finishes, open the AI_LEADS tab in the
spreadsheet, review each tool, tick Accepted / Rejected /
Duplicate, then manually move the rows to the appropriate
sheet (AI_Accepted / AI_Rejected / AI_Duplicates) directly
in Google Sheets.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT THE PIPELINE DOES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Step 1  Load current tools database from Google Sheets
  Step 2  Use Gemini AI + web search to find new tools
  Step 3  Verify categories and refine descriptions
  Step 4  Check tool website URLs
  Step 5  Fill any missing data fields
  Step 6  Score for duplicates and push to AI_LEADS sheet
  Step 7  Delete intermediate files
"""

import os
import sys
import json
import subprocess
from dotenv import load_dotenv

load_dotenv()

# ── Categories (must match gemini_search_with_web.py) ───────────────────────
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

# ── Helpers ──────────────────────────────────────────────────────────────────

def banner(title: str):
    width = 60
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def step_header(num: int, title: str):
    print(f"\n{'─' * 60}")
    print(f"  Step {num}  |  {title}")
    print(f"{'─' * 60}")


def run_script(script: str, step_num: int, description: str):
    """Run a Python script via subprocess. Aborts the pipeline on failure."""
    step_header(step_num, description)
    result = subprocess.run([sys.executable, script])
    if result.returncode != 0:
        print(f"\n[ERROR] {script} exited with code {result.returncode}.")
        print("Pipeline aborted. Fix the error above and re-run.")
        print("Intermediate files have been kept for debugging.")
        _cleanup_config()   # remove config but keep CSV files for inspection
        sys.exit(1)


INTERMEDIATE_FILES = [
    "new_tools.csv",
    "new_tools_filtered.csv",
    "new_tools_final.csv",
    "new_tools_with_validation.csv",
    "new_tools_complete.csv",
    "pipeline_config.json",
]


def _cleanup_config():
    if os.path.exists("pipeline_config.json"):
        os.remove("pipeline_config.json")


def _cleanup_intermediate(working_dir: str = "."):
    """Delete all intermediate pipeline files after a successful run."""
    removed = []
    for fname in INTERMEDIATE_FILES:
        fpath = os.path.join(working_dir, fname)
        if os.path.exists(fpath):
            os.remove(fpath)
            removed.append(fname)
    if removed:
        print(f"  Cleaned up: {', '.join(removed)}")
    else:
        print("  No intermediate files to clean up.")

# ── Step 0: Interactive category count prompt ────────────────────────────────

def ask_for_counts() -> dict:
    banner("AT Tool Discovery Pipeline")

    print(
        "\nHow many NEW tools do you want to find in each category?\n"
        "Enter a number (e.g. 10) or press Enter to skip a category.\n"
    )

    longest = max(len(c) for c in CATEGORIES)
    counts = {}

    for category in CATEGORIES:
        while True:
            raw = input(f"  {category:<{longest}}  : ").strip()

            if raw == "":           # Enter with no input → skip
                counts[category] = 0
                break

            if raw.isdigit():
                counts[category] = int(raw)
                break

            print("    ↳ Please enter a whole number, or press Enter to skip.")

    # Summary
    print()
    banner("Your selections")
    total = 0
    active = [(cat, n) for cat, n in counts.items() if n > 0]
    skipped = [cat for cat, n in counts.items() if n == 0]

    for cat, n in active:
        print(f"  ✓  {cat:<{longest}}  →  {n} tools")
        total += n
    for cat in skipped:
        print(f"  –  {cat:<{longest}}  →  SKIP")

    print(f"\n  Estimated tools to find: ~{total}")

    if not active:
        print("\nNothing to do — all categories skipped. Exiting.")
        sys.exit(0)

    print()
    answer = input("Proceed? [Y/n]: ").strip().lower()
    if answer not in ("", "y", "yes"):
        print("Aborted.")
        sys.exit(0)

    return counts

# ── Main pipeline ────────────────────────────────────────────────────────────

def main():
    # ── Step 0: Ask user ─────────────────────────────────────────────────────
    counts = ask_for_counts()

    # Write config so gemini_search_with_web.py picks up the per-category counts
    with open("pipeline_config.json", "w") as f:
        json.dump({"tools_per_category": counts}, f, indent=2)

    # ── Step 1: Load database from Google Sheets ─────────────────────────────
    run_script(
        "load_google_sheets_with_formatting.py", 1,
        "Loading existing tools from Google Sheets"
    )

    # ── Step 2: AI searches for new tools ────────────────────────────────────
    run_script(
        "gemini_search_with_web.py", 2,
        "Searching the web for new tools with Gemini AI"
    )

    # ── Step 3: Verify categories + refine descriptions ──────────────────────
    run_script(
        "second_pass.py", 3,
        "Verifying categories and refining descriptions"
    )

    # ── Step 4: Check tool websites ──────────────────────────────────────────
    run_script(
        "url_checker.py", 4,
        "Checking tool website URLs"
    )

    # ── Step 5: Fill any missing data ────────────────────────────────────────
    run_script(
        "third_pass.py", 5,
        "Completing missing data fields"
    )

    # ── Step 6: Score tools and push to AI_LEADS sheet ───────────────────────
    run_script(
        "push_to_ai_leads.py", 6,
        "Scoring tools for duplicates and pushing to AI_LEADS sheet"
    )

    # ── Step 7: Clean up all intermediate files ───────────────────────────────
    step_header(7, "Cleaning up intermediate files")
    _cleanup_intermediate()

    # ── Final message ─────────────────────────────────────────────────────────
    sheet_url = (
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
        if SPREADSHEET_ID else "https://docs.google.com/spreadsheets"
    )

    banner("PIPELINE COMPLETE")
    print(
        "\n  The AI-discovered tools have been scored and pushed to\n"
        "  the AI_LEADS sheet in your Google Spreadsheet.\n"
    )
    print(f"  Open it here:")
    print(f"\n      {sheet_url}\n")
    print(
        "  Next steps:\n"
        "    1. Open the AI_LEADS tab in the link above\n"
        "    2. Review each row — use the Confidence Score + Potential Match columns:\n"
        "         Green  (70–100)  →  likely a brand-new tool\n"
        "         Amber  (45–69)   →  check the Potential Match column\n"
        "         Red    (0–44)    →  probably already in the database\n"
        "    3. Tick ONE checkbox per row:\n"
        "         ✓ Accepted   — good new tool, add to database\n"
        "         ✗ Rejected   — not relevant or poor quality\n"
        "         ~ Duplicate  — already exists in the database\n"
        "    4. When done reviewing, manually move each row in Google Sheets to:\n"
        "         AI_Accepted   — good new tools\n"
        "         AI_Rejected   — not relevant or poor quality\n"
        "         AI_Duplicates — already exists in the database\n"
        "       then delete the processed rows from AI_LEADS.\n"
    )


if __name__ == "__main__":
    main()
