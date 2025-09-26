import os
import json
import io
import pandas as pd
import pytest
import sys
from unittest import mock
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools')))
from google_handler import get_drive_service, load_data


@pytest.fixture
def mock_env_vars():
    # Load fake credentials from file
    with open("resources/fake_credentials.json", "r") as f:
        fake_creds_json = f.read()

    os.environ["GDRIVE_CREDENTIALS_JSON"] = fake_creds_json
    os.environ["GDRIVE_FILE_ID"] = "fake_file_id"
    yield
    os.environ.pop("GDRIVE_CREDENTIALS_JSON", None)
    os.environ.pop("GDRIVE_FILE_ID", None)


def test_get_drive_service_success(mock_env_vars):
    with mock.patch("your_module.build") as mock_build, \
         mock.patch("your_module.service_account.Credentials.from_service_account_info") as mock_creds:

        mock_creds.return_value = "fake_credentials"
        mock_build.return_value = "fake_service"

        service = get_drive_service()
        assert service == "fake_service"
        mock_creds.assert_called_once()
        mock_build.assert_called_once_with("drive", "v3", credentials="fake_credentials")


def test_load_data_success(mock_env_vars):
    # Mock Google Drive service and file export behavior
    fake_csv_content = b"value,date\n123.45,2025-09-26 12:00:00\n"

    class FakeRequest:
        def __init__(self):
            self.chunks = [fake_csv_content]
            self.index = 0

        def next_chunk(self):
            if self.index < 1:
                self.index += 1
                # Return (status, done)
                return None, True
            else:
                return None, True

    class FakeDownloader:
        def __init__(self, fh, request):
            self.fh = fh
            self.request = request
            self.done = False

        def next_chunk(self):
            self.fh.write(fake_csv_content)
            self.done = True
            return None, self.done

    fake_service = mock.MagicMock()
    fake_service.files.return_value.export_media.return_value = FakeRequest()

    with mock.patch("your_module.get_drive_service", return_value=fake_service), \
         mock.patch("your_module.MediaIoBaseDownload", side_effect=FakeDownloader):

        df = load_data()
        assert isinstance(df, pd.DataFrame)
        assert "value" in df.columns
        assert len(df) == 1
        assert df.iloc[0]["value"] == 123.45


def test_load_data_exception_creates_empty_df(mock_env_vars):
    fake_service = mock.MagicMock()
    fake_service.files.return_value.export_media.side_effect = Exception("File not found")

    with mock.patch("your_module.get_drive_service", return_value=fake_service):
        df = load_data()
        assert isinstance(df, pd.DataFrame)
        assert df.empty
        assert list(df.columns) == ["value", "date"]
