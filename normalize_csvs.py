"""
Normalize all historical CSV files in resources/historicals/ to the standard format:
  date,open,high,low,close,volume

Handles NASDAQ format (Date, Close/Last with $ prefix, MM/DD/YYYY)
and leaves Yahoo Finance format untouched.
Overwrites files in place.
"""
import os
import pandas as pd

HIST_DIR = os.path.join(os.path.dirname(__file__), "resources", "historicals")


def is_nasdaq_format(df):
    return "Close/Last" in df.columns


def normalize_file(filepath):
    df = pd.read_csv(filepath)

    if not is_nasdaq_format(df):
        print(f"  ✅ {os.path.basename(filepath)} — already normalized, skipping")
        return

    # Remove $ prefix and convert to float
    for col in ["Close/Last", "Open", "High", "Low"]:
        df[col] = df[col].astype(str).str.replace("$", "", regex=False).astype(float)

    # Rename columns to standard format
    df = df.rename(columns={
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close/Last": "close",
        "Volume": "volume",
    })

    # Parse date and convert to Yahoo-like format
    df["date"] = pd.to_datetime(df["date"], format="%m/%d/%Y")
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    # Keep only standard columns, sort ascending by date
    df = df[["date", "open", "high", "low", "close", "volume"]]
    df = df.sort_values("date").reset_index(drop=True)

    # Overwrite file
    df.to_csv(filepath, index=False)
    print(f"  🔄 {os.path.basename(filepath)} — normalized ({len(df)} rows)")


def main():
    print(f"Normalizing CSVs in {HIST_DIR}\n")
    csv_files = sorted([f for f in os.listdir(HIST_DIR) if f.endswith(".csv")])

    if not csv_files:
        print("No CSV files found.")
        return

    for filename in csv_files:
        normalize_file(os.path.join(HIST_DIR, filename))

    print(f"\nDone. {len(csv_files)} files processed.")


if __name__ == "__main__":
    main()
