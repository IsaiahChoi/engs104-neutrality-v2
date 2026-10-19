"""tools/spec_check.py (DESIGN §11.7): each check on synthetic inputs (pass and fail), the
allow-list against DESIGN §13, and the static checks on the real S1 scaffolds."""
from __future__ import annotations

import re

import pytest
from pypdf import PdfWriter

from src.utils import ROOT
from tools import spec_check as sc


def _pdf(path, pages):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=612, height=792)
    with open(path, "wb") as f:
        w.write(f)
    return path


def test_allow_list_matches_design_section_13():
    """Every allow-list entry's first-author surname and year appear on one DESIGN §13 line, and
    every DESIGN §13 bullet (except the optional one) has an allow-list entry."""
    design = (ROOT / "docs" / "DESIGN.md").read_text()
    sec = design.split("## 13. References (allow-list)")[1]
    bullets = [l for l in sec.splitlines() if l.startswith("- ") and not l.startswith("- Optional")
               and not l.startswith("Every entry")]
    text = " ".join(bullets)
    for key, (surname, year) in sc.ALLOWED.items():
        if year is None:
            assert surname in text, key
        else:
            assert any(surname in b and year in b for b in bullets), key
    assert len(sc.ALLOWED) == 19
    assert "jegadeesh1993returns" not in sc.ALLOWED           # optional: only if Isaiah adds it


def test_markers_and_cites():
    tex = "% SPEC-ELEMENT 1\n% SPEC-ELEMENT 2\n\\cite{a,b} \\cite{b}\n% \\cite{c}\n"
    assert sc.missing_markers(tex) == [3, 4, 5, 6]
    assert sc.cite_keys(tex) == {"a", "b"}                      # commented cites ignored


def test_bib_parsing_and_subset():
    bib = "% verified: no\n@article{lee2008risk,\n author={Lee, J.-H.},\n year={2008}\n}\n" \
          "% verified: yes (2026-11-01)\n@misc{madeup2020,\n title={X},\n year={2020}\n}\n"
    entries = sc.bib_entries(bib)
    assert set(entries) == {"lee2008risk", "madeup2020"}
    assert entries["lee2008risk"]["verified"] is False and entries["madeup2020"]["verified"] is True
    assert sc.not_allowed(entries) == ["madeup2020"]


def test_forbidden_layout():
    ok = "\\begin{table}\\small x\\end{table}\nText \\vspace{2pt}.\n% \\linespread{2}\n"
    assert sc.forbidden_layout(ok) == []
    bad = "\\usepackage{geometry}\n\\linespread{0.9}\nBody \\small text\n\\vspace{-3pt}\n\\enlargethispage{1cm}"
    found = sc.forbidden_layout(bad)
    assert {"geometry", "\\linespread", "\\small", "negative \\vspace", "\\enlargethispage"} <= set(found)


def test_section_mapping_and_ai_use():
    tex = ("\\begin{abstract}x\\end{abstract}\\section{Introduction}\\section{Problem Setting}"
           "\\section{Solution Approach and Analysis}\\section{Results}\\section{Discussion}"
           "\\section{Conclusions}\\section*{Disclosures and AI-Use Acknowledgment}")
    assert sc.missing_sections(tex) == []
    assert sc.missing_sections(tex.replace("\\section{Discussion}", "")) == ["Discussion"]
    assert sc.has_ai_use(tex) and not sc.has_ai_use("\\section{Acknowledgment}")


def test_final_mode_markers():
    assert sc.draft_markers("\\todo{x}\n\\textcolor{red}{y}\n% drafted-by-agent\nTODO(Isaiah): z") == \
        ["TODO", "\\textcolor{red}", "% drafted-by-agent", "TODO(Isaiah)"]
    assert sc.draft_markers("clean text") == []


def test_aux_label_page_and_pdf_pages(tmp_path):
    aux = "\\newlabel{sec:intro}{{I}{1}{}{}{}}\n\\newlabel{refs:start}{{}{7}{}{}{}}\n"
    assert sc.label_page(aux, "refs:start") == 7 and sc.label_page(aux, "nope") is None
    assert sc.pdf_pages(_pdf(tmp_path / "a.pdf", 3)) == 3


def test_unreferenced_floats_and_log():
    tex = "\\begin{figure}\\label{fig:a}\\end{figure}\\begin{table}\\label{tab:b}\\end{table} see \\ref{fig:a}"
    assert sc.unreferenced_floats(tex) == ["tab:b"]
    log = "Overfull \\hbox (6.2pt too wide) in paragraph\nOverfull \\hbox (1.0pt too wide)\n" \
          "LaTeX Warning: Reference `x' on page 2 undefined"
    assert sc.overfull_boxes(log, 5.0) == [6.2]
    assert sc.undefined_refs(log) == ["Reference `x' on page 2 undefined"]


def test_scaffolds_pass_static_checks():
    """S1 scaffolds: the static checks that need no PDF pass in draft mode."""
    prop = (ROOT / "proposal" / "proposal.tex").read_text()
    rep = (ROOT / "report" / "main.tex").read_text()
    entries = sc.bib_entries((ROOT / "report" / "refs.bib").read_text())
    assert sc.missing_markers(prop) == []
    assert re.search(r"\\documentclass\[[^\]]*conference[^\]]*\]\{IEEEtran\}", rep)
    assert sc.missing_sections(rep) == [] and sc.has_ai_use(rep)
    assert sc.forbidden_layout(rep) == []
    assert sc.not_allowed(entries) == [] and set(entries) == set(sc.ALLOWED)
    assert not any(e["verified"] for e in entries.values())
    assert "\\label{refs:start}" in rep.split("\\bibliography{refs}")[0]


def test_run_checks_table_and_exit_code(tmp_path, capsys):
    """run() on a synthetic proposal: a missing marker and one citation fail; exit code 1."""
    d = tmp_path / "proposal"
    d.mkdir()
    (d / "proposal.tex").write_text("% SPEC-ELEMENT 1\n\\cite{lee2008risk}\n")
    _pdf(d / "proposal.pdf", 1)
    (tmp_path / "report").mkdir()
    (tmp_path / "report" / "refs.bib").write_text("% verified: no\n@article{lee2008risk,\n year={2008}\n}\n")
    rows = sc.run("proposal", "draft", root=tmp_path, build=False)
    status = {r[0]: r[2] for r in rows}
    assert status["PR-2"] == "PASS" and status["PR-3"] == "FAIL" and status["PR-4"] == "FAIL"
    assert sc.exit_code(rows) == 1
