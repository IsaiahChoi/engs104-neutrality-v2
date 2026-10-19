"""Universe subsamples and P-MI mandates (ported from v1 experiments/run_rq3.py; DESIGN §4, §3.4).

A subsample of size N is the top N eligible names by ADV (the median daily dollar volume over the
63 trading days ending at the date, src.opt.inputs.adv), ties broken stably; "full" is every
eligible name. The alpha is computed on the full universe and restricted (v2 keeps v1's
"restrict" rule only). P-MI uses the base mandate with u = 6%.

pmi_instance builds one P-MI instance (DESIGN §3.4, §8 P3): λ* is μ_risk of P-RB solved on the
same universe at the base mandate with u = 6% (its root-found λ, src.opt.risk_budget); the
continuous support size S counts |w_i| > 1e-6 in that P-RB; K = round(f·S), rounding half up
(a convention: DESIGN does not say), and at least 1.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from src.alpha.momentum import momentum_alpha
from src.opt.continuous import ContinuousProblem, Mandate, load_config
from src.opt.inputs import DateInputs, date_inputs, market_data
from src.opt.risk_budget import solve_risk_budget
from src.risk.factor_model import FACTORS

MIQP_POSITION_CAP = 0.06
MIQP_MIN_POSITION = 0.0025           # ℓ (DESIGN §3.3)
SUPPORT_TOL = 1e-6                   # P3: |w_i| > 1e-6 counts toward S


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


def round_half_up(x: float) -> int:
    return int(np.floor(x + 0.5))


@dataclass(frozen=True)
class PMIInstance:
    date: pd.Timestamp
    n: object                        # the subsample size requested (int or "full")
    f: float                         # K = round(f·S)
    B: np.ndarray
    F: np.ndarray
    d: np.ndarray
    S: np.ndarray
    adv: np.ndarray
    tickers: list
    alpha: np.ndarray
    lam: float                       # λ* (root-found, P-RB at u = 6% on this universe)
    risk_binding: bool
    mandate: Mandate
    S_support: int
    K: int
    ell: float

    @property
    def N(self) -> int:
        return len(self.d)

    @property
    def kwargs(self) -> dict:
        """Keyword arguments for src.opt.integer.PMI (formulation and s_obj left to the caller)."""
        return dict(B=self.B, F=self.F, d=self.d, S=self.S, alpha=self.alpha, lam=self.lam,
                    mandate=self.mandate, adv=self.adv, K=self.K, ell=self.ell,
                    factor_names=FACTORS)


def pmi_instance(date, n, f: float, ell: float = MIQP_MIN_POSITION,
                 position: float = MIQP_POSITION_CAP, base: Mandate | None = None) -> PMIInstance:
    """The P-MI instance at (date, n) with K = round(f·S) (module docstring)."""
    di, alpha_full, idx = subsample(date, n)
    B, F, d, S, adv, tickers = restricted(di, idx)
    alpha = alpha_full[idx]
    md = miqp_mandate(base if base is not None else load_config()[0], position=position)
    P = ContinuousProblem(B, F, d, S, md, adv=adv, factor_names=FACTORS)
    rb = solve_risk_budget(P, alpha)
    S_support = int((np.abs(rb.sol.w) > SUPPORT_TOL).sum())
    return PMIInstance(date=di.date, n=n, f=float(f), B=B, F=F, d=d, S=S, adv=adv,
                       tickers=tickers, alpha=alpha, lam=rb.lam, risk_binding=rb.risk_binding,
                       mandate=md, S_support=S_support, K=max(1, round_half_up(f * S_support)),
                       ell=float(ell))
