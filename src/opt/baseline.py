"""The I1/I2 continuous baseline (d) (DESIGN §7: "the same constraint in the continuous problem
(ℓ = 0, no K), dual versus slope"). S2d item 4: both readings are options; which one I1/I2 use is
Decision 35 (GATE DESIGN), and K27's δ is Decision 36, so nothing here is a default.

- kind "fixed_lambda": the kept mean-variance QP (src.opt.continuous, dual simplex at 1e-9) at the
  instance's λ* held fixed across b, on P-MI's universe and mandate with u = 6% and no integer
  parts; the value is U(b), in P-MI's units.
- kind "risk_budget": P-RB at u = 6%, λ re-root-found at every b (src.opt.risk_budget, warm-started
  at lam_guess); the value is A*(b), net alpha at 3%/yr.
At the base bound with the risk row binding the two are the same solution with the same duals
(the K13 chain: λ* is P-RB's μ_risk); away from it fixed λ lets risk float, P-RB holds it at 3%.

baseline_point returns, for one shadow-price key (src.opt.attribution.shadow_prices):
- the dual μ = dV/db at b;
- the slope by K15's rule (src.opt.sensitivity.envelope_point): a central difference at δ = 1% of
  b, flagged as a kink if the key's dual is 0 at b + δ or b − δ or the forward and backward
  differences differ by more than KINK_RTOL = 1% of the central one, and then rechecked at
  δ = 0.1%; the error |slope − μ| is read relative to max(|μ|, 1e-4·|V|/b) (the bindingness scale,
  so a zero dual is compared against the elasticity threshold) and is within if ≤ tol = 1%;
- the secant (V(b + δ) − V(b − δ))/(2δ) at each of secant_rels (I1's δ = 10%; 5% robustness).
baseline_value(b) is one solve at bound b (b = 0 allowed: the I2 sweep starts there): value, the
key's dual, λ, the risk flag and the weights. The problem's bounds are restored afterwards.
"""
from __future__ import annotations

import numpy as np

from src.opt.attribution import shadow_prices
from src.opt.continuous import ContinuousProblem
from src.opt.risk_budget import solve_risk_budget
from src.opt.sensitivity import (BINDING_ELASTICITY, KINK_RTOL, bound_value, restore,
                                 set_bound_by_key, snapshot)

KINDS = ("fixed_lambda", "risk_budget")


def _evaluator(problem: ContinuousProblem, alpha, kind: str, lam: float | None,
               lam_guess: float | None):
    """() ↦ (V, shadow prices, λ used, risk_binding, ann. vol, w) at the problem's current bounds."""
    if kind not in KINDS:
        raise ValueError(f"kind {kind!r} not in {KINDS}")
    if kind == "fixed_lambda":
        if lam is None or not (np.isfinite(lam) and lam > 0):
            raise ValueError("fixed_lambda needs the instance's λ* (lam)")

        def ev():
            s = problem.solve(alpha, lam=lam)
            return (s.objective, shadow_prices(problem, s), float(lam), None, problem.ann_vol(s.w),
                    s.w)
    else:
        def ev():
            r = solve_risk_budget(problem, alpha, lam_guess=lam_guess)
            return r.A, shadow_prices(problem, r.sol), r.lam, r.risk_binding, r.vol_ann, r.sol.w
    return ev


def baseline_value(problem: ContinuousProblem, alpha, key: str, b: float, kind: str,
                   lam: float | None = None, lam_guess: float | None = None) -> dict:
    """One baseline solve with the bound behind `key` at b (module docstring)."""
    ev = _evaluator(problem, alpha, kind, lam, lam_guess)
    snap = snapshot(problem)
    set_bound_by_key(problem, key, b)
    try:
        V, sp, lm, rbind, vol, w = ev()
    finally:
        restore(problem, snap)
    return {"key": key, "kind": kind, "b": float(b), "value": V, "mu": float(sp[key]), "lam": lm,
            "risk_binding": rbind, "vol_ann": vol, "w": np.asarray(w, float)}


def baseline_point(problem: ContinuousProblem, alpha, key: str, kind: str,
                   lam: float | None = None, lam_guess: float | None = None,
                   rel_step: float = 0.01, fine_step: float = 0.001, tol: float = 0.01,
                   secant_rels=(0.10,)) -> dict:
    """The baseline's dual, K15-rule slope and secants for `key` at the current bound (module
    docstring)."""
    ev = _evaluator(problem, alpha, kind, lam, lam_guess)
    b0 = bound_value(problem, key)
    if not (np.isfinite(b0) and b0 > 0):
        raise ValueError(f"no relative step for {key}: bound {b0}")
    snap = snapshot(problem)

    def at(b: float):
        set_bound_by_key(problem, key, b)
        try:
            V, sp, lm, rbind, vol, _ = ev()
            return V, float(sp[key]), lm, rbind, vol
        finally:
            restore(problem, snap)

    try:
        V, mu, lam_used, rbind, vol = at(b0)
        h = rel_step * b0
        (Vp, mp, *_), (Vm, mm, *_) = at(b0 + h), at(b0 - h)
        fwd, bwd, ctr = (Vp - V) / h, (V - Vm) / h, (Vp - Vm) / (2.0 * h)
        kink = bool(mp == 0 or mm == 0 or abs(fwd - bwd) > KINK_RTOL * abs(ctr))
        scale = max(abs(mu), BINDING_ELASTICITY * abs(V) / b0)
        out = {"key": key, "kind": kind, "b": b0, "value": V, "mu": mu, "lam": lam_used,
               "risk_binding": rbind, "vol_ann": vol, "step": h, "value_plus": Vp,
               "value_minus": Vm, "mu_plus": mp, "mu_minus": mm, "fwd": fwd, "bwd": bwd,
               "ctr_coarse": ctr, "rel_err_coarse": abs(ctr - mu) / scale, "kink": kink,
               "fine_step": np.nan, "ctr_fine": np.nan, "rel_err_fine": np.nan,
               "err_scale": scale}
        if kink:
            hf = fine_step * b0
            (Vpf, *_), (Vmf, *_) = at(b0 + hf), at(b0 - hf)
            cf = (Vpf - Vmf) / (2.0 * hf)
            out.update(fine_step=hf, ctr_fine=cf, rel_err_fine=abs(cf - mu) / scale)
        out["slope"] = out["ctr_fine"] if kink else ctr
        out["rel_err"] = out["rel_err_fine"] if kink else out["rel_err_coarse"]
        out["step_checked"] = out["fine_step"] if kink else h
        out["within"] = bool(out["rel_err"] <= tol)
        secants = {}
        for rel in secant_rels:
            d = rel * b0
            (Vps, *_), (Vms, *_) = at(b0 + d), at(b0 - d)
            secants[rel] = {"delta": d, "value_plus": Vps, "value_minus": Vms,
                            "secant": (Vps - Vms) / (2.0 * d)}
        out["secants"] = secants
        return out
    finally:
        restore(problem, snap)
