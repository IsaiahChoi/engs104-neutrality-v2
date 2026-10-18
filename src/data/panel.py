"""Processed daily panel (brief §4 processing rules).

Panel columns: date, ticker, ret, excess_ret, dollar_volume, sector; one row per (date, ticker).
- ret_t = adj_close_t / adj_close_{t-1} - 1 over consecutive cached rows of the same ticker,
  computed before any row filtering, so it always matches the raw file. Each ticker's first
  row has no return and is not in the panel.
- excess_ret = ret - RF (Ken French daily RF, decimal).
- dollar_volume = close * volume (split-adjusted close times split-adjusted share volume, i.e.
  traded dollars); NaN where volume is missing or zero, so it is > 0 wherever present.
- Rows on dates outside the Ken French trading calendar (e.g. weekends, holidays) are dropped
  and listed in the diagnostics. Nothing else is dropped silently; extreme returns are flagged.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from src.data.prices import END_INCLUSIVE, START

PANEL_COLUMNS = ["date", "ticker", "ret", "excess_ret", "dollar_volume", "sector"]
EXTREME_RET = 0.50
# Yahoo adjustment errors identified in the data report (brief §4). The panel keeps the raw price
# relatives; every downstream use of returns (risk-model inputs, alphas, residuals, realized
# returns) treats these stock-days as missing, i.e. invalid days.
ADJUSTMENT_ERRORS = (("JCI", "2007-07-02"), ("DHR", "2016-07-05"))


def ticker_returns(raw: pd.DataFrame) -> pd.DataFrame:
    """Returns from one ticker's cached raw frame: date, ret, dollar_volume, prev_date."""
    df = raw.sort_values("date").reset_index(drop=True)
    df = df[df["adj_close"].notna() & (df["adj_close"] > 0)].reset_index(drop=True)
    out = pd.DataFrame({
        "date": df["date"],
        "ret": df["adj_close"] / df["adj_close"].shift(1) - 1.0,
        "dollar_volume": (df["close"] * df["volume"]).where(df["volume"] > 0),
        "prev_date": df["date"].shift(1),
    })
    return out.iloc[1:].reset_index(drop=True)


def build_panel(constituents: pd.DataFrame, raw: dict[str, pd.DataFrame],
                factors: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Assemble the panel; return (panel, diagnostics)."""
    sector = constituents.set_index("ticker")["sector"]
    cal = pd.DatetimeIndex(factors["date"])
    pieces, diag_bad_price, diag_dup = [], {}, {}
    for t in sorted(raw):
        frame = raw[t]
        diag_bad_price[t] = int((~(frame["adj_close"] > 0)).sum())
        diag_dup[t] = int(frame["date"].duplicated().sum())
        r = ticker_returns(frame.drop_duplicates("date", keep="last"))
        r.insert(1, "ticker", t)
        pieces.append(r)
    allr = pd.concat(pieces, ignore_index=True)
    allr = allr[(allr["date"] >= START) & (allr["date"] <= END_INCLUSIVE)]

    off_cal = allr[~allr["date"].isin(cal)]
    allr = allr[allr["date"].isin(cal)].copy()

    # Interior gaps: the previous cached row is more than one trading day back, so the return
    # spans several sessions. Kept (it is the correct price relative), but counted and listed.
    pos = pd.Series(np.arange(len(cal)), index=cal)
    prev_pos = allr["prev_date"].map(pos)
    allr["gap_sessions"] = allr["date"].map(pos) - prev_pos  # NaN if prev_date is off-calendar

    rf = factors.set_index("date")["RF"]
    allr["excess_ret"] = allr["ret"] - allr["date"].map(rf)
    allr["sector"] = allr["ticker"].map(sector)

    panel = (allr[PANEL_COLUMNS].sort_values(["date", "ticker"]).reset_index(drop=True))
    panel["ticker"] = panel["ticker"].astype(str)
    panel["sector"] = panel["sector"].astype(str)

    multi = allr[allr["gap_sessions"] > 1]
    diagnostics = {
        "off_calendar_rows": off_cal[["date", "ticker", "ret"]].reset_index(drop=True),
        "multi_session_returns": multi[["date", "ticker", "prev_date", "gap_sessions", "ret"]]
        .sort_values(["ticker", "date"]).reset_index(drop=True),
        "bad_price_rows": int(sum(diag_bad_price.values())),
        "duplicate_date_rows": int(sum(diag_dup.values())),
        "zero_or_missing_volume_rows": int(panel["dollar_volume"].isna().sum()),
        "extreme_returns": panel.loc[panel["ret"].abs() > EXTREME_RET,
                                     ["date", "ticker", "ret", "sector"]].reset_index(drop=True),
    }
    return panel, diagnostics


def panel_hash(panel: pd.DataFrame) -> str:
    """Order-sensitive content hash of the panel (used for the reproducibility check)."""
    h = pd.util.hash_pandas_object(panel, index=False).to_numpy()
    return hashlib.sha256(h.tobytes()).hexdigest()


def returns_wide(panel: pd.DataFrame, column: str = "excess_ret") -> pd.DataFrame:
    """Dates x tickers matrix of a panel column (NaN where a ticker has no row)."""
    return panel.pivot(index="date", columns="ticker", values=column).sort_index()


def mask_adjustment_errors(wide: pd.DataFrame) -> pd.DataFrame:
    """Copy of a dates x tickers frame with the ADJUSTMENT_ERRORS cells set to NaN."""
    out = wide.copy()
    for ticker, day in ADJUSTMENT_ERRORS:
        if ticker in out.columns and pd.Timestamp(day) in out.index:
            out.loc[pd.Timestamp(day), ticker] = np.nan
    return out
