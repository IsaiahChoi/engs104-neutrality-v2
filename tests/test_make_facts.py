"""tools/make_facts.py (S2c; Isaiah's Decision 32): the P4 and P6 facts come from the S2b pilot
run, the S2 pilot's P4, P6 and P7 are never cited, the C1 attribution shares use attribution.py's
identity (total = α'w_α − α'w*), and the P7 projection is plain arithmetic on recorded Work.
Unit tests on synthetic tables; one integration test on the stored runs."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest

from tools import make_facts as mf


# ----- P4: per-arm statistics -----

def _p4_tables():
    rows = []
    # key k1: V_best = 1.0 (rescaled); key k2: V_best = 2.0 (big-M and perspective tie)
    for key, arm, V, B, cone, work in [
            ("k1", "bigm", 0.99, 1.0, np.nan, 1.0),
            ("k1", "perspective", 0.98, 1.01, 0.002, 2.0),
            ("k1", "perspective_rescaled", 1.0, 1.0001, 0.0, 0.5),
            ("k2", "bigm", 2.0, 2.0002, np.nan, 3.0),
            ("k2", "perspective", 2.0, 2.01, 0.004, 4.0),
            ("k2", "perspective_rescaled", 1.9, 2.0, 1e-11, 0.7)]:
        rows.append(dict(key=key, arm=arm, V=V, B=B, cone_effect_rel=cone, work=work))
    solves = pd.DataFrame(rows)
    agreement = pd.DataFrame([
        dict(key="k1", arm="perspective", ratio=0.5, **{"pass": True}),
        dict(key="k2", arm="perspective", ratio=0.9, **{"pass": True}),
        dict(key="k1", arm="perspective_rescaled", ratio=0.1, **{"pass": True}),
        dict(key="k2", arm="perspective_rescaled", ratio=1.3, **{"pass": False})])
    return solves, agreement


def test_p4_arm_stats_recomputes_gaps_and_shortfall_from_V_and_B():
    solves, agreement = _p4_tables()
    st = mf.p4_arm_stats(solves, agreement)
    assert list(st) == mf.P4_ARMS
    bm, pe, pr = st["bigm"], st["perspective"], st["perspective_rescaled"]
    # (B − V)/|V| against the arm's own polished V
    assert bm["max_gap_exact_rel"] == pytest.approx(max(0.01 / 0.99, 0.0002 / 2.0))
    assert pe["max_gap_exact_rel"] == pytest.approx(max(0.03 / 0.98, 0.01 / 2.0))
    assert pr["max_gap_exact_rel"] == pytest.approx(max(0.0001 / 1.0, 0.1 / 1.9))
    # shortfall (V_best − V)/|V_best|, V_best over the three arms at the same instance
    assert bm["max_shortfall_rel"] == pytest.approx(0.01)
    assert pe["max_shortfall_rel"] == pytest.approx(0.02)
    assert pr["max_shortfall_rel"] == pytest.approx(0.05)
    # cone effect: none for big-M; the max otherwise
    assert np.isnan(bm["max_cone_rel"])
    assert pe["max_cone_rel"] == pytest.approx(0.004) and pr["max_cone_rel"] == pytest.approx(1e-11)
    assert (bm["median_work"], pe["median_work"], pr["median_work"]) == (2.0, 3.0, 0.6)
    # agreement with big-M: big-M is the reference arm
    assert bm["n_agree"] is None and bm["worst_ratio"] is None
    assert (pe["n_agree_pass"], pe["n_agree"], pe["worst_ratio"]) == (2, 2, 0.9)
    assert (pr["n_agree_pass"], pr["n_agree"], pr["worst_ratio"]) == (1, 2, 1.3)
    assert all(st[a]["n"] == 2 for a in mf.P4_ARMS)


# ----- P6: combined certification, per candidate -----

def test_p6_candidate_rows_report_interval_and_suppliers():
    iv = pd.DataFrame([
        dict(candidate="sector", b=0.02, rank=0, L=1e-3, H=1.1e-3, s=1.05e-3, binding=True,
             v_from_plus="bigm", v_from_minus="perspective", b_from_plus="bigm",
             b_from_minus="bigm"),
        dict(candidate="style:Mom", b=0.025, rank=1, L=-1e-7, H=1e-7, s=0.0, binding=False,
             v_from_plus="bigm", v_from_minus="bigm", b_from_plus="perspective",
             b_from_minus="bigm")])
    pts = pd.DataFrame([
        dict(candidate="sector", b=0.02, sign=1, v_tie=True),
        dict(candidate="sector", b=0.02, sign=-1, v_tie=False),
        dict(candidate="style:Mom", b=0.025, sign=1, v_tie=False),
        dict(candidate="style:Mom", b=0.025, sign=-1, v_tie=False)])
    rows = mf.p6_candidate_rows(iv, pts)
    assert [r["label"] for r in rows] == ["sector@0.02", "style:Mom@0.025"]
    r0, r1 = rows
    assert (r0["L"], r0["H"], r0["s"], r0["binding"]) == (1e-3, 1.1e-3, 1.05e-3, True)
    assert (r0["v_plus"], r0["v_minus"], r0["b_plus"], r0["b_minus"]) == (
        "bigm", "perspective", "bigm", "bigm")
    assert r0["n_v_tie"] == 1 and r1["n_v_tie"] == 0
    assert r1["b_plus"] == "perspective" and not r1["binding"]


# ----- C1: attribution shares (attribution.py's identity) -----

def _attribution(total_shift: float = 0.0):
    fams = mf.ATTRIBUTION_FAMILIES
    losses = {"2017-12-29": dict(zip(fams, [1.0, 0.0, 0.0, 2.0, 0.0, 4.0, 1.0, 2.0, 0.0])),
              "2020-03-31": dict(zip(fams, [3.0, 0.0, 0.0, 1.0, 0.0, 2.0, 1.0, 2.0, 1.0]))}
    attr = []
    for d, fl in losses.items():
        attr += [dict(date=d, alpha="mom", family=f, loss=v) for f, v in fl.items()]
        attr.append(dict(date=d, alpha="mom", family="residual", loss=1e-18))
        attr += [dict(date=d, alpha="perp", family=f, loss=99.0) for f in fams]
    attr = pd.DataFrame(attr)
    points = pd.DataFrame([
        dict(date="2017-12-29", alpha="mom", is_base=True, alpha_ideal=12.0 + total_shift,
             alpha_total=2.0),
        dict(date="2020-03-31", alpha="mom", is_base=True, alpha_ideal=15.0, alpha_total=5.0),
        dict(date="2017-12-29", alpha="perp", is_base=True, alpha_ideal=1.0, alpha_total=0.0)])
    return attr, points


def test_attribution_families_are_attribution_py_family_order():
    from src.opt.attribution import FAMILY_ORDER
    assert mf.ATTRIBUTION_FAMILIES == FAMILY_ORDER


def test_attribution_shares_use_alpha_w_alpha_minus_alpha_w_star():
    attr, points = _attribution()
    sh = mf.attribution_shares(attr, points, alpha="mom")
    assert list(sh.index) == mf.ATTRIBUTION_FAMILIES
    # totals α'w_α − α'w* = 10 at both dates
    assert sh.loc["position", "median"] == pytest.approx(0.3)
    assert sh.loc["position", "min"] == pytest.approx(0.2)
    assert sh.loc["position", "max"] == pytest.approx(0.4)
    assert sh.loc["dollar", "min"] == pytest.approx(0.1) and sh.loc["dollar", "max"] == pytest.approx(0.3)
    assert sh.loc["inactive", "max"] == pytest.approx(0.1)
    assert (sh["n"] == 2).all()
    # every date's shares sum to 1
    assert sh.attrs["max_abs_share_sum_minus_1"] == pytest.approx(0.0, abs=1e-15)
    assert sh.attrs["max_abs_residual_share"] == pytest.approx(1e-19)


def test_attribution_shares_refuse_a_broken_identity():
    attr, points = _attribution(total_shift=1e-3)
    with pytest.raises(ValueError, match="identity"):
        mf.attribution_shares(attr, points, alpha="mom")


# ----- P7: projection arithmetic -----

INTEGER_CFG = {"i1": {"dates": ["a", "b", "c"], "f": [0.25, 0.5, 0.75],
                      "constraints": [{"key": "x"}] * 4, "certification": "combined",
                      "formulations": ["bigm", "perspective"],
                      "robustness": {"date": "b", "rel_delta": 0.05}},
               "i2": {"instances": [{}, {}], "points": 41, "certification": "combined"}}
NUMERICS_CFG = {"n1": {"dates": ["a", "b"], "N": [100, 250, "full"], "f": [0.25, 0.5],
                       "tightness": {"loose": {}, "base": {}, "tight": {}},
                       "formulations": ["bigm", "perspective", "perspective_rescaled"],
                       "presolve_off": {"N": 250}},
                "n2": {"miqp": {"s_obj": [1.0, 1e4],
                                "formulations": ["bigm", "perspective", "perspective_rescaled"]}}}


def test_p7_solve_counts():
    t = mf.p7_projection(rate=2.0, W_star=100.0, workers=4,
                         work_integer=pd.Series([1.0]), work_numerics=pd.Series([1.0]),
                         integer_cfg=INTEGER_CFG, numerics_cfg=NUMERICS_CFG).set_index("experiment")
    # I1: 3 dates × 3 f × (2·4 + 1) points + 3 f × 2·4 robustness points = 105, × 2 formulations
    assert t.loc["I1", "n_points"] == 105 and t.loc["I1", "n_miqp_solves"] == 210
    assert t.loc["I2", "n_points"] == 82 and t.loc["I2", "n_miqp_solves"] == 164
    # N1: 36 instances × 3 arms + 12 presolve-off instances (N = 250) × 3 arms
    assert t.loc["N1", "n_miqp_solves"] == 144
    # N2(a): 4 instances × 3 arms × 2 objective scales
    assert t.loc["N2a", "n_miqp_solves"] == 24
    assert t.loc["I1", "work_limit_per_solve"] == 200.0 and t.loc["N1", "work_limit_per_solve"] == 100.0


def test_p7_hours_are_work_over_rate_and_workers():
    t = mf.p7_projection(rate=2.0, W_star=100.0, workers=4,
                         work_integer=pd.Series([1.0, 3.0, 500.0]),   # median 3; 500 capped at 200
                         work_numerics=pd.Series([0.5, 0.7, 0.9, 1.1]),
                         integer_cfg=INTEGER_CFG, numerics_cfg=NUMERICS_CFG).set_index("experiment")
    assert t.loc["I1", "work_per_solve_expected"] == 3.0
    assert t.loc["N1", "work_per_solve_expected"] == pytest.approx(0.8)
    assert t.loc["I1", "hours_expected"] == pytest.approx(210 * 3.0 / 2.0 / 4 / 3600)
    assert t.loc["I1", "hours_worst"] == pytest.approx(210 * 200.0 / 2.0 / 4 / 3600)
    assert t.loc["N2a", "hours_worst"] == pytest.approx(24 * 100.0 / 2.0 / 4 / 3600)
    capped = mf.p7_projection(rate=2.0, W_star=100.0, workers=4,
                              work_integer=pd.Series([500.0]), work_numerics=pd.Series([500.0]),
                              integer_cfg=INTEGER_CFG, numerics_cfg=NUMERICS_CFG).set_index("experiment")
    assert capped.loc["I1", "work_per_solve_expected"] == 200.0
    assert capped.loc["N1", "work_per_solve_expected"] == 100.0


# ----- integration: the stored runs -----

def test_facts_cite_s2b_for_p4_p6_and_never_the_superseded_s2_items(tmp_path):
    try:
        lines = mf.build(tmp_path / "FACTS.md")
    except SystemExit as e:
        pytest.skip(f"stored runs not available: {e}")
    text = (tmp_path / "FACTS.md").read_text()
    facts = [ln for ln in lines if ln.startswith("- ")]
    s2 = re.compile(r"results/pilot/run_\d{8}T\d{6}Z")
    for ln in facts:
        body = ln[2:]
        if re.match(r"P(4|6)\b", body):          # superseded in S2: no S2 source at all
            assert not s2.search(ln), ln
    # nothing anywhere from S2's P4, P6 or P7 files; P7 may cite S2's summary.json for P5's
    # Work rate (P5 stands, Decision 32)
    assert not re.search(r"results/pilot/run_\d{8}T\d{6}Z/p(4|6|7)", text)
    p4 = [ln for ln in facts if ln[2:].startswith("P4")]
    assert {a for a in mf.P4_ARMS if any(f"P4, {a}:" in ln for ln in p4)} == set(mf.P4_ARMS)
    assert all("results/pilot_s2b/run_" in ln for ln in p4)
    p6 = [ln for ln in facts if ln[2:].startswith("P6")]
    assert p6 and all("results/pilot_s2b/run_" in ln for ln in p6)
    assert any("decided at GATE DESIGN" in ln for ln in p6)
    p7 = [ln for ln in facts if ln[2:].startswith("P7")]
    assert len(p7) == 1 and "projection" in p7[0] and "results/pilot_s2b/run_" in p7[0]
    assert all(m == "summary.json" for m in re.findall(
        r"results/pilot/run_\d{8}T\d{6}Z/(\S+?)`", p7[0]))
    assert any("α'w_α − α'w*" in ln and "attribution" in ln for ln in facts)
