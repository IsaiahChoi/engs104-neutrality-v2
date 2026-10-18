"""Build the processed data (PLAN Phase 1): `make data` or `uv run python -m src.data.build_all`.

Outputs in data/processed/: panel.parquet, factors_daily.parquet, constituents.csv,
build_meta.json; plus results/data_report.md. With --offline, nothing is downloaded and the
build uses only cached raw files (this is the reproducibility path).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys

import pandas as pd

from src.data.constituents import load_constituents
from src.data.factors import load_factors
from src.data.panel import build_panel, panel_hash
from src.data.prices import END_INCLUSIVE, RAW_DIR, START, download_prices, load_raw_prices
from src.data.report import write_report
from src.utils import DATA_PROCESSED, DATA_RAW, RESULTS, append_run_log, git_commit, utc_timestamp

PANEL_PATH = DATA_PROCESSED / "panel.parquet"
FACTORS_PATH = DATA_PROCESSED / "factors_daily.parquet"
CONSTITUENTS_PATH = DATA_PROCESSED / "constituents.csv"
META_PATH = DATA_PROCESSED / "build_meta.json"
REPORT_PATH = RESULTS / "data_report.md"


def raw_hashes() -> dict[str, str]:
    """SHA-256 of every file under data/raw/ (the cache is the dataset of record, brief §4)."""
    return {str(f.relative_to(DATA_RAW)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(DATA_RAW.rglob("*")) if f.is_file()}


def build(offline: bool = False, write: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    constituents, snap = load_constituents()
    tickers = constituents["ticker"].tolist()
    if offline:
        fail_path = RAW_DIR / "failures.csv"
        failures = pd.read_csv(fail_path) if fail_path.exists() else pd.DataFrame(
            columns=["ticker", "reason", "attempts", "timestamp_utc"])
    else:
        failures = download_prices(tickers)
    raw = load_raw_prices(tickers)

    factors = load_factors()
    factors = factors[(factors["date"] >= START) & (factors["date"] <= END_INCLUSIVE)]
    factors = factors.reset_index(drop=True)

    panel, diagnostics = build_panel(constituents, raw, factors)
    meta = {
        "git_commit": git_commit(), "built_utc": utc_timestamp(),
        "snapshot_date": snap["snapshot_date"],
        "wikipedia_revision_id": snap.get("wikipedia_revision_id"),
        "panel_sha256": panel_hash(panel), "panel_rows": len(panel),
        "n_tickers": int(panel["ticker"].nunique()), "n_dates": int(panel["date"].nunique()),
        "date_range": [f"{panel['date'].min():%Y-%m-%d}", f"{panel['date'].max():%Y-%m-%d}"],
        "units": {"ret": "daily simple return, decimal", "excess_ret": "ret - RF, decimal",
                  "dollar_volume": "USD per day (close x volume)", "factors": "daily, decimal"},
        "n_failed_downloads": len(failures),
        "raw_sha256": raw_hashes(),
    }
    if write:
        DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
        panel.to_parquet(PANEL_PATH, index=False)
        factors.to_parquet(FACTORS_PATH, index=False)
        constituents.to_csv(CONSTITUENTS_PATH, index=False)
        stats = write_report(REPORT_PATH, panel, factors, constituents, snap, failures,
                             diagnostics, meta)
        meta["report_stats"] = stats
        META_PATH.write_text(json.dumps(meta, indent=2, default=str))
    return panel, factors, meta


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--offline", action="store_true", help="use cached raw data only")
    args = p.parse_args()
    try:
        panel, factors, meta = build(offline=args.offline)
    except Exception as e:
        append_run_log("src/data/build_all.py", "failed", str(DATA_PROCESSED), f"{type(e).__name__}: {e}")
        raise
    s = meta["report_stats"]
    print(f"panel {panel.shape}, factors {factors.shape}, sha256 {meta['panel_sha256'][:12]}")
    print(f"coverage 2015-25: {s['coverage_2015_2025']}, 2010-14: {s['coverage_2010_2014']}, "
          f"failed: {s['n_failed']}, corr(EW, Mkt-RF): {s['corr_ew_mktrf']:.4f}, "
          f"EW vol: {s['ew_ann_vol']:.4f}, extreme: {s['extreme_count']}")
    append_run_log("src/data/build_all.py", "ok", str(PANEL_PATH),
                   f"offline={args.offline}; rows={meta['panel_rows']}; sha256={meta['panel_sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
