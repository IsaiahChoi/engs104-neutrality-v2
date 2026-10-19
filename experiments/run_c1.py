"""C1, the base mandate (DESIGN §7): `make c1` → results/c1/run_<UTC>/.

D12, full universe, u = 3%, alphas α_mom, α⊥, α∥ (α⊥ and α∥ rescaled to α_mom's information
ratio, src.alpha.decompose.alpha_set). At each (date, alpha), P-RB at base by the root-found QP
(DESIGN §6) and recorded by experiments.sweep.record: A*, the risk-binding flag, ex-ante
volatility, gross, names held, TC, every shadow price and elasticity, and the independent
checker's verdict (CHECKS K14). Also:
- the unconstrained, costless P-RB (A2/A3's denominator) and the retained fraction A*/A*_unc;
- the Stubbs–Vandenbussche attribution at λ = μ_risk (src.opt.attribution): α'w* = α'w_α +
  Σ_c α'w_c, so the losses −α'w_c (including `inactive` and the KKT `residual`) sum to
  α'w_α − α'w* (CHECKS K18); the fixed-risk loss A*_unc − A* is stored beside it (Fig. 3);
- φ; the two idealized equality mandates of DESIGN §7 C1 ((i) all six exposures 0, (ii) plus
  dollar neutral; risk budget only, no costs), numerical against the closed form (A2–A4);
- for α_mom, the envelope check (CHECKS K15): every constraint with e_j ≥ 1e-4, central
  difference with δ = 1% of the bound against μ_j; a stencil that crosses an active-set change
  is flagged as a kink and checked at δ = 0.1% (Isaiah, 2026-10-19; src.opt.sensitivity.
  envelope_point), both slopes recorded.
Dates run in a process pool (continuous.yaml `workers`); each date is a chunk.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from experiments.common import fail, finish, open_run
from experiments.cont import check_p_rb, OFF, case, pool_chunks, problem
from experiments.designs import config
from experiments.sweep import record
from src.alpha.decompose import alpha_set
from src.opt.attribution import attribution, shadow_prices, transfer_coefficient
from src.opt.closed_form import IDEALIZED, equality_case, idealized_mandate
from src.opt.continuous import load_config
from src.opt.feasibility import prb_violations
from src.opt.risk_budget import SIGMA_M, solve_risk_budget
from src.opt.sensitivity import BINDING_ELASTICITY, elasticities, envelope_point

CONFIG = "experiments/configs/continuous.yaml"
KINDS = ("c1_points", "c1_weights", "c1_attribution", "c1_idealized", "c1_envelope")


def c1_date(ym: str) -> dict[str, pd.DataFrame]:
    cfg = config("continuous")
    base, _ = load_config(cfg["mandate_config"])
    di, alpha_mom = case(ym)
    m = di.model
    ds = f"{di.date:%Y-%m-%d}"
    aset = alpha_set(alpha_mom, m.B, m.F, m.d)
    P, P0 = problem(di, base), problem(di, OFF)
    out = {k: [] for k in KINDS}
    for kind, a in aset["alphas"].items():
        rb = solve_risk_budget(P, a)
        ids = {"point_id": f"{ds}|Nfull|{kind}|base", "date": ds, "alpha": kind, "family": "base",
               "value": np.nan, "off": False, "is_base": True, "N": P.N, "n_label": "full"}
        row, w = record(P, rb, a, ids, di.tickers)
        unc = solve_risk_budget(P0, a)
        att = attribution(P, rb.sol)
        costs = float(a @ rb.sol.w) - rb.lam * P.variance(rb.sol.w) - rb.sol.objective
        row.update(phi=aset["phi"][kind], A_unc=unc.A, lam_unc=unc.lam,
                   unc_risk_binding=unc.risk_binding, retained=rb.A / unc.A,
                   alpha_ideal=att["alpha_ideal"], alpha_total=att["alpha_total"],
                   attribution_total_loss=att["alpha_ideal"] - att["alpha_total"],
                   fixed_risk_loss=unc.A - rb.A, costs=costs,
                   attribution_recon_error=att["reconstruction_error"],
                   kkt_residual_max=float(np.abs(att["adjustments"]["residual"]).max()),
                   unc_violations=json.dumps(prb_violations(unc.sol.w, P0.B, P0.F, P0.d, P0.S,
                                                            OFF, SIGMA_M, P0.adv)))
        out["c1_points"].append(row)
        out["c1_weights"].append(w.assign(alpha=kind, date=ds))
        out["c1_attribution"] += [{"date": ds, "alpha": kind, "family": f, "alpha_contribution": v,
                                   "loss": -v} for f, v in att["alpha_by_family"].items()]
        for name in IDEALIZED:
            Pi = problem(di, idealized_mandate(name))
            rbi = solve_risk_budget(Pi, a)
            A = m.B.T if name == "factor" else np.vstack([m.B.T, np.ones(m.N)])
            cf = equality_case(a, m.B, m.F, m.d, A, SIGMA_M)
            out["c1_idealized"].append({
                "date": ds, "alpha": kind, "mandate": name, "phi": aset["phi"][kind],
                "A_num": rbi.A, "A_cf": cf["A"], "A_unc_num": unc.A, "A_unc_cf": cf["A_unconstrained"],
                "retained_num": rbi.A / unc.A, "retained_cf": cf["retained"],
                "sqrt_1_minus_phi": float(np.sqrt(1 - aset["phi"][kind])),
                "lam_num": rbi.lam, "mu_cf": cf["mu"], "risk_binding": rbi.risk_binding,
                "tc_num": transfer_coefficient(Pi, a, rbi.sol.w), "tc_cf": cf["tc"],
                "w_rel_l2_err": float(np.linalg.norm(rbi.sol.w - cf["w"]) / np.linalg.norm(cf["w"])),
                "max_abs_exposure": float(np.abs(Pi.exposures(rbi.sol.w)).max()),
                "net": float(rbi.sol.w.sum()),
                "violations": json.dumps(prb_violations(rbi.sol.w, Pi.B, Pi.F, Pi.d, Pi.S,
                                                        idealized_mandate(name), SIGMA_M, Pi.adv))})
        if kind == "mom":
            sp = shadow_prices(P, rb.sol)
            e = elasticities(P, sp, rb.A)
            for k in [k for k in sp if e[k] >= BINDING_ELASTICITY]:
                r = envelope_point(P, a, k, sp[k], rb.A, rel_step=cfg["envelope_rel_step"],
                                   fine_step=cfg["envelope_fine_step"], lam_guess=rb.lam)
                out["c1_envelope"].append({"date": ds, "e": e[k], **r})
    return {k: (pd.concat(v, ignore_index=True) if k == "c1_weights" else pd.DataFrame(v))
            for k, v in out.items()}


def main() -> int:
    run = None
    try:
        cfg = config("continuous")
        check_p_rb(cfg)
        run, _ = open_run("c1", CONFIG, status="ok")
        fr = pool_chunks(run, KINDS, cfg["d12"], lambda ym: ym, c1_date, int(cfg["workers"]))
        pts, ide, env = fr["c1_points"], fr["c1_idealized"], fr["c1_envelope"]
        summary = {
            "n_points": len(pts), "n_not_optimal": int((pts["status"] != "optimal").sum()),
            "n_with_violations": int((pts["feasibility_violations"] != "{}").sum()),
            "n_not_risk_binding": int((~pts["risk_binding"]).sum()),
            "not_risk_binding": pts.loc[~pts["risk_binding"], ["date", "alpha"]].to_dict("records"),
            "envelope": {"n": len(env), "n_kink": int(env["kink"].sum()),
                         "kinks": env.loc[env["kink"], ["date", "key", "rel_err_coarse",
                                                        "rel_err_fine"]].to_dict("records"),
                         "max_rel_err": float(env["rel_err"].max()),
                         "max_rel_err_coarse": float(env["rel_err_coarse"].max()),
                         "n_above_1pct": int((~env["within"]).sum())},
            "idealized": {"max_A_rel_where_cf_nonzero": float(
                              (ide["A_num"] / ide["A_cf"] - 1)[ide["A_cf"].abs() > 1e-12].abs().max()),
                          "max_A_abs_where_cf_zero": float(
                              (ide["A_num"] - ide["A_cf"])[ide["A_cf"].abs() <= 1e-12].abs().max()),
                          "max_retained_abs": float((ide["retained_num"] - ide["retained_cf"]).abs().max()),
                          "max_factor_vs_sqrt": float((ide.loc[ide["mandate"] == "factor", "retained_cf"]
                                                       - ide.loc[ide["mandate"] == "factor", "sqrt_1_minus_phi"]).abs().max())},
            "attribution_identity_max_abs": float((pts["attribution_total_loss"]
                                                   - (pts["alpha_ideal"] - pts["alpha_total"])).abs().max()),
            "phi_range": {k: [float(g["phi"].min()), float(g["phi"].max())] for k, g in pts.groupby("alpha")},
        }
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        finish(run, CONFIG, fr, f"C1: {len(pts)} points, envelope max rel err "
               f"{summary['envelope']['max_rel_err']:.2e}")
        print(json.dumps(summary, indent=1, default=float))
    except Exception as e:
        fail(run, CONFIG, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
