"""S3b analysis (Isaiah's GATE I note, items 2–7): `uv run python -m tools.s3b_analysis` →
results/s3b_analysis/s3b_analysis.json and CSVs.

Reads the newest finished "ok" runs of k29b_ext and s3b, the I1, I2 and N1 runs those name (and
results/s3_analysis/s3_analysis.json for item 7), checks every run's outputs against its
outputs.json, and writes, with n and the source files:
- item 2: K29b's rule on all 36 cases, and on the binding ones; ŝ(s_obj) against I1's own slope;
- item 3: support classes (P1–P3) by f and δ, the note's predictions, every estimator's errors per
  class, and the δ = 10% Spearman correlations between each relaxation's gap at b and its error;
- item 4: the I2 grids' certified and uncertified nonconcave triples and support changes;
- item 5: hedged names per relaxation, the prediction, max min(w⁺, w⁻), 2λ*·dᵢ·ℓ against c + 2κ;
- item 6: whether both arms' z are stored at the I1 and I2 points;
- item 7: the presolve comparison, copied from s3_analysis.json.
Predictions and tolerances are the note's; a failed prediction is reported, never raised.
Deterministic: fixed order, no timestamps.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from experiments.common import file_sha256, latest_done, run_meta
from src.analysis import s3 as A
from src.analysis import s3b as S
from src.utils import ROOT
from tools.s3_analysis import _q, _rows, dumps

OUT = ROOT / "results" / "s3b_analysis"
P1_TOL = 1e-6           # item 3 prediction P1: |μ_fixed − s|/s ≤ 1e-6
P2_TOL = 4.2e-3         # item 3 prediction P2: at most the convex baseline's largest secant error (K27)
N_FIXED_IN_LH = {0.10: 4, 0.05: 5}   # the fixed-integer in-[L, H] cases the note counts


def _load(run) -> tuple[dict, dict]:
    run = ROOT / run if not str(run).startswith(str(ROOT)) else run
    hashes = json.loads((run / "outputs.json").read_text())
    bad = [f for f, h in hashes.items() if file_sha256(run / f) != h]
    if bad:
        raise ValueError(f"{run}: outputs differ from outputs.json: {bad}")
    frames = {f[:-8]: pd.read_parquet(run / f) for f in hashes if f.endswith(".parquet")}
    src = {"run": str(run.relative_to(ROOT)), "commit": run_meta(run)["git_commit"],
           "outputs_json_sha256": file_sha256(run / "outputs.json")}
    return frames, src


def item2(x: pd.DataFrame, i1est: pd.DataFrame) -> dict:
    e = i1est.set_index("id")
    if not set(x["id"]) <= set(e.index):
        raise ValueError("K29b-ext ids not in the I1 run")
    x = x.assign(binding=x["id"].map(e["binding"]).astype(bool),
                 i1_slope=x["id"].map(e["persp_slope"]))
    twin = x[x["rel_delta"] == 0.05].merge(x[x["rel_delta"] == 0.10], on=["instance", "key"],
                                          suffixes=("_5", "_10"))
    return {"all": {**A.k29b(x)}, "binding": A.k29b(_rows(x, x["binding"], "k29b_ext binding")),
            "n_binding": int(x["binding"].sum()),
            "slope_equals_i1_bitwise": int((x["persp_slope"] == x["i1_slope"]).sum()),
            "max_abs_slope_minus_i1": float((x["persp_slope"] - x["i1_slope"]).abs().max()),
            "delta5_twins": len(twin),
            "delta5_twins_identical_both_scales": int(((twin["persp_slope_5"] == twin["persp_slope_10"])
                                                       & (twin["persp_slope_k29b_5"] == twin["persp_slope_k29b_10"])).sum()),
            "kinks": int(x["persp_kink"].astype(bool).sum() + x["persp_kink_k29b"].astype(bool).sum())}


def item3(sup: pd.DataFrame, i1est: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    cls = S.case_classes(sup)
    long = A.i1_long(i1est)
    est = i1est.set_index("id")
    c = cls.set_index("id").join(est[["date", "f", "K", "key", "rel_delta", "binding", "s", "L", "H",
                                      "mu_fixed", "V", "U_bigm_relax", "persp_V"]])
    wide = long.pivot_table(index="id", columns="estimator", values=["rel_err", "in_interval"], aggfunc="first")
    for est_name in ("bigm_relax", "perspective", "fixed"):
        c[f"err_{est_name}"] = wide[("rel_err", est_name)]
        c[f"inLH_{est_name}"] = wide[("in_interval", est_name)].astype(bool)
    c = c.reset_index()
    b = c[c["binding"]]
    counts = {f"d{d:g}/f{f:g}": {k: int(v) for k, v in g["class"].value_counts().sort_index().items()}
              for (d, f), g in c.groupby(["rel_delta", "f"], sort=True)}
    counts_binding = {f"d{d:g}": {k: int(v) for k, v in g["class"].value_counts().sort_index().items()}
                      for d, g in b.groupby("rel_delta", sort=True)}
    per_class = {f"d{d:g}/{k}": {e: _q(g[f"err_{e}"]) for e in ("bigm_relax", "perspective", "fixed")}
                 for (d, k), g in b.groupby(["rel_delta", "class"], sort=True)}
    p1, p2 = b[b["class"] == "P1"], b[b["class"] == "P2"]
    inlh = b[b["inLH_fixed"]]
    pred = {"P1": {"n": len(p1), "tol": P1_TOL, "max_err": float(p1["err_fixed"].max()) if len(p1) else np.nan,
                   "misses": p1.loc[p1["err_fixed"] > P1_TOL, "id"].tolist()},
            "P2": {"n": len(p2), "tol": P2_TOL, "max_err": float(p2["err_fixed"].max()) if len(p2) else np.nan,
                   "misses": p2.loc[p2["err_fixed"] > P2_TOL, "id"].tolist()},
            "P3": {"n": int((b["class"] == "P3").sum()),
                   "fixed_err": _q(b.loc[b["class"] == "P3", "err_fixed"])},
            "fixed_in_LH_in_P1_or_P2": {
                f"d{d:g}": {"n": len(g), "n_expected_by_note": N_FIXED_IN_LH[d],
                            "in_P1_or_P2": int(g["class"].isin(["P1", "P2"]).sum()),
                            "misses": g.loc[~g["class"].isin(["P1", "P2"]), "id"].tolist()}
                for d, g in inlh.groupby("rel_delta", sort=True)}}
    main = _rows(b, b["rel_delta"] == 0.10, "item 3 binding at δ = 10%")
    gap_bigm = (main["U_bigm_relax"] - main["V"]) / main["V"].abs()
    gap_persp = (main["persp_V"] - main["V"]) / main["V"].abs()
    sp = {"n": len(main), "bigm_relax": S.spearman(gap_bigm, main["err_bigm_relax"]),
          "perspective": S.spearman(gap_persp, main["err_perspective"]),
          "gap_bigm": _q(gap_bigm), "gap_perspective": _q(gap_persp)}
    nb = c[~c["binding"]]
    rec = {"recompute": {"rows": len(sup), "max_V_rel_diff": float(sup["V_rel_diff"].max()),
                         "max_w_abs_diff": float(sup["w_max_abs_diff"].max()),
                         "support_mismatch": int((sup["support"] != sup["support_recomputed"]).sum()),
                         "max_mu_fixed_rel_diff_at_b": float(
                             ((sup["mu_fixed"] - sup["mu_fixed_stored"]).abs()
                              / sup["mu_fixed_stored"].abs().where(sup["mu_fixed_stored"] != 0))[sup["point"] == "b"].max())},
           "n_cases": len(c), "n_binding": len(b), "counts_by_delta_f": counts,
           "counts_binding_by_delta": counts_binding, "errors_per_class_binding": per_class,
           "predictions": pred, "spearman_delta10": sp,
           "nonbinding": {"n": len(nb), "classes": {k: int(v) for k, v in nb["class"].value_counts().items()},
                          "max_abs_mu_fixed": float(nb["mu_fixed"].abs().max()) if len(nb) else np.nan}}
    return rec, c


def _require_ids(ids, present, what: str) -> None:
    """Raise if any id has no stored rows (a missing id must not read as an empty support or
    zero hedged names; S4 step 0b)."""
    missing = sorted(set(ids) - set(present))
    if missing:
        raise ValueError(f"{what}: no stored rows for {len(missing)} id(s): {missing[:10]}")


def item4(pts: pd.DataFrame, wts: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    _require_ids(pts["id"], wts["id"], "item 4 weights")
    out, rows = {}, []
    for inst, g in pts.sort_values("bound").groupby("instance", sort=True):
        Be = A.b_eff(g["B"], g["V"])
        t = S.grid_nonconcavity(g["bound"], g["V"], Be).assign(instance=inst)
        sup = [S.support_signature(wts.loc[wts["id"] == i].sort_values("i")["w"]) for i in g["id"]]
        sets = [set(filter(None, s.split(";"))) for s in sup]
        ch = [len(sets[k] ^ sets[k - 1]) for k in range(1, len(sets))]
        rows.append(t)
        out[inst] = {"n_points": len(g), "n_triples": len(t), "certified_nonconcave": int(t["certified"].sum()),
                     "uncertified_nonconcave": int(t["uncertified"].sum()),
                     "certified_bounds": t.loc[t["certified"], "bound"].round(10).tolist(),
                     "neighbour_pairs": len(ch), "support_changes": int(sum(x > 0 for x in ch)),
                     "names_changed_per_change": _q([x for x in ch if x > 0])}
    return out, pd.concat(rows, ignore_index=True)


def item5(legs: pd.DataFrame, names: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    _require_ids(legs["id"], names["id"], "item 5 names")
    hs = []
    for _, r in legs.sort_values("id").iterrows():
        n = names[names["id"] == r["id"]].sort_values("i")
        h = S.hedged_names(n["wp"], n["wm"], n["zp"], n["zm"], r["ell"])
        d = n["d"].to_numpy()[h["i"].to_numpy()] if len(h) else np.array([])
        hs.append(h.assign(id=r["id"], source=r["source"], d=d,
                           two_lam_d_ell=2 * r["lam_star"] * d * r["ell"],
                           c_plus_2kappa=r["borrow_monthly"] + 2 * r["trade_cost"]))
    H = pd.concat(hs, ignore_index=True)
    ratio = H["two_lam_d_ell"] / H["c_plus_2kappa"]
    by = {i: int(v) for i, v in H.groupby("id").size().items()}
    return {"relaxations": len(legs), "failed": int((~legs["ok"].astype(bool)).sum()),
            "max_abs_value_minus_ref": float(legs["value_minus_ref"].abs().max()),
            "n_with_hedged": int((legs["n_hedged"] > 0).sum()), "hedged_names": len(H),
            "hedged_by_instance": by,
            "prediction_holds": int(H["prediction_holds"].sum()),
            "prediction_misses": H.loc[~H["prediction_holds"], ["id", "i", "net", "zeta"]].to_dict("records"),
            "net_below_ell": int(H["net_below_ell"].sum()),
            "zeta_above_net_over_ell": int(H["zeta_above_net_over_ell"].sum()),
            "max_min_leg": float(H["min_leg"].max()) if len(H) else 0.0,
            "two_lam_d_ell_over_c_plus_2kappa": _q(ratio),
            "n_two_lam_d_ell_above_c_plus_2kappa": int((ratio > 1).sum())}, H


def item6(i1: dict, i2: dict) -> dict:
    zcols = lambda df: sorted(c for c in df.columns if c in ("zp", "zm") or c.startswith("z_"))
    return {"i1_solves_z_columns": zcols(i1["i1_solves"]), "i2_solves_z_columns": zcols(i2["i2_solves"]),
            "i1_weights_columns": sorted(i1["i1_weights"].columns),
            "i2_weights_columns": sorted(i2["i2_weights"].columns),
            "both_arms_z_stored": False,
            "v_tie": {"i1": f"{int(i1['i1_points']['v_tie'].sum())}/{len(i1['i1_points'])}",
                      "i2": f"{int(i2['i2_points']['v_tie'].sum())}/{len(i2['i2_points'])}"},
            "note": "only V's polished weights are stored per point (one vector, the supplier's); "
                    "no rerun (GATE I item 6): the report says only that the polished values were identical"}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    X, sx = _load(latest_done("k29b_ext"))
    R, sr = _load(latest_done("s3b"))
    cfg = run_meta(ROOT / sr["run"])["config"]
    I1, si1 = _load(cfg["i1_run"])
    I2, si2 = _load(latest_done("i2"))
    s3a = ROOT / "results" / "s3_analysis" / "s3_analysis.json"
    res = {"item2_k29b_ext": item2(X["k29b_ext"], I1["i1_estimators"])}
    res["item3_support"], cls = item3(R["s3b_support"], I1["i1_estimators"])
    res["item4_i2_grid"], tri = item4(I2["i2_points"], I2["i2_weights"])
    res["item5_hedged_legs"], H = item5(R["s3b_legs"], R["s3b_leg_names"])
    res["item6_v_ties"] = item6(I1, I2)
    res["item7_presolve_N250"] = json.loads(s3a.read_text())["n1"]["presolve_N250"]
    res["sources"] = {"k29b_ext": sx, "s3b": sr, "i1": si1, "i2": si2,
                      "s3_analysis_json": {"path": str(s3a.relative_to(ROOT)), "sha256": file_sha256(s3a)}}
    for name, df in (("item3_cases", cls), ("item4_i2_triples", tri), ("item5_hedged_names", H)):
        df.to_csv(OUT / f"{name}.csv", index=False, float_format="%.10g")
    (OUT / "s3b_analysis.json").write_text(dumps(res) + "\n")
    print(dumps(res["sources"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
