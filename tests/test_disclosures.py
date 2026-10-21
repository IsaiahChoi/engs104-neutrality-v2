"""experiments/run_disclosures.py (DESIGN §11.5 item 3; S4): one-pass winsorization can leave
|z| above 3. Tests first, against constructed cross-sections whose answer is known."""
from __future__ import annotations

import numpy as np
import pytest

from experiments import run_disclosures as R
from src.alpha.momentum import winsorized_zscore


def test_one_pass_winsorization_can_leave_z_above_the_clip():
    """Negative control for the disclosure: one large outlier among small values. After clipping
    at ±3 the re-standardization shrinks the spread, so the clipped value exceeds 3 again."""
    x = np.r_[np.zeros(99), 100.0]
    z = winsorized_zscore(x)
    s = R.z_stats(z)
    assert s["max_abs_z"] > 3 and s["n_above"] == 1 and s["n"] == 100
    assert s["max_abs_z"] == pytest.approx(np.abs(z).max())


def test_z_stats_on_a_cross_section_within_the_clip():
    z = winsorized_zscore(np.linspace(-1.0, 1.0, 50))
    s = R.z_stats(z)
    assert s["n_above"] == 0 and s["max_abs_z"] <= 3


def test_summary_pools_dates_and_counts_skips():
    rows = [{"date": "a", "n": 10, "max_abs_z": 2.5, "n_above": 0},
            {"date": "b", "n": 12, "max_abs_z": 3.4, "n_above": 2}]
    out = R.summarize(rows, skipped=[{"date": "c", "reason": "lookback"}])
    assert out["n_dates"] == 2 and out["n_skipped"] == 1
    assert out["max_abs_z"] == 3.4 and out["max_abs_z_date"] == "b"
    assert out["n_dates_above"] == 1 and out["n_names_above"] == 2 and out["n_names"] == 22
