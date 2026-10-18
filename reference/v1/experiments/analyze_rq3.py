"""H3 and H4 metrics and verdicts from the stored E3 run, as hypotheses.md (frozen) and brief §7 E3
state. `uv run python -m experiments.analyze_rq3 [--run results/rq3/run_<UTC>]`

H3 (δ = 10%; δ = 5% reported as robustness): error |μ̂ − s| / |s| for the relaxation and
fixed-integer duals against the re-solve slope s, for the beta and Mom bounds over the H3
design. Exclusions (each counted): |s| < 1e-7·|U*| (not binding); any of the three MIQPs
(base, b+δ, b−δ) not reaching gap 1e-6. Supported iff, with K ≤ 60, the median error is ≥ 25%
for the relaxation duals AND ≥ 25% for the fixed-integer duals, AND the median error of the
continuous-problem duals against the continuous re-solve slope (same δ) over the matching
included instances is < 1%. Secondary: median error at K = 160 < at K = 40, per estimator.

H4: R = (big-M time to gap) / (perspective time to gap), times censored at 300 s, per
(date, N, K) at each tightness. Supported iff median R > 1 at every level AND median R(loose) <
median R(base) < median R(tight). Also Q8: where both formulations reached the 1e-4 gap, their
optimal values agree within the larger of the two final gaps (relative).
Writes results/rq3/h3h4_<UTC>.json and tables (new files).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.common import latest_done
from experiments.designs import config
from src.utils import RESULTS, ROOT, git_commit, utc_timestamp


def h3(est: pd.DataFrame, delta: float, nonbinding_rel: float) -> dict:
    e = est[np.isclose(est["delta"], delta)].copy()
    e["nonbinding"] = e["slope"].abs() < nonbinding_rel * e["U_star"].abs()
    e["gap_not_reached"] = ~e["all_reached_gap"]
    inc = e[~e["nonbinding"] & ~e["gap_not_reached"]].copy()
    for k in ("relax", "fixed"):
        inc[f"err_{k}"] = (inc[f"mu_{k}"] - inc["slope"]).abs() / inc["slope"].abs()
    inc["err_cont"] = (inc["mu_cont"] - inc["cont_slope"]).abs() / inc["cont_slope"].abs()
    small = inc[inc["K"] <= 60]
    med = lambda s: float(s.median()) if len(s) else float("nan")
    c1, c2 = med(small["err_relax"]) >= 0.25, med(small["err_fixed"]) >= 0.25
    c3 = med(inc["err_cont"]) < 0.01
    sec = {k: {"K40": med(inc.loc[inc["K"] == 40, f"err_{k}"]),
               "K160": med(inc.loc[inc["K"] == 160, f"err_{k}"])} for k in ("relax", "fixed")}
    for v in sec.values():
        v["lower_at_K160"] = bool(v["K160"] < v["K40"])
    return {"delta": delta, "n_total": int(len(e)), "n_excluded_nonbinding": int(e["nonbinding"].sum()),
            "n_excluded_gap": int((e["gap_not_reached"] & ~e["nonbinding"]).sum()),
            "n_included": int(len(inc)), "n_included_K_le_60": int(len(small)),
            "median_err_relax_K_le_60": med(small["err_relax"]),
            "median_err_fixed_K_le_60": med(small["err_fixed"]),
            "median_err_cont": med(inc["err_cont"]),
            "criterion_1": bool(c1), "criterion_2": bool(c2), "criterion_3": bool(c3),
            "H3_supported": bool(c1 and c2 and c3), "secondary": sec,
            "rows": inc[["date", "K", "constraint", "slope", "mu_relax", "mu_fixed", "mu_cont",
                         "cont_slope", "err_relax", "err_fixed", "err_cont"]].to_dict("records")}


def h4(h: pd.DataFrame, limit: float) -> dict:
    h = h.copy()
    h["t"] = h["runtime"].clip(upper=limit)
    w = h.pivot_table(index=["date", "N_label", "K", "tightness"], columns="formulation",
                      values="t").reset_index()
    w["R"] = w["bigm"] / w["perspective"]
    meds = {t: float(w.loc[w["tightness"] == t, "R"].median()) for t in ("loose", "base", "tight")}
    c1 = all(v > 1 for v in meds.values())
    c2 = meds["loose"] < meds["base"] < meds["tight"]
    both = h.pivot_table(index=["date", "N_label", "K", "tightness"], columns="formulation",
                         values=["U", "final_gap", "reached_gap"], aggfunc="first")
    q8 = []
    for idx, r in both.iterrows():
        if r[("reached_gap", "bigm")] and r[("reached_gap", "perspective")]:
            tol = max(r[("final_gap", "bigm")], r[("final_gap", "perspective")])
            ub, up = r[("U", "bigm")], r[("U", "perspective")]
            q8.append({"instance": "|".join(map(str, idx)), "rel_diff": abs(ub - up) / abs(ub),
                       "tolerance": tol, "agree": bool(abs(ub - up) / abs(ub) <= tol + 1e-12)})
    q8 = pd.DataFrame(q8)
    return {"median_R": meds, "criterion_1_all_gt_1": bool(c1),
            "criterion_2_increasing": bool(c2), "H4_supported": bool(c1 and c2),
            "n_instances": int(len(w)), "n_time_limited": {
                f: int((h[(h["formulation"] == f)]["runtime"] >= limit - 1e-6).sum())
                for f in ("bigm", "perspective")},
            "q8_checked": int(len(q8)), "q8_all_agree": bool(q8["agree"].all()) if len(q8) else None,
            "q8_max_rel_diff": float(q8["rel_diff"].max()) if len(q8) else None,
            "ratios": w.to_dict("records")}


def table_tex(r3: dict, r4: dict) -> str:
    pct = lambda x: f"{100 * x:.1f}\\%"
    yn = lambda b: "yes" if b else "no"
    return ("% Generated by experiments/analyze_rq3.py; do not edit by hand.\n"
            "\\begin{tabular}{lrrr}\n\\toprule\nMetric & Value & Criterion & Met \\\\\n\\midrule\n"
            f"H3: relaxation-dual error, $K\\le 60$ & {pct(r3['median_err_relax_K_le_60'])} & $\\geq$ 25\\% & {yn(r3['criterion_1'])} \\\\\n"
            f"H3: fixed-integer-dual error, $K\\le 60$ & {pct(r3['median_err_fixed_K_le_60'])} & $\\geq$ 25\\% & {yn(r3['criterion_2'])} \\\\\n"
            f"H3: continuous-dual error & {pct(r3['median_err_cont'])} & $<$ 1\\% & {yn(r3['criterion_3'])} \\\\\n"
            f"H3 supported & & & {yn(r3['H3_supported'])} \\\\\n\\midrule\n"
            + "".join(f"H4: median $R$, {t} & {v:.2f} & $>1$ & {yn(v > 1)} \\\\\n" for t, v in r4["median_R"].items())
            + f"H4: increasing loose $<$ base $<$ tight & & & {yn(r4['criterion_2_increasing'])} \\\\\n"
            f"H4 supported & & & {yn(r4['H4_supported'])} \\\\\n\\bottomrule\n\\end{{tabular}}\n")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", default=None)
    args = p.parse_args()
    if git_commit().endswith("-dirty"):       # analysis records must name the code that made them
        raise RuntimeError("commit code changes before running an analysis (clean tree required)")
    run = Path(args.run) if args.run else latest_done("rq3")
    cfg = config("rq3")
    est = pd.read_parquet(run / "h3_est.parquet")
    r3 = h3(est, cfg["h3"]["delta"], cfg["h3"]["nonbinding_rel"])
    r3_rob = h3(est, cfg["h3"]["delta_robustness"], cfg["h3"]["nonbinding_rel"])
    r4 = h4(pd.read_parquet(run / "h4.parquet"), cfg["h4"]["time_limit"])
    r4_rob = h4(pd.read_parquet(run / "h4robust.parquet"), cfg["h4"]["time_limit"])
    meta = json.loads((run / "run_meta.json").read_text())
    srcs = {f: hashlib.sha256((run / f).read_bytes()).hexdigest()
            for f in ("h3_est.parquet", "h4.parquet", "h4robust.parquet")}
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    out = {"created_utc": utc_timestamp(), "git_commit": git_commit(),
           "frozen_commit": meta["frozen_commit"], "run": str(run.relative_to(ROOT)),
           "source_sha256": srcs, "H3": r3, "H3_robustness_delta_5pct": r3_rob,
           "H4": r4, "H4_robustness_presolve_off": r4_rob}
    (RESULTS / "rq3" / f"h3h4_{stamp}.json").write_text(json.dumps(out, indent=1, default=str))
    (RESULTS / "rq3" / f"h3h4_table_{stamp}.tex").write_text(table_tex(r3, r4))
    print(json.dumps({"H3_supported": r3["H3_supported"], "H4_supported": r4["H4_supported"],
                      "median_R": r4["median_R"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
