"""S1 core verification run (CHECKS CORE K4-K13): `uv run python -m experiments.run_core`.

Recomputes, at a clean commit, the solutions the S1 tests check and stores them as raw outputs
in results/core/run_<UTC>/ (weights, duals, λ*, A*, closed forms, finite-difference slopes, the
consistency chain, the independent checker's verdict on every solution), with the run's own
summary of each criterion. The result-checker recomputes from these files and the stored inputs;
the summary is the runner's claim, not the verdict. No number here is reported.

CHECKS as revised 2026-10-19 (a74fb78): K8 and K9 gate the perspective relaxation's optimal value
(its slope method is gated by K29c before I1); Clarabel's raw perspective duals, statuses and
residuals are stored as a diagnostic. K9 runs the fixed toys T1 and T2 and a seeded random family
(src.opt.toy.random_toys; seed in core.yaml). Every P-MI solve adds a row to pmi_solves with the
signed discrepancies B − V and U_incumbent − V (DESIGN §6, A9). K10 stores the raw-B and the
B_eff intervals (DESIGN §6) for the toy and for two small MIQPs.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from experiments.common import fail, finish, open_run
from experiments.designs import config, month_end
from experiments.instances import miqp_mandate, pmi_instance, restricted, subsample
from experiments.sweep import C2_GRIDS, apply_point, build, sweep_date
from src.alpha.decompose import alignment_share, alpha_set, decompose, sigma_solve
from src.alpha.momentum import momentum_alpha
from src.opt.attribution import shadow_prices, transfer_coefficient
from src.opt.certified import certified_interval, certified_interval_eff
from src.opt.closed_form import IDEALIZED, equality_case, idealized_mandate
from src.opt.continuous import ContinuousProblem, Mandate, load_config
from src.opt.feasibility import pmi_violations, prb_violations
from src.opt.integer import PMI, choose_s_obj, exact_objective
from src.opt.inputs import date_inputs, market_data
from src.opt.risk_budget import SIGMA_M, solve_qcqp, solve_risk_budget
from src.opt.sensitivity import BINDING_ELASTICITY, bound_value, elasticities, fd_slope_rb
from src.opt.toy import Toy, random_toys
from src.risk.factor_model import FACTORS
from tests.test_opt import random_instance

CONFIG = "experiments/configs/core.yaml"
OFF = dict(dollar=None, beta=None, style=None, sector=None, gross=None, position=None,
           liquidity_theta=None, borrow_annual=0.0, trade_cost=0.0)


def _rel_err(est: pd.Series, cf: pd.Series, scale: pd.Series) -> pd.Series:
    """|est − cf|/|cf|, read against scale where the closed form is 0."""
    return (est - cf).abs() / cf.abs().where(cf != 0, scale)


def _k9_err(k9: pd.DataFrame, mu: str, cf: str) -> float:
    """Max |μ̂ − μ|/|μ| over non-kink points (|μ̂|/a where the closed form is 0); nan if none."""
    r = k9[~k9["kink"]]
    return float(_rel_err(r[mu], r[cf], r["a"]).max()) if len(r) else float("nan")


def _k9_summary(k9: pd.DataFrame) -> dict:
    """The runner's K9 claims on a subset of toys (CHECKS K9, revised 2026-10-19)."""
    est = k9[~k9["kink"]]
    raw = _rel_err(est["mu_persp_raw"], est["cf_persp"], est["a"])
    st = est["clarabel_status"]
    undefined = k9[k9["V_bigm"].isna() | k9["V_perspective"].isna()]
    return {
        "n_toys": int(k9["toy"].nunique()), "n_value_points": len(k9),
        # V undefined (exact polish infeasible; DESIGN §6): counted and listed, never dropped
        "n_V_undefined": {f: int(k9[f"V_{f}"].isna().sum()) for f in ("bigm", "perspective")},
        "V_undefined_points": undefined[["toy", "b", "ell_minus_b", "v_source_bigm",
                                         "v_source_perspective"]].to_dict("records"),
        "n_fixed_failed": int((est["fixed_status"] != "OPTIMAL").sum()),
        "max_abs_value_err_defined": float(max((k9[f"V_{f}"] - k9["U_cf"]).abs().max()
                                               for f in ("bigm", "perspective"))),
        "max_rel_err_R_persp": float(_rel_err(k9["R_persp"], k9["R_persp_cf"], k9["value_scale"]).max()),
        "max_rel_err_R_bigm": float(_rel_err(k9["R_bigm"], k9["R_bigm_cf"], k9["value_scale"]).max()),
        "n_persp_failed": int((~k9["persp_ok"]).sum()),
        "clarabel_status_counts": {str(k): int(v) for k, v in k9["clarabel_status"].value_counts().items()},
        "max_r_prim": float(k9["r_prim"].max()), "max_r_dual": float(k9["r_dual"].max()),
        "n_estimator_points": len(est),
        "max_rel_err_bigm": _k9_err(k9, "mu_bigm", "cf_bigm"),
        "max_rel_err_fixed": _k9_err(k9, "mu_fixed", "cf_fixed"),
        "diagnostic_persp_raw_dual": {
            "max_rel_err": float(raw.max()), "n_above_1e-6": int((raw > 1e-6).sum()),
            "max_rel_err_solved": float(raw[st == "Solved"].max()),
            "max_rel_err_almost_solved": float(raw[st == "AlmostSolved"].max())}}


def _solve_row(out: dict, case: str, r) -> None:
    """One pmi_solves row per P-MI solve: V, B, the incumbent, and the signed discrepancies B − V
    and U_incumbent − V in original units and relative to |V| (DESIGN §6, A9)."""
    rel = (lambda x: x / abs(r.V)) if np.isfinite(r.V) and r.V != 0 else (lambda x: np.nan)
    out["pmi_solves"].append({
        "case": case, "formulation": r.formulation, "s_obj": r.s_obj, "status": r.status_name,
        "v_source": r.v_source, "V": r.V, "B": r.B, "U_incumbent": r.U_incumbent, "U_raw": r.U_raw,
        "B_minus_V": r.B_minus_V, "incumbent_minus_V": r.incumbent_minus_V,
        "B_minus_V_rel": rel(r.B_minus_V), "incumbent_minus_V_rel": rel(r.incumbent_minus_V),
        "flag_incumbent_exceeds_polished": r.flag_incumbent_exceeds_polished,
        "flag_polished_exceeds_bound": r.flag_polished_exceeds_bound})


def _quantiles(x: pd.Series) -> dict:
    x = x.dropna()
    q = x.quantile([0.0, 0.01, 0.5, 0.99, 1.0]) if len(x) else pd.Series(dtype=float)
    return {"n": len(x), **{f"q{int(100 * k)}": float(v) for k, v in q.items()}}


def _case(ym):
    di = date_inputs(month_end(ym))
    return di, momentum_alpha(di.model, market_data().ret)


def _prob(di, mandate):
    m = di.model
    return ContinuousProblem(m.B, m.F, m.d, di.sector_matrix(), mandate, adv=di.adv,
                             factor_names=FACTORS)


def _toy_pmi(T: Toy, b: float, formulation: str = "perspective") -> PMI:
    """The A7 toy as a P-MI: one asset, the gross row as the bound b, K = 1 (as in the tests)."""
    m = Mandate(dollar=None, beta=None, style=None, sector=None, gross=b, position=T.u,
                liquidity_theta=None, borrow_annual=0.0, trade_cost=0.0)
    return PMI(np.zeros((1, len(FACTORS))), np.eye(len(FACTORS)) * 1e-4, np.array([T.d]),
               np.ones((1, 1)), np.array([T.a]), T.lam, m, None, K=1, ell=T.ell,
               formulation=formulation, s_obj=choose_s_obj(T.value(T.w_opt)), factor_names=FACTORS)


def _scale_ratio(mu_ref: float, mu: float, b: float, value: float) -> float:
    """|μ − μ_ref| / (1e-6·max(|μ_ref|, 1e-4·|value|/|b|)); ≤ 1 meets K8's 1e-6 relative (a
    non-binding dual, elasticity < 1e-4, read against the bindingness threshold)."""
    return abs(mu - mu_ref) / (1e-6 * max(abs(mu_ref), 1e-4 * abs(value) / abs(b)))


def _pmi_scale(case: str, kwargs: dict, out: dict, gated: bool, s_obj: float | None = None) -> dict:
    """P-MI at s_obj = 1 and at s_obj (default: the DESIGN §6 rule from |V| at s = 1), both to
    MIPGap 0: z, w, round trip, and the scaling of every dual of the three estimators (rows in
    out["k8_duals"]). Returns the summary row, with the two PMIResults under _r1 and _r2."""
    M1 = PMI(**kwargs, s_obj=1.0)
    r1 = M1.solve(mip_gap=0.0)
    s = choose_s_obj(r1.V) if s_obj is None else s_obj
    M2 = PMI(**kwargs, s_obj=s)
    r2 = M2.solve(mip_gap=0.0)
    est = {"fixed": (M1.fixed_integer_duals(r1.zp, r1.zm), M2.fixed_integer_duals(r2.zp, r2.zm))}
    rl1, rl2 = M1.relaxation_duals(), M2.relaxation_duals()
    est.update({f: (rl1[f], rl2[f]) for f in ("bigm", "perspective")})
    rec = {"case": case, "gated": gated, "s_obj": s,
           "z_equal": bool(np.array_equal(r1.zp, r2.zp) and np.array_equal(r1.zm, r2.zm)),
           "max_abs_dw": float(np.abs(r2.w - r1.w).max()),
           "dw_l1_rel": float(np.abs(r2.w - r1.w).sum() / np.abs(r1.w).sum()),
           "A_rel_diff": abs(r2.V / r1.V - 1), "V_s1": r1.V, "V_s": r2.V,
           "status_raw": r1.status_name, "status_scaled": r2.status_name,
           "flags_s1": f"{r1.flag_incumbent_exceeds_polished},{r1.flag_polished_exceeds_bound}",
           "flags_s": f"{r2.flag_incumbent_exceeds_polished},{r2.flag_polished_exceeds_bound}",
           "persp_status_s1": rl1["perspective"]["status"], "persp_status_s": rl2["perspective"]["status"],
           "persp_almost_solved": int(rl1["perspective"]["almost_solved"]) + int(rl2["perspective"]["almost_solved"]),
           "persp_ok_s1": rl1["perspective"]["ok"], "persp_ok_s": rl2["perspective"]["ok"],
           "persp_U_s1": rl1["perspective"]["U"], "persp_U_clarabel_s": rl2["perspective"]["U"],
           "persp_U_rel_diff": abs(rl2["perspective"]["U"] / rl1["perspective"]["U"] - 1),
           "persp_U_gurobi_barrier_s": rl2["perspective"]["U_gurobi_barrier"],
           "persp_U_rel_vs_barrier_s": abs(rl2["perspective"]["U"] / rl2["perspective"]["U_gurobi_barrier"] - 1),
           "_r1": r1, "_r2": r2}
    _solve_row(out, f"{case} s=1", r1)
    _solve_row(out, f"{case} s={s:g}", r2)
    for name, (a, b) in est.items():
        ratios = {}
        for k, mu1 in a["shadow"].items():
            bk = M1.bound_of(k)
            ratios[k] = _scale_ratio(mu1, b["shadow"][k], bk, r1.V)
            out["k8_duals"].append({"case": case, "estimator": name, "key": k, "bound": bk,
                                    "dual_gated": bool(gated and name != "perspective"),
                                    "value_unscaled": r1.V, "mu_unscaled": mu1,
                                    "mu_scaled": b["shadow"][k], "raw_scaled": b["raw_shadow"][k],
                                    "s_obj": s, "ratio": ratios[k]})
        rec[f"dual_ratio_{name}"] = max(ratios.values()) if ratios else float("nan")
        rec[f"ok_{name}"] = bool(a["ok"] and b["ok"])
    for tag, rl in (("s1", rl1), ("s", rl2)):
        info = rl["perspective"]["clarabel"]
        rec.update({f"clarabel_{k}_{tag}": info.get(k) for k in
                    ("clarabel_status", "iterations", "r_prim", "r_dual", "gap_abs", "gap_rel", "w_scale")})
    return rec


def main() -> int:
    run = None
    try:
        cfg = config("core")
        base, _ = load_config(cfg["mandate_config"])
        run, meta = open_run("core", CONFIG, status="ok")
        out: dict[str, list] = {k: [] for k in ("k4", "k4_weights", "k4_duals", "k5", "k6",
                                                "k6_weights", "k7", "k8", "k8_duals", "k8_weights",
                                                "k9", "k9_toys", "k10", "k10_mip", "k11", "k12",
                                                "k13", "pmi_solves")}
        extra = []
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

        # K8 (P-RB): Clarabel unscaled (s = 1, risk row ‖x‖ ≤ σ_m) vs scaled (normalized, s_obj)
        for ym in cfg["k8_months"]:
            di, alpha = _case(ym)
            P = _prob(di, base)
            raw = solve_qcqp(P, alpha, normalize=False, obj_scale=1.0)
            s = choose_s_obj(raw.objective)
            sc = solve_qcqp(P, alpha, normalize=True, obj_scale=s)
            ds = f"{di.date:%Y-%m-%d}"
            sp_raw, sp_sc = shadow_prices(P, raw), shadow_prices(P, sc)
            ratio = {k: _scale_ratio(v, sp_sc[k], bound_value(P, k), raw.objective)
                     for k, v in sp_raw.items()}
            out["k8"].append({"case": f"P-RB {ds}", "gated": True, "s_obj": s,
                              "max_abs_dw": float(np.abs(sc.w - raw.w).max()),
                              "dw_l1_rel": float(np.abs(sc.w - raw.w).sum() / np.abs(raw.w).sum()),
                              "A_rel_diff": abs(sc.objective / raw.objective - 1),
                              "lam_rel_diff": abs(sc.lam / raw.lam - 1),
                              "dual_ratio_family": max(v for k, v in ratio.items() if ":" not in k),
                              "dual_ratio_all": max(ratio.values()),
                              "status_raw": raw.status, "status_scaled": sc.status})
            out["k8_duals"] += [{"case": f"P-RB {ds}", "estimator": "prb_clarabel", "key": k,
                                 "bound": bound_value(P, k), "value_unscaled": raw.objective,
                                 "mu_unscaled": v, "mu_scaled": sp_sc[k], "s_obj": s,
                                 "dual_gated": False, "ratio": ratio[k]} for k, v in sp_raw.items()]

        # K8 (P-MI), gated: two real-data instances fixed in advance (core.yaml)
        for ym in cfg["k8_pmi_months"]:
            inst = pmi_instance(month_end(ym), cfg["k8_pmi_N"], cfg["k8_pmi_f"])
            ds = f"{inst.date:%Y-%m-%d}"
            case = f"P-MI {ds} top{inst.N}"
            rec = _pmi_scale(case, inst.kwargs, out, gated=True)
            r1, r2 = rec.pop("_r1"), rec.pop("_r2")
            rec.update(N=inst.N, K=inst.K, S_support=inst.S_support, lam_star=inst.lam,
                       risk_binding=inst.risk_binding)
            out["k8"].append(rec)
            out["k8_weights"] += [{"case": case, "ticker": tk, "w_s1": a, "w_s": b_,
                                   "zp_s1": zp1, "zm_s1": zm1, "zp_s": zp2, "zm_s": zm2}
                                  for tk, a, b_, zp1, zm1, zp2, zm2 in
                                  zip(inst.tickers, r1.w, r2.w, r1.zp, r1.zm, r2.zp, r2.zm)]
            feas.append({"source": f"k8 {case} s=1", "violations": json.dumps(
                pmi_violations(r1.w, r1.zp, r1.zm, inst.B, inst.S, inst.mandate, inst.K,
                               inst.ell, inst.adv))})

        # K8 (P-MI), diagnostic only: the degenerate synthetic instance (n = 20, u = 20%)
        B, F, d, S, adv, a = random_instance(n=20, seed=cfg["k8_pmi_seed"])
        mk = Mandate(dollar=0.02, beta=0.05, style=0.10, sector=0.05, gross=2.0, position=0.2,
                     liquidity_theta=None)
        np.savez(run / "k8_pmi_instance.npz", B=B, F=F, d=d, S=S, adv=adv, alpha=a)   # raw inputs
        extra.append(run / "k8_pmi_instance.npz")
        case = f"P-MI synthetic n=20 seed {cfg['k8_pmi_seed']}"
        rec = _pmi_scale(case, dict(B=B, F=F, d=d, S=S, alpha=a, lam=2.0, mandate=mk, adv=adv,
                                    K=8, ell=0.01, factor_names=FACTORS), out, gated=False,
                         s_obj=1000.0)
        r1 = rec.pop("_r1")
        rec.pop("_r2")
        out["k8"].append(rec)
        feas.append({"source": "k8 P-MI synthetic s=1", "violations": json.dumps(
            pmi_violations(r1.w, r1.zp, r1.zm, B, S, mk, 8, 0.01, adv))})

        # K9: one-asset toys (A7) on 41-point grids, the fixed toys T1, T2 and a seeded random
        # family: the MIQP value function (both formulations); the relaxation values at every
        # point, kinks included (perspective by Clarabel, big-M by dual simplex); the big-M and
        # fixed-integer duals off the kinks; Clarabel's raw perspective duals, statuses and
        # residuals as a diagnostic
        toys = [(name, "fixed", Toy(**{k: tp[k] for k in ("a", "lam", "d", "ell", "u")}), tp["b_max"])
                for name, tp in cfg["k9_toys"].items()]
        toys += [(f"R{i:03d}", "random", T, bm) for i, (T, bm) in
                 enumerate(random_toys(cfg["k9_random_seed"], cfg["k9_random_n"]))]
        for name, family, T, b_max in toys:
            out["k9_toys"].append({"toy": name, "family": family, "a": T.a, "lam": T.lam, "d": T.d,
                                   "ell": T.ell, "u": T.u, "w_opt": T.w_opt, "b_max": b_max,
                                   "seed": cfg["k9_random_seed"] if family == "random" else -1})
            kinks = (0.0, T.ell, T.w_opt, T.u)
            for b in np.linspace(0.0, b_max, 41):
                kink = min(abs(b - k) for k in kinks) <= 1e-12
                row = {"toy": name, "family": family, "a": T.a, "b": float(b), "kink": kink,
                       "U_cf": T.value(b), "value_scale": T.value(T.w_opt),
                       "s_obj": choose_s_obj(T.value(T.w_opt)),
                       "R_persp_cf": T.relaxation_value(b, "perspective"),
                       "R_bigm_cf": T.relaxation_value(b, "bigm")}
                row["ell_minus_b"] = T.ell - float(b)
                for form in ("bigm", "perspective"):
                    r = _toy_pmi(T, b, form).solve(mip_gap=0.0)
                    row[f"V_{form}"], row[f"v_source_{form}"] = r.V, r.v_source
                    _solve_row(out, f"k9 {name} b={b:.9g}", r)
                M = _toy_pmi(T, b)
                rl = M.relaxation_duals()
                pr, info = rl["perspective"], rl["perspective"]["clarabel"]
                row.update(R_persp=pr["U"], R_bigm=rl["bigm"]["U"], persp_ok=pr["ok"],
                           persp_status=pr["status"], clarabel_status=info.get("clarabel_status"),
                           r_prim=info.get("r_prim"), r_dual=info.get("r_dual"),
                           gap_rel=info.get("gap_rel"), iterations=info.get("iterations"),
                           U_gurobi_barrier=pr["U_gurobi_barrier"],
                           mu_persp_raw=pr["shadow"].get("gross", np.nan))
                if not kink:
                    cf = T.slopes(b)
                    inc = M.solve(mip_gap=0.0)
                    try:                    # a failed fixed-integer QP is recorded, not fatal
                        mu_fixed = M.fixed_integer_duals(inc.zp, inc.zm)["shadow"]["gross"]
                        fixed_status = "OPTIMAL"
                    except RuntimeError as err:
                        mu_fixed, fixed_status = np.nan, str(err)
                    row.update(mu_bigm=rl["bigm"]["shadow"]["gross"], mu_fixed=mu_fixed,
                               fixed_status=fixed_status, cf_bigm=cf["bigm"],
                               cf_persp=cf["perspective"], cf_fixed=cf["fixed"])
                out["k9"].append(row)

        # K10 (toy part): certified intervals on T1 against the closed-form secant
        T = Toy(**{k: cfg["k9_toys"]["T1"][k] for k in ("a", "lam", "d", "ell", "u")})
        dl = cfg["k10_toy_delta"]
        for b in cfg["k10_toy_points"]:
            sol = {sg: _toy_pmi(T, b + sg * dl).solve(mip_gap=0.0) for sg in (+1, -1)}
            for sg in (+1, -1):
                _solve_row(out, f"k10 T1 b={b + sg * dl:.9g}", sol[sg])
            ci = certified_interval(sol[1].V, sol[1].B, sol[-1].V, sol[-1].B, dl)
            ce = certified_interval_eff(sol[1].V, sol[1].B, sol[-1].V, sol[-1].B, dl)
            out["k10"].append({"toy": "T1", "b": b, "delta": dl, "V_plus": sol[1].V,
                               "B_plus": sol[1].B, "V_minus": sol[-1].V, "B_minus": sol[-1].B,
                               "L_raw": ci.L, "H_raw": ci.H, "L": ce.L, "H": ce.H, "s": ce.s,
                               "exact_secant": T.secant(b, dl), "solver_error": ce.solver_error,
                               "solver_error_raw": ci.solver_error})

        # K10 (MIQP part): two small MIQPs (as tests/test_certified.py), beta bound b0 ± δ, both
        # formulations, MIPGap 0; raw inputs stored (hashed) for an independent exact solve
        b0 = 0.01
        dm = 0.1 * b0
        for seed in cfg["k10_mip_seeds"]:
            B_, F_, d_, S_, adv_, a_ = random_instance(n=24, seed=seed)
            fn = run / f"k10_mip_seed{seed}.npz"
            np.savez(fn, B=B_, F=F_, d=d_, S=S_, adv=adv_, alpha=a_)
            extra.append(fn)
            for form in ("bigm", "perspective"):
                sol = {}
                for sg in (+1, -1):
                    md = Mandate(dollar=0.02, beta=b0 + sg * dm, style=0.05, sector=0.05, gross=2.0,
                                 position=0.2, liquidity_theta=None)
                    sol[sg] = PMI(B_, F_, d_, S_, a_, 2.0, md, adv_, K=8, ell=0.01, formulation=form,
                                  factor_names=FACTORS).solve(mip_gap=0.0)
                    _solve_row(out, f"k10 seed{seed} {form} beta={b0 + sg * dm:g}", sol[sg])
                ci = certified_interval(sol[1].V, sol[1].B, sol[-1].V, sol[-1].B, dm)
                ce = certified_interval_eff(sol[1].V, sol[1].B, sol[-1].V, sol[-1].B, dm)
                out["k10_mip"].append({"seed": seed, "n": 24, "formulation": form, "key": "beta",
                                       "b": b0, "delta": dm, "lam": 2.0, "K": 8, "ell": 0.01,
                                       "V_plus": sol[1].V, "B_plus": sol[1].B, "V_minus": sol[-1].V,
                                       "B_minus": sol[-1].B, "L_raw": ci.L, "H_raw": ci.H,
                                       "L": ce.L, "H": ce.H, "s": ce.s,
                                       "solver_error": ce.solver_error,
                                       "status_plus": sol[1].status_name, "status_minus": sol[-1].status_name})

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
                _solve_row(out, f"k13 {di.date:%Y-%m-%d} {form}", r)
                out["k13"].append({"date": f"{di.date:%Y-%m-%d}", "N": len(idx), "formulation": form,
                                   "lam_star": rb.lam, "risk_binding": rb.risk_binding,
                                   "V_pmi": r.V, "U_mv": mv.objective, "A_rb": rb.A,
                                   "A_pmi": exact_objective(r.w, alpha, 0.0, B, F, d, md),
                                   "w_rel_l2_err": float(np.linalg.norm(r.w - rb.sol.w) / np.linalg.norm(rb.sol.w)),
                                   "status": r.status_name, "v_source": r.v_source,
                                   "U_incumbent": r.U_incumbent, "B": r.B,
                                   "flag_incumbent_exceeds_polished": r.flag_incumbent_exceeds_polished,
                                   "flag_polished_exceeds_bound": r.flag_polished_exceeds_bound})
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
            "K9": {"random_seed": cfg["k9_random_seed"],
                   **{fam: _k9_summary(frames["k9"][frames["k9"]["family"].isin(sel)])
                      for fam, sel in (("all", ("fixed", "random")), ("fixed", ("fixed",)),
                                       ("random", ("random",)))}},
            "K10_toy": {"n": len(frames["k10"]),
                        "all_contain_eff": bool(((frames["k10"]["L"] <= frames["k10"]["exact_secant"])
                                                 & (frames["k10"]["exact_secant"] <= frames["k10"]["H"])).all()),
                        "all_contain_raw": bool(((frames["k10"]["L_raw"] <= frames["k10"]["exact_secant"])
                                                 & (frames["k10"]["exact_secant"] <= frames["k10"]["H_raw"])).all()),
                        "any_solver_error": bool(frames["k10"]["solver_error"].any())},
            "K10_mip": {"n": len(frames["k10_mip"]),
                        "any_solver_error": bool(frames["k10_mip"]["solver_error"].any()),
                        "min_H": float(frames["k10_mip"]["H"].min())},
            "pmi_solves": {"n": len(frames["pmi_solves"]),
                           "B_minus_V_rel": _quantiles(frames["pmi_solves"]["B_minus_V_rel"]),
                           "incumbent_minus_V_rel": _quantiles(frames["pmi_solves"]["incumbent_minus_V_rel"]),
                           "B_minus_V_abs_where_V0": _quantiles(frames["pmi_solves"].loc[
                               frames["pmi_solves"]["V"] == 0, "B_minus_V"]),
                           "n_flag_incumbent": int(frames["pmi_solves"]["flag_incumbent_exceeds_polished"].sum()),
                           "n_flag_bound": int(frames["pmi_solves"]["flag_polished_exceeds_bound"].sum())},
            "AlmostSolved": {"k4_qcqp": int((frames["k4"]["qcqp_status"] == "optimal_inaccurate").sum()),
                             "k8_prb": int(((frames["k8"]["status_raw"] == "optimal_inaccurate")
                                            | (frames["k8"]["status_scaled"] == "optimal_inaccurate")).sum())},
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
            f"{k} n={len(v)}" for k, v in frames.items()), extra_files=extra)
        print(json.dumps(summary, indent=1, default=float))
    except Exception as e:
        fail(run, CONFIG, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
