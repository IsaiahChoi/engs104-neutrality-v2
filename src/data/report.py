"""Generate results/data_report.md from the processed data (PLAN Phase 1).

Every number in the report is computed here from the processed panel, factor file, and
build diagnostics; nothing is typed by hand.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.panel import EXTREME_RET, returns_wide

ADV_WINDOW = 63
LOW_LIQUIDITY_USD = 1e6


def _md_table(df: pd.DataFrame, floatfmt: str = "{:.4f}") -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        cells = []
        for v in row:
            if isinstance(v, (float, np.floating)):
                cells.append(floatfmt.format(v))
            elif isinstance(v, pd.Timestamp):
                cells.append(v.strftime("%Y-%m-%d"))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def coverage_count(ret_wide: pd.DataFrame, start: str, end: str, min_frac: float = 0.8) -> int:
    """Tickers with >= min_frac non-missing daily returns over [start, end] trading days."""
    window = ret_wide.loc[start:end]
    return int((window.notna().mean() >= min_frac).sum())


def below_coverage(ret_wide: pd.DataFrame, start: str, end: str,
                   min_frac: float = 0.8) -> pd.DataFrame:
    """Tickers below min_frac coverage over [start, end], each with its first return date in the
    panel. The shortfall is explained (GATE_CRITERIA D2) when that date falls after the window's
    first trading day and coverage from that date onward (coverage_since_first) is >= min_frac,
    so late listing, not gaps, accounts for the missing days."""
    window = ret_wide.loc[start:end]
    frac = window.notna().mean()
    first = ret_wide.apply(pd.Series.first_valid_index)
    rows = []
    for t in frac.index[frac < min_frac]:
        f = first[t]
        listed_after_end = pd.notna(f) and f > window.index[-1]  # no data in the window at all
        since = window.loc[f:, t].notna().mean() if pd.notna(f) and not listed_after_end else np.nan
        rows.append({"ticker": t, "coverage": float(frac[t]), "first_return_date": f,
                     "coverage_since_first": float(since),
                     "explained": bool(pd.notna(f) and f > window.index[0]
                                       and (listed_after_end or since >= min_frac))})
    cols = ["ticker", "coverage", "first_return_date", "coverage_since_first", "explained"]
    return pd.DataFrame(rows, columns=cols)


def adv_at(dv_wide: pd.DataFrame, date: str, window: int = ADV_WINDOW) -> pd.Series:
    """ADV per brief §4: median dollar volume over the trailing `window` trading days."""
    return dv_wide.loc[:date].tail(window).median()


def market_sanity(panel: pd.DataFrame, factors: pd.DataFrame) -> dict:
    ew = panel.groupby("date")["excess_ret"].mean()
    f = factors.set_index("date")["Mkt-RF"].reindex(ew.index)
    return {"corr_ew_mktrf": float(ew.corr(f)), "ew_ann_vol": float(ew.std() * np.sqrt(252)),
            "n_days": int(len(ew))}


def write_report(path, panel: pd.DataFrame, factors: pd.DataFrame, constituents: pd.DataFrame,
                 snapshot_meta: dict, failures: pd.DataFrame, diagnostics: dict,
                 build_meta: dict) -> dict:
    ret_w = returns_wide(panel, "ret")
    dv_w = returns_wide(panel, "dollar_volume")
    n_obs = len(panel)

    n_const = len(constituents)
    n_fail = len(failures)
    cov_late = coverage_count(ret_w, "2015-01-01", "2025-12-31")
    cov_early = coverage_count(ret_w, "2010-01-01", "2014-12-31")
    below_late = below_coverage(ret_w, "2015-01-01", "2025-12-31")
    below_early = below_coverage(ret_w, "2010-01-01", "2014-12-31")
    mkt = market_sanity(panel, factors)
    fac = factors.set_index("date")
    adv_2024 = adv_at(dv_w, "2024-12-31").dropna()
    med_dv_2024 = dv_w.loc["2024-01-01":"2024-12-31"].median().dropna()
    extreme = diagnostics["extreme_returns"]
    class_shares = constituents[constituents["symbol"].str.contains(r"\.", regex=True)]
    in_panel = set(panel["ticker"].unique())

    by_year = []
    for year, block in ret_w.groupby(ret_w.index.year):
        frac = block.notna().mean()
        by_year.append({"year": int(year), "trading_days": len(block),
                        "tickers_any_data": int((frac > 0).sum()),
                        "tickers_ge_80pct": int((frac >= 0.8).sum()),
                        "missing_frac_listed": float(1 - block.notna().to_numpy()[:, frac > 0].mean())})
    by_year = pd.DataFrame(by_year)

    stats = {
        "n_constituents": n_const, "n_failed": n_fail, "fail_frac": n_fail / n_const,
        "n_tickers_panel": len(in_panel), "n_rows": n_obs,
        "coverage_2015_2025": cov_late, "coverage_2010_2014": cov_early,
        "below_80_unexplained_2015_2025": int((~below_late["explained"]).sum()),
        "below_80_unexplained_2010_2014": int((~below_early["explained"]).sum()),
        "mktrf_mean": float(fac["Mkt-RF"].mean()), "mktrf_std": float(fac["Mkt-RF"].std()),
        "rf_mean": float(fac["RF"].mean()),
        "extreme_count": len(extreme), "extreme_frac": len(extreme) / n_obs,
        "median_adv_2024": float(adv_2024.median()),
        **mkt,
    }

    sec = constituents["sector"].value_counts().rename_axis("sector").reset_index(name="count")
    sec_panel = (panel.drop_duplicates("ticker")["sector"].value_counts()
                 .rename_axis("sector").reset_index(name="count_in_panel"))
    sec = sec.merge(sec_panel, on="sector", how="left").fillna(0)
    sec["count_in_panel"] = sec["count_in_panel"].astype(int)

    multi = diagnostics["multi_session_returns"]
    off = diagnostics["off_calendar_rows"]
    L = []
    L.append("# Data report (generated by `src/data/build_all.py`; do not edit by hand)\n")
    L.append(f"- Build git commit: `{build_meta['git_commit']}`; built (UTC): {build_meta['built_utc']}")
    L.append(f"- Panel SHA-256 (content hash): `{build_meta['panel_sha256']}`")
    L.append(f"- Sample: {panel['date'].min():%Y-%m-%d} to {panel['date'].max():%Y-%m-%d}, "
             f"{panel['date'].nunique()} trading days, {len(in_panel)} tickers, {n_obs:,} rows")
    L.append("\n## 1. Constituent snapshot\n")
    L.append(f"- Source: {snapshot_meta['url']}")
    L.append(f"- **Snapshot date: {snapshot_meta['snapshot_date']}** (fetched {snapshot_meta['fetched_utc']}); "
             f"Wikipedia revision id {snapshot_meta.get('wikipedia_revision_id')}")
    L.append(f"- Constituents: {n_const}; GICS sectors: {constituents['sector'].nunique()}")
    L.append("- Class-share ticker mapping (Wikipedia → Yahoo), and presence in the panel:\n")
    cs = pd.DataFrame({"symbol": class_shares["symbol"], "yahoo_ticker": class_shares["ticker"],
                       "in_panel": class_shares["ticker"].isin(in_panel)})
    L.append(_md_table(cs))
    L.append("\n### Sector counts\n")
    L.append(_md_table(sec))
    L.append("\n## 2. Download failures\n")
    L.append(f"- Failed entirely: {n_fail} of {n_const} ({100 * n_fail / n_const:.2f}%)")
    if n_fail:
        L.append("")
        L.append(_md_table(failures[["ticker", "reason"]]))
    missing_from_panel = sorted(set(constituents["ticker"]) - in_panel - set(failures["ticker"]))
    L.append(f"- Downloaded but absent from the panel: {missing_from_panel or 'none'}")
    L.append("\n## 3. Coverage and missingness\n")
    L.append(f"- Tickers with ≥ 80% non-missing daily returns, 2015–2025: **{cov_late}**")
    L.append(f"- Tickers with ≥ 80% non-missing daily returns, 2010–2014: **{cov_early}**")
    L.append("- `missing_frac_listed`: share of missing (day, ticker) cells among tickers with "
             "any data that year (mostly partial first years after IPO/spin-off).\n")
    L.append(_md_table(by_year))
    for label, below in [("2015–2025", below_late), ("2010–2014", below_early)]:
        L.append(f"\n### Tickers below 80% coverage, {label}\n")
        L.append(f"- Count: {len(below)}; explained by a first return date after the window "
                 f"start: {int(below['explained'].sum())}; unexplained: "
                 f"**{int((~below['explained']).sum())}**")
        if len(below):
            L.append("")
            L.append(_md_table(below.sort_values("first_return_date")))
    L.append(f"\n- Returns spanning more than one session (gap in the cached series; kept, "
             f"since they are correct price relatives): {len(multi)}")
    if len(multi):
        L.append("")
        L.append(_md_table(multi.head(50), floatfmt="{:.6f}"))
        if len(multi) > 50:
            L.append(f"\n(first 50 of {len(multi)} shown)")
    L.append(f"- Rows on dates outside the Ken French trading calendar (dropped): {len(off)}")
    if len(off):
        L.append("")
        L.append(_md_table(off.head(50), floatfmt="{:.6f}"))
    L.append(f"- Raw rows with missing or non-positive adjusted close (skipped): "
             f"{diagnostics['bad_price_rows']}")
    L.append(f"- Raw duplicate-date rows (last kept): {diagnostics['duplicate_date_rows']}")
    L.append(f"- Panel rows with missing or zero volume (dollar_volume set to NaN): "
             f"{diagnostics['zero_or_missing_volume_rows']}")
    L.append("\n## 4. Factor units (Ken French, converted from percent to decimal)\n")
    L.append(f"- Factor dates: {fac.index.min():%Y-%m-%d} to {fac.index.max():%Y-%m-%d} "
             f"({len(fac)} days)")
    L.append(f"- Mean daily Mkt-RF: {stats['mktrf_mean']:.6f}; std: {stats['mktrf_std']:.6f}; "
             f"mean daily RF: {stats['rf_mean']:.7f}")
    L.append("\n## 5. Market sanity\n")
    L.append(f"- Correlation of equal-weight universe excess return with Mkt-RF (daily, full "
             f"sample, {mkt['n_days']} days): **{mkt['corr_ew_mktrf']:.4f}**")
    L.append(f"- Annualized volatility of the equal-weight universe excess return: "
             f"**{100 * mkt['ew_ann_vol']:.2f}%**")
    L.append("\n## 6. Liquidity\n")
    L.append(f"- Cross-sectional median ADV at 2024-12-31 (median close×volume over the trailing "
             f"{ADV_WINDOW} days): **${adv_2024.median() / 1e6:,.1f}M** ({len(adv_2024)} tickers)")
    L.append(f"- Cross-sectional median of each ticker's 2024 median dollar volume: "
             f"${med_dv_2024.median() / 1e6:,.1f}M")
    L.append(f"- Minimum dollar_volume where present: ${panel['dollar_volume'].min():,.0f}")
    yearly = dv_w.groupby(dv_w.index.year).median().T
    low = yearly.lt(LOW_LIQUIDITY_USD)
    low_tbl = pd.DataFrame([
        {"ticker": t, "n_years": int(low.loc[t].sum()),
         "years": ", ".join(str(y) for y in low.columns[low.loc[t]])}
        for t in low.index[low.any(axis=1)]])
    L.append(f"- Ticker-years with median daily dollar volume < ${LOW_LIQUIDITY_USD / 1e6:.0f}M "
             f"(possible pre-listing OTC/ADR history under a reused ticker; kept, not dropped; "
             f"the liquidity position limit caps these names near zero): {len(low_tbl)} tickers")
    if len(low_tbl):
        L.append("")
        L.append(_md_table(low_tbl))
    L.append(f"\n## 7. Extreme returns (|ret| > {EXTREME_RET:.0%}), flagged for inspection, not dropped\n")
    L.append(f"- Count: {len(extreme)} of {n_obs:,} observations ({100 * len(extreme) / n_obs:.5f}%)")
    if len(extreme):
        L.append("")
        L.append(_md_table(extreme, floatfmt="{:.4f}"))
    L.append("\n## 8. Known limitations\n")
    L.append("- Survivorship bias: the universe is the current constituent list applied to all history.")
    L.append("- Sector labels are not point-in-time (current GICS sector for all history).")
    L.append("- Yahoo adjusted closes can contain adjustment errors; extreme returns are listed above.")
    path.write_text("\n".join(L) + "\n")
    return stats
