"""
pipeline/step1_load_sheets.py
-------------------------------
Importable wrapper around load_google_sheets_with_formatting logic.
On Vercel, credentials come from base64-encoded env vars instead of local files.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Callable

import pandas as pd
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

COLUMNS_TO_DROP = [
    "ENTERED BY",
    "AUDITED BY",
    "READY TO PUT IN TOOL",
    "Unnamed: 35",
]

REASON_COL = "Reason"
_REJECTION_REASON_SUBSTR = "Rejection Reason"
_POTENTIAL_MATCH_SUBSTR = "Potential Match"
_CONFIDENCE_SUBSTR = "Confidence Score"
_ACCEPTED_SUBSTR = "Accepted"


# ── Auth ──────────────────────────────────────────────────────────────────────

def _get_credentials() -> Credentials | None:
    """
    Returns valid Google credentials.
    Prefers TOKEN_JSON env var (base64) for headless/Vercel environments.
    Falls back to token.json on disk for local runs.
    """
    creds = None

    token_b64 = os.getenv("TOKEN_JSON_B64")
    if token_b64:
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


# ── Generic helpers ───────────────────────────────────────────────────────────

def _read_sheet_raw(service, spreadsheet_id: str, sheet_name: str) -> list:
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'!A:AZ")
            .execute()
        )
        return result.get("values", [])
    except Exception as e:
        msg = str(e)
        if "Unable to parse range" in msg or "not found" in msg.lower():
            return []
        return []


def _raw_to_df(rows: list) -> pd.DataFrame | None:
    if not rows:
        return None
    headers = rows[0]
    n_cols = len(headers)
    padded = [row + [""] * (n_cols - len(row)) for row in rows[1:]]
    if not padded:
        return pd.DataFrame(columns=headers)
    return pd.DataFrame(padded, columns=headers)


def _find_col(headers: list, substring: str) -> int:
    for i, h in enumerate(headers):
        if substring.lower() in str(h).lower():
            return i
    return -1


def _align_columns(df: pd.DataFrame, target_cols: list) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for col in target_cols:
        out[col] = df[col] if col in df.columns else ""
    return out.reset_index(drop=True)


def _remove_empty_rows(df: pd.DataFrame) -> pd.DataFrame:
    empty_as_nan = df.replace(r"^\s*$", pd.NA, regex=True)
    return empty_as_nan.dropna(how="all").reset_index(drop=True)


# ── Sheet loaders ─────────────────────────────────────────────────────────────

def _load_main_tab(service, spreadsheet_id: str, log: Callable) -> pd.DataFrame | None:
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    target = None
    for sheet in meta["sheets"]:
        if sheet["properties"]["sheetId"] == 0:
            target = sheet["properties"]["title"]
            break
    if not target:
        log("[ERROR] Could not find sheet tab with gid=0.")
        return None

    log(f"  Reading main Data tab: '{target}'")
    rows = _read_sheet_raw(service, spreadsheet_id, target)
    if not rows or len(rows) < 2:
        log("[ERROR] Main Data tab is empty.")
        return None

    headers = rows[0]
    n_cols = len(headers)
    padded = [row + [""] * (n_cols - len(row)) for row in rows[1:]]
    df = pd.DataFrame(padded, columns=headers)

    cols_to_drop = [c for c in COLUMNS_TO_DROP if c in df.columns]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)

    df = _remove_empty_rows(df)
    log(f"  Loaded {len(df)} tools from main Data tab.")
    return df


def _load_ai_accepted(service, spreadsheet_id: str, data_cols: list, log: Callable) -> pd.DataFrame:
    rows = _read_sheet_raw(service, spreadsheet_id, "AI_Accepted")
    df = _raw_to_df(rows)
    if df is None or df.empty:
        log("  AI_Accepted: not found or empty — skipped.")
        return pd.DataFrame(columns=data_cols)
    df = _align_columns(df, data_cols)
    log(f"  Loaded {len(df)} tools from AI_Accepted.")
    return df


def _load_ai_leads(service, spreadsheet_id: str, data_cols: list, log: Callable) -> pd.DataFrame:
    rows = _read_sheet_raw(service, spreadsheet_id, "AI_LEADS")
    df = _raw_to_df(rows)
    if df is None or df.empty:
        log("  AI_LEADS: not found or empty — skipped.")
        return pd.DataFrame(columns=data_cols)

    headers = list(df.columns)
    extra_cols_idx = [
        _find_col(headers, s)
        for s in (_CONFIDENCE_SUBSTR, _ACCEPTED_SUBSTR)
        if _find_col(headers, s) >= 0
    ]
    if extra_cols_idx:
        first_extra = min(extra_cols_idx)
        df = df.iloc[:, :first_extra].copy()
        df.columns = headers[:first_extra]

    df = _align_columns(df, data_cols)
    log(f"  Loaded {len(df)} tools from AI_LEADS.")
    return df


def _load_ai_rejected(service, spreadsheet_id: str, data_cols: list, log: Callable) -> pd.DataFrame:
    rows = _read_sheet_raw(service, spreadsheet_id, "AI_Rejected")
    df = _raw_to_df(rows)
    if df is None or df.empty:
        log("  AI_Rejected: not found or empty — skipped.")
        return pd.DataFrame(columns=data_cols + [REASON_COL])

    headers = list(df.columns)
    rej_col = _find_col(headers, _REJECTION_REASON_SUBSTR)
    reason_series = (
        df.iloc[:, rej_col].fillna("").astype(str).str.strip()
        if rej_col >= 0
        else pd.Series([""] * len(df))
    )
    reason_series = reason_series.apply(lambda r: r if r else "Rejected during manual review")
    df_data = _align_columns(df, data_cols)
    df_data[REASON_COL] = reason_series.values
    log(f"  Loaded {len(df_data)} tools from AI_Rejected.")
    return df_data


def _load_ai_duplicates(service, spreadsheet_id: str, data_cols: list, log: Callable) -> pd.DataFrame:
    rows = _read_sheet_raw(service, spreadsheet_id, "AI_Duplicates")
    df = _raw_to_df(rows)
    if df is None or df.empty:
        log("  AI_Duplicates: not found or empty — skipped.")
        return pd.DataFrame(columns=data_cols + [REASON_COL])

    headers = list(df.columns)
    match_col = _find_col(headers, _POTENTIAL_MATCH_SUBSTR)

    def _build_reason(match_text: str) -> str:
        match_text = (match_text or "").strip()
        if not match_text or match_text.lower() == "no significant match found":
            return "Same or similar tool already exists in main database"
        names = []
        for line in match_text.splitlines():
            line = re.sub(r"^\d+\.\s*", "", line.strip())
            line = re.sub(r"\s*—\s*\d+%\s*$", "", line).strip()
            if line:
                names.append(line)
        if names:
            return "Same or similar tool already exists → " + "; ".join(names)
        return "Same or similar tool already exists in main database"

    if match_col >= 0:
        reason_series = df.iloc[:, match_col].fillna("").astype(str).apply(_build_reason)
    else:
        reason_series = pd.Series(["Same or similar tool already exists in main database"] * len(df))

    df_data = _align_columns(df, data_cols)
    df_data[REASON_COL] = reason_series.values
    log(f"  Loaded {len(df_data)} tools from AI_Duplicates.")
    return df_data


# ── Public entry point ────────────────────────────────────────────────────────

def run(config: dict, log: Callable[[str], None], base_dir: Path) -> bool:
    """
    Loads the Google Sheets database and writes active_tools.csv + removed_tools.csv
    to base_dir. Returns True on success, False on failure.
    """
    log("=" * 55)
    log("  Step 1  |  Loading tools database from Google Sheets")
    log("=" * 55)

    creds = _get_credentials()
    if not creds:
        log("[ERROR] No valid Google credentials found.")
        log("  Set TOKEN_JSON_B64 env var (base64-encoded token.json contents).")
        return False

    service = build("sheets", "v4", credentials=creds)
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    if not spreadsheet_id:
        log("[ERROR] SPREADSHEET_ID not set in environment.")
        return False

    main_df = _load_main_tab(service, spreadsheet_id, log)
    if main_df is None:
        return False

    data_cols = list(main_df.columns)

    accepted_df = _load_ai_accepted(service, spreadsheet_id, data_cols, log)
    leads_df = _load_ai_leads(service, spreadsheet_id, data_cols, log)

    active_df = pd.concat([main_df, accepted_df, leads_df], ignore_index=True)
    active_df = _remove_empty_rows(active_df)
    active_df.to_csv(base_dir / "active_tools.csv", index=False)
    log(f"  Saved {len(active_df)} active tools to active_tools.csv")

    rejected_df = _load_ai_rejected(service, spreadsheet_id, data_cols, log)
    duplicates_df = _load_ai_duplicates(service, spreadsheet_id, data_cols, log)

    removed_df = pd.concat([rejected_df, duplicates_df], ignore_index=True)
    removed_df = _remove_empty_rows(removed_df)
    if REASON_COL not in removed_df.columns:
        removed_df[REASON_COL] = ""
    removed_df.to_csv(base_dir / "removed_tools.csv", index=False)
    log(f"  Saved {len(removed_df)} removed tools to removed_tools.csv")

    log("  Step 1 complete.")
    return True
