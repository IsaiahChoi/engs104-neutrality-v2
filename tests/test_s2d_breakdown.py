"""tools/s2d_breakdown.py: the derived S2d pilot diagnostics behind the PROGRESS S2d table, recomputed
from the committed run (read-only) and consistent with the runner's own summary.json."""
from __future__ import annotations

import json

import tools.s2d_breakdown as bd
from src.utils import ROOT

RUN = "results/pilot_s2d/run_20261020T045603Z"


def test_breakdown_matches_the_run_summary():
    assert bd.main(RUN) == 0
    out = json.loads((ROOT / "results/pilot_s2d/s2d_breakdown_run_20261020T045603Z.json").read_text())
    summ = json.loads((ROOT / RUN / "summary.json").read_text())
    assert out["item1"]["a6_holds_plain"] == summ["rootgap"]["a6_holds_plain"]
    assert out["item1"]["a6_holds_root_stored"] == summ["rootgap"]["a6_holds_root_stored"]
    for s in ("1", "100", "10000"):
        assert out["item2_toys"][s]["n_failed"] == summ["k29c_toys"][s]["n_failed"]
        assert out["item2_toys"][s]["concavity3_failures"] == summ["k29c_toys"][s]["concavity_failures"]
    assert set(out["item3"]) >= {"1", "100", "10000", "1e+06"}
