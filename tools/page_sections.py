"""Per-section page measurement of report/main.tex (DESIGN §11.1; S4b step 4).

`uv run python tools/page_sections.py [--out FILE]` copies report/ to results/scratch/pages/
(gitignored), adds zref position markers (zref-savepos with the abspage property) before every
\\section and \\subsection, the abstract, refs:start and \\end{document}, and at the top and
bottom of every float body, builds that copy with tectonic, and reads the positions from its .aux
and the page geometry from its log. The real report is not touched; the copy's page count is
checked against report/main.pdf's.

A position is in column units, 2·(page − 1) + column + (text top − y)/textheight; a part's span
is the distance to the next part's marker, halved to pages. Two accountings:
- A, floats where they land: the spans as measured (a float sits in the span of the part whose
  span contains its top marker).
- B, each float in the part that first references it (DESIGN §11.1): its area (body height plus
  \\textfloatsep, or \\dbltextfloatsep and both columns for a starred float) moves from the part
  where it lands to the part with its first \\ref outside comments and outside the outline-only
  parts (Abstract and Introduction, whose red outlines point at floats as evidence).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = ROOT / "results" / "scratch" / "pages"
PT = 65536.0                                   # sp per pt
INCH_PT = 72.27
SKIP_TITLES = ("Abstract", "Introduction")     # outline-only parts (module docstring)

PREAMBLE = (r"\usepackage{zref-savepos,zref-abspage}\makeatletter\zref@addprop{savepos}{abspage}"
            r"\makeatother\newcommand{\mk}[1]{\zsavepos{#1}}"
            r"\AtBeginDocument{\typeout{PAGEGEOM paperheight=\the\paperheight;"
            r" textheight=\the\textheight; topmargin=\the\topmargin; headheight=\the\headheight;"
            r" headsep=\the\headsep; oddsidemargin=\the\oddsidemargin;"
            r" columnwidth=\the\columnwidth; columnsep=\the\columnsep;"
            r" textfloatsep=\the\textfloatsep; dbltextfloatsep=\the\dbltextfloatsep}}")
FLOAT = re.compile(r"\\begin\{(figure|table)(\*?)\}(\[[^\]]*\])?(.*?)\\end\{\1\2\}", re.S)
HEAD = re.compile(r"\\(section|subsection)\*?\{([^}]*)\}|\\begin\{abstract\}|\\label\{refs:start\}")


def _blank_comments(src: str) -> str:
    """Comments replaced by spaces, so character positions are kept."""
    return re.sub(r"(?<!\\)%[^\n]*", lambda m: " " * len(m.group(0)), src)


def parts(src: str) -> list[dict]:
    """The Abstract, every section and subsection, and the references, in source order."""
    out, k = [], 0
    for m in HEAD.finditer(_blank_comments(src)):
        if m.group(0).startswith(r"\begin{abstract}"):
            out.append({"key": "abs", "title": "Abstract", "pos": m.start(), "level": 1})
        elif m.group(0).startswith(r"\label"):
            out.append({"key": "refs", "title": "References", "pos": m.start(), "level": 1})
        else:
            k += 1
            sec = m.group(1) == "section"
            out.append({"key": f"{'sec' if sec else 'sub'}{k}", "title": m.group(2).strip(),
                        "pos": m.start(), "level": 1 if sec else 2})
    return out


def first_refs(src: str, prts: list[dict], skip=()) -> dict[str, str]:
    """{float label: key of the part with its first \\ref}, comments and `skip` parts ignored."""
    t = _blank_comments(src)
    out = {}
    for m in re.finditer(r"\\ref\{((?:fig|tab):[^}]*)\}", t):
        owner = [p["key"] for p in prts if p["pos"] <= m.start()]
        if not owner or owner[-1] in skip or m.group(1) in out:
            continue
        out[m.group(1)] = owner[-1]
    return out


def inject(src: str) -> str:
    """The source with the markers and the preamble (module docstring)."""
    def flt(m):
        body = m.group(4)
        lab = re.search(r"\\label\{([^}]*)\}", body)
        if not lab:
            return m.group(0)
        name, env = lab.group(1), m.group(1) + m.group(2)
        return (f"\\begin{{{env}}}{m.group(3) or ''}\\mk{{flt:{name}:top}}{body}"
                f"\\mk{{flt:{name}:bot}}\\end{{{env}}}")
    out = FLOAT.sub(flt, src)
    pieces, last = [], 0
    for p in parts(out):
        pieces += [out[last:p["pos"]], f"\\mk{{{p['key']}}}"]
        last = p["pos"]
    out = "".join(pieces) + out[last:]
    out = out.replace(r"\end{document}", r"\mk{end}\end{document}")
    return re.sub(r"(\\documentclass(\[[^\]]*\])?\{[^}]*\})", lambda m: m.group(1) + "\n" + PREAMBLE,
                  out, count=1)


@dataclass(frozen=True)
class Geometry:
    paperheight: float
    textheight: float
    texttop: float                             # y of the text block's top, from the page bottom
    colsplit: float                            # x between the two columns


def units(g: Geometry, page: int, x: float, y: float) -> float:
    return 2 * (page - 1) + (1 if x >= g.colsplit else 0) + (g.texttop - y) / g.textheight


def _u(g, pos, k):
    return units(g, *pos[k])


def spans(g: Geometry, pos: dict, keys: list[str], end: str = "end") -> dict[str, float]:
    """Pages from each part's marker to the next one's (the last to `end`)."""
    seq = list(keys) + [end]
    return {a: (_u(g, pos, b) - _u(g, pos, a)) / 2 for a, b in zip(seq, seq[1:])}


def float_areas(g: Geometry, pos: dict, wide: dict, sep: float, sep_wide: float | None = None) -> dict:
    out = {}
    for f, w in wide.items():
        h = (pos[f"flt:{f}:top"][2] - pos[f"flt:{f}:bot"][2] + (sep_wide if w and sep_wide is not None
                                                                 else sep)) / g.textheight
        out[f] = {"wide": bool(w), "pages": h if w else h / 2}
    return out


def landing(g: Geometry, pos: dict, floats: dict, keys: list[str], end: str = "end") -> dict:
    """{float: the part whose span contains its top marker}."""
    seq = list(keys) + [end]
    out = {}
    for f in floats:
        u = _u(g, pos, f"flt:{f}:top")
        out[f] = next((a for a, b in zip(seq, seq[1:]) if _u(g, pos, a) <= u < _u(g, pos, b)), None)
    return out


def by_first_reference(A: dict, floats: dict, landed: dict, first: dict) -> dict:
    B = dict(A)
    for f, info in floats.items():
        src, dst = landed.get(f), first.get(f)
        if src in B and dst in B and src != dst:
            B[src] -= info["pages"]
            B[dst] += info["pages"]
    return B


def _aux_positions(aux: str) -> dict:
    out = {}
    for m in re.finditer(r"\\zref@newlabel\{([^}]*)\}\{(.*)\}", aux):
        props = dict(re.findall(r"\\(posx|posy|abspage)\{(-?\d+)\}", m.group(2)))
        if {"posx", "posy", "abspage"} <= set(props):
            out[m.group(1)] = (int(props["abspage"]), float(props["posx"]), float(props["posy"]))
    return out


def _geometry(log: str) -> tuple[Geometry, dict]:
    m = re.search(r"PAGEGEOM (.*?dbltextfloatsep=[-\d.]+pt)", log.replace("\n", ""))   # TeX wraps at 79
    d = {k: float(v) * PT for k, v in re.findall(r"(\w+)=(-?[\d.]+)pt", m.group(1))}
    top = d["paperheight"] - (INCH_PT * PT + d["topmargin"] + d["headheight"] + d["headsep"])
    split = INCH_PT * PT + d["oddsidemargin"] + d["columnwidth"] + d["columnsep"] / 2
    return Geometry(d["paperheight"], d["textheight"], top, split), d


def measure(report: Path = ROOT / "report") -> dict:
    if SCRATCH.exists():                       # never deleted (CLAUDE.md rule 3): moved to trash
        trash = SCRATCH.parent / "trash"
        trash.mkdir(parents=True, exist_ok=True)
        k = len(list(trash.glob("pages_*")))
        SCRATCH.rename(trash / f"pages_{k:04d}")
    shutil.copytree(report, SCRATCH)
    shutil.copytree(ROOT / "figures", SCRATCH.parent / "figures", dirs_exist_ok=True)   # ../figures/
    src = (report / "main.tex").read_text()
    (SCRATCH / "main.tex").write_text(inject(src))
    subprocess.run(["tectonic", "--keep-intermediates", "--keep-logs", "main.tex"], cwd=SCRATCH,
                   check=True, capture_output=True)
    pos = _aux_positions((SCRATCH / "main.aux").read_text())
    g, dims = _geometry((SCRATCH / "main.log").read_text())
    prts = parts(src)
    keys = [p["key"] for p in prts]
    A = spans(g, pos, keys)
    wide = {m2.group(1): bool(m.group(2)) for m in FLOAT.finditer(src)
            for m2 in [re.search(r"\\label\{([^}]*)\}", m.group(4))] if m2}
    floats = float_areas(g, pos, wide, dims["textfloatsep"], dims["dbltextfloatsep"])
    landed = landing(g, pos, floats, keys)
    skip = tuple(p["key"] for p in prts if p["title"] in SKIP_TITLES)
    first = first_refs(src, prts, skip=skip)
    B = by_first_reference(A, floats, landed, first)
    n_copy = len(PdfReader(SCRATCH / "main.pdf").pages)
    n_real = len(PdfReader(report / "main.pdf").pages)
    rows = [{"key": p["key"], "title": p["title"], "level": p["level"], "A": A[p["key"]],
             "B": B[p["key"]]} for p in prts]
    sec = [p for p in prts if p["level"] == 1]
    names = [p["title"] for p in sec]
    i0, i1 = names.index("Problem Setting"), names.index("Discussion")
    in_2_4 = {p["key"] for p in prts if sec[i0]["pos"] <= p["pos"] < sec[i1]["pos"]}
    return {"pages_copy": n_copy, "pages_report": n_real, "refs_start_page": pos["refs"][0],
            "rows": rows, "floats": {f: {**v, "lands": landed[f], "first_ref": first.get(f)}
                                     for f, v in floats.items()},
            "II_IV": {"A": sum(r["A"] for r in rows if r["key"] in in_2_4),
                      "B": sum(r["B"] for r in rows if r["key"] in in_2_4)}}


def section_table(res: dict) -> list[dict]:
    """Rows rolled up to sections (subsections listed beneath with their own values)."""
    out, cur = [], None
    for r in res["rows"]:
        if r["level"] == 1:
            cur = {**r, "subs": []}
            out.append(cur)
        else:
            cur["A"] += r["A"]
            cur["B"] += r["B"]
            cur["subs"].append(r)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    res = measure()
    res["sections"] = section_table(res)
    lines = [f"pages: {res['pages_report']} (scratch copy {res['pages_copy']}); refs:start on page "
             f"{res['refs_start_page']}; II-IV: A {res['II_IV']['A']:.2f}, B {res['II_IV']['B']:.2f}",
             "part | A (where floats land) | B (first reference)"]
    for s in res["sections"]:
        lines.append(f"{s['title']} | {s['A']:.2f} | {s['B']:.2f}")
        lines += [f"  {r['title']} | {r['A']:.2f} | {r['B']:.2f}" for r in s["subs"]]
    lines.append("floats: " + "; ".join(f"{f} {v['pages']:.2f} p, lands {v['lands']}, first ref {v['first_ref']}"
                                        for f, v in res["floats"].items()))
    print("\n".join(lines))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
