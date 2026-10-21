"""tools/make_facts.py, S3 and S3b facts (S3b item 9; Isaiah's GATE I note), tests first.

The facts are read from results/s3_analysis/ (s3_analysis.json and its CSVs) and
results/s3b_analysis/s3b_analysis.json, each line citing its file and sha256 (CLAUDE.md rule 8:
no hand-typed numbers). The tests read those committed files and check that the numbers in the
generated lines are theirs; a prediction's verdict word is computed from the stored value and the
note's tolerance."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from src.utils import ROOT
from tools import make_facts as mf

S3 = ROOT / "results" / "s3_analysis"
S3B = ROOT / "results" / "s3b_analysis"


@pytest.fixture(scope="module")
def s3():
    if not (S3 / "s3_analysis.json").exists():
        pytest.skip("results/s3_analysis not available")
    return mf.load_s3(S3)


@pytest.fixture(scope="module")
def s3b():
    if not (S3B / "s3b_analysis.json").exists():
        pytest.skip("results/s3b_analysis not available")
    return json.loads((S3B / "s3b_analysis.json").read_text())


def test_verdict_word():
    assert mf.verdict_word(5e-7, 1e-6) == "holds" and mf.verdict_word(2e-6, 1e-6) == "fails"
    assert mf.verdict_word(1e-6, 1e-6) == "holds"


def test_s3_texts_carry_the_json_numbers(s3):
    texts = mf.s3_texts(s3)
    assert all(src in mf.S3_SOURCES for _, src in texts)
    js = s3["json"]
    rows = {r["estimator"]: r for r in js["i1"]["errors_all_f_main_delta"]}
    p = [t for t, _ in texts if t.startswith("I1 relative error") and "perspective relaxation slope" in t]
    assert len(p) == 1 and mf.g(rows["perspective"]["median_rel_err"]) in p[0]
    assert f"n = {rows['perspective']['n_binding']}" in p[0]
    assert any(t.startswith("I1 interval width") for t, _ in texts)
    sec = js["i1"]["k27_baseline_by_delta"]["0.1"]
    k27 = [t for t, _ in texts if "convex baseline" in t and "secant" in t]
    assert k27 and mf.g(sec["secant_rel_err_median"]) in k27[0] and f"n = {sec['n_secant']}" in k27[0]
    for pre in ("I1 certification", "I2", "N1 root gap", "N1 plain relaxations", "N1 K22", "N2(a)", "N2(b)"):
        assert any(x.startswith(pre) for x, _ in texts), pre


def test_s3b_texts_predictions_and_items(s3b):
    texts = mf.s3b_texts(s3b)
    t = dict((x.split(":")[0], x) for x, _ in texts)
    pr = s3b["item3_support"]["predictions"]
    assert mf.g(pr["P1"]["max_err"]) in t["Item 3, prediction P1"]
    assert mf.verdict_word(pr["P1"]["max_err"], pr["P1"]["tol"]) in t["Item 3, prediction P1"]
    assert mf.verdict_word(pr["P2"]["max_err"], pr["P2"]["tol"]) in t["Item 3, prediction P2"]
    x2 = s3b["item2_k29b_ext"]
    assert f"{x2['all']['n'] - x2['all']['misses']} of {x2['all']['n']}" in t["Item 2, K29b extended"]
    h = s3b["item5_hedged_legs"]
    assert f"{h['prediction_holds']} of {h['hedged_names']}" in t["Item 5, hedged legs"]
    for k in ("Item 4, I2 grid", "Item 6, V ties", "Item 7, N1 presolve at N = 250"):
        assert any(key.startswith(k) for key in t), k


def test_build_cites_s3_and_s3b_files(tmp_path):
    try:
        lines = mf.build(tmp_path / "FACTS.md")
    except SystemExit as e:
        pytest.skip(f"stored runs not available: {e}")
    text = "\n".join(lines)
    assert "## S3: I1, I2, N1, N2" in text and "## S3b (GATE I scope)" in text
    s3_lines = [ln for ln in lines if ln.startswith("- ") and ln[2:].startswith(("I1", "I2", "N1", "N2", "Item"))]
    assert s3_lines and all("results/s3_analysis/" in ln or "results/s3b_analysis/" in ln for ln in s3_lines)
    assert all(" sha256 `" in ln for ln in s3_lines)
