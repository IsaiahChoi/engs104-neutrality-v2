"""S3b items 3–5 (Isaiah's GATE I note): pure helpers for support stability, the I2 grid's shape
and hedged legs. experiments/run_s3b.py and tools/s3b_analysis.py apply them.

- Support (item 3): the sign pattern of V's polished weights, |w| > SUPPORT_TOL = 1e-6 (the P3
  support rule), as "i+;j-" over sorted indices.
- z from polished weights: with ℓ > 0, a held name has |w| ≥ ℓ (within the polish's 1e-9) and any
  other name has w = 0 exactly (the fixed-integer QP fixes it), so z⁺ = [w ≥ ℓ/2], z⁻ = [w ≤ −ℓ/2];
  a weight strictly between 1e-9 and ℓ/2 in magnitude is neither held nor zero, and raises.
- The fixed-integer QP's active set: every row of the QP that holds within ACTIVE_TOL = 1e-9 (the
  QP's FeasibilityTol, DESIGN §6) at its solution: the mandate rows of the model's current bounds
  ('<family>:<side>' for dollar, beta and gross; '<family>:<side>:<k>' per style factor and
  sector), and each held name's bounds ('min:i' at ℓ, 'cap:i' at u_i). Unheld names are fixed at 0
  and carry no row. The convention is src.opt.sensitivity.active_set's (residual ≥ −tol).
- Classes: P1 support and active set unchanged over b − δ, b, b + δ; P2 support unchanged and
  active set changed; P3 support changed.
- Case classes and the I2 grid (items 3–4): case_classes, grid_nonconcavity.
- Hedged legs (item 5): names with w⁺ > 1e-6 and w⁻ > 1e-6 in a perspective relaxation, and the
  note's prediction |w⁺ − w⁻| < ℓ and z⁺ + z⁻ > |w⁺ − w⁻|/ℓ per name.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

SUPPORT_TOL = 1e-6
ACTIVE_TOL = 1e-9
ZERO_TOL = 1e-9
LEG_TOL = 1e-6


def support_signature(w, tol: float = SUPPORT_TOL) -> str:
    w = np.asarray(w, float)
    idx = np.flatnonzero(np.abs(w) > tol)
    return ";".join(f"{i}{'+' if w[i] > 0 else '-'}" for i in idx)


def z_from_weights(w, ell: float, zero_tol: float = ZERO_TOL) -> tuple[np.ndarray, np.ndarray]:
    w = np.asarray(w, float)
    bad = (np.abs(w) > zero_tol) & (np.abs(w) < ell / 2)
    if bad.any():
        raise ValueError(f"weights neither held nor zero at {np.flatnonzero(bad).tolist()}")
    return (w >= ell / 2).astype(float), (w <= -ell / 2).astype(float)


def fixed_active_set(M, w, tol: float = ACTIVE_TOL) -> frozenset[str]:
    """The fixed-integer QP's active rows at w (module docstring). M: a src.opt.miqp.MIQPModel
    (or anything with B, S, mandate, bounds, mkt, style_idx, ub, holdable, ell)."""
    w = np.asarray(w, float)
    b, m = M.bounds, M.mandate
    y = M.B.T @ w
    out = set()

    def two(fam, val, bound, idx=None):
        tag = "" if idx is None else f":{idx}"
        if val >= bound - tol:
            out.add(f"{fam}:upper{tag}")
        if -val >= bound - tol:
            out.add(f"{fam}:lower{tag}")

    if m.dollar is not None:
        two("dollar", float(w.sum()), float(b["dollar"]))
    if m.beta is not None:
        two("beta", float(y[M.mkt]), float(b["beta"]))
    if m.style is not None:
        for k, (j, bk) in enumerate(zip(M.style_idx, np.asarray(b["style"], float))):
            two("style", float(y[j]), float(bk), k)
    if m.sector is not None:
        sw = M.S.T @ w
        for j, bj in enumerate(np.asarray(b["sector"], float)):
            two("sector", float(sw[j]), float(bj), j)
    if m.gross is not None and float(np.abs(w).sum()) >= float(b["gross"]) - tol:
        out.add("gross:upper")
    ub = np.where(M.holdable, M.ub, 0.0)
    held = np.abs(w) > ZERO_TOL
    for i in np.flatnonzero(held):
        a = abs(w[i])
        if a <= M.ell + tol:
            out.add(f"min:{i}")
        if a >= ub[i] - tol:
            out.add(f"cap:{i}")
    return frozenset(out)


def support_class(supports, actives) -> str:
    if len(set(supports)) > 1:
        return "P3"
    return "P1" if len(set(actives)) == 1 else "P2"


def hedged_names(wp, wm, zp, zm, ell: float, tol: float = LEG_TOL) -> pd.DataFrame:
    wp, wm, zp, zm = (np.asarray(a, float) for a in (wp, wm, zp, zm))
    idx = np.flatnonzero((wp > tol) & (wm > tol))
    net = np.abs(wp[idx] - wm[idx])
    zeta = zp[idx] + zm[idx]
    h = pd.DataFrame({"i": idx, "wp": wp[idx], "wm": wm[idx], "zp": zp[idx], "zm": zm[idx],
                      "net": net, "min_leg": np.minimum(wp[idx], wm[idx]), "zeta": zeta,
                      "net_below_ell": net < ell, "zeta_above_net_over_ell": zeta > net / ell})
    h["prediction_holds"] = h["net_below_ell"] & h["zeta_above_net_over_ell"]
    return h


def spearman(x, y) -> float:
    return float(spearmanr(np.asarray(x, float), np.asarray(y, float)).statistic)


def case_classes(support: pd.DataFrame) -> pd.DataFrame:
    """Item 3: one row per I1 case from s3b_support rows (three points each): the class (P1, P2,
    P3), the number of names whose support entry changes against b at b − δ and b + δ, and the
    active rows that change (';'-joined, sorted)."""
    out = []
    for cid, g in support.groupby("id", sort=True):
        g = g.set_index("point")
        if set(g.index) != {"minus", "b", "plus"}:
            raise ValueError(f"{cid}: points {sorted(g.index)}")
        sups = [g.loc[p, "support"] for p in ("minus", "b", "plus")]
        acts = [frozenset(filter(None, g.loc[p, "active_set"].split(";"))) for p in ("minus", "b", "plus")]
        sset = [set(filter(None, x.split(";"))) for x in sups]
        out.append({"id": cid, "class": support_class(sups, acts),
                    "n_support_changes_minus": len(sset[0] ^ sset[1]),
                    "n_support_changes_plus": len(sset[2] ^ sset[1]),
                    "active_rows_changed": ";".join(sorted((acts[0] ^ acts[1]) | (acts[2] ^ acts[1])))})
    return pd.DataFrame(out)


def grid_nonconcavity(bounds, V, B_eff) -> pd.DataFrame:
    """Item 4: interior triples of an equally spaced grid. certified: V(b_{k−1}) + V(b_{k+1}) >
    2·B_eff(b_k) (the true value at b_k is at most B_eff, and V is a lower bound at the ends, so
    the midpoint inequality of concavity fails for the true value function); uncertified: the same
    with V(b_k) in place of B_eff(b_k)."""
    b, V, Be = (np.asarray(a, float) for a in (bounds, V, B_eff))
    o = np.argsort(b)
    b, V, Be = b[o], V[o], Be[o]
    h = np.diff(b)
    if not np.allclose(h, h[0], rtol=1e-9, atol=0):
        raise ValueError("grid is not equally spaced")
    k = np.arange(1, len(b) - 1)
    lhs = V[k - 1] + V[k + 1]
    return pd.DataFrame({"k": k, "bound": b[k], "lhs_minus_2Beff": lhs - 2 * Be[k],
                         "lhs_minus_2V": lhs - 2 * V[k], "certified": lhs > 2 * Be[k],
                         "uncertified": lhs > 2 * V[k]})
