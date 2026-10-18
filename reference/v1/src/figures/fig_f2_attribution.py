"""F2 (RQ1): constraint attribution at the base case. Each family's alpha contribution α'w_c as a
share of the ideal portfolio's alpha α'w_α (src/opt/attribution.py), averaged over dates
(momentum) and date × draw (synthetic). Means are additive, so the steps end exactly at the
mean share kept, α'w*/α'w_α (the small KKT `residual` piece is included in that total).
Reads the newest finished results/rq1 run; writes figures/f2_attribution.pdf."""
from __future__ import annotations

import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from experiments.common import latest_done
from src.figures import style
from src.opt.attribution import FAMILY_ORDER


def make() -> str:
    style.apply()
    at = pd.read_parquet(latest_done("rq1") / "attribution.parquet")
    fams = [f for f in FAMILY_ORDER if f"alpha_{f}" in at.columns]
    fig, axes = plt.subplots(1, 2, figsize=(style.COLUMN_WIDTH_IN, 2.4), sharey=True)
    for ax, (kind, title) in zip(axes, (("momentum", "Momentum"), ("synthetic", "Synthetic"))):
        a = at[at["alpha"] == kind]
        shares = [100 * (a[f"alpha_{f}"] / a["alpha_ideal"]).mean() for f in fams]
        kept = 100 * (a["alpha_total"] / a["alpha_ideal"]).mean()
        labels = ["Ideal", *fams, "Kept"]
        y = np.arange(len(labels))[::-1]
        level = 100.0
        ax.barh(y[0], 100.0, color=style.SERIES[0], height=0.6)
        for i, s in enumerate(shares, start=1):
            ax.barh(y[i], s, left=level, color=style.SERIES[1] if s < 0 else style.SERIES[2], height=0.6)
            level += s
        ax.barh(y[-1], kept, color=style.SERIES[0], height=0.6)
        ax.set_yticks(y, labels, fontsize=6)
        ax.set_title(title, loc="left")
        ax.set_xlabel("% of ideal alpha (mean)")
    fig.tight_layout(w_pad=0.4)
    return str(style.save(fig, "f2_attribution"))


if __name__ == "__main__":
    print(make())
    sys.exit(0)
