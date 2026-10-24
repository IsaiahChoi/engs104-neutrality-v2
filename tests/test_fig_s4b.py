"""S4b step 2 (DESIGN §10 and §11.1 as edited at the S4 read, Decision 50): Fig. 1 in four panels,
Fig. 4 as a slope row only (about half the S4 height, within the text width so 8-pt text stays
8 pt), Fig. 5 as one panel, the experiment table, Table III as a single-column N2(b) table, and
Table II in one column. Tests first. Fig. 3 and the S4 two-block Table III stay generated (their
S3/S4 tests pin them) but leave the report."""
from __future__ import annotations

import re

import pandas as pd
import pytest
from pypdf import PdfReader

from experiments.common import latest_done
from src.figures import fig_c, fig_s3, make_all, numbers

IN = 72.0


def _size(path) -> tuple[float, float]:
    b = PdfReader(path).pages[0].mediabox
    return float(b.width) / IN, float(b.height) / IN


def test_fig1_has_the_four_design_panels_and_fits_a_column():
    assert [k for k, _ in fig_c.FIG1_PANELS] == ["liquidity", "sector", "style_all", "style:Mom"]
    assert {k for k, _ in fig_c.FIG1_PANELS} & fig_c.FACTOR_FAMILIES == {"style_all", "style:Mom"}
    w, h = _size(fig_c.fig1_cost_curves())
    assert w <= 3.5 + 1e-6 and h <= 3.6


def test_fig4_is_one_slope_row_within_the_text_width():
    w, h = _size(fig_s3.fig4_value_functions())
    assert w <= 7.16 and h <= 0.6 * 4.17                      # S4 version: 4.17 in tall


def test_fig5_is_one_panel():
    w, h = _size(fig_s3.fig5_formulations())
    assert w <= 3.5 + 1e-6 and h <= 3.0                        # S4 version: 4.45 in, two panels


def _rows(text: str) -> list[str]:
    return [r for r in text.splitlines() if r.rstrip().endswith(r"\\") and "&" in r]


def test_table3_n2b_is_single_column_with_n_per_row():
    text = numbers.table3_n2b().read_text()
    head = re.search(r"\\begin\{tabular\}\{([^}]*)\}", text).group(1)
    assert len(re.findall(r"[lrc]", head)) <= 6
    rows = _rows(text)[1:]
    labels = [r.split("&")[0].strip() for r in rows]
    assert len(rows) == 6 and {lab.split()[0] for lab in labels} == {"Gurobi", "Clarabel", "SCS"}
    cv = pd.read_parquet(latest_done("n2") / "n2_convex.parquet")
    n = cv[cv["solver"] == "CLARABEL"].groupby("scaled").size()
    assert all(f"& {int(n.iloc[0])} &" in r for r in rows)


def test_table2_fits_one_column_and_keeps_its_rows():
    rows = fig_s3.table2_lines()
    body = [r for r in rows if r.endswith(r"\\") and not r.startswith("estimator")]
    assert all(len(r.split("&")[0].strip()) <= 16 for r in body)
    assert any(r.startswith("convex baseline") and "& 24 &" in r for r in rows)


def test_experiment_table_lists_every_experiment_with_its_solve_count():
    rows = numbers.experiment_rows()
    assert [r["exp"] for r in rows] == ["C1", "C2", "I1", "I2", "N1", "N2(a)", "N2(b)", "N3"]
    n = {r["exp"]: r["solves"] for r in rows}
    rd = lambda name, t: pd.read_parquet(latest_done(name) / f"{t}.parquet")
    assert n["C1"] == len(rd("c1", "c1_points")) + len(rd("c1", "c1_idealized"))
    assert n["C2"] == len(rd("c2", "c2_points"))
    assert n["I1"] == len(rd("i1", "i1_solves")) and n["I2"] == len(rd("i2", "i2_solves"))
    assert n["N1"] == len(rd("n1", "n1_solves")) and n["N2(a)"] == len(rd("n2", "n2_miqp"))
    assert n["N2(b)"] == len(rd("n2", "n2_convex")) and n["N3"] == len(rd("n3", "n3_probes"))
    text = numbers.table_experiments().read_text()
    assert "Do not edit" in text and all(e in text for e in n)
    assert ("table_experiments", numbers.table_experiments) in make_all.REPORT_TABLES
    assert ("table3_n2b", numbers.table3_n2b) in make_all.REPORT_TABLES


@pytest.mark.parametrize("name", ["fig3_attribution", "table3_n2"])
def test_retired_outputs_are_still_generated_but_not_in_the_report(name):
    tex = (make_all.ROOT / "report" / "main.tex").read_text()
    tex = re.sub(r"(?<!\\)%[^\n]*", "", tex)
    assert not re.search(rf"{name}(?![A-Za-z0-9_])", tex)                # table3_n2b is the new one


# ----- S4b step 3: macros for the new content (tests first) -----

def _vals(tmp_path):
    p = tmp_path / "n.tex"
    make_all.write_numbers(p)
    return dict(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}", p.read_text()))


def test_s4b_macros_carry_the_recorded_values(tmp_path):
    v = _vals(tmp_path)
    # direct cost split of α'w* (C1 weights; no solves)
    assert v["SplitAMed"] == "0.80" and v["SplitTradeMed"] == "0.16" and v["SplitBorrowMed"] == "0.039"
    # N3 (results/n3/run_20261024T092033Z)
    assert v["NThreeN"] == "36" and v["NThreeEOneDef"] == "29" and v["NThreeEOneResc"] == "30"
    assert v["NThreeReproDef"] == "36" and v["NThreeRatioMed"] == "0.98" and v["NThreeCollapsed"] == "2"
    assert v["VolIOneMed"] == "2.87" and v["VolNOneMax"] == "3.31" and v["VolNOneAbove"] == "4"
    # censored effort: k of n stopped, and the range of the rest
    assert v["PreBigMCensOff"] == "6" and v["PreBigMWorkOffOkMax"] == "171"
    assert v["NTwoBigMWLOne"] == "2" and v["NTwoBigMWorkOneOkMin"] == "2.9"
    assert v["HedgedDistinct"] == "4" and v["BaseOnlyBind"] == "1" and v["KFifteenKeys"] == "18"
    assert v["ConeTolUnscaled"] == "0.16" and v["ConeTolRescaled"] == r"\ensuremath{5.8\times10^{-4}}"
    assert v["ClassPerspPOneFiveMax"] == "3.6" and v["ClassBigMPOneFiveMax"] == "5.4"
