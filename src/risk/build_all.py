"""Build the rolling risk model and its bias-statistic validation (PLAN Phase 2).

`make risk` or `uv run python -m src.risk.build_all [--config experiments/configs/risk.yaml]`.
Outputs:
- data/processed/risk/w<window>_loadings.parquet, w<window>_factor_cov.parquet, w<window>_meta.json
- results/risk/bias_w<window>_<timestamp>.parquet (all z-scores) and _summary.json
"""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd
import yaml

from src.data.build_all import FACTORS_PATH, PANEL_PATH
from src.data.panel import mask_adjustment_errors, returns_wide
from src.risk.bias import bias_zscores, summarize
from src.risk.factor_model import FACTORS, estimate, month_end_dates, to_frames
from src.utils import DATA_PROCESSED, RESULTS, append_run_log, git_commit, utc_timestamp

RISK_DIR = DATA_PROCESSED / "risk"
RESULTS_RISK = RESULTS / "risk"
DEFAULT_CONFIG = "experiments/configs/risk.yaml"


def model_paths(window: int):
    stem = RISK_DIR / f"w{window}"
    return (stem.with_name(stem.name + "_loadings.parquet"),
            stem.with_name(stem.name + "_factor_cov.parquet"),
            stem.with_name(stem.name + "_meta.json"))


def valid_days(excess: pd.DataFrame, dollar_volume: pd.DataFrame,
               min_dollar_volume: float) -> pd.DataFrame:
    """A day is valid for a stock iff it has a return and dollar volume >= min_dollar_volume
    (NaN dollar volume, i.e. zero or missing volume, is invalid). Each cell depends only on
    that day's data, so the rule uses nothing after the rebalance date."""
    return excess.notna() & (dollar_volume >= min_dollar_volume)


def load_inputs(min_dollar_volume: float | None = 1e6, mask_errors: bool = True):
    """Wide daily excess returns (for estimation), total returns (for realized bias-test
    returns), and factors. Unless min_dollar_volume is None, excess returns on invalid days
    (see valid_days) are set to NaN, so estimation and the 80% universe rule in
    factor_model.estimate both use valid days only. This screens out stale prices and thin or
    shell histories (e.g. reused tickers' pre-listing data, a SPAC period). With mask_errors,
    the two Yahoo adjustment errors (src.data.panel.ADJUSTMENT_ERRORS) are missing in both
    frames (brief §4)."""
    panel = pd.read_parquet(PANEL_PATH)
    factors = pd.read_parquet(FACTORS_PATH).set_index("date")
    excess = returns_wide(panel, "excess_ret").reindex(factors.index)
    ret = returns_wide(panel, "ret").reindex(factors.index)
    if mask_errors:
        excess, ret = mask_adjustment_errors(excess), mask_adjustment_errors(ret)
    if min_dollar_volume is not None:
        dv = returns_wide(panel, "dollar_volume").reindex(factors.index)
        excess = excess.where(valid_days(excess, dv, min_dollar_volume))
    return excess, ret, factors


def rebalance_dates(factors: pd.DataFrame, window: int, first_date, last_date) -> pd.DatetimeIndex:
    ends = month_end_dates(pd.DatetimeIndex(factors.index))
    pos = pd.Series(range(len(factors)), index=factors.index)
    ends = ends[pos.reindex(ends).to_numpy() >= window - 1]  # full window available
    if first_date:
        ends = ends[ends >= pd.Timestamp(first_date)]
    if last_date:
        ends = ends[ends <= pd.Timestamp(last_date)]
    return ends


def build_models(cfg: dict, excess, factors):
    dates = rebalance_dates(factors, cfg["window"], cfg.get("first_date"), cfg.get("last_date"))
    return [estimate(excess, factors[FACTORS], t, window=cfg["window"],
                     min_frac=cfg["min_frac"], floor_pct=cfg["floor_pct"]) for t in dates]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default=DEFAULT_CONFIG)
    args = p.parse_args()
    cfg = yaml.safe_load(open(args.config))
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    try:
        if not isinstance(cfg["min_dollar_volume_usd"], (int, float)):
            raise TypeError(f"min_dollar_volume_usd must be a number, got {cfg['min_dollar_volume_usd']!r}")
        excess, ret, factors = load_inputs(cfg["min_dollar_volume_usd"])
        models = build_models(cfg, excess, factors)
        loadings, fcov = to_frames(models)
        RISK_DIR.mkdir(parents=True, exist_ok=True)
        lp, fp, mp = model_paths(cfg["window"])
        loadings.to_parquet(lp, index=False)
        fcov.to_parquet(fp, index=False)
        meta = {"config": cfg, "config_path": args.config, "git_commit": git_commit(),
                "built_utc": utc_timestamp(), "n_dates": len(models),
                "first_date": f"{models[0].date:%Y-%m-%d}", "last_date": f"{models[-1].date:%Y-%m-%d}",
                "units": {"F": "monthly covariance (daily x 21)", "d": "monthly variance (daily x 21)",
                          "B": "loadings on daily decimal factor returns"}}
        mp.write_text(json.dumps(meta, indent=2))
        print(f"risk model: {len(models)} dates {meta['first_date']}..{meta['last_date']}, "
              f"N range {min(m.N for m in models)}-{max(m.N for m in models)}; loadings {loadings.shape}")

        b = cfg["bias"]
        z = bias_zscores(models, ret, factors["RF"], seed=b["seed"],
                         n_portfolios=b["n_portfolios"], gross=b["gross_long_short"])
        summary = summarize(z)
        RESULTS_RISK.mkdir(parents=True, exist_ok=True)
        zpath = RESULTS_RISK / f"bias_w{cfg['window']}_{stamp}.parquet"
        z.to_parquet(zpath, index=False)
        spath = RESULTS_RISK / f"bias_w{cfg['window']}_{stamp}_summary.json"
        spath.write_text(json.dumps({
            "config_path": args.config, "config": cfg, "git_commit": git_commit(),
            "seed": b["seed"], "created_utc": utc_timestamp(), "z_file": zpath.name,
            "summary": summary.to_dict(orient="records"),
            "mean_missing_share": float(z["missing_share"].mean()),
        }, indent=2))
        print(summary[["type", "pooled_std_z", "mean_z", "n_z", "n_dates"]].to_string(index=False))
    except Exception as e:
        append_run_log(args.config, "failed", str(RISK_DIR), f"{type(e).__name__}: {e}")
        raise
    append_run_log(args.config, "ok", str(spath),
                   "; ".join(f"{r.type} pooled std z={r.pooled_std_z:.3f}" for r in summary.itertuples()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
