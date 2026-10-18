"""Risk-model validation figure: bias statistic for random portfolios (brief §5, PLAN Phase 2).

Reads the newest results/risk/bias_w<window>_*_summary.json and its z file; writes
figures/bias_stat.pdf. (a) 12-month rolling std of z = realized / predicted, pooled over
the month's 100 portfolios; (b) pooled distribution of z against N(0, 1).
"""
from __future__ import annotations

import json
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.figures import style
from src.utils import RESULTS

LABELS = {"long_only": "Long-only", "factor_neutral": "Factor-neutral L/S"}
ORDER = ["long_only", "factor_neutral"]


def latest_summary(window: int = 252):
    files = sorted((RESULTS / "risk").glob(f"bias_w{window}_*_summary.json"))
    if not files:
        raise FileNotFoundError("no bias results: run `make risk`")
    meta = json.loads(files[-1].read_text())
    return meta, pd.read_parquet(files[-1].parent / meta["z_file"])


def rolling_std(z: pd.DataFrame, months: int = 12) -> pd.DataFrame:
    """Std of z over the trailing `months` rebalance dates (all portfolios pooled)."""
    out = {}
    for kind, g in z.groupby("type"):
        dates = sorted(g["date"].unique())
        vals = [g[g["date"].isin(dates[max(0, i - months + 1):i + 1])]["z"].std(ddof=1)
                for i in range(months - 1, len(dates))]
        out[kind] = pd.Series(vals, index=pd.DatetimeIndex(dates[months - 1:]))
    return pd.DataFrame(out)


def make() -> str:
    style.apply()
    meta, z = latest_summary()
    pooled = {r["type"]: r["pooled_std_z"] for r in meta["summary"]}
    roll = rolling_std(z)

    fig, (a, b) = plt.subplots(2, 1, figsize=(style.COLUMN_WIDTH_IN, 3.6),
                               gridspec_kw={"height_ratios": [1.15, 1]})
    for i, kind in enumerate(ORDER):
        a.plot(roll.index, roll[kind], color=style.SERIES[i],
               label=f"{LABELS[kind]} (pooled {pooled[kind]:.2f})")
    a.axhline(1.0, color=style.INK_SECONDARY, linewidth=0.6, linestyle="--")
    a.set_ylabel("Rolling 12-mo std of $z$")
    a.set_title("(a) Bias statistic over time", loc="left")
    a.set_ylim(top=2.2)
    a.legend(loc="upper left")

    grid = np.linspace(-5, 5, 401)
    bins = np.linspace(-5, 5, 51)
    for i, kind in enumerate(ORDER):
        b.hist(z.loc[z["type"] == kind, "z"].clip(-5, 5), bins=bins, density=True,
               histtype="step", color=style.SERIES[i], linewidth=1.0, label=LABELS[kind])
    b.plot(grid, np.exp(-grid**2 / 2) / np.sqrt(2 * np.pi), color=style.INK, linewidth=0.8,
           linestyle=":", label="N(0, 1)")
    b.set_xlabel("$z$ = realized next-month return / predicted volatility")
    b.set_ylabel("Density")
    b.set_title("(b) Pooled distribution of $z$", loc="left")
    b.legend(loc="upper left")
    fig.tight_layout(h_pad=0.8)
    return str(style.save(fig, "bias_stat"))


if __name__ == "__main__":
    print(make())
    sys.exit(0)
