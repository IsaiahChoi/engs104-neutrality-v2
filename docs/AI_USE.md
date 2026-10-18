# AI use log (supports disclosure in the proposal and report)

ENGS 104 AI policy (quote or link it here): ____
Discussed with Prof. Fügenschuh on: ____  Notes: ____

Tools: Claude (claude.ai chat) for planning; Claude Code for implementation.

| Date | Tool | What the AI did | What Isaiah did / reviewed |
|---|---|---|---|
| 2026-10-15 | Claude (chat) | Brainstormed project options; drafted the project brief, plan, draft hypotheses, and repo kit | Chose the project; will set parameters, edit and freeze hypotheses |
| 2026-10-15 | Claude Code | (Recorded retroactively.) Phase 0 environment checks and Phase 1 data pipeline (yfinance prices, Ken French factors, panel, data report, data tests) | Set up the gate-verifier and gate criteria; adjusted gate thresholds (commit 29b65d9) |
| 2026-10-15/16 | Claude Code + gate-verifier subagent | Gate 1 and 2 verification; data-report D2 tables; risk model (rolling 6-factor regressions, bias statistic, $1M liquidity rule) with tests; continuous optimizer, attribution, TC, alphas, and validation tests; REVIEW 3; proposal draft with a preliminary (exploratory) figure | Approved the zero-volume and $1M liquidity rules; required the recovery-test controls; to sign off on test changes, decide λ calibration, and rewrite the proposal |
| 2026-10-16 | Claude Code + gate-verifier subagent | REVIEW 3 rerun; Phase 3b (masked two Yahoo errors, winsorized momentum, raw hashes, recovery-test additions, λ policy and feasibility report) with AUTO-GATE 3b; freeze confirmed; Phase 5–7 code written but not run; stopped on REVIEW 3 concern 10 | Froze the hypotheses; to decide the E3 subsample alpha and sign off on test changes |
| 2026-10-16/18 | Claude Code + gate-verifier subagent | Ran E1 (incl. a rerun after a shadow-price bug), E2 and E3 with integrity gates 5 and 6 (each passed on round 2); computed the registered H1–H4 analyses; found that MIQP numerics invalidate the H3/H4 records and stopped | Decided the E3 subsample alpha (amendment), signed off test changes, made the GATE 8 decision; to decide how to handle the E3 numerics |

Draft disclosure for the report (edit so it is accurate before using it):
"Software for this project was written with the assistance of an AI coding agent (Claude Code)
under the author's direction. The problem formulation, modeling decisions, derivations,
hypotheses, and interpretation of results are the author's own; all AI-generated code was
reviewed and validated with the tests described in Section IV."

---

## v2 (restarted 2026-10-18)

The project was restarted as a course project without pre-registration, in a fresh repository extracted from v1 commit 05468f2 (see docs/MIGRATION.md). The extraction (selecting kept files, removing six v1-only tests, writing CLAUDE.md, DESIGN, CHECKS, RUNBOOK, Makefile, settings, and subagent files) was done by Claude in chat, under Isaiah's direction. Claude Code (with the ECC plugin) and the project's result-checker subagent continue from here.

| Date | Tool | What the AI did | What Isaiah did / reviewed |
|---|---|---|---|
| 2026-10-18 | Claude (chat) | Read the v1 repo, data backup, and course documents; designed v2; extracted the v2 repo and kit | Chose to restart; to confirm decisions D1–D15, check the AI-use policy, and write the proposal |
