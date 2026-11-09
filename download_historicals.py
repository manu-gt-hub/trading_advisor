"""
Download the backtest data set from Yahoo Finance (free, no API key):

  resources/historicals/<SYMBOL>.csv        one per symbol in backtest.universe
  resources/historicals/market/<NAME>.csv   index (^GSPC -> GSPC), VIX, market benchmark
                                            and every sector ETF in relative_strength

Prices are split/dividend adjusted (yfinance auto_adjust=True), the same series
production reads, in the standard format: date,open,high,low,close,volume.
Today's (possibly partial) bar is dropped.

Usage:
  python download_historicals.py                 # everything, 5 years
  python download_historicals.py --only MSFT SPY # a subset
  python download_historicals.py --windows-certs # TLS via the Windows root store
                                                 # (machines with TLS interception)
"""
import argparse
import base64
import os
import ssl
import sys
import tempfile
from datetime import date

import pandas as pd
import yfinance as yf

from tools import technical_engine

ROOT = os.path.dirname(os.path.abspath(__file__))
HIST_DIR = os.path.join(ROOT, "resources", "historicals")
MARKET_DIR = os.path.join(HIST_DIR, "market")


def market_file_name(ticker):
    """'^GSPC' -> 'GSPC' (file-system safe name used by the backtester)."""
    return ticker.lstrip("^").replace("/", "_")


def windows_ca_bundle():
    """Export the Windows certificate stores to a PEM file; TLS verification stays on."""
    path = os.path.join(tempfile.gettempdir(), "trading_advisor_win_roots.pem")
    seen = set()
    with open(path, "w") as f:
        for store in ("ROOT", "CA"):
            for cert, encoding, _ in ssl.enum_certificates(store):
                if encoding == "x509_asn" and cert not in seen:
                    seen.add(cert)
                    b64 = base64.b64encode(cert).decode()
                    body = "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64))
                    f.write(f"-----BEGIN CERTIFICATE-----\n{body}\n-----END CERTIFICATE-----\n")
    return path


def make_session(ca_bundle):
    if not ca_bundle:
        return None
    from curl_cffi import requests as curl_requests
    return curl_requests.Session(impersonate="chrome", verify=ca_bundle)


def download(ticker, period, session):
    hist = yf.Ticker(ticker, session=session).history(period=period, auto_adjust=True)
    if hist is None or hist.empty:
        return None
    df = hist.reset_index()
    df["date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.date
    df = df[df["date"] < date.today()]
    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
    df = df[["date", "open", "high", "low", "close", "volume"]].dropna(subset=["close"])
    return df.sort_values("date").reset_index(drop=True)


def targets():
    cfg = technical_engine.load_config()
    rs = cfg.get("relative_strength", {})
    md = cfg.get("market_data", {})
    symbols = [(s, os.path.join(HIST_DIR, f"{s}.csv")) for s in cfg.get("backtest", {}).get("universe", [])]
    market = {md.get("index", "^GSPC"), md.get("vix", "^VIX"), rs.get("market_benchmark", "SPY")}
    market |= set(rs.get("sector_etfs", {}).values())
    market = [(t, os.path.join(MARKET_DIR, f"{market_file_name(t)}.csv")) for t in sorted(market)]
    return symbols + market


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--period", default="5y")
    ap.add_argument("--only", nargs="*", help="tickers to refresh (default: all)")
    ap.add_argument("--ca-bundle", default=os.environ.get("YF_CA_BUNDLE"), help="PEM bundle for TLS verification")
    ap.add_argument("--windows-certs", action="store_true", help="build the CA bundle from the Windows store")
    args = ap.parse_args()

    session = make_session(windows_ca_bundle() if args.windows_certs else args.ca_bundle)
    os.makedirs(MARKET_DIR, exist_ok=True)
    failed = []
    for ticker, path in targets():
        if args.only and ticker not in args.only:
            continue
        try:
            df = download(ticker, args.period, session)
        except Exception as e:
            df = None
            print(f"  ❌ {ticker}: {type(e).__name__}: {str(e)[:120]}")
        if df is None or df.empty:
            failed.append(ticker)
            continue
        df.to_csv(path, index=False)
        print(f"  ✅ {ticker:6} {len(df):5} rows {df['date'].iloc[0]} → {df['date'].iloc[-1]}  {os.path.relpath(path, ROOT)}")
    if failed:
        print(f"\nFailed: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
