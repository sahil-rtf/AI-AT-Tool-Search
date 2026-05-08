"""
push_to_ai_leads.py
--------------------
Reads AI-discovered tools from new_tools_complete.csv, scores each one for
duplicate risk against the existing database (active_tools.csv), then writes
them to the AI_LEADS sheet in the main Google Spreadsheet.

Output format
--------------
  Columns 0–36  →  exactly the same columns (and order) as the Data tab
  Column  37    →  Confidence Score (% chance NOT a duplicate)
  Column  38    →  Accepted  (checkbox)

Confidence Score
-----------------
  100 = almost certainly a brand-new tool
    0 = almost certainly already in the database

Algorithm (weighted fuzzy matching)
--------------------------------------
  STEP 0  Hard rule: URL exact match → duplicate_score = 1.0
  STEP 1  Weighted score:
          0.46 × name_score  (token_set_ratio)
        + 0.16 × company_score
        + 0.16 × desc_score
        + 0.12 × url_sim  (full URL path similarity — not just domain,
                            so two tools from the same company at different
                            paths are NOT falsely flagged as duplicates)
        + 0.06 × category Jaccard
        + 0.03 × platform Jaccard
        + 0.01 × type match
          Penalty: ×0.70 if categories are known and fully disjoint
  confidence = sigmoid-mapped (1 − best_score) × 100
"""

import os
import re
import ast
import math
import unicodedata
import pandas as pd
from dotenv import load_dotenv
from rapidfuzz import fuzz, process
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# ── Config ───────────────────────────────────────────────────────────────────

load_dotenv()
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HIGH_THRESHOLD   = 0.88
LOW_THRESHOLD    = 0.45

# Potential-match display settings
MATCH_SHOW_THRESHOLD = 0.30   # minimum duplicate_score to appear in the match list
MAX_MATCHES          = 5      # never show more than this many matches per tool

# Candidate generation
MAX_CANDIDATES_BY_NAME = 250
MAX_CANDIDATES_BY_CO_NAME = 250
MAX_CANDIDATES_TOTAL = 600

# Extra columns appended after the Data tab columns
CONFIDENCE_HEADER = (
    "Confidence Score\n"
    "(% chance NOT a duplicate)\n"
    "100 = brand new  |  0 = certain duplicate"
)
POTENTIAL_MATCH_HEADER = "Potential Match\n(closest tool already in database)"

# The three action checkbox column headers
ACCEPTED_HEADER  = "Accepted\n(move to AI_Accepted)"
REJECTED_HEADER  = "Rejected\n(move to AI_Rejected)"
DUPLICATE_HEADER = "Duplicate\n(move to AI_Duplicates)"

# ── Mappings: new_tools fields  →  Data tab column names ────────────────────

# category label  →  (Data-tab column name,  letter to write)
CATEGORY_TO_COL = {
    "Reading":               ("Reading",           "R"),
    "Cognitive":             ("Cognitive",          "C"),
    "Vision":                ("Vision",             "V"),
    "Physical":              ("Physical",           "P"),
    "Hearing":               ("Hearing",            "H"),
    "Speech/ Communication": ("Speech/Comm",        "S"),
    "Training/ Therapy":     ("Training / Therapy", "T"),
    "Executive Function":    ("Exec / Focus",       "E"),
}

# platform keyword  →  (Data-tab column name,  letter to write)
PLATFORM_TO_COL = {
    "Windows":    ("Windows",       "W"),
    "Macintosh":  ("Macintosh",     "M"),
    "Mac":        ("Macintosh",     "M"),
    "Chromebook": ("Chromebook",    "C"),
    "iPad":       ("iPad (iPadOS)", "I"),
    "iPhone":     ("iPhone (iOS)",  "I"),
    "Android":    ("Android",       "A"),
}

# pricing value  →  (Data-tab column name,  letter to write)
PRICING_TO_COL = {
    "Free":              ("FREE",             "F"),
    "Free Trial":        ("Trial",            "F"),
    "One-time purchase": ("Lifetime License", "L"),
    "Subscription":      ("Subscription",     "S"),
}

# Active-tools columns used to look up type in fuzzy scoring
ACTIVE_TYPE_COLS = {
    "B": ["Built-In (no install)", "Built In"],
    "I": ["Need to install", "AT (Installed)"],
}

# Active-tools columns used to look up categories in fuzzy scoring
ACTIVE_CATEGORY_COLS = {
    "Reading":               "Reading",
    "Cognitive":             "Cognitive",
    "Vision":                "Vision",
    "Physical":              "Physical",
    "Hearing":               "Hearing",
    "Speech/ Communication": "Speech/Comm",
    "Training/ Therapy":     "Training / Therapy",
    "Executive Function":    "Exec / Focus",
}

ACTIVE_PLATFORM_COLS = {
    "Windows":    "Windows",
    "Macintosh":  "Macintosh",
    "Chromebook": "Chromebook",
    "iPad":       "iPad (iPadOS)",
    "iPhone":     "iPhone (iOS)",
    "Android":    "Android",
}

PRODUCT_NAME_COLS = [
    "PRODUCT/FEATURE NAME",
    "PRODUCT/FEATURE\nNAME",
    "PRODUCT NAME",
    "Product Name",
]

# ── Google Sheets auth ────────────────────────────────────────────────────────

def authenticate():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"  Saved token could not be refreshed ({e}).")
                print("  A new sign-in will be requested.")
                creds = None
        if not creds or not creds.valid:
            if not os.path.exists("credentials.json"):
                print()
                print("ERROR: credentials.json not found.")
                print("  Ask the project owner for this file and place it in the")
                print("  ToolsDiscovery/ folder alongside this script.")
                return None
            print()
            print("  Opening browser for Google sign-in...")
            print("  Sign in with the Google account that has access to the spreadsheet.")
            print("  If you see 'Google hasn't verified this app', click")
            print("  Advanced → 'Go to AT Tool Discovery (unsafe)' to continue.")
            print()
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as fh:
            fh.write(creds.to_json())
        print("  Sign-in successful. Token saved to token.json.")
    return creds

# ── Helpers for reading active_tools.csv ─────────────────────────────────────

def _get_col(row, *candidates):
    for col in candidates:
        if col in row and pd.notna(row[col]) and str(row[col]).strip():
            return str(row[col]).strip()
    return ""

def active_product_name(row):
    return _get_col(row, *PRODUCT_NAME_COLS)

def active_company(row):
    return _get_col(row, "COMPANY", "Company")

def active_type(row) -> str:
    for letter, cols in ACTIVE_TYPE_COLS.items():
        if any(_get_col(row, c) for c in cols):
            return letter
    return ""

def active_categories(row) -> set:
    return {cat for cat, col in ACTIVE_CATEGORY_COLS.items() if _get_col(row, col)}

def active_platforms(row) -> set:
    return {plat for plat, col in ACTIVE_PLATFORM_COLS.items() if _get_col(row, col)}

def active_website(row) -> str:
    return _get_col(row, "VENDOR'S WEBSITE DESC LINK", "Website").lower()

def active_description(row) -> str:
    return _get_col(row, "DESCRIPTION", "Description")

# ── Helpers for reading new_tools_complete.csv ────────────────────────────────

def parse_list_field(value) -> set:
    if pd.isna(value) or not str(value).strip():
        return set()
    try:
        result = ast.literal_eval(str(value))
        if isinstance(result, list):
            return {str(x).strip() for x in result if str(x).strip()}
    except (ValueError, SyntaxError):
        pass
    return {p.strip().strip("'\"[]") for p in str(value).split(",") if p.strip().strip("'\"[]")}

# ── Normalization / URL helpers ────────────────────────────────────────────────

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "mc_cid", "mc_eid", "igshid", "ref", "ref_src",
}

def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))

def norm_text(s: str) -> str:
    """
    Aggressive-ish normalization for fuzzy matching.
    Keeps letters/numbers, collapses whitespace, drops accents.
    """
    s = (s or "").strip().lower()
    if not s:
        return ""
    s = _strip_accents(s)
    s = re.sub(r"&", " and ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def canonical_domain(url: str) -> str:
    """
    Extracts a comparable domain for dedupe (no scheme, no path).
    Example: https://www.example.com/path -> example.com
    """
    url = (url or "").strip().lower()
    if not url:
        return ""
    url = re.sub(r"^https?://", "", url)
    url = url.split("/")[0]
    url = url.split("?")[0]
    url = url.split("#")[0]
    url = re.sub(r"^www\.", "", url)
    return url.strip()

def canonical_url(url: str) -> str:
    """
    Best-effort canonicalization for exact-match checks.
    Drops common tracking params and normalizes trailing slash.
    """
    url = (url or "").strip()
    if not url:
        return ""
    u = url.strip()
    u = re.sub(r"^http://", "https://", u, flags=re.I)
    # Remove fragment
    u = u.split("#")[0]
    if "?" in u:
        base, qs = u.split("?", 1)
        parts = []
        for p in qs.split("&"):
            if not p:
                continue
            k = p.split("=", 1)[0].strip().lower()
            if k in _TRACKING_PARAMS:
                continue
            parts.append(p)
        u = base + ("?" + "&".join(parts) if parts else "")
    # Normalize www + trailing slash
    u = re.sub(r"^https?://www\.", "https://", u, flags=re.I)
    if u.endswith("/"):
        u = u[:-1]
    return u

# ── Fuzzy matching primitives ─────────────────────────────────────────────────

def jaccard(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)

def keyword_overlap(text_a: str, text_b: str) -> float:
    words_a = set(re.findall(r"\b\w{3,}\b", text_a.lower()))
    words_b = set(re.findall(r"\b\w{3,}\b", text_b.lower()))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)

# ── Active tools pre-indexing ─────────────────────────────────────────────────

def build_active_index(active_df: pd.DataFrame) -> dict:
    """
    Precompute strings used for fast candidate generation.
    Returns dict containing lists aligned to active_df rows.
    """
    names = []
    companies = []
    co_name = []
    websites = []
    domains = []
    descs = []
    cats = []
    plats = []
    types = []

    for _, r in active_df.iterrows():
        n = active_product_name(r)
        c = active_company(r)
        w = active_website(r)
        d = canonical_domain(w)
        names.append(norm_text(n))
        companies.append(norm_text(c))
        co_name.append(norm_text(f"{c} {n}"))
        websites.append(canonical_url(w))
        domains.append(d)
        descs.append(norm_text(active_description(r)))
        cats.append(active_categories(r))
        plats.append(active_platforms(r))
        types.append(active_type(r))

    return {
        "names": names,
        "companies": companies,
        "co_name": co_name,
        "websites": websites,
        "domains": domains,
        "descs": descs,
        "cats": cats,
        "plats": plats,
        "types": types,
    }

def _candidate_indices(new_tool: dict, active_index: dict) -> list[int]:
    """
    Generate a reasonably small set of candidate indices in active_tools.
    Priority: exact URL, domain match, then fuzzy name/company+name.
    """
    new_name = norm_text(str(new_tool.get("Product Name", "")).strip())
    new_company = norm_text(str(new_tool.get("Company", "")).strip())
    new_url = canonical_url(str(new_tool.get("Website", "")).strip())
    new_domain = canonical_domain(new_url)

    candidates: set[int] = set()

    # URL exact canonical match
    if new_url:
        for i, ex_url in enumerate(active_index["websites"]):
            if ex_url and ex_url == new_url:
                candidates.add(i)

    # Domain match
    if new_domain:
        for i, ex_dom in enumerate(active_index["domains"]):
            if ex_dom and ex_dom == new_domain:
                candidates.add(i)

    # Fuzzy by name
    if new_name:
        # rapidfuzz.process.extract returns list of (match, score, idx)
        for _, score, idx in process.extract(
            new_name,
            active_index["names"],
            scorer=fuzz.WRatio,
            limit=MAX_CANDIDATES_BY_NAME,
        ):
            if score >= 55:
                candidates.add(idx)

    # Fuzzy by "company + name"
    if new_company or new_name:
        query = norm_text(f"{new_company} {new_name}".strip())
        if query:
            for _, score, idx in process.extract(
                query,
                active_index["co_name"],
                scorer=fuzz.WRatio,
                limit=MAX_CANDIDATES_BY_CO_NAME,
            ):
                if score >= 55:
                    candidates.add(idx)

    # Safety cap: if we still have nothing, fall back to broad scan
    if not candidates:
        return list(range(len(active_index["names"])))

    # Hard cap (keep best by name similarity)
    if len(candidates) > MAX_CANDIDATES_TOTAL and new_name:
        scored = []
        for idx in candidates:
            score = fuzz.WRatio(new_name, active_index["names"][idx])
            scored.append((score, idx))
        scored.sort(reverse=True)
        return [idx for _, idx in scored[:MAX_CANDIDATES_TOTAL]]

    return list(candidates)

# ── Core scoring ──────────────────────────────────────────────────────────────

def _sigmoid(x: float) -> float:
    # Stable sigmoid for moderate x ranges
    if x >= 0:
        z = math.exp(-x)
        return 1 / (1 + z)
    z = math.exp(x)
    return z / (1 + z)

def duplicate_score_to_confidence(score: float) -> int:
    """
    Convert a raw duplicate_score (0-1) into a confidence (0-100)
    where 100 means "very likely NOT a duplicate".

    Uses a logistic mapping to avoid bunching in the middle.
    """
    s = max(0.0, min(1.0, float(score)))
    # Tuned so ~0.55-0.75 stretches into a wider confidence band
    dup_prob = _sigmoid((s - 0.62) / 0.07)  # 0..1
    conf = int(round(100 * (1.0 - dup_prob)))
    return max(0, min(100, conf))

def calculate_duplicate_score(
    new_tool: dict,
    existing_row: pd.Series,
    *,
    existing_meta: dict | None = None,
    existing_idx: int | None = None,
):
    """
    Returns (duplicate_score 0..1, reason_str).

    existing_meta/existing_idx let us reuse precomputed normalized fields.
    """
    new_name_raw = str(new_tool.get("Product Name", "")).strip()
    new_company_raw = str(new_tool.get("Company", "")).strip()
    new_desc_raw = str(new_tool.get("Description", "")).strip()
    new_type = str(new_tool.get("Type", "")).strip()
    new_cats = parse_list_field(new_tool.get("Categories", ""))
    new_plats = parse_list_field(new_tool.get("Platforms", ""))
    new_url = canonical_url(str(new_tool.get("Website", "")).strip())
    new_domain = canonical_domain(new_url)

    ex_name_raw = active_product_name(existing_row)
    ex_company_raw = active_company(existing_row)
    ex_desc_raw = active_description(existing_row)
    ex_type = active_type(existing_row)
    ex_url = canonical_url(active_website(existing_row))
    ex_domain = canonical_domain(ex_url)
    ex_cats = active_categories(existing_row)
    ex_plats = active_platforms(existing_row)

    # Pre-normalized fields if provided
    if existing_meta is not None and existing_idx is not None:
        ex_name = existing_meta["names"][existing_idx]
        ex_company = existing_meta["companies"][existing_idx]
        ex_desc = existing_meta["descs"][existing_idx]
        ex_cats = existing_meta["cats"][existing_idx]
        ex_plats = existing_meta["plats"][existing_idx]
        ex_type = existing_meta["types"][existing_idx]
        ex_url = existing_meta["websites"][existing_idx]
        ex_domain = existing_meta["domains"][existing_idx]
    else:
        ex_name = norm_text(ex_name_raw)
        ex_company = norm_text(ex_company_raw)
        ex_desc = norm_text(ex_desc_raw)

    new_name = norm_text(new_name_raw)
    new_company = norm_text(new_company_raw)
    new_desc = norm_text(new_desc_raw)

    # STEP 0 – strong URL rule
    if new_url and ex_url and new_url == ex_url:
        return 1.0, "url:exact"

    # Full URL path similarity — requires path to match, not just domain.
    # This avoids false positives where a company hosts multiple distinct tools
    # under the same domain (e.g. texthelp.com/read-write vs texthelp.com/orbitnote).
    url_sim = fuzz.token_set_ratio(new_url, ex_url) / 100.0 if (new_url and ex_url) else 0.0

    name_score = fuzz.token_set_ratio(new_name, ex_name) / 100.0 if (new_name and ex_name) else 0.0
    company_score = fuzz.token_set_ratio(new_company, ex_company) / 100.0 if (new_company and ex_company) else 0.0
    desc_score = fuzz.token_set_ratio(new_desc, ex_desc) / 100.0 if (new_desc and ex_desc) else 0.0

    cat_sim = jaccard(new_cats, ex_cats) if (new_cats or ex_cats) else 0.0
    plat_sim = jaccard(new_plats, ex_plats) if (new_plats or ex_plats) else 0.0
    type_match = 1.0 if (new_type and ex_type and new_type == ex_type) else 0.0

    # Weighted score (0..1)
    score = (
        0.46 * name_score
        + 0.16 * company_score
        + 0.16 * desc_score
        + 0.12 * url_sim
        + 0.06 * cat_sim
        + 0.03 * plat_sim
        + 0.01 * type_match
    )

    # If categories are known and disjoint, penalize (helps avoid nonsense matches)
    if new_cats and ex_cats and not (new_cats & ex_cats):
        score *= 0.70

    reason = (
        f"name:{name_score:.0%},co:{company_score:.0%},desc:{desc_score:.0%},"
        f"url:{url_sim:.0%},cats:{cat_sim:.0%},plats:{plat_sim:.0%}"
    )
    return max(0.0, min(1.0, score)), reason


def score_new_tool(new_tool: dict, active_df: pd.DataFrame, active_index: dict):
    """
    Compares a new tool against every existing tool.

    Returns:
        confidence_pct  – int 0-100, % chance the tool is NOT a duplicate
        top_hits        – list of (duplicate_score, display_name, reason, active_df_idx) tuples,
                          sorted highest-score first, capped at MAX_MATCHES.
                          Empty list means no significant match found.
    """
    hits = []   # (duplicate_score, display_name, reason, active_df_idx)

    candidates = _candidate_indices(new_tool, active_index)

    # Optional: tighten candidate set using category/platform overlap if present
    new_cats = parse_list_field(new_tool.get("Categories", ""))
    new_plats = parse_list_field(new_tool.get("Platforms", ""))
    if new_cats:
        candidates = [
            i for i in candidates
            if (not active_index["cats"][i]) or (new_cats & active_index["cats"][i])
        ] or candidates
    if new_plats:
        candidates = [
            i for i in candidates
            if (not active_index["plats"][i]) or (new_plats & active_index["plats"][i])
        ] or candidates

    for idx in candidates:
        ex_row = active_df.iloc[idx]
        score, reason = calculate_duplicate_score(new_tool, ex_row, existing_meta=active_index, existing_idx=idx)
        if score >= MATCH_SHOW_THRESHOLD:
            name = f"{active_product_name(ex_row)} ({active_company(ex_row)})"
            hits.append((score, name, reason, idx))

    # Sort highest-score first, keep top N
    hits.sort(key=lambda x: x[0], reverse=True)
    top_hits = hits[:MAX_MATCHES]

    best_score = top_hits[0][0] if top_hits else 0.0
    confidence_pct = duplicate_score_to_confidence(best_score)

    return confidence_pct, top_hits

# ── Format a new tool into Data-tab row order ─────────────────────────────────

def format_as_data_row(tool: dict, data_cols: list) -> list:
    """
    Returns a list of cell values in the exact column order of the Data tab.
    Unknown / unmapped columns are left blank.
    """
    categories = parse_list_field(tool.get("Categories", ""))
    platforms  = parse_list_field(tool.get("Platforms",  ""))
    pricing    = parse_list_field(tool.get("Pricing",    ""))
    tool_type  = str(tool.get("Type", "")).strip()

    col_values: dict = {}

    # Type
    if tool_type == "B":
        col_values["Built-In (no install)"] = "B"
    elif tool_type == "I":
        col_values["Need to install"] = "I"

    # Pricing
    for price_key, (col, letter) in PRICING_TO_COL.items():
        if price_key in pricing:
            col_values[col] = letter

    # Categories
    for cat, (col, letter) in CATEGORY_TO_COL.items():
        if cat in categories:
            col_values[col] = letter

    # Platforms
    for plat in platforms:
        for key, (col, letter) in PLATFORM_TO_COL.items():
            if key.lower() in plat.lower():
                col_values[col] = letter
                break

    # Core text fields
    col_values["ID TAG"]                    = str(tool.get("ID Tag",         "") or "")
    col_values["COMPANY"]                   = str(tool.get("Company",        "") or "")
    col_values["PRODUCT/FEATURE NAME"]      = str(tool.get("Product Name",   "") or "")
    col_values["DESCRIPTION"]               = str(tool.get("Description",    "") or "")
    col_values["VENDOR'S WEBSITE DESC LINK"]= str(tool.get("Website",        "") or "")
    col_values["INTERNAL NOTES"]            = str(tool.get("AI Comments",    "") or "")
    col_values["Data-Entry-Person NOTES"]   = str(tool.get("Target Audience","") or "")

    return [col_values.get(col, "") for col in data_cols]

# ── Google Sheets operations ──────────────────────────────────────────────────

def ensure_ai_leads_sheet(service) -> int:
    spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for sheet in spreadsheet.get("sheets", []):
        if sheet["properties"]["title"] == "AI_LEADS":
            print("AI_LEADS sheet already exists.")
            return sheet["properties"]["sheetId"]
    print("Creating AI_LEADS sheet...")
    body = {"requests": [{"addSheet": {"properties": {"title": "AI_LEADS"}}}]}
    resp = service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, body=body
    ).execute()
    sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    print(f"Created AI_LEADS (sheetId={sheet_id}).")
    return sheet_id


def clear_ai_leads(service):
    service.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID, range="AI_LEADS!A:AZ"
    ).execute()


def get_ai_leads_existing_row_count(service) -> int:
    """
    Returns the number of rows currently in AI_LEADS that contain any data
    (including the header row).  Returns 0 if the sheet is completely empty.

    Reads all columns so it counts correctly even when column A is blank
    (as it is for potential-match sub-rows).
    """
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="AI_LEADS!A:AZ",
        majorDimension="ROWS",
    ).execute()
    # The API omits trailing empty rows, so len(values) == last row with data.
    return len(result.get("values", []))


def write_data(service, all_values: list):
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="AI_LEADS!A1",
        valueInputOption="USER_ENTERED",
        body={"values": all_values},
    ).execute()


def append_data(service, rows: list, start_row: int):
    """
    Writes rows starting at the given 1-based row index (so existing data is not touched).
    """
    range_name = f"AI_LEADS!A{start_row}"
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name,
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()


DEFAULT_COL_WIDTH = 100   # Google Sheets default when no explicit width is set

def get_data_tab_column_widths(service) -> list[int]:
    """
    Reads the pixel widths of every column in the Data tab (sheetId=0).
    Returns a list of ints in column order. Columns whose width was never
    explicitly set come back as 0 from the API — we substitute the default.
    """
    result = service.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID,
        includeGridData=True,
        fields="sheets.properties.sheetId,sheets.data.columnMetadata",
    ).execute()

    for sheet in result.get("sheets", []):
        if sheet["properties"]["sheetId"] == 0:
            col_meta = sheet.get("data", [{}])[0].get("columnMetadata", [])
            return [
                meta.get("pixelSize", 0) or DEFAULT_COL_WIDTH
                for meta in col_meta
            ]

    print("Warning: could not read column widths from Data tab — using defaults.")
    return []


def apply_formatting(service, sheet_id: int, total_rows: int, num_data_cols: int,
                     tool_row_indices: list[int], *, is_first_run: bool = True):
    """
    tool_row_indices: absolute 0-based sheet row indices of the main new-tool rows.
    is_first_run: when True, also applies one-time setup (freeze, header style,
                  column widths, gradient rule).  On subsequent runs only the
                  per-row checkbox validation is applied to the new rows.
    """
    if total_rows == 0:
        return

    total_cols      = num_data_cols + 5   # Confidence + Potential Match + Accepted + Rejected + Duplicate
    col_conf        = num_data_cols
    col_match       = num_data_cols + 1
    col_accepted    = num_data_cols + 2
    col_rejected    = num_data_cols + 3
    col_duplicate   = num_data_cols + 4

    # Build per-row ranges for main tool rows only (no match sub-rows)
    def _row_ranges(col_start, col_end):
        return [
            {
                "sheetId": sheet_id,
                "startRowIndex": r,
                "endRowIndex":   r + 1,
                "startColumnIndex": col_start,
                "endColumnIndex":   col_end,
            }
            for r in tool_row_indices
        ]

    requests = []

    if is_first_run:
        # Read column widths from the Data tab (only needed once)
        print("Reading column widths from Data tab...")
        source_widths = get_data_tab_column_widths(service)

        width_requests = []
        for col_idx in range(num_data_cols):
            px = source_widths[col_idx] if col_idx < len(source_widths) else DEFAULT_COL_WIDTH
            width_requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": col_idx,
                        "endIndex":   col_idx + 1,
                    },
                    "properties": {"pixelSize": px},
                    "fields": "pixelSize",
                }
            })
        # Confidence column
        width_requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id, "dimension": "COLUMNS",
                    "startIndex": col_conf, "endIndex": col_conf + 1,
                },
                "properties": {"pixelSize": 160}, "fields": "pixelSize",
            }
        })
        # Potential Match column
        width_requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id, "dimension": "COLUMNS",
                    "startIndex": col_match, "endIndex": col_match + 1,
                },
                "properties": {"pixelSize": 260}, "fields": "pixelSize",
            }
        })
        # Accepted / Rejected / Duplicate — narrow checkbox columns
        for col_i in (col_accepted, col_rejected, col_duplicate):
            width_requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id, "dimension": "COLUMNS",
                        "startIndex": col_i, "endIndex": col_i + 1,
                    },
                    "properties": {"pixelSize": 100}, "fields": "pixelSize",
                }
            })

        requests += [
            # Freeze header row
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            },
            # Bold + dark-blue header
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0, "endRowIndex": 1,
                        "startColumnIndex": 0, "endColumnIndex": total_cols,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {
                                "bold": True,
                                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                            },
                            "backgroundColor": {"red": 0.13, "green": 0.33, "blue": 0.58},
                            "wrapStrategy": "WRAP",
                            "verticalAlignment": "MIDDLE",
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor,wrapStrategy,verticalAlignment)",
                }
            },
            # Red → Amber → Green gradient on Confidence column (all tool rows, added once)
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": _row_ranges(col_conf, col_conf + 1),
                        "gradientRule": {
                            "minpoint": {
                                "color": {"red": 0.96, "green": 0.26, "blue": 0.21},
                                "type": "NUMBER", "value": "0",
                            },
                            "midpoint": {
                                "color": {"red": 1.0, "green": 0.84, "blue": 0.0},
                                "type": "NUMBER", "value": "50",
                            },
                            "maxpoint": {
                                "color": {"red": 0.20, "green": 0.66, "blue": 0.33},
                                "type": "NUMBER", "value": "100",
                            },
                        },
                    },
                    "index": 0,
                }
            },
        ] + width_requests
    else:
        # Subsequent run: extend the existing gradient rule to cover the new rows.
        # We do this by adding new ranges to it (index 0) via updateConditionalFormatRule.
        # Simpler approach: just add a fresh gradient rule for the new rows only —
        # multiple gradient rules on the same column are fine (each covers its own rows).
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": _row_ranges(col_conf, col_conf + 1),
                    "gradientRule": {
                        "minpoint": {
                            "color": {"red": 0.96, "green": 0.26, "blue": 0.21},
                            "type": "NUMBER", "value": "0",
                        },
                        "midpoint": {
                            "color": {"red": 1.0, "green": 0.84, "blue": 0.0},
                            "type": "NUMBER", "value": "50",
                        },
                        "maxpoint": {
                            "color": {"red": 0.20, "green": 0.66, "blue": 0.33},
                            "type": "NUMBER", "value": "100",
                        },
                    },
                },
                "index": 0,
            }
        })

    # Checkboxes on Accepted / Rejected / Duplicate — always applied to new tool rows
    requests += [
        {
            "setDataValidation": {
                "range": row_range,
                "rule": {"condition": {"type": "BOOLEAN"}, "showCustomUi": True},
            }
        }
        for col_i in (col_accepted, col_rejected, col_duplicate)
        for row_range in _row_ranges(col_i, col_i + 1)
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, body={"requests": requests}
    ).execute()
    print("Formatting applied to AI_LEADS.")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  push_to_ai_leads.py")
    print("=" * 60)

    # Load existing database
    if not os.path.exists("active_tools.csv"):
        print("ERROR: active_tools.csv not found. Run load_google_sheets_with_formatting.py first.")
        return

    active_df = pd.read_csv("active_tools.csv")
    data_cols = list(active_df.columns)          # exact column names from the Data tab
    print(f"Loaded {len(active_df)} existing tools  ({len(data_cols)} columns)")
    print("Building match index...")
    active_index = build_active_index(active_df)

    # Load AI-discovered tools
    if not os.path.exists("new_tools_complete.csv"):
        print("ERROR: new_tools_complete.csv not found. Run the full pipeline first.")
        return

    new_df = pd.read_csv("new_tools_complete.csv")
    print(f"Loaded {len(new_df)} candidate tools from new_tools_complete.csv")

    # Build header row:  Data-tab cols + Confidence + Potential Match + Accepted + Rejected + Duplicate
    header = data_cols + [
        CONFIDENCE_HEADER,
        POTENTIAL_MATCH_HEADER,
        ACCEPTED_HEADER,
        REJECTED_HEADER,
        DUPLICATE_HEADER,
    ]

    # Score + format each tool
    print("\nScoring and formatting tools...")
    rows = []
    tool_row_indices = []   # 0-based sheet row indices of main tool rows (header = row 0)

    for _, tool in new_df.iterrows():
        tool_dict = tool.to_dict()
        confidence, top_hits = score_new_tool(tool_dict, active_df, active_index)

        # Data-tab cells
        data_cells = format_as_data_row(tool_dict, data_cols)

        # Main tool row: Confidence filled, Potential Match blank, checkboxes
        tool_sheet_row = 1 + len(rows)   # header is row 0
        tool_row_indices.append(tool_sheet_row)
        row = data_cells + [confidence, "", False, False, False]
        rows.append(row)

        # Match sub-rows: one per potential match, full data from active_df, no checkboxes
        for match_num, (score, name, _reason, active_idx) in enumerate(top_hits):
            match_label = f"#{match_num + 1}  —  {round(score * 100)}% match"
            active_row  = active_df.iloc[active_idx]
            # Pull every data column from the matched existing tool.
            # Boolean True/False values (from checkbox columns in the Data tab) must NOT
            # be written as Python bools — USER_ENTERED would make Sheets render checkboxes.
            # Convert False/NaN → "" and True → the cell's string representation so it
            # displays as plain text with no checkbox validation.
            def _cell(val):
                if pd.isna(val):
                    return ""
                if isinstance(val, bool):
                    return "" if not val else str(val)   # False → blank; True → "True" text
                return str(val).strip()

            match_data = [
                _cell(active_row[col]) if col in active_row.index else ""
                for col in data_cols
            ]
            # Extra columns: leave confidence blank, label the match, NO checkbox values
            match_row = match_data + ["", match_label, "", "", ""]
            rows.append(match_row)

        label = "NEW   " if confidence >= 70 else ("UNSURE" if confidence >= 45 else "DUP   ")
        first_match = f"{top_hits[0][1]}  —  {round(top_hits[0][0]*100)}%" if top_hits else "—"
        print(f"  [{label}  {confidence:3d}%]  {tool.get('Product Name', '')}")
        print(f"              {first_match}")

    # Optional dry run: write a local CSV preview instead of uploading to Sheets
    if str(os.getenv("DRY_RUN", "")).strip().lower() in ("1", "true", "yes", "y"):
        out_path = "ai_leads_preview.csv"
        print(f"\nDRY_RUN enabled. Writing preview to {out_path} (no Google Sheets upload).")
        pd.DataFrame([header] + rows).to_csv(out_path, index=False, header=False)
        print(f"Done. {len(new_df)} tools, {len(rows)} total rows (including match sub-rows).")
        return

    # Push to Google Sheets
    creds = authenticate()
    if not creds:
        return

    service = build("sheets", "v4", credentials=creds)

    sheet_id = ensure_ai_leads_sheet(service)

    # How many rows already exist in AI_LEADS?
    existing_rows = get_ai_leads_existing_row_count(service)
    print(f"AI_LEADS currently has {existing_rows} row(s) (including header).")

    if existing_rows == 0:
        # First ever run — write header + all rows from A1
        print("Writing header + new rows to AI_LEADS (first run)...")
        write_data(service, [header] + rows)
        # tool_row_indices are already 0-based with header at index 0, no offset needed
        row_offset = 0
        is_first_run = True
    else:
        # Subsequent run — append only the new rows after existing content
        print(f"Appending {len(rows)} new rows after existing data...")
        append_data(service, rows, start_row=existing_rows + 1)
        # tool_row_indices assume header at index 0 and first data row at index 1;
        # shift them so index 1 lands at (existing_rows), i.e. add (existing_rows - 1)
        row_offset = existing_rows - 1
        is_first_run = False

    # Offset tool_row_indices to absolute 0-based sheet row positions
    absolute_tool_indices = [i + row_offset for i in tool_row_indices]

    apply_formatting(service, sheet_id, len(rows), len(data_cols), absolute_tool_indices,
                     is_first_run=is_first_run)

    print()
    print(f"Done. {len(new_df)} new tools appended to AI_LEADS ({len(rows)} total rows added).")
    print(f"View: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid={sheet_id}")


if __name__ == "__main__":
    main()
