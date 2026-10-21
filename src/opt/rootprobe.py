"""Root-node probe for the N1 root-gap question (S2d item 1; Decision 37 open). A diagnostic, not
an estimator.

root_probe builds the binary P-MI exactly as the kept solve does (src.opt.miqp.MIQPModel._build
"mip", or src.opt.integer.build_rescaled_mip for the rescaled arm), applies the kept solve's
parameters (MIPGap, Presolve, WorkLimit as given; Threads and Seed from the model) plus `params`,
stops after the root node (NodeLimit = 1), and records Gurobi's best bound, MIPNODE_OBJBND, at
every MIPNODE callback with MIPNODE_NODCNT = 0. Gurobi's callback reference: the first such call
gives the root relaxation with no cutting planes and the last the relaxation after all root cuts;
the kept solve records the last (root_bound). Values are U (= −Gurobi's objective) in the model's
units (× s_obj); the bound sequence, its length, the first and last, Gurobi's final ObjBound,
status, Work, Runtime and the settings are returned.

plain_relaxations(pmi) gives the z ∈ [0, 1] relaxations in original units: big-M by the kept
relax() (dual simplex), the perspective by Clarabel with the DESIGN §6 value (cones exact), its
status, residuals, gap and own objective, its raw duals (dU*/db per key, original units, as JSON;
DESIGN §6 diagnostics, kept on failure as Decision 25) and Gurobi's barrier on the same
relaxation (BarQCPConvTol 1e-9, the kept relax()).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
from gurobipy import GRB

from src.opt.integer import build_rescaled_mip
from src.opt.miqp import MIQPModel, _status_name
from src.opt.relaxation import perspective_relaxation

STATUS = {GRB.NODE_LIMIT: "NODE_LIMIT"}


def root_probe(M: MIQPModel, rescale: bool = False, mip_gap: float = 1e-4, presolve: int = -1,
               work_limit: float | None = None, params: dict | None = None) -> dict:
    """Gurobi's root bounds by cut pass (module docstring)."""
    if rescale:
        mdl = build_rescaled_mip(M)[0]
    else:
        mdl = M._build("mip")[0]
    settings = {"MIPGap": mip_gap, "Presolve": presolve, "NodeLimit": 1,
                "Threads": M.threads, "Seed": M.seed, **(params or {})}
    if work_limit is not None:
        settings["WorkLimit"] = work_limit
    for k, v in settings.items():
        mdl.setParam(k, v)
    passes, best = [], []

    def cb(model, where):
        if where == GRB.Callback.MIPNODE and model.cbGet(GRB.Callback.MIPNODE_NODCNT) == 0:
            passes.append(-model.cbGet(GRB.Callback.MIPNODE_OBJBND))
            best.append(-model.cbGet(GRB.Callback.MIPNODE_OBJBST))

    try:
        mdl.optimize(cb)
        out = {"passes": passes, "incumbents": best, "n_passes": len(passes),
               "first": passes[0] if passes else np.nan, "last": passes[-1] if passes else np.nan,
               "final_bound": -mdl.ObjBound,
               "status": STATUS.get(mdl.Status, _status_name(mdl.Status)),
               "work": mdl.Work, "runtime": mdl.Runtime, "nodes": mdl.NodeCount,
               "rescale": bool(rescale), "formulation": M.formulation, "settings": settings}
    finally:
        mdl.dispose()
    return out


def plain_relaxations(pmi) -> dict:
    """Both z ∈ [0, 1] relaxations of a P-MI instance at its current bounds, original units."""
    s = pmi.s_obj
    bigm = pmi._model("bigm").relax().U / s
    P = pmi._model("perspective")
    cl = perspective_relaxation(P)
    info = cl.info
    try:
        barrier, barrier_status = P.relax().U / s, "OPTIMAL"
    except RuntimeError as err:
        barrier, barrier_status = np.nan, str(err)
    raw = ({k: v / s for k, v in pmi._shadows(SimpleNamespace(duals=cl.duals)).items()}
           if cl.duals else {})
    return {"bigm": bigm, "perspective": info["value"] / s, "perspective_ok": bool(cl.ok),
            "perspective_raw_duals_json": json.dumps(raw, sort_keys=True),
            "perspective_raw_duals_usable": bool(cl.ok),
            "perspective_status": cl.status, "perspective_fail_reason": info.get("fail_reason"),
            "perspective_clarabel_status": info["clarabel_status"],
            "perspective_r_prim": info["r_prim"], "perspective_r_dual": info["r_dual"],
            "perspective_gap_abs": info["gap_abs"] / s, "perspective_gap_rel": info["gap_rel"],
            "perspective_clarabel_objective": info["clarabel_objective"] / s,
            "perspective_gurobi_barrier": barrier,
            "perspective_gurobi_barrier_status": barrier_status}
