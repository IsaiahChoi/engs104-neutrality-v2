"""proposal/FACTS.md: facts Isaiah may use in the proposal, one per line, each with its source file
and that file's sha256 (RUNBOOK §4, S2 step 5). Generated, never hand-typed (CLAUDE.md rule 8):
`uv run python tools/make_facts.py` reads the newest finished pilot, pilot_s2b and C1–C3 runs. While
C2 or C3 has no finished run the file is marked PRELIMINARY and those sections are listed as pending.
Decision 32 (PROGRESS, 2026-10-19): the S2 pilot's P1–P3 and P5 stand; its P4 and P6 are superseded
by the S2b run and its P7 is replaced by the projection computed here, so none of them is cited.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.common import latest_done  # noqa: E402
from src.opt.attribution import FAMILY_ORDER as ATTRIBUTION_FAMILIES  # noqa: E402
from src.utils import ROOT  # noqa: E402

OUT = ROOT / "proposal" / "FACTS.md"
CONFIGS = ROOT / "experiments" / "configs"
P4_ARMS = ["bigm", "perspective", "perspective_rescaled"]
IDENTITY_RTOL = 1e-9     # Σ family losses vs α'w_α − α'w*, relative (K18 pre-check: 9.1e-14)
REFS = ["lee2008risk", "ceria2012factor", "stubbs2010constraint", "clarke2002portfolio",
        "frangioni2006perspective", "gunluk2010perspective", "geoffrion1977parametric",
        "wolsey1981integer"]
FAMILIES = ["dollar", "beta", "style", "sector", "gross", "position", "liquidity"]
TIGHTEST = {"dollar": 0.0, "beta": 0.0, "style_all": 0.0, "sector": 0.0, "gross": 1.0,
            "position": 0.015, "liquidity": 0.025}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def g(x: float, n: int = 3) -> str:
    return f"{x:.{n}g}"


class Facts:
    def __init__(self):
        self.lines: list[str] = []

    def add(self, text: str, *sources: Path) -> None:
        src = "; ".join(f"`{rel(s)}` sha256 `{sha(s)}`" for s in sources)
        self.lines.append(f"- {text} — {src}")

    def head(self, text: str) -> None:
        self.lines += ["", f"## {text}", ""]


# ----- pure helpers (tests/test_make_facts.py) -----

def p4_arm_stats(solves: pd.DataFrame, agreement: pd.DataFrame) -> dict:
    """Per P4 arm, recomputed from the stored V and B: (B − V)/|V| against the arm's own polished
    V, the shortfall (V_best − V)/|V_best| against the best polished V of the arms at the same
    instance, the cone effect /|V|, the median Work, and agreement with big-M (the reference)."""
    s = solves.copy()
    s["V_best"] = s.groupby("key")["V"].transform("max")
    s["gap"] = (s["B"] - s["V"]) / s["V"].abs()
    s["short"] = (s["V_best"] - s["V"]) / s["V_best"].abs()
    out = {}
    for arm in P4_ARMS:
        x, a = s[s["arm"] == arm], agreement[agreement["arm"] == arm]
        ref = arm == "bigm"
        out[arm] = {"n": len(x), "max_gap_exact_rel": float(x["gap"].max()),
                    "max_shortfall_rel": float(x["short"].max()),
                    "max_cone_rel": float(x["cone_effect_rel"].max()),
                    "median_work": float(x["work"].median()),
                    "n_agree": None if ref else len(a),
                    "n_agree_pass": None if ref else int(a["pass"].sum()),
                    "worst_ratio": None if ref else float(a["ratio"].max())}
    return out


def p6_candidate_rows(intervals: pd.DataFrame, points: pd.DataFrame) -> list[dict]:
    """Per P6 candidate in rank order: the combined certified interval and who supplied V and B
    at b + δ and b − δ, with the number of its two points where V was an exact tie."""
    rows = []
    for r in intervals.sort_values("rank").itertuples():
        p = points[(points["candidate"] == r.candidate) & (points["b"] == r.b)]
        rows.append({"label": f"{r.candidate}@{r.b:g}", "rank": int(r.rank), "L": r.L, "H": r.H,
                     "s": r.s, "binding": bool(r.binding), "v_plus": r.v_from_plus,
                     "v_minus": r.v_from_minus, "b_plus": r.b_from_plus, "b_minus": r.b_from_minus,
                     "n_v_tie": int(p["v_tie"].sum())})
    return rows


def attribution_shares(attr: pd.DataFrame, points: pd.DataFrame, alpha: str = "mom",
                       rtol: float = IDENTITY_RTOL) -> pd.DataFrame:
    """Each attribution family's loss as a share of the attribution total at the base points of
    `alpha`: median, min, max and n over dates. The total is attribution.py's identity,
    α'w_α − α'w* (alpha_ideal − alpha_total), summed over FAMILY_ORDER (including `inactive`);
    raises ValueError if the stored losses do not add up to it within rtol."""
    pts = points[(points["alpha"] == alpha) & points["is_base"]].set_index("date")
    total = pts["alpha_ideal"] - pts["alpha_total"]
    loss = attr[attr["alpha"] == alpha].pivot_table(index="date", columns="family", values="loss",
                                                     aggfunc="sum")
    fam = loss.reindex(index=total.index, columns=ATTRIBUTION_FAMILIES)
    err = ((fam.sum(axis=1) - total) / total.abs()).abs()
    if not (err <= rtol).all():
        raise ValueError(f"attribution identity fails: max relative error {err.max():.3g} > {rtol}")
    share = fam.div(total, axis=0)
    out = pd.DataFrame({"median": share.median(), "min": share.min(), "max": share.max(),
                        "n": share.count()})
    out.attrs["max_abs_share_sum_minus_1"] = float((share.sum(axis=1) - 1).abs().max())
    out.attrs["max_abs_residual_share"] = (
        float((loss.reindex(total.index)["residual"] / total).abs().max())
        if "residual" in loss else np.nan)
    out.attrs["max_identity_rel_err"] = float(err.max())
    return out


def p7_projection(rate: float, W_star: float, workers: int, work_integer: pd.Series,
                  work_numerics: pd.Series, integer_cfg: dict, numerics_cfg: dict) -> pd.DataFrame:
    """S3 run-time arithmetic (no solves). Solve counts follow DESIGN §7 and the proposed configs:
    I1 = dates × f × (2 per constraint + 1 at b) points plus f × 2 per constraint at the
    robustness date; I2 = instances × points; under combined certification each point is one
    solve per formulation. N1 = (dates × N × f × tightness + the presolve-off instances at one N)
    × arms; N2(a) = dates × f × objective scales × arms. Expected Work per solve is the median of
    the given Work, each capped at its WorkLimit; the worst case puts every solve at its limit.
    Hours = solves × Work / rate / workers / 3600."""
    i1, i2 = integer_cfg["i1"], integer_cfg["i2"]
    n1, n2 = numerics_cfg["n1"], numerics_cfg["n2"]["miqp"]
    per_int = len(i1["formulations"]) if i1.get("certification") == "combined" else 1
    per_i2 = len(i1["formulations"]) if i2.get("certification") == "combined" else 1
    cap_int = i1.get("settings", {}).get("work_limit_factor", 2.0) * W_star
    cap_num = n1.get("settings", {}).get("work_limit_factor", 1.0) * W_star
    w_int = float(work_integer.clip(upper=cap_int).median())
    w_num = float(work_numerics.clip(upper=cap_num).median())
    nc, nd, nf = len(i1["constraints"]), len(i1["dates"]), len(i1["f"])
    i1_pts = nd * nf * (2 * nc + 1) + (nf * 2 * nc if i1.get("robustness") else 0)
    i2_pts = len(i2["instances"]) * int(i2["points"])
    grid = len(n1["dates"]) * len(n1["f"]) * len(n1["tightness"])
    n1_inst = grid * len(n1["N"]) + (grid if n1.get("presolve_off") else 0)
    n2_inst = len(n1["dates"]) * len(n1["f"]) * len(n2["s_obj"])
    exps = [("I1", i1_pts, i1_pts * per_int, w_int, cap_int),
            ("I2", i2_pts, i2_pts * per_i2, w_int, cap_int),
            ("N1", n1_inst, n1_inst * len(n1["formulations"]), w_num, cap_num),
            ("N2a", n2_inst, n2_inst * len(n2["formulations"]), w_num, cap_num)]
    return pd.DataFrame([{"experiment": e, "n_points": p, "n_miqp_solves": n,
                          "work_per_solve_expected": w, "work_limit_per_solve": c,
                          "work_expected": n * w, "work_worst": n * c,
                          "hours_expected": n * w / rate / workers / 3600,
                          "hours_worst": n * c / rate / workers / 3600, "workers": workers}
                         for e, p, n, w, c in exps])


def _latest(name: str, status: str = "ok") -> Path | None:
    try:
        return latest_done(name, status=status)
    except FileNotFoundError:
        return None


def data_facts(F: Facts) -> None:
    F.head("Data and universe")
    rep = ROOT / "results" / "data_report.md"
    m = re.search(r"Sample: (\S+) to (\S+), (\d+) trading days, (\d+) tickers", rep.read_text())
    F.add(f"Daily panel {m[1]} to {m[2]}: {m[3]} trading days, {m[4]} tickers (current S&P 500 "
          "constituents; survivorship to be disclosed)", rep)
    load = ROOT / "data" / "processed" / "risk" / "w252_loadings.parquet"
    dates = pd.to_datetime(pd.read_parquet(load, columns=["date"])["date"]).drop_duplicates().sort_values()
    F.add(f"Risk model: {len(dates)} month-ends, {dates.iloc[0]:%Y-%m} to {dates.iloc[-1]:%Y-%m}, six "
          "factors (FF5 + momentum), trailing 252-day window", load)
    cont = ROOT / "experiments" / "configs" / "continuous.yaml"
    F.add("D12 rebalance months: " + ", ".join(yaml.safe_load(cont.read_text())["d12"]), cont)


def universe_facts(F: Facts, c1: Path, c3: Path | None) -> None:
    src = (c3 / "c3_points.parquet") if c3 else (c1 / "c1_points.parquet")
    pts = pd.read_parquet(src)
    what = "all C3 month-ends" if c3 else "the D12 dates (C1)"
    F.add(f"Eligible universe size over {what}: {int(pts['N'].min())} to {int(pts['N'].max())} names", src)


def pilot_facts(F: Facts, pilot: Path, s2b: Path) -> None:
    """S2 pilot: P1–P3 and P5 (they stand, Decision 32). S2b: P4 and P6. P7: the projection."""
    F.head("Design pilot (DESIGN §8)")
    s = pilot / "summary.json"
    S = json.loads(s.read_text())
    p4s = s2b / "p4_solves.parquet"
    p1 = S["P1"]
    F.add(f"P1: the root-found QP and the Clarabel QCQP agree on A* to {g(p1['max_A_rel'], 2)} "
          f"(relative), λ* to {g(p1['max_lam_rel'], 2)}, binding duals to "
          f"{g(p1['max_binding_dual_rel'], 2)} at all {p1['n_dates']} D12 dates; "
          f"{int(p1['root_solves']['q0'])}–{int(p1['root_solves']['q100'])} QP solves per root-find", s)
    sv = pd.read_parquet(p4s)["scaled_abs_V"]
    F.add(f"P-MI objective scale s_obj = {g(p1['s_obj']['s_obj'])} (|U*|·s_obj in [1, 100]; S2b P4 "
          f"values |V|·s_obj {g(sv.min())}–{g(sv.max())})", s, p4s)
    F.add(f"P2: the 3%/yr risk budget binds at {S['P2']['n'] - S['P2']['n_not_binding']} of "
          f"{S['P2']['n']} base solves (D12 × three alphas); slack at "
          + ", ".join(f"{e['date'][:7]} ({e['alpha']})" for e in S["P2"]["exceptions"]), s)
    p3 = pilot / "p3.parquet"
    for _, r in pd.read_parquet(p3).iterrows():
        F.add(f"P3: {r['month']}, N = {r['n_label']} ({r['N']} names): continuous support S = {r['S']}; "
              f"K = round(f·S) = {r['K_f0.25']}/{r['K_f0.5']}/{r['K_f0.75']} for f = 0.25/0.5/0.75", p3)
    s2b_p4_facts(F, s2b)
    p5 = S["P5"]
    F.add(f"P5: Gurobi {p5['gurobi_version']}; WorkLimit confirmed; W* = {g(p5['W_star'])} Work units "
          f"(300 s at {g(p5['work_per_second_median'])} Work/s, 4 concurrent solves)", s)
    s2b_p6_facts(F, s2b)
    p7_fact(F, s, s2b)


def _arm_text(arm: str, st: dict) -> str:
    agree = ("n/a (the reference arm)" if st["n_agree"] is None else
             f"{st['n_agree_pass']}/{st['n_agree']}, worst |ΔV|/allowed {g(st['worst_ratio'])}")
    cone = "n/a (no cones)" if np.isnan(st["max_cone_rel"]) else g(st["max_cone_rel"])
    return (f"P4, {arm}: agreement with big-M {agree}; max cone effect/|V| {cone}; max (B − V)/|V| "
            f"against its exact (polished) V {g(st['max_gap_exact_rel'])}; max shortfall "
            f"(V_best − V)/|V_best| against the best V of the three arms "
            f"{g(st['max_shortfall_rel'])}; median Work {g(st['median_work'])} ({st['n']} solves)")


def s2b_p4_facts(F: Facts, s2b: Path) -> None:
    """P4 from the S2b rerun (three arms at the 1e-9 polish, Decisions 24 and 27(a))."""
    s, meta = s2b / "summary.json", s2b / "run_meta.json"
    P4, c = json.loads(s.read_text())["P4"], json.loads(meta.read_text())["config"]["p4"]
    st = {a: P4["by_arm"][a]["statuses"] for a in P4_ARMS}
    viol = sum(P4["by_arm"][a]["n_violations_1e9"] for a in P4_ARMS)
    F.add(f"P4 (S2b rerun): {P4['n_instances']} instances (N = {c['N']}; {', '.join(c['dates'])}; "
          f"f = {', '.join(f'{x:g}' for x in c['f'])}; {', '.join(c['tightness'])}) × 3 arms (big-M, "
          f"perspective, perspective with weights rescaled by the largest position bound) at MIPGap "
          f"{c['mip_gap']:g}, WorkLimit {c['work_limit_factor']:g}·W*: statuses "
          + "; ".join(f"{a} {st[a]}" for a in P4_ARMS)
          + f"; polished V at FeasibilityTol = OptimalityTol = 1e-9; checker violations at 1e-9: {viol}",
          s, meta)
    sv, ag = s2b / "p4_solves.parquet", s2b / "p4_agreement.parquet"
    stats = p4_arm_stats(pd.read_parquet(sv), pd.read_parquet(ag))
    for arm in P4_ARMS:
        F.add(_arm_text(arm, stats[arm]), sv, ag)


def s2b_p6_facts(F: Facts, s2b: Path) -> None:
    """P6 from the S2b rerun: combined certification (Decision 27(b)), ties included (Decision 28)."""
    s, meta = s2b / "summary.json", s2b / "run_meta.json"
    P6, c = json.loads(s.read_text())["P6"], json.loads(meta.read_text())["config"]["p6"]
    F.add(f"P6 rule (S2b): candidates are the {c['n_families']} constraint keys with the largest median "
          "C1 α_mom elasticity at the I1 dates (position and liquidity excluded), every key tied at "
          f"the cutoff, and the Mom bound at {c['mom_bound']:g}; certified central differences at "
          f"{c['date']}, N = {c['N']}, f = {c['f']:g}, δ = {c['rel_delta']:g}·b, MIPGap {c['mip_gap']:g}, "
          f"WorkLimit {c['work_limit_factor']:g}·W* per formulation solve, under combined "
          "certification (big-M and perspective at default scaling: V = the larger polished value, "
          "B = the smaller final bound, B_eff = max(B, V) + 1e-6·|V|); keep L > 0 in candidate "
          f"order, at most {c['max_keep']}", meta)
    iv, pts = s2b / "p6_intervals.parquet", s2b / "p6_points.parquet"
    for r in p6_candidate_rows(pd.read_parquet(iv), pd.read_parquet(pts)):
        F.add(f"P6, {r['label']} (rank {r['rank']}): combined certified L = {g(r['L'])}, "
              f"H = {g(r['H'])}, s = {g(r['s'])}; {'binding (L > 0)' if r['binding'] else 'not binding (L ≤ 0)'}; V from {r['v_plus']} (b + δ) and {r['v_minus']} (b − δ); B from "
              f"{r['b_plus']} (b + δ) and {r['b_minus']} (b − δ); exact V ties {r['n_v_tie']} of 2",
              iv, pts)
    vf = ", ".join(f"{k} {v}" for k, v in P6["v_from"].items())
    bf = ", ".join(f"{k} {v}" for k, v in P6["b_from"].items())
    F.add(f"P6: the mechanical rule keeps {', '.join(P6['selected'])}; V supplied by {vf} and B by "
          f"{bf} of {sum(P6['v_from'].values())} points ({P6['n_v_tie']} exact V ties, broken to "
          f"big-M); solves {P6['statuses']}, checker violations at 1e-9: {P6['n_violations_1e9']}. "
          "This is not the I1 set: the final I1 set is decided at GATE DESIGN (Decision 31)", s)


def p7_fact(F: Facts, s2_summary: Path, s2b: Path) -> None:
    """P7 projection (Decision 32): S2's measured Work/s and W* (P5), S2b's Work per solve."""
    P5 = json.loads(s2_summary.read_text())["P5"]
    meta, p6s, p4s = s2b / "run_meta.json", s2b / "p6_solves.parquet", s2b / "p4_solves.parquet"
    icfg, ncfg = CONFIGS / "integer.yaml", CONFIGS / "numerics.yaml"
    cfg = json.loads(meta.read_text())["config"]
    workers, p6c = cfg["workers"], cfg["p6"]
    k6 = ", ".join(str(k) for k in sorted(pd.read_parquet(p6s)["K"].unique()))
    ic, nc = yaml.safe_load(icfg.read_text()), yaml.safe_load(ncfg.read_text())
    nf, na = len(ic["i1"]["formulations"]), len(nc["n1"]["formulations"])
    per = {"I1": f"points × {nf} formulations, combined", "I2": f"points × {nf} formulations, combined",
           "N1": f"instances incl. presolve-off, × {na} arms",
           "N2a": f"instance-scale pairs, × {len(nc['n2']['miqp']['formulations'])} arms"}
    rate = P5["work_per_second_median"]
    t = p7_projection(rate, P5["W_star"], workers, pd.read_parquet(p6s)["work"],
                      pd.read_parquet(p4s)["work"], ic, nc).set_index("experiment")
    names = {"I1": "I1", "I2": "I2", "N1": "N1", "N2a": "N2(a)"}
    F.add(f"P7 projection (arithmetic, no solves; replaces S2's P7): at {workers} workers and "
          f"{g(rate)} Work/s (S2 P5 median), expected / WorkLimit worst case, hours: " + "; ".join(
              f"{names[e]} {int(r.n_miqp_solves)} solves ({int(r.n_points)} {per[e]}; WorkLimit "
              f"{g(r.work_limit_per_solve)}) {g(r.hours_expected, 2)} / {g(r.hours_worst, 2)}"
              for e, r in t.iterrows())
          + f". Expected Work per solve: median of S2b's P6 solves ({p6c['date']}, K = {k6}, MIPGap "
          f"{p6c['mip_gap']:g}, both formulations) "
          f"{g(t.loc['I1', 'work_per_solve_expected'])} for I1/I2, of S2b's P4 solves (three arms, "
          f"MIPGap {cfg['p4']['mip_gap']:g}, N = {cfg['p4']['N']}) "
          f"{g(t.loc['N1', 'work_per_solve_expected'])} for N1/N2(a); N1's "
          f"other N use the N = {cfg['p4']['N']} Work; I1 counts the constraints in the proposed "
          "integer.yaml", s2_summary, p6s, p4s, icfg, ncfg)


def c1_facts(F: Facts, c1: Path) -> None:
    F.head("C1, base mandate (D12, full universe)")
    pf, idf = c1 / "c1_points.parquet", c1 / "c1_idealized.parquet"
    pts, ide = pd.read_parquet(pf), pd.read_parquet(idf)
    mom = pts[pts["alpha"] == "mom"]
    F.add(f"α_mom base A*: median {g(1e4 * mom['A'].median())} bp/month (range "
          f"{g(1e4 * mom['A'].min())}–{g(1e4 * mom['A'].max())}); retained fraction against the "
          f"unconstrained, costless P-RB: median {g(mom['retained'].median())} (range "
          f"{g(mom['retained'].min())}–{g(mom['retained'].max())})", pf)
    meds = {f: float(mom[f"e_{f}"].median()) for f in FAMILIES if f"e_{f}" in mom}
    top = sorted(meds, key=lambda f: -meds[f])
    F.add("α_mom median elasticity by family over D12: " + ", ".join(
        f"{f} {g(meds[f], 2)} (binds at {int((mom[f'e_{f}'] >= 1e-4).sum())}/{len(mom)})" for f in top), pf)
    af = c1 / "c1_attribution.parquet"
    sh = attribution_shares(pd.read_parquet(af), pts, alpha="mom")
    order = sh.sort_values("median", ascending=False).index
    F.add(f"α_mom at base over D12 ({int(sh['n'].max())} dates): each family's attributed loss as a "
          "share of the attribution total α'w_α − α'w* (attribution.py's identity, summed over its "
          "families including `inactive`; w_α the costless unconstrained mean-variance optimum at "
          "λ = μ_risk; not A*_unc − A*), median (range): " + ", ".join(
              f"{f} {g(sh.loc[f, 'median'], 2)} ({g(sh.loc[f, 'min'], 2)}–{g(sh.loc[f, 'max'], 2)})"
              for f in order)
          + f"; shares sum to 1 within {g(sh.attrs['max_abs_share_sum_minus_1'], 2)}; `residual` "
          f"share ≤ {g(sh.attrs['max_abs_residual_share'], 2)}", af, pf)
    for kind in ("mom", "perp", "par"):
        x = pts[pts["alpha"] == kind]["phi"]
        F.add(f"Alignment share φ for α_{kind} over D12: {g(x.min(), 2)} to {g(x.max(), 2)}", pf)
    fac = ide[ide["mandate"] == "factor"]
    nz = ide["A_cf"].abs() > 1e-12
    F.add(f"Idealized full factor neutrality: numerical retained fraction matches the closed form "
          f"√(1 − φ) to {g((fac['retained_num'] - fac['sqrt_1_minus_phi']).abs().max(), 2)} (absolute, "
          f"{len(fac)} solves); A* to {g((ide['A_num'] / ide['A_cf'] - 1)[nz].abs().max(), 2)} relative "
          f"where the closed form is nonzero ({int(nz.sum())} solves), and A* = 0 to "
          f"{g((ide['A_num'] - ide['A_cf'])[~nz].abs().max(), 2)} where it is 0 (α∥, {int((~nz).sum())} "
          "solves)", idf)
    slack = pts[~pts["risk_binding"]]
    F.add(f"Risk budget slack at base in C1: {len(slack)} of {len(pts)} solves ("
          + ", ".join(f"{d[:7]} {a}" for d, a in zip(slack["date"], slack["alpha"])) + ")", pf)


def c2_facts(F: Facts, c2: Path) -> None:
    F.head("C2, cost curves (D12, α_mom)")
    pf = c2 / "c2_points.parquet"
    pts = pd.read_parquet(pf)
    mom = pts[(pts["alpha"] == "mom") & ~pts["off"]]
    parts = []
    for fam, b in TIGHTEST.items():
        x = mom[(mom["family"] == fam) & (mom["value"] == b)]["retained_vs_off"]
        parts.append(f"{fam} at {b:g}: {g(x.median())} ({g(x.min())}–{g(x.max())})")
    F.add("A*(b)/A*(off) at the tightest grid point, median (range) over D12: " + "; ".join(parts), pf)
    sl = pts[~pts["risk_binding"]]
    F.add(f"C2: {len(pts)} points; risk budget slack at {len(sl)} ("
          + ", ".join(f"{k} {v}" for k, v in sl["alpha"].value_counts().sort_index().items())
          + "; families " + ", ".join(sorted(sl["family"].unique())) + ")", pf)


def c3_facts(F: Facts, c3: Path) -> None:
    F.head("C3, time series (base, α_mom)")
    pf = c3 / "c3_points.parquet"
    pts = pd.read_parquet(pf)
    F.add(f"C3: {len(pts)} month-ends ({pts['date'].min()[:7]} to {pts['date'].max()[:7]}); A* median "
          f"{g(1e4 * pts['A'].median())} bp/month (range {g(1e4 * pts['A'].min())}–"
          f"{g(1e4 * pts['A'].max())}); φ {g(pts['phi'].min(), 2)} to {g(pts['phi'].max(), 2)}", pf)
    sk = c3 / "c3_skipped.parquet"
    if sk.exists() and len(pd.read_parquet(sk)):
        F.add("C3 month-ends without α_mom (252-day lookback): "
              + ", ".join(pd.read_parquet(sk)["date"]), sk)


def software_facts(F: Facts, run: Path) -> None:
    F.head("Software and tests")
    meta = run / "run_meta.json"
    p = json.loads(meta.read_text())["provenance"]
    F.add(f"Python {p['python']}; gurobipy {p['gurobipy']}; Clarabel {p['clarabel']}; CVXPY "
          f"{p['cvxpy']}; NumPy {p['numpy']}; SciPy {p['scipy']}; pandas {p['pandas']}", meta)
    logs = sorted((ROOT / "logs").glob("make_c*.log"), key=lambda f: f.stat().st_mtime)
    m = re.search(r"(\d+) passed(?:, (\d+) xfailed)?", logs[-1].read_text())
    F.add(f"Test suite before the newest C run: {m[1]} passed, {m[2] or 0} strict expected "
          "failures", logs[-1])


def refs(F: Facts) -> None:
    F.head("References (copied exactly from report/refs.bib)")
    bib = ROOT / "report" / "refs.bib"
    text = bib.read_text()
    F.lines += [f"Source: `{rel(bib)}` sha256 `{sha(bib)}`", "", "```bibtex"]
    for key in REFS:
        m = re.search(r"(% verified:[^\n]*\n@\w+\{" + key + r",.*?\n\})", text, re.S)
        F.lines += [m[1], ""]
    F.lines.append("```")


def build(out: Path = OUT) -> list[str]:
    """Write FACTS to `out` from the newest finished runs; return its lines."""
    pilot, s2b = _latest("pilot", "pilot"), _latest("pilot_s2b", "pilot")
    c1, c2, c3 = _latest("c1"), _latest("c2"), _latest("c3")
    if pilot is None or s2b is None or c1 is None:
        raise SystemExit("FACTS needs a finished pilot, pilot_s2b and C1 run")
    prelim = c2 is None or c3 is None
    F = Facts()
    F.lines += ["# FACTS for the proposal" + (" — PRELIMINARY (C2/C3 not finished)" if prelim else ""),
                "", "Generated by `tools/make_facts.py`; do not edit. One fact per line, with its "
                "source file and sha256. Numbers come from v2 runs only. Runs: "
                + ", ".join(f"`{rel(r)}`" for r in (pilot, s2b, c1, c2, c3) if r is not None) + ". "
                f"Decision 32: from `{rel(pilot)}` only P1–P3 and P5 are used; P4 and P6 come from "
                f"`{rel(s2b)}`, and P7 is a projection computed here."]
    data_facts(F)
    universe_facts(F, c1, c3)
    pilot_facts(F, pilot, s2b)
    c1_facts(F, c1)
    if c2 is not None:
        c2_facts(F, c2)
    else:
        F.head("C2, cost curves — pending")
    if c3 is not None:
        c3_facts(F, c3)
    else:
        F.head("C3, time series — pending")
    software_facts(F, c1)
    refs(F)
    Path(out).write_text("\n".join(F.lines) + "\n")
    return F.lines


def main() -> int:
    lines = build(OUT)
    kind = "preliminary" if "PRELIMINARY" in lines[0] else "final"
    print(f"wrote {rel(OUT)} ({kind}, {len(lines)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
