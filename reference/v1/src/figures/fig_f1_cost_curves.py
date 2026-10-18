"""F1 (RQ1): constraint cost curves. Relative expected-alpha loss 1 − A(bound)/A(family off) along
each family's E1 grid (loose → tight), median over dates (momentum) and over date × draw
(synthetic). Reads the newest finished results/rq1 run; writes figures/f1_cost_curves.pdf."""
from __future__ import annotations

import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from experiments.common import latest_done
from experiments.designs import config
from src.figures import style

PANELS = ["dollar", "beta", "style:Mom", "style_all", "sector", "gross", "position", "liquidity"]
TITLES = {"dollar": "Dollar", "beta": "Beta", "style:Mom": "Mom only", "style_all": "All style",
          "sector": "Sector", "gross": "Gross", "position": "Position cap", "liquidity": "Liquidity"}


def losses(pts: pd.DataFrame, family: str) -> pd.DataFrame:
    f = pts[pts["family"] == family]
    off = f[f["off"]].set_index(["date", "alpha", "draw"])["A"]
    on = f[~f["off"]].set_index(["date", "alpha", "draw"])
    on = on.assign(loss=1.0 - on["A"] / off.reindex(on.index).to_numpy())
    return on.reset_index()


def make() -> str:
    style.apply()
    pts = pd.read_parquet(latest_done("rq1") / "points.parquet")
    grids = config("rq1")["sweeps"]
    fig, axes = plt.subplots(2, 4, figsize=(2 * style.COLUMN_WIDTH_IN + 0.16, 3.4), sharey=False)
    for ax, fam in zip(axes.ravel(), PANELS):
        L = losses(pts, fam)
        vals = [v for v in grids[fam] if v is not None]
        for i, (kind, label) in enumerate((("momentum", "Momentum"), ("synthetic", "Synthetic (IC 0.05)"))):
            med = [100 * L[(L["alpha"] == kind) & np.isclose(L["value"], v)]["loss"].median() for v in vals]
            ax.plot(range(len(vals)), med, color=style.SERIES[i], marker="o", markersize=2.5, label=label)
        ax.set_xticks(range(len(vals)), [f"{v:g}" for v in vals], fontsize=6)
        ax.set_title(TITLES[fam], loc="left")
        ax.axhline(0, color=style.INK_SECONDARY, linewidth=0.5)
    for ax in axes[:, 0]:
        ax.set_ylabel("Alpha loss vs off (%)")
    for ax in axes[1]:
        ax.set_xlabel("Bound (loose → tight)")
    axes[0, 0].legend(loc="upper left", fontsize=6)
    fig.tight_layout(h_pad=0.6, w_pad=0.5)
    return str(style.save(fig, "f1_cost_curves"))


if __name__ == "__main__":
    print(make())
    sys.exit(0)
