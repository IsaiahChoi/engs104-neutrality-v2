"""Rolling time-series factor model (brief §5).

At rebalance date t (last trading day of a month), using the `window` trading days ending at
t inclusive:
- universe: tickers with >= min_frac non-missing daily excess returns in the window;
- B_t: OLS of each stock's daily excess return on the 6 factors plus an intercept, using that
  stock's non-missing days;
- d_i = residual variance (SSR / (n_obs - 7)) x 21, floored at the floor_pct cross-sectional
  percentile; units: monthly variance;
- F_t = sample covariance (ddof = 1) of the daily factor returns in the window x 21 (monthly).
Sigma_t = B F B' + diag(d). Nothing after t enters the estimate.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

FACTORS = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
DAYS_PER_MONTH = 21


@dataclass
class RiskModel:
    date: pd.Timestamp
    tickers: list[str]
    B: np.ndarray            # N x K loadings
    F: np.ndarray            # K x K factor covariance, monthly
    d: np.ndarray            # N idiosyncratic variances, monthly, floored
    d_raw: np.ndarray        # N residual variances x 21 before the floor
    intercept: np.ndarray    # N daily intercepts (not used by the optimizer)
    n_obs: np.ndarray        # N observations used per regression
    floor: float             # floor applied to d
    window_start: pd.Timestamp
    window_end: pd.Timestamp

    @property
    def N(self) -> int:
        return len(self.tickers)

    def cov(self) -> np.ndarray:
        """Dense Sigma = B F B' + D (monthly)."""
        return self.B @ self.F @ self.B.T + np.diag(self.d)


def month_end_dates(calendar: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Last trading day of each calendar month in the given trading calendar."""
    s = pd.Series(calendar, index=calendar)
    return pd.DatetimeIndex(s.groupby(calendar.to_period("M")).max().to_numpy())


def _ols_block(X: np.ndarray, Y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """OLS of each column of Y on X (both complete); return (coef p x n, SSR n)."""
    coef, *_ = np.linalg.lstsq(X, Y, rcond=None)
    resid = Y - X @ coef
    return coef, (resid**2).sum(axis=0)


def estimate(excess: pd.DataFrame, factors: pd.DataFrame, date, window: int = 252,
             min_frac: float = 0.8, floor_pct: float = 5.0) -> RiskModel:
    """Estimate the factor model at `date`.

    excess: dates x tickers daily excess returns (NaN = missing), indexed by trading date.
    factors: dates x FACTORS daily factor returns (decimal), same calendar.
    """
    date = pd.Timestamp(date)
    fac = factors.loc[:date, FACTORS]
    if len(fac) < window:
        raise ValueError(f"Only {len(fac)} trading days up to {date.date()}; need {window}")
    fac = fac.iloc[-window:]
    idx = fac.index
    R = excess.reindex(idx)
    frac = R.notna().mean()
    tickers = sorted(frac.index[frac >= min_frac])
    R = R[tickers].to_numpy()
    X = np.column_stack([np.ones(window), fac.to_numpy()])
    p = X.shape[1]

    coef = np.empty((p, len(tickers)))
    ssr = np.empty(len(tickers))
    n_obs = np.empty(len(tickers), dtype=int)
    mask = ~np.isnan(R)
    complete = mask.all(axis=0)
    if complete.any():
        coef[:, complete], ssr[complete] = _ols_block(X, R[:, complete])
        n_obs[complete] = window
    for j in np.flatnonzero(~complete):
        rows = mask[:, j]
        c, s = _ols_block(X[rows], R[rows, j][:, None])
        coef[:, j], ssr[j], n_obs[j] = c[:, 0], s[0], rows.sum()

    d_raw = ssr / (n_obs - p) * DAYS_PER_MONTH
    floor = float(np.percentile(d_raw, floor_pct))
    d = np.maximum(d_raw, floor)
    F = np.cov(fac.to_numpy(), rowvar=False, ddof=1) * DAYS_PER_MONTH
    F = 0.5 * (F + F.T)
    return RiskModel(date=date, tickers=tickers, B=coef[1:].T.copy(), F=F, d=d, d_raw=d_raw,
                     intercept=coef[0].copy(), n_obs=n_obs, floor=floor,
                     window_start=idx[0], window_end=idx[-1])


def to_frames(models: list[RiskModel]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Long-format frames for storage: loadings (one row per date x ticker) and F."""
    load, fc = [], []
    for m in models:
        df = pd.DataFrame(m.B, columns=[f"beta_{f}" for f in FACTORS])
        df.insert(0, "ticker", m.tickers)
        df.insert(0, "date", m.date)
        df["d"] = m.d
        df["d_raw"] = m.d_raw
        df["intercept"] = m.intercept
        df["n_obs"] = m.n_obs
        df["floor"] = m.floor
        df["window_start"] = m.window_start
        df["window_end"] = m.window_end
        load.append(df)
        f = pd.DataFrame(m.F, columns=FACTORS)
        f.insert(0, "factor", FACTORS)
        f.insert(0, "date", m.date)
        fc.append(f)
    return pd.concat(load, ignore_index=True), pd.concat(fc, ignore_index=True)


def from_frames(loadings: pd.DataFrame, factor_cov: pd.DataFrame, date) -> RiskModel:
    """Rebuild the RiskModel at `date` from stored frames."""
    date = pd.Timestamp(date)
    L = loadings[loadings["date"] == date].sort_values("ticker")
    if L.empty:
        raise KeyError(f"No risk model stored for {date.date()}")
    Fd = factor_cov[factor_cov["date"] == date].set_index("factor").loc[FACTORS, FACTORS]
    return RiskModel(
        date=date, tickers=L["ticker"].tolist(),
        B=L[[f"beta_{f}" for f in FACTORS]].to_numpy(), F=Fd.to_numpy(),
        d=L["d"].to_numpy(), d_raw=L["d_raw"].to_numpy(), intercept=L["intercept"].to_numpy(),
        n_obs=L["n_obs"].to_numpy(), floor=float(L["floor"].iloc[0]),
        window_start=pd.Timestamp(L["window_start"].iloc[0]),
        window_end=pd.Timestamp(L["window_end"].iloc[0]),
    )
