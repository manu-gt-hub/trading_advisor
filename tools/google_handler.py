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
    creds_json = os.environ.get("GDRIVE_CREDENTIALS_JSON")
    if not creds_json:
        raise Exception("No se encontró la variable de entorno GDRIVE_CREDENTIALS_JSON")
    creds_dict = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=credentials)
    return service

def load_data():
    service = get_drive_service()
    file_id = os.environ.get("GDRIVE_FILE_ID")
    if not file_id:
        raise Exception("No se encontró la variable de entorno GDRIVE_FILE_ID")
    try:
        # Cambiar get_media por export_media con mimeType CSV
        request = service.files().export_media(fileId=file_id, mimeType='text/csv')
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

        file_bytes = fh.getvalue()

        with open("backup_drive.csv", "wb") as f:
            f.write(file_bytes)

        fh2 = io.BytesIO(file_bytes)
        df = pd.read_csv(fh2)
        print(f"✅ CSV cargado desde Google Drive (Google Sheets export) con {len(df)} filas.")
    except Exception as e:
        print(f"📄 CSV no encontrado en Drive o error: {e}. Creando uno nuevo.")
        df = pd.DataFrame(columns=["value", "date"])
    return df


def add_row(df):
    now_madrid = datetime.now(ZoneInfo("Europe/Madrid"))
    
    nueva_fila = {
        "value": 143.23,
        "date": now_madrid.strftime("%Y-%m-%d %H:%M:%S")
    }
    print(f"📝 Añadiendo nueva fila: {nueva_fila}")
    return pd.concat([df, pd.DataFrame([nueva_fila])], ignore_index=True)

def save_dataframe(df):
    service = get_drive_service()
    file_id = os.environ.get("GDRIVE_FILE_ID")
    if not file_id:
        raise Exception("No se encontró la variable de entorno GDRIVE_FILE_ID")
    temp_csv = "temp_data.csv"
    df.to_csv(temp_csv, index=False)
    media = MediaFileUpload(temp_csv, mimetype='text/csv')
    updated_file = service.files().update(
        fileId=file_id,
        media_body=media
    ).execute()
    os.remove(temp_csv)
    print(f"💾 CSV guardado en Google Drive, archivo ID: {updated_file['id']}, filas totales: {len(df)}")
