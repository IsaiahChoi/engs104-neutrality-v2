"""Shared figure style: IEEE two-column sizes, vector PDF, validated categorical palette.

Categorical slots are assigned in fixed order and follow the entity, never its rank
(slots 1-2 validated for CVD and contrast on a light surface with the dataviz validator).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.utils import ROOT  # noqa: E402

FIGURES = ROOT / "figures"
COLUMN_WIDTH_IN = 3.5          # IEEE two-column: one column
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]   # categorical slots 1-4
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#d9d8d4"


def apply() -> None:
    plt.rcParams.update({
        "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "legend.fontsize": 7,
        "xtick.labelsize": 7, "ytick.labelsize": 7, "font.family": "serif",
        "pdf.fonttype": 42, "axes.edgecolor": INK_SECONDARY, "axes.labelcolor": INK,
        "xtick.color": INK_SECONDARY, "ytick.color": INK_SECONDARY, "axes.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
        "grid.color": GRID, "grid.linewidth": 0.4, "lines.linewidth": 1.0,
        "legend.frameon": False, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    })


def save(fig, name: str) -> Path:
    FIGURES.mkdir(exist_ok=True)
    path = FIGURES / f"{name}.pdf"
    fig.savefig(path, metadata={"CreationDate": None})   # byte-identical rebuilds
    plt.close(fig)
    return path
