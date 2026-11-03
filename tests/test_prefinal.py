"""Pre-FINAL session (Isaiah's note, PROGRESS 2026-11-02; S5 pass 1 issue 21): in Fig. 2, α∥'s
filled (full factor neutrality) and hollow (base mandate) triangles must be distinguishable where
they overlap at φ = 1. Every α∥ point lies on φ = 1: the filled ones stack at (1, 0) on the end of
the closed-form curve, and the hollow ones sit on the x = 1 gridline, which ran through their
centres and made them read as filled. Checked on the rendered pixels at 600 dpi. tests/test_s5.py
still pins the content, size, fonts and legend placement. Tests first."""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgba

from src.figures import fig_c, style

DPI = 600
TOL = 4                                   # 8-bit channel tolerance for antialiasing


def _render():
    fig = fig_c.fig2_figure()
    fig.set_dpi(DPI)
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[..., :3].astype(int)
    ax, = fig.get_axes()
    return fig, ax, img


def _pixel(ax, img, x, y, dy_pt=0.0):
    px, py = ax.transData.transform((x, y))
    py += dy_pt * DPI / 72.0
    return img[img.shape[0] - int(round(py)), int(round(px))]


def _rgb(color):
    return np.array([round(255 * c) for c in to_rgba(color)[:3]])


def _par_lines(ax):
    i = [k for k, *_ in fig_c.ALPHAS].index("par")
    lines = ax.get_lines()
    return lines[0], lines[1 + 2 * i], lines[2 + 2 * i], style.SERIES[i]


def test_fig2_par_hollow_markers_are_opaque_background():
    fig, ax, _ = _render()
    try:
        _, filled, hollow, color = _par_lines(ax)
        assert np.allclose(to_rgba(filled.get_markerfacecolor()), to_rgba(color))
        face = to_rgba(hollow.get_markerfacecolor())
        assert face[3] == 1.0                                        # opaque: stacks occlude
        assert np.allclose(face, to_rgba(ax.get_facecolor()))        # reads as hollow
        assert np.allclose(to_rgba(hollow.get_markeredgecolor()), to_rgba(color))
    finally:
        plt.close(fig)


def test_fig2_par_hollow_centres_show_background_not_grid():
    fig, ax, img = _render()
    try:
        _, _, hollow, _ = _par_lines(ax)
        x, y = np.asarray(hollow.get_xdata(), float), np.asarray(hollow.get_ydata(), float)
        assert np.allclose(x, 1.0, rtol=0, atol=1e-12)                # φ = 1 up to rounding
        disp = ax.transData.transform(np.column_stack([x, y])) * 72.0 / DPI       # points
        ms = hollow.get_markersize()
        isolated = [j for j in range(len(y))
                    if all(np.hypot(*(disp[j] - disp[k])) >= ms for k in range(len(y)) if k != j)]
        assert len(isolated) >= 2                                    # guard against a vacuous pass
        bg = _rgb(ax.get_facecolor())
        for j in isolated:
            assert np.all(np.abs(_pixel(ax, img, x[j], y[j]) - bg) <= TOL), (j, y[j])
    finally:
        plt.close(fig)


def test_fig2_par_filled_stack_is_drawn_whole_above_the_curve():
    fig, ax, img = _render()
    try:
        curve, filled, hollow, color = _par_lines(ax)
        assert filled.get_zorder() > curve.get_zorder()
        assert not filled.get_clip_on()                              # (1, 0) sits on the y-limit
        y = np.asarray(filled.get_ydata(), float)
        assert np.allclose(filled.get_xdata(), 1.0, rtol=0, atol=1e-12) and np.all(y == 0.0)
        c = _rgb(color)
        half = filled.get_markersize() / 2
        for dy in (0.0, -0.75 * half):                               # centre and near the base
            assert np.all(np.abs(_pixel(ax, img, 1.0, 0.0, dy) - c) <= TOL), dy
    finally:
        plt.close(fig)
