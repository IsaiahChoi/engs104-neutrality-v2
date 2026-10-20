"""S2d pilot runner (experiments/run_pilot_s2d.py): written before the runner. The helpers that turn
solves into records: the toy's one-sided closed forms and kink neighbourhoods (item 2), the
cross-scale differences (items 2–3), the root-gap table against the stored S2b P4 data (item 1),
and the provenance checks."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import experiments.run_pilot_s2d as r
from experiments.designs import config
from src.opt.toy import Toy

T1 = Toy(a=1.0, lam=1.0, d=10.0, ell=0.02, u=0.08)          # w° = 0.05


def test_toy_one_sided_derivatives():
    a, ld = T1.a, T1.lam * T1.d
    assert r.toy_one_sided(T1, 0.01) == pytest.approx((a - ld * T1.ell, a - ld * T1.ell))
    assert r.toy_one_sided(T1, T1.ell) == pytest.approx((a - ld * T1.ell, a - 2 * ld * T1.ell))
    assert r.toy_one_sided(T1, 0.03) == pytest.approx((a - 2 * ld * 0.03,) * 2)
    assert r.toy_one_sided(T1, T1.w_opt) == pytest.approx((0.0, 0.0), abs=1e-15)
    assert r.toy_one_sided(T1, 0.07) == (0.0, 0.0)


def test_toy_classify_kink_neighbourhoods():
    d = 1e-3 * T1.ell
    c = r.toy_classify(T1, 0.03, 3e-5)
    assert c == {"near": "", "fwd_valid": True, "bwd_valid": True, "interior": True}
    up = r.toy_classify(T1, T1.ell + 0.5 * d, d)
    assert up["near"] == "ell" and up["fwd_valid"] and not up["bwd_valid"] and not up["interior"]
    dn = r.toy_classify(T1, T1.ell - 0.5 * d, d)
    assert dn["near"] == "ell" and dn["bwd_valid"] and not dn["fwd_valid"]
    at = r.toy_classify(T1, T1.ell, d)
    assert at["fwd_valid"] and at["bwd_valid"] and not at["interior"]
    dw = 1e-3 * T1.w_opt
    w = r.toy_classify(T1, T1.w_opt + 1.5 * dw, dw)
    assert w["near"] == "w_opt" and w["fwd_valid"] and not w["bwd_valid"]


@pytest.mark.parametrize("b", [0.01, 0.03, 0.02 + 1e-5, 0.07])
def test_toy_point_rows_with_clarabel(b):
    """One toy point at two scales: a record per scale with the three-point and central slopes,
    their errors against the closed form where it applies, the noise term (s-independent in
    original units) and Clarabel's statuses."""
    rows = r.toy_point_rows("T1", T1, b, scales=(1.0, 100.0), rel_delta=1e-3)
    assert [x["s"] for x in rows] == [1.0, 100.0]
    for x in rows:
        assert x["ok"], x
        assert x["noise3"] == pytest.approx(4e-9 * max(abs(x["V"]), T1.value(T1.w_opt)) / x["delta"])
        for e in ("err_central", "err_fwd3", "err_bwd3"):
            assert np.isnan(x[e]) or x[e] <= 1e-6, (e, x[e])
        assert x["interior"] == np.isfinite(x["err_central"])
        assert {"statuses", "max_r_prim", "max_r_dual", "max_gap_rel", "n_almost_solved",
                "kink3", "kink2", "concave3", "noise3_rel"} <= set(x)


def test_scale_diffs():
    df = pd.DataFrame({"inst": ["a"] * 3 + ["b"] * 3, "s": [1.0, 100.0, 1e4] * 2,
                       "value": [1.0, 1.0 + 1e-9, 1.0 - 2e-9, 2.0, 2.0, 2.0 + 4e-9]})
    out = r.scale_diffs(df, "inst", "value", refs=(1.0, 1e4))
    a = out[out["inst"] == "a"].set_index("s")
    assert a.loc[100.0, "rel_diff_vs_s1"] == pytest.approx(1e-9, rel=1e-6)
    assert a.loc[1e4, "rel_diff_vs_s10000"] == 0.0
    assert a.loc[1.0, "rel_diff_vs_s10000"] == pytest.approx(2e-9 / (1 - 2e-9), rel=1e-6)
    assert out.loc[out["inst"] == "b", "max_pairwise_rel_diff"].iloc[0] == pytest.approx(2e-9, rel=1e-6)


def test_rootgap_table():
    """Root gaps (bound − V)/|V| against the combined V (the larger polished V of big-M and the
    default perspective), the A6 margin of the plain relaxations, and reproduction of the stored
    root bounds by the default probes."""
    stored = pd.DataFrame({"key": ["k"] * 3, "arm": ["bigm", "perspective", "perspective_rescaled"],
                           "V": [1.0, 0.99, 1.0], "root_bound": [1.01, 1.10, 1.005],
                           "cone_effect_rel": [np.nan, 0.004, 0.0], "B": [1.0001, 1.003, 1.0001]})
    plain = pd.DataFrame({"key": ["k"], "bigm": [1.02], "perspective": [1.004],
                          "perspective_gurobi_barrier": [1.0041]})
    probes = pd.DataFrame({"key": ["k"] * 3, "probe": ["bigm", "perspective", "perspective_rescaled"],
                           "first": [1.02, 1.11, 1.006], "last": [1.01, 1.10, 1.005]})
    t = r.rootgap_table(stored, plain, probes).set_index("key").loc["k"]
    assert t["V_comb"] == 1.0 and t["V_best3"] == 1.0
    assert t["gap_root_stored_perspective"] == pytest.approx(0.10)
    assert t["gap_plain_bigm"] == pytest.approx(0.02) and t["gap_plain_perspective"] == pytest.approx(0.004)
    assert t["a6_margin_plain"] == pytest.approx(0.016) and t["a6_holds_plain"]
    assert not t["a6_holds_root_stored"]                      # the recorded root bounds break A6
    assert t["gap_probe_first_perspective"] == pytest.approx(0.11)
    assert t["probe_last_vs_stored_perspective"] == 0.0
    assert t["cut_tightening_bigm"] == pytest.approx(0.01)    # (plain − last)/|V|
    assert t["first_minus_plain_perspective"] == pytest.approx(0.106)


def test_provenance_checks():
    cfg = config("pilot_s2d")
    prov = r.check_s2b(cfg)
    assert prov["s_obj"] == 1e4 and prov["W_star"] == 340.0 and prov["hashes_match"]
    with pytest.raises(ValueError):
        r.check_s2b({**cfg, "s_obj": 1e3})


def test_makefile_has_the_runner():
    from src.utils import ROOT
    line = next(l for l in (ROOT / "Makefile").read_text().splitlines() if l.startswith("RUNNERS"))
    assert "pilot_s2d" in line.split()
