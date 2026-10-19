"""C2 sweep machinery on P-RB (ported from v1 experiments/run_rq1.py: build, snapshot,
apply_point, reset; DESIGN §7 C2).

One family is swept at a time with every other family at base. "off" removes the family (a
problem built without it); for a single style factor it sets that factor's bound to +inf (v1
verified this identical to removing the constraint). At every point P-RB is root-found
(src/opt/risk_budget.py), warm-started from the previous point's λ*, and the point is recorded
(shadow prices, elasticities, feasibility) BEFORE the swept bound is reset: v1's first E1 run
recorded the position and liquidity shadow prices after resetting the caps to base, which is
wrong at every swept cap (CHECKS K12).
"""
from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pandas as pd

from src.opt.attribution import shadow_prices, transfer_coefficient
from src.opt.continuous import MKT, ContinuousProblem, Mandate
from src.opt.feasibility import prb_violations
from src.opt.risk_budget import SIGMA_M, solve_risk_budget
from src.opt.sensitivity import BINDING_ELASTICITY, elasticities, restore, snapshot
from src.risk.factor_model import FACTORS

OFF_STYLE = np.inf
REMOVABLE = {"dollar": "dollar", "beta": "beta", "style_all": "style", "sector": "sector",
             "gross": "gross", "position": "position", "liquidity": "liquidity_theta"}
STYLE_FACTORS = [f for f in FACTORS if f != MKT]
_STYLE_GRID = [None, 0.40, 0.20, 0.10, 0.05, 0.02, 0.0]
C2_GRIDS: dict[str, list] = {                          # DESIGN §7 C2 (None = off)
    "dollar": [None, 0.10, 0.05, 0.02, 0.01, 0.0],
    "beta": [None, 0.20, 0.10, 0.05, 0.02, 0.0],
    "style_all": list(_STYLE_GRID),
    **{f"style:{f}": list(_STYLE_GRID) for f in STYLE_FACTORS},
    "sector": [None, 0.08, 0.04, 0.02, 0.01, 0.0],
    "gross": [None, 4.0, 3.0, 2.0, 1.5, 1.0],
    "position": [None, 0.06, 0.03, 0.015],
    "liquidity": [None, 0.10, 0.05, 0.025],
}

reset = restore                                         # v1 name


def base_value(mandate: Mandate, family: str):
    if family.startswith("style"):
        return mandate.style
    return getattr(mandate, REMOVABLE[family])


def build(di, mandate: Mandate, B=None, F=None, d=None, S=None, adv=None) -> dict[str, ContinuousProblem]:
    """The base problem and one problem per removable family with that family off. Inputs
    default to the full universe of `di` (a DateInputs)."""
    m = di.model if di is not None else None
    B = m.B if B is None else B
    F = m.F if F is None else F
    d = m.d if d is None else d
    S = di.sector_matrix() if S is None else S
    adv = di.adv if adv is None else adv
    mk = lambda md: ContinuousProblem(B, F, d, S, md, adv=adv, factor_names=FACTORS)
    probs = {"base": mk(mandate)}
    for fam, field in REMOVABLE.items():
        probs[f"off:{fam}"] = mk(replace(mandate, **{field: None}))
    return probs


def apply_point(P: ContinuousProblem, mandate: Mandate, family: str, value: float) -> None:
    """Set one family's bound on the base problem (restored by reset)."""
    if family in ("dollar", "beta", "gross", "sector"):
        P.set_bound(family, value)
    elif family == "style_all":
        P.set_bound("style", value)
    elif family.startswith("style:"):
        P.set_bound("style", value, index=P.style_names.index(family.split(":")[1]))
    elif family == "position":
        P.set_position_caps(value, mandate.liquidity_theta)
    elif family == "liquidity":
        P.set_position_caps(mandate.position, value)
    else:
        raise KeyError(family)


def effective_mandate(P: ContinuousProblem) -> tuple[Mandate, np.ndarray | None]:
    """The Mandate behind P's current bounds, for the independent checker, plus per-factor style
    bounds when they are not all equal."""
    def scalar(fam):
        return float(P.bound(fam)) if fam in P.bounds else None
    style_b = P.bound("style") if "style" in P.bounds else None
    common = style_b is not None and bool(np.all(style_b == style_b[0]))
    sector_b = P.bound("sector") if "sector" in P.bounds else None
    if sector_b is not None and not np.all(sector_b == sector_b[0]):
        raise ValueError("per-sector bounds are not used by any v2 design")
    u, theta = P.position_caps if "position" in P.bounds else (None, None)
    m = replace(P.mandate, dollar=scalar("dollar"), beta=scalar("beta"), gross=scalar("gross"),
                style=float(style_b[0]) if common else None,
                sector=float(sector_b[0]) if sector_b is not None else None,
                position=u, liquidity_theta=theta)
    return m, (None if common or style_b is None else style_b)


def record(P: ContinuousProblem, rb, alpha, ids: dict, tickers) -> tuple[dict, pd.DataFrame]:
    sol = rb.sol
    sp = shadow_prices(P, sol)
    e = elasticities(P, sp, rb.A)
    y = P.exposures(sol.w)
    eff, style_b = effective_mandate(P)
    viol = prb_violations(sol.w, P.B, P.F, P.d, P.S, eff, SIGMA_M, P.adv, mkt=P.mkt,
                          style_bounds=style_b)
    row = {**ids, "lam": rb.lam, "A": rb.A, "U": sol.objective, "vol_ann": rb.vol_ann,
           "risk_binding": rb.risk_binding, "n_solves": rb.n_solves, "solve_time": rb.solve_time,
           "tc": transfer_coefficient(P, alpha, sol.w), "net": float(sol.w.sum()),
           "gross": float(np.abs(sol.w).sum()), "n_held": int((np.abs(sol.w) > 1e-6).sum()),
           "beta_exposure": float(y[P.mkt]),
           "max_abs_style_exposure": float(np.abs(np.delete(y, P.mkt)).max()),
           "status": sol.status, "feasibility_violations": json.dumps(viol, sort_keys=True),
           "binding": ",".join(sorted(k for k, v in e.items() if v >= BINDING_ELASTICITY))}
    row.update({f"sp_{k}": v for k, v in sp.items()})
    row.update({f"e_{k}": v for k, v in e.items()})
    nz = np.abs(sol.w) > 1e-12
    w = pd.DataFrame({"point_id": ids["point_id"], "ticker": np.asarray(tickers)[nz], "w": sol.w[nz]})
    return row, w


def sweep_date(di, alpha, alpha_kind: str, mandate: Mandate, grids: dict[str, list],
               families=None, inputs: dict | None = None,
               rb_kw: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every point of `grids` (restricted to `families`) at one date for one alpha. `inputs`
    overrides the full-universe B, F, d, S, adv (subsamples); rb_kw goes to solve_risk_budget."""
    rb_kw = dict(rb_kw or {})
    inputs = inputs or {}
    probs = build(di, mandate, **inputs)
    base = probs["base"]
    snap = snapshot(base)
    tickers = inputs.get("tickers", di.tickers)
    ds = f"{pd.Timestamp(di.date):%Y-%m-%d}"
    lam_base = solve_risk_budget(base, alpha, **rb_kw).lam
    rows, weights = [], []
    for family, grid in grids.items():
        if families is not None and family not in families:
            continue
        lam_prev = lam_base
        for value in grid:
            off = value is None
            if off and family in REMOVABLE:
                P = probs[f"off:{family}"]
            else:
                P = base
                apply_point(P, mandate, family, OFF_STYLE if off else value)
            rb = solve_risk_budget(P, alpha, lam_guess=lam_prev, **rb_kw)
            if rb.risk_binding:
                lam_prev = rb.lam
            is_base = (not off) and bool(np.isclose(value, base_value(mandate, family)))
            pid = f"{ds}|{alpha_kind}|{family}|{'off' if off else f'{value:g}'}"
            ids = {"point_id": pid, "date": ds, "alpha": alpha_kind, "family": family,
                   "value": np.nan if off else float(value), "off": off, "is_base": is_base,
                   "N": P.N}
            row, w = record(P, rb, alpha, ids, tickers)   # before reset: the shadow prices
            reset(base, snap)                              # need the swept caps (K12)
            rows.append(row)
            weights.append(w)
    return pd.DataFrame(rows), pd.concat(weights, ignore_index=True)
