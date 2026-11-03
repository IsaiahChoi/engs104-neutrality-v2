"""S5 pass 2 (Isaiah's S5 addendum, PROGRESS 2026-11-02; Decisions 63-65): tools/spec_check.py's
RP-4 (the text before the references fits in 8 pages; references do not count) and RP-8 (the
seven paragraph markers, counted only on a comment line that begins with one), and
tools/page_sections.py's outline-only parts (S5 pass 1 issue 23) and the length of the text
before the references. Tests first."""
from __future__ import annotations

import os

import pytest
from pypdf import PdfWriter

from tools import page_sections as P
from tools import spec_check as sc

FAIL8 = ("% drafted-by-agent", "% drafted-by-chat", "% verify-by-hand")
PASS8 = ("% chat-draft revised by Isaiah", "% chat-draft approved by Isaiah",
         "% agent-draft revised by Isaiah", "% agent-draft approved by Isaiah")


# ----- RP-8 (Decisions 64, 65) -----

def test_the_seven_markers_are_named_as_design_says():
    assert sc.RP8_FAIL_MARKERS == FAIL8
    assert sc.RP8_PASS_MARKERS == PASS8


def test_markers_count_only_on_a_comment_line_that_begins_with_one():
    tex = ("% header: paragraphs are marked \"% drafted-by-agent\" until reviewed\n"
           "% drafted-by-agent\n"
           "   % drafted-by-agent (indented)\n"
           "Text % drafted-by-agent after text is not a marker line\n"
           "% chat-draft approved by Isaiah (drafted by Claude, claude.ai chat)\n"
           "% agent-draft revised by Isaiah\n"
           "\\% drafted-by-chat is an escaped percent, not a comment\n")
    counts = sc.marker_counts(tex)
    assert list(counts) == list(FAIL8 + PASS8)
    assert counts["% drafted-by-agent"] == 2
    assert counts["% drafted-by-chat"] == 0
    assert counts["% chat-draft approved by Isaiah"] == 1
    assert counts["% agent-draft revised by Isaiah"] == 1
    assert sum(counts.values()) == 4


def test_rp8_final_fails_on_three_markers_and_never_on_the_four_review_markers():
    for m in FAIL8:
        assert sc.draft_markers(f"x\n{m}\ny", sc.RP8_FINAL) == [m], m
    for m in PASS8:
        assert sc.draft_markers(f"x\n{m}\ny", sc.RP8_FINAL) == [], m
    header = "% each paragraph marked \"% drafted-by-agent\", \"% verify-by-hand\"\nclean"
    assert sc.draft_markers(header, sc.RP8_FINAL) == []
    assert sc.draft_markers("TODO(Isaiah): x\n\\textcolor{red}{y}", sc.RP8_FINAL) == \
        ["TODO(Isaiah)", "red text"]


# ----- RP-4 (Decision 63) -----

def test_labels_after_a_page_ignore_refs_start():
    aux = ("\\newlabel{fig:a}{{1}{3}{}{}{}}\n\\newlabel{refs:start}{{}{9}{}{}{}}\n"
           "\\newlabel{tab:late}{{II}{9}{}{}{}}\n\\newlabel{sec:x}{{V}{8}{}{}{}}\n")
    assert sc.labels_after(aux, 8) == ["tab:late"]
    assert sc.labels_after(aux, 9) == []


def test_heading_at_top():
    assert sc.heading_at_top("REFERENCES\n[1] R. Grinold and R. Kahn")
    assert sc.heading_at_top("\n  R EFERENCES\n[1] x")
    assert not sc.heading_at_top("the end of the discussion.\nREFERENCES\n[1] x")
    assert not sc.heading_at_top("")


@pytest.mark.parametrize("n, refs, text, late, ok", [
    (8, 7, "", [], True),                                      # everything fits
    (9, 8, "", [], True),                                      # only references after page 8
    (10, 8, "", [], True),
    (9, 9, "REFERENCES\n[1] R. Grinold", [], True),            # heading at the top of page 9
    (9, 9, "last line of text.\nREFERENCES\n[1] x", [], False),
    (9, 8, "", ["fig:late"], False),                           # a float after page 8
    (10, 10, "REFERENCES\n[1] x", [], False),
    (9, None, "", [], False),                                  # refs:start unknown
    (None, 8, "", [], False),                                  # no PDF
])
def test_refs_fit(n, refs, text, late, ok):
    got, detail = sc.refs_fit(n, refs, text, late)
    assert got is ok
    assert f"{n} pages" in detail and f"refs:start on page {refs}" in detail


def _pdf(path, pages):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=612, height=792)
    with open(path, "wb") as f:
        w.write(f)


def _report(root, pages, refs_page, body):
    d = root / "report"
    d.mkdir()
    (d / "refs.bib").write_text("% verified: no\n@article{lee2008risk,\n year={2008}\n}\n")
    (d / "main.tex").write_text(
        "\\documentclass[conference]{IEEEtran}\n\\begin{document}\n" + body
        + "\\label{refs:start}\n\\end{document}\n")
    (d / "main.aux").write_text(f"\\newlabel{{refs:start}}{{{{}}{{{refs_page}}}{{}}{{}}{{}}}}\n")
    _pdf(d / "main.pdf", pages)
    later = os.stat(d / "main.tex").st_mtime + 1
    os.utime(d / "main.aux", (later, later))
    os.utime(d / "main.pdf", (later, later))
    return d


def test_run_rp4_counts_only_the_text_before_the_references(tmp_path):
    _report(tmp_path, 9, 8, "x\n")
    status = {r[0]: (r[2], r[3]) for r in sc.run("report", "draft", root=tmp_path)}
    assert status["RP-4"][0] == "PASS" and "9 pages" in status["RP-4"][1]


def test_run_rp4_ignores_a_stale_aux(tmp_path):
    d = _report(tmp_path, 9, 8, "x\n")
    old = os.stat(d / "main.tex").st_mtime - 10
    os.utime(d / "main.aux", (old, old))
    status = {r[0]: (r[2], r[3]) for r in sc.run("report", "draft", root=tmp_path)}
    assert status["RP-4"][0] == "FAIL" and "refs:start on page None" in status["RP-4"][1]


def test_run_rp8_draft_reports_the_seven_counts_and_final_fails(tmp_path, monkeypatch):
    _report(tmp_path, 8, 7, "% drafted-by-agent\npara\n% chat-draft approved by Isaiah\npara\n")
    rows = {r[0]: (r[2], r[3]) for r in sc.run("report", "draft", root=tmp_path)}
    assert rows["RP-8"][0] == "N/A"
    for m in FAIL8 + PASS8:
        assert m.lstrip("% ") in rows["RP-8"][1], m
    assert "drafted-by-agent 1" in rows["RP-8"][1]
    assert "chat-draft approved by Isaiah 1" in rows["RP-8"][1]
    monkeypatch.setattr(sc, "_build", lambda d, tex: (True, "stub build"))
    rows = {r[0]: (r[2], r[3]) for r in sc.run("report", "final", root=tmp_path)}
    assert rows["RP-8"][0] == "FAIL" and "% drafted-by-agent" in rows["RP-8"][1]


# ----- tools/page_sections.py -----

SRC = r"""\documentclass[conference]{IEEEtran}
\begin{document}
\begin{abstract}
\begin{outline}{Abstract}
\item claim $\rightarrow$ Fig.~\ref{fig:a}
\end{outline}
\end{abstract}
\section{Introduction}
\label{sec:intro}
% chat-draft approved by Isaiah
Prose that cites Fig.~\ref{fig:a}.
\section{Setting}
\begin{figure}[!t]
\label{fig:a}
\end{figure}
see Fig.~\ref{fig:a} and Table~\ref{tab:b}
\subsection{Sub}
\begin{table}[!t]
\label{tab:b}
\end{table}
\section{Discussion}
\label{sec:discussion}
\begin{outline}{V}
\item claim $\rightarrow$ Table~\ref{tab:b}
\end{outline}
\label{refs:start}
\end{document}
"""


def test_outline_only_parts_are_detected_from_the_source():
    parts = P.parts(SRC)
    assert [p["title"] for p in parts] == ["Abstract", "Introduction", "Setting", "Sub",
                                           "Discussion", "References"]
    skip = P.outline_only(SRC, parts)
    assert skip == ("abs", "sec4")                          # Abstract and Discussion, not I
    first = P.first_refs(SRC, parts, skip=skip)
    assert first == {"fig:a": "sec1", "tab:b": "sec2"}      # Section I's prose now counts


def test_text_before_the_references_in_pages():
    g = P.Geometry(paperheight=100.0, textheight=80.0, texttop=90.0, colsplit=50.0)
    pos = {"refs": (8, 60.0, 50.0)}                         # page 8, right column, halfway
    assert P.before_refs(g, pos) == pytest.approx(7.75)
