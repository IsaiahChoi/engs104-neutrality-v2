"""F4 (RQ3): MIQP value function U*(b_Mom) (2020-03, N = 250, K = 60; polished U*) with the
tangent lines at the base bound implied by the relaxation and fixed-integer duals.
Reads the newest finished results/rq3 run; writes figures/f4_value_function.pdf."""
from __future__ import annotations

import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from experiments.common import latest_done
from src.figures import style


def make() -> str:
    style.apply()
    run = latest_done("rq3")
    sw = pd.read_parquet(run / "f4_sweep.parquet").sort_values("bound_value")
    du = pd.read_parquet(run / "f4_duals.parquet").iloc[0]
    fig, ax = plt.subplots(figsize=(style.COLUMN_WIDTH_IN, 2.4))
    ax.plot(sw["bound_value"], 1e4 * sw["U"], color=style.INK, marker="o", markersize=2,
            linewidth=0.8, label="MIQP $U^*$ (re-solved)")
    b0, u0 = du["bound"], du["U_star"]
    xs = np.array([sw["bound_value"].min(), sw["bound_value"].max()])
    for i, (key, label) in enumerate((("mu_relax", "Relaxation dual"), ("mu_fixed", "Fixed-integer dual"))):
        ax.plot(xs, 1e4 * (u0 + du[key] * (xs - b0)), color=style.SERIES[i], linewidth=1.0,
                linestyle="--" if i == 0 else "-", label=label)
    ax.axvline(b0, color=style.INK_SECONDARY, linewidth=0.5, linestyle=":")
    ax.set_xlabel(r"Mom bound $b_{\mathrm{Mom}}$")
    ax.set_ylabel(r"$U^*$ (bp/month)")
    ax.legend(loc="lower right", fontsize=6)
    fig.tight_layout()
    return str(style.save(fig, "f4_value_function"))


if __name__ == "__main__":
    print(make())
    sys.exit(0)
