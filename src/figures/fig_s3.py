"""Figs. 4–5 and Tables II–III (DESIGN §10), from the newest finished I1, I2, N1 and N2 runs.

Same print rules as src/figures/fig_c.py: one IEEE column, text ≥ 8 pt, vector PDF with
deterministic metadata plus a 300-dpi PNG; identity never by color alone (line style, marker).
DESIGN §10 as amended at GATE I (edits 2–4) and the S4 addendum's item 4:
- Fig. 4 (I2), two-column width, the slope row only (DESIGN §10 as edited at the S4 read; the
  value functions are described in the text), about half the S4 height and within the text
  width so 8-pt text prints at 8 pt: one panel per instance with the secant slope of V between
  neighbouring grid points (the secants beside a grid point where nonconcavity is certified,
  results/s3b_analysis/item4_i2_triples.csv, drawn as hollow diamonds), the baseline's dual, and
  at 0.5·b, b, 1.5·b the three estimators beside the certified secant s with its interval [L, H].
- Fig. 5 (N1), one panel (DESIGN §10 as edited at the S4 read; Work medians are in the text): root
  gap (root bound − best known value)/|best known value| against tightness for the three arms at
  default presolve, one marker per instance, median connected;
  the default-scaling perspective is labelled solver behaviour (Decision 37). Thin gray lines
  mark the median plain-relaxation gaps of big-M and the perspective per tightness. Solves that
  stopped at the WorkLimit are hollow, with a legend entry only if any is drawn. Root gaps
  ≤ 1e-6 are drawn at 1e-6 (log axis); their count is printed.
- Table II (I1), δ = 10%, one column (S4b): each estimator's relative error |μ̂ − s|/|s| over
  binding cases with n, by f (K = round(f·S) differs by date), how many lie in [L, H], and the median relative
  interval width (H − L)/s of the row's cases; the convex baseline's dual-versus-secant error
  at δ = 10% beneath. report/tables/table2_i1.tex.
- Table III (N2): (b) convex solver variants against the reference (max over the dates);
  (a) MIQP arms at each s_obj: the median certified gap (B_eff-based, so floored at 1e-6), the
  largest cone effect, and how often the arm's V lies above another arm's B_eff, or its B_eff
  below another arm's V (no disagreement beyond the larger claimed gap is counted in the
  analysis, n2_pairs). report/tables/table3_n2.tex.
Tables are bare tabular environments; captions are in report/main.tex.
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
GRAY5 = "#8c8b87"


def _read(name: str, table: str) -> pd.DataFrame:
    return pd.read_parquet(latest_done(name) / f"{table}.parquet")


TRIPLES = ROOT / "results" / "s3b_analysis" / "item4_i2_triples.csv"
EST_MARK = {"bigm_relax": "v", "perspective": "s", "fixed": "D"}
TABLE2_LABEL = {"bigm_relax": "big-M dual", "perspective": "perspective", "fixed": "fixed-integer"}   # one column (S4b)
TEXT_WIDTH_IN = 7.0              # IEEE two-column text width is 7.16 in (DESIGN §10: Fig. 4 may span it)


def grid_secants(pts: pd.DataFrame, triples: pd.DataFrame) -> pd.DataFrame:
    """Per instance, the secant slope (V(b_{k+1}) − V(b_k))/(b_{k+1} − b_k) at each midpoint,
    flagged when either end is a grid point b_k whose triple is certified nonconcave
    (V(b_{k−1}) + V(b_{k+1}) > 2·B_eff(b_k); S3b item 4)."""
    out = []
    for inst, g in pts.sort_values("bound").groupby("instance", sort=True):
        b, v = g["bound"].to_numpy(float), g["V"].to_numpy(float)
        cert = set(np.round(triples.loc[(triples["instance"] == inst) & triples["certified"].astype(bool),
                                        "bound"].to_numpy(float), 12))
        for k in range(len(b) - 1):
            out.append({"instance": inst, "mid": (b[k] + b[k + 1]) / 2,
                        "slope": (v[k + 1] - v[k]) / (b[k + 1] - b[k]),
                        "beside_certified": bool({round(b[k], 12), round(b[k + 1], 12)} & cert)})
    return pd.DataFrame(out)


def fig4_value_functions() -> Path:
    _apply()
    pts = _read("i2", "i2_points").sort_values("bound")
    base = _read("i2", "i2_baseline").sort_values("bound")
    ivs = _read("i2", "i2_intervals")
    sec = grid_secants(pts, pd.read_csv(TRIPLES))
    insts = sorted(pts["instance"].unique())
    fig, axes = plt.subplots(1, len(insts), figsize=(TEXT_WIDTH_IN, 2.3), sharey=True)
    axes = np.atleast_1d(axes)
    for j, inst in enumerate(insts):
        low = axes[j]
        g, gb = pts[pts["instance"] == inst], base[base["instance"] == inst]
        date, rest = inst.split("_N")
        low.set_title(f"{date}, N = {rest.split('_')[0]}, K = {inst.split('_K')[1]}", loc="left")
        s = sec[sec["instance"] == inst]
        plain, mark = s[~s["beside_certified"]], s[s["beside_certified"]]
        low.plot(s["mid"], 1e4 * s["slope"], color=style.SERIES[0], lw=0.6, alpha=0.6)
        low.plot(plain["mid"], 1e4 * plain["slope"], ls="none", marker="o", ms=2, color=style.SERIES[0],
                 label="grid secant of $V$")
        low.plot(mark["mid"], 1e4 * mark["slope"], ls="none", marker="D", ms=3.5, mfc="none",
                 color=style.SERIES[0], label="grid secant beside certified nonconcavity")
        gbb = gb[gb["bound"] > 0]
        low.plot(gbb["bound"], 1e4 * gbb["mu"], color=style.INK_SECONDARY, ls="--", lw=0.8,
                 label="baseline dual")
        e = g[g["estimator"].astype(bool)]
        for k, (name, col, label, _, slot) in enumerate(EST_STYLE):
            off = (k - 1) * 0.0004
            low.plot(e["bound"] + off, 1e4 * e[col], ls="none", marker=EST_MARK[name], ms=4,
                     color=style.SERIES[slot], label=label)
        iv = ivs[ivs["instance"] == inst]
        low.errorbar(iv["e"] + 0.0008, 1e4 * iv["s"], yerr=[1e4 * (iv["s"] - iv["L"]), 1e4 * (iv["H"] - iv["s"])],
                     ls="none", marker="_", ms=7, mew=1.2, color=style.INK, capsize=2,
                     label="certified secant $s$ with $[L, H]$")
        low.set_xlabel(f"bound $b$ on {pts['key'].iloc[0]} (net weight)")
    axes[0].set_ylabel("slope of P-MI objective\n(bp/month per unit $b$)")
    seen = {}
    for ax in axes.flat:
        for hh, ll in zip(*ax.get_legend_handles_labels()):
            seen.setdefault(ll, hh)
    fig.tight_layout(rect=(0, 0, 1, 0.72))
    fig.legend(list(seen.values()), list(seen.keys()), loc="upper center", ncol=3,
               bbox_to_anchor=(0.5, 1.0), columnspacing=0.8, handletextpad=0.4)
    return _save(fig, "fig4_value_functions")


def plain_gap_medians(rg: pd.DataFrame) -> dict[str, list[float]]:
    """Median plain-relaxation gap per tightness (loose, base, tight), big-M and perspective."""
    return {arm: [float(rg.loc[rg["tightness"] == t, f"{arm}_gap"].median()) for t in TIGHT]
            for arm in ("bigm", "perspective")}


def fig5_labels(n_censored_plotted: int) -> list[str]:
    """Fig. 5's legend entries; the hollow-marker entry only if a censored solve is drawn."""
    labels = [ARM_LABEL5[a] for a, *_ in ARM_STYLE] + [
        "plain relaxation, big-M (median)", "plain relaxation, perspective (median)"]
    if n_censored_plotted:
        labels.append("hollow: stopped at the WorkLimit")
    return labels


ARM_LABEL5 = {"bigm": "big-M", "perspective": "perspective, default scaling (solver behaviour)",
              "perspective_rescaled": "perspective, rescaled"}
REF_STYLE = {"bigm": ":", "perspective": (0, (6, 2))}


def fig5_formulations() -> Path:
    _apply()
    solves = _read("n1", "n1_solves")
    tab = A.n1_table(solves)
    tab = tab[tab["presolve"] == -1]
    rg = A.relax_gaps(_read("n1", "n1_relax"), solves)
    ref = plain_gap_medians(rg)
    labels = fig5_labels(int(tab["censored"].sum()))
    fig, ax = plt.subplots(figsize=(style.COLUMN_WIDTH_IN, 2.75))
    x0 = {t: i for i, t in enumerate(TIGHT)}
    clipped = 0
    for k, (arm, label, mk, ls, slot) in enumerate(ARM_STYLE):
        g = tab[tab["arm"] == arm]
        off = (k - 1) * 0.18
        y = g["root_gap"].astype(float).to_numpy()
        clipped += int((y <= GAP_FLOOR).sum())
        y = np.maximum(y, GAP_FLOOR)
        xs = g["tightness"].map(x0).to_numpy() + off
        cen = g["censored"].to_numpy(bool)
        ax.plot(xs[~cen], y[~cen], ls="none", marker=mk, ms=3, color=style.SERIES[slot], alpha=0.8)
        ax.plot(xs[cen], y[cen], ls="none", marker=mk, ms=4, mfc="none", color=style.SERIES[slot])
        med = [float(np.median(y[g["tightness"].to_numpy() == t])) for t in TIGHT]
        ax.plot(np.arange(3) + off, med, ls=ls, marker=mk, ms=3, color=style.SERIES[slot], lw=1.0,
                label=ARM_LABEL5[arm])
    for arm, lab in (("bigm", labels[3]), ("perspective", labels[4])):
        ax.plot(np.arange(3), np.maximum(ref[arm], GAP_FLOOR), ls=REF_STYLE[arm], lw=0.6,
                color=GRAY5, label=lab)
    ax.set_yscale("log")
    ax.set_ylabel("root gap")
    ax.set_xticks(range(3), TIGHT)
    ax.set_xlabel("mandate tightness (style and beta bounds)")
    if len(labels) > 5:
        ax.plot([], [], ls="none", marker="o", mfc="none", color=style.INK_SECONDARY, label=labels[5])
    fig.tight_layout(rect=(0, 0, 1, 0.70))
    fig.legend(loc="upper center", ncol=1, bbox_to_anchor=(0.5, 1.0), handletextpad=0.4)
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


def table2_lines() -> list[str]:
    est, base = _read("i1", "i1_estimators"), _read("i1", "i1_baseline")
    long = A.i1_long(est[est["rel_delta"] == 0.10])
    by = A.error_summary(long, by=["f"])
    bl = long[long["binding"].astype(bool)].assign(width=lambda d: (d["H"] - d["L"]) / d["s"])
    lines = [r"\begin{tabular}{@{}p{1.3cm}@{\hspace{3pt}}l@{\hspace{4pt}}r@{\hspace{4pt}}r@{\hspace{4pt}}r@{\hspace{4pt}}r@{\hspace{4pt}}r@{}}",
             r"\hline",
             r"estimator & $f$ & $n$ & median & max & in $[L,H]$ & med.\ $(H-L)/s$ \\", r"\hline"]
    for name, _, _, _, _ in EST_STYLE:
        label = TABLE2_LABEL[name]
        for _, r in by[by["estimator"] == name].sort_values("f").iterrows():
            w = bl.loc[(bl["estimator"] == name) & (bl["f"] == r["f"]), "width"]
            lines.append(f"{label} & {r['f']:g} & {int(r['n_binding'])} & {_sci(r['median_rel_err'])} & "
                         f"{_sci(r['max_rel_err'])} & {int(r['n_in_interval'])} & {_sci(float(w.median()))} \\\\")
    b = base[base["rel_delta"] == 0.10]
    with np.errstate(divide="ignore", invalid="ignore"):
        e = b["mu"] * b["b"] / np.abs(b["value"])
        err = (np.abs(b["mu"] - b["secant"]) / np.abs(b["secant"]))[e >= A.ZERO_ELASTICITY]
    med, mx = (float(err.median()), float(err.max())) if len(err) else (np.nan, np.nan)
    lines += [r"\hline", f"convex baseline & all & {len(err)} & {_sci(med)} & {_sci(mx)} & -- & -- \\\\",
              r"\hline", r"\end{tabular}"]
    return lines


def table2_i1() -> Path:
    return _write("table2_i1", table2_lines())


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
              r"MIQP arm, $s_{\mathrm{obj}}$ & median $(B_{\mathrm{eff}}-V)/|V|$\textsuperscript{a} & max cone effect & $V$ above other $B_{\mathrm{eff}}$ & $B_{\mathrm{eff}}$ below other $V$ \\",
              r"\hline"]
    alab = {a: l for a, l, _, _, _ in ARM_STYLE}
    for (arm, s), g in m.groupby(["arm", "s_obj"], sort=True):
        ds = dd[dd["s_obj"] == s]
        above = int(ds.loc[ds["arm_i"] == arm, "i_beats_j"].sum() + ds.loc[ds["arm_j"] == arm, "j_beats_i"].sum())
        below = int(ds.loc[ds["arm_j"] == arm, "i_beats_j"].sum() + ds.loc[ds["arm_i"] == arm, "j_beats_i"].sum())
        cone = "--" if arm == "bigm" else _sci(g["cone_effect_rel"].max())
        lines.append(f"{alab.get(arm, arm)}, {s:g} & {_sci(g['gap_eff'].median())} & {cone} & {above} & {below} \\\\")
    lines += [r"\hline",
              r"\multicolumn{5}{l}{\textsuperscript{a}$B_{\mathrm{eff}}=\max(B,V)+10^{-6}|V|$-based, so floored at $10^{-6}$.} \\",
              r"\end{tabular}"]
    return _write("table3_n2", lines)


FIGURES = [("fig4_value_functions", fig4_value_functions), ("fig5_formulations", fig5_formulations),
           ("table2_i1", table2_i1), ("table3_n2", table3_n2)]
