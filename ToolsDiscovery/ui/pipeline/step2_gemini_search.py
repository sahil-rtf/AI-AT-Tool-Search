"""
pipeline/step2_gemini_search.py
---------------------------------
Importable version of gemini_search_with_web.py.
Accepts extra search parameters: platforms, access_type, pricing_filter.
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Callable

import pandas as pd
from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

CATEGORY_COLUMN_MAP = {
    "Vision":               "Vision",
    "Reading":              "Reading",
    "Cognitive":            "Cognitive",
    "Physical":             "Physical",
    "Hearing":              "Hearing",
    "Speech/ Communication":"Speech/Comm",
    "Training/ Therapy":    "Training / Therapy",
    "Executive Function":   "Exec / Focus",
}

PRODUCT_NAME_COLS = [
    "PRODUCT/FEATURE NAME",
    "PRODUCT/FEATURE\nNAME",
    "PRODUCT NAME",
    "Product Name",
]

ALL_CATEGORIES = [
    "Vision", "Reading", "Cognitive", "Physical", "Hearing",
    "Speech/ Communication", "Training/ Therapy", "Executive Function",
]

CATEGORY_DESCRIPTIONS = {
    "Reading": "Tools designed to assist individuals who have difficulty reading text. This includes people with reading disabilities such as dyslexia, those with low vision who struggles to read standard text, and individuals who are blind. These tools may offer features like text-to-speech, screen magnification, high-contrast modes, or simplified text presentation.",
    "Cognitive": "Tools intended to support users with cognitive disabilities that affect reading, writing, memory, or comprehension. This includes individuals with dyslexia, dysgraphia, ADHD, or processing disorders. Such tools may provide simplified content, visual or auditory alternatives, or support for multimodal learning.",
    "Vision": "Tools that assist individuals who are blind, have low vision, or other vision-related impairments. This category also includes tools designed to prevent seizures triggered by visual stimuli, such as flashing lights. Examples include screen readers, Braille displays, high-contrast modes, and tools that reduce flickering or visual clutter.",
    "Physical": "Tools designed to help users with physical disabilities that limit their ability to interact with devices using standard input methods. This includes individuals with limited or no use of their hands, or those with conditions like paralysis or motor impairments.",
    "Hearing": "Tools that assist individuals who are deaf or hard of hearing. These tools may include captioning, speech-to-text transcriptions, sign language support, amplification tools, and visual alerts.",
    "Speech/ Communication": "Tools that assist individuals who are non-verbal or have difficulty speaking or forming coherent verbal communication. This includes AAC devices, speech-generating apps, and sentence construction aids.",
    "Training/ Therapy": "Tools that offer therapeutic or educational support for individuals with disabilities. These may include structured programs to build life skills, cognitive therapies, speech therapy tools, or physical rehabilitation platforms.",
    "Executive Function": "Tools designed to assist individuals who have trouble with planning, organization, time management, and other executive functions. Examples include mind mapping software, task planners, and reminder apps.",
}

CATEGORY_PERSONAS = {
    "Vision": "I am a person who is looking for assistive technology tools that help people who are blind or have low vision.",
    "Hearing": "I am a person who is looking for assistive technology tools that help people who are deaf or hard of hearing.",
    "Physical": "I am a person who is looking for assistive technology tools that would help a person who has trouble using standard keyboards and mouse and needs adaptations or alternate ways to generate text or issue pointing commands on a computer.",
    "Cognitive": "I am a person who is looking for assistive technology tools that would help a person who has cognitive disabilities and has trouble understanding written text, handling complex things, remembering, carrying out multi step processes.",
    "Reading": "I am a person who is looking for assistive technology tools that would help a person who has trouble reading, including trouble seeing the text, having dyslexia, handling complex language, dealing with idioms, trouble tracking across lines, etc.",
    "Speech/ Communication": "I am a person who is looking for assistive technology tools that would help a person who has trouble speaking, and who needs tools to make speech clear or provide an alternate way of communicating. Also include tools that help change sign language to text or vice versa.",
    "Training/ Therapy": "I am a person who is looking for assistive technology tools that would help a person learn/develop skills, including things that help with reading, writing, using a computer, memory, attention, focus etc.",
    "Executive Function": "I am a person who is looking for assistive technology tools that would help a person who has trouble with executive functions such as planning, organization, staying on task, working on proper priorities, not missing appointments.",
}


def _load_tools_data(base_dir: Path):
    active = pd.read_csv(base_dir / "active_tools.csv")
    removed = pd.read_csv(base_dir / "removed_tools.csv")
    return active, removed


def _load_new_tools(base_dir: Path) -> pd.DataFrame:
    p = base_dir / "new_tools.csv"
    if p.exists():
        return pd.read_csv(p)
    return pd.DataFrame()


def _filter_by_category(df: pd.DataFrame, category: str) -> pd.DataFrame:
    col = CATEGORY_COLUMN_MAP.get(category, category)
    if col in df.columns:
        return df[df[col].notna() & (df[col] != "")]
    return pd.DataFrame()


def _format_tools_for_prompt(df: pd.DataFrame, category: str) -> str:
    if df.empty:
        return "No existing tools found."
    lines = []
    for _, row in df.iterrows():
        name = next((str(row[c]) for c in PRODUCT_NAME_COLS if c in row and pd.notna(row[c]) and row[c] != ""), "Unknown")
        company = next((str(row[c]) for c in ["COMPANY", "Company"] if c in row and pd.notna(row[c]) and row[c] != ""), "Unknown")
        desc = next((str(row[c]) for c in ["DESCRIPTION", "Description"] if c in row and pd.notna(row[c]) and row[c] != ""), "No description")
        lines.append(f"- {name} by {company}: {desc}")
    return "\n".join(lines)


def _build_prompt(
    category: str,
    tools_list: str,
    target_count: int,
    iteration: int,
    platforms_filter: list[str],
    access_type_filter: list[str],
    pricing_filter: list[str],
) -> str:
    persona = CATEGORY_PERSONAS.get(category, "I am looking for assistive technology tools.")
    cat_desc = CATEGORY_DESCRIPTIONS.get(category, "")
    other_cats = ", ".join(c for c in ALL_CATEGORIES if c != category)

    # Build optional constraint lines
    platform_line = ""
    if platforms_filter:
        platform_line = f"\n# Platform Filter #\nOnly include tools that are available on at least one of these platforms: {', '.join(platforms_filter)}. Do not include tools that are unavailable on all of these platforms.\n"

    access_line = ""
    if access_type_filter and set(access_type_filter) != {"Built-in", "Installable"}:
        if access_type_filter == ["Built-in"]:
            access_line = '\n# Access Type Filter #\nOnly include tools that are BUILT-IN features of an operating system or platform (type = "B"). Do not include separately installable apps.\n'
        elif access_type_filter == ["Installable"]:
            access_line = '\n# Access Type Filter #\nOnly include tools that require SEPARATE INSTALLATION such as apps, browser extensions, or downloadable software (type = "I"). Do not include built-in OS features.\n'

    pricing_line = ""
    if pricing_filter:
        pricing_line = f"\n# Pricing Filter #\nOnly include tools whose pricing model includes at least one of: {', '.join(pricing_filter)}.\n"

    prompt = f"""
# Persona #
{persona}

# Existing Tools #
I'm already familiar with the following tools in the {category} category and don't show me these again:
{tools_list}

# Category Definition #
Category description: {cat_desc}

# Core Requirement #
The tools you find MUST be directly usable by a person with the disability. Do NOT include tools designed for caregivers, therapists, or educators. The end-user must be the person with the disability.
{platform_line}{access_line}{pricing_line}
# Your Task #
Can you search the web for {target_count if iteration == 1 else 5} new, innovative digital assistive technology tools (software, apps, browser extensions, etc.) in the {category} category that are NOT in my list above? Do not include physical hardware or devices. Please search for the most current and up-to-date tools available.

Important: Assistive technology tools often serve multiple purposes. For each tool, please indicate ALL categories it belongs to from this list: {category} (primary), {other_cats}.

# Output Format #
For each tool, provide the information in JSON format with the following structure:
```json
[
  {{
    "id_tag": "example_id_tag",
    "product_name": "Name of the tool",
    "company": "Company/developer name",
    "description": "Brief description of features and benefits",
    "type": "I",
    "categories": ["Primary category", "Other category 1"],
    "target_audience": "Specific users within the {category} category who would benefit most",
    "platforms": ["Windows", "Chromebook", "Macintosh/Mac", "iPad", "iPhone", "Android"],
    "pricing": ["Free", "Subscription", "One-time purchase", "Free Trial"],
    "website": "https://official-website.com"
  }},
  ...
]
```

# Formatting Rules #
**ID Tag Instructions:**
- Create the `id_tag` from the company and product name. Lowercase with underscores instead of spaces.
- If both names are short, combine them (e.g., company "Apple" + product "Live Caption" → "apple_live_caption").

**Type Instructions:**
- Set "type" to "B" if the tool is a built-in feature of an OS or larger platform.
- Set "type" to "I" for any tool requiring separate installation (app, browser extension, etc.).

**Platform Instructions:**
- The "platforms" field must only contain values from: "Windows", "Chromebook", "Macintosh/Mac", "iPad", "iPhone", "Android".
- If a tool is a Chrome extension, list all platforms that support Chrome extensions from the allowed list.

**Pricing Instructions:**
- The "pricing" field must only contain values from: "Free", "Subscription", "One-time purchase", "Free Trial".
- Include all applicable pricing models.

# Final Instruction #
After the JSON, include a line: "More tools available: True/False"
Provide ONLY the JSON response followed by that line, with no additional text.
"""
    return prompt


def _search_single_category(
    category: str,
    base_dir: Path,
    target_count: int,
    iteration: int,
    platforms_filter: list[str],
    access_type_filter: list[str],
    pricing_filter: list[str],
    log: Callable,
) -> tuple[str | None, bool]:
    active, removed = _load_tools_data(base_dir)
    new_df = _load_new_tools(base_dir)

    all_df = pd.concat([active, removed, new_df], ignore_index=True)
    cat_tools = _filter_by_category(all_df, category)
    tools_list = _format_tools_for_prompt(cat_tools, category)

    prompt = _build_prompt(
        category, tools_list, target_count, iteration,
        platforms_filter, access_type_filter, pricing_filter,
    )

    client = genai.Client(api_key=GEMINI_API_KEY)
    RETRYABLE_CODES = {429, 500, 503}
    MAX_RETRIES = 6
    BASE_DELAY = 5

    log(f"  Searching {category} (iteration {iteration}, target {target_count})...")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={"tools": [{"google_search": {}}]},
            )
            text = response.text
            parts = text.split("More tools available:")
            json_text = parts[0].strip().replace("```json", "").replace("```", "").strip()
            more = len(parts) > 1 and parts[1].strip().lower() == "true"
            return json_text, more
        except Exception as e:
            error_str = str(e)
            is_retryable = any(str(code) in error_str for code in RETRYABLE_CODES)
            if is_retryable and attempt < MAX_RETRIES:
                cap = BASE_DELAY * (2 ** (attempt - 1))
                wait = random.uniform(cap / 2, cap)
                log(f"  API error (attempt {attempt}/{MAX_RETRIES}): {error_str}")
                log(f"  Retrying in {wait:.1f}s...")
                time.sleep(wait)
            else:
                log(f"[ERROR] Gemini API failed (attempt {attempt}): {error_str}")
                return None, False
    return None, False


def _parse_json(json_text: str, category: str, log: Callable) -> list:
    try:
        tools = json.loads(json_text)
        for tool in tools:
            if "categories" in tool and isinstance(tool["categories"], list):
                if category not in tool["categories"]:
                    tool["categories"].insert(0, category)
        return tools
    except Exception as e:
        log(f"[ERROR] JSON parse failed: {e}")
        return []


def _save_results(category: str, tools: list, iteration: int, base_dir: Path):
    results_dir = base_dir / "results"
    results_dir.mkdir(exist_ok=True)
    fname = results_dir / f"{category.replace('/', '_').replace(' ', '_')}_tools_{iteration}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(tools, f, indent=2)


def _update_new_tools_csv(tools: list, base_dir: Path) -> int:
    csv_file = base_dir / "new_tools.csv"
    try:
        df_existing = pd.read_csv(csv_file)
    except FileNotFoundError:
        df_existing = pd.DataFrame(columns=[
            "ID Tag", "Product Name", "Company", "Description", "Type",
            "Categories", "Target Audience", "Platforms", "Pricing", "Website",
        ])

    active_df = pd.read_csv(base_dir / "active_tools.csv")
    product_col = next((c for c in PRODUCT_NAME_COLS if c in active_df.columns), None)
    product_col_series = active_df[product_col] if product_col else pd.Series([""] * len(active_df))

    active_df["unique_id"] = (
        active_df["COMPANY"].fillna("").astype(str).str.lower().str.replace(r"\s+", "", regex=True)
        + "_"
        + product_col_series.fillna("").astype(str).str.lower().str.replace(r"\s+", "", regex=True)
    )
    df_existing["unique_id"] = (
        df_existing["Company"].fillna("").astype(str).str.lower().str.replace(r"\s+", "", regex=True)
        + "_"
        + df_existing["Product Name"].fillna("").astype(str).str.lower().str.replace(r"\s+", "", regex=True)
    )

    existing_ids = set(active_df["unique_id"]).union(set(df_existing["unique_id"]))
    new_df = pd.DataFrame(tools)
    new_df["unique_id"] = (
        new_df["company"].fillna("").astype(str).str.lower().str.replace(r"\s+", "", regex=True)
        + "_"
        + new_df["product_name"].fillna("").astype(str).str.lower().str.replace(r"\s+", "", regex=True)
    )

    deduped = new_df[~new_df["unique_id"].isin(existing_ids)]
    if deduped.empty:
        return 0

    deduped = deduped.rename(columns={
        "id_tag": "ID Tag", "product_name": "Product Name", "company": "Company",
        "description": "Description", "type": "Type", "categories": "Categories",
        "target_audience": "Target Audience", "platforms": "Platforms",
        "pricing": "Pricing", "website": "Website",
    })
    deduped["AI Verified"] = False
    deduped["Human Verified"] = "unverified"

    cols = ["ID Tag", "Product Name", "Company", "Description", "Type", "Categories",
            "Target Audience", "Platforms", "Pricing", "Website", "AI Verified", "Human Verified"]
    deduped[cols].to_csv(csv_file, mode="a", header=not csv_file.exists(), index=False)
    return len(deduped)


# ── Public entry point ────────────────────────────────────────────────────────

def run(config: dict, log: Callable[[str], None], base_dir: Path) -> bool:
    """
    config keys:
      tools_per_category: {category: count}
      platforms_filter:   list of platform strings (optional)
      access_type_filter: ["Built-in"] | ["Installable"] | ["Built-in","Installable"] (optional)
      pricing_filter:     list of pricing strings (optional)
    """
    log("=" * 55)
    log("  Step 2  |  Gemini AI web search for new tools")
    log("=" * 55)

    if not GEMINI_API_KEY:
        log("[ERROR] GEMINI_API_KEY not set.")
        return False

    counts: dict = config.get("tools_per_category", {})
    platforms_filter: list = config.get("platforms_filter", [])
    access_type_filter: list = config.get("access_type_filter", [])
    pricing_filter: list = config.get("pricing_filter", [])

    categories_to_run = {cat: cnt for cat, cnt in counts.items() if cnt > 0}
    if not categories_to_run:
        log("[ERROR] No categories with count > 0 in config.")
        return False

    (base_dir / "results").mkdir(exist_ok=True)

    for category, target_count in categories_to_run.items():
        log(f"\n  Processing category: {category} (target: {target_count})")
        iteration = 1
        more_available = True
        total_added = 0

        while more_available and iteration <= 5 and total_added < target_count:
            json_text, more_available = _search_single_category(
                category, base_dir, target_count, iteration,
                platforms_filter, access_type_filter, pricing_filter, log,
            )

            if json_text:
                tools = _parse_json(json_text, category, log)
                if tools:
                    _save_results(category, tools, iteration, base_dir)
                    added = _update_new_tools_csv(tools, base_dir)
                    total_added += added
                    log(f"  Iteration {iteration}: +{added} tools (total: {total_added}/{target_count})")
                    if added == 0:
                        more_available = False
                else:
                    more_available = False
            else:
                more_available = False

            iteration += 1
            if more_available and total_added < target_count:
                time.sleep(5)

        log(f"  {category}: {total_added} tools added.")

    log("  Step 2 complete.")
    return True
