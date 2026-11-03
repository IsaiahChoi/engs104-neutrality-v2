"""Pre-FINAL session 2 (Isaiah's request of 2026-11-03; Decision 68). (1) The Makefile's page
gate follows Decision 63: `make report` checks RP-4 itself, through tools/spec_check.py's own
measurement (`--only RP-4`), not a second count of the total pages. (2) In Fig. 2, α⊥'s hollow
(base mandate) squares at φ = 0 get the same opaque white face as α∥'s hollow triangles, so the
x = 0 gridline and stacked neighbours don't show through. Tests first."""
from __future__ import annotations

import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgba

from src.figures import fig_c, style
from tests.test_prefinal import DPI, TOL, _pixel, _render, _rgb
from tests.test_s5p2 import _report
from tools import spec_check as sc

ROOT = Path(__file__).resolve().parents[1]


# ----- (1) the page gate (Decision 68) -----


def _recipe(target: str) -> list[str]:
    lines = (ROOT / "Makefile").read_text().splitlines()
    i = next(k for k, ln in enumerate(lines) if re.match(re.escape(target) + r":", ln))
    out = []
    for ln in lines[i + 1:]:
        if not ln.startswith("\t"):
            break
        out.append(ln.strip())
    return out


def test_report_page_gate_is_rp4_through_spec_check():
    recipe = _recipe("report")
    assert recipe[0] == "cd report && tectonic main.tex"
    assert recipe[1] == "$(PY) tools/spec_check.py --target report --only RP-4 --build"
    assert recipe[2].startswith("$(PY) tools/spec_check.py --target report --mode $(MODE)")
    assert len(recipe) == 3
    assert not any("page_count.py" in ln for ln in recipe)


def test_proposal_page_check_is_unchanged():
    assert "$(PY) tools/page_count.py proposal/proposal.pdf --min 1 --max 2" in _recipe("proposal")


def _main(monkeypatch, root, argv):
    monkeypatch.setattr(sc, "ROOT", root)
    return sc.main(argv)


def test_only_rp4_passes_nine_pages_with_references_alone_after_page_8(tmp_path, monkeypatch,
                                                                       capsys):
    _report(tmp_path, 9, 8, "x\n")
    full = {r[0]: r[2] for r in sc.run("report", "draft", root=tmp_path)}
    assert "FAIL" in full.values()               # the fixture fails other checks (e.g. RP-3) ...
    code = _main(monkeypatch, tmp_path, ["--target", "report", "--only", "RP-4"])
    out = capsys.readouterr().out
    assert code == 0                             # ... which --only RP-4 does not count
    rows = [ln for ln in out.splitlines() if re.match(r"(RP|PR)-\d", ln)]
    assert len(rows) == 1 and rows[0].startswith("RP-4") and "PASS" in rows[0]
    assert "9 pages in total; refs:start on page 8" in rows[0]


def test_only_rp4_fails_when_text_runs_past_page_8(tmp_path, monkeypatch, capsys):
    _report(tmp_path, 9, 9, "x\n")              # blank page 9: no references heading at its top
    assert _main(monkeypatch, tmp_path, ["--target", "report", "--only", "RP-4"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_only_rp4_is_the_full_runs_rp4_row(tmp_path, monkeypatch, capsys):
    """The same measurement: the row --only prints is the full run's RP-4 row."""
    _report(tmp_path, 9, 8, "x\n")
    full = next(r for r in sc.run("report", "draft", root=tmp_path) if r[0] == "RP-4")
    _main(monkeypatch, tmp_path, ["--target", "report", "--only", "RP-4"])
    out = capsys.readouterr().out
    assert any(ln.split()[:3] == ["RP-4", full[1], full[2]] and ln.rstrip().endswith(full[3])
               for ln in out.splitlines())


def test_only_rejects_an_unknown_check(tmp_path, monkeypatch):
    _report(tmp_path, 8, 7, "x\n")
    try:
        _main(monkeypatch, tmp_path, ["--target", "report", "--only", "RP-99"])
    except SystemExit as e:
        assert e.code != 0
    else:
        raise AssertionError("--only RP-99 should be rejected")


# ----- (2) Fig. 2: α⊥'s hollow squares at φ = 0 -----


def _perp_lines(ax):
    i = [k for k, *_ in fig_c.ALPHAS].index("perp")
    lines = ax.get_lines()
    return lines[1 + 2 * i], lines[2 + 2 * i], style.SERIES[i]


def test_fig2_perp_hollow_markers_are_opaque_background():
    fig, ax, _ = _render()
    try:
        filled, hollow, color = _perp_lines(ax)
        assert np.allclose(to_rgba(filled.get_markerfacecolor()), to_rgba(color))
        face = to_rgba(hollow.get_markerfacecolor())
        assert face[3] == 1.0                                        # opaque: stacks occlude
        assert np.allclose(face, to_rgba(ax.get_facecolor()))        # reads as hollow
        assert np.allclose(to_rgba(hollow.get_markeredgecolor()), to_rgba(color))
    finally:
        plt.close(fig)


def test_fig2_perp_hollow_centres_show_background_not_grid():
    """No α⊥ hollow square is isolated (12 within 22 pt, each 4 pt wide), so check every one whose
    centre no later-drawn square covers: on top of its stack, its centre must be background."""
    fig, ax, img = _render()
    try:
        _, hollow, _ = _perp_lines(ax)
        x, y = np.asarray(hollow.get_xdata(), float), np.asarray(hollow.get_ydata(), float)
        assert np.allclose(x, 0.0, rtol=0, atol=1e-12)                # φ = 0 up to rounding
        disp = ax.transData.transform(np.column_stack([x, y])) * 72.0 / DPI       # points
        reach = hollow.get_markersize() / 2 + hollow.get_markeredgewidth()        # half-side + edge
        uncovered = [j for j in range(len(y))
                     if all(np.abs(disp[j] - disp[k]).max() >= reach for k in range(j + 1, len(y)))]
        assert len(uncovered) >= 2                                   # guard against a vacuous pass
        bg = _rgb(ax.get_facecolor())
        for j in uncovered:
            assert np.all(np.abs(_pixel(ax, img, x[j], y[j]) - bg) <= TOL), (j, y[j])
    finally:
        plt.close(fig)
