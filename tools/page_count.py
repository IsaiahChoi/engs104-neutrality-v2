#!/usr/bin/env python3
"""Print a PDF's page count and warn if it is outside the allowed range."""
import argparse
import sys

from pypdf import PdfReader

p = argparse.ArgumentParser()
p.add_argument("pdf")
p.add_argument("--min", type=int, required=True)
p.add_argument("--max", type=int, required=True)
a = p.parse_args()

n = len(PdfReader(a.pdf).pages)
if a.min <= n <= a.max:
    print(f"{a.pdf}: {n} pages (OK, limit {a.min}-{a.max})")
else:
    print(f"WARNING {a.pdf}: {n} pages, outside the {a.min}-{a.max} page limit", file=sys.stderr)
