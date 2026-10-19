"""Shared real-data fixtures for the v2 tests (not collected by pytest: no test_ prefix).

A month "YYYY-MM" is the rebalance date (last trading day) in that month, as in DESIGN §7.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from src.alpha.momentum import momentum_alpha
from src.opt.continuous import ContinuousProblem, Mandate, load_config
from src.opt.inputs import date_inputs, market_data, rebalance_dates
from src.risk.factor_model import FACTORS


def month_end(ym: str) -> pd.Timestamp:
    dates = rebalance_dates()
    hit = dates[dates.to_period("M") == pd.Period(ym, "M")]
    assert len(hit) == 1, ym
    return hit[0]


@lru_cache(maxsize=16)
def case(ym: str):
    """(DateInputs, momentum alpha, base Mandate) at the month-end of `ym`, full universe."""
    di = date_inputs(month_end(ym))
    return di, momentum_alpha(di.model, market_data().ret), load_config()[0]


def problem(ym: str, mandate: Mandate | None = None) -> ContinuousProblem:
    di, _, base = case(ym)
    m = di.model
    return ContinuousProblem(m.B, m.F, m.d, di.sector_matrix(), mandate or base, adv=di.adv,
                             factor_names=FACTORS)
