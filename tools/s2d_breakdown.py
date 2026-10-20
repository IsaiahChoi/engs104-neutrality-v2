"""S2d: derived pilot diagnostics from results/pilot_s2d/run_20261020T045603Z (items 1-3), written to
results/pilot_s2d/s2d_breakdown_<run>.json for the PROGRESS S2d table. Read-only on the run."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]           # the repository


def q(x):
    x = pd.to_numeric(pd.Series(x), errors="coerce").dropna()
    return {"n": int(len(x)), "min": float(x.min()) if len(x) else None,
            "median": float(x.median()) if len(x) else None, "max": float(x.max()) if len(x) else None}


def main(run_rel: str) -> int:
    R = ROOT / run_rel
    out = {"run": run_rel}
    # item 1
    rg = pd.read_parquet(R / "rootgap.parquet")
    pl = pd.read_parquet(R / "rootgap_plain.parquet")
    pr = pd.read_parquet(R / "rootgap_probes.parquet")
    keys = ["gap_root_stored_bigm", "gap_root_stored_perspective", "gap_root_stored_perspective_rescaled",
            "gap_plain_bigm", "gap_plain_perspective", "a6_margin_plain", "a6_margin_root_stored",
            "cut_tightening_bigm", "gap_probe_first_bigm", "gap_probe_first_perspective",
            "first_minus_plain_perspective", "gap_probe_last_perspective_feastol1e-9",
            "gap_probe_last_perspective_miqcp0", "gap_probe_last_perspective_miqcp1",
            "gap_probe_last_perspective_feastol1e-9_miqcp0", "gap_probe_first_perspective_rescaled",
            "gap_probe_last_perspective_rescaled", "cone_effect_rel_perspective",
            "probe_last_vs_stored_bigm", "probe_last_vs_stored_perspective",
            "probe_last_vs_stored_perspective_rescaled"]
    d = rg.set_index("key")
    item1 = {k: q(d[k]) for k in keys}
    item1["a6_holds_plain"] = int(d["a6_holds_plain"].sum())
    item1["a6_holds_root_stored"] = int(d["a6_holds_root_stored"].sum())
    item1["n_instances"] = len(d)
    item1["stored_root_reproduced_exactly"] = int(sum((d[c] == 0).sum() for c in keys if c.startswith("probe_last_vs")))
    item1["persp_default_vs_miqcp1_last_equal"] = int((pr[pr.probe == "perspective"].set_index("key")["last"]
                                                     == pr[pr.probe == "perspective_miqcp1"].set_index("key")["last"]).sum())
    fe = d["gap_probe_last_perspective_feastol1e-9"] / d["gap_root_stored_perspective"]
    item1["feastol1e-9_over_default_root_gap"] = q(fe)
    item1["miqcp0_last_minus_plain_perspective"] = q(d["gap_probe_last_perspective_miqcp0"] - d["gap_plain_perspective"])
    item1["plain_perspective_statuses"] = pl["perspective_clarabel_status"].value_counts().to_dict()
    item1["gurobi_barrier_statuses"] = pl["perspective_gurobi_barrier_status"].value_counts().to_dict()
    item1["probe_n_passes_median"] = pr.groupby("probe")["n_passes"].median().to_dict()
    item1["per_instance"] = d[keys[:11]].to_dict("index")
    out["item1"] = item1
    # item 2, toys
    t = pd.read_parquet(R / "k29c_toys.parquet")
    t["region"] = np.where(t.b < t.ell, "below_ell", np.where(t.b < t.w_opt, "ell_to_wopt", "flat"))
    item2 = {}
    for s, g in t.groupby("s"):
        ok = g[g.ok]
        gi = ok[ok.interior]
        nf = gi[gi.region != "flat"]
        near = ok[~ok.interior]
        almost = nf.n_almost_solved > 0
        item2[f"{s:g}"] = {
            "n_points": len(g), "n_failed": int((~g.ok).sum()),
            "fail_reasons": g.loc[~g.ok, "fail_reason"].value_counts().to_dict(),
            "n_interior_nonflat": len(nf), "n_interior_flat": int((gi.region == "flat").sum()),
            "n_near_kink": len(near),
            "err_central_nonflat": q(nf.err_central),
            "n_err_central_nonflat_gt_1e-6": int((nf.err_central > 1e-6).sum()),
            "n_err_central_nonflat_gt_1e-6_almost_solved": int(((nf.err_central > 1e-6) & almost).sum()),
            "err_central_nonflat_solved_only": q(nf.loc[~almost, "err_central"]),
            "err_fwd3_nonflat": q(nf.err_fwd3), "err_bwd3_nonflat": q(nf.err_bwd3),
            "err_central_flat": q(gi.loc[gi.region == "flat", "err_central"]),
            "err_one_sided_near_kink": q(pd.concat([near.err_fwd3, near.err_bwd3])),
            "max_err_central_over_noise": float(((gi.slope_central - gi.cf_right).abs() / gi.noise_central).max()),
            "max_err_fwd3_over_noise": float(((ok.forward3 - ok.cf_right).abs() / ok.noise3)[ok.fwd_valid].max()),
            "max_err_bwd3_over_noise": float(((ok.backward3 - ok.cf_left).abs() / ok.noise3)[ok.bwd_valid].max()),
            "noise3_rel_nonflat": q(nf.noise3_rel), "noise3_rel_flat": q(gi.loc[gi.region == "flat", "noise3_rel"]),
            "kink3_nonflat_interior": int(nf.kink3.sum()), "kink2_nonflat_interior": int(nf.kink2.sum()),
            "kink3_flat": int(gi.loc[gi.region == "flat", "kink3"].sum()),
            "kink3_near_ell": int((ok.kink3 & ok.near.str.contains("ell")).sum()),
            "n_near_ell": int(ok.near.str.contains("ell").sum()),
            "concavity3_failures": int((~ok.concave3).sum()),
            "concavity3_failures_interior": int((~ok.concave3 & ok.interior).sum()),
            "concavity2_failures_beyond_noise": int(((ok.fwd2 - ok.bwd2) > 4 * ok.noise_central).sum()),
            "points_with_almost_solved": int((g.n_almost_solved > 0).sum())}
    out["item2_toys"] = item2
    k = pd.read_parquet(R / "k29c_k8.parquet")
    k = k[k.ok]
    k["binding"] = k.slope_central.abs() > 1e-4 * k.V.abs() / k.b
    k8 = {}
    for s, g in k[k.s > 1].groupby("s"):
        b, nb = g[g.binding], g[~g.binding]
        k8[f"{s:g}"] = {"n_binding": len(b), "n_nonbinding": len(nb),
                        "central_rel_diff_binding": q(b.slope_central_rel_diff_vs_s1),
                        "forward3_rel_diff_binding": q(b.forward3_rel_diff_vs_s1),
                        "backward3_rel_diff_binding": q(b.backward3_rel_diff_vs_s1),
                        "central_rel_diff_nonbinding": q(nb.slope_central_rel_diff_vs_s1),
                        "noise3_rel_binding": q(b.noise3_rel), "noise3_rel_nonbinding": q(nb.noise3_rel),
                        "raw_dual_rel_err_binding": q(b.raw_dual_rel_err),
                        "kink3_binding": int(b.kink3.sum()), "kink3_nonbinding": int(nb.kink3.sum())}
    k1 = k[k.s == 1]
    k8["1"] = {"raw_dual_rel_err_binding": q(k1.loc[k1.binding, "raw_dual_rel_err"]),
               "raw_dual_rel_err_nonbinding": q(k1.loc[~k1.binding, "raw_dual_rel_err"])}
    out["item2_k8"] = k8
    # item 3
    sc = pd.read_parquet(R / "clarabel_scale.parquet")
    out["item3"] = {f"{s:g}": {"statuses": g.clarabel_status.value_counts().to_dict(),
                               "n_failed": int((~g.ok).sum()), "r_prim": q(g.r_prim), "r_dual": q(g.r_dual),
                               "gap_abs_orig": q(g.gap_abs), "gap_abs_scaled": q(g.gap_abs_scaled),
                               "gap_rel": q(g.gap_rel), "abs_V_scaled": q(g.abs_V_scaled),
                               "rel_diff_vs_s1": q(g.rel_diff_vs_s1), "rel_diff_vs_s1e4": q(g.rel_diff_vs_s10000)}
                    for s, g in sc.groupby("s")}
    out["item3"]["max_pairwise_rel_diff"] = q(sc.drop_duplicates("inst").max_pairwise_rel_diff)
    out["item3"]["per_instance"] = sc.pivot(index="inst", columns="s", values="clarabel_status").to_dict("index")
    dst = ROOT / "results" / "pilot_s2d" / f"s2d_breakdown_{Path(run_rel).name}.json"
    dst.write_text(json.dumps(out, indent=1, default=float))
    print(dst.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "results/pilot_s2d/run_20261020T045603Z"))
