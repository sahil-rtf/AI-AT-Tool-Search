"""
pipeline/step4_url_checker.py
-------------------------------
Importable version of url_checker.py.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable

import pandas as pd
import requests


def _check_url(url: str) -> str:
    if not isinstance(url, str) or not url.startswith("http"):
        return "Invalid URL"
    try:
        response = requests.head(url, allow_redirects=True, timeout=5)
        if response.status_code == 200:
            return "OK"
        return f"Broken (Status code: {response.status_code})"
    except requests.RequestException as e:
        return f"Broken ({e.__class__.__name__})"


def run(config: dict, log: Callable[[str], None], base_dir: Path) -> bool:
    log("=" * 55)
    log("  Step 4  |  Check website URLs")
    log("=" * 55)

    input_file = base_dir / "new_tools_final.csv"
    output_file = base_dir / "new_tools_with_validation.csv"

    if not input_file.exists():
        log("[ERROR] new_tools_final.csv not found.")
        return False

    df = pd.read_csv(input_file)
    log(f"  Checking URLs for {len(df)} tools...")

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(df.columns.tolist() + ["Website Status"])
        for _, row in df.iterrows():
            status = _check_url(row["Website"])
            writer.writerow(row.tolist() + [status])

    log(f"  URL validation complete. Results saved to new_tools_with_validation.csv")
    log("  Step 4 complete.")
    return True
