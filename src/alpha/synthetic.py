"""Synthetic alpha with known IC (brief §6a; Grinold–Kahn construction).

This alpha uses next month's realized residual returns BY DESIGN: it is an oracle with
controlled noise that isolates what the constraints do to a forecaster of known skill. It is
never a tradable signal and must be described that way.

At rebalance date t with next rebalance date t':
  e_i  = Σ_{days in (t, t']} (x_i,day − B_i·f_day)   realized next-month residual return
         (x = daily excess return; days without a return are skipped; intercept excluded)
  ω_i  = √d_i;   ẽ = e/ω, standardized cross-sectionally (mean 0, std 1)
  s_i  = IC·ẽ_i + √(1 − IC²)·η_i,   η iid N(0, 1)
  α_i  = IC·ω_i·s_i                                  (monthly)
The empirical IC of a draw is corr(α/ω, e/ω) = corr(s, ẽ), whose mean over draws is ≈ IC.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.risk.factor_model import FACTORS, RiskModel


def residual_returns(model: RiskModel, excess: pd.DataFrame, factors: pd.DataFrame,
                     next_date) -> np.ndarray:
    """e_i over (model.date, next_date] for the model's tickers."""
    sel = (excess.index > model.date) & (excess.index <= pd.Timestamp(next_date))
    X = excess.loc[sel, model.tickers].to_numpy()
    f = factors.loc[sel, FACTORS].to_numpy()
    return np.nansum(X - f @ model.B.T, axis=0)


def draw_rng(seed: int, date, ic: float, draw: int) -> np.random.Generator:
    """Independent, reproducible stream per (seed, date, IC, draw)."""
    return np.random.default_rng([seed, int(pd.Timestamp(date).strftime("%Y%m%d")),
                                  int(round(ic * 10_000)), draw])


def synthetic_alpha(e: np.ndarray, d: np.ndarray, ic: float,
                    rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (α, s, ẽ) for realized residuals e and idiosyncratic variances d."""
    omega = np.sqrt(d)
    z = e / omega
    e_std = (z - z.mean()) / z.std()
    s = ic * e_std + np.sqrt(1.0 - ic * ic) * rng.standard_normal(len(e))
    return ic * omega * s, s, e_std


def empirical_ic(alpha: np.ndarray, e: np.ndarray, d: np.ndarray) -> float:
    omega = np.sqrt(d)
    return float(np.corrcoef(alpha / omega, e / omega)[0, 1])
