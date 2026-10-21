"""src/figures/numbers.py and src/analysis/cont.py (S4): the report's result macros, Table I, and
the K17 shape statistics, tests first. Every macro names its source file and that file's sha256
(CHECKS K32); formatting never rounds silently or prints exponent notation outside \\ensuremath."""
from __future__ import annotations

import hashlib
import re

import numpy as np
import pandas as pd
import pytest

from src.analysis import cont as C
from src.figures import make_all, numbers as NB
from src.utils import ROOT


def test_sig_and_sci_formats():
    assert NB.sig(0.07286, 2) == "0.073" and NB.sig(30.548, 3) == "30.5"
    assert NB.sig(3.67e-4, 2) == r"\ensuremath{3.7\times10^{-4}}"
    assert NB.sig(9.96e-5, 2) == r"\ensuremath{1.0\times10^{-4}}"
    assert NB.sig(2537.6, 3) == "2538" and NB.sig(0.0, 2) == "0"
    assert NB.sig(4.21, 2) == "4.2" and NB.sig(1.0, 2) == "1.0"
    assert NB.pow10(1e-9) == r"\ensuremath{10^{-9}}"
    with pytest.raises(ValueError):
        NB.sig(float("nan"), 2)


def test_k17_monotone_and_concave_sweeps():
    rows = []
    for fam, vals, A in (("f", [0.0, 0.1, 0.2, None], [1.0, 2.0, 2.5, 2.6]),
                         ("g", [0.0, 0.1, 0.2, None], [1.0, 1.5, 2.5, 2.6])):     # g: convex kink
        for v, a in zip(vals, A):
            rows.append({"date": "d", "alpha": "mom", "family": fam, "value": np.nan if v is None else v,
                         "off": v is None, "A": a})
    out = C.k17(pd.DataFrame(rows))
    assert out["n_sweeps"] == 2 and out["n_pairs"] == 6 and out["n_triples"] == 2
    assert out["monotone_failures"] == 0 and out["concavity_failures"] == 1


def test_k17_flags_a_decrease():
    df = pd.DataFrame({"date": "d", "alpha": "mom", "family": "f", "value": [0.0, 0.1, np.nan],
                       "off": [False, False, True], "A": [1.0, 0.9, 1.1]})
    assert C.k17(df)["monotone_failures"] == 1


def test_result_macros_are_sourced_unique_and_balanced(tmp_path):
    p = tmp_path / "n.tex"
    make_all.write_numbers(p)
    lines = p.read_text().splitlines()
    names = []
    for i, ln in enumerate(lines):
        if ln.startswith("\\newcommand"):
            m = re.fullmatch(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}", ln)
            assert m, ln
            names.append(m[1])
            src = re.fullmatch(r"% source: (\S+) sha256=([0-9a-f]{64})", lines[i - 1])
            assert src and hashlib.sha256((ROOT / src[1]).read_bytes()).hexdigest() == src[2], lines[i - 1]
    assert len(names) == len(set(names)) and len(names) > 150
    vals = dict(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}", p.read_text()))
    assert vals["IOneBindTen"] == "23" and vals["SpearmanPersp"] == "0.64" and vals["SpearmanBigM"] == "0.50"
    assert vals["FalseCertGap"] == r"\ensuremath{9.1\times10^{-5}}"
    assert vals["DisclosureMaxZ"] == "5.47" and vals["MultiSessionReturns"] == "1"


def test_table1_is_generated_from_the_configs():
    text = NB.table1_mandate().read_text()
    assert "Do not edit" in text and r"\pm" in text and "ADV" in text
