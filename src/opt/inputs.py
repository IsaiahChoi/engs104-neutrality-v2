"""Per-date optimizer inputs: stored risk model, GICS sectors, and ADV (brief §3.1, §4).

The universe at a rebalance date is the stored risk model's universe there (≥ 80% valid days,
$1M dollar-volume rule). ADV_i is the median of close × volume over the trailing 63 trading
days ending at the date (data up to the date only).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd
import yaml

from src.data.build_all import FACTORS_PATH, PANEL_PATH
from src.data.panel import mask_adjustment_errors, returns_wide
from src.risk.build_all import DEFAULT_CONFIG as RISK_CONFIG, model_paths
from src.risk.factor_model import RiskModel, from_frames

ADV_WINDOW = 63


@dataclass
class MarketData:
    """Wide daily frames on the factor calendar (dates x tickers) plus factors and sectors."""
    excess: pd.DataFrame        # daily excess returns ($1M rule not applied; the two Yahoo errors masked)
    ret: pd.DataFrame           # daily total returns
    dollar_volume: pd.DataFrame
    factors: pd.DataFrame       # 6 factors + RF, daily decimal
    sector: pd.Series           # ticker -> GICS sector


@lru_cache(maxsize=1)
def market_data() -> MarketData:
    panel = pd.read_parquet(PANEL_PATH)
    factors = pd.read_parquet(FACTORS_PATH).set_index("date")
    cal = factors.index
    return MarketData(       # the two Yahoo adjustment errors are missing here too (brief §4)
        excess=mask_adjustment_errors(returns_wide(panel, "excess_ret").reindex(cal)),
        ret=mask_adjustment_errors(returns_wide(panel, "ret").reindex(cal)),
        dollar_volume=returns_wide(panel, "dollar_volume").reindex(cal),
        factors=factors,
        sector=panel.drop_duplicates("ticker").set_index("ticker")["sector"],
    )


@lru_cache(maxsize=1)
def _stored_model() -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = yaml.safe_load(open(RISK_CONFIG))
    lp, fp, _ = model_paths(cfg["window"])
    if not lp.exists():
        raise FileNotFoundError("risk model missing: run `make risk`")
    return pd.read_parquet(lp), pd.read_parquet(fp)


def rebalance_dates() -> pd.DatetimeIndex:
    loadings, _ = _stored_model()
    return pd.DatetimeIndex(sorted(loadings["date"].unique()))


def next_rebalance_date(date) -> pd.Timestamp | None:
    dates = rebalance_dates()
    later = dates[dates > pd.Timestamp(date)]
    return later[0] if len(later) else None


def risk_model(date) -> RiskModel:
    loadings, fcov = _stored_model()
    return from_frames(loadings, fcov, date)


def adv(tickers: list[str], date, window: int = ADV_WINDOW) -> np.ndarray:
    """Median daily dollar volume over the trailing `window` trading days ending at `date`."""
    dv = market_data().dollar_volume
    return dv.loc[:pd.Timestamp(date), tickers].tail(window).median().to_numpy()


@dataclass
class DateInputs:
    date: pd.Timestamp
    model: RiskModel
    sectors: np.ndarray          # GICS sector label per ticker
    adv: np.ndarray              # USD per day

    @property
    def tickers(self) -> list[str]:
        return self.model.tickers

    @property
    def sector_names(self) -> list[str]:
        return sorted(set(self.sectors))

    def sector_matrix(self) -> np.ndarray:
        """S (N x J): S[i, j] = 1 if stock i is in sector j (sector_names order)."""
        return (self.sectors[:, None] == np.array(self.sector_names)[None, :]).astype(float)


def date_inputs(date) -> DateInputs:
    date = pd.Timestamp(date)
    m = risk_model(date)
    sec = market_data().sector.reindex(m.tickers).to_numpy()
    if pd.isna(sec).any():
        raise ValueError(f"missing sector for {np.array(m.tickers)[pd.isna(sec)][:5]}")
    return DateInputs(date=date, model=m, sectors=sec.astype(str), adv=adv(m.tickers, date))
