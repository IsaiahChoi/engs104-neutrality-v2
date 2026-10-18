"""Risk-model tests (PLAN Phase 2; GATE_CRITERIA R1, R2, R6).

Synthetic tests check the estimator against known truth and independent computations; the
stored-model tests check every rebalance date of the built model (`make risk`).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
import yaml

from src.data.build_all import FACTORS_PATH, PANEL_PATH
from src.data.panel import returns_wide
from src.risk.bias import (bias_zscores, monthly_excess_returns, predicted_vol,
                           random_factor_neutral, random_long_only, summarize)
from src.risk.build_all import (DEFAULT_CONFIG, load_inputs, model_paths, rebalance_dates,
                                 valid_days)
from src.risk.factor_model import FACTORS, estimate, from_frames, month_end_dates, to_frames

K = len(FACTORS)


def simulate(n: int = 60, n_days: int = 252 + 21 * 120, seed: int = 7, missing: float = 0.0):
    """Daily returns from a known 6-factor model (business-day calendar, no risk-free)."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2001-01-01", periods=n_days)
    A = rng.normal(size=(K, K)) * 0.004
    F_daily = A @ A.T + np.diag(np.full(K, 0.004**2))
    f = rng.multivariate_normal(np.zeros(K), F_daily, size=n_days)
    B = np.column_stack([rng.normal(1.0, 0.3, n), rng.normal(0.0, 0.4, size=(n, K - 1))])
    sd = rng.uniform(0.01, 0.025, n)
    r = f @ B.T + rng.normal(size=(n_days, n)) * sd
    tickers = [f"S{i:03d}" for i in range(n)]
    R = pd.DataFrame(r, index=idx, columns=tickers)
    if missing:
        R = R.mask(rng.uniform(size=R.shape) < missing)
    fac = pd.DataFrame(f, index=idx, columns=FACTORS)
    return R, fac, B, F_daily, sd


@pytest.fixture(scope="module")
def sim():
    return simulate(missing=0.02)


def test_month_end_dates():
    cal = pd.bdate_range("2020-01-01", "2020-03-31")
    got = month_end_dates(cal)
    assert list(got) == [pd.Timestamp("2020-01-31"), pd.Timestamp("2020-02-28"),
                         pd.Timestamp("2020-03-31")]


def test_shapes_psd_nan_floor(sim):
    R, fac, *_ = sim
    m = estimate(R, fac, R.index[400])
    assert m.B.shape == (m.N, K) and m.F.shape == (K, K) and m.d.shape == (m.N,)
    assert np.array_equal(m.F, m.F.T)
    assert np.linalg.eigvalsh(m.F).min() > 0
    for a in (m.B, m.F, m.d, m.d_raw):
        assert np.isfinite(a).all()
    assert m.floor == pytest.approx(np.percentile(m.d_raw, 5.0), rel=0, abs=0)
    assert (m.d > 0).all() and (m.d >= m.floor).all()
    np.testing.assert_array_equal(m.d, np.maximum(m.d_raw, m.floor))
    assert (m.d_raw < m.floor).sum() >= 1  # the floor binds for the bottom names
    assert m.window_end == R.index[400] and m.window_start == R.index[400 - 251]


def test_loadings_match_independent_ols(sim):
    """R2: one stock with missing days, normal-equations OLS on its own non-missing rows."""
    R, fac, *_ = sim
    date = R.index[700]
    m = estimate(R, fac, date)
    t = next(t for t in m.tickers if R.loc[:date, t].iloc[-252:].isna().any())
    win = pd.concat([R.loc[:date, t].iloc[-252:], fac.loc[:date].iloc[-252:]], axis=1).dropna()
    X = np.column_stack([np.ones(len(win)), win[FACTORS].to_numpy()])
    y = win[t].to_numpy()
    coef = np.linalg.solve(X.T @ X, X.T @ y)
    resid = y - X @ coef
    j = m.tickers.index(t)
    np.testing.assert_allclose(m.B[j], coef[1:], rtol=0, atol=1e-8)
    assert m.d_raw[j] == pytest.approx(resid @ resid / (len(y) - K - 1) * 21, rel=1e-10)
    F = np.cov(fac.loc[:date].iloc[-252:].to_numpy(), rowvar=False) * 21
    np.testing.assert_allclose(m.F, F, rtol=1e-12, atol=0)


def test_no_lookahead(sim):
    """Scrambling everything after the rebalance date leaves the model unchanged."""
    R, fac, *_ = sim
    date = R.index[500]
    m1 = estimate(R, fac, date)
    R2, fac2 = R.copy(), fac.copy()
    R2.loc[R2.index > date] = 0.5
    fac2.loc[fac2.index > date] = -0.3
    m2 = estimate(R2, fac2, date)
    for a, b in [(m1.B, m2.B), (m1.F, m2.F), (m1.d, m2.d)]:
        np.testing.assert_array_equal(a, b)


def test_universe_rule():
    R, fac, *_ = simulate(n=10, n_days=300)
    R.iloc[-252:, 0] = np.nan                # no data in the window
    R.iloc[-60:, 1] = np.nan                 # 76% coverage: out
    R.iloc[-40:, 2] = np.nan                 # 84% coverage: in
    m = estimate(R, fac, R.index[-1])
    assert "S000" not in m.tickers and "S001" not in m.tickers and "S002" in m.tickers
    assert m.n_obs[m.tickers.index("S002")] == 212


def assert_loadings_recovered(m, fac_used, B_true, R=None, sd_true=None):
    """Loading errors in units of their OLS standard errors, z = (B_hat - B) / se, should look
    like N(0, 1) draws. se_ij = sqrt(s_i^2 [(X_i'X_i)^-1]_jj), with X_i the rows stock i used
    (R given: per-stock missing days; else every row). A stock's six estimates are correlated
    through (X_i'X_i)^-1 (correlation C_i); stocks are independent, so
    SE(mean z) = sqrt(sum_i 1'C_i 1) / (6n). Bounds (history and negative controls: PROGRESS.md):
    max |z| < 4.5 (P ~ 0.002 for 240 coefficients), std(z) in [0.85, 1.15], and
    |mean z| < 4 SE(mean z), which catches a uniform bias the other two miss.
    Phase 3b additions (verifier's proposals): per-factor |mean_i z_ik| < 4/sqrt(n); and, with
    sd_true, the pooled variance ratio mean_i(s_i^2/sigma_i^2) within 4 SE of 1, where
    SE = sqrt(mean_i 2/(n_i - 7)) / sqrt(n) (chi-square), which catches a wrong d scaling."""
    X = np.column_stack([np.ones(len(fac_used)), fac_used.to_numpy()])
    n, k = m.B.shape
    if R is None:
        Vs = [np.linalg.inv(X.T @ X)[1:, 1:]] * n
    else:
        mask = R.reindex(index=fac_used.index, columns=m.tickers).notna().to_numpy()
        Vs = [np.linalg.inv(X[mask[:, i]].T @ X[mask[:, i]])[1:, 1:] for i in range(n)]
    se = np.sqrt(np.array([m.d_raw[i] / 21 * np.diag(Vs[i]) for i in range(n)]))
    z = (m.B - B_true) / se
    one_c_one = sum((V / np.sqrt(np.outer(np.diag(V), np.diag(V)))).sum() for V in Vs)
    se_mean = np.sqrt(one_c_one) / z.size
    assert np.abs(z).max() < 4.5, np.abs(z).max()
    assert 0.85 <= z.std() <= 1.15, z.std()
    assert abs(z.mean()) < 4 * se_mean, (z.mean(), 4 * se_mean)
    per_factor = z.mean(axis=0)
    assert (np.abs(per_factor) < 4 / np.sqrt(n)).all(), per_factor
    if sd_true is not None:
        ratio = (m.d_raw / 21) / np.asarray(sd_true) ** 2
        se_ratio = np.sqrt(np.mean(2.0 / (m.n_obs - k - 1))) / np.sqrt(n)
        assert abs(ratio.mean() - 1.0) < 4 * se_ratio, (ratio.mean(), 4 * se_ratio)


def shuffled(R, B, sd, seed=11):
    """Rename the simulated stocks so sorted ticker order differs from the data's column order,
    shuffle the columns, and return the truth keyed by ticker (catches loadings attached to the
    wrong ticker)."""
    rng = np.random.default_rng(seed)
    names = [f"S{p:03d}" for p in rng.permutation(R.shape[1])]
    R = R.set_axis(names, axis=1).iloc[:, rng.permutation(R.shape[1])]
    return R, dict(zip(names, B)), dict(zip(names, sd))


@pytest.fixture(scope="module")
def recovery():
    R, fac, B, F_daily, sd = simulate(n=40, n_days=2000, seed=3)
    R, B_by, sd_by = shuffled(R, B, sd)
    m = estimate(R, fac, R.index[-1], window=2000)
    assert m.tickers != list(R.columns)            # the shuffle is not a no-op
    B_true = np.array([B_by[t] for t in m.tickers])
    sd_true = np.array([sd_by[t] for t in m.tickers])
    return R, fac, B_true, F_daily, sd_true, m


def test_recovers_true_model(recovery):
    R, fac, B, F_daily, sd, m = recovery
    assert_loadings_recovered(m, fac, B, sd_true=sd)
    np.testing.assert_allclose(np.sqrt(np.diag(m.F) / 21), np.sqrt(np.diag(F_daily)), rtol=0.1)
    np.testing.assert_allclose(np.sqrt(m.d_raw / 21), sd, rtol=0.1)


def test_recovers_true_model_with_missing_data():
    """Phase 3b: 2% missing days; standard errors from each stock's own rows."""
    R, fac, B, F_daily, sd = simulate(n=40, n_days=2000, seed=5, missing=0.02)
    R, B_by, sd_by = shuffled(R, B, sd, seed=12)
    m = estimate(R, fac, R.index[-1], window=2000)
    assert (m.n_obs < 2000).all()
    assert_loadings_recovered(m, fac, np.array([B_by[t] for t in m.tickers]), R=R,
                              sd_true=np.array([sd_by[t] for t in m.tickers]))


def test_recovery_check_rejects_wrong_d_scaling(recovery):
    """Negative control: residual variance scaled by 22 instead of 21."""
    R, fac, B, F_daily, sd, m = recovery
    from dataclasses import replace as dc_replace
    with pytest.raises(AssertionError):
        assert_loadings_recovered(dc_replace(m, d_raw=m.d_raw * 22 / 21), fac, B, sd_true=sd)


def test_recovery_check_rejects_one_factor_bias(recovery):
    """Negative control: +0.03 on every Mkt-RF loading only."""
    R, fac, B, F_daily, sd, m = recovery
    biased = B.copy()
    biased[:, 0] += 0.03
    with pytest.raises(AssertionError):
        assert_loadings_recovered(m, fac, biased, sd_true=sd)


def test_recovery_check_rejects_misattached_loadings(recovery):
    """Negative control: true loadings attached to the wrong tickers."""
    R, fac, B, F_daily, sd, m = recovery
    with pytest.raises(AssertionError):
        assert_loadings_recovered(m, fac, np.roll(B, 1, axis=0), sd_true=np.roll(sd, 1))


def test_recovery_check_rejects_lagged_factors(recovery):
    """Negative control (a): factor returns lagged one day relative to stock returns."""
    R, fac, B, *_ = recovery
    lagged = fac.shift(1).iloc[1:]
    m = estimate(R.iloc[1:], lagged, R.index[-1], window=len(lagged))
    with pytest.raises(AssertionError):
        assert_loadings_recovered(m, lagged, B)


def test_recovery_check_rejects_uniform_bias(recovery):
    """Negative control (b): every true loading off by +0.05 (about 1 median SE)."""
    R, fac, B, F_daily, sd, m = recovery
    with pytest.raises(AssertionError):
        assert_loadings_recovered(m, fac, B + 0.05)


def test_reproducible_and_roundtrip(sim):
    R, fac, *_ = sim
    dates = month_end_dates(R.index)[12:15]
    ms1 = [estimate(R, fac, d) for d in dates]
    ms2 = [estimate(R, fac, d) for d in dates]
    L, Fc = to_frames(ms1)
    for a, b in zip(ms1, ms2):
        np.testing.assert_array_equal(a.B, b.B)
        np.testing.assert_array_equal(a.d, b.d)
    back = from_frames(L, Fc, dates[1])
    np.testing.assert_array_equal(back.B, ms1[1].B)
    np.testing.assert_array_equal(back.F, ms1[1].F)
    np.testing.assert_array_equal(back.d, ms1[1].d)
    assert back.tickers == ms1[1].tickers


def test_predicted_vol_and_realized_returns(sim):
    R, fac, *_ = sim
    m = estimate(R, fac, R.index[300])
    W = random_factor_neutral(np.random.default_rng(0), m.B, 5)
    np.testing.assert_allclose(predicted_vol(m, W), np.sqrt(np.diag(W.T @ m.cov() @ W)),
                               rtol=1e-12)
    np.testing.assert_allclose(W.sum(axis=0), 0, atol=1e-12)                # dollar-neutral
    np.testing.assert_allclose(m.B.T @ W, 0, atol=1e-12)                    # factor-neutral
    np.testing.assert_allclose(np.abs(W).sum(axis=0), 2.0, rtol=1e-12)
    L = random_long_only(np.random.default_rng(0), m.N, 5)
    assert (L >= 0).all() and np.allclose(L.sum(axis=0), 1.0)
    start, end = R.index[300], R.index[321]
    rf = pd.Series(0.0001, index=R.index)
    got, missing = monthly_excess_returns(R, rf, start, end, m.tickers[:3])
    block = R.loc[(R.index > start) & (R.index <= end), m.tickers[:3]]
    want = (1 + block.fillna(0)).prod().to_numpy() - 1.0001**21
    np.testing.assert_allclose(got, want, rtol=1e-12)
    assert missing == pytest.approx(block.isna().to_numpy().mean())


def test_bias_statistic_near_one_when_model_is_right(sim):
    """On data from a constant factor model the bias statistic is close to 1. Long-only z's
    share the market draw within a month, so their tolerance is wider."""
    R, fac, *_ = sim
    dates = month_end_dates(R.index)
    dates = dates[dates >= R.index[251]]
    models = [estimate(R, fac, d) for d in dates]
    z = bias_zscores(models, R, pd.Series(0.0, index=R.index), seed=1, n_portfolios=100,
                     gross=2.0)
    s = summarize(z).set_index("type")["pooled_std_z"]
    assert 0.9 <= s["factor_neutral"] <= 1.1, s.to_dict()
    assert 0.75 <= s["long_only"] <= 1.25, s.to_dict()
    z2 = bias_zscores(models, R, pd.Series(0.0, index=R.index), seed=1, n_portfolios=100,
                      gross=2.0)
    pd.testing.assert_frame_equal(z, z2)


# ---------- the built model (`make risk`) ----------

@pytest.fixture(scope="module")
def built():
    cfg = yaml.safe_load(open(DEFAULT_CONFIG))
    lp, fp, mp = model_paths(cfg["window"])
    assert lp.exists() and fp.exists(), "risk model missing: run `make risk`"
    return cfg, pd.read_parquet(lp), pd.read_parquet(fp), json.loads(mp.read_text())


def test_built_model_every_date(built):
    """R1 and the window part of R2 at every stored rebalance date."""
    cfg, L, Fc, meta = built
    dates = sorted(L["date"].unique())
    assert len(dates) == meta["n_dates"] > 200
    for d in dates:
        m = from_frames(L, Fc, d)
        assert m.B.shape == (m.N, K) and m.F.shape == (K, K)
        assert np.array_equal(m.F, m.F.T) and np.linalg.eigvalsh(m.F).min() >= -1e-12
        assert (m.d > 0).all() and (m.d >= m.floor).all()
        assert all(np.isfinite(a).all() for a in (m.B, m.F, m.d))
        assert m.window_end <= m.date


def test_built_model_reestimates_identically(built):
    cfg, L, Fc, _ = built
    excess, _, factors = load_inputs(cfg["min_dollar_volume_usd"])
    dates = rebalance_dates(factors, cfg["window"], cfg.get("first_date"), cfg.get("last_date"))
    rng = np.random.default_rng(0)
    for d in rng.choice(dates, size=3, replace=False):
        stored = from_frames(L, Fc, d)
        fresh = estimate(excess, factors[FACTORS], d, window=cfg["window"],
                         min_frac=cfg["min_frac"], floor_pct=cfg["floor_pct"])
        assert stored.tickers == fresh.tickers
        np.testing.assert_array_equal(stored.B, fresh.B)
        np.testing.assert_array_equal(stored.F, fresh.F)
        np.testing.assert_array_equal(stored.d, fresh.d)


def test_valid_day_rule_and_eligibility():
    """A day is valid iff it has a return and dollar volume >= $1M (boundary included; NaN
    volume invalid); a stock enters iff >= 80% of its 252 window days are valid."""
    idx = pd.bdate_range("2020-01-01", periods=4)
    ex = pd.DataFrame({"A": [0.01, 0.01, np.nan, 0.01]}, index=idx)
    dv = pd.DataFrame({"A": [1e6, 999_999.0, 5e6, np.nan]}, index=idx)
    assert valid_days(ex, dv, 1e6)["A"].tolist() == [True, False, False, False]

    R, fac, *_ = simulate(n=4, n_days=300)
    dv = pd.DataFrame(5e6, index=R.index, columns=R.columns)
    dv.iloc[-53:, 0] = 2e5                  # 199/252 = 79.0% valid: out
    dv.iloc[-47:, 1] = np.nan               # 205/252 = 81.3% valid: in
    masked = R.where(valid_days(R, dv, 1e6))
    m = estimate(masked, fac, R.index[-1])
    assert m.tickers == ["S001", "S002", "S003"]
    assert m.n_obs[0] == 205


def test_valid_day_rule_uses_no_future_data():
    R, fac, *_ = simulate(n=6, n_days=1000)
    dv = pd.DataFrame(5e6, index=R.index, columns=R.columns)
    date = R.index[300]                      # 699 of 1,000 days lie after the date, so a rule
                                             # using a whole-sample statistic would also change
    m1 = estimate(R.where(valid_days(R, dv, 1e6)), fac, date)
    dv2 = dv.copy()
    dv2.loc[dv2.index > date] = 0.0          # every later day invalid
    m2 = estimate(R.where(valid_days(R, dv2, 1e6)), fac, date)
    assert m1.tickers == m2.tickers
    np.testing.assert_array_equal(m1.B, m2.B)
    np.testing.assert_array_equal(m1.d, m2.d)


def test_low_dollar_volume_days_are_masked():
    masked, _, factors = load_inputs(1e6)
    raw, _, _ = load_inputs(None)
    dv = returns_wide(pd.read_parquet(PANEL_PATH), "dollar_volume").reindex(factors.index)
    dv = dv.reindex(columns=masked.columns)
    kept = masked.notna().to_numpy()
    assert (dv.to_numpy()[kept] >= 1e6).all()
    assert not kept[raw.isna().to_numpy()].any()
    assert raw.notna().to_numpy().sum() - kept.sum() > 6000


def test_built_universe_matches_liquidity_rule(built):
    """Independent recomputation from the panel: eligible iff >= 80% of the 252 days ending at
    the rebalance date have a return and dollar volume >= $1M."""
    cfg, L, Fc, _ = built
    panel = pd.read_parquet(PANEL_PATH)
    cal = pd.DatetimeIndex(sorted(pd.read_parquet(FACTORS_PATH)["date"]))
    ok = panel.assign(v=panel["ret"].notna() & (panel["dollar_volume"] >= 1e6))
    ok = ok.pivot(index="date", columns="ticker", values="v").reindex(cal).eq(True)
    from src.data.panel import ADJUSTMENT_ERRORS                    # brief §4: invalid days
    for t, day in ADJUSTMENT_ERRORS:
        ok.loc[pd.Timestamp(day), t] = False
    rng = np.random.default_rng(1)
    dates = sorted(L["date"].unique())
    for d in [dates[0], dates[-1], *rng.choice(dates, size=4, replace=False)]:
        d = pd.Timestamp(d)
        win = ok.loc[:d].iloc[-252:]
        want = sorted(win.columns[win.astype(float).mean() >= 0.8])
        assert sorted(L.loc[L["date"] == d, "ticker"]) == want, d


def test_spac_shell_excluded(built):
    """Gate 2 concern 4: VRT's 2019 SPAC period (beta 0.02, $107k median dollar volume)."""
    _, L, _, _ = built
    vrt = L[(L["ticker"] == "VRT") & (L["date"].dt.year == 2019)]
    assert vrt.empty


def test_adjustment_errors_masked_in_risk_inputs():
    """GATE_CRITERIA P1: exactly the two Yahoo adjustment errors change in the return inputs."""
    from src.data.panel import ADJUSTMENT_ERRORS
    a, ra, _ = load_inputs(1e6, mask_errors=True)
    b, rb, _ = load_inputs(1e6, mask_errors=False)
    for x, y in ((a, b), (ra, rb)):
        changed = ((x.isna() != y.isna()) | ((x - y).abs() > 0)).stack()
        cells = sorted((t, f"{d:%Y-%m-%d}") for d, t in changed[changed].index)
        assert cells == sorted((t, d) for t, d in ADJUSTMENT_ERRORS)
