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

Status (DESIGN §6). A solve counts as failed (ok = False, no result) only if Clarabel's status is
neither "Solved" (CVXPY optimal) nor "AlmostSolved" (optimal_inaccurate), a CVXPY SolverError
occurs, or a relative residual exceeds RESIDUAL_MAX = 1e-8. The residuals are Clarabel's own
(r_prim = ‖Ax + s − b‖/max(1, ‖b‖ + ‖x‖ + ‖s‖), r_dual = ‖Px + Aᵀz + q‖/max(1, ‖q‖ + ‖x‖ + ‖z‖),
Clarabel.rs 0.11.1 info.rs), in the rescaled problem solved here. AlmostSolved is counted
separately by the caller. Clarabel's final status, iterations, residuals, primal and dual
objectives and their gap are recorded for every solve (CHECKS K29b); gap_rel is
|p − d|/max(|p|, |d|) in Clarabel's (scaled, minimization) objective. The duals returned are
Clarabel's raw duals, a diagnostic (the perspective estimator is a finite difference of values).
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


@dataclass
class ClarabelRelaxation:
    ok: bool
    status: str                          # CVXPY status: optimal, optimal_inaccurate, or the failure
    info: dict = field(default_factory=dict)
    result: MIQPResult | None = None     # U in model units (× s_obj); w in fractions of AUM


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


def perspective_relaxation(model: MIQPModel, opts: dict | None = None) -> ClarabelRelaxation:
    """The perspective relaxation of `model` at its current bounds (module docstring)."""
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
    info = {"clarabel_status": raw["status"], "iterations": raw["iterations"],
            "r_prim": raw["r_prim"], "r_dual": raw["r_dual"], "obj_primal": p, "obj_dual": d,
            "gap_abs": abs(p - d), "gap_rel": abs(p - d) / max(abs(p), abs(d), 1e-300),
            "solve_time": raw["solve_time"], "w_scale": c, "tol": opts.get("tol_gap_abs")}
    status = raw["cvxpy_status"]
    if status not in ACCEPTED:
        return ClarabelRelaxation(ok=False, status=f"clarabel relax status {raw['status']} "
                                  f"({status})", info=info)
    if not (raw["r_prim"] <= RESIDUAL_MAX and raw["r_dual"] <= RESIDUAL_MAX):
        return ClarabelRelaxation(ok=False, status=f"clarabel relax residual above {RESIDUAL_MAX:g} "
                                  f"(r_prim {raw['r_prim']:.2e}, r_dual {raw['r_dual']:.2e}; "
                                  f"{raw['status']})", info=info)
    duals = {}
    for key, con in rows.items():
        k = 1.0 if key[0] == "cardinality" else c
        duals[key] = -np.atleast_1d(np.asarray(con.dual_value, float)) / k
    wv = c * (np.asarray(wp.value, float) - np.asarray(wm.value, float))
    res = MIQPResult(U=float(prob.value), bound=float(prob.value), w=wv,
                     zp=np.asarray(zp.value, float), zm=np.asarray(zm.value, float),
                     status=-1, status_name=status, runtime=raw["solve_time"], nodes=0.0,
                     final_gap=0.0, root_gap=0.0, reached_gap=True, duals=duals)
    return ClarabelRelaxation(ok=True, status=status, info=info, result=res)
