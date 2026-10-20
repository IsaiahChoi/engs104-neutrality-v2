"""Figs. 4–5 and Tables II–III (DESIGN §10), from the newest finished I1, I2, N1 and N2 runs.

Same print rules as src/figures/fig_c.py: one IEEE column, text ≥ 8 pt, vector PDF with
deterministic metadata plus a 300-dpi PNG; identity never by color alone (line style, marker).
- Fig. 4 (I2): P-MI's value V(b) (combined certification) and the continuous baseline's value
  U(b) against the I2 bound, one panel per instance, in bp/month; at the estimator points 0.5b,
  b, 1.5b, tangent segments through (e, V(e)) with each estimator's slope (big-M relaxation dual,
  perspective relaxation slope, fixed-integer dual).
- Fig. 5 (N1): root gap (root bound − best known value)/|best known value| and Work against
  tightness, one marker per instance (default presolve), median connected, per arm; solves that
  stopped at the WorkLimit are hollow. Root gaps ≤ 1e-6 are drawn at 1e-6 (log axis); their
  count is printed.
- Table II (I1): each estimator's relative error |μ̂ − s|/|s| over binding cases with n, by f
  (K = round(f·S) differs by date), δ = 10%, and how many lie in [L, H]; the convex baseline's
  dual-versus-secant error at the same step beneath. report/tables/table2_i1.tex.
- Table III (N2): (b) convex solver variants against the reference (max over the dates);
  (a) MIQP arms at each s_obj. report/tables/table3_n2.tex.
Tables are bare tabular environments (writing mode B: no captions).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from experiments.common import latest_done
from src.analysis import s3 as A
from src.figures import style
from src.figures.fig_c import _apply, _save
from src.utils import ROOT

TABLES = ROOT / "report" / "tables"
EST_STYLE = [("bigm_relax", "mu_bigm_relax", "big-M relaxation dual", ":", 1),
             ("perspective", "persp_slope", "perspective relaxation slope", "--", 2),
             ("fixed", "mu_fixed", "fixed-integer dual", "-.", 3)]
ARM_STYLE = [("bigm", "big-M", "o", "-", 0), ("perspective", "perspective (default scaling)", "s", "--", 1),
             ("perspective_rescaled", "perspective (rescaled)", "^", "-.", 2)]
TIGHT = ["loose", "base", "tight"]
GAP_FLOOR = 1e-6


def _read(name: str, table: str) -> pd.DataFrame:
    return pd.read_parquet(latest_done(name) / f"{table}.parquet")


def fig4_value_functions() -> Path:
    _apply()
    pts = _read("i2", "i2_points").sort_values("bound")
    base = _read("i2", "i2_baseline").sort_values("bound")
    insts = sorted(pts["instance"].unique())
    fig, axes = plt.subplots(len(insts), 1, figsize=(style.COLUMN_WIDTH_IN, 4.6), sharex=True)
    axes = np.atleast_1d(axes)
    half = 0.12 * float(pts["b_base"].iloc[0])
    for ax, inst in zip(axes, insts):
        g, gb = pts[pts["instance"] == inst], base[base["instance"] == inst]
        ax.plot(g["bound"], 1e4 * g["V"], color=style.SERIES[0], marker="o", ms=2.5, lw=1.0,
                label="P-MI value $V(b)$")
        ax.plot(gb["bound"], 1e4 * gb["value"], color=style.INK_SECONDARY, ls="-", lw=0.8,
                label="continuous baseline $U(b)$")
        for _, r in g[g["estimator"].astype(bool)].iterrows():
            for _, col, label, ls, slot in EST_STYLE:
                mu = r[col]
                if np.isfinite(mu):
                    x = np.array([r["bound"] - half, r["bound"] + half])
                    ax.plot(x, 1e4 * (r["V"] + mu * (x - r["bound"])), ls=ls, lw=1.0,
                            color=style.SERIES[slot], label=label)
        date, rest = inst.split("_N")
        ax.set_title(f"{date}, N = {rest.split('_')[0]}, K = {inst.split('_K')[1]}", loc="left")
        ax.set_ylabel("value (bp/month)")
    axes[-1].set_xlabel(f"bound $b$ on {pts['key'].iloc[0]} (net weight)")
    seen = {}
    for hh, ll in zip(*axes[0].get_legend_handles_labels()):
        seen.setdefault(ll, hh)
    fig.legend(list(seen.values()), list(seen.keys()), loc="upper center", ncol=2,
               bbox_to_anchor=(0.5, 1.06), columnspacing=0.8, handletextpad=0.4)
    fig.tight_layout()
    return _save(fig, "fig4_value_functions")


def fig5_formulations() -> Path:
    _apply()
    tab = A.n1_table(_read("n1", "n1_solves"))
    tab = tab[tab["presolve"] == -1]
    fig, axes = plt.subplots(2, 1, figsize=(style.COLUMN_WIDTH_IN, 4.2), sharex=True)
    x0 = {t: i for i, t in enumerate(TIGHT)}
    clipped = 0
    for k, (arm, label, mk, ls, slot) in enumerate(ARM_STYLE):
        g = tab[tab["arm"] == arm]
        off = (k - 1) * 0.18
        for ax, col in ((axes[0], "root_gap"), (axes[1], "work")):
            y = g[col].astype(float).to_numpy()
            if col == "root_gap":
                clipped += int((y <= GAP_FLOOR).sum())
                y = np.maximum(y, GAP_FLOOR)
            xs = g["tightness"].map(x0).to_numpy() + off
            cen = g["censored"].to_numpy(bool)
            ax.plot(xs[~cen], y[~cen], ls="none", marker=mk, ms=3, color=style.SERIES[slot], alpha=0.8)
            ax.plot(xs[cen], y[cen], ls="none", marker=mk, ms=4, mfc="none", color=style.SERIES[slot])
            med = [float(np.median(y[g["tightness"].to_numpy() == t])) for t in TIGHT]
            ax.plot(np.arange(3) + off, med, ls=ls, color=style.SERIES[slot], lw=1.0,
                    label=label if col == "root_gap" else None)
    for ax in axes:
        ax.set_yscale("log")
    axes[0].set_ylabel("root gap")
    axes[1].set_ylabel("Work (Gurobi units)")
    axes[1].set_xticks(range(3), TIGHT)
    axes[1].set_xlabel("mandate tightness (style and beta bounds)")
    axes[0].plot([], [], ls="none", marker="o", mfc="none", color=style.INK_SECONDARY,
                 label="hollow: stopped at the WorkLimit")
    fig.legend(loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.05), columnspacing=0.8,
               handletextpad=0.4)
    fig.tight_layout()
    if clipped:
        print(f"fig5: {clipped} root gaps ≤ {GAP_FLOOR:g} drawn at {GAP_FLOOR:g}")
    return _save(fig, "fig5_formulations")


# ----- tables -----

def _sci(x, nd: int = 2) -> str:
    """LaTeX scientific notation with nd significant digits; '--' for nan."""
    if x is None or not np.isfinite(x):
        return "--"
    if x == 0:
        return "$0$"
    m, e = f"{float(x):.{nd - 1}e}".split("e")
    return f"${m}\\times10^{{{int(e)}}}$"


def _write(name: str, lines: list[str]) -> Path:
    TABLES.mkdir(parents=True, exist_ok=True)
    p = TABLES / f"{name}.tex"
    p.write_text("% generated by `make figures` (src/figures/fig_s3.py). Do not edit.\n"
                 + "\n".join(lines) + "\n")
    return p


def table2_i1() -> Path:
    est, base = _read("i1", "i1_estimators"), _read("i1", "i1_baseline")
    by = A.error_summary(A.i1_long(est[est["rel_delta"] == 0.10]), by=["f"])
    lines = [r"\begin{tabular}{llrrrr}", r"\hline",
             r"estimator & $f$ & $n$ & median err. & max err. & in $[L,H]$ \\", r"\hline"]
    for name, _, label, _, _ in EST_STYLE:
        for _, r in by[by["estimator"] == name].sort_values("f").iterrows():
            lines.append(f"{label} & {r['f']:g} & {int(r['n_binding'])} & {_sci(r['median_rel_err'])} & "
                         f"{_sci(r['max_rel_err'])} & {int(r['n_in_interval'])} \\\\")
    b = base[base["rel_delta"] == 0.10]
    with np.errstate(divide="ignore", invalid="ignore"):
        e = b["mu"] * b["b"] / np.abs(b["value"])
        err = (np.abs(b["mu"] - b["secant"]) / np.abs(b["secant"]))[e >= A.ZERO_ELASTICITY]
    med, mx = (float(err.median()), float(err.max())) if len(err) else (np.nan, np.nan)
    lines += [r"\hline", f"convex baseline dual vs.\\ secant & all & {len(err)} & {_sci(med)} & {_sci(mx)} & -- \\\\",
              r"\hline", r"\end{tabular}"]
    return _write("table2_i1", lines)


def table3_n2() -> Path:
    cv, m = _read("n2", "n2_convex"), _read("n2", "n2_miqp")
    dd = A.n2_disagreements(m)
    dd = dd[~dd["undefined"].astype(bool)]
    yn = lambda t: "yes" if t else "no"
    lab = {"GUROBI_BARRIER": "Gurobi barrier", "CLARABEL": "Clarabel", "SCS": "SCS", "ECOS": "ECOS"}
    lines = [r"\begin{tabular}{lrrrr}", r"\hline",
             r"convex solver (normalized, scaled) & $|\Delta A^*|/A^*$ & $\|\Delta w\|_1/\|w\|_1$ & dual err. & solved \\",
             r"\hline"]
    for (sol, nz, sc), g in cv[cv["solver"] != "reference"].groupby(["solver", "normalize", "scaled"], sort=True):
        lines.append(f"{lab.get(sol, sol)} ({yn(nz)}, {yn(sc)}) & {_sci(g['A_rel_err'].max())} & "
                     f"{_sci(g['w_l1_rel_err'].max())} & {_sci(g['max_binding_dual_rel_err'].max())} & "
                     f"{int(g['ok'].sum())}/{len(g)} \\\\")
    lines += [r"\hline",
              r"MIQP arm, $s_{\mathrm{obj}}$ & median $(B_{\mathrm{eff}}-V)/|V|$ & max cone effect & beats other bound & beyond gap \\",
              r"\hline"]
    alab = {a: l for a, l, _, _, _ in ARM_STYLE}
    for (arm, s), g in m.groupby(["arm", "s_obj"], sort=True):
        inv = dd[(dd["s_obj"] == s) & ((dd["arm_i"] == arm) | (dd["arm_j"] == arm))]
        cone = "--" if arm == "bigm" else _sci(g["cone_effect_rel"].max())
        lines.append(f"{alab.get(arm, arm)}, {s:g} & {_sci(g['gap_eff'].median())} & {cone} & "
                     f"{int(inv['incumbent_beats_other_bound'].sum())} & {int(inv['beyond_claimed_gap'].sum())} \\\\")
    lines += [r"\hline", r"\end{tabular}"]
    return _write("table3_n2", lines)


FIGURES = [("fig4_value_functions", fig4_value_functions), ("fig5_formulations", fig5_formulations),
           ("table2_i1", table2_i1), ("table3_n2", table3_n2)]
