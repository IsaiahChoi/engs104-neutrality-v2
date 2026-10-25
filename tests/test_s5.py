"""S5 pass 1 (Isaiah's S5 addendum, PROGRESS 2026-10-25; Decision 58(b)): Fig. 2's height reduced
from 3.4 in to about 2.6 in, keeping its content (the closed form, the idealized and base-mandate
points of all three alphas, every C1 point) and its legibility (text ≥ 8 pt at 3.5 in, the legend
clear of the axes and their labels). Tests first."""
from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.text import Text
from pypdf import PdfReader

from src.figures import fig_c

IN = 72.0


def _size(path) -> tuple[float, float]:
    b = PdfReader(path).pages[0].mediabox
    return float(b.width) / IN, float(b.height) / IN


def test_fig2_keeps_its_content():
    ide = fig_c._read("c1", "c1_idealized")
    ide = ide[ide["mandate"] == "factor"]
    pts = fig_c._read("c1", "c1_points")
    kinds = [k for k, *_ in fig_c.ALPHAS]
    fig = fig_c.fig2_figure()
    try:
        ax, = fig.get_axes()
        labels = [t.get_text() for t in ax.get_legend().get_texts()]
        assert len(labels) == 1 + 2 * len(kinds) == 7
        assert labels[0].startswith("closed form")
        lines = ax.get_lines()
        assert len(lines) == 7
        n_pts = sum(len(ln.get_xdata()) for ln in lines[1:])
        assert n_pts == ide["alpha"].isin(kinds).sum() + pts["alpha"].isin(kinds).sum()
    finally:
        plt.close(fig)


def test_fig2_is_about_2p6_in_tall_and_legible():
    fig = fig_c.fig2_figure()
    try:
        w, h = fig.get_size_inches()
        assert w <= 3.5 + 1e-9 and h <= 2.6 + 1e-9                 # S4c version: 3.4 in
        sizes = [t.get_fontsize() for t in fig.findobj(Text) if t.get_visible() and t.get_text().strip()]
        assert sizes and min(sizes) >= 8.0
        fig.canvas.draw()
        r = fig.canvas.get_renderer()
        ax, = fig.get_axes()
        leg = ax.get_legend().get_window_extent(r)
        for other in (ax.get_window_extent(r), ax.xaxis.label.get_window_extent(r),
                      *(t.get_window_extent(r) for t in ax.get_xticklabels() if t.get_text())):
            assert not leg.overlaps(other)
    finally:
        plt.close(fig)
    _, h_pdf = _size(fig_c.fig2_alignment())
    assert h_pdf <= 2.6                                              # S4c version: 3.05 in as saved
