import pandas as pd
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import os
from dotenv import load_dotenv
import logging
import numpy as np

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def authenticate_google_sheets():
    """
    Authenticate with Google Sheets API with write permissions
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"Token refresh failed: {e}")
                logger.info("Creating new authentication flow...")
                creds = None  # Reset creds to force new flow
        
        # If refresh failed or no valid creds, create new flow
        if not creds or not creds.valid:
            # You'll need to create credentials.json from Google Cloud Console
            if os.path.exists('credentials.json'):
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            else:
                logger.error("ERROR: credentials.json file not found!")
                logger.error("Please follow these steps:")
                logger.error("1. Go to Google Cloud Console")
                logger.error("2. Create a new project or select existing")
                logger.error("3. Enable Google Sheets API")
                logger.error("4. Create credentials (OAuth 2.0)")
                logger.error("5. Download as credentials.json")
                return None
        
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    return creds

def append_to_google_sheets(csv_file_path):
    """
    Append data from CSV file to Google Sheets
    """
    # Check if CSV file exists
    if not os.path.exists(csv_file_path):
        logger.error(f"CSV file not found: {csv_file_path}")
        return False
    
    # Authenticate
    creds = authenticate_google_sheets()
    if not creds:
        logger.error("Failed to authenticate with Google Sheets")
        return False
    
    service = build('sheets', 'v4', credentials=creds)
    
    # Spreadsheet details
    SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
    if not SPREADSHEET_ID:
        logger.error("SPREADSHEET_ID not found in environment variables")
        return False
    
    try:
        # Read the CSV file
        df = pd.read_csv(csv_file_path)
        logger.info(f"Loaded {len(df)} rows from {csv_file_path}")
        
        # Clean the data: replace NaN values with empty strings
        df_clean = df.fillna('')
        
        # Convert DataFrame to list of lists for Google Sheets
        # Skip the header row since we don't want to include column names
        values = []
        
        for _, row in df_clean.iterrows():
            # Convert each value to string and handle any remaining non-serializable values
            clean_row = []
            for value in row:
                if pd.isna(value) or value is None:
                    clean_row.append('')
                elif isinstance(value, (int, float)):
                    if pd.isna(value):
                        clean_row.append('')
                    else:
                        clean_row.append(str(value))
                else:
                    clean_row.append(str(value))
            values.append(clean_row)
        
        logger.info(f"Prepared {len(values)} data rows (excluding header) for Google Sheets")
        
        # Prepare the append request
        body = {
            'values': values
        }
        
        # First, get the current data to find the last row
        sheet_metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        sheet_name = sheet_metadata['sheets'][0]['properties']['title']  # Get the first sheet name
        
        # Get current data to determine where to append
        current_data = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f'{sheet_name}!A:A'
        ).execute()
        
        current_rows = len(current_data.get('values', []))
        next_row = current_rows + 1
        
        # Append the data to the sheet starting from the next available row
        result = service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f'{sheet_name}!A{next_row}',  # Start from the next available row
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()
        
        logger.info(f"Successfully appended {len(df)} rows to Google Sheets")
        logger.info(f"Updated range: {result.get('updates', {}).get('updatedRange', 'Unknown')}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error appending to Google Sheets: {e}")
        return False

def main():
    """
    Main function to append formatted results to Google Sheets
    """
    logger.info("Starting Google Sheets append process...")
    
    # Try to append from active_tools.csv first
    if os.path.exists('ready_for_import.csv'):
        logger.info("Found ready_for_import.csv, appending to Google Sheets...")
        success = append_to_google_sheets('ready_for_import.csv')
        if success:
            logger.info("Successfully appended active_tools.csv to Google Sheets")
        else:
            logger.error("Failed to append active_tools.csv to Google Sheets")
            return False
    else:
        logger.warning("ready_for_import.csv not found")
        return False
    
    logger.info("Google Sheets append process completed successfully!")
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1) 