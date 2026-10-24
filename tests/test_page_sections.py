"""tools/page_sections.py (S4b step 4; DESIGN §11.1): per-section page measurement from zref
positions in a scratch copy, floats counted where they land (A) or in the section that first
references them (B). Tests first, on constructed sources and positions."""
from __future__ import annotations

import pytest

from tools import page_sections as P

SRC = r"""\documentclass[conference]{IEEEtran}
\begin{document}
\begin{abstract}
x \ref{fig:a}
\end{abstract}
\section{Intro}
% \ref{tab:b} in a comment is not a reference
\section{Setting}
\begin{figure}[!t]
\label{fig:a}
\end{figure}
see Fig.~\ref{fig:a} and Table~\ref{tab:b}
\begin{table*}[!t]
\label{tab:b}
\end{table*}
\subsection{Sub}
\label{refs:start}
\end{document}
"""


def test_inject_places_markers_at_sections_floats_and_the_end():
    out = P.inject(SRC)
    assert "zref-savepos" in out and "zref-abspage" in out
    for m in ("mk{abs}", "mk{sec1}", "mk{sec2}", "mk{sub3}", "mk{refs}", "mk{end}",
              "mk{flt:fig:a:top}", "mk{flt:fig:a:bot}", "mk{flt:tab:b:top}", "mk{flt:tab:b:bot}"):
        assert m in out, m
    assert out.index("mk{sec2}") < out.index(r"\section{Setting}")
    assert out.index("mk{refs}") < out.index(r"\label{refs:start}")


def test_parts_and_first_references_skip_comments_and_outlines():
    parts = P.parts(SRC)
    assert [p["key"] for p in parts] == ["abs", "sec1", "sec2", "sub3", "refs"]
    assert [p["title"] for p in parts][:3] == ["Abstract", "Intro", "Setting"]
    first = P.first_refs(SRC, parts, skip=("abs",))
    assert first == {"fig:a": "sec2", "tab:b": "sec2"}
    assert P.first_refs(SRC, parts)["fig:a"] == "abs"


def test_column_units_and_spans():
    g = P.Geometry(paperheight=100.0, textheight=80.0, texttop=90.0, colsplit=50.0)
    assert P.units(g, page=1, x=10.0, y=90.0) == pytest.approx(0.0)
    assert P.units(g, page=1, x=60.0, y=50.0) == pytest.approx(1.5)
    assert P.units(g, page=2, x=10.0, y=10.0) == pytest.approx(3.0)
    pos = {"a": (1, 10.0, 90.0), "b": (1, 60.0, 50.0), "end": (2, 10.0, 10.0)}
    spans = P.spans(g, pos, ["a", "b"], end="end")
    assert spans == {"a": pytest.approx(0.75), "b": pytest.approx(0.75)}   # pages = units / 2


def test_float_accounting_moves_area_to_the_first_referencing_section():
    g = P.Geometry(paperheight=100.0, textheight=80.0, texttop=90.0, colsplit=50.0)
    # a column float of 0.25 column height landing in section b's span, first referenced in a
    pos = {"a": (1, 10.0, 90.0), "b": (1, 60.0, 90.0), "end": (2, 10.0, 90.0),
           "flt:f:top": (1, 60.0, 70.0), "flt:f:bot": (1, 60.0, 50.0)}
    floats = P.float_areas(g, pos, wide={"f": False}, sep=0.0)
    assert floats["f"]["pages"] == pytest.approx(0.125)
    landed = P.landing(g, pos, floats, ["a", "b"], end="end")
    assert landed == {"f": "b"}
    A = P.spans(g, pos, ["a", "b"], end="end")
    B = P.by_first_reference(A, floats, landed, {"f": "a"})
    assert B["a"] == pytest.approx(A["a"] + 0.125) and B["b"] == pytest.approx(A["b"] - 0.125)
    assert sum(B.values()) == pytest.approx(sum(A.values()))
    wide = P.float_areas(g, pos, wide={"f": True}, sep=0.0)
    assert wide["f"]["pages"] == pytest.approx(0.25)                      # both columns
