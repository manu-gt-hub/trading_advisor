import pandas as pd
import os
import io
import json
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

def obtener_servicio_drive():
    creds_json = os.environ.get("GDRIVE_CREDENTIALS_JSON")
    if not creds_json:
        raise Exception("No se encontró la variable de entorno GDRIVE_CREDENTIALS_JSON")
    creds_dict = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=credentials)
    return service

def cargar_o_crear_dataframe():
    service = obtener_servicio_drive()
    file_id = os.environ.get("GDRIVE_FILE_ID")
    if not file_id:
        raise Exception("No se encontró la variable de entorno GDRIVE_FILE_ID")
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        df = pd.read_csv(fh)
        print("✅ CSV cargado desde Google Drive.")
    except Exception as e:
        print(f"📄 CSV no encontrado en Drive o error: {e}. Creando uno nuevo.")
        df = pd.DataFrame(columns=["value", "date"])
    return df

def añadir_fila(df):
    nueva_fila = {
        "value": 143.23,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    return pd.concat([df, pd.DataFrame([nueva_fila])], ignore_index=True)

def guardar_dataframe(df):
    service = obtener_servicio_drive()
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
    print(f"💾 CSV guardado en Google Drive, archivo ID: {updated_file['id']}")
