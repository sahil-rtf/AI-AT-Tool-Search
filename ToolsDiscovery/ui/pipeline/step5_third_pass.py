"""
pipeline/step5_third_pass.py
-------------------------------
Importable version of third_pass.py.
Fills missing fields using Gemini with Google Search.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

import pandas as pd
from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

VALID_CATEGORIES = [
    "Reading", "Writing", "Cognitive", "Vision", "Braille", "Physical", "Hearing",
    "Speech/ Communication", "Training/ Therapy", "Executive Function",
]
VALID_PLATFORMS = ["Windows", "Macintosh", "Chromebook", "iPad (iPadOS)", "iPhone (iOS)", "Android"]
VALID_PRICING = ["Free", "Free Trial", "Subscription", "One-time purchase"]

CATEGORY_DEFINITIONS = {
    "Reading": "Tools designed to assist individuals who have difficulty reading text.",
    "Writing": "Tools designed to help individuals who have difficulty producing written text, including those with dysgraphia, motor impairments, or language processing difficulties.",
    "Cognitive": "Tools intended to support users with cognitive disabilities.",
    "Vision": "Tools that assist individuals who are blind or have low vision.",
    "Braille": "Tools that provide Braille output or input for individuals who are blind or deafblind.",
    "Physical": "Tools designed to help users with physical disabilities.",
    "Hearing": "Tools that assist individuals who are deaf or hard of hearing.",
    "Speech/ Communication": "Tools that assist individuals who are non-verbal or have difficulty speaking.",
    "Training/ Therapy": "Tools that offer therapeutic or educational support.",
    "Executive Function": "Tools designed to assist individuals who have trouble with planning and organization.",
}


def _get_missing_fields(row) -> list[str]:
    missing = []
    for field in ["Categories", "Platforms", "Pricing", "Target Audience", "Company"]:
        value = row.get(field)
        if pd.isna(value) or value == "" or str(value).strip() == "[]":
            missing.append(field)
    return missing


def _build_completion_prompt(tool_info: dict, missing_fields: list[str]) -> str:
    missing_str = ", ".join(missing_fields)
    field_instructions = ""

    if "Categories" in missing_fields:
        defs_text = "\n".join(f"- **{n}**: {d}" for n, d in CATEGORY_DEFINITIONS.items())
        valid_cats = ", ".join(VALID_CATEGORIES)
        field_instructions += f"\n# Category Definitions\n{defs_text}\n\n# Category Selection\nFor 'Categories', choose from: [{valid_cats}].\n"

    if "Platforms" in missing_fields:
        valid_plats = ", ".join(VALID_PLATFORMS)
        field_instructions += f"\n- For 'Platforms', choose from: [{valid_plats}]."

    if "Pricing" in missing_fields:
        valid_pricing = ", ".join(VALID_PRICING)
        field_instructions += f"\n- For 'Pricing', choose from: [{valid_pricing}]."

    return f"""# Your Task
You are a meticulous data researcher. Find missing information for an assistive technology tool.

# Tool Information
- Name: {tool_info.get('Product Name', 'N/A')}
- Description: {tool_info.get('Description', 'N/A')}
- Website: {tool_info.get('Website', 'N/A')}

# Missing Information
Find the following missing fields: {missing_str}

# Core Requirement
All information must focus on the person with the disability who directly uses the tool.

# Instructions
1. Examine the tool's website and use Google Search to find missing info.
2. If you cannot find information, DO NOT make anything up.{field_instructions}
3. Return a single JSON object with "filled_data" and "ai_comment" keys.

Example Response:
```json
{{
  "filled_data": {{"Pricing": ["Free Trial", "Subscription"]}},
  "ai_comment": "Could not determine the specific Target Audience."
}}
```
Provide only the JSON response."""


def run(config: dict, log: Callable[[str], None], base_dir: Path) -> bool:
    log("=" * 55)
    log("  Step 5  |  Fill missing data fields")
    log("=" * 55)

    input_file = base_dir / "new_tools_with_validation.csv"
    output_file = base_dir / "new_tools_complete.csv"

    if not input_file.exists():
        log("[ERROR] new_tools_with_validation.csv not found.")
        return False

    df = pd.read_csv(input_file)
    client = genai.Client(api_key=GEMINI_API_KEY)

    tools_to_process = df[df.apply(lambda row: len(_get_missing_fields(row)) > 0, axis=1)]

    if tools_to_process.empty:
        log("  No tools with missing data to process.")
        if "AI Comments" not in df.columns:
            df["AI Comments"] = ""
    else:
        log(f"  Found {len(tools_to_process)} tools with missing information.")
        if "AI Comments" not in df.columns:
            df["AI Comments"] = ""

        for index, row in tools_to_process.iterrows():
            missing = _get_missing_fields(row)
            if not missing:
                continue

            log(f"  Processing: {row['Product Name']} (missing: {', '.join(missing)})")
            prompt = _build_completion_prompt(row.to_dict(), missing)

            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config={"tools": [{"google_search": {}}]},
                )
                json_text = response.text.replace("```json", "").replace("```", "").strip()
                api_response = json.loads(json_text)

                for field, value in api_response.get("filled_data", {}).items():
                    if field in df.columns:
                        df.loc[index, field] = str(value)

                comment = api_response.get("ai_comment", "")
                if comment:
                    existing = df.loc[index, "AI Comments"]
                    if pd.isna(existing) or existing == "":
                        df.loc[index, "AI Comments"] = comment
                    else:
                        df.loc[index, "AI Comments"] += f"; {comment}"

                time.sleep(5)
            except Exception as e:
                log(f"  [WARN] Error processing {row['Product Name']}: {e}")
                df.loc[index, "AI Comments"] = f"Error during AI processing: {e}"

    df.to_csv(output_file, index=False)
    log(f"  Saved {len(df)} tools to new_tools_complete.csv")
    log("  Step 5 complete.")
    return True
