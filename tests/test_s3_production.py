"""S3 production runners under the configs approved at GATE DESIGN (S3 step 1), tests first.

- integer.yaml / numerics.yaml are approved: production runs are accepted (RUN_LOG "ok").
- I1/I2: combined certification over big-M and the rescaled perspective (DESIGN §6); the
  perspective slope by DESIGN §6's edited rule (5-point stencil, src.opt.slopes "design");
  the baseline is fixed_lambda only (Decision 35); CHECKS K29b's 10·s_obj slopes on the first 3
  I1 instances by sorted instance id; I2 records the baseline's K15-rule slope (CHECKS K27).
- CHECKS K26: every P-MI solve records the raw incumbent's verdict at Gurobi's tolerances
  (FeasibilityTol 1e-6, IntFeasTol 1e-5) at the solve's current bounds.
- N1: the plain relaxations once per instance (CHECKS K24) and the K25 determinism reruns.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

import experiments.run_i1 as i1
import experiments.run_i2 as i2
import experiments.run_n1 as n1
import experiments.s3 as s3
from experiments.designs import config
from src.opt.integer import PMI, incumbent_verdict

SMALL = {"date": "2017-12", "N": 30, "f": 0.5}


@pytest.fixture(scope="module")
def inst():
    return s3.instance(SMALL["date"], SMALL["N"], SMALL["f"])


@pytest.mark.parametrize("runner", ["i1", "i2", "n1", "n2"])
def test_approved_configs_run_as_production(runner):
    path, cfg, status = s3.load_run_config(runner, [])
    assert status == "ok" and cfg["status"].startswith("approved at GATE DESIGN")
    assert path == f"experiments/configs/{s3.DEFAULT_CONFIG[runner]}.yaml"


def test_i1_config_is_the_gate_design_set():
    c = config("integer")["i1"]
    assert c["certification"] == "combined" and c["formulations"] == ["bigm", "perspective_rescaled"]
    assert [(x["key"], x["b"]) for x in c["constraints"]] == [
        ("sector", 0.02), ("dollar", 0.02), ("style", 0.10), ("style:Mom", 0.025)]
    assert c["baseline_kinds"] == ["fixed_lambda"] and c["perspective_slope_method"] == "central"
    assert len(i1.plan(config("integer"))) == 9 * 4 + 3 * 4


def test_slope_rule_maps_central_to_design():
    assert s3.slope_rule("central") == "design" and s3.slope_rule("three_point") == "three_point"
    with pytest.raises(ValueError):
        s3.slope_rule("five_point")


def test_k29b_instances_are_the_first_three_by_sorted_id():
    cfg = config("integer")
    ids = i1.instance_ids(cfg)
    assert len(ids) == 9 and ids == sorted(ids)
    assert i1.k29b_instances(cfg) == set(ids[:3])
    assert all(x.startswith("2009-03_N250_") for x in ids[:3])


def test_incumbent_verdict_gurobi_tolerances_at_current_bounds(inst):
    """Rows at FeasibilityTol 1e-6 and z at IntFeasTol 1e-5, against the bounds the solve used."""
    P = PMI(**inst.kwargs, formulation="bigm", s_obj=1e4)
    r = P.solve(mip_gap=1e-4)
    assert incumbent_verdict(P, r.w_incumbent, r.zp, r.zm) == "{}"
    dollar = float(np.sum(r.w_incumbent))
    w = r.w_incumbent.copy()
    j = int(np.argmax(np.abs(w)))
    P.set_bound("dollar", abs(dollar) + 0.0)
    w2 = w.copy()
    w2[j] += np.sign(dollar or 1.0) * 5e-7                        # 5e-7 over: inside 1e-6
    v = json.loads(incumbent_verdict(P, w2, r.zp, r.zm))
    assert "dollar" not in v
    w3 = w.copy()
    w3[j] += np.sign(dollar or 1.0) * 3e-6                        # 3e-6 over: a violation
    assert "dollar" in json.loads(incumbent_verdict(P, w3, r.zp, r.zm))
    zp = r.zp.astype(float).copy()
    k = int(np.argmax(zp))
    zp[k] -= 5e-6                                                 # inside IntFeasTol
    assert "binary" not in json.loads(incumbent_verdict(P, w, zp, r.zm))
    zp[k] -= 2e-5
    assert "binary" in json.loads(incumbent_verdict(P, w, zp, r.zm))


def test_i1_task_production_records(inst):
    cfg = config("integer")
    t = i1.make_task(cfg, inst, {"key": "sector", "b": 0.02}, rel_delta=0.10, f=SMALL["f"],
                     k29b_scale=10.0)
    assert t["slope_method"] == "design" and t["baseline_kinds"] == ["fixed_lambda"]
    out = i1.i1_task(t)
    sv = out["i1_solves"]
    assert set(sv["arm"]) == {"bigm", "perspective_rescaled"} and len(sv) == 6
    assert sv.loc[sv["arm"] == "perspective_rescaled", "rescale"].all()
    assert not sv.loc[sv["arm"] == "bigm", "rescale"].any()
    assert (sv["polished_violations"] == "{}").all()
    assert "incumbent_verdict" in sv.columns and sv["incumbent_verdict"].notna().all()
    pts = out["i1_points"]
    assert set(pts["v_from"]) <= {"bigm", "perspective_rescaled"}
    assert set(pts["b_from"]) <= {"bigm", "perspective_rescaled"}
    e = out["i1_estimators"].iloc[0]
    assert e["persp_method"] == "design"
    assert {"persp_forward2", "persp_backward2", "persp_slope_k29b", "persp_ok_k29b",
            "k29b_scale"} <= set(e.index)
    assert e["k29b_scale"] == 10.0 and np.isfinite(e["persp_slope_k29b"])
    sp = out["i1_slope_points"]
    assert len(sp[sp["scale_factor"] == 1.0]) == 5 and len(sp[sp["scale_factor"] == 10.0]) == 5
    b = out["i1_baseline"]
    assert list(b["kind"]) == ["fixed_lambda"] and (b["checker"] == "{}").all()


def test_i1_task_without_k29b(inst):
    cfg = config("integer")
    t = i1.make_task(cfg, inst, {"key": "dollar", "b": 0.02}, rel_delta=0.10, f=SMALL["f"])
    out = i1.i1_task(t)
    e = out["i1_estimators"].iloc[0]
    assert np.isnan(e["k29b_scale"]) and np.isnan(e["persp_slope_k29b"])
    assert set(out["i1_slope_points"]["scale_factor"]) == {1.0}


def test_i2_task_records_baseline_envelope_slope(inst):
    cfg = {**config("integer")}
    cfg["i2"] = {**cfg["i2"], "constraint": {"key": "sector", "b": 0.02}}
    t = i2.make_task(cfg, inst, {"key": "sector", "b": 0.02}, b=0.02, estimator=True)
    assert t["slope_method"] == "design" and t["formulations"] == ["bigm", "perspective_rescaled"]
    out = i2.i2_task(t)
    assert set(out["i2_solves"]["arm"]) == {"bigm", "perspective_rescaled"}
    assert len(out["i2_slope_points"]) == 5
    b = out["i2_baseline"].iloc[0]
    assert {"slope", "rel_err", "within", "kink", "step_checked"} <= set(b.index)
    assert np.isfinite(b["slope"])
    t0 = i2.make_task(cfg, inst, {"key": "sector", "b": 0.02}, b=0.0, estimator=False)
    b0 = i2.i2_task(t0)["i2_baseline"].iloc[0]
    assert np.isnan(b0["slope"]) and b0["envelope_note"] == "b = 0: no relative step"


def test_n1_plan_relaxations_and_reruns():
    cfg = config("numerics")
    assert len(n1.plan(cfg)) == 144
    rel = n1.relax_plan(cfg)
    assert len(rel) == 36 and len({(r["date"], r["N"], r["f"], r["tightness"]) for r in rel}) == 36
    reruns = n1.rerun_plan(cfg)
    assert len(reruns) == 3 and all(r["rerun"] for r in reruns)
    ids = {n1.task_id(p, K=0) for p in n1.plan(cfg)}
    assert all(n1.task_id({**r, "rerun": False}, K=0) in ids for r in reruns)


def test_n1_relax_task(inst):
    cfg = config("numerics")
    p = {"date": SMALL["date"], "N": SMALL["N"], "f": SMALL["f"], "tightness": "base"}
    out = n1.relax_task(n1.make_relax_task(cfg, p, inst))
    r = out["n1_relax"].iloc[0]
    assert np.isfinite(r["bigm"]) and np.isfinite(r["perspective"]) and r["perspective_ok"]
    assert r["perspective"] <= r["bigm"] + 1e-8 * abs(r["bigm"])          # A6 on the plain relaxations


def test_n1_frames_with_full_and_numeric_N_write_to_parquet(inst, tmp_path):
    """The N1 run of 2026-10-20 (results/n1/run_20261020T232021Z) failed at finish: N mixed ints
    (100, 250) and "full", which parquet cannot store. N is recorded as a text label."""
    import pandas as pd
    cfg = config("numerics")
    recs, rels = [], []
    for N in (30, "full"):
        p = {"date": SMALL["date"], "N": N, "f": SMALL["f"], "tightness": "base", "arm": "bigm",
             "presolve": -1}
        recs.append(n1.n1_task(n1.make_task(cfg, p, inst))["n1_solves"])
        q = {k: p[k] for k in ("date", "N", "f", "tightness")}
        rels.append(n1.relax_task(n1.make_relax_task(cfg, q, inst))["n1_relax"])
    for frames in (recs, rels):
        df = pd.concat(frames, ignore_index=True)
        assert list(df["N"]) == ["30", "full"]
        df.to_parquet(tmp_path / "x.parquet", index=False)


def test_solves_record_s_obj_and_workers(inst):
    """DESIGN §6 "Recorded per solve": the scale factors and the worker count (CHECKS K29 note)."""
    cfg = config("integer")
    t = i1.make_task(cfg, inst, {"key": "sector", "b": 0.02}, rel_delta=0.10, f=SMALL["f"])
    out = i1.i1_task(t)
    sv = out["i1_solves"]
    assert (sv["s_obj"] == 1e4).all() and (sv["workers"] == 4).all()
    assert {"raw_dual", "raw_duals_json", "raw_duals_usable"} <= set(out["i1_slope_points"].columns)
    ncfg = config("numerics")
    p = {"date": SMALL["date"], "N": SMALL["N"], "f": SMALL["f"], "tightness": "base", "arm": "bigm",
         "presolve": -1}
    r = n1.n1_task(n1.make_task(ncfg, p, inst))["n1_solves"].iloc[0]
    assert r["s_obj"] == 1e4 and r["workers"] == 4


def test_n1_relax_records_perspective_raw_duals(inst):
    import json
    cfg = config("numerics")
    p = {"date": SMALL["date"], "N": SMALL["N"], "f": SMALL["f"], "tightness": "base"}
    r = n1.relax_task(n1.make_relax_task(cfg, p, inst))["n1_relax"].iloc[0]
    d = json.loads(r["perspective_raw_duals_json"])
    assert "sector" in d and "gross" in d and r["perspective_raw_duals_usable"]
