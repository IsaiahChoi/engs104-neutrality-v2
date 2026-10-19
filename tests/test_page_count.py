"""tools/page_count.py (MIGRATION §3 item 1): exit 0 inside the page range, 1 outside it, so an
over-length PDF fails `make proposal` / `make report`."""
from __future__ import annotations

import subprocess
import sys

import pytest
from pypdf import PdfWriter

from src.utils import ROOT


def _pdf(path, pages: int):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=612, height=792)
    with open(path, "wb") as f:
        w.write(f)
    return path


def _run(pdf, lo, hi):
    return subprocess.run([sys.executable, str(ROOT / "tools" / "page_count.py"), str(pdf),
                           "--min", str(lo), "--max", str(hi)], capture_output=True, text=True)


@pytest.mark.parametrize("pages", [1, 2])
def test_in_range_exits_zero(tmp_path, pages):
    r = _run(_pdf(tmp_path / "a.pdf", pages), 1, 2)
    assert r.returncode == 0 and f"{pages} pages" in r.stdout


@pytest.mark.parametrize("pages,lo,hi", [(3, 1, 2), (5, 6, 8), (9, 1, 8)])
def test_out_of_range_exits_one(tmp_path, pages, lo, hi):
    r = _run(_pdf(tmp_path / "a.pdf", pages), lo, hi)
    assert r.returncode == 1 and "outside" in r.stderr
