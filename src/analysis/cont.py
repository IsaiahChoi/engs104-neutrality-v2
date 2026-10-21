"""Continuous-result statistics for the report (S4), recomputed from the C runs' frames.

- k17: CHECKS K17 on the C2 sweeps. Within each (date, alpha, family) sweep, sorted by the bound
  with "off" last (+∞): A* must not decrease as the bound loosens (tolerance 1e-8·A*, with A* the
  smaller of the pair), and on the finite bounds the successive secant slopes must not increase
  (tolerance 1e-6·A* per unit of bound, A* the smallest of the triple).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MONO_RTOL = 1e-8
CONC_RTOL = 1e-6


def k17(points: pd.DataFrame) -> dict:
    n_sweeps = n_pairs = n_triples = mono = conc = 0
    worst_mono = worst_conc = 0.0
    for _, g in points.groupby(["date", "alpha", "family"], sort=True):
        n_sweeps += 1
        b = np.where(g["off"].astype(bool), np.inf, g["value"].astype(float))
        order = np.argsort(b, kind="stable")
        b, A = b[order], g["A"].to_numpy(float)[order]
        for k in range(len(A) - 1):
            n_pairs += 1
            tol = MONO_RTOL * min(abs(A[k]), abs(A[k + 1]))
            drop = A[k] - A[k + 1]
            worst_mono = max(worst_mono, drop / tol if tol > 0 else (np.inf if drop > 0 else 0.0))
            mono += int(drop > tol)
        fin = np.isfinite(b)
        bf, Af = b[fin], A[fin]
        for k in range(len(bf) - 2):
            n_triples += 1
            s1 = (Af[k + 1] - Af[k]) / (bf[k + 1] - bf[k])
            s2 = (Af[k + 2] - Af[k + 1]) / (bf[k + 2] - bf[k + 1])
            tol = CONC_RTOL * min(abs(Af[k]), abs(Af[k + 1]), abs(Af[k + 2]))
            rise = s2 - s1
            worst_conc = max(worst_conc, rise / tol if tol > 0 else (np.inf if rise > 0 else 0.0))
            conc += int(rise > tol)
    return {"n_sweeps": n_sweeps, "n_pairs": n_pairs, "n_triples": n_triples, "n_points": len(points),
            "monotone_failures": mono, "concavity_failures": conc,
            "worst_monotone_over_tol": float(worst_mono), "worst_concavity_over_tol": float(worst_conc)}
