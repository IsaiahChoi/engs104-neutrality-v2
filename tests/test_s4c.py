"""S4c (Isaiah's S4c addendum, PROGRESS 2026-10-25; DESIGN §10 and §11.1 as edited for Decision 54):
Fig. 1 in three panels in one row with text ≥ 8 pt at 3.5 in; the macros for the step 2–3 fixes;
the idealized-C1 comparisons over every point (Q-a: φ rounds above 1 for α∥); Table I's sector
bound renamed (F13). Tests first. The four-panel Fig. 1 and Table III (N2(b)) stay generated
(their S4b tests pin them; Decision 55's pattern) but leave the report."""
from __future__ import annotations

import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.text import Text
from pypdf import PdfReader

from src.figures import fig_c, make_all, numbers

IN = 72.0


def _size(path) -> tuple[float, float]:
    b = PdfReader(path).pages[0].mediabox
    return float(b.width) / IN, float(b.height) / IN


# ----- Fig. 1, three panels in one row -----

def test_fig1_row_has_the_three_design_panels():
    assert [k for k, _ in fig_c.FIG1_ROW_PANELS] == ["liquidity", "sector", "style_all"]
    assert {k for k, _ in fig_c.FIG1_ROW_PANELS} & fig_c.FACTOR_FAMILIES == {"style_all"}


def test_fig1_row_is_one_row_at_column_width_with_8pt_text():
    fig = fig_c.fig1_row_figure()
    try:
        axes = fig.get_axes()
        assert len(axes) == 3
        y0 = {round(ax.get_position().y0, 6) for ax in axes}
        assert len(y0) == 1                                         # one row
        w, _ = fig.get_size_inches()
        assert w <= 3.5 + 1e-9
        sizes = [t.get_fontsize() for t in fig.findobj(Text) if t.get_visible() and t.get_text().strip()]
        assert sizes and min(sizes) >= 8.0
    finally:
        plt.close(fig)
    w, h = _size(fig_c.fig1_cost_curves_row())
    assert w <= 3.5 + 1e-6 and h <= 2.6                             # four-panel version: 3.3 in


def test_fig1_row_is_generated_and_four_panel_version_kept():
    assert ("fig1_cost_curves_row", fig_c.fig1_cost_curves_row) in make_all.REPORT_FIGURES
    assert "fig1_cost_curves" in [n for n, _ in make_all.FIGURES]


# ----- idealized C1: every point compared (Q-a) -----

def test_ideal_errors_compare_every_point_with_clipped_closed_forms():
    ide = pd.DataFrame({
        "mandate": ["factor"] * 4 + ["factor_dollar"],
        "alpha": ["mom", "par", "par", "perp", "par"],
        "phi": [0.25, 1.0 - 4e-15, 1.0 + 2e-16, 0.0, 1.0 + 2e-16],
        "retained_num": [np.sqrt(0.75), 0.0, 0.0, 1.0, 0.0],
        "A_num": [1.0, 0.0, 0.0, 2.0, 0.0],
        "A_cf": [1.0, 1e-17, np.nan, 2.0, 0.0],
    })
    r = numbers.ideal_errors(ide)
    assert r["n_factor"] == 4 and r["n_nonzero"] == 2 and r["n_zero"] == 3
    assert r["ret_err"] == pytest.approx(np.sqrt(1.0 - (1.0 - 4e-15)), rel=1e-12)   # the α∥ rounding, not NaN-skipped
    assert r["ret_err_non_par"] == pytest.approx(0.0, abs=1e-15)
    assert np.isfinite(r["zero_abs"]) and r["zero_abs"] == pytest.approx(1e-17)
    assert r["phi_round"] == pytest.approx(1.0 - (1.0 - 4e-15), rel=1e-12)
    with pytest.raises(ValueError):                                 # NaN closed form only for α∥
        numbers.ideal_errors(ide.assign(A_cf=[np.nan, 0.0, 0.0, 2.0, 0.0]))


# ----- macros for the step 2–3 fixes -----

def _vals(tmp_path):
    p = tmp_path / "n.tex"
    make_all.write_numbers(p)
    return dict(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}", p.read_text()))


def test_s4c_macros_carry_the_recorded_values(tmp_path):
    v = _vals(tmp_path)
    # Q-a: unchanged values, now over every point; the rounding behind 7.5e-8
    assert v["IdealRetErr"] == r"\ensuremath{7.5\times10^{-8}}" and v["IdealFactorN"] == "36"
    assert v["IdealZeroAbs"] == r"\ensuremath{3.6\times10^{-17}}" and v["IdealZeroN"] == "24"
    assert v["IdealRetErrNonPar"] == r"\ensuremath{1.9\times10^{-15}}"
    assert v["IdealPhiRound"] == r"\ensuremath{5.7\times10^{-15}}"
    # F4 / Q-j: the slack case, λ_min·σ_m²
    assert v["SlackValueBound"] == r"\ensuremath{7.5\times10^{-11}}"
    # F7: the N2(a) default-scaling solves at s_obj = 10⁴ ended OPTIMAL
    assert v["NTwoDefScaledOpt"] == "4" and v["NTwoDefScaledN"] == "4"
    # II jargon: the number of sectors
    assert v["NSectors"] == "11"
    # Q-f: the I2 selection by elasticity
    assert v["NearTieElSector"] == "0.020" and v["NearTieElMom"] == "0.027"
    assert v["NearTieInst"] == "9"
    # IV-C, E3: 31 within a factor 2, 2 below, 3 above (max 4.4)
    assert v["NThreeRatioIn"] == "31" and v["NThreeCollapsed"] == "2"
    assert v["NThreeRatioAbove"] == "3" and v["NThreeRatioMax"] == "4.4"
    # Q-g: N2(b)'s objective scale
    assert v["NTwoConvexScale"] == r"\ensuremath{10^{3}}"
    # IV-B: P1/P2/P3 counts per step; slope agreement over all 48 I1 cases (Q-e)
    assert v["SupBindFive"] == "11" and v["IOneBindTen"] == "23" and v["SupBind"] == "34"
    assert v["SlopeScaleN"] == "48" and v["SlopeScaleWithin"] == "48"
    assert v["SlopeScaleBindN"] == "34" and v["SlopeScaleBindDiff"] == r"\ensuremath{3.2\times10^{-7}}"
    # Q-b: K29c's one failed toy relaxation
    assert v["KTwentyNineCToyFailed"] == "1"


def test_table1_names_the_sector_bound_h():
    text = numbers.table1_mandate().read_text()
    assert "Each sector $h_j$ (net)" in text and "$s_j$" not in text


# ----- retired from the report, still generated -----

@pytest.mark.parametrize("name", ["table3_n2b", "fig1_cost_curves"])
def test_s4c_retired_outputs_are_generated_but_not_in_the_report(name):
    tex = (make_all.ROOT / "report" / "main.tex").read_text()
    tex = re.sub(r"(?<!\\)%[^\n]*", "", tex)
    assert not re.search(rf"{name}(?![A-Za-z0-9_])", tex)
    fns = dict(make_all.FIGURES + make_all.REPORT_FIGURES + make_all.REPORT_TABLES)
    assert name in fns


def test_s4c_text_macros(tmp_path):
    """Macros for numbers the S4c text states (K31: no hand-typed numerals)."""
    v = _vals(tmp_path)
    assert v["MonthsPerYear"] == "12"                                # σ_m = 3%/√12 (src/opt/risk_budget.py)
    assert v["VerdictTol"] == r"\ensuremath{10^{-9}}"                # checker on V's weights (Decision 24)
    assert v["NThreeBandHi"] == "2"                                  # n3.yaml E3_band
    assert v["SObjProxyMin"] == "9.1" and v["SObjProxyMax"] == "21"  # pilot P1 s_obj rule
    assert v["IOneNCons"] == "4"
    g = v["CTwoGrids"]
    assert g.startswith("dollar 0.1, 0.05, 0.02, 0.01, 0;") and "each style and all styles 0.4, 0.2, 0.1, 0.05, 0.02, 0;" in g
    assert g.endswith(r"$\theta$ 0.1, 0.05, 0.025")


def test_experiment_table_i1_says_also_five_percent():
    """Cold read (S4c): "(5% at 2017-12)" read as instead of; I1 runs both steps at 2017-12."""
    i1 = next(r for r in numbers.experiment_rows() if r["exp"] == "I1")
    assert "(also 5\\% at 2017-12)" in i1["what"]
