#!/usr/bin/env python3
"""Specification checks for the proposal and the report (DESIGN §11.7; RUNBOOK §8).

    uv run python tools/spec_check.py --target {proposal,report} --mode {draft,final} [--build]

Prints a table (check ID, requirement ID from RUNBOOK §8, PASS/FAIL/WARN/N/A, detail) and exits
1 on any FAIL. Without --build, PR-1/RP-1 check that the PDF exists and is at least as new as
its sources (the Makefile builds first). With --build, and always in final mode, the document
is built here with `tectonic --keep-logs --keep-intermediates` so the .log (RP-10, RP-11) and
the .aux (RP-5: the page of \\label{refs:start}) exist.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# DESIGN §13 allow-list: key -> (first author or name as DESIGN writes it, year). The optional
# Jegadeesh–Titman entry is not here; it is allowed only if Isaiah adds it (DESIGN §13).
ALLOWED: dict[str, tuple[str, str | None]] = {
    "grinold2000active": ("Grinold", "2000"),
    "clarke2002portfolio": ("Clarke", "2002"),
    "stubbs2010constraint": ("Stubbs", "2010"),
    "lee2008risk": ("Lee", "2008"),
    "ceria2012factor": ("Ceria", "2012"),
    "jacobs2005portfolio": ("Jacobs", "2005"),
    "frangioni2006perspective": ("Frangioni", "2006"),
    "gunluk2010perspective": ("Günlük", "2010"),
    "geoffrion1977parametric": ("Geoffrion", "1977"),
    "wolsey1981integer": ("Wolsey", "1981"),
    "bertsimas2022scalable": ("Bertsimas", "2022"),
    "fama2015five": ("Fama", "2015"),
    "boyd2004convex": ("Boyd", "2004"),
    "wolsey2020integer": ("Wolsey", "2020"),
    "diamond2016cvxpy": ("Diamond", "2016"),
    "gurobi2026manual": ("Gurobi", "2026"),
    "goulart2024clarabel": ("Goulart", "2024"),
    "french_data_library": ("French Data Library", None),
    "yfinance": ("yfinance", None),
}

REQ = {"PR-1": "P0", "PR-2": "P0", "PR-3": "P1-P6", "PR-4": "P5", "PR-5": "P0",
       "RP-1": "R0", "RP-2": "R0", "RP-3": "R2-R8", "RP-4": "R0", "RP-5": "R0", "RP-6": "R0",
       "RP-7": "C5", "RP-8": "C5", "RP-9": "C5", "RP-10": "R9", "RP-11": "R0"}

SECTIONS = {   # required section -> accepted titles (prefix match, case-insensitive)
    "Introduction": ("Introduction",),
    "Problem Setting": ("Problem Setting", "Problem Formulation"),
    "Solution Approach": ("Solution Approach", "Approach", "Methods"),
    "Results": ("Results", "Computational Results", "Experiments"),
    "Discussion": ("Discussion",),
    "Conclusion": ("Conclusion",),
}
SIZE_SWITCHES = ("tiny", "scriptsize", "footnotesize", "small", "large", "Large", "LARGE",
                 "huge", "Huge")
FINAL_MARKERS = ("TODO", "\\textcolor{red}", "% drafted-by-agent", "TODO(Isaiah)")
# Paragraph markers (DESIGN §11.6-§11.7; Decisions 64, 65). RP-8 fails in final mode on the first
# three and never on the other four; a marker counts only on a comment line that begins with it.
RP8_FAIL_MARKERS = ("% drafted-by-agent", "% drafted-by-chat", "% verify-by-hand")
RP8_PASS_MARKERS = ("% chat-draft revised by Isaiah", "% chat-draft approved by Isaiah",
                    "% agent-draft revised by Isaiah", "% agent-draft approved by Isaiah")
RP8_FINAL = ("TODO(Isaiah)", "red text", *RP8_FAIL_MARKERS)
PAGE_LIMIT = 8                                 # RP-4: the text before the references (Decision 63)


# ----- text helpers -----

def strip_comments(tex: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", tex)


def missing_markers(tex: str) -> list[int]:
    return [n for n in range(1, 7)
            if not re.search(rf"^\s*%\s*SPEC-ELEMENT {n}\b", tex, flags=re.M)]


def cite_keys(tex: str) -> set[str]:
    keys = set()
    for group in re.findall(r"\\cite\w*\*?(?:\[[^\]]*\])*\{([^}]*)\}", strip_comments(tex)):
        keys |= {k.strip() for k in group.split(",") if k.strip()}
    return keys


def bib_entries(bib: str) -> dict[str, dict]:
    """key -> {"type", "year", "verified"}; `verified` from the nearest preceding
    `% verified: no | yes (...)` comment."""
    out = {}
    starts = [m for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", bib)]
    for i, m in enumerate(starts):
        prev_end = starts[i - 1].end() if i else 0
        body = bib[m.end(): starts[i + 1].start() if i + 1 < len(starts) else len(bib)]
        marks = re.findall(r"%\s*verified:\s*(\w+)", bib[prev_end:m.start()])
        year = re.search(r"year\s*=\s*[{\"]?(\d{4})", body)
        out[m.group(2)] = {"type": m.group(1).lower(), "year": year.group(1) if year else None,
                           "verified": bool(marks) and marks[-1].lower() == "yes"}
    return out


def not_allowed(entries: dict[str, dict]) -> list[str]:
    """Keys outside the allow-list, or whose year differs from it."""
    return sorted(k for k, e in entries.items()
                  if k not in ALLOWED or (ALLOWED[k][1] is not None and e["year"] != ALLOWED[k][1]))


def _without_floats(tex: str) -> str:
    return re.sub(r"\\begin\{(figure|table)(\*?)\}.*?\\end\{\1\2\}", "", tex, flags=re.S)


def forbidden_layout(tex: str) -> list[str]:
    """DESIGN §11.2 forbidden layout commands found in the (comment-stripped) source."""
    t = strip_comments(tex)
    found = []
    if re.search(r"\\usepackage(\[[^\]]*\])?\{[^}]*\bgeometry\b[^}]*\}|\\newgeometry", t):
        found.append("geometry")
    for cmd in ("fontsize", "linespread", "baselinestretch", "enlargethispage"):
        if re.search(rf"\\{cmd}\b", t):
            found.append(f"\\{cmd}")
    if re.search(r"\\vspace\*?\s*\{\s*-", _without_floats(t)):
        found.append("negative \\vspace")
    if re.search(r"\\vskip\s*-", _without_floats(t)):
        found.append("negative \\vskip")
    if re.search(r"\\setlength\s*\{?\s*\\parskip", t):
        found.append("\\setlength{\\parskip}")
    body = _without_floats(t.split("\\begin{document}", 1)[-1])
    for s in SIZE_SWITCHES:
        if re.search(rf"\\{s}(?![A-Za-z])", body):
            found.append(f"\\{s}")
    return found


def section_titles(tex: str) -> list[str]:
    return re.findall(r"\\section\*?\{([^}]*)\}", strip_comments(tex))


def missing_sections(tex: str) -> list[str]:
    titles = [t.strip().lower() for t in section_titles(tex)]
    miss = [] if re.search(r"\\begin\{abstract\}", strip_comments(tex)) else ["Abstract"]
    for req, aliases in SECTIONS.items():
        if not any(t.startswith(a.lower()) for t in titles for a in aliases):
            miss.append(req)
    return miss


def has_ai_use(tex: str) -> bool:
    heads = re.findall(r"\\(?:sub)?section\*?\{([^}]*)\}", strip_comments(tex))
    return any(re.search(r"\bAI\b", h) and re.search(r"acknowledg", h, re.I) for h in heads)


RED_TEXT = re.compile(r"\\(?:text)?color\s*\{\s*red[^}]*\}", re.I)   # \color{red}, \textcolor{Red!50}


def marker_lines(text: str, marker: str) -> list[int]:
    """1-based numbers of the lines that begin (after optional spaces) with a `% ...` marker
    (Decision 65(b)): a marker quoted inside another comment or after text does not count."""
    word = re.escape(marker.lstrip("%").strip())
    pat = re.compile(rf"^[ \t]*%[ \t]*{word}(?![\w-])")
    return [i for i, line in enumerate(text.splitlines(), 1) if pat.match(line)]


def marker_counts(text: str) -> dict[str, int]:
    """The seven paragraph markers of RP-8, in DESIGN order, with their line counts."""
    return {m: len(marker_lines(text, m)) for m in RP8_FAIL_MARKERS + RP8_PASS_MARKERS}


def draft_markers(text: str, markers=FINAL_MARKERS) -> list[str]:
    """Markers present: TODO and red text in the comment-stripped text; `% ...` markers on a
    comment line that begins with them (marker_lines). The pseudo-marker "red text" matches any
    \\color{red...} or \\textcolor{red...} spelling, any case."""
    stripped = strip_comments(text)

    def present(m):
        if m == "red text":
            return bool(RED_TEXT.search(stripped))
        return bool(marker_lines(text, m)) if m.startswith("%") else m in stripped
    return [m for m in markers if present(m)]


def label_page(aux: str, label: str) -> int | None:
    m = re.search(r"\\newlabel\{" + re.escape(label) + r"\}\{\{[^}]*\}\{(\d+)\}", aux)
    return int(m.group(1)) if m else None


def labels_after(aux: str, page: int) -> list[str]:
    """Labels (other than refs:start) that the .aux places after `page`: material set after it."""
    return [lab for lab, p in re.findall(r"\\newlabel\{([^}]*)\}\{\{[^}]*\}\{(\d+)\}", aux)
            if lab != "refs:start" and int(p) > page]


def heading_at_top(page_text: str) -> bool:
    """The page's first text is the references heading (IEEEtran sets it in small capitals)."""
    return bool(re.match(r"\s*R\s?E\s?F\s?E\s?R\s?E\s?N\s?C\s?E\s?S\b", page_text or ""))


def refs_fit(n_pages: int | None, refs_page: int | None, refs_page_text: str,
             late_labels: list[str], limit: int = PAGE_LIMIT) -> tuple[bool, str]:
    """RP-4 (Decision 63): the text before the references fits in `limit` pages, i.e. nothing
    but references after page `limit`: refs:start on page `limit` or earlier, or at the top of
    page `limit` + 1 with nothing before it there, and no labelled float or section after
    page `limit`."""
    detail = f"{n_pages} pages in total; refs:start on page {refs_page}"
    if n_pages is None:
        return False, detail + " (no PDF)"
    if n_pages <= limit:
        return True, detail + f" (at most {limit} pages)"
    if refs_page is None:
        return False, detail + " (no fresh .aux: build with --build)"
    top = refs_page == limit + 1 and heading_at_top(refs_page_text)
    ok = (refs_page <= limit or top) and not late_labels
    why = (f"references start at the top of page {refs_page}" if top
           else f"text before the references ends on page {refs_page}")
    return ok, (detail + f"; {why}" + (f"; after page {limit}: {late_labels}" if late_labels else "")
                + f" (text before the references: max {limit} pages)")


def pdf_pages(path: Path) -> int:
    from pypdf import PdfReader
    return len(PdfReader(str(path)).pages)


def pdf_text(path: Path) -> str:
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)


def unreferenced_floats(tex: str) -> list[str]:
    t = strip_comments(tex)
    labels = []
    for body in re.findall(r"\\begin\{(?:figure|table)\*?\}(.*?)\\end\{(?:figure|table)\*?\}", t, re.S):
        labels += re.findall(r"\\label\{([^}]*)\}", body)
    refs = set()
    for group in re.findall(r"\\(?:ref|autoref|cref|Cref)\{([^}]*)\}", t):
        refs |= {k.strip() for k in group.split(",")}
    return [lab for lab in labels if lab not in refs]


def overfull_boxes(log: str, threshold: float) -> list[float]:
    return [float(x) for x in re.findall(r"Overfull \\hbox \(([\d.]+)pt too wide\)", log)
            if float(x) > threshold]


def undefined_refs(log: str) -> list[str]:
    return re.findall(r"((?:Reference|Citation) `[^']*' on page \d+ undefined)", log)


# ----- the checks -----

def _build(d: Path, tex: str) -> tuple[bool, str]:
    r = subprocess.run(["tectonic", "--keep-logs", "--keep-intermediates", tex], cwd=d,
                       capture_output=True, text=True)
    tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or [""]
    return r.returncode == 0, f"tectonic exit {r.returncode}: {tail[0][:80]}"


def _fresh(pdf: Path, sources: list[Path]) -> tuple[bool, str]:
    if not pdf.exists():
        return False, f"{pdf.name} missing"
    newest = max((s.stat().st_mtime for s in sources if s.exists()), default=0.0)
    ok = pdf.stat().st_mtime >= newest
    return ok, f"{pdf.name} {'is' if ok else 'is NOT'} newer than its sources"


def run(target: str, mode: str, root: Path = ROOT, build: bool = False) -> list[tuple]:
    root = Path(root)
    final = mode == "final"
    rows: list[tuple] = []

    def add(cid, ok, detail, warn=False, na=False):
        status = "N/A" if na else ("PASS" if ok else ("WARN" if warn else "FAIL"))
        rows.append((cid, REQ[cid], status, detail))

    bib_path = root / "report" / "refs.bib"
    entries = bib_entries(bib_path.read_text()) if bib_path.exists() else {}
    if target == "proposal":
        d = root / "proposal"
        tex_path, pdf = d / "proposal.tex", d / "proposal.pdf"
        tex = tex_path.read_text()
        if build or final:
            ok, detail = _build(d, tex_path.name)
        else:
            ok, detail = _fresh(pdf, [tex_path, bib_path])
        add("PR-1", ok, detail)
        n = pdf_pages(pdf) if pdf.exists() else None
        add("PR-2", n is not None and 1 <= n <= 2, f"{n} pages (allowed 1-2)")
        miss = missing_markers(tex)
        add("PR-3", not miss, f"missing SPEC-ELEMENT {miss}" if miss else "markers 1-6 present")
        keys = cite_keys(tex)
        unresolved = sorted(keys - set(entries))
        add("PR-4", len(keys) >= 2 and not unresolved,
            f"{len(keys)} distinct keys; unresolved {unresolved}")
        found = draft_markers(tex, ("TODO", "red text"))
        add("PR-5", not found, f"found {found}" if found else "none", na=not final)
        return rows

    if target != "report":
        raise ValueError(target)
    d = root / "report"
    tex_path, pdf = d / "main.tex", d / "main.pdf"
    tex = tex_path.read_text()
    all_tex = "\n".join(p.read_text() for p in sorted(d.glob("*.tex")))
    if build or final:
        ok, detail = _build(d, tex_path.name)
    else:
        ok, detail = _fresh(pdf, [*d.glob("*.tex"), bib_path, *(root / "figures").glob("*.pdf")])
    add("RP-1", ok, detail)
    add("RP-2", bool(re.search(r"\\documentclass\[[^\]]*\bconference\b[^\]]*\]\{IEEEtran\}",
                               strip_comments(tex))), "IEEEtran with the conference option")
    miss = missing_sections(tex)
    add("RP-3", not miss, f"missing {miss}" if miss else "abstract and six sections present")
    n = pdf_pages(pdf) if pdf.exists() else None
    aux = d / "main.aux"
    # the .aux counts only if it is from a build at least as new as the sources (`make report`
    # runs tectonic without --keep-intermediates, so an older .aux can be left behind)
    aux_ok = aux.exists() and _fresh(aux, [*d.glob("*.tex"), bib_path,
                                          *(root / "figures").glob("*.pdf")])[0]
    aux_text = aux.read_text() if aux_ok else ""
    page = label_page(aux_text, "refs:start") if aux_ok else None
    if n is not None and page is not None and n > PAGE_LIMIT:
        from pypdf import PdfReader
        page_text = PdfReader(str(pdf)).pages[page - 1].extract_text() if page <= n else ""
    else:
        page_text = ""
    add("RP-4", *refs_fit(n, page, page_text, labels_after(aux_text, PAGE_LIMIT)))
    add("RP-5", page is not None and page >= 7, f"refs:start on page {page} (need >= 7)",
        na=not final)
    bad = forbidden_layout(all_tex)
    add("RP-6", not bad, f"found {bad}" if bad else "none")
    keys = cite_keys(all_tex)
    unresolved, extra = sorted(keys - set(entries)), not_allowed(entries)
    add("RP-7", not unresolved and not extra,
        f"{len(keys)} cited; unresolved {unresolved}; outside DESIGN §13 {extra}")
    found = draft_markers(all_tex, RP8_FINAL)
    counts = ", ".join(f"{m.lstrip('% ')} {c}" for m, c in marker_counts(all_tex).items())
    add("RP-8", not found, (f"found {found}" if found else "none") + f"; markers: {counts}",
        na=not final)
    add("RP-9", has_ai_use(tex), "AI-use acknowledgment heading")
    log_path = d / "main.log"
    log = log_path.read_text(errors="replace") if log_path.exists() else ""
    unref = unreferenced_floats(all_tex)
    undef = undefined_refs(log)
    qq = pdf.exists() and "??" in pdf_text(pdf)
    add("RP-10", not unref and not undef and not qq,
        f"unreferenced {unref}; undefined {undef[:3]}; '??' in PDF: {qq}"
        + ("" if log else " (no .log: build with --build)"))
    over = overfull_boxes(log, 5.0)
    add("RP-11", bool(log) and not over,
        f"overfull > 5pt: {over}" if log else "no .log (build with --build)", warn=True)
    return rows


def exit_code(rows) -> int:
    return 1 if any(r[2] == "FAIL" for r in rows) else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", choices=["proposal", "report"], required=True)
    p.add_argument("--mode", choices=["draft", "final"], default="draft")
    p.add_argument("--build", action="store_true", help="build here with logs and .aux")
    p.add_argument("--only", metavar="CHECK",
                   help="print and exit on this check alone, as the full run measures it "
                        "(the Makefile's page gate: --only RP-4, Decision 68)")
    a = p.parse_args(argv)
    rows = run(a.target, a.mode, root=ROOT, build=a.build)
    if a.only:
        rows = [r for r in rows if r[0] == a.only]
        if not rows:
            p.error(f"no check {a.only} for --target {a.target}")
    print(f"{'check':<6} {'req':<6} {'status':<6} detail")
    for cid, req, status, detail in rows:
        print(f"{cid:<6} {req:<6} {status:<6} {detail}")
    code = exit_code(rows)
    print(f"spec_check {a.target} ({a.only or a.mode}): {'FAIL' if code else 'PASS'}")
    return code


if __name__ == "__main__":
    sys.exit(main())
