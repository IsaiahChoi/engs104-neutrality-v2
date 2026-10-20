"""Shared helpers for the continuous runners C1–C3 (DESIGN §7) and the CONT self-checks: the
date's inputs and α_mom, P-RB problems, the all-off mandate, and a process pool over chunks
(each finished item is one chunk, so a killed run resumes; experiments/common.py). S2d: a kill
between an item's chunk writes no longer blocks the resume (pool_chunks)."""
from __future__ import annotations

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import pandas as pd

from experiments.common import chunk_path, combine, write_chunk
from experiments.designs import month_end
from src.alpha.momentum import momentum_alpha
from src.opt.continuous import ContinuousProblem, Mandate
from src.opt.inputs import date_inputs, market_data
from src.opt.risk_budget import LAMBDA_MIN, ROOT_RTOL, TARGET_VOL
from src.risk.factor_model import FACTORS
from src.utils import utc_timestamp

# every family off and no costs: the unconstrained, costless P-RB (A2/A3's denominator)
OFF = Mandate(dollar=None, beta=None, style=None, sector=None, gross=None, position=None,
              liquidity_theta=None, borrow_annual=0.0, trade_cost=0.0)


def check_p_rb(cfg: dict) -> None:
    """continuous.yaml's P-RB block must state the settings src/opt/risk_budget.py uses."""
    p = cfg["p_rb"]
    got = (p["target_annual_vol"], p["root_rtol"], p["lambda_min"])
    if got != (TARGET_VOL, ROOT_RTOL, LAMBDA_MIN):
        raise ValueError(f"continuous.yaml p_rb {got} != risk_budget {(TARGET_VOL, ROOT_RTOL, LAMBDA_MIN)}")


def case(month_or_date):
    """(DateInputs, α_mom over the full universe) at a month "YYYY-MM" or a rebalance date."""
    d = month_end(month_or_date) if isinstance(month_or_date, str) and len(month_or_date) == 7 \
        else pd.Timestamp(month_or_date)
    di = date_inputs(d)
    return di, momentum_alpha(di.model, market_data().ret)


def problem(di, mandate: Mandate) -> ContinuousProblem:
    m = di.model
    return ContinuousProblem(m.B, m.F, m.d, di.sector_matrix(), mandate, adv=di.adv,
                             factor_names=FACTORS)


def _set_aside_incomplete(run, kinds: tuple[str, ...], k: str) -> None:
    """An unfinished item's leftover secondary chunks (a kill between its chunk writes) move to
    chunks/_incomplete/<kind>/ (kept, never deleted), so the write-once rewrite can proceed."""
    for kind in kinds[1:]:
        p = chunk_path(run, kind, k)
        if p.exists():
            dst = Path(run) / "chunks" / "_incomplete" / kind
            dst.mkdir(parents=True, exist_ok=True)
            p.rename(dst / f"{k}_{utc_timestamp().replace(':', '')}.parquet")


def pool_chunks(run, kinds: tuple[str, ...], items: list, key: Callable, fn: Callable,
                workers: int) -> dict[str, pd.DataFrame]:
    """fn(item) -> {kind: DataFrame}; items whose first chunk exists are skipped (resume). The first
    kind is written last, as the completion marker; an unfinished item's leftover chunks are set
    aside (_set_aside_incomplete) before it is recomputed."""
    todo = [it for it in items if not chunk_path(run, kinds[0], key(it)).exists()]
    for it in todo:
        _set_aside_incomplete(run, kinds, key(it))
    if todo:
        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
            futs = {ex.submit(fn, it): it for it in todo}
            for fut in as_completed(futs):
                it, out = futs[fut], fut.result()
                for kind in reversed(kinds):          # the first kind last: it marks completion
                    write_chunk(chunk_path(run, kind, key(it)), out[kind])
                print(f"{kinds[0]} {key(it)} done", flush=True)
    return {kind: combine(run, kind) for kind in kinds}
