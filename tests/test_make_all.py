"""src/figures/make_all.py: report/numbers.tex is generated, deterministic, and every macro names
its source file with a sha256 that matches (CLAUDE.md rule 8; CHECKS K32, K33)."""
from __future__ import annotations

import hashlib
import re

from src.figures import make_all
from src.utils import ROOT


def test_numbers_tex_is_deterministic_and_sourced(tmp_path):
    a, b = tmp_path / "a.tex", tmp_path / "b.tex"
    make_all.write_numbers(a)
    make_all.write_numbers(b)
    assert a.read_bytes() == b.read_bytes()
    lines = a.read_text().splitlines()
    macros = [i for i, l in enumerate(lines) if l.startswith("\\newcommand")]
    assert len(macros) >= 10
    names = []
    for i in macros:
        m = re.fullmatch(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}", lines[i])
        assert m, lines[i]
        names.append(m.group(1))
        src = re.fullmatch(r"% source: (\S+) sha256=([0-9a-f]{64})", lines[i - 1])
        assert src, lines[i - 1]
        assert hashlib.sha256((ROOT / src.group(1)).read_bytes()).hexdigest() == src.group(2)
    assert len(set(names)) == len(names)


def test_design_constants_match_the_configs(tmp_path):
    p = tmp_path / "n.tex"
    make_all.write_numbers(p)
    vals = dict(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}", p.read_text()))
    assert vals["RiskBudgetPct"] == "3" and vals["BaseGross"] == "2"
    assert vals["BaseNetPct"] == "2" and vals["BaseBeta"] == "0.05" and vals["BaseStyle"] == "0.10"
    assert vals["BaseSectorPct"] == "2" and vals["BasePositionPct"] == "3"
    assert vals["MiqpPositionPct"] == "6" and vals["BaseLiquidityPct"] == "5"
    assert vals["BorrowBpYear"] == "30" and vals["TradeCostBp"] == "5"
    assert vals["AUMBillion"] == "1" and vals["LambdaMin"] == "\\ensuremath{10^{-6}}"
    assert vals["RootRtol"] == "\\ensuremath{10^{-10}}"


def test_number_formatting():
    """Review L3: no float noise, no exponent notation, no silent rounding."""
    import pytest
    assert make_all._num(100 * 0.07) == "7" and make_all._num(1e4 * 0.0005) == "5"
    assert make_all._num(0.00001) == "0.00001" and make_all._num(2.5) == "2.5"
    assert make_all._fixed(0.10, 2) == "0.10"
    with pytest.raises(ValueError):
        make_all._fixed(0.025, 2)
