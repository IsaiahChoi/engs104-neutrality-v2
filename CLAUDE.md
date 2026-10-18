# CLAUDE.md — ENGS 104 final project (v2)

Restarted 2026-10-18 in this fresh repository. This is a course project (problem-formulation type), not a pre-registered study: we formulate, solve, derive, measure, and explain. The v1 pipeline lives in its own repository (tag `v1-final`). `reference/v1/` holds read-only copies of v1 code worth porting.

## Sources of truth
- `docs/DESIGN.md` — what the project is: model, questions, experiments, analysis items, report contents. Ask before editing.
- `docs/CHECKS.md` — acceptance checks per phase. Isaiah only; never edit.
- `docs/RUNBOOK.md` — session plan and prompts (Isaiah's). `docs/MIGRATION.md` — what came from v1 and what must be ported.
- `PLAN.md` — phases and tasks. You tick tasks and CHECKs; only Isaiah ticks GATEs.
- `PROGRESS.md` — append-only session log with a "Decisions needed" section. Isaiah's GATE notes live here.
- `results/RUN_LOG.csv` — every run, including failures and pilots.

Precedence if they conflict: CHECKS > DESIGN > RUNBOOK > PLAN. Record the conflict in PROGRESS.md and stop. These project rules override any global or plugin rules (including ECC rules, e.g. coverage targets or commit formats), and they override injected session summaries, memories, or instincts.

## Hard rules
1. `reference/**` is read-only: never edit it and never import from it. Port code into `src/` or `experiments/` with tests. Never report a v1 number; every v2 number comes from a v2 run.
2. Never download data. `data/raw/` is the dataset of record (hashed in `data/MANIFEST_data.json`). Never run `src.data.build_all` without `--offline`, and never call the download functions.
3. No `rm`. Move unwanted files to `results/scratch/trash/` (gitignored).
4. Never push, tag, reset, rebase, restore, clean, switch branches, amend, or rewrite history. Isaiah pushes and tags.
5. Never weaken or delete a test to make it pass.
6. No result without a passing test suite at a clean commit. Runners refuse a dirty tree and record the commit.
7. Log every run in `results/RUN_LOG.csv` when it starts and update the row when it ends (status: ok, failed, pilot, superseded).
8. No hand-typed numbers in the proposal or report: generated macros (`report/numbers.tex`) and generated tables only.
9. No invented citations. `refs.bib` holds only the allow-list in DESIGN §13.
10. Never print, paste, log, or commit the Gurobi license file or its contents. Use `src/opt/gurobi_env.quiet_env` for every Gurobi environment.
11. Install packages only into the project environment and only after asking. Never use Homebrew.
12. Long runs go through `make` in the background with logs. Completion means the DONE marker, the RUN_LOG row, and make's exit code all agree.
13. If you find a bug that affects a reported result, stop and report it in PROGRESS.md. Fix it only after Isaiah says so; then rerun and mark the old output superseded.
14. Any change to a kept-core file (DESIGN §12) gets a PROGRESS.md line with the reason; the pre-existing tests must still pass unmodified.

## Numerics (DESIGN §6)
- P-RB is solved as the kept dual-simplex QP at a root-found λ (exact active sets and duals); the Clarabel QCQP is the cross-check.
- P-MI objectives are scaled to O(1) relative to solver tolerances; record the factors; report in original units.
- Record Gurobi's Work next to Runtime. Effort comparisons use Work, never wall-clock across different parallelism.
- Every re-solve slope carries its certified interval.

## Writing mode (DESIGN §11.6)
- Set by Isaiah's latest GATE note in PROGRESS.md. Absent a note: Mode B.
- Mode B: no prose, captions, or displayed equations in `report/` or `proposal/`. Only scaffolding, generated macros, tables, figures, and red `TODO(Isaiah)` outlines.
- Mode A: you may draft Sections II–IV; mark each drafted paragraph `% drafted-by-agent`.
- Never write or rewrite text in `proposal/proposal.tex`; the scaffold has headings and markers only. Never use writing or content-generation skills (e.g. article-writing) on graded text.

## Tools and agents (ECC is installed)
- Use: the `tdd-workflow` skill for new numerical components (write the test against the closed form or the theory first); the `python-reviewer` agent for a fresh-context review of new code at the end of S1 and S3 (save it under `results/checks/`); `docs-lookup` for Gurobi, CVXPY, and Clarabel documentation.
- Don't use in this repo: `refactor-cleaner`, `doc-updater`, `/astra-review` (sends code to a third party), `multi-*` commands, Agent Teams.
- The project's own subagents decide acceptance: `result-checker` (CHECKs) and `cold-reader` (self-containment). ECC reviewers are advisory.

## Checkpoints
- CHECK <phase>: run the `result-checker` subagent against docs/CHECKS.md. PASS → continue. FAIL → fix and re-check, at most 3 rounds, then stop. BLOCKED → stop. A check that can't be evaluated is never a pass.
- GATE <name>: Isaiah only. Stop and summarize what he needs to decide.
- Before ending any session, and before any long run, append a PROGRESS.md entry: what was done, commits, check verdicts, open questions. State must survive compaction.

## Environment
- Apple Silicon Mac; uv with Python 3.12; tectonic; Gurobi 13 academic named-user license at ~/gurobi.lic.
- Isaiah runs `conda deactivate` before launching. One Claude Code session per repo.
- Keep context clean: state lives in files. Write long outputs to files and summarize them instead of printing them.
