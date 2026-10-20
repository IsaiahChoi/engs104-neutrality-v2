"""Root-node probe for the N1 root-gap question (S2d item 1; Decision 37 open): Gurobi's bound at
every root cut pass (the first is the root relaxation before cuts, the last is what the kept solve
records as root_bound), next to the plain relaxations (big-M by dual simplex, perspective by
Clarabel with the cones exact, DESIGN §6)."""
from __future__ import annotations

import numpy as np
import pytest

from src.opt.relaxation import perspective_relaxation
from src.opt.rootprobe import plain_relaxations, root_probe
from tests.test_integer import small

FORMS = ["bigm", "perspective"]


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("rescale", [False, True])
def test_last_pass_is_the_recorded_root_bound(form, rescale):
    """With the kept solve's parameters the probe's last root pass equals PMI.solve's root_bound
    (the same model and callback point); passes are recorded in order and the best bound never
    rises across them."""
    if rescale and form == "bigm":
        pytest.skip("the rescaled arm is a perspective arm (Decision 27(a))")
    P, _ = small(form=form)
    P.rescale = rescale
    r = P.solve(mip_gap=1e-4)
    pr = root_probe(P.model, rescale=rescale, mip_gap=1e-4)
    assert pr["n_passes"] >= 1 and len(pr["passes"]) == pr["n_passes"]
    assert pr["last"] == pytest.approx(r.root_bound * P.s_obj, rel=1e-12)
    assert pr["first"] >= pr["last"] - 1e-12 * abs(pr["last"])
    assert all(a >= b - 1e-12 * abs(b) for a, b in zip(pr["passes"], pr["passes"][1:]))
    assert pr["settings"]["NodeLimit"] == 1


def test_parameters_are_applied_and_recorded():
    P, _ = small(form="perspective")
    pr = root_probe(P.model, params={"FeasibilityTol": 1e-9, "MIQCPMethod": 0})
    assert pr["settings"]["FeasibilityTol"] == 1e-9 and pr["settings"]["MIQCPMethod"] == 0
    assert pr["status"] in ("NODE_LIMIT", "OPTIMAL")
    assert np.isfinite(pr["work"]) and pr["work"] >= 0


def test_plain_relaxations_satisfy_a6_and_match_the_modules():
    """A6: the perspective relaxation's value is at most big-M's (maximization). The values are the
    kept big-M relax() (dual simplex) and the DESIGN §6 Clarabel value (cones exact)."""
    P, _ = small(form="bigm")
    out = plain_relaxations(P)
    assert out["bigm"] == pytest.approx(P.model.relax().U / P.s_obj, rel=1e-12)
    Pp = P.sibling("perspective")
    assert out["perspective"] == pytest.approx(
        perspective_relaxation(Pp.model).info["value"] / P.s_obj, rel=1e-12)
    assert out["perspective"] <= out["bigm"] + 1e-9 * abs(out["bigm"])
    assert {"perspective_clarabel_status", "perspective_r_prim", "perspective_gap_abs",
            "perspective_ok", "perspective_clarabel_objective",
            "perspective_gurobi_barrier"} <= set(out)
