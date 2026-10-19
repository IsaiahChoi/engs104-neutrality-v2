"""P-MI (DESIGN §3.4, §6) on top of the kept MIQP model (src/opt/miqp.py).

- Objective scaling. The model is built with α, λ, the borrow cost c and the trading cost κ all
  multiplied by s_obj, which multiplies the objective (and every dual) by s_obj and leaves the
  feasible set unchanged. Everything reported is in original units; raw scaled values are kept.
- Incumbent value. V = max(U(w_incumbent), U_polished): U(·) is the objective evaluated exactly
  at the solver's incumbent weights (exact_objective, so the perspective cone tolerance cannot
  overstate it), U_polished the exact fixed-integer QP at the incumbent's z. A failed polish is
  recorded, not fatal. B is the solver's final bound; the root bound is recorded too.
- Duals. relaxation_duals() solves the z ∈ [0, 1] relaxation of both formulations (big-M: a QP,
  dual simplex; perspective: a QCP, barrier with QCPDual); a failed relaxation (e.g. SUBOPTIMAL)
  is recorded with its status and no duals, never raised. fixed_integer_duals(z) re-solves the
  convex problem at fixed z. Shadow prices dU*/db use src.opt.miqp.shadow_price (sign
  established by the kept tests), divided by s_obj.
- Effort. Work (deterministic) and Runtime are recorded; work_limit sets Gurobi's WorkLimit.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace

import numpy as np

from src.opt.continuous import Mandate
from src.opt.gurobi_env import DEFAULT_SEED, DEFAULT_THREADS
from src.opt.miqp import TWO_SIDED, MIQPModel, shadow_price

FORMULATIONS = ("bigm", "perspective")


def choose_s_obj(U_abs: float) -> float:
    """DESIGN §6 / pilot P1: the power of 10 that puts |U*|·s_obj in [1, 100]. Returns the
    smallest such power, for which |U*|·s_obj ∈ [1, 10)."""
    U_abs = abs(float(U_abs))
    if not (np.isfinite(U_abs) and U_abs > 0):
        raise ValueError(f"|U*| must be positive and finite, got {U_abs}")
    s = 10.0 ** int(np.ceil(-np.log10(U_abs)))
    if U_abs * s < 1.0:              # guard against log10 rounding at exact powers of ten
        s *= 10.0
    return s


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

    @property
    def final_gap(self) -> float:
        return (self.B - self.V) / abs(self.V) if np.isfinite(self.V) and self.V != 0 else np.nan

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
        use_pol = has and np.isfinite(U_pol) and U_pol >= U_inc
        V = (U_pol if use_pol else U_inc) if has else np.nan
        w = w_pol if use_pol else r.w
        return PMIResult(V=V, B=r.bound / s, w=w, zp=r.zp, zm=r.zm, status_name=r.status_name,
                         reached_gap=r.reached_gap, runtime=r.runtime, work=r.work,
                         nodes=r.nodes, root_bound=r.root_bound / s, U_incumbent=U_inc,
                         w_incumbent=r.w, U_polished=U_pol, polish_status=pstat,
                         U_raw=r.U / s, U_raw_scaled=r.U, B_scaled=r.bound, s_obj=s,
                         formulation=self.formulation, settings=settings)

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
        assert set(TWO_SIDED) >= {"dollar", "beta", "style", "sector"}
        return out

    def _dual_record(self, res, status: str = "OPTIMAL") -> dict:
        raw = self._shadows(res)
        return {"ok": True, "status": status, "U": res.U / self.s_obj, "work": res.work,
                "raw_shadow": raw, "shadow": {k: v / self.s_obj for k, v in raw.items()}}

    def fixed_integer_duals(self, zp, zm) -> dict:
        return self._dual_record(self.model.fixed_integer(zp, zm))

    def relaxation_duals(self) -> dict[str, dict]:
        """Both relaxations at the current bounds; failures are recorded, not raised."""
        out = {}
        for form in FORMULATIONS:
            M = self.model if form == self.formulation else self._make(form, self.model.bounds)
            try:
                out[form] = self._dual_record(M.relax())
            except RuntimeError as err:
                out[form] = {"ok": False, "status": str(err), "U": np.nan, "work": np.nan,
                             "raw_shadow": {}, "shadow": {}}
        return out
