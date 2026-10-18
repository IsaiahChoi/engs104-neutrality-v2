"""E1 / RQ1 — constraint cost curves (brief §7 E1). Run with `make rq1` (requires the freeze).

For each E1 date and alpha (momentum; synthetic IC 0.05, draws 0–19), with λ read from the λ
record (fixed per (date, alpha); synthetic draws share the IC's λ), sweep each family's grid
one at a time with all other families at base, and record at every point U*, A = α'w*, ex-ante
volatility, TC (cosine and diagonal), every shadow price and the binding set; store the
weights. Constraint attribution at the base case for every (date, alpha, draw).
"off" removes the family (a problem built without it); for a single style factor it sets that
factor's bound to +inf (verified identical to removing that constraint; the largest |y_k|
reached is recorded as `max_abs_style_exposure`). Checkpoint: one chunk per date.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace

import numpy as np
import pandas as pd

from experiments.common import chunk_path, combine, fail, finish, open_run, write_chunk
from experiments.designs import check_config_path, config, e1_dates
from src.alpha.momentum import momentum_alpha
from src.alpha.synthetic import draw_rng, residual_returns, synthetic_alpha
from src.opt.attribution import (attribution, implied_alpha_adjustments, shadow_prices,
                                 tc_diagonal, transfer_coefficient)
from src.opt.continuous import ContinuousProblem, load_config
from src.opt.inputs import date_inputs, market_data, next_rebalance_date
from src.opt.lambda_policy import LambdaBook, alpha_key
from src.risk.factor_model import FACTORS

OFF_STYLE = np.inf   # removes one style factor's bound (REVIEW 3: identical to removal)
REMOVABLE = {"dollar": "dollar", "beta": "beta", "style_all": "style", "sector": "sector",
             "gross": "gross", "position": "position", "liquidity": "liquidity_theta"}


def sweep_points(cfg: dict) -> list[tuple[str, float | None]]:
    return [(fam, v) for fam, grid in cfg["sweeps"].items() for v in grid]


def base_value(mandate, family: str):
    if family.startswith("style"):
        return mandate.style
    return getattr(mandate, REMOVABLE[family])


def build(di, mandate) -> dict[str, ContinuousProblem]:
    m = di.model
    mk = lambda md: ContinuousProblem(m.B, m.F, m.d, di.sector_matrix(), md, adv=di.adv,
                                      factor_names=FACTORS)
    probs = {"base": mk(mandate)}
    for fam, field in REMOVABLE.items():
        probs[f"off:{fam}"] = mk(replace(mandate, **{field: None}))
    return probs


def apply_point(P: ContinuousProblem, mandate, family: str, value: float) -> None:
    """Set one family's bound on the base problem (restored by reset)."""
    if family in ("dollar", "beta", "gross", "sector"):
        P.set_bound(family, value)
    elif family == "style_all":
        P.set_bound("style", value)
    elif family.startswith("style:"):
        P.set_bound("style", value, index=P.style_names.index(family.split(":")[1]))
    elif family == "position":
        P.set_position_caps(value, mandate.liquidity_theta)
    elif family == "liquidity":
        P.set_position_caps(mandate.position, value)
    else:
        raise KeyError(family)


def snapshot(P):
    vals = {k: np.array(p.value, float) if p.shape else float(p.value) for k, p in P.bounds.items()}
    return vals, P.position_caps


def reset(P, snap):
    vals, caps = snap
    for k, v in vals.items():
        P.bounds[k].value = v
    P.position_caps = caps


def record(P, sol, alpha, lam, ids: dict, tickers) -> tuple[dict, pd.DataFrame]:
    sp = shadow_prices(P, sol)
    y = P.exposures(sol.w)
    style = np.delete(y, P.mkt)
    row = {**ids, "lam": lam, "U": sol.objective, "A": float(alpha @ sol.w),
           "vol_ann": P.ann_vol(sol.w), "tc": transfer_coefficient(P, alpha, sol.w),
           "tc_diag": tc_diagonal(alpha, sol.w, P.d), "net": float(sol.w.sum()),
           "gross": float(np.abs(sol.w).sum()), "beta_exposure": float(y[P.mkt]),
           "max_abs_style_exposure": float(np.abs(style).max()), "status": sol.status,
           "solve_time": sol.solve_time,
           "binding": ",".join(sorted(k for k, v in sp.items() if ":" not in k and v > 1e-9))}
    row.update({f"sp_{k}": v for k, v in sp.items()})
    nz = np.abs(sol.w) > 1e-12
    w = pd.DataFrame({"point_id": ids["point_id"], "ticker": np.asarray(tickers)[nz],
                      "w": sol.w[nz]})
    return row, w


def run_date(date, cfg, mandate, book, seed, families=None,
             draws=None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """All E1 points at one date. `families` / `draws` restrict the work (tests only)."""
    di = date_inputs(date)
    md = market_data()
    ds = f"{date:%Y-%m-%d}"
    probs = build(di, mandate)
    base = probs["base"]
    snap = snapshot(base)
    syn = cfg["alphas"]["synthetic"]
    e = residual_returns(di.model, md.excess, md.factors, next_rebalance_date(date))
    alphas = [("momentum", -1, cfg["alphas"]["momentum"]["ic"], momentum_alpha(di.model, md.ret),
               book.get(ds, "momentum"))]
    lam_syn = book.get(ds, alpha_key("synthetic", syn["ic"]))
    for k in range(syn["draws"] if draws is None else draws):
        a = synthetic_alpha(e, di.model.d, syn["ic"], draw_rng(seed, date, syn["ic"], k))[0]
        alphas.append(("synthetic", k, syn["ic"], a, lam_syn))
    rows, weights, attrib = [], [], []
    for kind, draw, ic, alpha, lam in alphas:
        for family, value in sweep_points(cfg):
            if families is not None and family not in families:
                continue
            off = value is None
            if off and family in REMOVABLE:
                P = probs[f"off:{family}"]
            else:
                P = base
                apply_point(P, mandate, family, OFF_STYLE if off else value)
            sol = P.solve(alpha, lam=lam)
            is_base = (not off) and np.isclose(value, base_value(mandate, family))
            pid = f"{ds}|{kind}|{draw}|{family}|{'off' if off else f'{value:g}'}"
            ids = {"point_id": pid, "date": ds, "alpha": kind, "draw": draw, "ic": ic,
                   "family": family, "value": np.nan if off else float(value), "off": off,
                   "is_base": bool(is_base), "N": P.N}
            row, w = record(P, sol, alpha, lam, ids, di.tickers)   # before reset: the shadow
            reset(base, snap)                                      # prices need the swept caps
            rows.append(row)
            weights.append(w)
        sol = base.solve(alpha, lam=lam)
        at = attribution(base, sol)
        res = implied_alpha_adjustments(base, sol)["residual"]
        attrib.append({"date": ds, "alpha": kind, "draw": draw, "lam": lam,
                       "alpha_total": at["alpha_total"], "alpha_ideal": at["alpha_ideal"],
                       **{f"alpha_{k}": v for k, v in at["alpha_by_family"].items()},
                       "reconstruction_error": at["reconstruction_error"],
                       "kkt_residual_max": float(np.abs(res).max())})
    return pd.DataFrame(rows), pd.concat(weights, ignore_index=True), pd.DataFrame(attrib)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="experiments/configs/rq1.yaml")
    args = p.parse_args()
    check_config_path("rq1", args.config)
    run = None
    try:
        cfg = config("rq1")
        mandate, mcfg = load_config(cfg["mandate_config"])
        run, meta = open_run("rq1", args.config, {"seed": cfg["seed"], "off_style_bound": OFF_STYLE})
        book = LambdaBook(meta["lambda_book"])
        for date in e1_dates():
            key = f"{date:%Y-%m-%d}"
            if chunk_path(run, "points", key).exists():
                continue
            t0 = time.time()
            pts, w, at = run_date(date, cfg, mandate, book, cfg["seed"])
            write_chunk(chunk_path(run, "weights", key), w)
            write_chunk(chunk_path(run, "attribution", key), at)
            write_chunk(chunk_path(run, "points", key), pts)
            print(f"{key}: {len(pts)} points in {time.time() - t0:.0f}s", flush=True)
        pts = combine(run, "points")
        finish(run, args.config, {"points": pts, "attribution": combine(run, "attribution")},
               f"rq1 {len(pts)} points")
    except Exception as e:
        fail(run, args.config, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
