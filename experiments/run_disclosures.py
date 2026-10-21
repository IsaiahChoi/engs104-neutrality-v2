"""Disclosure facts (DESIGN §11.5 item 3; S4): `make disclosures` → results/disclosures/run_<UTC>/.

One-pass winsorization (src/alpha/momentum.winsorized_zscore: the z-score clipped at ±3, then
re-standardized) can leave |z| above 3. For every risk-model month-end where α_mom is defined
(the full eligible universe, as in C3), this records the cross-section size, the largest |z|
after winsorization, and the number of names with |z| > 3; month-ends without the 252-day
lookback are recorded in disclosures_skipped with the reason, never dropped silently.
Item 2's multi-session count is the v2 offline rebuild's (results/data_report.md), not run here.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from experiments.common import fail, finish, open_run
from experiments.designs import config
from src.alpha.momentum import WINSOR, momentum_score, winsorized_zscore
from src.opt.inputs import date_inputs, market_data, rebalance_dates

CONFIG = "experiments/configs/disclosures.yaml"


def z_stats(z: np.ndarray, clip: float = WINSOR) -> dict:
    z = np.asarray(z, float)
    return {"n": int(z.size), "max_abs_z": float(np.abs(z).max()), "n_above": int((np.abs(z) > clip).sum())}


def summarize(rows: list[dict], skipped: list[dict]) -> dict:
    df = pd.DataFrame(rows)
    top = df.loc[df["max_abs_z"].idxmax()]
    return {"n_dates": len(df), "n_skipped": len(skipped), "skipped": skipped,
            "first": str(df["date"].iloc[0]), "last": str(df["date"].iloc[-1]),
            "max_abs_z": float(top["max_abs_z"]), "max_abs_z_date": str(top["date"]),
            "n_dates_above": int((df["n_above"] > 0).sum()), "n_names_above": int(df["n_above"].sum()),
            "n_names": int(df["n"].sum()), "clip": WINSOR}


def main() -> int:
    run = None
    try:
        config("disclosures")
        run, _ = open_run("disclosures", CONFIG, status="ok")
        ret = market_data().ret
        rows, skipped = [], []
        for d in rebalance_dates():
            ds = f"{d:%Y-%m-%d}"
            di = date_inputs(d)
            try:
                m = momentum_score(ret, di.model.tickers, di.model.date)
            except ValueError as err:                     # α_mom undefined (lookback): recorded
                skipped.append({"date": ds, "reason": str(err)})
                continue
            rows.append({"date": ds, **z_stats(winsorized_zscore(m))})
        summary = summarize(rows, skipped)
        (run / "summary.json").write_text(json.dumps(summary, indent=1))
        finish(run, CONFIG, {"disclosures_z": pd.DataFrame(rows),
                             "disclosures_skipped": pd.DataFrame(skipped, columns=["date", "reason"])},
               f"disclosures: {summary['n_dates']} month-ends; max |z| {summary['max_abs_z']:.4g}",
               extra_files=[run / "summary.json"])
        print(json.dumps(summary, indent=1))
    except Exception as e:
        fail(run, CONFIG, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
