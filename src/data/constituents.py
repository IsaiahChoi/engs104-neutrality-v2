"""S&P 500 constituents and GICS sectors from Wikipedia (brief §4).

The page is fetched once with a browser User-Agent and the raw HTML is cached in
data/raw/constituents/, so later builds parse the same snapshot. The snapshot date is the UTC
date of the fetch; the Wikipedia revision id is recorded too.
"""
from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone

import pandas as pd
import requests

from src.utils import DATA_RAW

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
RAW_DIR = DATA_RAW / "constituents"
GICS_SECTORS = frozenset({
    "Communication Services", "Consumer Discretionary", "Consumer Staples", "Energy",
    "Financials", "Health Care", "Industrials", "Information Technology", "Materials",
    "Real Estate", "Utilities",
})


def to_yahoo(symbol: str) -> str:
    """Wikipedia/exchange symbol -> Yahoo Finance ticker (class shares: BRK.B -> BRK-B)."""
    return symbol.strip().upper().replace(".", "-")


def fetch_snapshot(refresh: bool = False) -> tuple[str, dict]:
    """Return (html, meta) for the cached snapshot, fetching it first if none exists."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = RAW_DIR / "snapshot_meta.json"
    if meta_path.exists() and not refresh:
        meta = json.loads(meta_path.read_text())
        return (RAW_DIR / meta["html_file"]).read_text(encoding="utf-8"), meta

    resp = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    now = datetime.now(timezone.utc)
    rev = re.search(r'"wgRevisionId":(\d+)', resp.text)
    meta = {
        "url": URL,
        "snapshot_date": now.strftime("%Y-%m-%d"),
        "fetched_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "wikipedia_revision_id": int(rev.group(1)) if rev else None,
        "html_file": f"sp500_{now.strftime('%Y%m%d')}.html",
    }
    (RAW_DIR / meta["html_file"]).write_text(resp.text, encoding="utf-8")
    meta_path.write_text(json.dumps(meta, indent=2))
    return resp.text, meta


def parse_constituents(html: str, snapshot_date: str) -> pd.DataFrame:
    """Parse the first table on the page into one row per constituent."""
    table = pd.read_html(io.StringIO(html))[0]
    df = pd.DataFrame({
        "symbol": table["Symbol"].astype(str).str.strip(),
        "security": table["Security"].astype(str).str.strip(),
        "sector": table["GICS Sector"].astype(str).str.strip(),
        "sub_industry": table["GICS Sub-Industry"].astype(str).str.strip(),
        "date_added": table["Date added"].astype(str),
        "cik": table["CIK"],
    })
    df.insert(1, "ticker", df["symbol"].map(to_yahoo))
    df["snapshot_date"] = snapshot_date

    unknown = set(df["sector"]) - GICS_SECTORS
    if unknown:
        raise ValueError(f"Unrecognized GICS sectors in snapshot: {sorted(unknown)}")
    if df["ticker"].duplicated().any():
        raise ValueError(f"Duplicate tickers: {df.loc[df['ticker'].duplicated(), 'ticker'].tolist()}")
    return df.sort_values("ticker").reset_index(drop=True)


def load_constituents(refresh: bool = False) -> tuple[pd.DataFrame, dict]:
    html, meta = fetch_snapshot(refresh=refresh)
    return parse_constituents(html, meta["snapshot_date"]), meta
