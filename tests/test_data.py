"""Phase 1 data tests: schema, uniqueness, finiteness, date alignment, units, reproducibility.

Unit tests use synthetic inputs. Tests on the processed data require `make data` to have run;
they fail (not skip) if the processed files are missing.
"""
import json

import numpy as np
import pandas as pd
import pytest

from src.data.build_all import CONSTITUENTS_PATH, FACTORS_PATH, META_PATH, PANEL_PATH, build
from src.data.constituents import GICS_SECTORS, to_yahoo
from src.data.factors import FACTOR_COLS, parse_french_csv
from src.data.panel import PANEL_COLUMNS, returns_wide, ticker_returns
from src.data.report import below_coverage
from src.data.prices import END_INCLUSIVE, START, cache_path


# ---------- unit tests (synthetic inputs) ----------

def test_to_yahoo_maps_class_shares():
    assert to_yahoo("BRK.B") == "BRK-B"
    assert to_yahoo("BF.B") == "BF-B"
    assert to_yahoo(" aapl ") == "AAPL"


def test_parse_french_csv_reads_first_block_and_keeps_percent():
    text = (
        "This file was created by CMPT_ME_BEME_RETS_DAILY\n\n"
        ",Mkt-RF,SMB,HML,RF\n"
        "20240102,  -0.71,  0.10, 0.50, 0.021\n"
        "20240103,  1.25, -0.20, -99.99, 0.021\n"
        "\n Annual Factors\n,Mkt-RF,SMB,HML,RF\n1999, 1.0, 2.0, 3.0, 4.0\n"
    )
    df = parse_french_csv(text)
    assert list(df.columns) == ["date", "Mkt-RF", "SMB", "HML", "RF"]
    assert len(df) == 2  # the annual block is not read
    assert df["date"].tolist() == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]
    assert df.loc[0, "Mkt-RF"] == pytest.approx(-0.71)  # parser keeps percent; load_factors divides
    assert np.isnan(df.loc[1, "HML"])  # missing code -> NaN


def test_ticker_returns_matches_price_relatives():
    raw = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
        "adj_close": [100.0, 110.0, np.nan, 99.0],
        "close": [100.0, 110.0, np.nan, 99.0],
        "volume": [1e6, 0.0, np.nan, 2e6],
    })
    r = ticker_returns(raw)
    assert r["date"].tolist() == [pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-05")]
    np.testing.assert_allclose(r["ret"], [0.10, 99.0 / 110.0 - 1.0], rtol=0, atol=1e-15)
    assert np.isnan(r["dollar_volume"].iloc[0])  # zero volume -> NaN
    assert r["dollar_volume"].iloc[1] == pytest.approx(99.0 * 2e6)


# ---------- processed data ----------

@pytest.fixture(scope="module")
def panel():
    assert PANEL_PATH.exists(), "processed panel missing: run `make data`"
    return pd.read_parquet(PANEL_PATH)


@pytest.fixture(scope="module")
def factors():
    assert FACTORS_PATH.exists(), "processed factors missing: run `make data`"
    return pd.read_parquet(FACTORS_PATH)


def test_panel_schema(panel):
    assert list(panel.columns) == PANEL_COLUMNS
    assert pd.api.types.is_datetime64_any_dtype(panel["date"])
    for c in ("ret", "excess_ret", "dollar_volume"):
        assert pd.api.types.is_float_dtype(panel[c]), c
    assert len(panel) > 1_000_000


def test_panel_unique_keys(panel):
    assert not panel.duplicated(["date", "ticker"]).any()


def test_panel_finite_returns(panel):
    assert np.isfinite(panel["ret"]).all()
    assert np.isfinite(panel["excess_ret"]).all()
    assert (panel["ret"] > -1.0).all()
    dv = panel["dollar_volume"].dropna()
    assert (dv > 0).all() and np.isfinite(dv).all()


def test_panel_dates_aligned_with_factors(panel, factors):
    pdates = pd.DatetimeIndex(panel["date"].unique())
    fdates = pd.DatetimeIndex(factors["date"])
    assert pdates.isin(fdates).all()
    assert (pdates.dayofweek < 5).all() and (fdates.dayofweek < 5).all()
    # excess_ret is ret minus that same day's RF
    rf = factors.set_index("date")["RF"]
    sample = panel.sample(5_000, random_state=0)
    np.testing.assert_allclose(sample["ret"] - sample["date"].map(rf), sample["excess_ret"],
                               rtol=0, atol=1e-15)


def test_raw_dates_on_factor_calendar(panel, factors):
    """Not circular: the panel is filtered to the factor calendar, so check the raw cache."""
    fdates = pd.DatetimeIndex(factors["date"])
    for t in sorted(panel["ticker"].unique()):
        d = pd.DatetimeIndex(pd.read_parquet(cache_path(t), columns=["date"])["date"])
        d = d[(d >= START) & (d <= END_INCLUSIVE)]
        assert d.isin(fdates).all(), (t, d[~d.isin(fdates)][:3].tolist())


def test_same_day_alignment_with_market(panel, factors):
    """A one-day shift between prices and factors would move the peak correlation off lag 0."""
    ew = panel.groupby("date")["excess_ret"].mean()
    mkt = factors.set_index("date")["Mkt-RF"].reindex(ew.index)
    corr = {lag: ew.corr(mkt.shift(lag)) for lag in (-1, 0, 1)}
    assert corr[0] >= 0.9
    assert corr[0] > max(corr[-1], corr[1]) + 0.5


def test_factor_units_are_decimal(factors):
    assert list(factors.columns) == ["date", *FACTOR_COLS, "RF"]
    assert np.isfinite(factors[[*FACTOR_COLS, "RF"]].to_numpy()).all()
    assert abs(factors["Mkt-RF"].mean()) < 0.002
    assert 0.005 <= factors["Mkt-RF"].std() <= 0.02
    assert factors["RF"].mean() < 0.0003


def test_sectors_and_class_shares(panel):
    c = pd.read_csv(CONSTITUENTS_PATH)
    assert set(c["sector"]) <= GICS_SECTORS and c["sector"].nunique() == 11
    per_ticker = panel.groupby("ticker")["sector"].nunique()
    assert (per_ticker == 1).all()
    assert set(panel["sector"].unique()) <= GICS_SECTORS
    assert {"BRK-B", "BF-B"} <= set(panel["ticker"].unique())
    meta = json.loads(META_PATH.read_text())
    assert meta["snapshot_date"]


def test_returns_match_raw_prices(panel):
    """No lookahead: ret_t = P_t / P_{t-1} - 1 from the cached raw adjusted closes."""
    rng = np.random.default_rng(0)
    tickers = rng.choice(sorted(panel["ticker"].unique()), size=3, replace=False)
    for t in [*tickers, "BRK-B"]:
        raw = pd.read_parquet(cache_path(t)).sort_values("date")
        raw = raw[raw["adj_close"] > 0]
        expected = (raw["adj_close"] / raw["adj_close"].shift(1) - 1).set_axis(raw["date"])
        got = panel[panel["ticker"] == t].set_index("date")["ret"]
        np.testing.assert_allclose(got.to_numpy(), expected.reindex(got.index).to_numpy(),
                                   rtol=0, atol=1e-10)


def test_below_coverage_flags_late_listings():
    idx = pd.bdate_range("2015-01-01", periods=10)
    wide = pd.DataFrame({"FULL": 0.01, "LATE": [np.nan] * 5 + [0.01] * 5,
                         "GAPPY": [0.01] * 2 + [np.nan] * 6 + [0.01] * 2,
                         "LATE_GAPPY": [np.nan] * 4 + [0.01, np.nan, np.nan, 0.01, np.nan, 0.01]},
                        index=idx)
    out = below_coverage(wide, "2015-01-01", "2015-12-31").set_index("ticker")
    assert set(out.index) == {"LATE", "GAPPY", "LATE_GAPPY"}
    assert out.loc["LATE", "explained"] and out.loc["LATE", "coverage_since_first"] == 1.0
    assert not out.loc["GAPPY", "explained"]
    assert not out.loc["LATE_GAPPY", "explained"]  # listed late, but gappy after listing
    idx2 = pd.bdate_range("2014-12-24", periods=10)  # 2014-12-24 .. 2015-01-06
    wide2 = pd.DataFrame({"OLD": 0.01, "NEW": [np.nan] * 6 + [0.01] * 4}, index=idx2)
    after = below_coverage(wide2, "2014-01-01", "2014-12-31").set_index("ticker")
    assert list(after.index) == ["NEW"]  # listed after the window ends: no data in it at all
    assert after.loc["NEW", "explained"] and np.isnan(after.loc["NEW", "coverage_since_first"])


def test_low_coverage_explained_by_listing_date(panel):
    """D2: every ticker under 80% coverage in either window listed after the window start."""
    wide = returns_wide(panel, "ret")
    for start, end in [("2015-01-01", "2025-12-31"), ("2010-01-01", "2014-12-31")]:
        below = below_coverage(wide, start, end)
        assert below["explained"].all(), below.loc[~below["explained"], "ticker"].tolist()[:5]


def test_rebuild_from_cache_is_identical(panel):
    rebuilt, _, _ = build(offline=True, write=False)
    pd.testing.assert_frame_equal(rebuilt, panel, check_exact=True)


def test_raw_hashes_recorded():
    """GATE_CRITERIA P3: every file in data/raw/ has its SHA-256 in the build metadata."""
    import hashlib
    from src.utils import DATA_RAW
    meta = json.loads(META_PATH.read_text())
    files = sorted(str(f.relative_to(DATA_RAW)) for f in DATA_RAW.rglob("*") if f.is_file())
    assert sorted(meta["raw_sha256"]) == files
    for f in np.random.default_rng(0).choice(files, size=5, replace=False):
        assert hashlib.sha256((DATA_RAW / f).read_bytes()).hexdigest() == meta["raw_sha256"][f]
