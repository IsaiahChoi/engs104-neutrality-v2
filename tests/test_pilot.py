"""The pilot's rules (experiments/run_pilot.py; DESIGN §6, §8), on constructed inputs: the s_obj
rule, the P4 agreement criterion, P5's rounding, and P6's candidates and selection."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from experiments.run_pilot import (STYLE_NAMES, _key_bounds, choose_s_obj_centred, p4_agreement,
                                   p6_candidates, p6_select, round_sig)
from src.opt.continuous import load_config

PILOT = {"i1": {"dates": ["2009-03", "2017-12", "2020-03"]},
         "p6": {"n_families": 4, "mom_bound": 0.025}}


def test_s_obj_puts_the_geometric_mean_nearest_ten():
    out = choose_s_obj_centred([1.2e-3, 3.0e-3])                 # geometric mean 1.9e-3
    assert out["s_obj"] == 1e4 and out["proxies_inside"]
    assert out["proxy_min_scaled"] == pytest.approx(12.0) and out["proxy_max_scaled"] == pytest.approx(30.0)
    assert choose_s_obj_centred([0.05])["s_obj"] == 100.0        # 0.05·100 = 5, nearest 10 in log
    wide = choose_s_obj_centred([1e-4, 1e-1])                   # spans 3 decades: not all inside
    assert not wide["proxies_inside"]


def _solves(Vb, Bb, Vp, Bp):
    return pd.DataFrame([
        {"key": "k", "formulation": "bigm", "V": Vb, "B": Bb, "B_eff": max(Bb, Vb) + 1e-6 * abs(Vb),
         "gap_eff": np.nan, "status": "OPTIMAL"},
        {"key": "k", "formulation": "perspective", "V": Vp, "B": Bp,
         "B_eff": max(Bp, Vp) + 1e-6 * abs(Vp), "gap_eff": np.nan, "status": "OPTIMAL"}])


def test_p4_agreement_is_against_the_larger_certified_gap():
    ok = p4_agreement(_solves(1.0, 1.0 + 1e-4, 1.0 + 5e-5, 1.0 + 6e-5)).iloc[0]
    assert ok["pass"] and ok["allowed"] == pytest.approx(1e-4 + 1e-6)
    bad = p4_agreement(_solves(1.0, 1.0 + 1e-5, 1.0 + 5e-5, 1.0 + 6e-5)).iloc[0]
    assert not bad["pass"]                                    # 5e-5 apart, gaps ≈ 1e-5 each
    undefined = p4_agreement(_solves(np.nan, 1.0, 1.0, 1.0)).iloc[0]
    assert not undefined["pass"]                              # V undefined: not a pass


def test_round_sig():
    assert round_sig(1234.5) == 1200.0 and round_sig(0.0012345) == 0.0012
    assert round_sig(9.96e5) == 1.0e6


def test_key_bounds():
    assert _key_bounds("style:Mom", 0.03) == [("style", 0.03, STYLE_NAMES.index("Mom"))]
    assert _key_bounds("beta", 0.05) == [("beta", 0.05, None)]
    assert _key_bounds("style", 0.1) == [("style", 0.1, None)]
    with pytest.raises(KeyError):
        _key_bounds("position", 0.03)


def test_p6_candidates_rank_by_median_elasticity_and_add_mom():
    rows = []
    for ym in ["2009-03", "2017-12", "2020-03", "2011-08"]:
        for kind in ("mom", "perp"):
            base = 1.0 if ym != "2011-08" and kind == "mom" else 100.0   # other rows must not count
            rows.append({"month": ym, "alpha": kind, "e_dollar": 0.01 * base, "e_beta": 0.2 * base,
                         "e_style": 0.5 * base, "e_style:Mom": 0.3 * base, "e_sector": 0.4 * base,
                         "e_sector:3": 9.0 * base, "e_gross": 0.05 * base, "e_position": 5.0 * base,
                         "e_liquidity": 7.0 * base})
    base_m, _ = load_config()
    c = p6_candidates(pd.DataFrame(rows), PILOT, base_m)
    assert list(c["candidate"]) == ["style", "sector", "style:Mom", "beta", "style:Mom"]
    assert list(c["b"]) == [base_m.style, base_m.sector, base_m.style, base_m.beta, 0.025]
    assert list(c["is_factor"]) == [True, False, True, True, True]


def _iv(binding, factor):
    return pd.DataFrame({"candidate": [f"c{i}" for i in range(len(binding))],
                         "rank": range(len(binding)), "binding": binding, "is_factor": factor})


def test_p6_select_keeps_binding_in_order_with_a_factor_bound():
    keep, _ = p6_select(_iv([True, False, True, True, True], [False] * 4 + [True]), 4)
    assert keep == ["c0", "c2", "c3", "c4"]
    keep, note = p6_select(_iv([True] * 5, [False] * 4 + [True]), 4)
    assert keep == ["c0", "c1", "c2", "c4"] and "c4" in note   # the factor bound replaces c3
    keep, _ = p6_select(_iv([True] * 5, [True] + [False] * 4), 4)
    assert keep == ["c0", "c1", "c2", "c3"]
    assert p6_select(_iv([False] * 5, [True] * 5), 4)[0] == []
