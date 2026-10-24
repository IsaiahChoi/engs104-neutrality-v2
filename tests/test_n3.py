"""experiments/run_n3.py (DESIGN §7 N3; Decision 51; S4b addendum step 0). Tests first: the
volatility against the dense Σ, the kept core and a risk-binding P-RB on real data; the weight
assembly; the probe plan against N1's; the probe task on a small instance; the N3 table and the
E1–E4 rules on constructed tables whose answers are known; the stored-run hash guard."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from experiments import run_n3 as R
from experiments.designs import config
from experiments.instances import miqp_mandate, restricted, subsample
from src.opt.continuous import ContinuousProblem, load_config
from src.opt.risk_budget import solve_risk_budget
from src.risk.factor_model import FACTORS
from tests.realdata import month_end
from tests.test_integer import small
from tests.test_opt import dense_sigma, random_instance


def test_ann_vol_matches_dense_sigma_and_the_kept_core():
    B, F, d, S, adv, alpha = random_instance(n=20, seed=5)
    w = np.random.default_rng(1).normal(size=20) * 0.02
    want = np.sqrt(12.0 * w @ dense_sigma(B, F, d) @ w)
    assert R.ann_vol(w, B, F, d) == pytest.approx(want, rel=1e-12)
    P = ContinuousProblem(B, F, d, S, load_config()[0], adv=adv, factor_names=FACTORS)
    assert R.ann_vol(w, B, F, d) == pytest.approx(P.ann_vol(w), rel=1e-12)
    assert R.ann_vol(np.zeros(20), B, F, d) == 0.0


def test_ann_vol_of_a_risk_binding_prb_is_the_budget_on_real_data():
    """The universe assembly (top-N by ADV, restricted) gives the Σ under which P-RB at u = 6% sits
    on its 3%/yr budget (DESIGN §6: root-found to relative 1e-10)."""
    di, alpha, idx = subsample(month_end("2017-12"), 30)
    B, F, d, S, adv, _ = restricted(di, idx)
    P = ContinuousProblem(B, F, d, S, miqp_mandate(load_config()[0]), adv=adv, factor_names=FACTORS)
    rb = solve_risk_budget(P, alpha[idx])
    assert rb.risk_binding
    assert R.ann_vol(rb.sol.w, B, F, d) == pytest.approx(0.03, rel=1e-8)
    Bu, Fu, du = R.universe("2017-12", 30)
    assert np.array_equal(Bu, B) and np.array_equal(Fu, F) and np.array_equal(du, d)


def test_weight_vectors_are_ordered_by_name_index_and_complete():
    df = pd.DataFrame({"id": ["a"] * 3 + ["b"] * 3, "i": [2, 0, 1, 0, 1, 2],
                       "w": [0.3, 0.1, 0.2, 1.0, 2.0, 3.0]})
    out = R.weight_vectors(df, ["id"])
    assert np.array_equal(out[("a",)], [0.1, 0.2, 0.3]) and np.array_equal(out[("b",)], [1, 2, 3])
    with pytest.raises(ValueError):
        R.weight_vectors(pd.DataFrame({"id": ["a", "a"], "i": [0, 2], "w": [1.0, 2.0]}), ["id"])


def test_probe_plan_covers_the_36_n1_instances_at_default_presolve():
    cfg, ncfg = config("n3"), config("numerics")
    plan = R.probe_plan(cfg, ncfg)
    inst = {(p["date"], str(p["N"]), p["f"], p["tightness"]) for p in plan}
    assert len(inst) == 36
    assert len(plan) == 36 * 2                                  # one task per instance and arm
    assert {p["arm"] for p in plan} == {"perspective", "perspective_rescaled"}
    assert all(p["presolve"] == -1 for p in plan)
    n_probes = sum(len(cfg["probes"][p["arm"]]) for p in plan)
    assert n_probes == 36 * (4 + 3)
    persp = [pr["params"] for pr in cfg["probes"]["perspective"]]
    assert {} in persp and {"MIQCPMethod": 0} in persp and {"MIQCPMethod": 1} in persp
    assert {"FeasibilityTol": 1e-9} in persp


def test_probe_task_on_a_small_instance_records_every_probe():
    P, _ = small(form="perspective", s_obj=10.0)
    kw = dict(B=P.B, F=P.F, d=P.d, S=P.S, alpha=P.alpha, lam=P.lam, mandate=P.mandate, adv=P.adv,
              K=P.K, ell=P.ell, factor_names=FACTORS)
    probes = config("n3")["probes"]
    for arm, rescale in (("perspective", False), ("perspective_rescaled", True)):
        t = {"id": "x", "inst": "x_inst", "arm": arm, "rescale": rescale, "kwargs": kw,
             "s_obj": 10.0, "mip_gap": 1e-4, "presolve": -1, "work_limit": 340.0,
             "probes": probes[arm]}
        df = R.probe_task(t)["n3_probes"]
        assert list(df["probe"]) == [p["probe"] for p in probes[arm]]
        assert (df["n_passes"] >= 1).all() and np.isfinite(df["last"]).all()
        assert set(df["status"]) <= {"NODE_LIMIT", "OPTIMAL"}
        st = [json.loads(s) for s in df["settings"]]
        assert all(s["NodeLimit"] == 1 and s["Presolve"] == -1 and s["MIPGap"] == 1e-4 for s in st)
        # values are in original units: the root bound is an upper bound on the optimum
        r = P.sibling("perspective", rescale=rescale).solve(mip_gap=1e-6)
        assert (df["last"] >= r.V - 1e-6 * abs(r.V)).all()


def _probes(rows):
    return pd.DataFrame(rows, columns=["inst", "arm", "probe", "last", "status", "work", "n_passes"])


def test_n3_table_gaps_and_stored_reproduction():
    probes = _probes([
        ("I", "perspective", "m-1", 1.10, "NODE_LIMIT", 1.0, 9),
        ("I", "perspective", "m0", 1.002, "NODE_LIMIT", 0.2, 3),
        ("I", "perspective", "m1", 1.10, "NODE_LIMIT", 1.0, 9),
        ("I", "perspective", "m-1_feastol1e-9", 1.09, "NODE_LIMIT", 1.1, 10),
        ("I", "perspective_rescaled", "m-1", 1.001, "NODE_LIMIT", 0.6, 20),
        ("I", "perspective_rescaled", "m0", 1.002, "NODE_LIMIT", 0.2, 3),
        ("I", "perspective_rescaled", "m1", 1.001, "NODE_LIMIT", 0.6, 20)])
    stored = pd.DataFrame({"inst": ["I", "I"], "arm": ["perspective", "perspective_rescaled"],
                           "root_bound": [1.10, 1.0015], "V_best": [1.0, 1.0],
                           "plain_perspective": [1.001, 1.001]})
    t = R.n3_table(probes, stored).set_index("arm")
    assert t.loc["perspective", "gap_m-1"] == pytest.approx(0.10)
    assert t.loc["perspective", "gap_m0"] == pytest.approx(0.002)
    assert t.loc["perspective", "gap_plain"] == pytest.approx(0.001)
    assert bool(t.loc["perspective", "repro_stored"]) is True
    assert bool(t.loc["perspective_rescaled", "repro_stored"]) is False
    assert t.loc["perspective_rescaled", "stored_minus_probe_rel"] == pytest.approx(0.0005)
    assert bool(t.loc["perspective", "E1_exact"]) is True
    assert t.loc["perspective", "E2_dist"] == pytest.approx(0.001)
    assert t.loc["perspective", "E3_ratio"] == pytest.approx(0.09 / 0.10)
    assert t.loc["perspective_rescaled", "E4_spread"] == pytest.approx(0.002 / 0.001)
    assert np.isnan(t.loc["perspective", "E4_spread"])          # E4 is the rescaled arm's


def test_expectations_rules_count_hits_and_misses():
    t = pd.DataFrame({
        "arm": ["perspective"] * 3 + ["perspective_rescaled"] * 3,
        "E1_exact": [True, True, False, True, False, False],
        "E2_dist": [1e-3, 6e-3, 2e-3, np.nan, np.nan, np.nan],
        "E3_ratio": [0.99, 0.2, 1.1, np.nan, np.nan, np.nan],
        "E4_spread": [np.nan] * 3 + [2.0, 50.0, np.nan]})
    e = R.expectations(t, {"E2_atol_rel": 0.005, "E3_band": [0.5, 2.0], "E4_factor": 10.0})
    assert e["E1"]["perspective"] == {"n": 3, "exact": 2, "hit": True}
    assert e["E1"]["perspective_rescaled"] == {"n": 3, "exact": 1, "hit": False}
    assert e["E1"]["hit"] is False                              # "both arms"
    assert e["E2"]["n"] == 3 and e["E2"]["within"] == 2 and e["E2"]["hit"] is True
    assert e["E3"]["median_ratio"] == pytest.approx(0.99) and e["E3"]["hit"] is True
    assert e["E3"]["n_collapsed"] == 1                           # ratio < band low
    assert e["E4"]["n"] == 2 and e["E4"]["n_undefined"] == 1 and e["E4"]["within"] == 1
    assert e["E4"]["hit"] is False                               # 1 of 3 is not "most"


def test_vol_summary_counts_against_the_budget():
    df = pd.DataFrame({"experiment": ["I1"] * 4, "arm": ["bigm"] * 4,
                       "vol_ann": [0.029, 0.03, 0.0300000001, 0.025]})
    s = R.vol_summary(df, ["experiment", "arm"], target=0.03)
    row = s[0]
    assert row["n"] == 4 and row["min"] == 0.025 and row["max"] == pytest.approx(0.0300000001)
    assert row["median"] == pytest.approx(np.median(df["vol_ann"]))
    assert row["n_below"] == 2 and row["n_at"] == 2 and row["n_above"] == 0   # at = within 1e-6 rel


def test_stored_run_guard_refuses_a_changed_output(tmp_path):
    run = tmp_path / "run_x"
    run.mkdir()
    pd.DataFrame({"a": [1]}).to_parquet(run / "t.parquet")
    (run / "DONE").write_text("x")
    from experiments.common import file_sha256
    (run / "outputs.json").write_text(json.dumps({"t.parquet": file_sha256(run / "t.parquet")}))
    (run / "run_meta.json").write_text(json.dumps({"git_commit": "abc"}))
    out = R.check_run(run, ["t"])
    assert out["git_commit"] == "abc" and set(out["sha256"]) == {"t.parquet"}
    pd.DataFrame({"a": [2]}).to_parquet(run / "t.parquet")
    with pytest.raises(ValueError):
        R.check_run(run, ["t"])
    (run / "SUPERSEDED").write_text("x")
    with pytest.raises(ValueError):
        R.check_run(run, ["t"])
