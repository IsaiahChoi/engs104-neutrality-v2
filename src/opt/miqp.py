"""MIQP extension (brief §3.4, §7 E3) in gurobipy: cardinality and minimum position sizes.

    maximize  α'w − λ (y'F y + R_idio) − c 1'w⁻ − κ 1'(w⁺ + w⁻)            (w₀ = 0)
    s.t.      y = B'w,  w = w⁺ − w⁻,  the continuous mandate families of src/opt/continuous.py
              (dollar, beta, style, sector, gross; each side `expr <= bound`),
              ℓ z⁺_i ≤ w⁺_i ≤ u_i z⁺_i,   ℓ z⁻_i ≤ w⁻_i ≤ u_i z⁻_i,   z⁺_i + z⁻_i ≤ 1,
              Σ_i (z⁺_i + z⁻_i) ≤ K,      u_i = min(u, θ·ADV_i/AUM)
    Names with u_i < ℓ cannot be held (z fixed to 0).
    Big-M:        R_idio = Σ d_i w_i²
    Perspective:  R_idio = Σ d_i s_i,  v_i² ≤ s_i ζ_i,  v_i = w⁺_i − w⁻_i,  ζ_i = z⁺_i + z⁻_i
                  (auxiliary v, ζ so Gurobi sees the rotated cone x² ≤ y·z).
With w₀ = 0 the trading cost κ|w| equals κ(w⁺ + w⁻) because z⁺ + z⁻ ≤ 1.

Gurobi minimizes −U, so U* = −ObjVal and, for a constraint `expr <= b`, dU*/db = GRB_SHADOW_SIGN
× Pi. GRB_SHADOW_SIGN is established by tests/test_miqp.py (envelope theorem on fixed-integer
QPs), not assumed. Duals come from two continuous problems:
- relax(): z ∈ [0, 1] (for the perspective form a QCP; QCPDual = 1);
- fixed_integer(z⁺, z⁻): z fixed at an incumbent, solved as the equivalent QP (held names keep
  [ℓ, u_i] on their side; others are 0). At integer z both formulations give this same QP.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import gurobipy as gp
import numpy as np
from gurobipy import GRB

from src.opt.continuous import MKT, Mandate
from src.opt.gurobi_env import DEFAULT_SEED, DEFAULT_THREADS, quiet_env

GRB_SHADOW_SIGN = -1.0
TWO_SIDED = ("dollar", "beta", "style", "sector")


@dataclass
class MIQPResult:
    U: float                     # U* (monthly) of the incumbent; nan if none
    bound: float                 # best upper bound on U*
    w: np.ndarray
    zp: np.ndarray
    zm: np.ndarray
    status: int
    status_name: str
    runtime: float               # seconds (Gurobi Runtime)
    nodes: float
    final_gap: float             # (bound − U) / |U|
    root_gap: float              # same at the end of the root node (nan if not observed)
    reached_gap: bool            # stopped because MIPGap was met (time to gap = runtime)
    duals: dict = field(default_factory=dict)   # (family, side) -> Pi array (continuous solves)
    U_polished: float = np.nan   # U at the incumbent's z, continuous part re-solved exactly
    w_polished: np.ndarray | None = None


class MIQPModel:
    """One instance: data, λ, α fixed; family bounds can be changed between solves."""

    def __init__(self, B, F, d, S, alpha, lam: float, mandate: Mandate, adv, K: int | None,
                 ell: float, formulation: str = "perspective", factor_names=None,
                 threads: int = DEFAULT_THREADS, seed: int = DEFAULT_SEED):
        if formulation not in ("bigm", "perspective"):
            raise ValueError(formulation)
        self.B, self.F, self.d, self.S = (np.asarray(a, float) for a in (B, F, d, S))
        self.alpha, self.lam = np.asarray(alpha, float), float(lam)
        self.mandate, self.K, self.ell, self.formulation = mandate, K, float(ell), formulation
        self.N, self.nK = self.B.shape
        names = list(factor_names) if factor_names is not None else None
        self.mkt = names.index(MKT) if names else 0
        self.style_idx = [k for k in range(self.nK) if k != self.mkt]
        self.style_names = [names[k] for k in self.style_idx] if names else None
        ub = mandate.position_bounds(adv, self.N)
        if ub is None:
            raise ValueError("the MIQP needs a position cap (big-M = u_i)")
        self.ub = ub
        self.holdable = (self.ub >= self.ell) & (self.ub > 0)
        self.bounds = {"dollar": mandate.dollar, "beta": mandate.beta, "gross": mandate.gross,
                       "style": None if mandate.style is None
                       else np.full(len(self.style_idx), mandate.style),
                       "sector": None if mandate.sector is None
                       else np.full(self.S.shape[1], mandate.sector)}
        self.threads, self.seed = threads, seed

    # ----- bounds -----
    def set_bound(self, family: str, value, index: int | None = None) -> None:
        cur = self.bounds[family]
        if cur is None:
            raise KeyError(f"{family} is off in this instance")
        if index is None:
            self.bounds[family] = (np.full_like(cur, float(value)) if isinstance(cur, np.ndarray)
                                   else float(value))
        else:
            v = np.array(cur, float)
            v[index] = float(value)
            self.bounds[family] = v

    def bound(self, family: str):
        b = self.bounds[family]
        return np.array(b, float) if isinstance(b, np.ndarray) else b

    # ----- model construction -----
    def _build(self, mode: str, zp_fix=None, zm_fix=None):
        """mode: 'mip' (binary z), 'relax' (z in [0,1]), 'fixed' (z given; equivalent QP)."""
        N, m = self.N, self.mandate
        mdl = gp.Model(env=quiet_env(self.threads, self.seed))
        mdl.Params.Threads, mdl.Params.Seed = self.threads, self.seed
        ub = np.where(self.holdable, self.ub, 0.0)
        wp = mdl.addMVar(N, lb=0.0, ub=ub, name="wp")
        wm = mdl.addMVar(N, lb=0.0, ub=ub, name="wm")
        y = mdl.addMVar(self.nK, lb=-GRB.INFINITY, name="y")
        mdl.addConstr(y == self.B.T @ wp - self.B.T @ wm, name="ydef")
        cons = {}
        if m.dollar is not None:
            s = wp.sum() - wm.sum()
            cons[("dollar", "upper")] = mdl.addConstr(s <= self.bounds["dollar"])
            cons[("dollar", "lower")] = mdl.addConstr(-s <= self.bounds["dollar"])
        if m.beta is not None:
            cons[("beta", "upper")] = mdl.addConstr(y[self.mkt] <= self.bounds["beta"])
            cons[("beta", "lower")] = mdl.addConstr(-y[self.mkt] <= self.bounds["beta"])
        if m.style is not None:
            ys = y[self.style_idx]
            cons[("style", "upper")] = mdl.addConstr(ys <= self.bounds["style"])
            cons[("style", "lower")] = mdl.addConstr(-ys <= self.bounds["style"])
        if m.sector is not None:
            sw = self.S.T @ wp - self.S.T @ wm
            cons[("sector", "upper")] = mdl.addConstr(sw <= self.bounds["sector"])
            cons[("sector", "lower")] = mdl.addConstr(-sw <= self.bounds["sector"])
        if m.gross is not None:
            cons[("gross", "upper")] = mdl.addConstr(wp.sum() + wm.sum() <= self.bounds["gross"])

        idio_lin = None
        zp = zm = None
        if mode == "fixed":
            hp, hm = np.asarray(zp_fix) > 0.5, np.asarray(zm_fix) > 0.5
            wp.lb, wp.ub = np.where(hp, self.ell, 0.0), np.where(hp, ub, 0.0)
            wm.lb, wm.ub = np.where(hm, self.ell, 0.0), np.where(hm, ub, 0.0)
        else:
            vtype = GRB.BINARY if mode == "mip" else GRB.CONTINUOUS
            zub = self.holdable.astype(float)
            zp = mdl.addMVar(N, lb=0.0, ub=zub, vtype=vtype, name="zp")
            zm = mdl.addMVar(N, lb=0.0, ub=zub, vtype=vtype, name="zm")
            mdl.addConstr(wp <= ub * zp, name="ub_p")
            mdl.addConstr(wm <= ub * zm, name="ub_m")
            if self.ell > 0:
                mdl.addConstr(wp >= self.ell * zp, name="lb_p")
                mdl.addConstr(wm >= self.ell * zm, name="lb_m")
            mdl.addConstr(zp + zm <= 1, name="onesided")
            if self.K is not None:
                cons[("cardinality", "upper")] = mdl.addConstr(zp.sum() + zm.sum() <= self.K)
            if self.formulation == "perspective":
                v = mdl.addMVar(N, lb=-GRB.INFINITY, name="v")
                zeta = mdl.addMVar(N, lb=0.0, ub=1.0, name="zeta")
                s = mdl.addMVar(N, lb=0.0, name="s")
                mdl.addConstr(v == wp - wm, name="vdef")
                mdl.addConstr(zeta == zp + zm, name="zetadef")
                vl, sl, zl = v.tolist(), s.tolist(), zeta.tolist()
                for i in range(N):
                    mdl.addQConstr(vl[i] * vl[i] <= sl[i] * zl[i], name=f"persp{i}")
                idio_lin = self.d @ s
        Ly = np.linalg.cholesky(self.F)
        fy = Ly.T @ y
        fac = fy @ fy
        if idio_lin is None:
            dw = np.sqrt(self.d)
            idio = (dw * wp) @ (dw * wp) + (dw * wm) @ (dw * wm)   # w⁺·w⁻ = 0 when one-sided
        else:
            idio = idio_lin
        c, kappa = m.borrow_monthly, m.trade_cost
        U = (self.alpha @ wp - self.alpha @ wm - self.lam * (fac + idio)
             - c * wm.sum() - kappa * (wp.sum() + wm.sum()))
        mdl.setObjective(-U, GRB.MINIMIZE)
        return mdl, wp, wm, zp, zm, cons

    # ----- solves -----
    def solve(self, time_limit: float = 300.0, mip_gap: float = 1e-4, presolve: int = -1,
              polish: bool = True) -> MIQPResult:
        """Solve the MIQP with default Gurobi tolerances (H4 times use these). With polish,
        also re-solve the continuous part at the incumbent's z as an exact QP: U_polished is
        the incumbent support's true optimal value, free of the cone tolerance in the
        perspective form (~1e-6 relative at default settings); H3 slopes use it."""
        mdl, wp, wm, zp, zm, _ = self._build("mip")
        mdl.Params.TimeLimit, mdl.Params.MIPGap, mdl.Params.Presolve = time_limit, mip_gap, presolve
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
        res = MIQPResult(U=U, bound=bound,
                         w=(wp.X - wm.X) if has else np.full(self.N, np.nan),
                         zp=np.round(zp.X) if has else np.zeros(self.N),
                         zm=np.round(zm.X) if has else np.zeros(self.N),
                         status=mdl.Status, status_name=_status_name(mdl.Status),
                         runtime=mdl.Runtime, nodes=mdl.NodeCount, final_gap=gap, root_gap=rg,
                         reached_gap=mdl.Status == GRB.OPTIMAL)
        mdl.dispose()
        if polish and has:
            fx = self.fixed_integer(res.zp, res.zm)
            res.U_polished, res.w_polished = fx.U, fx.w
        return res

    def _continuous(self, mode, zp_fix=None, zm_fix=None) -> MIQPResult:
        mdl, wp, wm, zp, zm, cons = self._build(mode, zp_fix, zm_fix)
        if mode == "relax" and self.formulation == "perspective":
            mdl.Params.QCPDual = 1
            mdl.Params.BarQCPConvTol = 1e-9
        else:
            mdl.Params.Method = 1            # dual simplex on the QP: exact active set and duals
        t0 = time.perf_counter()
        mdl.optimize()
        if mdl.Status != GRB.OPTIMAL:
            raise RuntimeError(f"{mode} solve status {_status_name(mdl.Status)}")
        duals = {k: np.atleast_1d(np.asarray(c.Pi, float)) for k, c in cons.items()}
        res = MIQPResult(U=-mdl.ObjVal, bound=-mdl.ObjVal, w=wp.X - wm.X,
                         zp=zp.X if zp is not None else np.asarray(zp_fix, float),
                         zm=zm.X if zm is not None else np.asarray(zm_fix, float),
                         status=mdl.Status, status_name="OPTIMAL",
                         runtime=time.perf_counter() - t0, nodes=0.0, final_gap=0.0,
                         root_gap=0.0, reached_gap=True, duals=duals)
        mdl.dispose()
        return res

    def relax(self) -> MIQPResult:
        return self._continuous("relax")

    def fixed_integer(self, zp, zm) -> MIQPResult:
        return self._continuous("fixed", zp, zm)


def shadow_price(res: MIQPResult, family: str, index: int | None = None) -> float:
    """dU*/d(bound) from a continuous solve's duals: both sides of a two-sided family (one
    element if index is given), or the gross bound."""
    sides = ("upper", "lower") if family in TWO_SIDED else ("upper",)
    total = 0.0
    for side in sides:
        pi = res.duals[(family, side)]
        total += pi[index] if index is not None else pi.sum()
    return GRB_SHADOW_SIGN * float(total)


def _status_name(code: int) -> str:
    names = {GRB.OPTIMAL: "OPTIMAL", GRB.TIME_LIMIT: "TIME_LIMIT", GRB.INFEASIBLE: "INFEASIBLE",
             GRB.SUBOPTIMAL: "SUBOPTIMAL", GRB.INTERRUPTED: "INTERRUPTED",
             GRB.NUMERIC: "NUMERIC", GRB.INF_OR_UNBD: "INF_OR_UNBD"}
    return names.get(code, str(code))
