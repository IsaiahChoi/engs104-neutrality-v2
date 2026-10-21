"""The optional C1 analysis of the GATE DESIGN addendum (experiments/run_c1_ratio.py): for each
flagged C1 envelope point, |F − B| at δ = 0.1% over |F − B| at δ = 1% (F, B the forward and
backward differences). A quadratic piece gives exactly the step ratio 0.1; a slope break at b
gives 1."""
from __future__ import annotations

import pytest

from experiments.run_c1_ratio import BANDS, classify, fb_ratio


def test_quadratic_gives_the_step_ratio():
    f = lambda b: 0.003 * b - 0.4 * (b - 0.02) ** 2
    b, hc, hf = 0.02, 2e-4, 2e-5
    r = fb_ratio(f(b), f(b + hc), f(b - hc), hc, f(b + hf), f(b - hf), hf)
    assert r["ratio"] == pytest.approx(0.1, rel=1e-6) and classify(r["ratio"]) == "near 0.1"


def test_slope_break_gives_one():
    f = lambda b: min(0.003 * b, 0.001 * b + 0.00004)          # kink at b = 0.02
    b, hc, hf = 0.02, 2e-4, 2e-5
    r = fb_ratio(f(b), f(b + hc), f(b - hc), hc, f(b + hf), f(b - hf), hf)
    assert r["ratio"] == pytest.approx(1.0, rel=1e-6) and classify(r["ratio"]) == "near 1"


def test_bands():
    assert BANDS == {"near 0.1": (0.05, 0.2), "near 1": (0.5, 2.0)}
    assert classify(0.3) == "other" and classify(float("nan")) == "undefined"
