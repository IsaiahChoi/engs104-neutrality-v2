"""12-1 momentum alpha (brief §6b).

m_i = P_{t−21} / P_{t−252} − 1 = Π (1 + r_i,day) over the trading days (t−252, t−21], from
daily total returns (a missing day counts as no price change). z_i is the cross-sectional
z-score of m over the date's universe, winsorized at ±3 and then re-standardized to mean 0,
std 1 (brief §6b), and α_i = IC·ω_i·z_i with ω_i = √d_i and IC = IC_assumed = 0.03.
Uses data up to t − 21 only. This alpha is
strongly aligned with the Mom factor by construction; that is its role in RQ1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.risk.factor_model import RiskModel

IC_ASSUMED = 0.03
LOOKBACK, SKIP = 252, 21
WINSOR = 3.0


def momentum_score(ret: pd.DataFrame, tickers: list[str], date) -> np.ndarray:
    pos = ret.index.get_loc(pd.Timestamp(date))
    if pos < LOOKBACK:
        raise ValueError(f"need {LOOKBACK} trading days before {pd.Timestamp(date).date()}")
    block = ret.iloc[pos - LOOKBACK + 1: pos - SKIP + 1][tickers]   # days t−251 .. t−21
    return (1.0 + block.fillna(0.0)).prod().to_numpy() - 1.0


def winsorized_zscore(x: np.ndarray, clip: float = WINSOR) -> np.ndarray:
    """Cross-sectional z-score, clipped at ±clip, then re-standardized (population std)."""
    z = np.clip((x - x.mean()) / x.std(), -clip, clip)
    return (z - z.mean()) / z.std()


def momentum_alpha(model: RiskModel, ret: pd.DataFrame, ic: float = IC_ASSUMED) -> np.ndarray:
    z = winsorized_zscore(momentum_score(ret, model.tickers, model.date))
    return ic * np.sqrt(model.d) * z
