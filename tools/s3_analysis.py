"""S3 analysis (RUNBOOK S3 step 3): `uv run python -m tools.s3_analysis` → results/s3_analysis/.

Reads the newest finished "ok" runs of i1, i2, n1 and n2 (experiments.common.latest_done), checks
each run's outputs against its outputs.json, applies src.analysis.s3, and writes
- s3_analysis.json: every headline count and statistic with n, the CHECKS INT quantities (K22–K29b)
  and the source run directories with their outputs.json sha256;
- tables (CSV): i1_long, i1_errors_by_f, i1_errors_by_delta, i1_nonbinding, i2_estimators,
  n1_table, n1_relax, k22_pairs, n2_pairs, n2_convex.
Deterministic: fixed order, no timestamps.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from experiments.common import file_sha256, latest_done
from src.analysis import s3 as A
from src.utils import ROOT

OUT = ROOT / "results" / "s3_analysis"


def _load(name: str) -> tuple[dict, dict]:
    run = latest_done(name)
    hashes = json.loads((run / "outputs.json").read_text())
    bad = [f for f, h in hashes.items() if file_sha256(run / f) != h]
    if bad:
        raise ValueError(f"{run}: outputs differ from outputs.json: {bad}")
    frames = {f[:-8]: pd.read_parquet(run / f) for f in hashes if f.endswith(".parquet")}
    meta = json.loads((run / "run_meta.json").read_text())
    src = {"run": str(run.relative_to(ROOT)), "commit": meta["git_commit"],
           "outputs_json_sha256": file_sha256(run / "outputs.json")}
    return frames, src


def _rows(df: pd.DataFrame, mask, what: str) -> pd.DataFrame:
    """df[mask], raising if the filter leaves 0 rows (review M2: an emptied filter must not be
    reported as n = 0 or nan)."""
    out = df[mask]
    if out.empty:
        raise ValueError(f"filter {what!r} left 0 rows (of {len(df)})")
    return out


class _Encoder(json.JSONEncoder):
    """Review L4: numpy bools and ints stay bools and ints; numpy floats become floats."""

    def default(self, o):
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        return super().default(o)


def dumps(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, cls=_Encoder)


def _q(s) -> dict:
    s = pd.Series(s, dtype=float).dropna()
    if s.empty:
        return {"n": 0}
    return {"n": int(len(s)), "min": float(s.min()), "median": float(s.median()), "max": float(s.max())}


def _counts(s: pd.Series) -> dict:
    return {str(k): int(v) for k, v in s.value_counts(dropna=False).sort_index().items()}


def k26(frames: dict[str, pd.DataFrame]) -> dict:
    """CHECKS K26: the 1e-9 verdict on every polished V (gated) and the raw incumbents' verdicts
    at Gurobi's tolerances (counted)."""
    out = {}
    for name, df in sorted(frames.items()):
        pv = df["polished_violations"]
        iv = df["incumbent_verdict"]
        flagged = iv[~iv.isin(["{}", "no incumbent"])]
        out[name] = {"n": len(df), "n_V_defined": int(df["V"].notna().sum()),
                     "polished_violations": int((~pv.isin(["{}", "V undefined"])).sum()),
                     "raw_incumbent_flagged": int(len(flagged)),
                     "raw_incumbent_rows": _counts(flagged.map(lambda x: ",".join(sorted(json.loads(x)))))}
    return out


def i1_analysis(f: dict) -> tuple[dict, dict]:
    est, pts, solves, sp, base = (f["i1_estimators"], f["i1_points"], f["i1_solves"],
                                  f["i1_slope_points"], f["i1_baseline"])
    long = A.i1_long(est)
    main_est = _rows(est, est["rel_delta"] == 0.10, "i1 rel_delta == 0.10")
    main = _rows(long, long["rel_delta"] == 0.10, "i1 long rel_delta == 0.10")
    rawerr = {}                                 # review L1: main δ only, split by usability
    for usable, col in ((True, "mu_persp_raw"), (False, "mu_persp_raw_unusable")):
        g = main_est[A._flag(main_est, "binding") & (A._flag(main_est, "persp_raw_usable") == usable)]
        with np.errstate(divide="ignore", invalid="ignore"):
            rawerr["usable" if usable else "unusable"] = _q(
                np.abs(g[col] - g["persp_slope"]) / np.abs(g["persp_slope"]))
    sp1 = _rows(sp, sp["scale_factor"] == 1.0, "i1 slope points scale_factor == 1")
    ok = est["persp_ok"].astype(bool)
    raw_bad = ~est["persp_raw_usable"].astype(bool)
    out = {
        "n_cases": len(est), "n_cases_main_delta": len(main_est),
        "n_binding_main_delta": int(main_est["binding"].sum()),
        "binding_by_key_main_delta": {k: int(v) for k, v in main_est.groupby("key")["binding"].sum().items()},
        "errors_all_f_main_delta": A.error_summary(main, by=[]).to_dict("records"),
        "k23": A.k23(est, pts),
        "suppliers": {"v_from": _counts(pts["v_from"]), "b_from": _counts(pts["b_from"]),
                      "v_tie": int(pts["v_tie"].sum()), "b_tie": int(pts["b_tie"].sum())},
        "perspective": {"stencils": len(est), "failed": int((~ok).sum()),
                        "fail_reasons": _counts(est.loc[~ok, "persp_fail_reason"]),
                        "relaxations": len(sp1), "relaxations_failed": int((~sp1["ok"].astype(bool)).sum()),
                        "failed_fraction": float((~sp1["ok"].astype(bool)).mean()),
                        "over_10pct": bool((~sp1["ok"].astype(bool)).mean() > 0.10),
                        "kinks": int(est["persp_kink"].astype(bool).sum()),
                        "concavity_failures": int((~est.loc[ok, "persp_concave"].astype(bool)).sum()),
                        "raw_dual_rel_err_binding": rawerr,
                        "raw_relaxation_failed": int(raw_bad.sum()),
                        "raw_relaxation_failed_kept_duals": int((raw_bad & est["mu_persp_raw_unusable"].notna()).sum())},
        "k29b": {**A.k29b(est), "binding_keys": A.k29b(est[est["binding"].astype(bool)])},
        "nonbinding_by_delta": A.nonbinding_breakdown(est, by="rel_delta").to_dict("records"),
        "k27_baseline": A.k27(base),
        "k27_baseline_by_delta": {f"{d:g}": A.k27(g) for d, g in base.groupby("rel_delta", sort=True)},
        "work": _q(solves["work"]), "statuses": _counts(solves["status"]),
    }
    tables = {"i1_long": long, "i1_errors_by_f": A.error_summary(main, by=["f"]),
              "i1_errors_by_delta": A.error_summary(_rows(long, long["date"] == "2017-12", "i1 date == 2017-12"),
                                                    by=["rel_delta"]),
              "i1_nonbinding": A.nonbinding_breakdown(est, by="rel_delta")}
    return out, tables


def i2_estimators(pts: pd.DataFrame, iv: pd.DataFrame) -> pd.DataFrame:
    """Estimator rows at I2's estimator points, with the certified interval from the sweep."""
    e = _rows(pts, A._flag(pts, "estimator"), "i2 estimator points")
    rows = []
    for _, r in iv.iterrows():
        g = e[(e["instance"] == r["instance"]) & np.isclose(e["bound"], r["e"], rtol=0, atol=1e-15)]
        if len(g) != 1:
            raise ValueError(f"I2 estimator point {r['instance']} {r['e']}: {len(g)} rows")
        q = g.iloc[0]
        rows.append({"id": f"{r['instance']}_e{r['e']:.6g}", "instance": r["instance"],
                     "date": q["date"], "K": q["K"], "key": q["key"], "b": r["e"],
                     "rel_delta": r["delta"] / r["e"], "V": q["V"], "B": q["B"], "L": r["L"],
                     "H": r["H"], "s": r["s"], "binding": bool(r["binding"]),
                     "solver_error": bool(r["solver_error"]), "mu_bigm_relax": q["mu_bigm_relax"],
                     "persp_slope": q["persp_slope"], "persp_ok": bool(q["persp_ok"]),
                     "mu_fixed": q["mu_fixed"]})
    return pd.DataFrame(rows)


def i2_analysis(f: dict) -> tuple[dict, dict]:
    pts, iv, base = f["i2_points"], f["i2_intervals"], f["i2_baseline"]
    est = i2_estimators(pts, iv)
    long = A.i1_long(est)
    sec = []                                   # the baseline's centred grid secants (interior points)
    for inst, g in base.sort_values("bound").groupby("instance"):
        g = g.reset_index(drop=True)
        for i in range(1, len(g) - 1):
            h1, h2 = g.loc[i + 1, "bound"] - g.loc[i, "bound"], g.loc[i, "bound"] - g.loc[i - 1, "bound"]
            if np.isclose(h1, h2, rtol=1e-9):
                sec.append({"instance": inst, "bound": g.loc[i, "bound"], "mu": g.loc[i, "mu"],
                            "value": g.loc[i, "value"],
                            "secant": (g.loc[i + 1, "value"] - g.loc[i - 1, "value"]) / (h1 + h2)})
    sec = pd.DataFrame(sec)
    if sec.empty:
        raise ValueError("i2: 0 centred grid secants")
    with np.errstate(divide="ignore", invalid="ignore"):
        e = sec["mu"] * sec["bound"] / np.abs(sec["value"])
        serr = (np.abs(sec["mu"] - sec["secant"]) / np.abs(sec["secant"]))[e >= A.ZERO_ELASTICITY]
    gb = _rows(base, base["bound"] > 0, "i2 baseline bound > 0")
    out = {"n_points": len(pts), "instances": sorted(pts["instance"].unique().tolist()),
           "constraint": f"{pts['key'].iloc[0]}@{pts['b_base'].iloc[0]:g}",
           "k23": A.k23(est, pts), "estimators": A.error_summary(long, by=[]).to_dict("records"),
           "k27_baseline_grid": A.k27(gb.assign(b=gb["bound"])),
           "baseline_grid_secant_rel_err": _q(serr),
           "suppliers": {"v_from": _counts(pts["v_from"]), "b_from": _counts(pts["b_from"])},
           "statuses": _counts(f["i2_solves"]["status"]), "work": _q(f["i2_solves"]["work"])}
    return out, {"i2_estimators": long}


def n1_analysis(f: dict) -> tuple[dict, dict]:
    s, rel = f["n1_solves"], f["n1_relax"]
    tab = A.n1_table(s)
    rg = A.relax_gaps(rel, s)
    pairs = A.k22_pairs(s)
    dfn = pairs[~pairs["undefined"].astype(bool)]
    by = {}
    on = _rows(tab, tab["presolve"] == -1, "n1 presolve == -1")
    off = _rows(tab, tab["presolve"] == 0, "n1 presolve == 0")
    for (tn, arm), g in on.groupby(["tightness", "arm"], sort=True):
        by[f"{tn}/{arm}"] = {"n": len(g), "root_gap": _q(g["root_gap"]), "work": _q(g["work"]),
                             "nodes": _q(g["nodes"]), "final_gap_eff": _q(g["final_gap_eff"]),
                             "shortfall": _q(g["shortfall"]), "censored": int(g["censored"].sum())}
    pairsum = {f"{ai}|{aj}": {"n": len(g), "fail": int((~g["pass"].astype(bool)).sum()),
                              "worst_ratio": float(g["ratio"].max()), "worst_abs_dV": float(g["abs_dV"].max()),
                              "both_reached_gap": int(g["both_reached_gap"].sum())}
               for (ai, aj), g in dfn.groupby(["arm_i", "arm_j"])}
    m = A._main(s)
    out = {"n_solves": len(m), "statuses": _counts(m["status"]), "by_tightness_arm": by,
           "plain_relaxation_gaps": {tn: {"bigm": _q(g["bigm_gap"]), "perspective": _q(g["perspective_gap"])}
                                     for tn, g in rg.groupby("tightness")},
           "k22": {"n_pairs": len(pairs), "n_undefined": int(pairs["undefined"].astype(bool).sum()),
                   "n_fail": int((~dfn["pass"].astype(bool)).sum()), "by_pair": pairsum},
           "k24": A.k24(rg), "k25": A.k25(s),
           "cone_effect_rel": {arm: _q(g["cone_effect_rel"]) for arm, g in m.groupby("arm")},
           "presolve_off": {arm: {"n": len(g), "work": _q(g["work"]), "root_gap": _q(g["root_gap"]),
                                  "censored": int(g["censored"].sum())}
                            for arm, g in off.groupby("arm")},
           "presolve_N250": presolve_like_for_like(on, off, rg)}
    return out, {"n1_table": tab, "n1_relax": rg, "k22_pairs": pairs}


def presolve_like_for_like(on: pd.DataFrame, off: pd.DataFrame, rg: pd.DataFrame, N: str = "250") -> dict:
    """S3b item 7: at N = 250 (the presolve-off instances), per arm, presolve on against off: the
    root gap (median, range), the median Work and the censored count; beside the median
    plain-relaxation gaps of the same instances."""
    lab = lambda df: df["N"].astype(str) == N
    on, off = _rows(on, lab(on), f"n1 presolve on, N = {N}"), _rows(off, lab(off), f"n1 presolve off, N = {N}")
    r = _rows(rg, lab(rg), f"n1 relaxations, N = {N}")
    side = lambda g: {"n": len(g), "root_gap": _q(g["root_gap"]), "work_median": float(g["work"].median()),
                      "censored": int(g["censored"].sum())}
    arms = {arm: {"on": side(g), "off": side(_rows(off, off["arm"] == arm, f"n1 presolve off, {arm}"))}
            for arm, g in on.groupby("arm", sort=True)}
    return {"N": N, "arms": arms,
            "plain_relaxation_gap": {"bigm": _q(r["bigm_gap"]), "perspective": _q(r["perspective_gap"])}}


def n2_analysis(f: dict) -> tuple[dict, dict]:
    m, cv = f["n2_miqp"], f["n2_convex"]
    d = A.n2_disagreements(m)
    dd = d[~d["undefined"].astype(bool)]
    arms = {f"{arm}/s{s:g}": {"statuses": _counts(g["status"]), "gap_eff": _q(g["gap_eff"]),
                              "cone_effect_rel": _q(g["cone_effect_rel"]), "work": _q(g["work"])}
            for (arm, s), g in m.groupby(["arm", "s_obj"])}
    conv = {f"{sol}/norm={nz}/scaled={sc}": {"n": len(g), "ok": int(g["ok"].sum()), "statuses": _counts(g["status"]),
                                             "A_rel_err": _q(g["A_rel_err"]), "w_l1_rel_err": _q(g["w_l1_rel_err"]),
                                             "max_binding_dual_rel_err": _q(g["max_binding_dual_rel_err"])}
            for (sol, nz, sc), g in _rows(cv, cv["solver"] != "reference", "n2 convex non-reference")
            .groupby(["solver", "normalize", "scaled"])}
    out = {"miqp": {"n": len(m), "arms": arms, "n_pairs": len(d),
                    "incumbent_beats_other_bound": int(dd["incumbent_beats_other_bound"].sum()),
                    "beyond_claimed_gap": int(dd["beyond_claimed_gap"].sum()),
                    "by_scale": {f"s{s:g}": {"n": len(g), "beats": int(g["incumbent_beats_other_bound"].sum()),
                                             "beyond": int(g["beyond_claimed_gap"].sum())}
                                 for s, g in dd.groupby("s_obj")}},
           "convex": conv}
    return out, {"n2_pairs": d, "n2_convex": cv}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    srcs, res, tables, solve_frames = {}, {}, {}, {}
    for name, fn in (("i1", i1_analysis), ("i2", i2_analysis), ("n1", n1_analysis), ("n2", n2_analysis)):
        frames, srcs[name] = _load(name)
        res[name], t = fn(frames)
        tables.update(t)
        solve_frames.update({k: v for k, v in frames.items()
                             if k in ("i1_solves", "i2_solves", "n1_solves", "n2_miqp")})
    res["k26"] = k26(solve_frames)
    res["sources"] = srcs
    for k, df in sorted(tables.items()):
        df.to_csv(OUT / f"{k}.csv", index=False, float_format="%.10g")
    (OUT / "s3_analysis.json").write_text(dumps(res) + "\n")
    print(json.dumps(res["sources"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
