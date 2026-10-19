"""v2 sweep machinery (ported from v1 run_rq1.py: build, snapshot, apply_point, reset) on P-RB,
the swept-cap shadow-price regression (CHECKS K12; v1 tests/removed_from_test_opt.py, last test),
and the envelope self-check (ported from v1 check_rq1_envelope.py)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from experiments.check_envelope import envelope_check, sp_key
from experiments.sweep import (C2_GRIDS, apply_point, build, reset, snapshot, sweep_date)
from src.opt.attribution import shadow_prices
from src.opt.risk_budget import solve_risk_budget
from src.opt.sensitivity import fd_slope_rb
from tests import realdata

YM = "2020-03"


def test_c2_grids_match_design():
    """DESIGN §7 C2 table (None = off); the base value is in every grid."""
    assert C2_GRIDS["dollar"] == [None, 0.10, 0.05, 0.02, 0.01, 0.0]
    assert C2_GRIDS["beta"] == [None, 0.20, 0.10, 0.05, 0.02, 0.0]
    assert C2_GRIDS["style_all"] == [None, 0.40, 0.20, 0.10, 0.05, 0.02, 0.0]
    assert C2_GRIDS["style:Mom"] == C2_GRIDS["style_all"]
    assert C2_GRIDS["sector"] == [None, 0.08, 0.04, 0.02, 0.01, 0.0]
    assert C2_GRIDS["gross"] == [None, 4.0, 3.0, 2.0, 1.5, 1.0]
    assert C2_GRIDS["position"] == [None, 0.06, 0.03, 0.015]
    assert C2_GRIDS["liquidity"] == [None, 0.10, 0.05, 0.025]
    assert len([k for k in C2_GRIDS if k.startswith("style:")]) == 5


@pytest.fixture(scope="module")
def caps_sweep():
    di, alpha, base = realdata.case(YM)
    pts, w = sweep_date(di, alpha, "mom", base, C2_GRIDS, families={"position", "liquidity"})
    return di, alpha, base, pts, w


def _fd_at_point(di, alpha, base, family, value):
    P = build(di, base)["base"]
    apply_point(P, base, family, value)
    lam = solve_risk_budget(P, alpha).lam
    return fd_slope_rb(P, alpha, sp_key(family), rel_step=1e-3, lam_guess=lam)


def test_k12_shadow_prices_at_swept_caps(caps_sweep):
    """At swept u and θ values the recorded position and liquidity shadow prices match central
    finite differences of A* in that cap (within 1%), at ≥ 2 binding points."""
    di, alpha, base, pts, _ = caps_sweep
    checked = 0
    for _, r in pts[~pts["off"] & ~pts["is_base"]].iterrows():
        sp = r[f"sp_{sp_key(r['family'])}"]
        if not sp > 1e-7:
            continue
        fd = _fd_at_point(di, alpha, base, r["family"], r["value"])
        assert fd == pytest.approx(sp, rel=0.01), r["point_id"]
        checked += 1
    assert checked >= 2


def test_k12_negative_control_reset_before_record_is_wrong(caps_sweep):
    """The v1 bug: shadow prices read after resetting the caps to base are not the slopes at
    the swept cap. The regression test above would catch it."""
    di, alpha, base, pts, _ = caps_sweep
    P = build(di, base)["base"]
    snap = snapshot(P)
    apply_point(P, base, "liquidity", 0.025)
    sol = solve_risk_budget(P, alpha).sol
    reset(P, snap)                                         # the bug: reset, then record
    wrong = shadow_prices(P, sol)["liquidity"]
    right = pts.loc[(pts["family"] == "liquidity") & (pts["value"] == 0.025), "sp_liquidity"].item()
    assert right > 1e-7 and abs(wrong / right - 1) > 0.01


def test_sweep_rows_are_complete_and_feasible(caps_sweep):
    _, _, _, pts, w = caps_sweep
    assert len(pts) == 8 and pts["risk_binding"].all()
    assert (pts["feasibility_violations"] == "{}").all()
    a_base = pts.loc[pts["is_base"], "A"]                               # both base points agree
    assert len(a_base) == 2 and a_base.max() / a_base.min() - 1 <= 1e-9
    assert {"lam", "A", "vol_ann", "n_solves", "tc", "e_position", "binding"} <= set(pts.columns)
    assert set(w["point_id"]) == set(pts["point_id"])
    for _, r in pts.iterrows():
        assert abs(r["vol_ann"] / 0.03 - 1) <= 1e-10


def test_envelope_self_check_and_negative_control():
    di, alpha, base = realdata.case(YM)
    grids = {"sector": [0.04, 0.02, 0.01], "liquidity": [0.10, 0.05, 0.025]}   # bind at 2020-03
    pts, _ = sweep_date(di, alpha, "mom", base, grids)

    def rebuild(row):
        P = build(di, base)["base"]
        apply_point(P, base, row["family"], row["value"])
        return P, alpha

    out = envelope_check(pts, rebuild, n=4, seed=0)
    assert len(out) >= 2 and out["within"].all()
    bad = pts.copy()
    k = bad.index[bad["family"] == "liquidity"][1]
    bad.loc[k, "sp_liquidity"] *= 1.10                                  # corrupt one stored price
    flagged = envelope_check(bad.loc[[k]], rebuild, n=1, seed=0)
    assert not flagged["within"].any()
