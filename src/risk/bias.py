"""Bias-statistic validation of the risk model (brief §5, GATE_CRITERIA R5).

At each rebalance date t with a following rebalance date t', and for each portfolio type:
- long_only: 100 random portfolios, w = u / sum(u), u ~ U(0, 1);
- factor_neutral: 100 random dollar- and factor-neutral long/short portfolios: v ~ N(0, I),
  w = v projected off span[1, B], scaled to gross 2.
z = (realized excess return over (t, t']) / (predicted monthly vol sqrt(w' Sigma_t w)).
A well-calibrated model gives std(z) close to 1. Missing daily returns in the holding month
count as zero return (reported).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.risk.factor_model import RiskModel


def monthly_excess_returns(ret_wide: pd.DataFrame, rf: pd.Series, start, end,
                           tickers: list[str]) -> tuple[np.ndarray, float]:
    """Compounded excess return over (start, end] for each ticker; and the missing share."""
    block = ret_wide.loc[(ret_wide.index > start) & (ret_wide.index <= end)].reindex(columns=tickers)
    missing = float(block.isna().to_numpy().mean()) if block.size else 1.0
    gross = (1.0 + block.fillna(0.0)).prod().to_numpy()
    rf_gross = float((1.0 + rf.loc[(rf.index > start) & (rf.index <= end)]).prod())
    return gross - rf_gross, missing


def random_long_only(rng: np.random.Generator, n: int, m: int) -> np.ndarray:
    u = rng.uniform(size=(n, m))
    return u / u.sum(axis=0, keepdims=True)


def random_factor_neutral(rng: np.random.Generator, B: np.ndarray, m: int,
                          gross: float = 2.0) -> np.ndarray:
    n = B.shape[0]
    X = np.column_stack([np.ones(n), B])
    Q, _ = np.linalg.qr(X)
    v = rng.standard_normal(size=(n, m))
    w = v - Q @ (Q.T @ v)
    return gross * w / np.abs(w).sum(axis=0, keepdims=True)


def predicted_vol(model: RiskModel, W: np.ndarray) -> np.ndarray:
    """sqrt(w' (B F B' + D) w) for each column of W (monthly)."""
    E = model.B.T @ W
    var = np.einsum("km,kl,lm->m", E, model.F, E) + (model.d[:, None] * W**2).sum(axis=0)
    return np.sqrt(var)


def bias_zscores(models: list[RiskModel], ret_wide: pd.DataFrame, rf: pd.Series,
                 seed: int, n_portfolios: int, gross: float) -> pd.DataFrame:
    """One row per (date, type, portfolio): realized, predicted vol, z."""
    rng = np.random.default_rng(seed)
    rows = []
    for m, nxt in zip(models[:-1], models[1:]):
        r, missing = monthly_excess_returns(ret_wide, rf, m.date, nxt.date, m.tickers)
        for kind in ("long_only", "factor_neutral"):
            W = (random_long_only(rng, m.N, n_portfolios) if kind == "long_only"
                 else random_factor_neutral(rng, m.B, n_portfolios, gross))
            realized = r @ W
            sigma = predicted_vol(m, W)
            rows.append(pd.DataFrame({
                "date": m.date, "next_date": nxt.date, "type": kind,
                "portfolio": np.arange(n_portfolios), "realized": realized,
                "pred_vol": sigma, "z": realized / sigma, "missing_share": missing,
                "max_abs_factor_exposure": np.abs(m.B.T @ W).max(axis=0),
            }))
    return pd.concat(rows, ignore_index=True)


def summarize(z: pd.DataFrame) -> pd.DataFrame:
    """Pooled std of z per type, plus the spread of per-portfolio (time-series) std."""
    out = []
    for kind, g in z.groupby("type"):
        per_port = g.groupby("portfolio")["z"].std(ddof=1)
        out.append({"type": kind, "pooled_std_z": float(g["z"].std(ddof=1)),
                    "mean_z": float(g["z"].mean()), "n_z": len(g),
                    "n_dates": int(g["date"].nunique()),
                    "per_portfolio_std_median": float(per_port.median()),
                    "per_portfolio_std_p05": float(per_port.quantile(0.05)),
                    "per_portfolio_std_p95": float(per_port.quantile(0.95))})
    return pd.DataFrame(out)
