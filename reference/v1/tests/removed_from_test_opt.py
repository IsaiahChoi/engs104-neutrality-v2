"""Reference only (not collected, not imported). Tests removed from tests/test_opt.py when v2
was extracted from v1 commit 05468f2, because they exercise v1-only code (the fixed-lambda
book in src/opt/lambda_policy.py and the v1 runners in experiments/). The last one guards a
real bug (shadow prices recorded after resetting swept caps); v2 must port an equivalent
regression test for its own sweep runner (docs/RUNBOOK.md S1)."""

def test_lambda_calibration_target_and_fallback():
    """Brief §3.3: calibrate to the target when attainable, else to 90% of the maximum."""
    from src.opt.lambda_policy import calibrate
    B, F, d, S, adv, alpha = random_instance(seed=3)
    P = ContinuousProblem(B, F, d, S, Mandate(**{**OFF, "dollar": 0.0, "beta": 0.0}), factor_names=FACTORS)
    r = calibrate(P, alpha, "2020-01-31", "test", target=0.03)
    assert not r.fallback and r.attained_vol == pytest.approx(0.03, rel=1e-4)
    Pg = ContinuousProblem(B, F, d, S, Mandate(**{**OFF, "dollar": 0.0, "gross": 0.5}), factor_names=FACTORS)
    r = calibrate(Pg, alpha, "2020-01-31", "test", target=5.0)       # unattainable
    assert r.fallback and r.target_vol == pytest.approx(0.9 * r.max_vol, rel=1e-12)
    assert r.attained_vol == pytest.approx(r.target_vol, rel=1e-4)



@pytest.fixture
def temp_book(tmp_path, real):
    """A λ record for the real date (values chosen by the test, not calibrated)."""
    from src.opt.lambda_policy import LambdaBook, LambdaRecord, write_book
    recs = [LambdaRecord(REAL_DATE, k, lam, 0.03, 0.03, 0.05, False, (1e-3, 1e5), 0)
            for k, lam in (("momentum", 7.0), ("synthetic_ic0.05", 11.0))]
    return LambdaBook(write_book(recs, {"test": True}, "20000101T000000Z", directory=tmp_path))



def test_lambda_held_fixed_across_sweep_and_e2_configurations(real, temp_book, monkeypatch):
    """GATE_CRITERIA P6: the runners read λ from the record, never recalibrate, and use one λ
    per (date, alpha) across every sweep point, draw, and E2 configuration."""
    import experiments.run_rq1 as rq1
    import experiments.run_rq2 as rq2
    import src.opt.continuous as cont
    import src.opt.lambda_policy as lp
    from experiments.designs import config
    def boom(*a, **k):
        raise AssertionError("calibration called during a run")
    monkeypatch.setattr(cont, "calibrate_lambda", boom)
    monkeypatch.setattr(lp, "calibrate", boom)
    with pytest.raises(KeyError):
        temp_book.get("2019-01-31", "momentum")
    mandate, _ = load_config()
    pts, _, att = rq1.run_date(pd.Timestamp(REAL_DATE), config("rq1"), mandate, temp_book, 20261015,
                               families={"beta", "style:Mom", "position"}, draws=2)
    assert set(pts.loc[pts["alpha"] == "momentum", "lam"]) == {7.0}
    assert set(pts.loc[pts["alpha"] == "synthetic", "lam"]) == {11.0}
    assert set(att["lam"]) == {7.0, 11.0} and pts["family"].nunique() == 3
    cfg2 = {**config("rq2"), "ics": [0.05]}
    sol, _ = rq2.run_month((pd.Timestamp(REAL_DATE), cfg2, 2, str(temp_book.path), "GUROBI", None))
    assert set(sol["lam"]) == {11.0} and sol["config"].nunique() == 6 and sol["draw"].nunique() == 2



def test_alpha_seed_is_one_value_everywhere():
    """GATE 3b concern 7: the draw seed in base_mandate, rq1, rq2 and the λ record must agree,
    or λ (calibrated on draw 0) would silently stop matching draw 0."""
    from experiments.designs import config
    from src.opt.lambda_policy import LambdaBook
    seeds = {load_config()[1]["alpha"]["seed"], config("rq1")["seed"], config("rq2")["seed"],
             config("rq2")["months"]["seed"], LambdaBook.latest().meta["alpha_seed"]}
    assert seeds == {20261015}



def test_e3_subsample_alpha_options(real):
    """REVIEW 3 concern 10 is open: run_rq3 supports both choices and refuses an unset one."""
    from experiments.run_rq3 import subsample
    di, a_r, idx = subsample(REAL_DATE, 100, "restrict")
    _, a_z, idx2 = subsample(REAL_DATE, 100, "rezscore")
    np.testing.assert_array_equal(idx, idx2)
    z = a_z[idx] / (0.03 * np.sqrt(di.model.d[idx]))
    assert abs(z.mean()) < 1e-12 and abs(z.std() - 1) < 1e-12
    assert not np.allclose(a_r[idx], a_z[idx])
    with pytest.raises(ValueError):
        subsample(REAL_DATE, 100, None)



def test_e1_runner_shadow_prices_at_swept_caps(real, temp_book):
    """Found by the E1 envelope self-check: at swept u and θ values the recorded position and
    liquidity shadow prices must match finite differences of U* in that cap (they were computed
    after resetting the caps to base in the first E1 run)."""
    import experiments.run_rq1 as rq1
    from experiments.designs import config
    mandate, _ = load_config()
    pts, _, _ = rq1.run_date(pd.Timestamp(REAL_DATE), config("rq1"), mandate, temp_book, 20261015,
                             families={"position", "liquidity"}, draws=0)
    di, alpha, _ = real
    checked = 0
    for _, r in pts[~pts["off"] & ~pts["is_base"]].iterrows():
        sp = r[f"sp_{r['family']}"]
        if not sp > 1e-7:
            continue
        P = rq1.build(di, mandate)["base"]
        snap = rq1.snapshot(P)
        h = 1e-5 * r["value"]
        vals = []
        for s_ in (+1, -1):
            rq1.apply_point(P, mandate, r["family"], r["value"] + s_ * h)
            vals.append(P.solve(alpha, lam=r["lam"]).objective)
            rq1.reset(P, snap)
        assert (vals[0] - vals[1]) / (2 * h) == pytest.approx(sp, rel=0.01), r["point_id"]
        checked += 1
    assert checked >= 2
