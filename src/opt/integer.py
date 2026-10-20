"""P-MI (DESIGN §3.4, §6) on top of the kept MIQP model (src/opt/miqp.py).

- Objective scaling. The model is built with α, λ, the borrow cost c and the trading cost κ all
  multiplied by s_obj, which multiplies the objective (and every dual) by s_obj and leaves the
  feasible set unchanged. Everything reported is in original units; raw scaled values are kept.
- Incumbent value (DESIGN §6, revised after CHECK CORE round 1). V is the polished value alone:
  the exact fixed-integer QP at the incumbent's z (dual simplex at 1e-9), exactly feasible, so a
  valid lower bound on U*. The raw incumbent is recorded (the solver's value U_raw, its weights
  w_incumbent, the exact objective U_incumbent at them, and the independent checker's verdict on
  them). Flags (incumbent_flags), both at B_eff's slack 1e-6·|V| (src.opt.certified):
  U_incumbent > V + 1e-6·|V| (the incumbent violates rows within solver tolerance) and
  V > B + 1e-6·|V|. The signed discrepancies B − V and U_incumbent − V are recorded for every
  solve (B_minus_V, incumbent_minus_V; reported as distributions, A9). If the polish fails, V and
  w are nan and v_source is "polish_failed": the case is recorded and counted as excluded. B is
  the solver's final bound (raw; certified intervals use B_eff); the root bound is recorded too.
- Duals. relaxation_duals() solves the z ∈ [0, 1] relaxation of both formulations: big-M by
  Gurobi dual simplex (a QP); perspective by Clarabel (src/opt/relaxation.py, an SOCP), with
  Gurobi's barrier on the same relaxation kept only as a value cross-check (U_gurobi_barrier).
  The perspective value U is the objective at Clarabel's point with every cone exact (DESIGN §6,
  Decision 21); Clarabel's own objective (U_clarabel) and the difference are recorded alongside.
  A failed relaxation (DESIGN §6: Clarabel status neither Solved nor AlmostSolved, a relative
  residual above 1e-8, or a duality gap above 1e-9·max(|V|, |V_ref|), v_ref in original units)
  is recorded with its reason and no value or usable duals, never raised; Clarabel's status, residuals
  and gap are recorded for every solve, AlmostSolved flagged (almost_solved). The perspective
  estimator is the finite-difference slope of these values (DESIGN §6, gated by CHECKS K29c in
  S3); Clarabel's raw perspective duals here are a diagnostic. Every relaxation record carries
  raw_duals (dU*/db per key, original units) and raw_duals_usable. Decision 25 (GATE C): a failed
  perspective relaxation keeps Clarabel's raw duals there, with raw_duals_usable False; shadow
  and raw_shadow, which the estimators read, stay empty, so no estimator reads them.
  fixed_integer_duals(z) re-solves the convex problem at fixed z. Shadow prices dU*/db use
  src.opt.miqp.shadow_price (sign established by the kept tests), divided by s_obj.
- Effort. Work (deterministic) and Runtime are recorded; work_limit sets Gurobi's WorkLimit.
- Cone diagnostic (S2, pilot P4; A9). solve(cone_diag=True) runs solve_mip_with_cones, a line-
  for-line port of the kept MIQPModel.solve (polish off; bitwise the same result, tested) that
  also reads the perspective model's s and ζ at the raw incumbent, and records the objective
  effect of the cones' violation within Gurobi's tolerances, λ·Σ_i d_i·max(0, w_i²/ζ_i − s_i)
  (cone_effect, original units; nan for big-M or when not requested).
- S2b (Isaiah's GATE C note, 2026-10-19).
  - Decision 24: the polish (the fixed-integer QP behind V, and the fixed-integer duals, the same
    QP) runs by dual simplex at FeasibilityTol = OptimalityTol = 1e-9 (POLISH_PARAMS; DESIGN §6).
    PolishModel extends the kept MIQPModel's _build for mode "fixed" only, so the kept solve,
    relax and fixed_integer methods are unchanged. The independent checker's verdict on V's
    weights at 1e-9, at the solve's current bounds (PMI.verdict), is recorded on every solve
    (polished_violations); it is recorded, not used to exclude.
  - Decision 27(a), an option (default off until GATE DESIGN): PMI(rescale=True) solves the
    binary P-MI in weights w' = w/c, c the largest position bound over holdable names
    (build_rescaled_mip): rows expr(w') ≤ b/c, bounds u_i/c and ℓ/c, objective written in w' (the
    same function, so values and bounds need no mapping), and each perspective cone in its name's
    bound, t_i = v_i/u_i, s_i = u_i²·s'_i, t_i² ≤ s'_i·ζ_i, as the Clarabel relaxation does. The
    raw incumbent and the cone variables are mapped back to original units; c is recorded
    (w_scale; 1.0 unscaled). The polish, duals and relaxations stay in original units.
  - Decision 27(b), an option for I1/I2: solve_combined solves both formulations; V = the larger
    polished value, B = the smaller final bound, B_eff = max(B, V) + 1e-6·|V|; the fixed-integer
    dual at the incumbent that supplied V; the suppliers of V and B are recorded (exact ties go to
    big-M, the first of FORMULATIONS, and are flagged). combined_interval is the certified
    interval (DESIGN §6) from combined values and bounds. S2e item 3: DESIGN §6's second flag,
    V > B + 1e-6·|V|, is also applied to the combined V and B (flag_V_exceeds_B), recorded on
    every I1/I2 point and counted in the runners' summaries.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field, replace
from types import SimpleNamespace

import gurobipy as gp
import numpy as np
from gurobipy import GRB

from src.opt.certified import BOUND_RTOL, CertifiedSlope, certified_interval_eff, effective_bound
from src.opt.continuous import Mandate
from src.opt.gurobi_env import DEFAULT_SEED, DEFAULT_THREADS, quiet_env
from src.opt.feasibility import pmi_violations
from src.opt.miqp import MIQPModel, MIQPResult, _status_name, shadow_price
from src.opt.relaxation import cone_exact_s, perspective_relaxation

FORMULATIONS = ("bigm", "perspective")
FLAG_RTOL = BOUND_RTOL               # DESIGN §6 incumbent flags: B_eff's slack 1e-6·|V|
POLISH_PARAMS = {"Method": 1, "FeasibilityTol": 1e-9, "OptimalityTol": 1e-9}   # Decision 24
VERDICT_TOL = 1e-9                   # the independent checker on V's weights (Decision 24)


class PolishModel(MIQPModel):
    """The kept MIQPModel with its fixed-integer QP (mode "fixed": the polish and the
    fixed-integer duals) at POLISH_PARAMS (Decision 24). Only _build is extended."""

    def _build(self, mode: str, zp_fix=None, zm_fix=None):
        out = super()._build(mode, zp_fix, zm_fix)
        if mode == "fixed":
            for name, value in POLISH_PARAMS.items():
                out[0].setParam(name, value)
        return out


def choose_s_obj(U_abs: float) -> float:
    """DESIGN §6 / pilot P1: a power of 10 with |U*|·s_obj in DESIGN's [1, 100]. This returns
    the smallest such power, so |U*|·s_obj lands in [1, 10)."""
    U_abs = abs(float(U_abs))
    if not (np.isfinite(U_abs) and U_abs > 0):
        raise ValueError(f"|U*| must be positive and finite, got {U_abs}")
    s = 10.0 ** int(np.ceil(-np.log10(U_abs)))
    if U_abs * s < 1.0:              # guard against log10 rounding at exact powers of ten
        s *= 10.0
    return s


def polished_exceeds_bound(V: float, B: float, rtol: float = FLAG_RTOL) -> bool:
    """DESIGN §6's second flag: V > B + rtol·|V| (False if V or B is undefined). Applied per solve
    (incumbent_flags) and, for combined certification, to the combined V and B (S2e item 3)."""
    if not (np.isfinite(V) and np.isfinite(B)):
        return False
    return bool(V > B + rtol * abs(V))


def incumbent_flags(U_incumbent: float, V: float, B: float,
                    rtol: float = FLAG_RTOL) -> tuple[bool, bool]:
    """(exact objective at the incumbent's weights > V + rtol·|V|, V > B + rtol·|V|); both False
    when V is undefined (the polish failed)."""
    if not np.isfinite(V):
        return False, False
    return bool(U_incumbent > V + rtol * abs(V)), polished_exceeds_bound(V, B, rtol)


def exact_objective(w, alpha, lam: float, B, F, d, mandate: Mandate) -> float:
    """U(w) = α'w − λ(y'Fy + Σ d_i w_i²) − c Σ max(−w_i, 0) − κ Σ |w_i|, y = B'w (w₀ = 0)."""
    w = np.asarray(w, float)
    y = np.asarray(B, float).T @ w
    risk = float(y @ np.asarray(F, float) @ y + np.asarray(d, float) @ (w * w))
    return float(np.asarray(alpha, float) @ w - lam * risk
                 - mandate.borrow_monthly * np.maximum(-w, 0.0).sum()
                 - mandate.trade_cost * np.abs(w).sum())


def _run_mip(mdl, wp, wm, zp, zm, n: int, time_limit: float, mip_gap: float, presolve: int,
             work_limit: float | None, w_scale: float = 1.0) -> MIQPResult:
    """The body of src.opt.miqp.MIQPModel.solve (polish off), ported line for line: parameters,
    root callback, optimize, record. w = w_scale·(w⁺ − w⁻) (1.0 unless the weights were
    rescaled). The model is left for the caller to read and dispose."""
    mdl.Params.TimeLimit, mdl.Params.MIPGap, mdl.Params.Presolve = time_limit, mip_gap, presolve
    if work_limit is not None:
        mdl.Params.WorkLimit = work_limit
    root = {}

    def cb(model, where):
        if where == GRB.Callback.MIPNODE and model.cbGet(GRB.Callback.MIPNODE_NODCNT) == 0:
            root["bnd"] = model.cbGet(GRB.Callback.MIPNODE_OBJBND)
            root["best"] = model.cbGet(GRB.Callback.MIPNODE_OBJBST)

    mdl.optimize(cb)
    has = mdl.SolCount > 0
    U = -mdl.ObjVal if has else np.nan
    bound = -mdl.ObjBound
    gap = (bound - U) / abs(U) if has and U != 0 else np.nan
    rg = np.nan
    if "bnd" in root and abs(root["best"]) < GRB.INFINITY:
        rb, rbest = -root["bnd"], -root["best"]
        rg = (rb - rbest) / abs(rbest) if rbest != 0 else np.nan
    return MIQPResult(U=U, bound=bound,
                      w=w_scale * (wp.X - wm.X) if has else np.full(n, np.nan),
                      zp=np.round(zp.X) if has else np.zeros(n),
                      zm=np.round(zm.X) if has else np.zeros(n),
                      status=mdl.Status, status_name=_status_name(mdl.Status),
                      runtime=mdl.Runtime, nodes=mdl.NodeCount, final_gap=gap, root_gap=rg,
                      reached_gap=mdl.Status == GRB.OPTIMAL, work=mdl.Work,
                      root_bound=-root["bnd"] if "bnd" in root else np.nan)


def solve_mip_with_cones(M: MIQPModel, time_limit: float, mip_gap: float, presolve: int,
                         work_limit: float | None) -> tuple[MIQPResult, dict | None]:
    """src.opt.miqp.MIQPModel.solve with polish=False, ported line for line (the same model,
    parameters and root callback, so the same result; tests/test_integer.py checks this
    bitwise), plus, for the perspective formulation, Gurobi's raw cone variables at the
    incumbent: w = w⁺ − w⁻, ζ and s, read before the model is disposed (A9 diagnostic)."""
    mdl, wp, wm, zp, zm, _ = M._build("mip")
    res = _run_mip(mdl, wp, wm, zp, zm, M.N, time_limit, mip_gap, presolve, work_limit)
    cones = None
    if mdl.SolCount > 0 and M.formulation == "perspective":
        get = lambda name: np.array([mdl.getVarByName(f"{name}[{i}]").X for i in range(M.N)])
        cones = {"w": wp.X - wm.X, "zeta": get("zeta"), "s": get("s")}
    mdl.dispose()
    return res, cones


def build_rescaled_mip(M: MIQPModel):
    """Decision 27(a): the binary P-MI of M (its formulation, data and current bounds) in weights
    w' = w/c, c = max u_i over holdable names (module docstring). Returns (model, w'⁺, w'⁻, z⁺,
    z⁻, c, cone) with cone = (ζ, s', (c·r_i)²) for the perspective form (s_i = (c·r_i)²·s'_i,
    r_i = u_i/c, 1 where a name cannot be held), else None."""
    N, m, b = M.N, M.mandate, M.bounds
    ub = np.where(M.holdable, M.ub, 0.0)
    c = float(ub.max()) if ub.max() > 0 else 1.0
    r = np.where(ub > 0, ub / c, 1.0)
    mdl = gp.Model(env=quiet_env(M.threads, M.seed))
    mdl.Params.Threads, mdl.Params.Seed = M.threads, M.seed
    wp = mdl.addMVar(N, lb=0.0, ub=ub / c, name="wp")
    wm = mdl.addMVar(N, lb=0.0, ub=ub / c, name="wm")
    y = mdl.addMVar(M.nK, lb=-GRB.INFINITY, name="y")           # y' = B'w' = y/c
    mdl.addConstr(y == M.B.T @ wp - M.B.T @ wm, name="ydef")
    if m.dollar is not None:
        s = wp.sum() - wm.sum()
        mdl.addConstr(s <= b["dollar"] / c)
        mdl.addConstr(-s <= b["dollar"] / c)
    if m.beta is not None:
        mdl.addConstr(y[M.mkt] <= b["beta"] / c)
        mdl.addConstr(-y[M.mkt] <= b["beta"] / c)
    if m.style is not None:
        ys = y[M.style_idx]
        mdl.addConstr(ys <= np.asarray(b["style"], float) / c)
        mdl.addConstr(-ys <= np.asarray(b["style"], float) / c)
    if m.sector is not None:
        sw = M.S.T @ wp - M.S.T @ wm
        mdl.addConstr(sw <= np.asarray(b["sector"], float) / c)
        mdl.addConstr(-sw <= np.asarray(b["sector"], float) / c)
    if m.gross is not None:
        mdl.addConstr(wp.sum() + wm.sum() <= b["gross"] / c)
    zub = M.holdable.astype(float)
    zp = mdl.addMVar(N, lb=0.0, ub=zub, vtype=GRB.BINARY, name="zp")
    zm = mdl.addMVar(N, lb=0.0, ub=zub, vtype=GRB.BINARY, name="zm")
    mdl.addConstr(wp <= (ub / c) * zp, name="ub_p")
    mdl.addConstr(wm <= (ub / c) * zm, name="ub_m")
    if M.ell > 0:
        mdl.addConstr(wp >= (M.ell / c) * zp, name="lb_p")
        mdl.addConstr(wm >= (M.ell / c) * zm, name="lb_m")
    mdl.addConstr(zp + zm <= 1, name="onesided")
    if M.K is not None:
        mdl.addConstr(zp.sum() + zm.sum() <= M.K)
    cone = None
    if M.formulation == "perspective":
        t = mdl.addMVar(N, lb=-GRB.INFINITY, name="v")            # t_i = v_i/u_i
        zeta = mdl.addMVar(N, lb=0.0, ub=1.0, name="zeta")
        s = mdl.addMVar(N, lb=0.0, name="s")                       # s'_i = s_i/u_i²
        mdl.addConstr(r * t == wp - wm, name="vdef")
        mdl.addConstr(zeta == zp + zm, name="zetadef")
        tl, sl, zl = t.tolist(), s.tolist(), zeta.tolist()
        for i in range(N):
            mdl.addQConstr(tl[i] * tl[i] <= sl[i] * zl[i], name=f"persp{i}")
        s_scale = (c * r) ** 2
        idio = (M.d * s_scale) @ s
        cone = (zeta, s, s_scale)
    else:
        dw = c * np.sqrt(M.d)
        idio = (dw * wp) @ (dw * wp) + (dw * wm) @ (dw * wm)
    fy = np.linalg.cholesky(M.F).T @ y
    cb, kappa = m.borrow_monthly, m.trade_cost
    U = (c * (M.alpha @ wp - M.alpha @ wm) - M.lam * (c * c * (fy @ fy) + idio)
         - c * cb * wm.sum() - c * kappa * (wp.sum() + wm.sum()))
    mdl.setObjective(-U, GRB.MINIMIZE)
    return mdl, wp, wm, zp, zm, c, cone


def solve_mip_rescaled(M: MIQPModel, time_limit: float, mip_gap: float, presolve: int,
                       work_limit: float | None) -> tuple[MIQPResult, dict | None, float]:
    """The binary P-MI solved in rescaled weights (build_rescaled_mip) with the kept solve's
    parameters and root callback (_run_mip); the incumbent and, for the perspective form, the
    cone variables mapped back to original units (w, ζ, s). Returns (result, cones, c)."""
    mdl, wp, wm, zp, zm, c, cone = build_rescaled_mip(M)
    res = _run_mip(mdl, wp, wm, zp, zm, M.N, time_limit, mip_gap, presolve, work_limit, w_scale=c)
    cones = None
    if mdl.SolCount > 0 and cone is not None:
        zeta, s, s_scale = cone
        cones = {"w": res.w, "zeta": zeta.X, "s": s_scale * s.X}
    mdl.dispose()
    return res, cones, c


def cone_violation_effect(w, zeta, s, ub, d, lam: float) -> tuple[float, int]:
    """λ·Σ_i d_i·max(0, w_i²/ζ_i − s_i) at Gurobi's raw incumbent (w, ζ, s): the objective
    effect of the perspective cones' violation within Gurobi's tolerances (A9, pilot P4).
    w_i²/ζ_i is src.opt.relaxation.cone_exact_s (0 where w_i = 0, at most u_i|w_i|); returns
    the effect in the units of λ and the number of names held at that bound."""
    need, n_cap = cone_exact_s(w, zeta, ub)
    return float(lam * (np.asarray(d, float) @ np.maximum(need - np.asarray(s, float), 0.0))), n_cap


@dataclass
class PMIResult:
    V: float                     # incumbent value, original units (nan if no incumbent)
    B: float                     # final bound on U*, original units
    w: np.ndarray                # weights achieving V
    zp: np.ndarray
    zm: np.ndarray
    status_name: str
    reached_gap: bool
    runtime: float
    work: float
    nodes: float
    root_bound: float            # original units (nan if not observed)
    U_incumbent: float           # exact U at the solver's incumbent weights
    w_incumbent: np.ndarray
    U_polished: float            # exact fixed-integer QP at the incumbent's z (nan if failed)
    polish_status: str
    U_raw: float                 # the solver's own incumbent value, original units
    U_raw_scaled: float          # ... and as solved (× s_obj)
    B_scaled: float
    s_obj: float
    formulation: str
    settings: dict = field(default_factory=dict)
    v_source: str = "polished"   # "polished", "polish_failed" (V = nan) or "none" (no incumbent)
    incumbent_violations: str = "{}"   # JSON: the checker on the raw incumbent weights
    flag_incumbent_exceeds_polished: bool = False
    flag_polished_exceeds_bound: bool = False
    cone_effect: float = float("nan")   # λ·Σ d_i·max(0, w_i²/ζ_i − s_i) at the raw incumbent
    cone_n_capped: int = -1              # names where w²/ζ took the linking bound u|w| (-1: none)
    polished_violations: str = "not run"   # JSON: the checker on V's weights at 1e-9 (Decision 24)
    w_scale: float = 1.0                 # c of the rescaled solve (Decision 27(a)); 1.0 unscaled

    @property
    def cone_effect_rel(self) -> float:
        """cone_effect/|V| (nan if either is undefined or V = 0)."""
        return self.cone_effect / abs(self.V) if np.isfinite(self.V) and self.V != 0 else np.nan

    @property
    def final_gap(self) -> float:
        return (self.B - self.V) / abs(self.V) if np.isfinite(self.V) and self.V != 0 else np.nan

    @property
    def B_minus_V(self) -> float:
        """Signed B − V, original units (nan if V is undefined); DESIGN §6, A9."""
        return self.B - self.V if np.isfinite(self.V) else np.nan

    @property
    def incumbent_minus_V(self) -> float:
        """Signed U_incumbent − V, original units (nan if V is undefined); DESIGN §6, A9."""
        return self.U_incumbent - self.V if np.isfinite(self.V) else np.nan

    @property
    def root_gap(self) -> float:
        """(root bound − V)/|V| against this solve's V; analyses use the best known value."""
        return (self.root_bound - self.V) / abs(self.V) if np.isfinite(self.V) and self.V != 0 else np.nan


class PMI:
    """One P-MI instance in original units; bounds can be changed between solves."""

    def __init__(self, B, F, d, S, alpha, lam: float, mandate: Mandate, adv, K: int | None,
                 ell: float, formulation: str = "perspective", s_obj: float = 1.0,
                 factor_names=None, threads: int = DEFAULT_THREADS, seed: int = DEFAULT_SEED,
                 rescale: bool = False):
        if formulation not in FORMULATIONS:
            raise ValueError(formulation)
        self.B, self.F, self.d, self.S = (np.asarray(a, float) for a in (B, F, d, S))
        self.alpha, self.lam, self.mandate = np.asarray(alpha, float), float(lam), mandate
        self.adv, self.K, self.ell, self.formulation = adv, K, float(ell), formulation
        self.s_obj, self.factor_names = float(s_obj), factor_names
        self.threads, self.seed, self.rescale = threads, seed, bool(rescale)
        self.model = self._make(formulation)

    def _make(self, formulation: str, bounds: dict | None = None) -> MIQPModel:
        s, m = self.s_obj, self.mandate
        scaled = replace(m, borrow_annual=s * m.borrow_annual, trade_cost=s * m.trade_cost)
        M = PolishModel(self.B, self.F, self.d, self.S, s * self.alpha, s * self.lam, scaled,
                        self.adv, K=self.K, ell=self.ell, formulation=formulation,
                        factor_names=self.factor_names, threads=self.threads, seed=self.seed)
        if bounds is not None:
            M.bounds = copy.deepcopy(bounds)
        return M

    def sibling(self, formulation: str, rescale: bool = False) -> "PMI":
        """The same instance (data, λ, s_obj, current bounds, copied) as another formulation."""
        P = PMI(self.B, self.F, self.d, self.S, self.alpha, self.lam, self.mandate, self.adv,
                self.K, self.ell, formulation=formulation, s_obj=self.s_obj,
                factor_names=self.factor_names, threads=self.threads, seed=self.seed,
                rescale=rescale)
        P.model.bounds = copy.deepcopy(self.model.bounds)
        return P

    def verdict(self, w, zp, zm, tol: float = VERDICT_TOL) -> str:
        """The independent checker (src.opt.feasibility.pmi_violations) on (w, z⁺, z⁻) at the
        current bounds, as JSON. A style or sector bound that is not common to every element is
        checked element by element from w here (keys style:<factor>, sector:<j>)."""
        b, w = self.model.bounds, np.asarray(w, float)
        common = lambda v: v is None or bool(np.all(np.asarray(v) == np.asarray(v).flat[0]))
        first = lambda v: None if v is None or not common(v) else float(np.asarray(v).flat[0])
        eff = replace(self.mandate, dollar=b["dollar"], beta=b["beta"], gross=b["gross"],
                      style=first(b["style"]), sector=first(b["sector"]))
        v = pmi_violations(w, zp, zm, self.B, self.S, eff, self.K, self.ell, self.adv,
                           mkt=self.model.mkt, tol=tol)
        if not common(b["style"]):
            y = self.B.T @ w
            names = self.style_names or [str(k) for k in self.model.style_idx]
            v.update({f"style:{n}": float(abs(y[k]) - bk) for n, k, bk in
                      zip(names, self.model.style_idx, b["style"]) if abs(y[k]) > bk + tol})
        if not common(b["sector"]):
            sw = self.S.T @ w
            v.update({f"sector:{j}": float(abs(sw[j]) - bj) for j, bj in enumerate(b["sector"])
                      if abs(sw[j]) > bj + tol})
        return json.dumps(v, sort_keys=True)

    # ----- bounds -----
    def set_bound(self, family: str, value, index: int | None = None) -> None:
        self.model.set_bound(family, value, index)

    def bound(self, family: str):
        return self.model.bound(family)

    @property
    def style_names(self):
        return self.model.style_names

    def bound_of(self, key: str) -> float:
        """The bound b behind a shadow-price key: dollar, beta, gross, cardinality (K), style and
        sector (the common bound; nan if not common), style:<factor>, sector:<j>."""
        fam, _, tail = key.partition(":")
        if fam == "cardinality":
            return float(self.K) if self.K is not None else float("nan")
        b = self.bound(fam)
        if tail:
            i = (self.style_names or [str(k) for k in self.model.style_idx]).index(tail) \
                if fam == "style" else int(tail)
            return float(np.asarray(b)[i])
        if np.ndim(b) == 0:
            return float(b)
        b = np.asarray(b, float)
        return float(b[0]) if np.all(b == b[0]) else float("nan")

    # ----- solves -----
    def solve(self, mip_gap: float, work_limit: float | None = None,
              time_limit: float = float("inf"), presolve: int = -1,
              cone_diag: bool = False) -> PMIResult:
        s, M = self.s_obj, self.model
        cones, c = None, 1.0
        if self.rescale:
            r, cones, c = solve_mip_rescaled(M, time_limit, mip_gap, presolve, work_limit)
            cones = cones if cone_diag else None
        elif cone_diag:
            r, cones = solve_mip_with_cones(M, time_limit, mip_gap, presolve, work_limit)
        else:
            r = M.solve(time_limit=time_limit, mip_gap=mip_gap, presolve=presolve, polish=False,
                        work_limit=work_limit)
        settings = {"mip_gap": mip_gap, "work_limit": work_limit, "time_limit": time_limit,
                    "presolve": presolve, "threads": self.threads, "seed": self.seed,
                    "rescale": self.rescale, "w_scale": c, "polish": dict(POLISH_PARAMS)}
        has = bool(np.isfinite(r.U))
        U_inc = exact_objective(r.w, self.alpha, self.lam, self.B, self.F, self.d,
                                self.mandate) if has else np.nan
        U_pol, w_pol, pstat = np.nan, None, "not run"
        if has:
            try:
                fx = M.fixed_integer(r.zp, r.zm)
                U_pol, w_pol, pstat = fx.U / s, fx.w, "OPTIMAL"
            except RuntimeError as err:
                pstat = str(err)
        use_pol = has and bool(np.isfinite(U_pol))
        V = U_pol if use_pol else np.nan
        w = w_pol if use_pol else np.full(M.N, np.nan)
        B = r.bound / s
        f_inc, f_bnd = incumbent_flags(U_inc, V, B)
        inc_viol = json.dumps(pmi_violations(r.w, r.zp, r.zm, self.B, self.S, self.mandate,
                                             self.K, self.ell, self.adv, mkt=M.mkt),
                              sort_keys=True) if has else "no incumbent"
        c_eff, c_cap = np.nan, -1
        if cones is not None:
            c_eff, c_cap = cone_violation_effect(cones["w"], cones["zeta"], cones["s"],
                                                 np.where(M.holdable, M.ub, 0.0), self.d, self.lam)
        return PMIResult(V=V, B=B, w=w, zp=r.zp, zm=r.zm, status_name=r.status_name,
                         reached_gap=r.reached_gap, runtime=r.runtime, work=r.work,
                         nodes=r.nodes, root_bound=r.root_bound / s, U_incumbent=U_inc,
                         w_incumbent=r.w, U_polished=U_pol, polish_status=pstat,
                         U_raw=r.U / s, U_raw_scaled=r.U, B_scaled=r.bound, s_obj=s,
                         formulation=self.formulation, settings=settings,
                         v_source="polished" if use_pol else ("polish_failed" if has else "none"),
                         incumbent_violations=inc_viol, flag_incumbent_exceeds_polished=f_inc,
                         flag_polished_exceeds_bound=f_bnd, cone_effect=c_eff, cone_n_capped=c_cap,
                         polished_violations=self.verdict(w, r.zp, r.zm) if use_pol
                         else "V undefined", w_scale=c)

    def _shadows(self, res) -> dict[str, float]:
        """Raw (scaled) dU*/db per key: dollar, beta, gross, style and style:<f>, sector and
        sector:<j>, cardinality (relaxations only)."""
        out = {}
        for fam in ("dollar", "beta", "gross", "cardinality"):
            if (fam, "upper") in res.duals:
                out[fam] = shadow_price(res, fam)
        if ("style", "upper") in res.duals:
            out["style"] = shadow_price(res, "style")
            names = self.model.style_names or [str(k) for k in self.model.style_idx]
            out.update({f"style:{n}": shadow_price(res, "style", i) for i, n in enumerate(names)})
        if ("sector", "upper") in res.duals:
            out["sector"] = shadow_price(res, "sector")
            out.update({f"sector:{j}": shadow_price(res, "sector", j)
                        for j in range(len(res.duals[("sector", "upper")]))})
        return out

    def _dual_record(self, res, status: str = "OPTIMAL") -> dict:
        raw = self._shadows(res)
        shadow = {k: v / self.s_obj for k, v in raw.items()}
        return {"ok": True, "status": status, "U": res.U / self.s_obj, "work": res.work,
                "raw_shadow": raw, "shadow": shadow,
                "raw_duals": dict(shadow), "raw_duals_usable": True}

    @staticmethod
    def _failed(status: str) -> dict:
        return {"ok": False, "status": status, "U": np.nan, "work": np.nan,
                "raw_shadow": {}, "shadow": {}, "raw_duals": {}, "raw_duals_usable": False}

    def fixed_integer_duals(self, zp, zm) -> dict:
        return self._dual_record(self.model.fixed_integer(zp, zm))

    def _model(self, form: str) -> MIQPModel:
        return self.model if form == self.formulation else self._make(form, self.model.bounds)

    def relaxation_duals(self, v_ref: float | None = None) -> dict[str, dict]:
        """Both relaxations at the current bounds (module docstring); failures are recorded.
        v_ref: the perspective gap clause's reference value, original units (DESIGN §6)."""
        try:
            bigm = {**self._dual_record(self._model("bigm").relax()), "solver": "gurobi"}
        except RuntimeError as err:
            bigm = {**self._failed(str(err)), "solver": "gurobi"}
        P = self._model("perspective")
        cl = perspective_relaxation(P, v_ref=None if v_ref is None else self.s_obj * v_ref)
        persp = self._dual_record(cl.result, cl.status) if cl.ok else self._failed(cl.status)
        if not cl.ok and cl.duals:                # Decision 25: kept, unusable, not in shadow
            persp["raw_duals"] = {k: v / self.s_obj for k, v in
                                  self._shadows(SimpleNamespace(duals=cl.duals)).items()}
        s, info = self.s_obj, cl.info
        persp.update(solver="clarabel", clarabel=info,
                     almost_solved=info.get("clarabel_status") == "AlmostSolved",
                     fail_reason=info.get("fail_reason"),
                     U_value=info["value"] / s,               # the DESIGN §6 value, failed or not
                     U_clarabel=info["clarabel_objective"] / s,
                     U_minus_clarabel=info["value_minus_clarabel"] / s)
        try:
            persp.update(U_gurobi_barrier=P.relax().U / self.s_obj, gurobi_barrier_status="OPTIMAL")
        except RuntimeError as err:
            persp.update(U_gurobi_barrier=np.nan, gurobi_barrier_status=str(err))
        return {"bigm": bigm, "perspective": persp}


# ----- Decision 27(b): combined certification (an option for I1/I2) -----

def combine_certification(parts: dict[str, PMIResult]) -> dict:
    """V = the larger defined polished value, B = the smaller defined final bound over the
    formulations solved, B_eff = max(B, V) + 1e-6·|V|, and who supplied each (FORMULATIONS order;
    an exact tie goes to the first and is flagged; "none" if no formulation has one).
    flag_V_exceeds_B is DESIGN §6's second flag on the combined values, V > B + 1e-6·|V| (S2e
    item 3): V and B can come from different formulations, so it can be set when neither
    formulation's own flag is."""
    forms = [f for f in FORMULATIONS if f in parts]
    Vs = {f: parts[f].V for f in forms if np.isfinite(parts[f].V)}
    Bs = {f: parts[f].B for f in forms if np.isfinite(parts[f].B)}
    v_from = max(Vs, key=Vs.get) if Vs else "none"        # max/min keep the first of a tie
    b_from = min(Bs, key=Bs.get) if Bs else "none"
    V = Vs[v_from] if Vs else np.nan
    B = Bs[b_from] if Bs else np.nan
    return {"V": V, "B": B,
            "B_eff": effective_bound(B, V) if np.isfinite(V) and np.isfinite(B) else np.nan,
            "v_from": v_from, "b_from": b_from,
            "v_tie": sum(v == V for v in Vs.values()) > 1,
            "b_tie": sum(v == B for v in Bs.values()) > 1,
            "flag_V_exceeds_B": polished_exceeds_bound(V, B)}


@dataclass
class CombinedResult:
    V: float                     # the larger polished value (nan if neither is defined)
    B: float                     # the smaller final bound
    B_eff: float                 # max(B, V) + 1e-6·|V|
    v_from: str                  # the formulation that supplied V ("none" if undefined)
    b_from: str                  # the formulation that supplied B
    v_tie: bool
    b_tie: bool
    flag_V_exceeds_B: bool       # combined V > combined B + 1e-6·|V| (DESIGN §6's second flag)
    w: np.ndarray                # V's weights and incumbent z
    zp: np.ndarray
    zm: np.ndarray
    parts: dict                  # formulation -> PMIResult
    fixed_duals: dict | None     # the fixed-integer duals at V's incumbent (None if not run)

    @property
    def certified_gap(self) -> float:
        """B_eff − V, original units."""
        return self.B_eff - self.V


def solve_combined(pmi: PMI, mip_gap: float, work_limit: float | None = None,
                   time_limit: float = float("inf"), presolve: int = -1,
                   rescale_perspective: bool = False, cone_diag: bool = True,
                   duals: bool = True) -> CombinedResult:
    """Both formulations of `pmi` at its current bounds (siblings; the perspective one rescaled
    if asked), combined by combine_certification, with the fixed-integer duals at the incumbent
    that supplied V (a failed dual solve is recorded, not raised)."""
    parts = {f: pmi.sibling(f, rescale=rescale_perspective and f == "perspective").solve(
        mip_gap=mip_gap, work_limit=work_limit, time_limit=time_limit, presolve=presolve,
        cone_diag=cone_diag) for f in FORMULATIONS}
    c = combine_certification(parts)
    if c["v_from"] == "none":
        nan = np.full(pmi.model.N, np.nan)
        return CombinedResult(**c, w=nan, zp=nan.copy(), zm=nan.copy(), parts=parts,
                              fixed_duals=None)
    src = parts[c["v_from"]]
    fixed = None
    if duals:
        try:
            fixed = pmi.fixed_integer_duals(src.zp, src.zm)
        except RuntimeError as err:
            fixed = pmi._failed(str(err))
    return CombinedResult(**c, w=src.w, zp=src.zp, zm=src.zm, parts=parts, fixed_duals=fixed)


def combined_interval(plus: CombinedResult, minus: CombinedResult, delta: float) -> CertifiedSlope:
    """The certified slope interval (DESIGN §6, B_eff at both points) from combined results at
    b + δ and b − δ."""
    return certified_interval_eff(plus.V, plus.B, minus.V, minus.B, delta)
