"""Universe subsamples and P-MI mandates (ported from v1 experiments/run_rq3.py; DESIGN §4, §3.4).

A subsample of size N is the top N eligible names by ADV (the median daily dollar volume over the
63 trading days ending at the date, src.opt.inputs.adv), ties broken stably; "full" is every
eligible name. The alpha is computed on the full universe and restricted (v2 keeps v1's
"restrict" rule only). P-MI uses the base mandate with u = 6%.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from src.alpha.momentum import momentum_alpha
from src.opt.continuous import Mandate
from src.opt.inputs import DateInputs, date_inputs, market_data

MIQP_POSITION_CAP = 0.06


def subsample(date, n) -> tuple[DateInputs, np.ndarray, np.ndarray]:
    """(DateInputs, α_mom over the full universe, sorted index of the top-n names by ADV)."""
    di = date_inputs(date)
    alpha = momentum_alpha(di.model, market_data().ret)
    if n == "full":
        idx = np.arange(di.model.N)
    else:
        idx = np.sort(np.argsort(-di.adv, kind="stable")[:int(n)])
    return di, alpha, idx


def restricted(di: DateInputs, idx):
    """(B, F, d, S, adv, tickers) on the names in idx; sectors with no name there are dropped."""
    m = di.model
    S = di.sector_matrix()[idx]
    return (m.B[idx], m.F, m.d[idx], S[:, S.sum(axis=0) > 0], di.adv[idx],
            list(np.asarray(di.tickers)[idx]))


def miqp_mandate(base: Mandate, position: float = MIQP_POSITION_CAP, style: float | None = None,
                 beta: float | None = None) -> Mandate:
    """The base mandate with the P-MI position cap and optional style/beta tightness."""
    m = replace(base, position=position)
    if style is not None:
        m = replace(m, style=style)
    if beta is not None:
        m = replace(m, beta=beta)
    return m
