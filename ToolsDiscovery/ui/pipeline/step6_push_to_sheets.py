"""
pipeline/step6_push_to_sheets.py
----------------------------------
Importable version of push_to_ai_leads.py.
Scores new tools and pushes them to the AI_LEADS Google Sheet.
"""

from __future__ import annotations

import ast
import base64
import json
import math
import os
import re
import unicodedata
from pathlib import Path
from typing import Callable

import pandas as pd
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from rapidfuzz import fuzz, process

load_dotenv()

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HIGH_THRESHOLD = 0.88
LOW_THRESHOLD = 0.45
MATCH_SHOW_THRESHOLD = 0.30
MAX_MATCHES = 5
MAX_CANDIDATES_BY_NAME = 250
MAX_CANDIDATES_BY_CO_NAME = 250
MAX_CANDIDATES_TOTAL = 600

CONFIDENCE_HEADER = (
    "Confidence Score\n"
    "(% chance NOT a duplicate)\n"
    "100 = brand new  |  0 = certain duplicate"
)
POTENTIAL_MATCH_HEADER = "Potential Match\n(closest tool already in database)"
ACCEPTED_HEADER = "Accepted\n(move to AI_Accepted)"
REJECTED_HEADER = "Rejected\n(move to AI_Rejected)"
DUPLICATE_HEADER = "Duplicate\n(move to AI_Duplicates)"

CATEGORY_TO_COL = {
    "Reading": ("Reading", "R"),
    "Cognitive": ("Cognitive", "C"),
    "Vision": ("Vision", "V"),
    "Physical": ("Physical", "P"),
    "Hearing": ("Hearing", "H"),
    "Speech/ Communication": ("Speech/Comm", "S"),
    "Training/ Therapy": ("Training / Therapy", "T"),
    "Executive Function": ("Exec / Focus", "E"),
}

PLATFORM_TO_COL = {
    "Windows": ("Windows", "W"),
    "Macintosh": ("Macintosh", "M"),
    "Mac": ("Macintosh", "M"),
    "Chromebook": ("Chromebook", "C"),
    "iPad": ("iPad (iPadOS)", "I"),
    "iPhone": ("iPhone (iOS)", "I"),
    "Android": ("Android", "A"),
}

PRICING_TO_COL = {
    "Free": ("FREE", "F"),
    "Free Trial": ("Trial", "F"),
    "One-time purchase": ("Lifetime License", "L"),
    "Subscription": ("Subscription", "S"),
}

ACTIVE_TYPE_COLS = {
    "B": ["Built-In (no install)", "Built In"],
    "I": ["Need to install", "AT (Installed)"],
}

ACTIVE_CATEGORY_COLS = {
    "Reading": "Reading", "Cognitive": "Cognitive", "Vision": "Vision",
    "Physical": "Physical", "Hearing": "Hearing",
    "Speech/ Communication": "Speech/Comm",
    "Training/ Therapy": "Training / Therapy",
    "Executive Function": "Exec / Focus",
}

ACTIVE_PLATFORM_COLS = {
    "Windows": "Windows", "Macintosh": "Macintosh", "Chromebook": "Chromebook",
    "iPad": "iPad (iPadOS)", "iPhone": "iPhone (iOS)", "Android": "Android",
}

PRODUCT_NAME_COLS = [
    "PRODUCT/FEATURE NAME", "PRODUCT/FEATURE\nNAME", "PRODUCT NAME", "Product Name",
]

DEFAULT_COL_WIDTH = 100


# ── Auth ──────────────────────────────────────────────────────────────────────

def _get_credentials() -> Credentials | None:
    creds = None
    token_b64 = os.getenv("TOKEN_JSON_B64")
    if token_b64:
        token_b64 = token_b64.strip()
        token_b64 += "=" * (-len(token_b64) % 4)
        token_data = base64.b64decode(token_b64).decode("utf-8")
        creds = Credentials.from_authorized_user_info(json.loads(token_data), SCOPES)
    elif os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None
    return creds


# ── Active-tools helpers ──────────────────────────────────────────────────────

def _get_col(row, *candidates):
    for col in candidates:
        if col in row and pd.notna(row[col]) and str(row[col]).strip():
            return str(row[col]).strip()
    return ""


def active_product_name(row): return _get_col(row, *PRODUCT_NAME_COLS)
def active_company(row): return _get_col(row, "COMPANY", "Company")
def active_description(row): return _get_col(row, "DESCRIPTION", "Description")
def active_website(row): return _get_col(row, "VENDOR'S WEBSITE DESC LINK", "Website").lower()

def active_type(row) -> str:
    for letter, cols in ACTIVE_TYPE_COLS.items():
        if any(_get_col(row, c) for c in cols):
            return letter
    return ""

def active_categories(row) -> set:
    return {cat for cat, col in ACTIVE_CATEGORY_COLS.items() if _get_col(row, col)}

def active_platforms(row) -> set:
    return {plat for plat, col in ACTIVE_PLATFORM_COLS.items() if _get_col(row, col)}


# ── Normalization ─────────────────────────────────────────────────────────────

_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"}

def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))

def norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    if not s:
        return ""
    s = _strip_accents(s)
    s = re.sub(r"&", " and ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def canonical_domain(url: str) -> str:
    url = (url or "").strip().lower()
    url = re.sub(r"^https?://", "", url).split("/")[0].split("?")[0]
    return re.sub(r"^www\.", "", url).strip()

def canonical_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    url = re.sub(r"^http://", "https://", url, flags=re.I).split("#")[0]
    if "?" in url:
        base, qs = url.split("?", 1)
        parts = [p for p in qs.split("&") if p and p.split("=", 1)[0].strip().lower() not in _TRACKING_PARAMS]
        url = base + ("?" + "&".join(parts) if parts else "")
    url = re.sub(r"^https?://www\.", "https://", url, flags=re.I)
    return url.rstrip("/")


# ── Fuzzy helpers ─────────────────────────────────────────────────────────────

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

def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1 / (1 + z)
    z = math.exp(x)
    return z / (1 + z)

def dup_score_to_confidence(score: float) -> int:
    s = max(0.0, min(1.0, float(score)))
    dup_prob = _sigmoid((s - 0.62) / 0.07)
    return max(0, min(100, int(round(100 * (1.0 - dup_prob)))))


# ── Index + scoring ────────────────────────────────────────────────────────────

def _build_index(active_df: pd.DataFrame) -> dict:
    names, companies, co_name, websites, domains, descs, cats, plats, types = [], [], [], [], [], [], [], [], []
    for _, r in active_df.iterrows():
        n, c, w = active_product_name(r), active_company(r), active_website(r)
        d = canonical_domain(w)
        names.append(norm_text(n)); companies.append(norm_text(c))
        co_name.append(norm_text(f"{c} {n}")); websites.append(canonical_url(w))
        domains.append(d); descs.append(norm_text(active_description(r)))
        cats.append(active_categories(r)); plats.append(active_platforms(r))
        types.append(active_type(r))
    return dict(names=names, companies=companies, co_name=co_name, websites=websites,
                domains=domains, descs=descs, cats=cats, plats=plats, types=types)


def _candidate_indices(tool: dict, idx: dict) -> list[int]:
    new_name = norm_text(str(tool.get("Product Name", "")))
    new_company = norm_text(str(tool.get("Company", "")))
    new_url = canonical_url(str(tool.get("Website", "")))
    new_domain = canonical_domain(new_url)
    candidates: set = set()

    if new_url:
        candidates.update(i for i, u in enumerate(idx["websites"]) if u and u == new_url)
    if new_domain:
        candidates.update(i for i, d in enumerate(idx["domains"]) if d and d == new_domain)
    if new_name:
        candidates.update(i for _, sc, i in process.extract(new_name, idx["names"], scorer=fuzz.WRatio, limit=MAX_CANDIDATES_BY_NAME) if sc >= 55)
    if new_company or new_name:
        q = norm_text(f"{new_company} {new_name}".strip())
        if q:
            candidates.update(i for _, sc, i in process.extract(q, idx["co_name"], scorer=fuzz.WRatio, limit=MAX_CANDIDATES_BY_CO_NAME) if sc >= 55)

    if not candidates:
        return list(range(len(idx["names"])))
    if len(candidates) > MAX_CANDIDATES_TOTAL and new_name:
        scored = sorted(((fuzz.WRatio(new_name, idx["names"][i]), i) for i in candidates), reverse=True)
        return [i for _, i in scored[:MAX_CANDIDATES_TOTAL]]
    return list(candidates)


def _calc_dup_score(tool: dict, existing: pd.Series, meta: dict, eidx: int):
    new_url = canonical_url(str(tool.get("Website", "")))
    ex_url = meta["websites"][eidx]
    if new_url and ex_url and new_url == ex_url:
        return 1.0, "url:exact"

    url_sim = fuzz.token_set_ratio(new_url, ex_url) / 100.0 if (new_url and ex_url) else 0.0
    name_sc = fuzz.token_set_ratio(norm_text(str(tool.get("Product Name", ""))), meta["names"][eidx]) / 100.0
    co_sc = fuzz.token_set_ratio(norm_text(str(tool.get("Company", ""))), meta["companies"][eidx]) / 100.0
    desc_sc = fuzz.token_set_ratio(norm_text(str(tool.get("Description", ""))), meta["descs"][eidx]) / 100.0
    cat_sim = jaccard(parse_list_field(tool.get("Categories", "")), meta["cats"][eidx])
    plat_sim = jaccard(parse_list_field(tool.get("Platforms", "")), meta["plats"][eidx])
    type_match = 1.0 if (str(tool.get("Type", "")) == meta["types"][eidx] and meta["types"][eidx]) else 0.0

    score = 0.46*name_sc + 0.16*co_sc + 0.16*desc_sc + 0.12*url_sim + 0.06*cat_sim + 0.03*plat_sim + 0.01*type_match
    new_cats = parse_list_field(tool.get("Categories", ""))
    if new_cats and meta["cats"][eidx] and not (new_cats & meta["cats"][eidx]):
        score *= 0.70

    return max(0.0, min(1.0, score)), f"name:{name_sc:.0%},co:{co_sc:.0%},desc:{desc_sc:.0%}"


def _score_tool(tool: dict, active_df: pd.DataFrame, active_index: dict):
    candidates = _candidate_indices(tool, active_index)
    new_cats = parse_list_field(tool.get("Categories", ""))
    new_plats = parse_list_field(tool.get("Platforms", ""))
    if new_cats:
        candidates = [i for i in candidates if not active_index["cats"][i] or (new_cats & active_index["cats"][i])] or candidates
    if new_plats:
        candidates = [i for i in candidates if not active_index["plats"][i] or (new_plats & active_index["plats"][i])] or candidates

    hits = []
    for idx in candidates:
        score, reason = _calc_dup_score(tool, active_df.iloc[idx], active_index, idx)
        if score >= MATCH_SHOW_THRESHOLD:
            name = f"{active_product_name(active_df.iloc[idx])} ({active_company(active_df.iloc[idx])})"
            hits.append((score, name, reason, idx))

    hits.sort(key=lambda x: x[0], reverse=True)
    top = hits[:MAX_MATCHES]
    best = top[0][0] if top else 0.0
    return dup_score_to_confidence(best), top


def _format_row(tool: dict, data_cols: list) -> list:
    categories = parse_list_field(tool.get("Categories", ""))
    platforms = parse_list_field(tool.get("Platforms", ""))
    pricing = parse_list_field(tool.get("Pricing", ""))
    tool_type = str(tool.get("Type", "")).strip()
    col_values: dict = {}

    if tool_type == "B":
        col_values["Built-In (no install)"] = "B"
    elif tool_type == "I":
        col_values["Need to install"] = "I"

    for pk, (col, letter) in PRICING_TO_COL.items():
        if pk in pricing:
            col_values[col] = letter
    for cat, (col, letter) in CATEGORY_TO_COL.items():
        if cat in categories:
            col_values[col] = letter
    for plat in platforms:
        for key, (col, letter) in PLATFORM_TO_COL.items():
            if key.lower() in plat.lower():
                col_values[col] = letter
                break

    col_values["ID TAG"] = str(tool.get("ID Tag", "") or "")
    col_values["COMPANY"] = str(tool.get("Company", "") or "")
    col_values["PRODUCT/FEATURE NAME"] = str(tool.get("Product Name", "") or "")
    col_values["DESCRIPTION"] = str(tool.get("Description", "") or "")
    col_values["VENDOR'S WEBSITE DESC LINK"] = str(tool.get("Website", "") or "")
    col_values["INTERNAL NOTES"] = str(tool.get("AI Comments", "") or "")
    col_values["Data-Entry-Person NOTES"] = str(tool.get("Target Audience", "") or "")

    return [col_values.get(col, "") for col in data_cols]


# ── Sheets operations ─────────────────────────────────────────────────────────

def _ensure_ai_leads_sheet(service) -> int:
    spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for sheet in spreadsheet.get("sheets", []):
        if sheet["properties"]["title"] == "AI_LEADS":
            return sheet["properties"]["sheetId"]
    body = {"requests": [{"addSheet": {"properties": {"title": "AI_LEADS"}}}]}
    resp = service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body=body).execute()
    return resp["replies"][0]["addSheet"]["properties"]["sheetId"]


def _get_row_count(service) -> int:
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="AI_LEADS!A:AZ", majorDimension="ROWS"
    ).execute()
    return len(result.get("values", []))


def _write_data(service, all_values: list):
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range="AI_LEADS!A1",
        valueInputOption="USER_ENTERED", body={"values": all_values},
    ).execute()


def _append_data(service, rows: list, start_row: int):
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range=f"AI_LEADS!A{start_row}",
        valueInputOption="USER_ENTERED", body={"values": rows},
    ).execute()


def _apply_formatting(service, sheet_id: int, total_rows: int, num_data_cols: int,
                      tool_row_indices: list, *, is_first_run: bool = True):
    if total_rows == 0:
        return
    col_conf = num_data_cols
    col_match = num_data_cols + 1
    col_accepted = num_data_cols + 2
    col_rejected = num_data_cols + 3
    col_duplicate = num_data_cols + 4
    total_cols = num_data_cols + 5

    def _row_ranges(cs, ce):
        return [{"sheetId": sheet_id, "startRowIndex": r, "endRowIndex": r+1,
                 "startColumnIndex": cs, "endColumnIndex": ce} for r in tool_row_indices]

    requests = []
    if is_first_run:
        requests += [
            {"updateSheetProperties": {"properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}},
            {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": total_cols},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    "backgroundColor": {"red": 0.13, "green": 0.33, "blue": 0.58}, "wrapStrategy": "WRAP", "verticalAlignment": "MIDDLE"}},
                "fields": "userEnteredFormat(textFormat,backgroundColor,wrapStrategy,verticalAlignment)"}},
        ]

    requests.append({"addConditionalFormatRule": {"rule": {"ranges": _row_ranges(col_conf, col_conf+1),
        "gradientRule": {"minpoint": {"color": {"red": 0.96, "green": 0.26, "blue": 0.21}, "type": "NUMBER", "value": "0"},
            "midpoint": {"color": {"red": 1.0, "green": 0.84, "blue": 0.0}, "type": "NUMBER", "value": "50"},
            "maxpoint": {"color": {"red": 0.20, "green": 0.66, "blue": 0.33}, "type": "NUMBER", "value": "100"}}}, "index": 0}})

    for col_i in (col_accepted, col_rejected, col_duplicate):
        requests += [{"setDataValidation": {"range": r, "rule": {"condition": {"type": "BOOLEAN"}, "showCustomUi": True}}}
                     for r in _row_ranges(col_i, col_i+1)]

    service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={"requests": requests}).execute()


# ── Public entry point ────────────────────────────────────────────────────────

def run(config: dict, log: Callable[[str], None], base_dir: Path) -> bool:
    log("=" * 55)
    log("  Step 6  |  Score and push to AI_LEADS sheet")
    log("=" * 55)

    active_path = base_dir / "active_tools.csv"
    new_path = base_dir / "new_tools_complete.csv"

    if not active_path.exists():
        log("[ERROR] active_tools.csv not found.")
        return False
    if not new_path.exists():
        log("[ERROR] new_tools_complete.csv not found.")
        return False

    active_df = pd.read_csv(active_path)
    data_cols = list(active_df.columns)
    log(f"  Loaded {len(active_df)} existing tools. Building match index...")
    active_index = _build_index(active_df)

    new_df = pd.read_csv(new_path)
    log(f"  Loaded {len(new_df)} candidate tools. Scoring...")

    header = data_cols + [CONFIDENCE_HEADER, POTENTIAL_MATCH_HEADER, ACCEPTED_HEADER, REJECTED_HEADER, DUPLICATE_HEADER]
    rows = []
    tool_row_indices = []

    for _, tool in new_df.iterrows():
        tool_dict = tool.to_dict()
        confidence, top_hits = _score_tool(tool_dict, active_df, active_index)
        data_cells = _format_row(tool_dict, data_cols)
        tool_sheet_row = 1 + len(rows)
        tool_row_indices.append(tool_sheet_row)
        rows.append(data_cells + [confidence, "", False, False, False])

        for match_num, (score, name, _, active_idx) in enumerate(top_hits):
            match_label = f"#{match_num + 1}  —  {round(score * 100)}% match"
            active_row = active_df.iloc[active_idx]
            def _cell(val):
                if pd.isna(val): return ""
                if isinstance(val, bool): return "" if not val else str(val)
                return str(val).strip()
            match_data = [_cell(active_row[col]) if col in active_row.index else "" for col in data_cols]
            rows.append(match_data + ["", match_label, "", "", ""])

        label = "NEW" if confidence >= 70 else ("UNSURE" if confidence >= 45 else "DUP")
        log(f"  [{label} {confidence:3d}%]  {tool.get('Product Name', '')}")

    if str(os.getenv("DRY_RUN", "")).strip().lower() in ("1", "true", "yes", "y"):
        preview = base_dir / "ai_leads_preview.csv"
        pd.DataFrame([header] + rows).to_csv(preview, index=False, header=False)
        log(f"  DRY_RUN: wrote preview to {preview.name}")
        log("  Step 6 complete.")
        return True

    creds = _get_credentials()
    if not creds:
        log("[ERROR] No valid Google credentials.")
        return False

    service = build("sheets", "v4", credentials=creds)
    sheet_id = _ensure_ai_leads_sheet(service)
    existing_rows = _get_row_count(service)
    log(f"  AI_LEADS currently has {existing_rows} row(s).")

    if existing_rows == 0:
        _write_data(service, [header] + rows)
        row_offset = 0
        is_first_run = True
    else:
        _append_data(service, rows, start_row=existing_rows + 1)
        row_offset = existing_rows - 1
        is_first_run = False

    absolute_indices = [i + row_offset for i in tool_row_indices]
    _apply_formatting(service, sheet_id, len(rows), len(data_cols), absolute_indices, is_first_run=is_first_run)

    log(f"  Done. {len(new_df)} tools pushed to AI_LEADS.")
    log(f"  View: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
    log("  Step 6 complete.")
    return True
