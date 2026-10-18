"""F5 (RQ3/H4): big-M vs perspective. (a) median root gap, (b) median time to the 1e-4 gap
(censored at 300 s), by factor-bound tightness over the H4 design. Reads the newest finished
results/rq3 run; writes figures/f5_formulations.pdf."""
from __future__ import annotations

import sys

import matplotlib.pyplot as plt
import pandas as pd

from experiments.common import latest_done
from experiments.designs import config
from src.figures import style

LEVELS = ["loose", "base", "tight"]


def make() -> str:
    style.apply()
    h = pd.read_parquet(latest_done("rq3") / "h4.parquet")
    limit = config("rq3")["h4"]["time_limit"]
    h["t"] = h["runtime"].clip(upper=limit)
    fig, (a, b) = plt.subplots(1, 2, figsize=(style.COLUMN_WIDTH_IN, 1.9))
    for i, (form, label) in enumerate((("bigm", "Big-M"), ("perspective", "Perspective"))):
        g = h[h["formulation"] == form].groupby("tightness")
        a.plot(LEVELS, [100 * g["root_gap"].median()[t] for t in LEVELS], color=style.SERIES[i],
               marker="o", markersize=3, label=label)
        b.plot(LEVELS, [g["t"].median()[t] for t in LEVELS], color=style.SERIES[i], marker="o",
               markersize=3, label=label)
    a.set_ylabel("Median root gap (%)")
    b.set_ylabel("Median time to gap (s)")
    b.set_yscale("log")
    a.set_title("(a) Root gap", loc="left")
    b.set_title("(b) Time to 1e-4 gap", loc="left")
    a.legend(fontsize=6)
    fig.tight_layout(w_pad=0.6)
    return str(style.save(fig, "f5_formulations"))


if __name__ == "__main__":
    print(make())
    sys.exit(0)
