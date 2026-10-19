"""The core runner's K9 summary helpers (experiments/run_core.py; CHECKS K9 as revised at a43c264,
Decisions 21, 22 and 22a in PROGRESS), on constructed rows.

- Decision 22: grid points with ℓ − FeasibilityTol ≤ b < ℓ are excluded from the value-function
  comparison and counted by formulation. Decision 22a: at each, where the incumbent holds the
  name (z = 1) the exact objective at its weights equals f(b) to 1e-12 relative; where it does
  not (w = 0), V equals the closed form (0) to 1e-8.
- Decision 22b: the band is also excluded from the fixed-integer-dual comparison (the exact
  fixed QP at an incumbent that holds the name below ℓ is infeasible); counted and listed.
- Decision 21: failed perspective relaxations are counted with their reasons, the value is
  compared on relaxations not failed, and K9 fails if more than 1% fail.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from experiments.run_core import _k9_band, _k9_fixed, _k9_persp, _k9_value_function, band_mask

ELL, FTOL = 0.01, 1e-6


def test_band_mask_is_half_open_below_ell():
    b = np.array([ELL - 2e-6, ELL - FTOL, ELL - 5e-7, ELL - 1e-15, ELL, ELL + 1e-9])
    np.testing.assert_array_equal(band_mask(b, ELL, FTOL), [False, True, True, True, False, False])


def _band_rows():
    """Three band points: (A) both incumbents hold the name, exact objective = f(b); (B) big-M
    took w = 0 with V = 0 = the closed form, perspective holds it; (C) a big-M incumbent off f(b)."""
    fb = np.array([5.6e-5, 2.7e-8, 1.2e-4])
    return pd.DataFrame({
        "toy": ["A", "B", "C"], "b": ELL - np.array([2.5e-8, 9.6e-7, 6.7e-8]), "band": True,
        "U_cf": 0.0, "f_b": fb,
        "zeta_inc_bigm": [1.0, 0.0, 1.0], "U_inc_bigm": [fb[0], 0.0, fb[2] * (1 + 1e-9)],
        "V_bigm": [np.nan, 0.0, np.nan],
        "zeta_inc_perspective": [1.0, 1.0, 1.0],
        "U_inc_perspective": fb * (1 + np.array([1e-16, -2e-16, 0.0])),
        "V_perspective": np.nan})


def test_band_check_either_test_by_formulation():
    out = _k9_band(_band_rows())
    assert out["n_points"] == 3
    bm, pe = out["bigm"], out["perspective"]
    assert (bm["n"], bm["n_holds_name"], bm["n_w0"], bm["n_V_undefined"]) == (3, 2, 1, 2)
    assert (pe["n"], pe["n_holds_name"], pe["n_w0"], pe["n_V_undefined"]) == (3, 3, 0, 3)
    assert pe["all_pass"] and pe["n_pass"] == 3
    assert 0 < pe["max_rel_err_exact_obj_vs_f_b"] <= 1e-15                # rounding of f(b)·(1 ± ε)
    assert not bm["all_pass"] and bm["n_pass"] == 2           # point C misses 1e-12
    assert bm["max_rel_err_exact_obj_vs_f_b"] == pytest.approx(1e-9, rel=1e-6)
    assert bm["max_abs_err_V_where_w0"] == 0.0
    assert [p["toy"] for p in bm["failed_points"]] == ["C"]


def test_band_check_w0_needs_V_equal_closed_form():
    rows = _band_rows().iloc[[1]].copy()
    rows["V_bigm"] = 1e-7                                     # w = 0 but V off the closed form
    assert not _k9_band(rows)["bigm"]["all_pass"]
    rows["V_bigm"] = np.nan                                   # w = 0 and V undefined
    assert not _k9_band(rows)["bigm"]["all_pass"]


def test_value_function_excludes_band_and_counts_undefined():
    rows = pd.DataFrame({
        "band": [False, False, True, False], "U_cf": [0.0, 1e-3, 0.0, 2e-3],
        "V_bigm": [0.0, 1e-3 + 5e-9, 5.6e-5, 2e-3], "V_perspective": [0.0, 1e-3, np.nan, np.nan]})
    out = _k9_value_function(rows)
    assert out["n_excluded_band"] == 1 and out["n_compared"] == 3
    assert out["bigm"] == {"n_V_undefined": 0, "max_abs_err": pytest.approx(5e-9),
                           "n_above_1e-8": 0, "pass": True}
    assert out["perspective"]["n_V_undefined"] == 1 and not out["perspective"]["pass"]


def _persp_rows(n_ok: int, n_failed: int):
    ok = np.r_[np.ones(n_ok, bool), np.zeros(n_failed, bool)]
    n = n_ok + n_failed
    cf = np.linspace(1.0, 2.0, n)
    return pd.DataFrame({
        "toy": [f"R{i:03d}" for i in range(n)], "b": np.linspace(0.1, 0.2, n),
        "persp_ok": ok, "persp_status": np.where(ok, "optimal", "clarabel relax duality gap ..."),
        "persp_fail_reason": np.where(ok, None, "gap"),
        "clarabel_status": "AlmostSolved", "R_persp_cf": cf, "value_scale": 2.0,
        "R_persp": np.where(ok, cf * (1 + 5e-10), np.nan),
        "R_persp_value": cf * (1 + 5e-10), "R_persp_clarabel_obj": cf * (1 + 2e-9),
        "gap_abs": np.where(ok, 1e-12, 1e-7), "gap_threshold": 1e-9 * cf,
        "r_prim": 1e-10, "r_dual": 1e-10})


def test_persp_summary_counts_failures_and_compares_not_failed():
    out = _k9_persp(_persp_rows(199, 1))
    assert out["n"] == 200 and out["n_failed"] == 1 and out["failed_reasons"] == {"gap": 1}
    assert out["failed_fraction"] == pytest.approx(0.005) and out["within_failure_cap"]
    assert out["max_rel_err_not_failed"] == pytest.approx(5e-10, rel=1e-3)
    assert out["n_not_failed_above_1e-9"] == 0
    assert out["diagnostic_clarabel_objective"]["n_above_1e-9"] == 200
    assert len(out["failed_points"]) == 1 and out["failed_points"][0]["reason"] == "gap"


def test_persp_failure_cap_is_one_percent():
    assert _k9_persp(_persp_rows(99, 1))["within_failure_cap"]          # exactly 1%
    assert not _k9_persp(_persp_rows(98, 2))["within_failure_cap"]      # 2% > 1%


def test_fixed_dual_excludes_band_and_lists_it():
    rows = pd.DataFrame({
        "toy": ["A", "B", "C", "D"], "b": [0.1, 0.2, ELL - 5e-7, 0.3], "a": 1.0,
        "kink": [False, False, False, True], "band": [False, False, True, False],
        "mu_fixed": [0.5 * (1 + 2e-7), 0.0, np.nan, np.nan], "cf_fixed": [0.5, 0.0, 0.0, 0.0],
        "fixed_status": ["OPTIMAL", "OPTIMAL", "fixed solve status INFEASIBLE", None]})
    out = _k9_fixed(rows)
    assert out["n_compared"] == 2 and out["n_excluded_band"] == 1
    assert out["excluded_band_points"] == [{"toy": "C", "b": ELL - 5e-7,
                                            "fixed_status": "fixed solve status INFEASIBLE"}]
    assert out["max_rel_err"] == pytest.approx(2e-7, rel=1e-6) and out["n_failed_outside_band"] == 0
    assert out["pass"]
    rows.loc[1, ["mu_fixed", "fixed_status"]] = [np.nan, "fixed solve status INFEASIBLE"]
    out = _k9_fixed(rows)                      # a failure off the band is counted and fails
    assert out["n_failed_outside_band"] == 1 and not out["pass"]
