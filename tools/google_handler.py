import pandas as pd
import os
import io
import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

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

def load_data():
    # Load CSV data exported from Google Sheets on Google Drive
    service = get_drive_service()
    file_id = os.environ.get("GDRIVE_FILE_ID")
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

        # Save a local backup of the downloaded CSV
        with open("backup_drive.csv", "wb") as f:
            f.write(file_bytes)

        fh2 = io.BytesIO(file_bytes)
        df = pd.read_csv(fh2)
        print(f"✅ CSV loaded from Google Drive (Google Sheets export) with {len(df)} rows.")
    except Exception as e:
        print(f"📄 CSV not found on Drive or error occurred: {e}. Creating a new empty DataFrame.")
        df = pd.DataFrame(columns=["value", "date"])
    return df

def add_row(df):
    # Add a new row with current datetime (Europe/Madrid timezone) and fixed value
    now_madrid = datetime.now(ZoneInfo("Europe/Madrid"))
    
    new_row = {
        "value": 143.23,
        "date": now_madrid.strftime("%Y-%m-%d %H:%M:%S")
    }
    print(f"📝 Adding new row: {new_row}")
    return pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

def save_dataframe(df):
    # Save the updated DataFrame back to Google Drive as a CSV file
    service = get_drive_service()
    file_id = os.environ.get("GDRIVE_FILE_ID")
    if not file_id:
        raise Exception("Environment variable GDRIVE_FILE_ID not found")
    temp_csv = "temp_data.csv"
    df.to_csv(temp_csv, index=False)
    media = MediaFileUpload(temp_csv, mimetype='text/csv')
    updated_file = service.files().update(
        fileId=file_id,
        media_body=media
    ).execute()
    os.remove(temp_csv)
    print(f"💾 CSV saved to Google Drive, file ID: {updated_file['id']}, total rows: {len(df)}")
