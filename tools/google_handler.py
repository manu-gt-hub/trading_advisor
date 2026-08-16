import pandas as pd
import os
import io
import json
from datetime import datetime, timezone, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

def _is_missing(value):
    """Return True for NaN, None, empty/whitespace strings or literal 'NaT'/'nan'/'None'."""
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str):
        return value.strip() == "" or value.strip().lower() in {"nat", "nan", "none", "null"}
    try:
        return pd.isna(value)
    except Exception:
        return False

# Load .env file only if not running in production (e.g., GitHub Actions)
if not os.getenv("GITHUB_ACTIONS"):  # This var is auto-set in GitHub Actions
    load_dotenv()

def get_drive_service():
    # Retrieve Google Drive service client using credentials from environment variable
    creds_json = os.environ.get("GDRIVE_CREDENTIALS_JSON")
    if not creds_json:
        raise Exception("Environment variable GDRIVE_CREDENTIALS_JSON not found")
    try:
        creds_dict = json.loads(creds_json)
    except (json.JSONDecodeError, TypeError) as e:
        raise Exception(f"Invalid GDRIVE_CREDENTIALS_JSON format: {e}")
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

    if revenue_percentage is None:
        logger.warning("⚠️ revenue_percentage is None. Skipping transaction review.")
        return df_transactions

    # Ensure columns we are going to write can accept mixed types
    # (Google Sheets may export empty cells as strings, giving the column a string dtype).
    for col in ['sell_value', 'sell_date', 'buy_sell_days_diff', 'percentage_benefit']:
        if col in df_transactions.columns:
            df_transactions[col] = df_transactions[col].astype(object)

    # Coerce numeric columns to floats/ints for reliable comparisons and math
    df_transactions['buy_value'] = pd.to_numeric(df_transactions['buy_value'], errors='coerce')
    if 'stop_loss' in df_transactions.columns:
        df_transactions['stop_loss'] = pd.to_numeric(df_transactions['stop_loss'], errors='coerce')
    if 'take_profit' in df_transactions.columns:
        df_transactions['take_profit'] = pd.to_numeric(df_transactions['take_profit'], errors='coerce')
    # Loop through each row in the transactions dataframe
    for idx, row in df_transactions.iterrows():
        try:
            symbol = row['symbol']
            buy_value = row['buy_value']
            sell_value_raw = row.get('sell_value')
            sell_date = row.get('sell_date')
            buy_sell_days_diff = row.get('buy_sell_days_diff')
            percentage_benefit = row.get('percentage_benefit')

            # Coerce sell_value to a float; invalid/non-numeric values are treated as missing.
            sell_value = pd.to_numeric(sell_value_raw, errors='coerce')

            logger.debug(
                f"Row {idx} {symbol}: sell_value={sell_value_raw} (coerced={sell_value}), "
                f"sell_date={sell_date!r}, missing={_is_missing(sell_date)}"
            )

            # Defensive repair: row has a sell price but is missing sell metadata.
            # This can happen if a previous run failed mid-write or after a partial save,
            # or if Google Sheets exported an empty string instead of NaN.
            if not _is_missing(sell_value) and _is_missing(sell_date):
                logger.warning(f"⚠️ Repairing incomplete sale record for {symbol} (sell_value={sell_value:.2f})")
                exit_price = float(sell_value)
                buy_date_raw = pd.to_datetime(row['buy_date'], errors='coerce')
                if _is_missing(buy_date_raw):
                    logger.error(f"❌ Cannot repair {symbol}: invalid buy_date '{row['buy_date']}'")
                    continue
                sell_date_obj = datetime.today().date()
                days_diff = (sell_date_obj - buy_date_raw.date()).days
                pct = ((exit_price - buy_value) / buy_value) * 100
                df_transactions.at[idx, 'sell_date'] = sell_date_obj.isoformat()
                df_transactions.at[idx, 'buy_sell_days_diff'] = int(days_diff)
                df_transactions.at[idx, 'percentage_benefit'] = round(pct, 2)
                logger.info(
                    f"✅ Repaired {symbol}: buy={buy_value:.2f}, sell={exit_price:.2f}, "
                    f"days={days_diff}, benefit={pct:.2f}%, date={sell_date_obj.isoformat()}"
                )
                continue

            # Skip fully closed rows
            if not _is_missing(sell_value):
                continue

            # Look for the symbol in the analysis dataframe
            analysis_row = df_analysis[df_analysis['symbol'] == symbol]

            if not analysis_row.empty:
                current_price = analysis_row.iloc[0]['current_price']
                target_price = buy_value * (1 + float(revenue_percentage) / 100)

                # Check stop-loss hit (trailing stop)
                stop_loss = row.get('stop_loss')
                stop_hit = pd.notna(stop_loss) and current_price <= stop_loss

                if current_price >= target_price or stop_hit:
                    # Normalize all dates to ISO strings so they sort/serialize consistently
                    sell_date_obj = datetime.today().date()
                    buy_date_raw = pd.to_datetime(row['buy_date'], errors='coerce')
                    if pd.isna(buy_date_raw):
                        logger.error(f"❌ Cannot compute days held for {symbol}: invalid buy_date '{row['buy_date']}'. Skipping sale.")
                        continue
                    buy_date = buy_date_raw.date()
                    days_diff = (sell_date_obj - buy_date).days

                    # Use the actual exit price: take_profit when target hit, stop_loss when stopped out
                    # This avoids recording a lower price if current_price has moved since the trigger
                    if stop_hit:
                        exit_price = float(stop_loss)
                        logger.info(f"🛑 Stop-loss triggered for {symbol}: price {current_price:.2f} <= stop {stop_loss:.2f}")
                    else:
                        # Target hit: use take_profit if available, otherwise target_price
                        take_profit = row.get('take_profit')
                        exit_price = float(take_profit) if pd.notna(take_profit) else target_price
                        logger.info(f"🎯 Take-profit hit for {symbol}: price {current_price:.2f} >= target {target_price:.2f}")

                    pct = ((exit_price - buy_value) / buy_value) * 100

                    # Update the transaction record (store dates as ISO strings for consistency)
                    df_transactions.at[idx, 'sell_value'] = round(exit_price, 2)
                    df_transactions.at[idx, 'sell_date'] = sell_date_obj.isoformat()
                    df_transactions.at[idx, 'buy_sell_days_diff'] = int(days_diff)
                    df_transactions.at[idx, 'percentage_benefit'] = round(pct, 2)
                    logger.info(
                        f"✅ Closed {symbol}: buy={buy_value:.2f}, sell={exit_price:.2f}, "
                        f"days={days_diff}, benefit={pct:.2f}%, date={sell_date_obj.isoformat()}"
                    )
        except Exception as e:
            logger.error(f"❌ Error processing transaction row {idx}: {e}. Skipping.")

    return df_transactions


def save_dataframe_file_id(df, file_id):
    """
    Updates an existing CSV file on Google Drive using in-memory upload (no temp file).
    Fully Windows-compatible.
    """
    if not file_id:
        logger.error("❌ file_id not provided. Skipping save.")
        return

    try:
        service = get_drive_service()
        logger.info("saving data into google drive...")

        # Write CSV to an in-memory bytes buffer
        csv_buffer = io.BytesIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)  # Rewind to start

        media = MediaIoBaseUpload(csv_buffer, mimetype='text/csv')

        updated_file = service.files().update(
            fileId=file_id,
            media_body=media
        ).execute()

        logger.info(f"✅ Saved to Google Drive (file_id={file_id})")
    except Exception as e:
        logger.error(f"❌ Failed to save to Google Drive (file_id={file_id}): {e}")

