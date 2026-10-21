"""S3 analysis (RUNBOOK S3 step 3; DESIGN §7; CHECKS INT), from the runners' frames. Pure functions
on DataFrames; tools/s3_analysis.py applies them to the newest finished runs and writes
results/s3_analysis/.

Estimators at an I1 case (DESIGN §7): bigm_relax (the big-M relaxation dual, dual simplex),
perspective (the slope of the perspective relaxation's value, DESIGN §6 as edited), fixed (the
fixed-integer dual at the incumbent that supplied V). The truth is the certified point slope
s = (V₊ − V₋)/(2δ) with its interval [L, H] (combined V and B, B_eff); a case binds iff L > 0.
- Relative error |μ̂ − s|/|s| over binding cases; an estimator is excluded where it is undefined
  (the perspective stencil failed, or a dual is nan); both counts are reported (K28).
- "Zero" for the non-binding breakdown: |μ̂|·b/|V| < 1e-4, DESIGN §6's bindingness scale.
- B_eff = max(B, V) + 1e-6·|V| (DESIGN §6) wherever a bound enters (K22, K23, N2).
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

ZERO_ELASTICITY = 1e-4
BEFF_RTOL = 1e-6
ESTIMATORS = (("bigm_relax", "mu_bigm_relax"), ("perspective", "persp_slope"), ("fixed", "mu_fixed"))
CASE_COLS = ("id", "instance", "date", "f", "K", "key", "b", "rel_delta")


def _flag(df: pd.DataFrame, col: str) -> pd.Series:
    """A boolean column; a missing value is an error, never True (pandas' astype(bool) would
    make NaN True)."""
    s = df[col]
    if s.isna().any():
        raise ValueError(f"{col}: {int(s.isna().sum())} missing values")
    return s.astype(bool)


def b_eff(B, V):
    B, V = np.asarray(B, float), np.asarray(V, float)
    return np.maximum(B, V) + BEFF_RTOL * np.abs(V)


def _is_zero(mu, b, V):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.abs(mu) * np.abs(b) / np.abs(V) < ZERO_ELASTICITY


# ----- I1 / I2 estimators -----

def i1_long(est: pd.DataFrame, bound_col: str = "b") -> pd.DataFrame:
    """One row per (case, estimator): μ̂, s, [L, H], binding, available, rel_err (binding and
    available only), in_interval, zero."""
    rows = []
    defined = np.isfinite(est["L"].astype(float)) & np.isfinite(est["H"].astype(float))
    binding = _flag(est, "binding") & defined
    s = est["s"].astype(float)
    for name, col in ESTIMATORS:
        mu = est[col].astype(float)
        avail = np.isfinite(mu)
        if name == "perspective" and "persp_ok" in est:
            avail &= _flag(est, "persp_ok")
        with np.errstate(divide="ignore", invalid="ignore"):
            err = np.where(binding & avail, np.abs(mu - s) / np.abs(s), np.nan)
        d = est[[c for c in CASE_COLS if c in est] + ["s", "L", "H", "V"]].copy()
        d["bound"] = est[bound_col].astype(float)
        d["estimator"], d["mu"], d["available"] = name, mu, avail
        d["defined"], d["binding"], d["rel_err"] = defined, binding, err
        d["in_interval"] = avail & defined & (mu >= est["L"]) & (mu <= est["H"])
        d["zero"] = _is_zero(mu, d["bound"], est["V"])
        rows.append(d)
    return pd.concat(rows, ignore_index=True)


def error_summary(long: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Per estimator (and `by`): cases, binding cases with the estimator available (n_binding),
    binding cases where it is not (n_excluded), error quantiles, and how many lie in [L, H]."""
    out = []
    for keys, g in long.groupby(["estimator"] + list(by), sort=True):
        keys = keys if isinstance(keys, tuple) else (keys,)
        b = g[g["binding"]]
        ok = b[b["available"]]
        e = ok["rel_err"]
        q = (lambda x: float(e.quantile(x))) if len(e) else (lambda x: np.nan)
        out.append({**dict(zip(["estimator"] + list(by), keys)), "n_cases": len(g),
                    "n_binding": len(ok), "n_excluded": int((~b["available"]).sum()),
                    "median_rel_err": q(0.5), "q25_rel_err": q(0.25), "q75_rel_err": q(0.75),
                    "max_rel_err": float(e.max()) if len(e) else np.nan,
                    "n_in_interval": int(ok["in_interval"].sum())})
    return pd.DataFrame(out)


def nonbinding_breakdown(est: pd.DataFrame, by: str | None = None) -> pd.DataFrame:
    """Non-binding cases (interval defined, L ≤ 0) by which estimators are zero or nonzero;
    with `by` (e.g. rel_delta), one breakdown per value."""
    if by is not None:
        parts = [nonbinding_breakdown(g).assign(**{by: v}) for v, g in est.groupby(by, sort=True)]
        parts = [p for p in parts if len(p)]
        cols = [by, "pattern", "n"]
        return pd.concat(parts, ignore_index=True)[cols] if parts else pd.DataFrame(columns=cols)
    long = i1_long(est)
    nb = long[long["defined"] & ~long["binding"]]
    pats = {}
    for cid, g in nb.groupby("id", sort=True):
        g = g.set_index("estimator")
        parts = []
        for name, _ in ESTIMATORS:
            r = g.loc[name]
            parts.append(f"{name}=failed" if not r["available"]
                         else (f"{name}=0" if r["zero"] else f"{name}≠0"))
        pats[cid] = ", ".join(parts)
    s = pd.Series(pats, dtype=object)
    out = s.value_counts().rename_axis("pattern").reset_index(name="n")
    return out.sort_values(["n", "pattern"], ascending=[False, True], ignore_index=True)


def k23(est: pd.DataFrame, points: pd.DataFrame) -> dict:
    """CHECKS K23: cases excluded (undefined V; K28), H < 0, and every point's combined
    V ≤ B + 1e-6·|V| (recomputed from V and B, not read from the flag)."""
    defined = np.isfinite(est["L"].astype(float)) & np.isfinite(est["H"].astype(float))
    Hneg = int((est.loc[defined, "H"] < 0).sum())
    V, B = points["V"].astype(float), points["B"].astype(float)
    fin = np.isfinite(V) & np.isfinite(B)
    over = int((V[fin] > B[fin] + BEFF_RTOL * np.abs(V[fin])).sum())
    flag_rec = int(points["flag_V_exceeds_B"].astype(bool).sum()) if "flag_V_exceeds_B" in points else 0
    serr = int(est["solver_error"].astype(bool).sum()) if "solver_error" in est else 0
    return {"n_cases": len(est), "n_excluded": int((~defined).sum()), "n_H_negative": Hneg,
            "n_points": len(points), "n_points_undefined": int((~fin).sum()),
            "n_V_exceeds_B": over, "n_flag_recorded": flag_rec, "n_solver_error_flag": serr,
            "violations": Hneg + over}


# ----- N1 / N2 -----

INSTANCE = ("date", "N", "f", "K", "tightness")


def _main(solves: pd.DataFrame) -> pd.DataFrame:
    return solves[~solves["rerun"].astype(bool)] if "rerun" in solves else solves


def _pairs(solves: pd.DataFrame, group: list[str]) -> pd.DataFrame:
    out = []
    for keys, g in solves.groupby(group, sort=True, dropna=False):
        keys = keys if isinstance(keys, tuple) else (keys,)
        g = g.sort_values("arm")
        for (_, a), (_, c) in itertools.combinations(g.iterrows(), 2):
            rec = {**dict(zip(group, keys)), "arm_i": a["arm"], "arm_j": c["arm"],
                   "status_i": a["status"], "status_j": c["status"],
                   "both_reached_gap": bool(a["reached_gap"]) and bool(c["reached_gap"])}
            if not all(np.isfinite(x) for x in (a["V"], c["V"], a["B"], c["B"])):
                why = "V undefined" if not (np.isfinite(a["V"]) and np.isfinite(c["V"])) else "B undefined"
                out.append({**rec, "undefined": True, "undefined_reason": why, "pass": np.nan, "abs_dV": np.nan,
                            "allowed": np.nan, "ratio": np.nan, "within_allowed": np.nan,
                            "i_beats_j": False, "j_beats_i": False})
                continue
            bi, bj = float(b_eff(a["B"], a["V"])), float(b_eff(c["B"], c["V"]))
            dV = abs(a["V"] - c["V"])
            allowed = max(bi - a["V"], bj - c["V"])
            out.append({**rec, "undefined": False, "undefined_reason": "", "V_i": a["V"], "V_j": c["V"], "Beff_i": bi,
                        "Beff_j": bj, "pass": bool(a["V"] <= bj and c["V"] <= bi),
                        "i_beats_j": bool(a["V"] > bj), "j_beats_i": bool(c["V"] > bi), "abs_dV": dV,
                        "allowed": allowed, "ratio": dV / allowed if allowed > 0 else np.inf,
                        "within_allowed": bool(dV <= allowed)})
    return pd.DataFrame(out)


def k22_pairs(solves: pd.DataFrame) -> pd.DataFrame:
    """CHECKS K22: every pair of arms at every N1 instance (and presolve setting), at any stop
    status: V_i ≤ B_eff,j both ways; |ΔV| against the larger certified gap B_eff − V."""
    s = _main(solves)
    return _pairs(s, [c for c in INSTANCE + ("presolve",) if c in s])


def n2_disagreements(miqp: pd.DataFrame) -> pd.DataFrame:
    """N2(a): per instance and s_obj, every pair of arms: an incumbent beating the other arm's
    bound (V_i > B_eff,j) and a disagreement beyond the larger claimed gap."""
    p = _pairs(miqp, [c for c in INSTANCE + ("s_obj",) if c in miqp])
    if p.empty:
        return p
    d = ~p["undefined"].astype(bool)
    p["incumbent_beats_other_bound"] = False
    p.loc[d, "incumbent_beats_other_bound"] = ~p.loc[d, "pass"].astype(bool)
    p["beyond_claimed_gap"] = False
    p.loc[d, "beyond_claimed_gap"] = ~p.loc[d, "within_allowed"].astype(bool)
    return p


def k24(relax: pd.DataFrame) -> dict:
    """CHECKS K24: plain perspective relaxation ≤ big-M relaxation + 1e-8·max(|V|, |V_ref|), V the
    perspective value and V_ref the instance's best known value; failed relaxations excluded."""
    ok = _flag(relax, "perspective_ok")
    if relax.loc[ok, ["bigm", "perspective", "V_best"]].isna().any().any():
        raise ValueError("K24: a usable instance has an undefined relaxation or best known value")
    r = relax[ok]
    tol = 1e-8 * np.maximum(np.abs(r["perspective"]), np.abs(r["V_best"]))
    margin = (r["bigm"] - r["perspective"]) / np.abs(r["V_best"])
    bad = relax[~ok]
    return {"n": len(relax), "n_failed": int((~ok).sum()),
            "failed_reasons": {str(k): int(v) for k, v in
                               bad["perspective_fail_reason"].fillna("status").value_counts().items()},
            "violations": int((r["perspective"] > r["bigm"] + tol).sum()),
            "margin_rel_min": float(margin.min()) if len(r) else np.nan,
            "margin_rel_median": float(margin.median()) if len(r) else np.nan,
            "margin_rel_max": float(margin.max()) if len(r) else np.nan}


def k25(solves: pd.DataFrame) -> dict:
    """CHECKS K25: each rerun against its original: identical Work, node count and incumbent value."""
    keys = [c for c in INSTANCE + ("arm", "presolve") if c in solves]
    rr = solves[solves["rerun"].astype(bool)]
    orig = _main(solves).set_index(keys)
    rows = []
    for _, r in rr.iterrows():
        o = orig.loc[tuple(r[k] for k in keys)]
        sameV = o["V"] == r["V"] or (np.isnan(o["V"]) and np.isnan(r["V"]))
        same = bool(o["work"] == r["work"] and o["nodes"] == r["nodes"] and o["U_raw"] == r["U_raw"] and sameV)
        rows.append({**{k: r[k] for k in keys}, "status": r["status"], "work": r["work"],
                     "work_orig": o["work"], "nodes": r["nodes"], "nodes_orig": o["nodes"],
                     "U_raw": r["U_raw"], "U_raw_orig": o["U_raw"], "identical": same})
    return {"n": len(rr), "identical": int(sum(x["identical"] for x in rows)), "rows": rows}


def best_known(solves: pd.DataFrame) -> pd.Series:
    """The best known value per N1 instance: the largest polished V over its arms and presolve
    settings."""
    s = _main(solves)
    return s.groupby([c for c in INSTANCE if c in s])["V"].max().rename("V_best")


def n1_table(solves: pd.DataFrame) -> pd.DataFrame:
    """Per N1 solve: V_best, root gap (root bound − V_best)/|V_best|, final certified gap
    (B_eff − V)/|V|, shortfall against V_best, censoring (stopped before the gap)."""
    s = _main(solves).copy()
    s = s.join(best_known(solves), on=[c for c in INSTANCE if c in s])
    s["root_gap"] = (s["root_bound"] - s["V_best"]) / np.abs(s["V_best"])
    s["final_gap_eff"] = (b_eff(s["B"], s["V"]) - s["V"]) / np.abs(s["V"])
    s["shortfall"] = (s["V_best"] - s["V"]) / np.abs(s["V_best"])
    s["censored"] = s["status"] != "OPTIMAL"
    return s


def relax_gaps(relax: pd.DataFrame, solves: pd.DataFrame) -> pd.DataFrame:
    """The plain relaxations' gaps against the best known value."""
    r = relax.join(best_known(solves), on=[c for c in INSTANCE if c in relax])
    r["bigm_gap"] = (r["bigm"] - r["V_best"]) / np.abs(r["V_best"])
    r["perspective_gap"] = (r["perspective"] - r["V_best"]) / np.abs(r["V_best"])
    return r


# ----- baseline and K29b -----

def k27(base: pd.DataFrame) -> dict:
    """CHECKS K27 on baseline records: where the constraint binds (e = μ·b/value ≥ 1e-4) the dual
    matches the K15-rule slope within 1% (flagged stencils rechecked at 0.1%, already applied in
    the record); the dual-versus-secant error is reported, not gated."""
    with np.errstate(divide="ignore", invalid="ignore"):
        e = base["mu"] * base["b"] / np.abs(base["value"])
        binding = (e >= ZERO_ELASTICITY) & np.isfinite(base["slope"].astype(float))
    for col in ("within", "kink"):
        _flag(base[binding], col)
        sec = (np.abs(base["mu"] - base["secant"]) / np.abs(base["secant"])) if "secant" in base else None
    b = base[binding]
    out = {"n": len(base), "n_binding": int(binding.sum()), "n_within": int(b["within"].astype(bool).sum()),
           "n_flagged": int(b["kink"].astype(bool).sum()),
           "violations": int((~b["within"].astype(bool)).sum()),
           "max_rel_err": float(b["rel_err"].max()) if len(b) else np.nan}
    if sec is not None:
        sb = sec[binding & np.isfinite(sec)]
        out.update(n_secant=int(len(sb)),
                   secant_rel_err_median=float(sb.median()) if len(sb) else np.nan,
                   secant_rel_err_max=float(sb.max()) if len(sb) else np.nan)
    return out


def k29b(est: pd.DataFrame) -> dict:
    """CHECKS K29b: slopes at s_obj and k29b_scale·s_obj agree within 1e-5·|ŝ| + 2N, N the central
    slope's a-priori noise at s_obj (1e-9·max(|V|, |V_ref|)/δ_r with V_ref = V(b))."""
    r = est[np.isfinite(est["k29b_scale"].astype(float))]
    ok = _flag(r, "persp_ok") & _flag(r, "persp_ok_k29b")
    q = r[ok]
    diff = np.abs(q["persp_slope"] - q["persp_slope_k29b"])
    tol = 1e-5 * np.abs(q["persp_slope"]) + 2 * q["persp_noise_central"]
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = diff / np.abs(q["persp_slope"])
    rel = rel[np.isfinite(rel)]
    return {"n": int(len(q)), "n_failed": int((~ok).sum()), "misses": int((diff > tol).sum()),
            "max_ratio": float((diff / tol).max()) if len(q) else np.nan,
            "max_rel_diff": float(rel.max()) if len(rel) else np.nan,
            "instances": sorted(r["instance"].unique().tolist()) if "instance" in r else []}
