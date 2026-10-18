"""Daily adjusted close, close, and volume from yfinance (brief §4), cached per ticker.

Raw files: data/raw/prices/<TICKER>.parquet with columns date, adj_close, close, volume.
Tickers are downloaded in batches; any ticker a batch misses is retried individually with
exponential backoff. Tickers that still fail are written to data/raw/prices/failures.csv with
the last error message. Cached tickers are never re-downloaded unless refresh=True, because
Yahoo's adjusted closes are recomputed on every download.
"""
from __future__ import annotations

import json
import time

import pandas as pd
import yfinance as yf

from src.utils import DATA_RAW, utc_timestamp

RAW_DIR = DATA_RAW / "prices"
START = "2005-01-01"
END_INCLUSIVE = "2025-12-31"
_END_EXCLUSIVE = "2026-01-01"  # yfinance treats `end` as exclusive
BATCH_SIZE = 25
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 2.0


def cache_path(ticker: str):
    return RAW_DIR / f"{ticker}.parquet"


def _tidy(frame: pd.DataFrame) -> pd.DataFrame:
    """yfinance columns -> date, adj_close, close, volume; rows with no prices dropped."""
    out = pd.DataFrame({
        "date": pd.to_datetime(frame.index).tz_localize(None).normalize(),
        "adj_close": frame["Adj Close"].to_numpy(dtype=float),
        "close": frame["Close"].to_numpy(dtype=float),
        "volume": frame["Volume"].to_numpy(dtype=float),
    })
    out = out.dropna(subset=["adj_close", "close"], how="all")
    return out.sort_values("date").reset_index(drop=True)


def _download_batch(tickers: list[str]) -> dict[str, pd.DataFrame]:
    raw = yf.download(
        tickers, start=START, end=_END_EXCLUSIVE, auto_adjust=False, actions=False,
        progress=False, threads=True, group_by="ticker",
    )
    got = {}
    for t in tickers:
        if raw is None or raw.empty or t not in raw.columns.get_level_values(0):
            continue
        tidy = _tidy(raw[t])
        if not tidy.empty:
            got[t] = tidy
    return got


def _download_single(ticker: str) -> tuple[pd.DataFrame | None, str]:
    """Retry one ticker with exponential backoff; return (frame or None, last error)."""
    err = "empty response"
    for attempt in range(MAX_ATTEMPTS):
        try:
            hist = yf.Ticker(ticker).history(
                start=START, end=_END_EXCLUSIVE, auto_adjust=False, actions=False,
                raise_errors=True,
            )
            tidy = _tidy(hist) if hist is not None and not hist.empty else pd.DataFrame()
            if not tidy.empty:
                return tidy, ""
        except Exception as e:  # yfinance raises several exception types; record the message
            err = f"{type(e).__name__}: {e}".replace("\n", " ")[:300]
        time.sleep(BACKOFF_SECONDS * 2**attempt)
    return None, err


def download_prices(tickers: list[str], refresh: bool = False) -> pd.DataFrame:
    """Download and cache prices; return the failures table (ticker, reason, timestamp)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    todo = [t for t in tickers if refresh or not cache_path(t).exists()]
    print(f"prices: {len(tickers)} tickers, {len(tickers) - len(todo)} cached, {len(todo)} to download")

    missed: list[str] = []
    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i:i + BATCH_SIZE]
        try:
            got = _download_batch(batch)
        except Exception as e:
            print(f"  batch {i // BATCH_SIZE} failed ({type(e).__name__}); retrying individually")
            got = {}
        for t, frame in got.items():
            frame.to_parquet(cache_path(t), index=False)
        missed += [t for t in batch if t not in got]
        print(f"  batch {i // BATCH_SIZE + 1}/{-(-len(todo) // BATCH_SIZE)}: "
              f"{len(got)}/{len(batch)} ok")

    failures = []
    for t in missed:
        frame, err = _download_single(t)
        if frame is None:
            failures.append({"ticker": t, "reason": err, "attempts": MAX_ATTEMPTS + 1,
                             "timestamp_utc": utc_timestamp()})
            print(f"  FAILED {t}: {err}")
        else:
            frame.to_parquet(cache_path(t), index=False)

    fail_path = RAW_DIR / "failures.csv"
    previous = pd.read_csv(fail_path) if fail_path.exists() and not refresh else pd.DataFrame()
    if not previous.empty:  # keep earlier failures that are still uncached
        previous = previous[~previous["ticker"].map(lambda t: cache_path(t).exists())]
        previous = previous[~previous["ticker"].isin([f["ticker"] for f in failures])]
    fail_df = pd.concat([previous, pd.DataFrame(failures)], ignore_index=True)
    fail_df = fail_df.reindex(columns=["ticker", "reason", "attempts", "timestamp_utc"])
    fail_df.to_csv(fail_path, index=False)

    manifest_path = RAW_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.update({"yfinance_version": yf.__version__, "start": START,
                     "end_inclusive": END_INCLUSIVE, "auto_adjust": False})
    downloads = manifest.setdefault("downloaded_utc", {})
    now = utc_timestamp()
    for t in todo:
        if cache_path(t).exists():
            downloads[t] = now
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return fail_df


def load_raw_prices(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Cached raw frames for the tickers that have them."""
    return {t: pd.read_parquet(cache_path(t)) for t in tickers if cache_path(t).exists()}
