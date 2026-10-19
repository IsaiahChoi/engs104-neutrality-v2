"""proposal/FACTS.md: facts Isaiah may use in the proposal, one per line, each with its source file
and that file's sha256 (RUNBOOK §4, S2 step 5). Generated, never hand-typed (CLAUDE.md rule 8):
`uv run python tools/make_facts.py` reads the newest finished pilot and C1–C3 runs. While C2 or C3
has no finished run the file is marked PRELIMINARY and those sections are listed as pending.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.common import latest_done  # noqa: E402
from src.utils import ROOT  # noqa: E402

OUT = ROOT / "proposal" / "FACTS.md"
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


def pilot_facts(F: Facts, pilot: Path) -> None:
    F.head("Design pilot (DESIGN §8)")
    s = pilot / "summary.json"
    S = json.loads(s.read_text())
    p1 = S["P1"]
    F.add(f"P1: the root-found QP and the Clarabel QCQP agree on A* to {g(p1['max_A_rel'], 2)} "
          f"(relative), λ* to {g(p1['max_lam_rel'], 2)}, binding duals to "
          f"{g(p1['max_binding_dual_rel'], 2)} at all {p1['n_dates']} D12 dates; "
          f"{int(p1['root_solves']['q0'])}–{int(p1['root_solves']['q100'])} QP solves per root-find", s)
    F.add(f"P-MI objective scale s_obj = {g(p1['s_obj']['s_obj'])} (|U*|·s_obj in [1, 100]; P4 values "
          f"{g(S['P4']['scaled_abs_V']['q0'])}–{g(S['P4']['scaled_abs_V']['q100'])})", s)
    F.add(f"P2: the 3%/yr risk budget binds at {S['P2']['n'] - S['P2']['n_not_binding']} of "
          f"{S['P2']['n']} base solves (D12 × three alphas); slack at "
          + ", ".join(f"{e['date'][:7]} ({e['alpha']})" for e in S["P2"]["exceptions"]), s)
    p3 = pilot / "p3.parquet"
    for _, r in pd.read_parquet(p3).iterrows():
        F.add(f"P3: {r['month']}, N = {r['n_label']} ({r['N']} names): continuous support S = {r['S']}; "
              f"K = round(f·S) = {r['K_f0.25']}/{r['K_f0.5']}/{r['K_f0.75']} for f = 0.25/0.5/0.75", p3)
    p4 = S["P4"]
    F.add(f"P4: big-M and perspective agree within the larger certified gap at {p4['n_pass']} of "
          f"{p4['n_instances']} instances (N = 250, MIPGap 1e-4); all {sum(p4['statuses'].values())} "
          "solves optimal", s)
    a9 = p4["A9"]["cone_effect_rel_perspective"]
    F.add(f"P4 (A9): the perspective cones' violation within Gurobi's tolerance moves the raw objective "
          f"by up to {g(a9['q100'], 2)}·|V| (median {g(a9['q50'], 2)}), above MIPGap 1e-4", s)
    p5 = S["P5"]
    F.add(f"P5: Gurobi {p5['gurobi_version']}; WorkLimit confirmed; W* = {g(p5['W_star'])} Work units "
          f"(300 s at {g(p5['work_per_second_median'])} Work/s, 4 concurrent solves)", s)
    F.add("P6 rule: candidates are the 4 constraint keys with the largest median C1 elasticity at the "
          "I1 dates (position and liquidity excluded) plus the Mom bound at 0.025; keep certified "
          "L > 0 (2017-12, N = 250, f = 0.5, δ = 10%), at most 4, a factor bound included", s)
    sel = S["P6"]["selected"]
    kept = [r for r in sorted(S["P6"]["intervals"], key=lambda r: r["rank"])
            if r["binding"] and r["candidate"] in sel]
    F.add("P6 proposed I1 constraints: " + "; ".join(
        f"{r['candidate']} at b = {r['b']:g} (certified L = {g(r['L'])})" for r in kept), s)
    p7 = pilot / "p7.parquet"
    t = pd.read_parquet(p7)
    F.add("P7 projection at 4 workers (expected / WorkLimit worst case, hours): " + "; ".join(
        f"{r.experiment} {g(r.hours_expected_at_workers, 2)} / {g(r.hours_worst_at_workers, 2)}"
        for r in t.itertuples()), p7)


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


def main() -> int:
    pilot = _latest("pilot", "pilot")
    c1, c2, c3 = _latest("c1"), _latest("c2"), _latest("c3")
    if pilot is None or c1 is None:
        raise SystemExit("FACTS needs a finished pilot and C1 run")
    prelim = c2 is None or c3 is None
    F = Facts()
    F.lines += ["# FACTS for the proposal" + (" — PRELIMINARY (C2/C3 not finished)" if prelim else ""),
                "", "Generated by `tools/make_facts.py`; do not edit. One fact per line, with its "
                "source file and sha256. Numbers come from v2 runs only. Runs: "
                + ", ".join(f"`{rel(r)}`" for r in (pilot, c1, c2, c3) if r is not None) + "."]
    data_facts(F)
    universe_facts(F, c1, c3)
    pilot_facts(F, pilot)
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
    OUT.write_text("\n".join(F.lines) + "\n")
    print(f"wrote {rel(OUT)} ({'preliminary' if prelim else 'final'}, {len(F.lines)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
