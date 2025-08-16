import pandas as pd
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import os
from dotenv import load_dotenv

load_dotenv()

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def authenticate_google_sheets():
    """
    Authenticate with Google Sheets API
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
                print(f"Token refresh failed: {e}")
                print("Creating new authentication flow...")
                creds = None  # Reset creds to force new flow
        
        # If refresh failed or no valid creds, create new flow
        if not creds or not creds.valid:
            # You'll need to create credentials.json from Google Cloud Console
            if os.path.exists('credentials.json'):
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            else:
                print("ERROR: credentials.json file not found!")
                print("Please follow these steps:")
                print("1. Go to Google Cloud Console")
                print("2. Create a new project or select existing")
                print("3. Enable Google Sheets API")
                print("4. Create credentials (OAuth 2.0)")
                print("5. Download as credentials.json")
                return None
        
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    return creds

def detect_strikethrough_tools():
    """
    Detect tools with strikethrough formatting using Google Sheets API
    """
    # Authenticate
    creds = authenticate_google_sheets()
    if not creds:
        return None, None
    
    service = build('sheets', 'v4', credentials=creds)
    
    # Spreadsheet details
    SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
    RANGE_NAME = 'A:AH'  # Use range without sheet name
    
    try:
        # Get the spreadsheet data with formatting
        sheet = service.spreadsheets()
        
        # Get values
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        values = result.get('values', [])
        
        # Get formatting information
        result_format = sheet.get(spreadsheetId=SPREADSHEET_ID, 
                                includeGridData=True,
                                ranges=[RANGE_NAME]).execute()
        
        # Extract formatting data
        sheets_data = result_format.get('sheets', [])
        if not sheets_data:
            print("No sheet data found")
            return None, None
            
        grid_data = sheets_data[0].get('data', [])
        if not grid_data:
            print("No grid data found")
            return None, None
        
        row_data = grid_data[0].get('rowData', [])
        
        # Create DataFrame from values
        df = pd.DataFrame(values[1:], columns=values[0] if values else [])
        
        # Drop unwanted columns
        columns_to_drop = [
            'ENTERED BY', 
            'AUDITED BY',
            'READY TO PUT IN TOOL',
            'Unnamed: 35'
        ]
        
        existing_columns_to_drop = [col for col in columns_to_drop if col in df.columns]
        if existing_columns_to_drop:
            df = df.drop(columns=existing_columns_to_drop)
            print(f"Dropped columns: {existing_columns_to_drop}")
        
        # Find the DESCRIPTION column index
        description_col_idx = None
        if len(values) > 0:
            headers = values[0]
            for idx, header in enumerate(headers):
                if header == 'DESCRIPTION':
                    description_col_idx = idx
                    break
        
        if description_col_idx is None:
            print("DESCRIPTION column not found!")
            return None, None
        
        print(f"DESCRIPTION column found at index: {description_col_idx}")
        
        # Find strikethrough rows by checking only the DESCRIPTION column
        strikethrough_rows = []
        
        for row_idx, row in enumerate(row_data[1:], 1):  # Skip header row
            if 'values' in row and len(row['values']) > description_col_idx:
                # Check only the DESCRIPTION column (at description_col_idx)
                desc_cell = row['values'][description_col_idx]
                
                if 'userEnteredFormat' in desc_cell:
                    text_format = desc_cell['userEnteredFormat'].get('textFormat', {})
                    if text_format.get('strikethrough', False):
                        strikethrough_rows.append(row_idx - 1)  # Adjust for DataFrame indexing
                        print(f"Row {row_idx - 1}: DESCRIPTION has strikethrough - marking entire row as removed")
        
        print(f"Found {len(strikethrough_rows)} rows with strikethrough formatting")
        print(f"Strikethrough row indices: {strikethrough_rows[:10]}...")  # Show first 10
        
        # Split the data
        if strikethrough_rows:
            removed_tools = df.iloc[strikethrough_rows].copy()
            active_tools = df.drop(index=strikethrough_rows).copy()
            
            print(f"Active tools: {len(active_tools)} rows")
            print(f"Removed tools: {len(removed_tools)} rows")
            
            return active_tools, removed_tools
        else:
            print("No strikethrough formatting found")
            return df, pd.DataFrame()
            
    except Exception as e:
        print(f"Error accessing Google Sheets API: {e}")
        return None, None



def main():
    """
    Main function to detect and separate strikethrough tools
    """
    print("Attempting to detect strikethrough formatting...")
    
    active_tools, removed_tools = detect_strikethrough_tools()
    
    if active_tools is not None:
        # Save the separated data
        active_tools.to_csv('active_tools.csv', index=False)
        if len(removed_tools) > 0:
            removed_tools.to_csv('removed_tools.csv', index=False)
            print(f"Saved {len(removed_tools)} removed tools to 'removed_tools.csv'")
        
        print(f"Saved {len(active_tools)} active tools to 'active_tools.csv'")
        
        return active_tools, removed_tools
    else:
        print("Failed to load data")
        return None, None

if __name__ == "__main__":
    active, removed = main() 