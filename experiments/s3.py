"""Shared machinery for the S3 runners run_i1, run_i2, run_n1 and run_n2 (DESIGN §7), written in S2d
(item 5) before GATE DESIGN, so S3 does not start with untested runners.

- Config guard. A runner reads its DESIGN config (integer.yaml for I1/I2, numerics.yaml for N1/N2)
  by default. While that config's status starts with "proposed" (pending GATE DESIGN) a production
  run is refused: the I1 constraint set and the other parameters are decided there (Decision 31)
  and must not be chosen from results. `--config <path>` accepts only a file under
  experiments/configs/ marked `smoke: true` for this runner (the S2d crash tests); its run is
  logged with RUN_LOG status "pilot" and is marked superseded afterwards.
- Instances: experiments.instances.pmi_instance at (date, N, f) with the config's u and ℓ; where the
  config states K for that (date, N), the computed K must be one of them.
- Checker. Every P-MI solve records the independent checker's 1e-9 verdict on V's weights
  (PMIResult.polished_violations; CHECKS K26); continuous solutions are checked by
  continuous_verdict at the problem's current bounds (src.opt.feasibility, default tolerance 1e-7
  as in C1–C3).
- Summaries hold statuses, counts, Work and Runtime only (solve_summary). Estimator errors, root
  gaps and agreement are computed by the S3 analysis (S3 item 3), not by the runners.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.designs import CONFIGS, config, month_end
from experiments.instances import pmi_instance
from experiments.run_pilot_s2b import _rec
from src.opt.continuous import ContinuousProblem, load_config
from src.opt.feasibility import violations
from src.risk.factor_model import FACTORS
from src.utils import ROOT

DEFAULT_CONFIG = {"i1": "integer", "i2": "integer", "n1": "numerics", "n2": "numerics"}
WORKERS = 4                          # DESIGN §6: up to 4 workers


def load_run_config(runner: str, argv=None) -> tuple[str, dict, str]:
    """(config path relative to the repo, config, RUN_LOG status) under the config guard."""
    p = argparse.ArgumentParser(prog=f"experiments.run_{runner}")
    p.add_argument("--config", default=None)
    args = p.parse_args(argv)
    if args.config is None:
        name = DEFAULT_CONFIG[runner]
        cfg = config(name)
        if str(cfg.get("status", "")).startswith("proposed"):
            raise RuntimeError(f"{name}.yaml is '{cfg['status']}': a production {runner} run waits "
                               "for GATE DESIGN (smoke runs take --config experiments/configs/smoke_*.yaml)")
        return f"experiments/configs/{name}.yaml", cfg, "ok"
    path = Path(args.config)
    full = (ROOT / path if not path.is_absolute() else path).resolve()
    if full.parent != CONFIGS.resolve():
        raise ValueError(f"--config must be a file in experiments/configs/, got {args.config}")
    cfg = config(full.stem)
    if cfg.get("smoke") is not True or cfg.get("runner") != runner:
        raise ValueError(f"--config takes only a smoke config for {runner} (smoke: true, runner: "
                         f"{runner}); got {args.config}")
    return str(full.relative_to(ROOT)), cfg, "pilot"


def instance(ym: str, N, f: float, cfg: dict | None = None, K_table: dict | None = None):
    """The P-MI instance (experiments.instances.pmi_instance) with the config's u and ℓ; K checked
    against K_table[ym] (a {S, K} block, or one per str(N)) where given."""
    md = (cfg or {}).get("mandate", {})
    inst = pmi_instance(month_end(ym), N, f, ell=float(md.get("min_position", 0.0025)),
                        position=float(md.get("position", 0.06)))
    if K_table and ym in K_table:
        blk = K_table[ym].get(str(N), K_table[ym]) if isinstance(K_table[ym], dict) else None
        if blk is not None and "K" in blk and inst.K not in blk["K"]:
            raise ValueError(f"K = {inst.K} at ({ym}, N = {N}, f = {f}) is not in the config's {blk['K']}")
    return inst


def tightened(mandate, tight: dict | None):
    return replace(mandate, **{k: float(v) for k, v in (tight or {}).items()})


def pmi_record(r, extra: dict) -> dict:
    """One P-MI solve's record (the S2b runner's fields: status, V, B, B_eff, gaps, cone effect,
    checker verdicts, Work, Runtime, nodes, settings), plus the raw incumbent's verdict at
    Gurobi's tolerances (CHECKS K26)."""
    return {**_rec(r, extra), "incumbent_verdict": r.incumbent_verdict}


SLOPE_RULES = {"central": "design", "three_point": "three_point"}


def slope_rule(config_method: str) -> str:
    """src.opt.slopes method for a config's perspective_slope_method. "central" (the estimate is
    the central slope, Decision 38) runs DESIGN §6 as edited at GATE DESIGN: slopes.py's "design"
    rule (5-point stencil, three-point one-sided slopes, 8N kink floor, two-point concavity)."""
    if config_method not in SLOPE_RULES:
        raise ValueError(f"perspective_slope_method {config_method!r} not in {sorted(SLOPE_RULES)}")
    return SLOPE_RULES[config_method]


ARMS = {"bigm": ("bigm", False), "perspective": ("perspective", False),
        "perspective_rescaled": ("perspective", True)}


def persp_raw_columns(rec: dict, key: str) -> dict:
    """The perspective relaxation's raw Clarabel dual for `key`, a diagnostic (DESIGN §6, A9).
    mu_persp_raw is read from `shadow` (usable duals only, nan if the relaxation failed); under
    Decision 25 a failed relaxation's kept raw dual goes to mu_persp_raw_unusable instead (nan
    when the relaxation succeeded or Clarabel returned none). No estimator reads either."""
    usable = bool(rec.get("raw_duals_usable", False))
    return {"mu_persp_raw": rec["shadow"].get(key, np.nan),
            "mu_persp_raw_unusable": np.nan if usable else rec.get("raw_duals", {}).get(key, np.nan),
            "persp_raw_usable": usable, "persp_raw_status": rec["status"]}


def point_flag_summary(df: pd.DataFrame) -> dict:
    """Counts over I1/I2 points: points, flag_V_exceeds_B (DESIGN §6's second flag on the point's
    V and B, combined across formulations under combined certification), undefined V."""
    if df.empty:
        return {"n_points": 0, "n_flag_V_exceeds_B": 0, "n_V_undefined": 0}
    return {"n_points": len(df), "n_flag_V_exceeds_B": int(df["flag_V_exceeds_B"].astype(bool).sum()),
            "n_V_undefined": int(df["V"].isna().sum())}


def baseline_problem(kwargs: dict) -> tuple[ContinuousProblem, np.ndarray]:
    """The continuous baseline's problem on a P-MI instance: the same universe and mandate (u = 6%),
    no integer parts (DESIGN §7 I1 (d))."""
    P = ContinuousProblem(kwargs["B"], kwargs["F"], kwargs["d"], kwargs["S"], kwargs["mandate"],
                          adv=kwargs["adv"], factor_names=FACTORS)
    return P, np.asarray(kwargs["alpha"], float)


def continuous_verdict(problem: ContinuousProblem, w, tol: float = 1e-7) -> str:
    """src.opt.feasibility.violations on w at the problem's current bounds, as JSON; a style or
    sector bound not common to every element is checked element by element."""
    w = np.asarray(w, float)
    b = {k: problem.bound(k) for k in problem.bounds if k != "position"}
    common = lambda v: bool(np.all(v == v.flat[0]))
    first = lambda k: (float(b[k].flat[0]) if common(b[k]) else None) if k in b else None
    eff = replace(problem.mandate, dollar=first("dollar"), beta=first("beta"), gross=first("gross"),
                  style=first("style"), sector=first("sector"))
    v = violations(w, problem.B, problem.S, eff, problem.adv, mkt=problem.mkt, tol=tol)
    if "style" in b and not common(b["style"]):
        y = problem.B.T @ w
        names = problem.style_names or [str(k) for k in problem.style_idx]
        v.update({f"style:{n}": float(abs(y[k]) - bk) for n, k, bk in
                  zip(names, problem.style_idx, b["style"]) if abs(y[k]) > bk + tol})
    if "sector" in b and not common(b["sector"]):
        sw = problem.S.T @ w
        v.update({f"sector:{j}": float(abs(sw[j]) - bj) for j, bj in enumerate(b["sector"])
                  if abs(sw[j]) > bj + tol})
    return json.dumps(v, sort_keys=True)


def solve_summary(df: pd.DataFrame) -> dict:
    """Statuses, the checker's violation count (V's weights at 1e-9), undefined V, Work, Runtime."""
    if df.empty:
        return {"n": 0}
    pv = df["polished_violations"]
    return {"n": len(df), "statuses": {str(k): int(v) for k, v in df["status"].value_counts().items()},
            "n_checker_violations": int((~pv.isin(["{}", "V undefined"])).sum()),
            "n_v_undefined": int(df["V"].isna().sum()),
            "work_total": float(df["work"].sum()), "work_median": float(df["work"].median()),
            "runtime_total": float(df["runtime"].sum())}


def workers(cfg: dict) -> int:
    return int(cfg.get("workers", WORKERS))


def base_mandate():
    return load_config()[0]
