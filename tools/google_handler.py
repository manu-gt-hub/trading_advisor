import pandas as pd
import os
import io
import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from datetime import datetime
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env file only if not running in production (e.g., GitHub Actions)
if not os.getenv("GITHUB_ACTIONS"):  # This var is auto-set in GitHub Actions
    load_dotenv()

def get_drive_service():
    # Retrieve Google Drive service client using credentials from environment variable
    creds_json = os.environ.get("GDRIVE_CREDENTIALS_JSON")
    if not creds_json:
        raise Exception("Environment variable GDRIVE_CREDENTIALS_JSON not found")
    creds_dict = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=credentials)
    return service

def load_data(file_id):
    # Load CSV data exported from Google Sheets on Google Drive
    service = get_drive_service()
    
    if not file_id:
        raise Exception("Environment variable GDRIVE_FILE_ID not found")
    try:
        # Use export_media to export Google Sheets as CSV
        request = service.files().export_media(fileId=file_id, mimeType='text/csv')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

        file_bytes = fh.getvalue()

        df = pd.read_csv(io.BytesIO(file_bytes))
        logger.info(f"✅ CSV loaded from Google Drive (Google Sheets export) with {len(df)} rows.")

    except Exception as e:

        logger.error(f"❌ CSV not found on Drive or error occurred: {e}.")
        return None
    return df

def update_transactions(df_analysis, df_transactions, revenue_percentage):
    # Make a copy to avoid changing the original dataframe
    df_transactions = df_transactions.copy()
    
    # Loop through each row in the transactions dataframe
    for idx, row in df_transactions.iterrows():
        symbol = row['symbol']
        buy_value = row['buy_value']
        
        # Skip if already sold
        if pd.notna(row.get('sell_value')):
            continue
        
        # Look for the symbol in the analysis dataframe
        analysis_row = df_analysis[df_analysis['symbol'] == symbol]
        
        if not analysis_row.empty:
            current_price = analysis_row.iloc[0]['current_price']
            target_price = buy_value * (1 + float(revenue_percentage) / 100)
            
            if current_price >= target_price:
                sell_date = datetime.today().date()
                buy_date = pd.to_datetime(row['buy_date']).date()
                days_diff = (sell_date - buy_date).days
                percentage_benefit = ((current_price - buy_value) / buy_value) * 100

                # Update the transaction record
                df_transactions.at[idx, 'sell_value'] = round(current_price, 2)
                df_transactions.at[idx, 'sell_date'] = sell_date
                df_transactions.at[idx, 'buy_sell_days_diff'] = days_diff
                df_transactions.at[idx, 'percentage_benefit'] = round(percentage_benefit, 2)

    return df_transactions


def save_dataframe_file_id(df, file_id):
    """
    Updates an existing CSV file on Google Drive using in-memory upload (no temp file).
    Fully Windows-compatible.
    """
    service = get_drive_service()
    logger.info("saving data into google drive...")

    if not file_id:
        raise Exception("❌ file_id not provided or environment variable GDRIVE_FILE_ID is missing.")

    # Write CSV to an in-memory bytes buffer
    csv_buffer = io.BytesIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)  # Rewind to start

    media = MediaIoBaseUpload(csv_buffer, mimetype='text/csv')

    updated_file = service.files().update(
        fileId=file_id,
        media_body=media
    ).execute()

