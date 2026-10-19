"""Perspective relaxation of P-MI in Clarabel (DESIGN §6, revised after CHECK CORE round 1).

The z ∈ [0, 1] relaxation of the perspective P-MI (src/opt/miqp.py) is an SOCP. Its value and
duals come from Clarabel (tolerances 1e-12), built from the MIQPModel's own data and current
bounds: the same α, λ and costs (already multiplied by s_obj there), the same variable bounds,
linking rows, one-sidedness, cardinality and mandate rows, and the rotated cones
v_i² ≤ s_i ζ_i, v = w⁺ − w⁻, ζ = z⁺ + z⁻.

Clarabel solves an equivalent rescaled problem (A9): weights w' = w/c with c the largest position
bound u_i over holdable names, and each cone in its name's bound, s_i = u_i²·s'_i, written as
‖(2v'_i/r_i, s'_i − ζ_i)‖ ≤ s'_i + ζ_i with r_i = u_i/c. A mandate row expr(w) ≤ b becomes
expr(w') ≤ b/c, so its dual is c·dU/db; the cardinality row is unchanged. Results are mapped
back: w = c·w', and duals are returned in Gurobi's convention for `expr <= b` in min(−U)
(Pi = −dU/db), so src.opt.miqp.shadow_price applies unchanged. Values stay in the model's units
(× s_obj); src.opt.integer divides by s_obj.

Value (DESIGN §6, Decision 21). The relaxation's value is the objective at Clarabel's returned
(w⁺, w⁻, ζ), mapped back to original units, with each s_i replaced by w_i²/ζ_i (cone_exact_s), so
every cone holds exactly; y = Bᵀw is recomputed from w. Clarabel's own objective (−p) is recorded
alongside, with CVXPY's value and the difference. (Clarabel's s can sit above w²/ζ by more than its
residuals and gap show: R043 in the CHECK CORE round-3 run.)

Status (DESIGN §6). A solve counts as failed (ok = False, no result) if Clarabel's status is
neither "Solved" (CVXPY optimal) nor "AlmostSolved" (optimal_inaccurate) or a CVXPY SolverError
occurs; if a relative residual exceeds RESIDUAL_MAX = 1e-8; or if the duality gap |p − d|
exceeds GAP_RTOL·max(|V|, |V_ref|) = 1e-9·max(|V|, |V_ref|), with V the value above and V_ref the
caller's reference value in model units (the toy's U*; for a finite-difference stencil, the value
at the unperturbed bound; None: |V| alone). The residuals are Clarabel's own
(r_prim = ‖Ax + s − b‖/max(1, ‖b‖ + ‖x‖ + ‖s‖), r_dual = ‖Px + Aᵀz + q‖/max(1, ‖q‖ + ‖x‖ + ‖z‖),
Clarabel.rs 0.11.1 info.rs), in the rescaled problem solved here; p and d are in model units
(the objective is not rescaled). A failure is recorded with its reason (fail_reason "status",
"residual" or "gap") and never raised; AlmostSolved is counted separately by the caller.
Recorded for every solve (CHECKS K29b, A9): Clarabel's status, iterations, residuals, p and d,
gap_abs = |p − d|, gap_rel = |p − d|/max(|p|, |d|) (the pure relative gap), clarabel_gap_rel =
|p − d|/max(1, min(|p|, |d|)) (Clarabel's own), the value, Clarabel's objective, their difference,
the gap threshold and V_ref. The duals returned are Clarabel's raw duals, a diagnostic (the
perspective estimator is a finite difference of values).
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import cvxpy as cp
import numpy as np

from src.opt.continuous import SOLVER_OPTS
from src.opt.miqp import MIQPModel, MIQPResult

ACCEPTED = (cp.OPTIMAL, cp.OPTIMAL_INACCURATE)
CLARABEL_OPTS = SOLVER_OPTS["CLARABEL"]          # tol_gap_abs = tol_gap_rel = tol_feas = 1e-12
RESIDUAL_MAX = 1e-8                               # DESIGN §6: larger relative residual = failed
GAP_RTOL = 1e-9                                   # DESIGN §6: gap above 1e-9·max(|V|, |V_ref|) = failed


@dataclass
class ClarabelRelaxation:
    ok: bool
    status: str                          # CVXPY status: optimal, optimal_inaccurate, or the failure
    info: dict = field(default_factory=dict)
    result: MIQPResult | None = None     # U in model units (× s_obj); w in fractions of AUM
    wp: np.ndarray | None = None         # Clarabel's returned point in original units (recorded
    wm: np.ndarray | None = None         # whenever the status is accepted, failed or not)
    s: np.ndarray | None = None          # cone_exact_s at that point


def cone_exact_s(v, zeta, ub) -> tuple[np.ndarray, int]:
    """DESIGN §6: s_i = v_i²/ζ_i, so each cone v_i² ≤ s_i·ζ_i holds with equality; s_i = 0 where
    v_i = 0. The linking row |v_i| ≤ u_i·ζ_i bounds s_i by u_i·|v_i|; where Clarabel's point breaks
    it (within its tolerance, or ζ_i ≤ 0) s_i is that bound. Computed as (|v_i|/ζ_i)·|v_i|, which
    does not underflow as ζ_i → 0. Returns s and the number of names held at the bound."""
    v, zeta, ub = (np.asarray(x, float) for x in (v, zeta, ub))
    av = np.abs(v)
    cap = ub * av
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        ratio = np.where(zeta > 0, (av / np.where(zeta > 0, zeta, 1.0)) * av, np.inf)
    held = av > 0
    return np.where(held, np.minimum(ratio, cap), 0.0), int((held & (ratio > cap)).sum())


def _solve(prob: cp.Problem, opts: dict) -> dict:
    """Solve through CVXPY's chain so Clarabel's raw solution (status, residuals) is kept."""
    data, chain, inverse = prob.get_problem_data(cp.CLARABEL, solver_opts=opts)
    with warnings.catch_warnings():          # "may be inaccurate": the status is recorded instead
        warnings.simplefilter("ignore", UserWarning)
        raw = chain.solve_via_data(prob, data, warm_start=False, verbose=False, solver_opts=opts)
        out = {"status": str(raw.status), "iterations": int(raw.iterations),
               "r_prim": float(raw.r_prim), "r_dual": float(raw.r_dual),
               "obj_primal": float(raw.obj_val), "obj_dual": float(raw.obj_val_dual),
               "solve_time": float(raw.solve_time)}
        try:
            prob.unpack_results(raw, chain, inverse)
            out["cvxpy_status"] = prob.status
        except cp.error.SolverError:
            out["cvxpy_status"] = cp.SOLVER_ERROR
    return out


def perspective_relaxation(model: MIQPModel, opts: dict | None = None,
                           v_ref: float | None = None) -> ClarabelRelaxation:
    """The perspective relaxation of `model` at its current bounds (module docstring); v_ref is the
    reference value of the gap clause, in model units (× s_obj)."""
    M, m, b = model, model.mandate, model.bounds
    opts = {**CLARABEL_OPTS, **(opts or {})}
    N = M.N
    ub = np.where(M.holdable, M.ub, 0.0)
    c = float(ub.max()) if ub.max() > 0 else 1.0
    r = np.where(ub > 0, ub / c, 1.0)
    zub = M.holdable.astype(float)
    wp, wm, zp, zm, s = (cp.Variable(N, nonneg=True) for _ in range(5))
    y = cp.Variable(M.nK)
    v, zeta = wp - wm, zp + zm
    # Gurobi's variable bounds w± ≤ u_i are implied by w± ≤ u_i z± and z± ≤ 1, so they are not
    # repeated as rows (a first draft did; see PROGRESS, CHECK CORE round 2)
    cons = [y == M.B.T @ v, zp <= zub, zm <= zub,
            wp <= cp.multiply(ub / c, zp), wm <= cp.multiply(ub / c, zm),
            zeta <= 1,
            cp.SOC(s + zeta, cp.vstack([2 * cp.multiply(1.0 / r, v), s - zeta]), axis=0)]
    if M.ell > 0:
        cons += [wp >= (M.ell / c) * zp, wm >= (M.ell / c) * zm]
    rows: dict[tuple[str, str], cp.Constraint] = {}
    if m.dollar is not None:
        rows[("dollar", "upper")] = cp.sum(v) <= b["dollar"] / c
        rows[("dollar", "lower")] = -cp.sum(v) <= b["dollar"] / c
    if m.beta is not None:
        rows[("beta", "upper")] = y[M.mkt] <= b["beta"] / c
        rows[("beta", "lower")] = -y[M.mkt] <= b["beta"] / c
    if m.style is not None:
        rows[("style", "upper")] = y[M.style_idx] <= np.asarray(b["style"], float) / c
        rows[("style", "lower")] = -y[M.style_idx] <= np.asarray(b["style"], float) / c
    if m.sector is not None:
        rows[("sector", "upper")] = M.S.T @ v <= np.asarray(b["sector"], float) / c
        rows[("sector", "lower")] = -(M.S.T @ v) <= np.asarray(b["sector"], float) / c
    if m.gross is not None:
        rows[("gross", "upper")] = cp.sum(wp + wm) <= b["gross"] / c
    if M.K is not None:
        rows[("cardinality", "upper")] = cp.sum(zeta) <= M.K
    LF = np.linalg.cholesky(M.F)
    U = (c * (M.alpha @ v) - M.lam * c * c * (cp.sum_squares(LF.T @ y) + (M.d * r * r) @ s)
         - c * m.borrow_monthly * cp.sum(wm) - c * m.trade_cost * cp.sum(wp + wm))
    prob = cp.Problem(cp.Maximize(U), cons + list(rows.values()))
    raw = _solve(prob, opts)
    p, d = raw["obj_primal"], raw["obj_dual"]
    gap = abs(p - d)
    nan = float("nan")
    info = {"clarabel_status": raw["status"], "iterations": raw["iterations"],
            "r_prim": raw["r_prim"], "r_dual": raw["r_dual"], "obj_primal": p, "obj_dual": d,
            "gap_abs": gap, "gap_rel": gap / max(abs(p), abs(d), 1e-300),
            "clarabel_gap_rel": gap / max(1.0, min(abs(p), abs(d))),
            "clarabel_objective": -p, "cvxpy_value": nan, "value": nan,
            "value_minus_clarabel": nan, "v_ref": v_ref, "gap_threshold": nan, "n_s_capped": -1,
            "fail_reason": None,
            "solve_time": raw["solve_time"], "w_scale": c, "tol": opts.get("tol_gap_abs")}
    status = raw["cvxpy_status"]
    if status not in ACCEPTED:
        info["fail_reason"] = "status"
        return ClarabelRelaxation(ok=False, status=f"clarabel relax status {raw['status']} "
                                  f"({status})", info=info)
    # the DESIGN §6 value: the objective at the returned point with every cone exact
    wpv, wmv = c * np.asarray(wp.value, float), c * np.asarray(wm.value, float)
    zpv, zmv = np.asarray(zp.value, float), np.asarray(zm.value, float)
    wv = wpv - wmv
    s_ex, n_cap = cone_exact_s(wv, zpv + zmv, ub)
    yv = M.B.T @ wv
    value = float(M.alpha @ wv - M.lam * (yv @ M.F @ yv + M.d @ s_ex)
                  - m.borrow_monthly * wmv.sum() - m.trade_cost * (wpv + wmv).sum())
    threshold = GAP_RTOL * max(abs(value), abs(v_ref) if v_ref is not None else 0.0)
    info.update(cvxpy_value=float(prob.value), value=value,
                value_minus_clarabel=value - info["clarabel_objective"],
                gap_threshold=threshold, n_s_capped=n_cap)
    point = dict(wp=wpv, wm=wmv, s=s_ex)
    if not (raw["r_prim"] <= RESIDUAL_MAX and raw["r_dual"] <= RESIDUAL_MAX):
        info["fail_reason"] = "residual"
        return ClarabelRelaxation(ok=False, status=f"clarabel relax residual above {RESIDUAL_MAX:g} "
                                  f"(r_prim {raw['r_prim']:.2e}, r_dual {raw['r_dual']:.2e}; "
                                  f"{raw['status']})", info=info, **point)
    if not gap <= threshold:
        info["fail_reason"] = "gap"
        return ClarabelRelaxation(ok=False, status=f"clarabel relax duality gap {gap:.2e} above "
                                  f"{GAP_RTOL:g}·max(|V|, |V_ref|) = {threshold:.2e} "
                                  f"({raw['status']})", info=info, **point)
    duals = {}
    for key, con in rows.items():
        k = 1.0 if key[0] == "cardinality" else c
        duals[key] = -np.atleast_1d(np.asarray(con.dual_value, float)) / k
    res = MIQPResult(U=value, bound=value, w=wv, zp=zpv, zm=zmv,
                     status=-1, status_name=status, runtime=raw["solve_time"], nodes=0.0,
                     final_gap=0.0, root_gap=0.0, reached_gap=True, duals=duals)
    return ClarabelRelaxation(ok=True, status=status, info=info, result=res, **point)
