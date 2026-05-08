"""
load_google_sheets_with_formatting.py
--------------------------------------
Reads the main tools database from Google Sheets and builds two local CSVs:

  active_tools.csv
    - All rows from the main Data tab  (gid=0)
    - All rows from AI_Accepted        (tools approved by a human reviewer)
    - All rows from AI_LEADS           (tools still pending review — included so
                                        the AI search won't re-discover them)

  removed_tools.csv
    - All rows from AI_Rejected  +  a "Reason" column  →  human rejection reason
    - All rows from AI_Duplicates  +  a "Reason" column  →  auto-built duplicate note

The "Reason" column is always the last column in removed_tools.csv.
"""

import sys
import re
import pandas as pd
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import os
from dotenv import load_dotenv

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

COLUMNS_TO_DROP = [
    'ENTERED BY',
    'AUDITED BY',
    'READY TO PUT IN TOOL',
    'Unnamed: 35',
]

# Column header substrings used to locate special columns in AI sheets
_REJECTION_REASON_SUBSTR = "Rejection Reason"
_POTENTIAL_MATCH_SUBSTR  = "Potential Match"
_CONFIDENCE_SUBSTR       = "Confidence Score"
_ACCEPTED_SUBSTR         = "Accepted"
_REJECTED_SUBSTR         = "Rejected"
_DUPLICATE_SUBSTR        = "Duplicate"

# Final column name in removed_tools.csv
REASON_COL = "Reason"


# ── Auth ──────────────────────────────────────────────────────────────────────

def authenticate_google_sheets():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"  Saved token could not be refreshed ({e}).")
                print("  A new sign-in will be requested.")
                creds = None

        if not creds or not creds.valid:
            if not os.path.exists('credentials.json'):
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
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as fh:
            fh.write(creds.to_json())
        print("  Sign-in successful. Token saved to token.json.")

    return creds


# ── Generic sheet reader ───────────────────────────────────────────────────────

def read_sheet_raw(service, spreadsheet_id: str, sheet_name: str) -> list[list]:
    """Returns all rows (including header) as a list of lists, or [] if sheet missing."""
    try:
        result = (
            service.spreadsheets().values()
            .get(spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'!A:AZ")
            .execute()
        )
        return result.get('values', [])
    except Exception as e:
        msg = str(e)
        if "Unable to parse range" in msg or "not found" in msg.lower():
            return []
        print(f"  Warning: could not read sheet '{sheet_name}': {e}")
        return []


def sheet_exists(service, spreadsheet_id: str, name: str) -> bool:
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    return any(s['properties']['title'] == name for s in meta.get('sheets', []))


def _find_col(headers: list, substring: str) -> int:
    """Returns 0-based index of first header whose text contains substring, or -1."""
    for i, h in enumerate(headers):
        if substring.lower() in str(h).lower():
            return i
    return -1


def raw_to_df(rows: list[list]) -> pd.DataFrame | None:
    """Convert raw sheet rows to a DataFrame (aligned to header width)."""
    if not rows or len(rows) < 1:
        return None
    headers = rows[0]
    n_cols  = len(headers)
    padded  = [row + [''] * (n_cols - len(row)) for row in rows[1:]]
    if not padded:
        return pd.DataFrame(columns=headers)
    return pd.DataFrame(padded, columns=headers)


# ── Main data tab ─────────────────────────────────────────────────────────────

def load_main_tab(service, spreadsheet_id: str) -> pd.DataFrame | None:
    """Loads the primary Data tab (gid=0) and returns a cleaned DataFrame."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    target_sheet_name = None
    for sheet in meta['sheets']:
        if sheet['properties']['sheetId'] == 0:
            target_sheet_name = sheet['properties']['title']
            break

    if not target_sheet_name:
        print("ERROR: Could not find a sheet tab with gid=0.")
        return None

    print(f"  Reading main Data tab: '{target_sheet_name}' (gid=0)")
    rows = read_sheet_raw(service, spreadsheet_id, target_sheet_name)
    if not rows or len(rows) < 2:
        print("ERROR: Main Data tab appears to be empty or has only a header row.")
        return None

    headers = rows[0]
    n_cols  = len(headers)
    padded  = [row + [''] * (n_cols - len(row)) for row in rows[1:]]
    df = pd.DataFrame(padded, columns=headers)

    # Drop housekeeping columns
    cols_to_drop = [c for c in COLUMNS_TO_DROP if c in df.columns]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)
        print(f"  Dropped columns: {cols_to_drop}")

    # Remove fully-empty rows
    empty_as_nan = df.replace(r'^\s*$', pd.NA, regex=True)
    df = empty_as_nan.dropna(how='all').reset_index(drop=True)

    print(f"  Loaded {len(df)} tools from main Data tab.")
    return df


# ── AI_Accepted ───────────────────────────────────────────────────────────────

def load_ai_accepted(service, spreadsheet_id: str, data_cols: list) -> pd.DataFrame:
    """
    Returns a DataFrame (columns = data_cols) with all rows from AI_Accepted.
    Returns an empty DataFrame if the sheet does not exist or is empty.
    """
    rows = read_sheet_raw(service, spreadsheet_id, "AI_Accepted")
    df   = raw_to_df(rows)
    if df is None or df.empty:
        print("  AI_Accepted: sheet not found or empty — skipped.")
        return pd.DataFrame(columns=data_cols)

    # Keep only data_cols that exist in this sheet; fill missing ones with ''
    df = _align_columns(df, data_cols)
    print(f"  Loaded {len(df)} tools from AI_Accepted.")
    return df


# ── AI_LEADS (pending-review tools) ──────────────────────────────────────────

def load_ai_leads(service, spreadsheet_id: str, data_cols: list) -> pd.DataFrame:
    """
    Returns a DataFrame (columns = data_cols) with all rows from AI_LEADS.
    Extra scoring/checkbox columns are stripped out.
    Only rows that haven't been actioned yet are included (no checkbox ticked).
    Returns empty DataFrame if sheet not present.
    """
    rows = read_sheet_raw(service, spreadsheet_id, "AI_LEADS")
    df   = raw_to_df(rows)
    if df is None or df.empty:
        print("  AI_LEADS: sheet not found or empty — skipped.")
        return pd.DataFrame(columns=data_cols)

    headers = list(df.columns)

    # Find the first "extra" column (Confidence / Accepted / etc.) to know where data ends
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
    print(f"  Loaded {len(df)} tools from AI_LEADS (pending review).")
    return df


# ── AI_Rejected ───────────────────────────────────────────────────────────────

def load_ai_rejected(service, spreadsheet_id: str, data_cols: list) -> pd.DataFrame:
    """
    Returns a DataFrame (columns = data_cols + [REASON_COL]) from AI_Rejected.
    The Reason is taken from the 'Rejection Reason' column (human-entered).
    """
    rows = read_sheet_raw(service, spreadsheet_id, "AI_Rejected")
    df   = raw_to_df(rows)
    if df is None or df.empty:
        print("  AI_Rejected: sheet not found or empty — skipped.")
        return pd.DataFrame(columns=data_cols + [REASON_COL])

    headers = list(df.columns)
    rej_col = _find_col(headers, _REJECTION_REASON_SUBSTR)

    reason_series = (
        df.iloc[:, rej_col].fillna("").astype(str).str.strip()
        if rej_col >= 0
        else pd.Series([""] * len(df))
    )
    reason_series = reason_series.apply(
        lambda r: r if r else "Rejected during manual review"
    )

    df_data = _align_columns(df, data_cols)
    df_data[REASON_COL] = reason_series.values

    print(f"  Loaded {len(df_data)} tools from AI_Rejected.")
    return df_data


# ── AI_Duplicates ──────────────────────────────────────────────────────────────

def load_ai_duplicates(service, spreadsheet_id: str, data_cols: list) -> pd.DataFrame:
    """
    Returns a DataFrame (columns = data_cols + [REASON_COL]) from AI_Duplicates.
    The Reason is auto-built: "Same or similar tool already exists → {match names}"
    """
    rows = read_sheet_raw(service, spreadsheet_id, "AI_Duplicates")
    df   = raw_to_df(rows)
    if df is None or df.empty:
        print("  AI_Duplicates: sheet not found or empty — skipped.")
        return pd.DataFrame(columns=data_cols + [REASON_COL])

    headers = list(df.columns)
    match_col = _find_col(headers, _POTENTIAL_MATCH_SUBSTR)

    def _build_reason(match_text: str) -> str:
        match_text = (match_text or "").strip()
        if not match_text or match_text.lower() == "no significant match found":
            return "Same or similar tool already exists in main database"
        # The Potential Match column contains numbered lines like:
        #   1. Read&Write Gold (Texthelp) — 82%
        # Extract just the tool names for readability.
        names = []
        for line in match_text.splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip leading "1. " numbering
            line = re.sub(r"^\d+\.\s*", "", line)
            # Strip trailing " — 82%" percentage
            line = re.sub(r"\s*—\s*\d+%\s*$", "", line).strip()
            if line:
                names.append(line)
        if names:
            return "Same or similar tool already exists in main database → " + "; ".join(names)
        return "Same or similar tool already exists in main database"

    if match_col >= 0:
        reason_series = df.iloc[:, match_col].fillna("").astype(str).apply(_build_reason)
    else:
        reason_series = pd.Series(
            ["Same or similar tool already exists in main database"] * len(df)
        )

    df_data = _align_columns(df, data_cols)
    df_data[REASON_COL] = reason_series.values

    print(f"  Loaded {len(df_data)} tools from AI_Duplicates.")
    return df_data


# ── Column alignment helper ────────────────────────────────────────────────────

def _align_columns(df: pd.DataFrame, target_cols: list) -> pd.DataFrame:
    """
    Returns a DataFrame containing exactly target_cols in that order.
    Columns present in df but not in target_cols are dropped.
    Columns in target_cols but missing from df are added as empty strings.
    """
    out = pd.DataFrame(index=df.index)
    for col in target_cols:
        if col in df.columns:
            out[col] = df[col]
        else:
            out[col] = ""
    return out.reset_index(drop=True)


def _remove_empty_rows(df: pd.DataFrame) -> pd.DataFrame:
    empty_as_nan = df.replace(r'^\s*$', pd.NA, regex=True)
    return empty_as_nan.dropna(how='all').reset_index(drop=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Loading tools database from Google Sheets")
    print("=" * 60)

    creds = authenticate_google_sheets()
    if not creds:
        sys.exit(1)

    service        = build('sheets', 'v4', credentials=creds)
    spreadsheet_id = os.getenv('SPREADSHEET_ID')
    if not spreadsheet_id:
        print("ERROR: SPREADSHEET_ID not set in .env")
        sys.exit(1)

    # ── Step 1: Main Data tab (establishes the canonical column list) ─────────
    main_df = load_main_tab(service, spreadsheet_id)
    if main_df is None:
        print("FAILED: could not load main Data tab.")
        sys.exit(1)

    data_cols = list(main_df.columns)

    # ── Step 2: AI_Accepted + AI_LEADS  →  append to active_tools ────────────
    accepted_df = load_ai_accepted(service, spreadsheet_id, data_cols)
    leads_df    = load_ai_leads(service, spreadsheet_id, data_cols)

    active_df = pd.concat(
        [main_df, accepted_df, leads_df],
        ignore_index=True,
    )
    active_df = _remove_empty_rows(active_df)

    active_df.to_csv('active_tools.csv', index=False)
    print(
        f"\nSaved {len(active_df)} total active tools to active_tools.csv"
        f"  ({len(main_df)} main + {len(accepted_df)} AI_Accepted"
        f" + {len(leads_df)} AI_LEADS)"
    )

    # ── Step 3: AI_Rejected + AI_Duplicates  →  removed_tools ────────────────
    rejected_df   = load_ai_rejected(service, spreadsheet_id, data_cols)
    duplicates_df = load_ai_duplicates(service, spreadsheet_id, data_cols)

    removed_df = pd.concat(
        [rejected_df, duplicates_df],
        ignore_index=True,
    )
    removed_df = _remove_empty_rows(removed_df)

    # Ensure the Reason column is always present (even if both sheets are empty)
    if REASON_COL not in removed_df.columns:
        removed_df[REASON_COL] = ""

    removed_df.to_csv('removed_tools.csv', index=False)
    print(
        f"Saved {len(removed_df)} removed tools to removed_tools.csv"
        f"  ({len(rejected_df)} AI_Rejected + {len(duplicates_df)} AI_Duplicates)"
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
