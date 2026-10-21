# AI use log (supports disclosure in the proposal and report)

ENGS 104 AI policy (quote or link it here): AI use is fine for this course, with disclosure (recorded by Isaiah on 2026-10-20). Source: ____ (who said it, how and when; quote it if it was written).
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
| 2026-10-18/19 | Claude Code + result-checker | S1: verified the kept core, ported v1 infrastructure, built the v2 foundations with tests; CHECK CORE passed in round 3. S2: design pilot, C1–C3, Figs. 1–3, FACTS; CHECK CONT passed in round 1 | Decided Decisions 1–26 at gates; signed GATE C |
| 2026-10-19/20 | Claude Code + result-checker | S2b–S2e: pilot reruns with the 1e-9 polish, the rescaled perspective arm, slope and root-bound tooling, Decision 25; K20 recomputation | Decided Decisions 27–43; signed GATE DESIGN and the CHECKS edits |
| 2026-10-18 to 10-21 | Claude (chat) | Read results and checker reports; proposed most design decisions, CHECKS row text, DESIGN edit text, gate-note drafts and session prompts; derivation sketches (finite-difference noise, certified-slope sensitivity, value-function differentiability, the hedged-leg relaxation mechanism) | Chose among the proposals; edited and signed the gate notes and CHECKS; ran the commands |
| 2026-10-20/21 | Claude Code + result-checker + python-reviewer | S3: K29c, I1, I2, N1, N2, analysis, Figs. 4–5, Tables II–III; CHECK INT passed in round 2 | Read the results; signed GATE I |
| 2026-10-21 | Claude (chat) | Drafted the proposal text from proposal/FACTS.md and docs/DESIGN.md. (The row first written here on 10/20 anticipated a draft that did not exist yet; corrected 10/21.) | Reviewed it before committing it; the submission is recorded in PROGRESS |
| 2026-10-21 | Claude Code + result-checker | S3b: analysis hardening (tests first), K29b-ext, support-stability and hedged-leg recomputations, the N2(b) normalization probe, FACTS extended; CHECK S3B passed in round 2 | Approved the S3b scope and its predictions at GATE I; read S3b; Decision 49 |
| 2026-10-21 | Claude Code + result-checker + cold-reader | S4: FACTS step 0; the disclosures run; the report build in Mode A (drafted Sections II–IV and their captions, with red outlines elsewhere; numbers.tex, figures, tables); CHECK REPORT failed after 3 rounds (page count, one sentence); cold read | Set Mode A at GATE I; read the S4 build |
| 2026-10-21 | Claude (chat) | Read the S4 build and checked its numbers and drafted derivations against the files; recommended Decisions 50–53, the DESIGN edits and the S4b scope; looked up the bibliographic details of the 8 proposal references; wrote the commit kit | Adopted the recommendations for Decisions 50–53 without changes; ran the kit's commands and checks; checks the derivations by hand at GATE R |

Note (2026-10-20): the "Draft disclosure for the report" paragraph in the v1 section predates v2 and is not accurate for it. In v2, Claude (chat and Code) proposed most design decisions and checks, and Isaiah decided them at gates. Rewrite the disclosure from this log before using it.
