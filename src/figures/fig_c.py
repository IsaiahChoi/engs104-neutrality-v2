"""Figs. 1–3 and the C3 summary figure (DESIGN §10), from the newest finished C1–C3 runs.

Final since S3 (RUNBOOK §4 S3 step 4, after GATE C); until then the file names carried
"preliminary" (RUNBOOK §4, S2). Print figures: one IEEE
column (3.5 in), text ≥ 8 pt, vector PDF with deterministic metadata (byte-identical rebuilds)
plus a 300-dpi PNG in figures/png/. Identity is never carried by color alone: series also differ
in line style or marker, stacks in hatching, and every figure has a legend (src/figures/style.py
slots 1–4 pass the dataviz validator; slots 3–4 are below 3:1 contrast on white, so they always
come with labels, markers, or hatching).

- Fig. 1 (C2): A*(b)/A*(off) against the bound in four panels (DESIGN §10 as edited at the S4
  read): liquidity θ, sector, all styles jointly and the Mom bound; α_mom median over D12 with its
  interquartile band, the α⊥ and α∥ medians dashed and dash-dotted on the two factor panels, and
  the base value marked. The other families are flat; the text gives their tightest-point values.
- Fig. 2 (C1): retained fraction against φ: the closed form √(1 − φ), the idealized full-factor-
  neutrality solves (filled, three alphas × D12) and the base-mandate solves (hollow), both
  relative to the unconstrained, costless P-RB.
- Fig. 3 (C1): the Stubbs–Vandenbussche losses at λ* for α_mom by date, stacked in five groups,
  with the fixed-risk loss A*_unc − A* marked (the stack exceeds it: the unconstrained portfolio
  at λ* carries more than 3% risk; DESIGN §10). Dates where the risk budget is slack are omitted
  and listed in the axis label (μ_risk = λ_min there).
- C3 summary: A*, φ, and the elasticities of the four families with the largest median, by date.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from experiments.common import latest_done
from src.figures import style

TAG = ""                             # "_preliminary" until GATE C (S2)
FIG1_PANELS = [("liquidity", "Liquidity cap"), ("sector", "Sector"), ("style_all", "All styles jointly"),
               ("style:Mom", "Momentum")]
FIG1_XLABEL = {"liquidity": "θ (fraction of ADV)", "sector": "bound on each net weight",
               "style_all": "exposure bound", "style:Mom": "exposure bound"}
FIG1_BASE = {"liquidity": "liquidity_theta", "sector": "sector", "style_all": "style", "style:Mom": "style"}
FACTOR_FAMILIES = {"beta", "style_all", "style:Mom"}
ALPHAS = [("mom", r"$\alpha_{\mathrm{mom}}$", "-", "o"), ("perp", r"$\alpha_\perp$", "--", "s"),
          ("par", r"$\alpha_\parallel$", "-.", "^")]
ATT_GROUPS = [("Factor (beta, style)", ("beta", "style"), "///"),
              ("Dollar and sector", ("dollar", "sector"), "\\\\\\"),
              ("Gross and position caps (u, θ)", ("gross", "position"), "xx"),
              ("Costs (borrow, trading)", ("borrow", "trading"), ".."),
              ("Zero names and residual", ("inactive", "residual"), "")]
GRAY = "#8c8b87"


def _apply() -> None:
    style.apply()
    plt.rcParams.update({"font.size": 8, "axes.labelsize": 8, "legend.fontsize": 8,
                         "xtick.labelsize": 8, "ytick.labelsize": 8, "hatch.linewidth": 0.5})


def _save(fig, name: str) -> Path:
    png = style.FIGURES / "png"
    png.mkdir(parents=True, exist_ok=True)
    fig.savefig(png / f"{name}.png", dpi=300, metadata={"Software": None})
    return style.save(fig, name)


def _read(name: str, table: str) -> pd.DataFrame:
    return pd.read_parquet(latest_done(name) / f"{table}.parquet")


def fig1_cost_curves() -> Path:
    _apply()
    from src.opt.continuous import load_config
    base = load_config()[0]
    pts = _read("c2", "c2_points")
    pts = pts[~pts["off"]]
    fig, axes = plt.subplots(2, 2, figsize=(style.COLUMN_WIDTH_IN, 3.3), sharey=True)
    for ax, (fam, title) in zip(axes.flat, FIG1_PANELS):
        for i, (kind, label, ls, mk) in enumerate(ALPHAS):
            if kind != "mom" and fam not in FACTOR_FAMILIES:
                continue
            g = pts[(pts["family"] == fam) & (pts["alpha"] == kind)]
            q = g.groupby("value")["retained_vs_off"].quantile([0.25, 0.5, 0.75]).unstack()
            if kind == "mom":
                ax.fill_between(q.index, q[0.25], q[0.75], color=style.SERIES[i], alpha=0.2,
                                linewidth=0)
            ax.plot(q.index, q[0.5], ls=ls, marker=mk, ms=3, color=style.SERIES[i], label=label)
        ax.axvline(getattr(base, FIG1_BASE[fam]), color=style.INK_SECONDARY, lw=0.6, ls=":",
                   label="base value")
        ax.set_title(title, loc="left")
        ax.set_xlabel(FIG1_XLABEL[fam])
        ax.axhline(1.0, color=style.INK_SECONDARY, lw=0.5)
    for ax in axes[:, 0]:
        ax.set_ylabel(r"$A^*(b)/A^*(\mathrm{off})$")
    seen = {}
    for ax in axes.flat:
        for hh, ll in zip(*ax.get_legend_handles_labels()):
            seen.setdefault(ll, hh)
    h, lab = list(seen.values()), list(seen.keys())
    fig.legend(h, lab, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.03), columnspacing=0.8,
               handletextpad=0.4)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return _save(fig, f"fig1_cost_curves{TAG}")


def fig2_alignment() -> Path:
    _apply()
    ide = _read("c1", "c1_idealized")
    ide = ide[ide["mandate"] == "factor"]
    pts = _read("c1", "c1_points")
    fig, ax = plt.subplots(figsize=(style.COLUMN_WIDTH_IN, 3.4))
    phi = np.linspace(0, 1, 201)
    ax.plot(phi, np.sqrt(1 - phi), color=style.INK, lw=1.0, label=r"closed form $\sqrt{1-\varphi}$")
    for i, (kind, label, _, mk) in enumerate(ALPHAS):
        g = ide[ide["alpha"] == kind]
        ax.plot(g["phi"], g["retained_num"], ls="none", marker=mk, ms=4, color=style.SERIES[i],
                label=f"{label}, full factor neutrality")
        r = pts[pts["alpha"] == kind]
        ax.plot(r["phi"], r["retained"], ls="none", marker=mk, ms=4, mfc="none",
                color=style.SERIES[i], label=f"{label}, base mandate")
    ax.set_xlabel(r"alignment share $\varphi$")
    ax.set_ylabel(r"retained fraction $A^*/A^*_{\mathrm{unc}}$")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.05)
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.2), ncol=2, columnspacing=0.8,
              handletextpad=0.3)
    fig.tight_layout()
    return _save(fig, f"fig2_alignment{TAG}")


def fig3_attribution() -> Path:
    _apply()
    att = _read("c1", "c1_attribution")
    pts = _read("c1", "c1_points")
    att, pts = att[att["alpha"] == "mom"], pts[pts["alpha"] == "mom"].set_index("date")
    slack = sorted(pts.index[~pts["risk_binding"]])
    dates = [d for d in sorted(pts.index) if d not in slack]
    fig, ax = plt.subplots(figsize=(style.COLUMN_WIDTH_IN, 3.9))
    x = np.arange(len(dates))
    pos, neg = np.zeros(len(dates)), np.zeros(len(dates))
    for i, (label, fams, hatch) in enumerate(ATT_GROUPS):
        v = np.array([1e4 * att[(att["date"] == d) & att["family"].isin(fams)]["loss"].sum()
                      for d in dates])
        color = style.SERIES[i] if i < len(style.SERIES) else GRAY
        bottom = np.where(v >= 0, pos, neg)
        ax.bar(x, v, 0.75, bottom=bottom, color=color, hatch=hatch, edgecolor="white",
               linewidth=0.5, label=label)
        pos, neg = pos + np.maximum(v, 0), neg + np.minimum(v, 0)
    ax.plot(x, 1e4 * pts.loc[dates, "fixed_risk_loss"], ls="none", marker="_", ms=10, mew=1.5,
            color=style.INK, label=r"fixed-risk loss $A^*_{\mathrm{unc}} - A^*$")
    ax.axhline(0, color=style.INK_SECONDARY, lw=0.5)
    ax.set_xticks(x, [d[:7] for d in dates], rotation=90)
    ax.set_ylabel("alpha lost (bp/month)")
    if slack:
        ax.set_xlabel("risk budget slack, omitted: " + ", ".join(d[:7] for d in slack))
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.32), ncol=2, columnspacing=0.8,
              handletextpad=0.4)
    fig.tight_layout()
    return _save(fig, f"fig3_attribution{TAG}")


def fig_c3_summary() -> Path:
    _apply()
    pts = _read("c3", "c3_points").sort_values("date")
    t = pd.to_datetime(pts["date"])
    ecols = [c for c in pts.columns if c.startswith("e_") and ":" not in c]
    top = sorted(ecols, key=lambda c: -pts[c].median())[:4]
    fig, axes = plt.subplots(3, 1, figsize=(style.COLUMN_WIDTH_IN, 4.2), sharex=True)
    axes[0].plot(t, 1e4 * pts["A"], color=style.SERIES[0])
    axes[0].set_ylabel(r"$A^*$ (bp/month)")
    axes[1].plot(t, pts["phi"], color=style.SERIES[0])
    axes[1].set_ylabel(r"$\varphi$")
    for i, (c, ls) in enumerate(zip(top, ["-", "--", "-.", ":"])):
        axes[2].plot(t, pts[c], ls=ls, color=style.SERIES[i], label=c[2:])
    axes[2].set_ylabel("elasticity $e_j$")
    axes[2].legend(loc="upper right", ncol=2)
    fig.tight_layout()
    return _save(fig, f"fig_c3_summary{TAG}")


FIGURES = [("fig1_cost_curves", fig1_cost_curves), ("fig2_alignment", fig2_alignment),
           ("fig3_attribution", fig3_attribution), ("fig_c3_summary", fig_c3_summary)]
