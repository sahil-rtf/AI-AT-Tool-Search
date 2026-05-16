"""
pipeline/step3_second_pass.py
-------------------------------
Importable version of second_pass.py.
Verifies categories, refines descriptions, filters non-digital tools.
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

CATEGORY_DEFINITIONS = {
    "Reading": "Tools designed to assist individuals who have difficulty reading text. This includes people with reading disabilities such as dyslexia, those with low vision who struggles to read standard text, and individuals who are blind.",
    "Writing": "Tools designed to help individuals who have difficulty producing written text, including those with dysgraphia, motor impairments, or language processing difficulties.",
    "Cognitive": "Tools intended to support users with cognitive disabilities that affect reading, writing, memory, or comprehension. This includes individuals with dyslexia, dysgraphia, ADHD, or processing disorders.",
    "Vision": "Tools that assist individuals who are blind, have low vision, or other vision-related impairments. This category also includes tools designed to prevent seizures triggered by visual stimuli.",
    "Braille": "Tools that provide Braille output or input support for individuals who are blind or deafblind, including Braille display drivers, translation software, and apps that interface with refreshable Braille devices.",
    "Physical": "Tools designed to help users with physical disabilities that limit their ability to interact with devices using standard input methods.",
    "Hearing": "Tools that assist individuals who are deaf or hard of hearing.",
    "Speech/ Communication": "Tools that assist individuals who are non-verbal or have difficulty speaking or forming coherent verbal communication.",
    "Training/ Therapy": "Tools that offer therapeutic or educational support for individuals with disabilities.",
    "Executive Function": "Tools designed to assist individuals who have trouble with planning, organization, time management, and other executive functions.",
}


def _verify_categories(df: pd.DataFrame, log: Callable) -> pd.DataFrame:
    if df.empty:
        return df
    log(f"  Verifying categories for {len(df)} tools...")
    defs_text = "\n".join(f"- **{n}**: {d}" for n, d in CATEGORY_DEFINITIONS.items())
    client = genai.Client(api_key=GEMINI_API_KEY)
    verified: dict = {}
    batch_size = 10

    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i + batch_size]
        tools_text = ""
        for _, row in batch.iterrows():
            tools_text += f"  - id_tag: {row['ID Tag']}\n    name: {row['Product Name']}\n    description: {row['Description']}\n"

        prompt = f"""# Your Task
You are a meticulous data validator. Verify the functional categories for a batch of assistive technology tools.

# Category Definitions
{defs_text}

# Tools to Verify
{tools_text}

# Instructions
Based on each tool's description, identify all categories it belongs to.
The categories should reflect direct use by a person with a disability.

Return a single JSON object:
```json
{{
  "tools": [
    {{"id_tag": "example_id_1", "categories": ["Vision", "Reading"]}},
    {{"id_tag": "example_id_2", "categories": ["Cognitive"]}}
  ]
}}
```
Provide only the JSON response."""

        try:
            log(f"  Category verification batch {i // batch_size + 1}...")
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            json_text = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(json_text)
            for tool in data["tools"]:
                verified[tool["id_tag"]] = tool["categories"]
        except Exception as e:
            log(f"  [WARN] Category verification batch error: {e}")
            for _, row in batch.iterrows():
                verified[row["ID Tag"]] = row["Categories"]
        time.sleep(5)

    df["Categories"] = df["ID Tag"].map(verified).fillna(df["Categories"])
    return df


def _refine_descriptions(df: pd.DataFrame, log: Callable) -> pd.DataFrame:
    if df.empty:
        return df
    log(f"  Refining descriptions for {len(df)} tools...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    refined: dict = {}
    batch_size = 10

    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i + batch_size]
        tools_text = ""
        for _, row in batch.iterrows():
            tools_text += f"  - id_tag: {row['ID Tag']}\n    name: {row['Product Name']}\n    current_description: {row['Description']}\n"

        prompt = f"""# Your Task
You are a technical writer specializing in assistive technology. Refine the descriptions for this batch of tools.

# Tools to Refine
{tools_text}

# Instructions
- If a description is already high-quality (>90% correct), use it unchanged.
- Otherwise, provide a concise improved description (2-3 sentences max).
- Focus on how the tool is used DIRECTLY by a person with a disability.

Return a single JSON object:
```json
{{
  "tools": [
    {{"id_tag": "example_id_1", "description": "Refined description."}},
    {{"id_tag": "example_id_2", "description": "Already good description."}}
  ]
}}
```
Provide only the JSON response."""

        try:
            log(f"  Description refinement batch {i // batch_size + 1}...")
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            json_text = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(json_text)
            for tool in data["tools"]:
                refined[tool["id_tag"]] = tool["description"]
        except Exception as e:
            log(f"  [WARN] Description refinement batch error: {e}")
            for _, row in batch.iterrows():
                refined[row["ID Tag"]] = row["Description"]
        time.sleep(5)

    df["Description"] = df["ID Tag"].map(refined).fillna(df["Description"])
    return df


def run(config: dict, log: Callable[[str], None], base_dir: Path) -> bool:
    log("=" * 55)
    log("  Step 3  |  Verify categories & refine descriptions")
    log("=" * 55)

    input_file = base_dir / "new_tools.csv"
    filtered_file = base_dir / "new_tools_filtered.csv"
    final_file = base_dir / "new_tools_final.csv"

    if not input_file.exists():
        log("[ERROR] new_tools.csv not found.")
        return False

    df = pd.read_csv(input_file)

    if "AI Verified" not in df.columns:
        df["AI Verified"] = False
    if "Human Verified" not in df.columns:
        df["Human Verified"] = "unverified"

    # Filter non-digital tools
    original = len(df)
    df.dropna(subset=["Platforms"], inplace=True)
    df = df[df["Platforms"].str.strip() != ""]
    df = df[df["Platforms"].str.strip() != "[]"]
    removed = original - len(df)
    if removed > 0:
        log(f"  Removed {removed} non-digital tools (empty platforms).")

    df.to_csv(filtered_file, index=False)
    log(f"  Filtered tools saved: {len(df)} digital tools.")

    df_verified = df[df["AI Verified"] == True]
    df_unverified = df[df["AI Verified"] == False]

    if not df_unverified.empty:
        log(f"  Processing {len(df_unverified)} unverified tools...")
        df_processed = _verify_categories(df_unverified.copy(), log)
        df_processed = _refine_descriptions(df_processed, log)
        df_processed["AI Verified"] = True
        df_final = pd.concat([df_verified, df_processed], ignore_index=True)
    else:
        log("  No new tools to process.")
        df_final = df_verified

    if not df_final.empty:
        df_final.to_csv(final_file, index=False)
        log(f"  Saved {len(df_final)} tools to new_tools_final.csv")

    log("  Step 3 complete.")
    return True
