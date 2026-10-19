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
  is recorded with its reason and no value or duals, never raised; Clarabel's status, residuals
  and gap are recorded for every solve, AlmostSolved flagged (almost_solved). The perspective
  estimator is the finite-difference slope of these values (DESIGN §6, gated by CHECKS K29c in
  S3); Clarabel's raw perspective duals here are a diagnostic.
  fixed_integer_duals(z) re-solves the convex problem at fixed z. Shadow prices dU*/db use
  src.opt.miqp.shadow_price (sign established by the kept tests), divided by s_obj.
- Effort. Work (deterministic) and Runtime are recorded; work_limit sets Gurobi's WorkLimit.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field, replace

import numpy as np

from src.opt.certified import BOUND_RTOL
from src.opt.continuous import Mandate
from src.opt.gurobi_env import DEFAULT_SEED, DEFAULT_THREADS
from src.opt.feasibility import pmi_violations
from src.opt.miqp import MIQPModel, shadow_price
from src.opt.relaxation import perspective_relaxation

FORMULATIONS = ("bigm", "perspective")
FLAG_RTOL = BOUND_RTOL               # DESIGN §6 incumbent flags: B_eff's slack 1e-6·|V|


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


def incumbent_flags(U_incumbent: float, V: float, B: float,
                    rtol: float = FLAG_RTOL) -> tuple[bool, bool]:
    """(exact objective at the incumbent's weights > V + rtol·|V|, V > B + rtol·|V|); both False
    when V is undefined (the polish failed)."""
    if not np.isfinite(V):
        return False, False
    slack = rtol * abs(V)
    return bool(U_incumbent > V + slack), bool(V > B + slack)


def exact_objective(w, alpha, lam: float, B, F, d, mandate: Mandate) -> float:
    """U(w) = α'w − λ(y'Fy + Σ d_i w_i²) − c Σ max(−w_i, 0) − κ Σ |w_i|, y = B'w (w₀ = 0)."""
    w = np.asarray(w, float)
    y = np.asarray(B, float).T @ w
    risk = float(y @ np.asarray(F, float) @ y + np.asarray(d, float) @ (w * w))
    return float(np.asarray(alpha, float) @ w - lam * risk
                 - mandate.borrow_monthly * np.maximum(-w, 0.0).sum()
                 - mandate.trade_cost * np.abs(w).sum())


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
                 factor_names=None, threads: int = DEFAULT_THREADS, seed: int = DEFAULT_SEED):
        if formulation not in FORMULATIONS:
            raise ValueError(formulation)
        self.B, self.F, self.d, self.S = (np.asarray(a, float) for a in (B, F, d, S))
        self.alpha, self.lam, self.mandate = np.asarray(alpha, float), float(lam), mandate
        self.adv, self.K, self.ell, self.formulation = adv, K, float(ell), formulation
        self.s_obj, self.factor_names = float(s_obj), factor_names
        self.threads, self.seed = threads, seed
        self.model = self._make(formulation)

    def _make(self, formulation: str, bounds: dict | None = None) -> MIQPModel:
        s, m = self.s_obj, self.mandate
        scaled = replace(m, borrow_annual=s * m.borrow_annual, trade_cost=s * m.trade_cost)
        M = MIQPModel(self.B, self.F, self.d, self.S, s * self.alpha, s * self.lam, scaled,
                      self.adv, K=self.K, ell=self.ell, formulation=formulation,
                      factor_names=self.factor_names, threads=self.threads, seed=self.seed)
        if bounds is not None:
            M.bounds = copy.deepcopy(bounds)
        return M

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
              time_limit: float = float("inf"), presolve: int = -1) -> PMIResult:
        s, M = self.s_obj, self.model
        r = M.solve(time_limit=time_limit, mip_gap=mip_gap, presolve=presolve, polish=False,
                    work_limit=work_limit)
        settings = {"mip_gap": mip_gap, "work_limit": work_limit, "time_limit": time_limit,
                    "presolve": presolve, "threads": self.threads, "seed": self.seed}
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
        return PMIResult(V=V, B=B, w=w, zp=r.zp, zm=r.zm, status_name=r.status_name,
                         reached_gap=r.reached_gap, runtime=r.runtime, work=r.work,
                         nodes=r.nodes, root_bound=r.root_bound / s, U_incumbent=U_inc,
                         w_incumbent=r.w, U_polished=U_pol, polish_status=pstat,
                         U_raw=r.U / s, U_raw_scaled=r.U, B_scaled=r.bound, s_obj=s,
                         formulation=self.formulation, settings=settings,
                         v_source="polished" if use_pol else ("polish_failed" if has else "none"),
                         incumbent_violations=inc_viol, flag_incumbent_exceeds_polished=f_inc,
                         flag_polished_exceeds_bound=f_bnd)

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
        return {"ok": True, "status": status, "U": res.U / self.s_obj, "work": res.work,
                "raw_shadow": raw, "shadow": {k: v / self.s_obj for k, v in raw.items()}}

    @staticmethod
    def _failed(status: str) -> dict:
        return {"ok": False, "status": status, "U": np.nan, "work": np.nan,
                "raw_shadow": {}, "shadow": {}}

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
