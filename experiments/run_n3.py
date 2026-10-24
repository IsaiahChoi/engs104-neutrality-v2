"""N3 — root-bound diagnostic and MIQP volatility (DESIGN §7 N3; Decision 51; S4b addendum step 0):
`make n3` → results/n3/run_<UTC>/. Added at the S4 read, after the S3 results and the cold read.

Inputs are the stored S3 runs named in n3.yaml (I1, I2, N1 at 120ea56); each must be DONE, not
superseded or failed, and its outputs must match its outputs.json (check_run). N1's settings are
read from the stored N1 run's config, which must equal numerics.yaml's.

- Volatility (0a; no MIQP solves). σ = √(12·wᵀΣw), Σ = BFBᵀ + D of the instance's (date, N)
  (experiments.instances: top-N by ADV, restricted), for every stored polished-V weight vector:
  I1 (144 points) and I2 (82 points) store the combined V's weights (DESIGN §6), N1 one vector per
  solve (arm, presolve). Each V is recomputed from its weights (src.opt.integer.exact_objective at
  the instance's α and λ*; λ* checked against the stored one) and must match the stored V to
  v_check_rtol: this checks the name order and Σ. The continuous baseline's volatility (I1 (d):
  P-MI with ℓ = 0 and no cardinality row) is the stored vol_ann at the I1 base points and along
  the I2 grids.
- Root probes (0b). The 36 N1 instances at default presolve, the perspective at default scaling
  and rescaled (DESIGN §3.4), root-only with N1's settings (src.opt.rootprobe.root_probe:
  NodeLimit 1, MIPGap, WorkLimit W*, Threads 1, Seed 0) at MIQCPMethod −1, 0 and 1, and for the
  default-scaling arm −1 with FeasibilityTol 1e-9. Per probe: the root bound (the last MIPNODE
  callback at node 0, which is what N1 recorded as root_bound), the first, the count of node-0
  MIPNODE callbacks (n_passes; Gurobi has no root-cut-pass attribute), status, Work. n3_table puts
  each bound beside N1's stored root bound (the −1 probe must reproduce it: S2d's separating test),
  N1's best known value V_best (src.analysis.s3.best_known) and the plain perspective relaxation
  (n1_relax), as gaps (bound − V_best)/|V_best|; expectations() applies the E1–E4 rules of n3.yaml.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from experiments import run_n1, s3
from experiments.common import fail, file_sha256, finish, open_run, run_meta
from experiments.cont import pool_chunks
from experiments.designs import config, month_end
from experiments.instances import restricted, subsample
from src.analysis.s3 import best_known
from src.opt.integer import PMI, exact_objective
from src.opt.rootprobe import root_probe
from src.utils import ROOT

CONFIG = "experiments/configs/n3.yaml"
STORED = {"i1": ("i1_weights", "i1_points", "i1_baseline"),
          "i2": ("i2_weights", "i2_points", "i2_baseline"),
          "n1": ("n1_weights", "n1_solves", "n1_relax")}
AT_RTOL = 1e-6                       # "at the budget": |σ/target − 1| ≤ 1e-6


# ----- inputs -----

def check_run(run: Path, frames) -> dict:
    """A stored run usable as input: DONE, no SUPERSEDED or FAILED marker, and each frame's file
    matching its outputs.json hash. Returns its commit and the hashes."""
    run = Path(run)
    if not (run / "DONE").exists() or (run / "SUPERSEDED").exists() or (run / "FAILED").exists():
        raise ValueError(f"{run} is not a finished, current run")
    hashes = json.loads((run / "outputs.json").read_text())
    got = {}
    for f in frames:
        name = f"{f}.parquet"
        h = file_sha256(run / name)
        if hashes.get(name) != h:
            raise ValueError(f"{run / name} does not match its outputs.json")
        got[name] = h
    return {"run": str(run.relative_to(ROOT)) if run.is_relative_to(ROOT) else str(run),
            "git_commit": run_meta(run)["git_commit"], "sha256": got}


def load_stored(cfg: dict) -> tuple[dict, dict]:
    frames, prov = {}, {}
    for name, kinds in STORED.items():
        run = ROOT / cfg["runs"][name]
        prov[name] = check_run(run, kinds)
        for k in kinds:
            frames[k] = pd.read_parquet(run / f"{k}.parquet")
    return frames, prov


# ----- 0a: volatility -----

def ann_vol(w, B, F, d) -> float:
    """√(12·wᵀΣw), Σ = BFBᵀ + diag(d), in factor form."""
    w = np.asarray(w, float)
    y = np.asarray(B, float).T @ w
    return float(np.sqrt(12.0 * (y @ np.asarray(F, float) @ y + np.asarray(d, float) @ (w * w))))


def universe(ym: str, N) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(B, F, d) of the P-MI universe at (date, N): the instances' top-N by ADV, restricted."""
    di, _, idx = subsample(month_end(ym), "full" if str(N) == "full" else int(N))
    B, F, d, *_ = restricted(di, idx)
    return B, F, d


def weight_vectors(df: pd.DataFrame, keys: list[str]) -> dict[tuple, np.ndarray]:
    """{key tuple: w ordered by name index i}; each vector's i must be 0..n−1."""
    out = {}
    for k, g in df.groupby(keys, sort=True):
        g = g.sort_values("i")
        i = g["i"].to_numpy()
        if not np.array_equal(i, np.arange(len(i))):
            raise ValueError(f"weights of {k} do not cover names 0..{len(i) - 1}")
        out[k if isinstance(k, tuple) else (k,)] = g["w"].to_numpy(float)
    return out


def vol_rows(frames: dict, insts: dict, rtol: float) -> pd.DataFrame:
    """One row per stored weight vector (module docstring)."""
    rows = []

    def add(exp, key, meta, w, lam_stored):
        ym, N = meta["date"], str(meta["N"])
        inst = insts[(ym, N)]
        if len(w) != len(inst.d):
            raise ValueError(f"{exp} {key}: {len(w)} weights for {len(inst.d)} names")
        if not np.isclose(inst.lam, lam_stored, rtol=1e-10, atol=0.0):
            raise ValueError(f"{exp} {key}: λ* {inst.lam} != stored {lam_stored}")
        Vc = exact_objective(w, inst.alpha, inst.lam, inst.B, inst.F, inst.d, inst.mandate)
        V = float(meta["V"])
        rel = abs(Vc - V) / abs(V)
        if rel > rtol:
            raise ValueError(f"{exp} {key}: V recomputed {Vc} != stored {V} (rel {rel:.2e})")
        rows.append({"experiment": exp, "key_id": "|".join(map(str, key)), "date": ym, "N": N,
                     "f": meta.get("f", np.nan), "K": int(meta["K"]), "family": meta.get("key"),
                     "point": meta.get("point"), "bound": float(meta.get("bound", np.nan)),
                     "tightness": meta.get("tightness"), "arm": meta["arm"],
                     "presolve": int(meta.get("presolve", -1)), "v_tie": meta.get("v_tie"),
                     "V": V, "V_recomputed": Vc, "V_rel_diff": rel,
                     "n_held": int((np.abs(w) > 0).sum()),
                     "vol_ann": ann_vol(w, inst.B, inst.F, inst.d)})

    lam_i1 = frames["i1_baseline"].groupby("instance")["lam"].first()
    pts = frames["i1_points"].set_index(["id", "point"])
    for (cid, pt), w in weight_vectors(frames["i1_weights"], ["id", "point"]).items():
        m = pts.loc[(cid, pt)]
        add("I1", (cid, pt), {**m.to_dict(), "point": pt, "arm": m["v_from"]}, w,
            lam_i1.loc[m["instance"]])
    lam_i2 = frames["i2_baseline"].groupby("instance")["lam"].first()
    pts2 = frames["i2_points"].set_index("id")
    for (pid,), w in weight_vectors(frames["i2_weights"], ["id"]).items():
        m = pts2.loc[pid]
        add("I2", (pid,), {**m.to_dict(), "arm": m["v_from"]}, w, lam_i2.loc[m["instance"]])
    sv = frames["n1_solves"]
    sv = sv[~sv["rerun"].astype(bool)].set_index("id")
    for (sid,), w in weight_vectors(frames["n1_weights"], ["id"]).items():
        if sid not in sv.index:                         # the K25 reruns: same weights, not counted
            continue
        m = sv.loc[sid]
        add("N1", (sid,), m.to_dict(), w, m["lam_star"])
    return pd.DataFrame(rows)


def baseline_rows(frames: dict) -> pd.DataFrame:
    b1 = frames["i1_baseline"].assign(experiment="I1 base points", bound=lambda x: x["b"])
    b2 = frames["i2_baseline"].assign(experiment="I2 grid")
    cols = ["experiment", "id", "instance", "date", "key", "bound", "vol_ann", "lam"]
    return pd.concat([b1[cols], b2[cols]], ignore_index=True)


def vol_summary(df: pd.DataFrame, by: list[str], target: float) -> list[dict]:
    out = []
    for k, g in df.groupby(by, sort=True, dropna=False):
        v = g["vol_ann"].to_numpy(float)
        r = v / target - 1.0
        out.append({**dict(zip(by, k if isinstance(k, tuple) else (k,))), "n": len(v),
                    "median": float(np.median(v)), "min": float(v.min()), "max": float(v.max()),
                    "n_below": int((r < -AT_RTOL).sum()), "n_at": int((np.abs(r) <= AT_RTOL).sum()),
                    "n_above": int((r > AT_RTOL).sum())})
    return out


# ----- 0b: root probes -----

def probe_plan(cfg: dict, ncfg: dict) -> list[dict]:
    """N1's plan (run_n1.plan) at default presolve, for the arms with probes in n3.yaml."""
    pre = int(ncfg["n1"]["settings"].get("presolve", -1))
    return [p for p in run_n1.plan(ncfg) if p["presolve"] == pre and p["arm"] in cfg["probes"]]


def probe_task(t: dict) -> dict[str, pd.DataFrame]:
    """Every probe of one (instance, arm), original units."""
    P = PMI(**t["kwargs"], formulation="perspective", s_obj=t["s_obj"])
    s, rows = P.s_obj, []
    for pr in t["probes"]:
        out = root_probe(P.model, rescale=t["rescale"], mip_gap=t["mip_gap"],
                         presolve=t["presolve"], work_limit=t["work_limit"], params=pr["params"])
        rows.append({"id": f"{t['inst']}_{t['arm']}_{pr['probe']}", "inst": t["inst"],
                     "arm": t["arm"], "probe": pr["probe"],
                     "params": json.dumps(pr["params"], sort_keys=True),
                     "first": out["first"] / s, "last": out["last"] / s,
                     "final_bound": out["final_bound"] / s, "n_passes": out["n_passes"],
                     "passes": json.dumps([p / s for p in out["passes"]]), "status": out["status"],
                     "work": out["work"], "runtime": out["runtime"], "nodes": out["nodes"],
                     "settings": json.dumps(out["settings"], sort_keys=True, default=str)})
    return {"n3_probes": pd.DataFrame(rows)}


def stored_roots(n1_solves: pd.DataFrame, n1_relax: pd.DataFrame, presolve: int = -1) -> pd.DataFrame:
    """Per (instance, perspective arm): N1's stored root bound, V_best and the plain perspective."""
    sv = n1_solves[~n1_solves["rerun"].astype(bool)]
    vb = best_known(n1_solves)
    inst_of = lambda r: f"{r['date']}_N{r['N']}_f{r['f']:g}_K{r['K']}_{r['tightness']}"
    rows = []
    for _, r in sv[(sv["presolve"] == presolve) & sv["arm"].str.startswith("perspective")].iterrows():
        rows.append({"inst": inst_of(r), "arm": r["arm"], "root_bound": float(r["root_bound"]),
                     "V_best": float(vb.loc[(r["date"], r["N"], r["f"], r["K"], r["tightness"])])})
    out = pd.DataFrame(rows)
    rx = n1_relax.assign(inst=n1_relax.apply(inst_of, axis=1)).set_index("inst")
    out["plain_perspective"] = rx.loc[out["inst"], "perspective"].to_numpy(float)
    out["plain_perspective_ok"] = rx.loc[out["inst"], "perspective_ok"].to_numpy(bool)
    return out


def n3_table(probes: pd.DataFrame, stored: pd.DataFrame) -> pd.DataFrame:
    """One row per (instance, arm): each probe's root bound and gap, the plain gap, the stored
    root bound's reproduction by m-1, and the E1–E4 quantities."""
    rows = []
    st = stored.set_index(["inst", "arm"])
    for (inst, arm), g in probes.groupby(["inst", "arm"], sort=True):
        s = st.loc[(inst, arm)]
        V = float(s["V_best"])
        gap = lambda x: (float(x) - V) / abs(V)
        last = g.set_index("probe")["last"]
        row = {"inst": inst, "arm": arm, "V_best": V, "root_stored": float(s["root_bound"]),
               "plain_perspective": float(s["plain_perspective"]),
               "gap_plain": gap(s["plain_perspective"]), "gap_stored": gap(s["root_bound"])}
        for p, x in last.items():
            row[f"root_{p}"], row[f"gap_{p}"] = float(x), gap(x)
        for p, x in g.set_index("probe")["status"].items():
            row[f"status_{p}"] = x
        row["repro_stored"] = bool(last["m-1"] == s["root_bound"])
        row["stored_minus_probe_rel"] = (float(s["root_bound"]) - float(last["m-1"])) / abs(V)
        row["E1_exact"] = bool(last["m1"] == last["m-1"])
        row["E1_rel_diff"] = (float(last["m1"]) - float(last["m-1"])) / abs(V)
        row["E2_dist"] = (abs(float(last["m0"]) - float(s["plain_perspective"])) / abs(V)
                          if arm == "perspective" else np.nan)
        row["E2_signed"] = ((float(last["m0"]) - float(s["plain_perspective"])) / abs(V)
                            if arm == "perspective" else np.nan)
        ft = "m-1_feastol1e-9"
        row["E3_ratio"] = (gap(last[ft]) / gap(last["m-1"])
                           if arm == "perspective" and ft in last.index else np.nan)
        if arm == "perspective_rescaled":
            gs = np.array([gap(last[p]) for p in ("m-1", "m0", "m1")])
            row["E4_spread"] = float(gs.max() / gs.min()) if gs.min() > 0 else np.nan
        else:
            row["E4_spread"] = np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def expectations(t: pd.DataFrame, rules: dict) -> dict:
    """The E1–E4 rules of n3.yaml applied to n3_table; "most" = more than half."""
    most = lambda k, n: k > n / 2
    e1 = {}
    for arm, g in t.groupby("arm", sort=True):
        k = int(g["E1_exact"].sum())
        e1[arm] = {"n": len(g), "exact": k, "hit": bool(most(k, len(g)))}
    e1["hit"] = all(v["hit"] for v in e1.values())
    p = t[t["arm"] == "perspective"]
    d2 = p["E2_dist"].dropna()
    k2 = int((d2 <= rules["E2_atol_rel"]).sum())
    r3 = p["E3_ratio"].dropna()
    lo, hi = rules["E3_band"]
    med3 = float(r3.median()) if len(r3) else np.nan
    q = t[t["arm"] == "perspective_rescaled"]
    s4 = q["E4_spread"]
    k4 = int((s4.dropna() <= rules["E4_factor"]).sum())
    sg = p["E2_signed"].dropna() if "E2_signed" in p else pd.Series(dtype=float)
    return {"E1": e1,
            "E2": {"n": len(d2), "within": k2, "hit": bool(most(k2, len(p))),
                   "signed_min": float(sg.min()) if len(sg) else np.nan,
                   "signed_max": float(sg.max()) if len(sg) else np.nan},
            "E3": {"n": len(r3), "median_ratio": med3,
                   "min": float(r3.min()) if len(r3) else np.nan,
                   "max": float(r3.max()) if len(r3) else np.nan,
                   "n_in_band": int(((r3 >= lo) & (r3 <= hi)).sum()),
                   "n_collapsed": int((r3 < lo).sum()), "hit": bool(lo <= med3 <= hi)},
            "E4": {"n": int(s4.notna().sum()), "n_undefined": int(s4.isna().sum()), "within": k4,
                   "max_spread": float(s4.max()) if s4.notna().any() else np.nan,
                   "hit": bool(most(k4, len(q)))}}


def _q(x) -> dict:
    x = pd.to_numeric(pd.Series(x), errors="coerce").dropna()
    return {"n": int(len(x)), "min": float(x.min()) if len(x) else np.nan,
            "median": float(x.median()) if len(x) else np.nan,
            "max": float(x.max()) if len(x) else np.nan}


def probe_summary(probes: pd.DataFrame, table: pd.DataFrame) -> dict:
    grp = probes.groupby(["arm", "probe"])
    out = {"n_probes": len(probes), "n_instances": int(table["inst"].nunique()),
           "statuses": {f"{a}/{p}": {str(k): int(v) for k, v in g["status"].value_counts().items()}
                        for (a, p), g in grp},
           "n_passes": {f"{a}/{p}": _q(g["n_passes"]) for (a, p), g in grp},
           "work": {f"{a}/{p}": _q(g["work"]) for (a, p), g in grp},
           "repro_stored": {a: {"n": len(g), "exact": int(g["repro_stored"].sum()),
                                "max_abs_rel": float(g["stored_minus_probe_rel"].abs().max())}
                            for a, g in table.groupby("arm")},
           "gaps": {}}
    for a, g in table.groupby("arm"):
        out["gaps"][a] = {c: _q(g[c]) for c in g.columns if c.startswith("gap_")}
        out["gaps"][a]["by_tightness"] = {
            tn: {c: _q(h[c]) for c in h.columns if c.startswith("gap_")}
            for tn, h in g.groupby(g["inst"].str.rsplit("_", n=1).str[-1])}
    return out


def main() -> int:
    run = None
    try:
        cfg = config("n3")
        frames, prov = load_stored(cfg)
        ncfg = run_meta(ROOT / cfg["runs"]["n1"])["config"]
        if ncfg != config("numerics"):
            raise ValueError("the stored N1 run's config differs from numerics.yaml")
        run, _ = open_run("n3", CONFIG, status="ok")

        # λ*, α and Σ at every (date, N) the stored weights use (P-RB at u = 6% on that universe)
        insts, pinsts = {}, {}
        pairs = sorted({(r["date"], str(r["N"])) for k in ("i1_points", "i2_points", "n1_solves")
                        for _, r in frames[k][["date", "N"]].drop_duplicates().iterrows()})
        for ym, N in pairs:
            insts[(ym, N)] = s3.instance(ym, "full" if N == "full" else int(N), 0.5)

        vol = vol_rows(frames, insts, float(cfg["v_check_rtol"]))
        base = baseline_rows(frames)
        tgt = float(cfg["target_vol"])
        n1v = vol[vol["experiment"] == "N1"]
        vsum = {"by_experiment_arm": vol_summary(vol, ["experiment", "arm"], tgt),
                "I1_base_points": vol_summary(vol[(vol["experiment"] == "I1") & (vol["point"] == "b")],
                                              ["experiment", "arm"], tgt),
                "N1_by_arm_presolve": vol_summary(n1v, ["arm", "presolve"], tgt),
                "N1_by_arm_tightness": vol_summary(n1v[n1v["presolve"] == -1], ["arm", "tightness"], tgt),
                "baseline": vol_summary(base, ["experiment"], tgt),
                "max_V_rel_diff": float(vol["V_rel_diff"].max()),
                "v_ties": {e: int(g["v_tie"].fillna(False).astype(bool).sum())
                           for e, g in vol[vol["experiment"] != "N1"].groupby("experiment")}}

        tasks = []
        for p in probe_plan(cfg, ncfg):
            k = (p["date"], p["N"], p["f"])
            if k not in pinsts:
                pinsts[k] = s3.instance(p["date"], p["N"], p["f"], ncfg, ncfg["n1"].get("K"))
            t = run_n1.make_task(ncfg, p, pinsts[k])
            inst = f"{p['date']}_N{p['N']}_f{p['f']:g}_K{t['K']}_{p['tightness']}"
            tasks.append({"id": f"{inst}_{p['arm']}", "inst": inst, "arm": p["arm"],
                          "rescale": t["rescale"], "kwargs": t["kwargs"], "s_obj": t["s_obj"],
                          "mip_gap": t["mip_gap"], "presolve": p["presolve"],
                          "work_limit": t["work_limit"], "probes": cfg["probes"][p["arm"]]})
        probes = pool_chunks(run, ("n3_probes",), tasks, lambda t: t["id"], probe_task,
                             int(cfg["workers"]))["n3_probes"]
        stored = stored_roots(frames["n1_solves"], frames["n1_relax"])
        table = n3_table(probes, stored)
        summary = {"inputs": prov, "volatility": vsum,
                   "probes": probe_summary(probes, table),
                   "expectations": expectations(table, cfg["expectations"]),
                   "plain_perspective_ok": int(stored.drop_duplicates("inst")["plain_perspective_ok"].sum()),
                   "notes": ["n_passes counts Gurobi's MIPNODE callbacks at node 0; Gurobi reports no "
                             "root-cut-pass attribute",
                             "I1 and I2 store the combined V's weights only (DESIGN §6)"]}
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        e = summary["expectations"]
        finish(run, CONFIG, {"n3_vol": vol, "n3_baseline_vol": base, "n3_probes": probes,
                             "n3_table": table},
               f"n3: {len(vol)} weight vectors; {len(probes)} probes; E1 {e['E1']['hit']}, "
               f"E2 {e['E2']['hit']}, E3 {e['E3']['hit']}, E4 {e['E4']['hit']}",
               extra_files=[run / "summary.json"])
        print(json.dumps({"volatility": vsum, "expectations": e}, indent=1, default=float)[:6000])
    except Exception as err:
        fail(run, CONFIG, err)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
