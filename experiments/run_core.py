"""S1 core verification run (CHECKS CORE K4-K13): `uv run python -m experiments.run_core`.

Recomputes, at a clean commit, the solutions the S1 tests check and stores them as raw outputs
in results/core/run_<UTC>/ (weights, duals, λ*, A*, closed forms, finite-difference slopes, the
consistency chain, the independent checker's verdict on every solution), with the run's own
summary of each criterion. The result-checker recomputes from these files and the stored inputs;
the summary is the runner's claim, not the verdict. No number here is reported.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from experiments.common import fail, finish, open_run
from experiments.designs import config, month_end
from experiments.instances import miqp_mandate, restricted, subsample
from experiments.sweep import C2_GRIDS, apply_point, build, sweep_date
from src.alpha.decompose import alignment_share, alpha_set, decompose, sigma_solve
from src.alpha.momentum import momentum_alpha
from src.opt.attribution import shadow_prices, transfer_coefficient
from src.opt.closed_form import IDEALIZED, equality_case, idealized_mandate
from src.opt.continuous import ContinuousProblem, Mandate, load_config
from src.opt.feasibility import pmi_violations, prb_violations
from src.opt.integer import PMI, choose_s_obj, exact_objective
from src.opt.inputs import date_inputs, market_data
from src.opt.risk_budget import SIGMA_M, solve_qcqp, solve_risk_budget
from src.opt.sensitivity import BINDING_ELASTICITY, elasticities, fd_slope_rb
from src.risk.factor_model import FACTORS

CONFIG = "experiments/configs/core.yaml"
OFF = dict(dollar=None, beta=None, style=None, sector=None, gross=None, position=None,
           liquidity_theta=None, borrow_annual=0.0, trade_cost=0.0)


def _case(ym):
    di = date_inputs(month_end(ym))
    return di, momentum_alpha(di.model, market_data().ret)


def _prob(di, mandate):
    m = di.model
    return ContinuousProblem(m.B, m.F, m.d, di.sector_matrix(), mandate, adv=di.adv,
                             factor_names=FACTORS)


def main() -> int:
    run = None
    try:
        cfg = config("core")
        base, _ = load_config(cfg["mandate_config"])
        run, meta = open_run("core", CONFIG, status="ok")
        out: dict[str, list] = {k: [] for k in ("k4", "k4_weights", "k4_duals", "k5", "k6",
                                                "k6_weights", "k7", "k8", "k11", "k12", "k13")}
        feas = out["k11"]

        # K4: root-found QP vs Clarabel SOC at base
        for ym in cfg["k4_months"]:
            di, alpha = _case(ym)
            P = _prob(di, base)
            rb, q = solve_risk_budget(P, alpha), solve_qcqp(P, alpha)
            ds = f"{di.date:%Y-%m-%d}"
            out["k4"].append({"date": ds, "N": P.N, "A_qp": rb.A, "A_qcqp": q.objective,
                              "lam_qp": rb.lam, "mu_risk_qcqp": q.lam, "vol_ann_qp": rb.vol_ann,
                              "risk_binding": rb.risk_binding, "n_solves": rb.n_solves,
                              "qcqp_status": q.status,
                              "dw_l1_rel": float(np.abs(q.w - rb.sol.w).sum() / np.abs(rb.sol.w).sum())})
            out["k4_weights"] += [{"date": ds, "ticker": t, "w_qp": a, "w_qcqp": b}
                                  for t, a, b in zip(di.tickers, rb.sol.w, q.w)]
            sq, sc = shadow_prices(P, rb.sol), shadow_prices(P, q)
            e = elasticities(P, sq, rb.A)
            out["k4_duals"] += [{"date": ds, "key": k, "sp_qp": v, "sp_qcqp": sc[k], "e_qp": e[k]}
                                for k, v in sq.items()]
            feas.append({"source": f"k4 P-RB {ds}", "violations": json.dumps(
                prb_violations(rb.sol.w, P.B, P.F, P.d, P.S, base, SIGMA_M, P.adv))})

        # K5: decomposition; α⊥ under the risk budget alone, then with factor bounds
        for ym in cfg["k5_months"]:
            di, alpha = _case(ym)
            m = di.model
            perp, par = decompose(alpha, m.B, m.d)
            BtDi = m.B.T / m.d
            q = lambda x: float(x @ sigma_solve(m.B, m.F, m.d, x))
            perp_n = alpha_set(alpha, m.B, m.F, m.d)["alphas"]["perp"]
            P0 = _prob(di, Mandate(**OFF))
            rb0 = solve_risk_budget(P0, perp_n)
            Pf = _prob(di, Mandate(**{**OFF, "beta": 0.05, "style": 0.10}))
            rbf = solve_risk_budget(Pf, perp_n)
            ef = elasticities(Pf, shadow_prices(Pf, rbf.sol), rbf.A)
            keys = ["beta", *[f"style:{n}" for n in Pf.style_names]]
            out["k5"].append({
                "date": f"{di.date:%Y-%m-%d}", "phi": alignment_share(alpha, m.B, m.F, m.d),
                "BtDinv_perp_rel": float(np.linalg.norm(BtDi @ perp) / np.linalg.norm(BtDi @ alpha)),
                "split_max_abs_err": float(np.abs(perp + par - alpha).max()),
                "split_scale": float(max(np.abs(alpha).max(), np.abs(perp).max(), np.abs(par).max())),
                "identity_rel_err": abs(q(alpha) - (float(perp @ (perp / m.d)) + q(par))) / q(alpha),
                "max_abs_y_perp_risk_only": float(np.abs(P0.exposures(rb0.sol.w)).max()),
                "max_factor_elasticity_perp": float(max(abs(ef[k]) for k in keys))})

        # K6: idealized equality mandates vs closed form
        for ym in cfg["k6_months"]:
            di, alpha = _case(ym)
            m = di.model
            ds = f"{di.date:%Y-%m-%d}"
            unc = solve_risk_budget(_prob(di, Mandate(**OFF)), alpha)
            phi = alignment_share(alpha, m.B, m.F, m.d)
            for name in IDEALIZED:
                md = idealized_mandate(name)
                P = _prob(di, md)
                rb = solve_risk_budget(P, alpha)
                A = m.B.T if name == "factor" else np.vstack([m.B.T, np.ones(m.N)])
                cf = equality_case(alpha, m.B, m.F, m.d, A, SIGMA_M)
                out["k6"].append({"date": ds, "mandate": name, "phi": phi, "A_num": rb.A,
                                  "A_cf": cf["A"], "A_unc_num": unc.A,
                                  "A_unc_cf": cf["A_unconstrained"], "lam_num": rb.lam, "mu_cf": cf["mu"],
                                  "w_rel_l2_err": float(np.linalg.norm(rb.sol.w - cf["w"]) / np.linalg.norm(cf["w"])),
                                  "tc_num": transfer_coefficient(P, alpha, rb.sol.w),
                                  "retained_num": rb.A / unc.A, "retained_cf": cf["retained"],
                                  "sqrt_1_minus_phi": float(np.sqrt(1 - phi))})
                out["k6_weights"] += [{"date": ds, "mandate": name, "ticker": t, "w_num": a, "w_cf": b}
                                      for t, a, b in zip(di.tickers, rb.sol.w, cf["w"])]

        # K7: envelope at base, δ = 1% of the bound
        for ym in cfg["k7_months"]:
            di, alpha = _case(ym)
            P = _prob(di, base)
            rb = solve_risk_budget(P, alpha)
            sp = shadow_prices(P, rb.sol)
            e = elasticities(P, sp, rb.A)
            for k in [k for k in sp if e[k] >= BINDING_ELASTICITY]:
                fd = fd_slope_rb(P, alpha, k, rel_step=cfg["k7_rel_step"], lam_guess=rb.lam)
                out["k7"].append({"date": f"{di.date:%Y-%m-%d}", "key": k, "mu": sp[k], "e": e[k],
                                  "fd_slope": fd, "rel_err": abs(fd / sp[k] - 1)})

        # K8: Clarabel scaled vs unscaled (P-RB); P-MI s_obj = 1 vs 1000 (small instance)
        for ym in cfg["k8_months"]:
            di, alpha = _case(ym)
            P = _prob(di, base)
            raw = solve_qcqp(P, alpha, normalize=False, obj_scale=1.0)
            s = choose_s_obj(raw.objective)
            sc = solve_qcqp(P, alpha, normalize=True, obj_scale=s)
            out["k8"].append({"case": f"P-RB {di.date:%Y-%m-%d}", "s_obj": s,
                              "max_abs_dw": float(np.abs(sc.w - raw.w).max()),
                              "A_rel_diff": abs(sc.objective / raw.objective - 1),
                              "lam_rel_diff": abs(sc.lam / raw.lam - 1),
                              "status_raw": raw.status, "status_scaled": sc.status})
        from tests.test_opt import random_instance
        B, F, d, S, adv, a = random_instance(n=20, seed=cfg["k8_pmi_seed"])
        mk = Mandate(dollar=0.02, beta=0.05, style=0.10, sector=0.05, gross=2.0, position=0.2,
                     liquidity_theta=None)
        np.savez(run / "k8_pmi_instance.npz", B=B, F=F, d=d, S=S, adv=adv, alpha=a)   # raw inputs
        res = {}
        for s in (1.0, 1000.0):
            M = PMI(B, F, d, S, a, 2.0, mk, adv, K=8, ell=0.01, s_obj=s, factor_names=FACTORS)
            r = M.solve(mip_gap=0.0)
            res[s] = (r, M.fixed_integer_duals(r.zp, r.zm), M.relaxation_duals()["bigm"])
        (r1, f1, b1), (r2, f2, b2) = res[1.0], res[1000.0]
        dual_err = max([abs(f2["shadow"][k] - v) / max(abs(v), 1e-12) for k, v in f1["shadow"].items()
                        if abs(v) > 1e-12] + [abs(b2["shadow"][k] - v) / max(abs(v), 1e-12)
                                             for k, v in b1["shadow"].items() if abs(v) > 1e-12])
        out["k8"].append({"case": "P-MI random n=20 seed 63", "s_obj": 1000.0,
                          "max_abs_dw": float(np.abs(r2.w - r1.w).max()),
                          "A_rel_diff": abs(r2.V / r1.V - 1), "lam_rel_diff": float("nan"),
                          "status_raw": r1.status_name, "status_scaled": r2.status_name,
                          "z_equal": bool(np.array_equal(r1.zp, r2.zp) and np.array_equal(r1.zm, r2.zm)),
                          "max_rel_dual_err_simplex": float(dual_err)})
        feas.append({"source": "k8 P-MI s=1", "violations": json.dumps(
            pmi_violations(r1.w, r1.zp, r1.zm, B, S, mk, 8, 0.01, adv))})

        # K12: swept caps; recorded shadow prices vs FD at each binding swept point
        di, alpha = _case(cfg["k12_month"])
        pts, _ = sweep_date(di, alpha, "mom", base, C2_GRIDS, families={"position", "liquidity"})
        for _, r in pts[~pts["off"] & ~pts["is_base"]].iterrows():
            sp = r[f"sp_{r['family']}"]
            fd = np.nan
            if sp > 1e-7:
                P = build(di, base)["base"]
                apply_point(P, base, r["family"], r["value"])
                fd = fd_slope_rb(P, alpha, r["family"], rel_step=cfg["k12_rel_step"],
                                 lam_guess=solve_risk_budget(P, alpha).lam)
            out["k12"].append({"point_id": r["point_id"], "family": r["family"], "value": r["value"],
                               "sp_recorded": sp, "fd_slope": fd, "lam": r["lam"], "A": r["A"],
                               "rel_err": abs(fd / sp - 1) if sp > 1e-7 else np.nan})
            feas.append({"source": f"k12 {r['point_id']}", "violations": r["feasibility_violations"]})

        # K13: P-MI (K ≥ N, ℓ = 0) = mean-variance at λ* = P-RB at u = 6%
        for ym in cfg["k13_months"]:
            di, alpha_full, idx = subsample(month_end(ym), cfg["k13_N"])
            B, F, d, S, adv, _ = restricted(di, idx)
            alpha = alpha_full[idx]
            md = miqp_mandate(base)
            P = ContinuousProblem(B, F, d, S, md, adv=adv, factor_names=FACTORS)
            rb = solve_risk_budget(P, alpha)
            mv = P.solve(alpha, lam=rb.lam)
            for form in ("bigm", "perspective"):
                r = PMI(B, F, d, S, alpha, rb.lam, md, adv, K=len(idx), ell=0.0, formulation=form,
                        factor_names=FACTORS).solve(mip_gap=0.0)
                out["k13"].append({"date": f"{di.date:%Y-%m-%d}", "N": len(idx), "formulation": form,
                                   "lam_star": rb.lam, "risk_binding": rb.risk_binding,
                                   "V_pmi": r.V, "U_mv": mv.objective, "A_rb": rb.A,
                                   "A_pmi": exact_objective(r.w, alpha, 0.0, B, F, d, md),
                                   "w_rel_l2_err": float(np.linalg.norm(r.w - rb.sol.w) / np.linalg.norm(rb.sol.w)),
                                   "status": r.status_name})
                feas.append({"source": f"k13 P-MI {form} {di.date:%Y-%m-%d}", "violations": json.dumps(
                    pmi_violations(r.w, r.zp, r.zm, B, S, md, len(idx), 0.0, adv))})
            feas.append({"source": f"k13 P-RB {di.date:%Y-%m-%d}", "violations": json.dumps(
                prb_violations(rb.sol.w, B, F, d, S, md, SIGMA_M, adv))})

        frames = {k: pd.DataFrame(v) for k, v in out.items()}
        summary = {
            "K4": {"max_dw_l1_rel": frames["k4"]["dw_l1_rel"].max(),
                   "max_A_rel": (frames["k4"]["A_qcqp"] / frames["k4"]["A_qp"] - 1).abs().max(),
                   "max_lam_rel": (frames["k4"]["mu_risk_qcqp"] / frames["k4"]["lam_qp"] - 1).abs().max(),
                   "max_vol_rel": (frames["k4"]["vol_ann_qp"] / 0.03 - 1).abs().max()},
            "K5": frames["k5"].drop(columns=["date"]).max().to_dict(),
            "K6": {"max_A_rel": ((frames["k6"]["A_num"] / frames["k6"]["A_cf"]) - 1).abs().max(),
                   "max_w_rel": frames["k6"]["w_rel_l2_err"].max(),
                   "max_tc_vs_retained": ((frames["k6"]["tc_num"] / frames["k6"]["retained_num"]) - 1).abs().max()},
            "K7": {"n": len(frames["k7"]), "max_rel_err": frames["k7"]["rel_err"].max()},
            "K8": frames["k8"].to_dict("records"),
            "K11": {"n_solutions": len(frames["k11"]),
                    "n_with_violations": int((frames["k11"]["violations"] != "{}").sum())},
            "K12": {"n_checked": int(frames["k12"]["rel_err"].notna().sum()),
                    "max_rel_err": frames["k12"]["rel_err"].max()},
            "K13": {"max_V_vs_mv_rel": (frames["k13"]["V_pmi"] / frames["k13"]["U_mv"] - 1).abs().max(),
                    "max_A_rel": (frames["k13"]["A_pmi"] / frames["k13"]["A_rb"] - 1).abs().max(),
                    "max_w_rel": frames["k13"]["w_rel_l2_err"].max()},
        }
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        finish(run, CONFIG, frames, "core verification: " + "; ".join(
            f"{k} n={len(v)}" for k, v in frames.items()))
        print(json.dumps(summary, indent=1, default=float))
    except Exception as e:
        fail(run, CONFIG, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
