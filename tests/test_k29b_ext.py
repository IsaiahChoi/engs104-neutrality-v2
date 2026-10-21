"""S3b item 2 (GATE I note, Decision 45): K29b extended, as a diagnostic, to every I1 case K29b did
not cover (experiments/run_k29b_ext.py, config experiments/configs/k29b_ext.yaml), tests first.

- The cases: every I1 case except K29b's (the first 3 instances by sorted id at the main δ):
  the 6 instances at 2017-12 and 2020-03 at δ = 10% (24 cases) and the 12 at 2017-12 at δ = 5%,
  36 in all; together with K29b's 12 they are the 48 I1 cases.
- Each case: the perspective-relaxation slope by I1's rule (DESIGN §6, src.opt.slopes "design",
  5-point stencil) at s_obj and at scale_factor·s_obj, from a fresh P-MI at the case's bound;
  at s_obj it reproduces I1's own slope bit for bit.
- The criterion is K29b's: |ŝ(10·s_obj) − ŝ(s_obj)| ≤ 1e-5·|ŝ| + 2N, N at s_obj.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import experiments.run_i1 as i1
import experiments.run_k29b_ext as X
import experiments.s3 as s3
from experiments.designs import config

SMALL = {"date": "2017-12", "N": 30, "f": 0.5}


def test_config_is_its_own_file_and_reads_integer_yaml():
    c = config("k29b_ext")
    assert c["runner"] == "k29b_ext" and c["source_config"] == "integer"
    assert c["scale_factor"] == 10.0 and c["n_cases_expected"] == 36


def test_ext_cases_are_every_i1_case_k29b_did_not_cover():
    icfg = config("integer")
    cases = X.ext_cases(icfg)
    assert len(cases) == 36
    k29b = i1.k29b_instances(icfg)
    main = float(icfg["i1"]["rel_delta"])
    ids = lambda c: i1.instance_id(c["date"], icfg["i1"]["N"], c["f"], c["K"])
    assert not any(ids(c) in k29b and c["rel_delta"] == main for c in cases)
    n = pd.Series([(c["date"], c["rel_delta"]) for c in cases]).value_counts().to_dict()
    assert n == {("2017-12", 0.10): 12, ("2020-03", 0.10): 12, ("2017-12", 0.05): 12}
    covered = {(i, c["key"]) for i in k29b for c in icfg["i1"]["constraints"]}
    assert len(covered) == 12 and len(cases) + len(covered) == len(i1.plan(icfg))


def test_case_count_guard():
    with pytest.raises(ValueError, match="36"):
        X.check_count([{}] * 35, 36)
    X.check_count([{}] * 36, 36)


@pytest.fixture(scope="module")
def small_task():
    inst = s3.instance(SMALL["date"], SMALL["N"], SMALL["f"])
    cfg = config("integer")
    return i1.make_task(cfg, inst, {"key": "sector", "b": 0.02}, rel_delta=0.10, f=SMALL["f"],
                        k29b_scale=10.0)


def test_ext_task_records_both_scales_and_reproduces_i1(small_task):
    out = X.ext_task(small_task)
    e = out["k29b_ext"].iloc[0]
    assert e["id"] == small_task["id"] and e["k29b_scale"] == 10.0
    assert np.isfinite(e["persp_slope"]) and np.isfinite(e["persp_slope_k29b"])
    assert np.isfinite(e["persp_noise_central"]) and e["persp_ok"] and e["persp_ok_k29b"]
    sp = out["k29b_ext_points"]
    assert len(sp[sp["scale_factor"] == 1.0]) == 5 and len(sp[sp["scale_factor"] == 10.0]) == 5
    assert {"status", "r_prim", "r_dual", "raw_dual", "raw_duals_json", "raw_duals_usable"} <= set(sp.columns)
    ref = i1.i1_task(small_task)["i1_estimators"].iloc[0]          # I1's own records for this case
    assert e["persp_slope"] == ref["persp_slope"]                    # bit for bit
    assert e["persp_slope_k29b"] == ref["persp_slope_k29b"]


def test_verdict_applies_k29b_rule():
    df = pd.DataFrame({"instance": ["a", "b", "c"], "persp_slope": [1e-3, 1e-3, 1e-3],
                       "persp_slope_k29b": [1e-3 * (1 + 5e-6), 1e-3 * (1 + 2e-5), np.nan],
                       "persp_noise_central": [1e-12] * 3, "persp_ok": [True, True, True],
                       "persp_ok_k29b": [True, True, False], "k29b_scale": [10.0] * 3})
    v = X.verdict(df)
    assert v["n"] == 2 and v["n_failed"] == 1 and v["misses"] == 1 and not v["pass"]
    assert X.verdict(df.iloc[:1])["pass"]
