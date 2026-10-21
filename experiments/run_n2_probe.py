"""N2(b) normalization probe (S3b item 8, optional; Isaiah's GATE I note, Decision 47):
`make n2_probe` → results/n2_probe/run_<UTC>/ (RUN_LOG "ok"). Exploratory, no prediction.

S3 found Gurobi's barrier identical to 12 digits with and without the risk-row normalization
(N2(b)). For each N2(b) date (numerics.yaml) and objective scaling (unscaled, and s_obj as in
run_n2), the explicit P-RB QCQP is built by CVXPY exactly as run_n2 builds it
(run_n2._problem, run_n2._solve, src.opt.risk_budget.solve_qcqp; DEFAULT_TOLS for the barrier),
with the risk row normalized and not, and:
- the Gurobi model CVXPY builds is written to .lp (CVXPY's save_file, before the solve) in the run
  directory, and the two files are diffed line by line (lp_diff);
- each is solved at the default setting (which reproduces run_n2's solve), with Presolve 0, and
  with ScaleFlag 0. Recorded: status, A*, A* against the N2 run's reference (Clarabel at 1e-10),
  and, per setting, the normalized-against-unnormalized differences in A* and w.
"""
from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import experiments.run_n2 as n2
from experiments import s3
from experiments.common import fail, finish, open_run
from experiments.cont import pool_chunks
from experiments.designs import config
from experiments.run_s3b import load_run
from src.opt.integer import choose_s_obj
from src.opt.risk_budget import solve_risk_budget

CONFIG = "experiments/configs/n2_probe.yaml"
FRAMES = ("n2_probe", "n2_probe_lp", "n2_probe_pairs")
SOLVER = "GUROBI_BARRIER"
MAX_LISTED = 20


def lp_diff(a: Path, b: Path) -> dict:
    """Line counts of two LP files, the number of changed lines, and up to MAX_LISTED changed
    line pairs ([line in a, line in b]; None where a line is only on one side)."""
    la, lb = Path(a).read_text().splitlines(), Path(b).read_text().splitlines()
    changed, n = [], 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=la, b=lb, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        n += max(i2 - i1, j2 - j1)
        A, B = la[i1:i2], lb[j1:j2]
        for k in range(max(len(A), len(B))):
            changed.append([A[k] if k < len(A) else None, B[k] if k < len(B) else None])
    return {"n_lines_a": len(la), "n_lines_b": len(lb), "n_changed": n, "changed": changed[:MAX_LISTED]}


def probe_task(item: dict) -> dict[str, pd.DataFrame]:
    P, alpha = n2._problem(item["date"], item["N"])
    s = choose_s_obj(solve_risk_budget(P, alpha).A)
    scale = s if item["scaled"] else 1.0
    run = Path(item["run_dir"])
    tag = f"{item['date']}_scaled{int(bool(item['scaled']))}"
    files = {nz: f"n2probe_{tag}_norm{int(nz)}.lp" for nz in (True, False)}
    A_ref = item.get("A_ref", np.nan)
    rows, sols = [], {}
    for nz in (True, False):
        for name, extra in item["settings"].items():
            opts = {**n2.DEFAULT_TOLS[SOLVER], **extra}
            if name == "default":
                opts["save_file"] = str(run / files[nz])
            rec = {"date": item["date"], "N": str(item["N"]), "scaled": bool(item["scaled"]),
                   "obj_scale": scale, "normalize": nz, "setting": name,
                   "params": json.dumps(extra, sort_keys=True), "A_ref": A_ref}
            try:
                sol = n2._solve(P, alpha, SOLVER, nz, scale, opts)
                sols[(name, nz)] = sol
                rec.update(ok=True, status=sol.status, error=None, A=sol.objective,
                           A_rel_err=abs(sol.objective - A_ref) / abs(A_ref), solve_time=sol.solve_time)
            except Exception as err:                       # a solver failure is a result here
                rec.update(ok=False, status="failed", error=f"{type(err).__name__}: {err}", A=np.nan,
                           A_rel_err=np.nan, solve_time=np.nan)
            rows.append(rec)
    pairs = []
    for name in item["settings"]:
        a, b = sols.get((name, True)), sols.get((name, False))
        pairs.append({"date": item["date"], "scaled": bool(item["scaled"]), "setting": name,
                      "dA_rel": abs(a.objective - b.objective) / abs(a.objective) if a and b else np.nan,
                      "dw_max": float(np.max(np.abs(a.w - b.w))) if a and b else np.nan,
                      "identical_A": bool(a and b and a.objective == b.objective)})
    d = lp_diff(run / files[True], run / files[False])
    lp = {"date": item["date"], "scaled": bool(item["scaled"]), "lp_normalized": files[True],
          "lp_unnormalized": files[False], **{k: v for k, v in d.items() if k != "changed"},
          "changed_json": json.dumps(d["changed"])}
    return {"n2_probe": pd.DataFrame(rows), "n2_probe_lp": pd.DataFrame([lp]),
            "n2_probe_pairs": pd.DataFrame(pairs)}


def main(argv=None) -> int:
    run = None
    try:
        cfg = config("n2_probe")
        ncfg = config(cfg["source_config"])
        if not str(ncfg.get("status", "")).startswith("approved"):
            raise RuntimeError(f"{cfg['source_config']}.yaml is not approved: {ncfg.get('status')}")
        cv = load_run(cfg["n2_run"])["n2_convex"]
        ref = cv[cv["solver"] == "reference"].set_index("date")["A"]
        c = ncfg["n2"]["convex"]
        run, _ = open_run("n2_probe", CONFIG)
        items = [{"date": ym, "N": c.get("N", "full"), "scaled": bool(sc), "run_dir": str(run),
                  "settings": cfg["settings"], "A_ref": float(ref.loc[ym])}
                 for ym in c["dates"] for sc in cfg["scaled"]]
        out = pool_chunks(run, FRAMES, items, lambda t: f"{t['date']}_scaled{int(t['scaled'])}",
                          probe_task, s3.workers(cfg))
        pr = out["n2_probe_pairs"]
        summary = {"n_items": len(items), "solves": len(out["n2_probe"]),
                   "failed": int((~out["n2_probe"]["ok"].astype(bool)).sum()),
                   "identical_A_by_setting": {k: int(g["identical_A"].sum()) for k, g in pr.groupby("setting")},
                   "max_dA_rel_by_setting": {k: float(g["dA_rel"].max()) for k, g in pr.groupby("setting")},
                   "lp_changed_lines": {f"{r.date}/scaled{int(r.scaled)}": int(r.n_changed)
                                        for r in out["n2_probe_lp"].itertuples()}}
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        lps = sorted(run.glob("n2probe_*.lp"))
        finish(run, CONFIG, out, f"n2_probe: {summary['solves']} solves", extra_files=[run / "summary.json", *lps])
        print(json.dumps(summary, indent=1, default=float))
    except Exception as e:
        fail(run, CONFIG, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
