import os
import json
import pandas as pd
from dotenv import dotenv_values
import pytest
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from google_handler import get_drive_service, load_data

# Get absolute path to the env path
current_dir = os.path.dirname(__file__)
path = os.path.join(current_dir, '..', '.env')
env_path = os.path.abspath(path)

def test_get_drive_service_real():
    """
    Real test connecting to Google Drive service using real credentials from .env.
    """
    # Reload .env on every run
    env = dotenv_values(env_path)  # Assumes test/ is sibling to .env
    os.environ["GDRIVE_CREDENTIALS_JSON"] = env.get("GDRIVE_CREDENTIALS_JSON", "")
    os.environ["GDRIVE_FILE_ID"] = env.get("GDRIVE_FILE_ID", "")

    assert os.environ["GDRIVE_CREDENTIALS_JSON"], "GDRIVE_CREDENTIALS_JSON is not set"
    assert os.environ["GDRIVE_FILE_ID"], "GDRIVE_FILE_ID is not set"

    service = get_drive_service()
    files_list = service.files().list(pageSize=1).execute()

    assert "files" in files_list


def test_load_data_real():
    """
    Real test loading CSV data from Google Drive using real credentials from .env.
    """
    env = dotenv_values(env_path)
    os.environ["GDRIVE_CREDENTIALS_JSON"] = env.get("GDRIVE_CREDENTIALS_JSON", "")
    os.environ["GDRIVE_FILE_ID"] = env.get("GDRIVE_FILE_ID", "")

    assert os.environ["GDRIVE_CREDENTIALS_JSON"], "GDRIVE_CREDENTIALS_JSON is not set"
    assert os.environ["GDRIVE_FILE_ID"], "GDRIVE_FILE_ID is not set"

    df = load_data()

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "symbol" in df.columns or "buy_price" in df.columns  
