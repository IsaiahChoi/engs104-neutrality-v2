"""Finite-difference slopes of a relaxation's value function (DESIGN §6, perspective estimator a′;
the method CHECKS K29c gates before I1).

- Default, "central" (DESIGN §6): δ_r = REL_DELTA·b = 1e-3·b; the slope is the central difference
  (V(b+δ) − V(b−δ))/(2δ); the forward and backward two-point differences (V(b±δ) − V(b))/(±δ) are
  recorded, and the point is flagged as a kink if they differ by more than KINK_RTOL = 1e-4
  relative to the central slope (the rule of src.opt.sensitivity.envelope_point, at DESIGN's
  1e-4).
- Option, "three_point" (S2d item 2; not a default until GATE DESIGN): one-sided three-point
  differences, exact on quadratics,
      forward  s₊ = (−3V(b) + 4V(b+δ) − V(b+2δ))/(2δ)
      backward s₋ = ( 3V(b) − 4V(b−δ) + V(b−2δ))/(2δ),
  so on a piece of the A7 toy they are its one-sided derivatives. The slope is still the central
  difference; the kink flag is the same rule on |s₊ − s₋|.
- "design" (DESIGN §6 as edited at GATE DESIGN, Decision 38; the I1/I2 rule): the central slope
  ŝ is the estimate; the three-point one-sided slopes s₊, s₋ above are recorded as forward and
  backward, and the two-point differences as forward2 and backward2; with N = VALUE_RTOL·max(|V(b)|,
  |V_ref|)/δ, the point is flagged as a kink iff |s₊ − s₋| > max(KINK_RTOL·|ŝ|, 8N), and it is
  concave iff forward2 − backward2 ≤ 4N (each two-point difference moves by at most 2N). The
  two-point differences carry the concavity check because three-point slopes need not keep the
  concave ordering within 2δ of a kink. noise = 4N (either three-point slope), noise_central = N.
- Noise (a-priori). A relaxation value passes DESIGN §6's gap clause at |p − d| ≤ 1e-9·max(|V|,
  |V_ref|), so its value error is taken as ε = VALUE_RTOL·max(|V(b)|, |V_ref|) (V_ref defaults to
  V(b), the value at the unperturbed bound). Errors up to ε move a one-sided three-point slope by
  at most (3 + 4 + 1)ε/(2δ) = 4ε/δ, the noise term recorded for "three_point"; for "central" the
  one-sided two-point differences move by at most 2ε/δ (recorded as noise) and the central slope
  by ε/δ (noise_central).
- Concavity. A relaxation's value function is concave in a right-hand side b, so s₊ ≤ s₋ must
  hold up to the noise of the difference: concave = s₊ − s₋ ≤ 2·noise.
The arithmetic uses only +, −, ×, ÷ on the values, so Fractions stay exact (the closed-form tests).

relaxation_slope(pmi, key) evaluates the perspective relaxation (src.opt.relaxation, Clarabel) at
the stencil for one shadow-price key of a P-MI instance (dollar, beta, gross, style, sector,
style:<factor>, sector:<j>; a family key moves every element together) and restores the bounds.
Every point also records Clarabel's raw duals (CHECKS K29b, DESIGN §6; a diagnostic, never an
estimator): raw_dual for `key` and raw_duals_json for every key, dU*/db in original units, with
raw_duals_usable = the relaxation passed DESIGN §6 (a failed point keeps its duals, Decision 25).
V(b) is solved first and passed as V_ref to the other points' gap clause (the stencil rule of
DESIGN §6); a given v_ref (original units, e.g. the toy's U* as in K9) is used at every point
instead, and in the noise term. Values are in original units (÷ s_obj). If any point fails (DESIGN §6) the slope is nan, ok = False, and the first failed
point's reason is recorded; every point's status, residuals and gaps are recorded either way.
"""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass
from types import SimpleNamespace

import numpy as np

from src.opt.relaxation import GAP_RTOL, perspective_relaxation

METHODS = ("central", "three_point")
DESIGN_METHOD = "design"         # DESIGN §6 as edited at GATE DESIGN (module docstring)
ALL_METHODS = METHODS + (DESIGN_METHOD,)
REL_DELTA = 1e-3                 # δ_r = 1e-3·b (DESIGN §6)
KINK_RTOL = 1e-4                 # DESIGN §6: one-sided slopes differing by more = flagged
VALUE_RTOL = GAP_RTOL            # 1e-9: the value accuracy behind the noise term
OFFSETS = {"central": (-1, 0, 1), "three_point": (-2, -1, 0, 1, 2), "design": (-2, -1, 0, 1, 2)}
DESIGN_KINK_NOISE = 8            # kink floor 8N (DESIGN §6 as edited)
DESIGN_CONCAVE_NOISE = 4         # two-point concavity slack 4N


def stencil(b, rel_delta: float = REL_DELTA, method: str = "central", delta=None):
    """(δ, offsets): the points are b + k·δ for k in offsets; δ = rel_delta·b unless given."""
    if method not in ALL_METHODS:
        raise ValueError(f"method {method!r} not in {ALL_METHODS}")
    if delta is None:
        if not (np.isfinite(float(b)) and b > 0):
            raise ValueError(f"no relative step at bound {b}")
        delta = rel_delta * b
    return delta, OFFSETS[method]


def noise_term(V, V_ref, delta, value_rtol=VALUE_RTOL):
    """4·value_rtol·max(|V|, |V_ref|)/δ: the worst-case effect of value errors on a one-sided
    three-point slope (module docstring)."""
    return 4 * value_rtol * max(abs(V), abs(V_ref)) / delta


@dataclass(frozen=True)
class SlopeEstimate:
    method: str
    delta: object
    slope: object                # central difference
    forward: object              # one-sided: two-point (central) or three-point
    backward: object
    kink: bool                   # |forward − backward| > KINK_RTOL·|slope|
    concave: bool                # forward − backward ≤ 2·noise
    noise: object                # a-priori bound on either one-sided slope's value-error effect
    noise_central: object        # ... and on the central slope's
    diff: object                 # forward − backward
    forward2: object = None      # "design": the two-point differences (concavity check)
    backward2: object = None


def fd_slopes(values: dict, delta, method: str = "central", v_ref=None, rtol=KINK_RTOL,
              value_rtol=VALUE_RTOL) -> SlopeEstimate:
    """Slopes from stencil values {offset k: V(b + k·δ)} (module docstring). KeyError if a value
    the method needs is missing."""
    if method not in ALL_METHODS:
        raise ValueError(f"method {method!r} not in {ALL_METHODS}")
    v0 = values[0]
    vp, vm = values[1], values[-1]
    eps = value_rtol * max(abs(v0), abs(v_ref) if v_ref is not None else 0)
    slope = (vp - vm) / (2 * delta)
    if method == DESIGN_METHOD:
        N = eps / delta
        fwd = (-3 * v0 + 4 * vp - values[2]) / (2 * delta)
        bwd = (3 * v0 - 4 * vm + values[-2]) / (2 * delta)
        fwd2, bwd2 = (vp - v0) / delta, (v0 - vm) / delta
        diff = fwd - bwd
        return SlopeEstimate(method=method, delta=delta, slope=slope, forward=fwd, backward=bwd,
                             kink=bool(abs(diff) > max(rtol * abs(slope), DESIGN_KINK_NOISE * N)),
                             concave=bool(fwd2 - bwd2 <= DESIGN_CONCAVE_NOISE * N),
                             noise=4 * N, noise_central=N, diff=diff, forward2=fwd2, backward2=bwd2)
    if method == "central":
        fwd, bwd = (vp - v0) / delta, (v0 - vm) / delta
        noise = 2 * eps / delta
    else:
        fwd = (-3 * v0 + 4 * vp - values[2]) / (2 * delta)
        bwd = (3 * v0 - 4 * vm + values[-2]) / (2 * delta)
        noise = 4 * eps / delta
    diff = fwd - bwd
    return SlopeEstimate(method=method, delta=delta, slope=slope, forward=fwd, backward=bwd,
                         kink=bool(abs(diff) > rtol * abs(slope)), concave=bool(diff <= 2 * noise),
                         noise=noise, noise_central=eps / delta, diff=diff)


# ----- the perspective relaxation of a P-MI instance -----

def _apply(pmi, key: str, value: float) -> None:
    fam, _, tail = key.partition(":")
    if fam not in ("dollar", "beta", "gross", "style", "sector"):
        raise KeyError(key)
    if not tail:
        pmi.set_bound(fam, value)
    else:
        names = pmi.style_names or [str(k) for k in pmi.model.style_idx]
        pmi.set_bound(fam, value, names.index(tail) if fam == "style" else int(tail))


POINT_FIELDS = ("clarabel_status", "iterations", "r_prim", "r_dual", "gap_abs", "gap_rel",
                "clarabel_gap_rel", "gap_threshold", "fail_reason")


def relaxation_slope(pmi, key: str, b: float | None = None, rel_delta: float = REL_DELTA,
                     method: str = "central", opts: dict | None = None,
                     v_ref: float | None = None) -> dict:
    """The slope of the perspective relaxation's value in the bound behind `key` at b (default:
    the current bound), by `method` (module docstring). Returns a flat record with the stencil
    points under "points"."""
    b0 = pmi.bound_of(key) if b is None else float(b)
    delta, offsets = stencil(b0, rel_delta, method)
    s = pmi.s_obj
    saved = copy.deepcopy(pmi.model.bounds)
    vals, points, fail = {}, [], None
    try:
        for k in sorted(offsets, key=lambda k: (k != 0, k)):        # V(b) first: it is V_ref
            _apply(pmi, key, b0 + k * delta)
            ref = s * v_ref if v_ref is not None else (None if k == 0 else s * vals.get(0, np.nan))
            cl = perspective_relaxation(pmi.model, opts=opts,
                                        v_ref=ref if ref is not None and np.isfinite(ref) else None)
            info = cl.info
            value = info.get("value", np.nan) / s
            raw = ({kk: v / s for kk, v in pmi._shadows(SimpleNamespace(duals=cl.duals)).items()}
                   if cl.duals else {})
            points.append({"offset": k, "bound": b0 + k * delta, "ok": bool(cl.ok),
                           "status": cl.status, "value": value,
                           **{f: info.get(f) for f in POINT_FIELDS},
                           "raw_dual": raw.get(key, np.nan),
                           "raw_duals_json": json.dumps(raw, sort_keys=True),
                           "raw_duals_usable": bool(cl.ok)})
            if cl.ok:
                vals[k] = value
            elif fail is None:
                fail = info.get("fail_reason") or "status"
    finally:
        pmi.model.bounds = saved
    points.sort(key=lambda p: p["offset"])
    rec = {"key": key, "b": b0, "method": method, "rel_delta": rel_delta, "s_obj": s,
           "ok": fail is None, "fail_reason": fail, "V": vals.get(0, np.nan), "points": points,
           "v_ref": v_ref if v_ref is not None else vals.get(0, np.nan),
           "n_almost_solved": sum(p["clarabel_status"] == "AlmostSolved" for p in points)}
    if fail is None:
        est = fd_slopes(vals, delta, method=method, v_ref=v_ref)
        rec.update({k: (v if isinstance(v, (bool, str)) else np.nan if v is None else float(v))
                    for k, v in asdict(est).items() if k != "method"})
    else:
        rec.update(delta=delta, slope=np.nan, forward=np.nan, backward=np.nan, kink=False,
                   concave=False, noise=np.nan, noise_central=np.nan, diff=np.nan,
                   forward2=np.nan, backward2=np.nan)
    return rec
