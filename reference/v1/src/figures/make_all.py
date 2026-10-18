"""`make figures`: regenerate every figure and table from files in results/ (CLAUDE.md rule 7;
GATE_CRITERIA I7). Entries are added as each RQ's results exist."""
from __future__ import annotations

import sys

from src.figures import fig_bias, fig_f1_cost_curves, fig_f2_attribution, fig_f3_tc_ir, tables

STEPS = [fig_bias.make, fig_f1_cost_curves.make, fig_f2_attribution.make, tables.h1,
         fig_f3_tc_ir.make, tables.h2]


def main() -> int:
    for step in STEPS:
        print(step())
    return 0


if __name__ == "__main__":
    sys.exit(main())
