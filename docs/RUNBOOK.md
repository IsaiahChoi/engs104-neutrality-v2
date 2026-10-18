# RUNBOOK (v2.1) — ENGS 104 "The Shadow Price of Neutrality"

The plan from tonight to a submitted proposal and IEEE report, executed mostly by Claude Code (with the ECC plugin) on Isaiah's Mac. Prepared Sunday 2026-10-18, after reading the full v1 repo, the data backup, the course documents, and the ECC README. **This replaces both earlier runbooks.**

Out of scope: the 15-minute talk, its Q&A, and audience participation.

---

## 0. Read this first

### 0.1 What you are holding

`engs104-neutrality-v2.zip` is a **fresh repository**, not a kit to unpack into the old one:

- **What it contains:**
  - The v1 code that is already validated (data pipeline, risk model, optimizer, alphas, and their tests), imported unchanged except for removing six v1-only tests.
  - The v2 documents (this file, `DESIGN.md`, `CHECKS.md`, `MIGRATION.md`), a v2 `CLAUDE.md`, `Makefile`, `.claude/settings.json`, and two project subagents.
  - Read-only copies of the v1 code worth porting (`reference/v1/`), and the course PDFs.
- **What it leaves out:**
  - **The data.** The pre-flight copies it from your v1 folder and checks every file against the committed manifest. I verified that all 507 raw files in both your repo zip and `data_raw_backup.zip` match their recorded hashes.
  - **The v1 project itself.** Hypotheses, gates, results, and the proposal draft stay in the v1 repo. You tag that repo `v1-final` and push it as a private archive.

Why a fresh repository instead of archiving inside the old one:

- The agent never sees frozen hypotheses, gate criteria, or v1 results it might act on.
- Nothing has to be untangled by `git mv` at the start.
- The v1 history stays intact, on its own.

`docs/MIGRATION.md` lists every file and the one edit made at extraction.

### 0.2 Precedence

CHECKS > DESIGN > RUNBOOK > PLAN, and project rules > ECC global rules > injected memories or instincts (CLAUDE.md).

### 0.3 What reading the repo changed in the plan

1. **The risk budget is solved through the existing exact QP, not as a new QCQP.**
   - The kept optimizer deliberately uses Gurobi's dual simplex at 1e-9 tolerances. Its own comments record that barrier leaves weights of 1e-7–1e-5 on names that should be zero, with KKT residuals around 1e-5; the attribution code needs exact active sets.
   - The 3% risk budget is therefore enforced by root-finding λ on that QP (KKT makes this exactly the risk-budget problem), with a Clarabel QCQP as the cross-check.
   - This keeps every validated piece and removes the quadratic-constraint dual problem entirely.
2. **The subsample rule is the existing one:** top-N by 63-day median dollar volume, alpha restricted from the full universe.
3. **The MIQP code already has a "polish" step** (re-solving the exact QP at the incumbent's support). v2 uses it for incumbent values.
4. **Both relaxations are reported, because they disagree.** The perspective relaxation (a barrier QCP) returned SUBOPTIMAL in v1's first E3 run and crashed it. The big-M relaxation is a plain QP. v2 reports both relaxation duals, and records a failed relaxation instead of crashing.
5. **Six tests depended on v1-only code** and were removed. One of them guards a real v1 bug (shadow prices recorded after resetting swept caps). v2 must re-create it for its own sweep runner (CHECKS K12).
6. **`tools/page_count.py` never fails a build:** it prints a warning and exits 0. Fixed in S1.
7. **v1's `make data` target would have re-downloaded prices.** The v2 Makefile has no download path.
8. **v1's settings allowed `uv add` without asking**, contradicting its own CLAUDE.md. v2 moves it to "ask".
9. **v1 has no git remote.** Nothing has been pushed, so both repos get a private GitHub copy tonight.

### 0.4 Key dates (Overview calendar; confirm due times on Canvas)

| Date | Event |
|---|---|
| Tue 10/20 | Ferguson office hours 11:00–12:00, MacLean 309 |
| Wed 10/21 | Fügenschuh office hours 2:00–3:00, MacLean 307 |
| **Thu 10/22** | **Project proposal due**; Fügenschuh office hours 2:00–3:00 |
| **Fri 10/23** | **Project proposal discussions** (class, 4:35–5:25) |
| Fri 10/30 | HW3 due |
| Fri 11/13 | HW4 due |
| Tue 11/17, Thu 11/19, Fri 11/20 | Final presentations |
| **Fri 11/20** | **Project report due** |

The Overview prints Weeks 9–10 as "10/10" through "10/20"; they follow 11/6, so they must mean 11/10 through 11/20.

### 0.5 Discrepancies across the course documents (ask; don't guess)

- **Grading.**
  - Handout: proposal 10%, presentation 30%, report 60% of the project.
  - Syllabus: the project is 50% of the course grade.
  - Overview: the project is 40% (5/15/20).
  - The report is the largest component in every version.
- **Page count.** "6–8 pages" doesn't say whether references count. The plan meets both readings: at least 6 pages before references, at most 8 in total.
- **Instructors.** There are two; the Overview says the proposal is discussed with "one or both".
- **AI use.** No rule in either document; the syllabus defers to the DCAL guide and the Honor Principle.

---

## 1. Calendar

```
SUN 10/18  S0 pre-flight (~45 min) → email instructors → paste S1 → S1+S2 run overnight (stop on any failed check)
MON 10/19  read the S2 report → GATE C → write the proposal
TUE 10/20  proposal (optional Ferguson office hours)
WED 10/21  Fügenschuh office hours: MIQP design (§5.1) → finish the proposal
THU 10/22  submit the proposal
FRI 10/23  proposal discussion → GATE DESIGN → paste S3 (integer + numerics, Fri night–Sun)
MON 10/26  read the S3 report → GATE I (sets writing mode) → paste S4 (report build)
10/27–11/12  you: derivations and your sections; S5 integration passes
MON 11/16  FINAL → paste S6
FRI 11/20  submit the report
```

| When | You | Claude Code | Gate |
|---|---|---|---|
| Sun 10/18 | S0 (§3); the email (§5.1); paste S1 | S1: audit, verify the core, port, v2 foundations, tests, scaffolds; then S2: pilot, C1–C3, proposal facts (≈6–9 h total, overnight) | CHECK CORE, CHECK CONT |
| Mon 10/19 | Read the S2 report; write the GATE C note; write the proposal | Idle | GATE C |
| Tue 10/20–Wed 10/21 | Proposal; office hours | Idle | — |
| Thu 10/22 | Submit the proposal | — | — |
| Fri 10/23 | Discussion; GATE DESIGN note; paste S3 | S3: I1, I2, N1, N2, analysis, figures (Fri night–Sun) | CHECK INT |
| Mon 10/26 | Read S3; GATE I note (writing mode); paste S4 | S4: report build, spec check, cold read | GATE I |
| 10/27–10/30 | Derivations (§5.3); GATE R; HW3 due 10/30 | — | GATE R |
| 11/2–11/12 | Your sections; reference verification | S5 integration passes, about twice | — |
| Mon 11/16 | FINAL note | S6: clean-checkout build, compliance walk, SUBMISSION.md | FINAL |
| Fri 11/20 | Submit | — | — |

**Your hours, roughly:**
- proposal: 6–8;
- meetings: 2;
- derivations: 5–7;
- gate reading: 3–4;
- writing: 12–20 in Mode A, 22–35 in Mode B.

Claude Code does all the code, runs, verification, figures, tables, macros, LaTeX, integrity checks, and (in Mode A) the Section II–IV drafts.

---

## 2. Sticking points and decisions (confirm before pasting S1)

Each row is a choice that changes what gets built. The recommendation is what the kit already implements; change PROGRESS.md's decision line in S0 if you choose otherwise.

| # | Sticking point | Recommendation | Why | Main alternative and its cost |
|---|---|---|---|---|
| D1 | Restart inside the old repo, or a fresh one | **Fresh v2 repo (this zip); v1 tagged `v1-final` and pushed as a private archive** | The agent never sees v1's frozen files or results; no untangling; v1 history intact | Archive in place: a risky first session of `git mv`, plus v1 clutter in every context |
| D2 | Scope | **Q1–Q3 (DESIGN §2). Drop the Monte Carlo and the oracle alpha; keep ex-ante TC** | The course rewards the optimization; the Monte Carlo was the heaviest compute and the messiest result | Keep a reduced Monte Carlo: about a page of statistics |
| D3 | Continuous formulation | **Fixed risk budget (3%/yr)**: constraint costs at equal risk | Fixed λ let uncapped books lever up in v1 | Fixed λ: costs mix risk and alpha |
| D4 | How to solve the risk budget | **Root-find λ on the kept exact dual-simplex QP; Clarabel QCQP as cross-check** | Exact active sets and duals the attribution needs; reuses validated code; no QCP dual issues | Gurobi barrier QCQP: approximate active sets, KKT residual ~1e-5 |
| D5 | Control for "which alpha pays for neutrality" | **Factor decomposition α⊥/α∥ with the closed form √(1 − φ)** | No future data; analysis and computation meet in one figure | The oracle alpha: needs future returns and a "not tradable" caveat |
| D6 | Risk in the MIQP | **Mean-variance at λ\* (the risk budget's multiplier), fixed within (date, N)** | Lagrangian relaxation of the risk row; standard perspective setting; kept code | MISOCP with a risk row: harder branch-and-bound, less standard |
| D7 | Which relaxation dual | **Both: big-M (QP) and perspective (QCP)** | They differ (DESIGN A7), and that difference is a finding | One only: loses the "tighter bound ≠ better slope" point |
| D8 | Effort metric | **Gurobi Work with WorkLimit** (confirmed in S1) | Deterministic: results don't depend on load, sleep, or parallelism | Wall-clock: runs must be strictly alone and are still noisy |
| D9 | When MIQP parameters are fixed | **At GATE DESIGN, after an instructor has seen the pilot's proposal** | Weekend compute isn't wasted if he suggests changes | Run now: a suggestion means rerunning |
| D10 | Agent autonomy tonight | **Chain S1 → S2 in one session, stopping on any failed check** | You wake up to continuous results and preliminary figures with three days to the proposal | Two sessions: a day later |
| D11 | Who writes what | **Proposal: you. Report: Mode A or B by the policy; Mode B if unknown at GATE I** | Graded prose carries the Honor Principle risk; B→A is reversible | Mode A without permission |
| D12 | ECC configuration for this repo | **SessionStart context off; main model Opus; result-checker pinned to Opus; use tdd-workflow, python-reviewer, docs-lookup; avoid refactor-cleaner, doc-updater, article-writing, astra-review, multi-*, teams (§6)** | Injected v1 memories and cleanup agents are the main ways ECC could hurt this repo | Defaults: possible Haiku subagents, stale injected context, cleanup of "dead" code |
| D13 | Pages | **≥ 6 before references, ≤ 8 in total** | Meets either reading | — |
| D14 | The earlier iteration in the report | **One or two sentences on its lessons; no v1 numbers** | Legitimate "unexpected behavior" material | Silence |
| D15 | GitHub | **Two private repos under IsaiahChoi:** `engs104-neutrality-v1` (archive) and `engs104-neutrality-v2` (working) | v1 has no remote today; laptop failure would lose both | One repo with both histories |

---

## 3. S0 — Pre-flight (you, tonight, ~45 minutes)

Run in Terminal. Stop at any unexpected output.

```bash
# 0. v1: nothing running, tree clean
cd ~/Desktop/engs104-neutrality-kit
git status --short                                   # expect no output
pgrep -fl "run_rq|gurobi" || echo "no runs active"
claude agents                                        # expect no background session here

# 1. Freeze v1 and back it up off this Mac
git tag v1-final
#    Create an EMPTY PRIVATE repo on GitHub: IsaiahChoi/engs104-neutrality-v1. Then:
git remote add origin git@github.com:IsaiahChoi/engs104-neutrality-v1.git   # or the https URL GitHub shows
git push -u origin main --tags
cd ~/Desktop && mv engs104-neutrality-kit engs104-neutrality-v1             # v1 is read-only from now on

# 2. Unpack v2 somewhere iCloud doesn't sync
mkdir -p ~/code && cd ~/code
unzip -q ~/Downloads/engs104-neutrality-v2.zip && cd engs104-neutrality-v2

# 3. Data from v1 (never re-downloaded), then verify every file against the committed manifest
cp -Rp ~/Desktop/engs104-neutrality-v1/data/raw data/raw
cp -Rp ~/Desktop/engs104-neutrality-v1/data/processed data/processed
find data -name .DS_Store -delete                    # Finder files would break the hash test
python3 - <<'EOF'
import hashlib, json, pathlib
m = json.load(open("data/MANIFEST_data.json"))["raw_sha256"]
raw = pathlib.Path("data/raw")
disk = {str(p.relative_to(raw)) for p in raw.rglob("*") if p.is_file()}
bad = [f for f in m if f in disk and hashlib.sha256((raw / f).read_bytes()).hexdigest() != m[f]]
print("manifest", len(m), "on disk", len(disk), "missing/extra", sorted(set(m) ^ disk)[:5], "mismatched", bad[:5])
EOF
#    expect: manifest 507 on disk 507 missing/extra [] mismatched []

# 4. Environment, first commit, private remote
conda deactivate 2>/dev/null || true
uv sync
make check-license                                   # expect OK (academic license active)
git init -b main && git add -A && git commit -qm "v2 start: kept core from v1 05468f2 (tag v1-final) + v2 docs"
git tag v2-start
#    Create an EMPTY PRIVATE repo: IsaiahChoi/engs104-neutrality-v2. Then:
git remote add origin git@github.com:IsaiahChoi/engs104-neutrality-v2.git
git push -u origin main --tags

# 5. Machine
chmod 600 ~/gurobi.lic && ls -l ~/gurobi.lic         # expect -rw-------
pmset -g batt | head -1                              # expect "AC Power"
pmset -g | grep -i lowpowermode                      # expect 0

# 6. ECC: check the global settings this repo can't see
grep -n '"model"\|SUBAGENT_MODEL\|EFFORT_LEVEL\|AUTOCOMPACT' ~/.claude/settings.json
#    If CLAUDE_CODE_SUBAGENT_MODEL is set to haiku, raise it to sonnet or remove it there:
#    the result-checker is pinned to opus in its frontmatter, but don't rely on precedence.

# 7. Launch
caffeinate -dims claude --permission-mode acceptEdits
#    In the session: /model opus  →  /hooks (glance: anything that blocks writing .md/.csv files
#    or running make?)  →  Shift+Tab to auto mode  →  paste S1
```

Before you sleep, send the email in §5.1.

---

## 4. Claude Code sessions

**Rules for every session:**
- Start fresh (`/clear` or a new launch); one session per repo.
- Long runs go through `make` in the background with logs.
- After a usage limit, resume with "Your limit reset. Resume from PROGRESS.md."
- The agent appends to PROGRESS.md before stopping and before any long run.
- The agent never pushes or tags.

**After each session, you check:**
- `git status --short` is clean.
- `git log --oneline -5` matches the report.
- The newest file in `results/checks/` has the verdict the report claims.
- Two numbers from the report match their result files.
- Then `git push`.

### S1 (+ S2) — Verify, port, build the foundations; then the pilot and continuous experiments (tonight)

```text
Fresh session S1 (verify the kept core, port v1 infrastructure, build the v2 foundations), continuing into S2 if CHECK CORE passes. Read, in order: CLAUDE.md; docs/RUNBOOK.md §0, §4 (S1 and S2), and §6; docs/DESIGN.md (all of it); docs/CHECKS.md (CORE and CONT); docs/MIGRATION.md; reference/v1/README.md; PROGRESS.md. reference/v1/ is read-only source to port from; never import from it.

0. Audit (read-only). Confirm `echo $ECC_SESSION_START_CONTEXT` prints "off". List the hooks active in this session that fire on Write, Edit, or Bash (from the installed ECC plugin's hooks configuration), and say whether any would block or rewrite files under results/, proposal/, report/, or docs/, or block background `make` runs. If one would, stop and tell Isaiah which ECC_DISABLED_HOOKS entry to add. Confirm the tree is clean at tag v2-start and `make check-license` exits 0.
1. Verify the kept core. Write tools/verify_data.py (MIGRATION §3 item 2); run `make data-verify`, `make risk-verify`, and `make test`. Record counts and results in PROGRESS.md.
2. Small fixes: MIGRATION §3 items 1 and 3. Log each in PROGRESS.md.
3. Port from reference/v1, with tests (DESIGN §12): experiments/common.py without the freeze guard and the λ book; the sweep machinery with the swept-cap shadow-price regression test (CHECKS K12); subsample and restricted; the envelope self-check. Use the tdd-workflow skill.
4. Build the v2 foundations (DESIGN §3, §5, §6, §9), writing each test first against the closed form or the theory (tdd-workflow):
   - P-RB by root-finding λ on the kept QP, plus the Clarabel QCQP cross-check;
   - λ*; P-MI objective scaling, incumbent V = max(incumbent, polished), and both relaxation duals with failed relaxations recorded, not fatal;
   - the alpha decomposition, φ, and normalization; elasticities; the closed-form equality-case predictor;
   - certified slope intervals; Work recording and WorkLimit support (confirm both with docs-lookup or docs.gurobi.com);
   - the independent feasibility checker extended to P-RB and P-MI.
   Tests cover CHECKS K4–K13. Runners refuse a dirty tree.
5. tools/spec_check.py (DESIGN §11.7). Scaffolds with no prose: proposal/proposal.tex (six headings, each with its `% SPEC-ELEMENT n` marker, and a bibliography); report/main.tex (IEEEtran conference; DESIGN §11.1 sections; `\label{refs:start}` before the bibliography); report/refs.bib (DESIGN §13 entries, each `% verified: no`); src/figures/make_all.py, which also writes report/numbers.tex.
6. PLAN.md for v2 from RUNBOOK §1 and §4 (CHECKs; Isaiah-only GATEs C, DESIGN, I, R, FINAL). A fresh-context review of the new code by the python-reviewer agent, saved to results/checks/code_review_S1_<UTC stamp>.md: fix clear bugs and list the rest in PROGRESS.md.
7. CHECK CORE with the result-checker subagent.
8. If CHECK CORE is PASS: append the S1 entry to PROGRESS.md, commit, and continue with S2 below in this session. If it is FAIL after 3 rounds, or BLOCKED, stop and report.
```

### S2 — Design pilot and continuous experiments (runs inside S1 tonight; paste separately only if S1 stopped)

```text
Session S2 (design pilot and continuous experiments). If this is a fresh session, first read CLAUDE.md, docs/RUNBOOK.md §4 (S2), docs/DESIGN.md §3–§10, docs/CHECKS.md (CONT), and the last entries of PROGRESS.md.

1. Pilot items P1–P7 exactly as DESIGN §8, with outputs under results/pilot/<UTC stamp>/ and RUN_LOG status "pilot". If P1 or P4 fails, finish the other pilot items, then stop and report.
2. Record the P-RB settings (root tolerance, λ bracket) and s_obj in experiments/configs/continuous.yaml. Draft experiments/configs/integer.yaml and numerics.yaml from the pilot rules, marked "proposed, pending GATE DESIGN".
3. Run C1, C2, C3 (DESIGN §7), up to 4 workers, through `make c1 c2 c3` in the background.
4. Draft Figs. 1–3 and the C3 summary (DESIGN §10), with "preliminary" in the file names until GATE C.
5. Write proposal/FACTS.md: each fact Isaiah may use, one per line, with its source file and sha256. Include: data span and universe-size range; D12; the C1/C2 headlines (largest elasticities, retained fractions, the range of φ, closed-form versus numerical agreement); the proposed K grids and I1 constraints with the rule behind each; solver versions; the test count; and the refs.bib entries for Lee & Stefek, Ceria et al., Stubbs & Vandenbussche, Clarke et al., Frangioni & Gentile, Günlük & Linderoth, Geoffrion & Nauss, and Wolsey (1981), copied exactly.
6. CHECK CONT with the result-checker.

Stop at GATE C with: the pilot table; the proposed I1/N1 parameters and constraints with the rule that produced each; the C1/C2 headlines with their files; the CHECK CONT verdict; the S3 run-time projection.
```

### S3 — Integer sensitivity, formulations, numerics (Friday evening, after GATE DESIGN)

```text
Fresh session S3 (integer sensitivity, formulations, numerics). Precondition: Isaiah's GATE DESIGN note in PROGRESS.md. Read: CLAUDE.md; docs/RUNBOOK.md §4 (S3); docs/DESIGN.md §3 and §6–§10; docs/CHECKS.md (INT); the last entries of PROGRESS.md.

1. Finalize experiments/configs/integer.yaml and numerics.yaml exactly as the GATE DESIGN note says, removing "proposed". If the note changes DESIGN.md content, propose that edit and wait for approval. Commit.
2. Run I1, I2, N1 (with the presolve-off robustness), and N2 (DESIGN §7). Up to 4 workers; Work is the effort metric. If pilot P5 found WorkLimit unavailable, run N1 strictly alone under TimeLimit, and before each N1 block record `pmset -g batt` (must show AC Power), `pmset -g | grep lowpowermode` (must be 0), a held caffeinate assertion (`pmset -g assertions`), and the 1-minute load average.
3. Analysis per DESIGN §7: estimator errors with n, certified intervals, the non-binding breakdown, the convex baseline; root gaps and Work; the numerics tables.
4. Figs. 4–5 and Tables II–III; finalize Figs. 1–3 (drop "preliminary").
5. CHECK INT with the result-checker. If K22 or K23 is BLOCKED, stop and report; don't work around it.

Stop at GATE I with: the headline numbers with n and source files, the CHECK INT verdict, anything surprising (with the file that shows it), and open questions for the Discussion.
```

### S4 — Report build (Monday 10/26, after GATE I)

```text
Fresh session S4 (report build). Read: CLAUDE.md; docs/RUNBOOK.md §4 (S4), §7, §8; docs/DESIGN.md §9–§13; docs/CHECKS.md (REPORT); the last entries of PROGRESS.md, especially Isaiah's GATE I note, which sets the writing mode.

1. Writing mode per DESIGN §11.6 (default B).
2. Build report/main.tex per DESIGN §11: sections and page budget, the content requirements in §11.3, A1–A9, the figures and tables in §10, the disclosures in §11.5. Mode A: draft II–IV and red outlines elsewhere. Mode B: scaffold plus red claim→evidence outlines everywhere, captions included. The Discussion outline names every item in DESIGN §11.4.
3. Generate numbers.tex: every number a macro, each with a comment naming its source file and sha256; design constants are macros too, read from the configs.
4. `make figures && make report`; tools/spec_check.py --target report --mode draft, and --target proposal --mode final against the submitted proposal.
5. CHECK REPORT (K30–K39 in draft mode) with the result-checker; then the cold-reader on report/main.pdf, saved to results/checks/cold_read_<UTC stamp>.md.

Stop at GATE R with: the spec_check table, the CHECK verdict, the cold-read top five, the page count with per-section estimates against DESIGN §11.1, and Isaiah's open items by section with the target dates from RUNBOOK §1.
```

### S5 — Integration pass (repeat after each round of your writing)

```text
Fresh session S5 (integration pass; repeatable). Read: CLAUDE.md; docs/RUNBOOK.md §4 (S5) and §8; docs/DESIGN.md §10–§13; docs/CHECKS.md (REPORT); the last entries of PROGRESS.md (Isaiah's latest note says "draft" or "final").

Isaiah has written or revised sections. Do not change any sentence, caption, heading, or equation he wrote. Allowed: regenerating numbers.tex, figures, and tables; fixing mechanical LaTeX build errors, recording each with its diff in PROGRESS.md. Nothing else in his text.
1. `make figures && make report`; tools/spec_check.py in the mode Isaiah stated.
2. CHECK REPORT (K30–K40) in that mode with the result-checker.
3. List every numeric literal in Isaiah's prose that is not a macro, with the macro that should replace it (he makes the change).
4. Claims table: every result claim in the Abstract, Introduction, Discussion, and Conclusion matched to its macro, figure, table, or result file; list each mismatch or unsupported claim.
5. The cold-reader on the new PDF.

Stop with one issue list ordered by severity (blocking, should-fix, optional), each with its file and line.
```

### S6 — Final build and submission package (Monday 11/16, after FINAL)

```text
Fresh session S6 (final build and submission package). Precondition: Isaiah's FINAL note in PROGRESS.md. Read: CLAUDE.md; docs/RUNBOOK.md §4 (S6) and §8; docs/DESIGN.md §11; docs/CHECKS.md (REPORT); the last entries of PROGRESS.md.
1. Clean-checkout build: clone the repo into a temporary directory; supply only the gitignored inputs that `make figures` needs (list each, and copy or link it from the working repo); run make test, make figures, and make report there. Confirm the figures and numbers.tex are byte-identical to the working repo's, and that the two PDFs have the same page count and the same extracted text.
2. tools/spec_check.py --target report --mode final and --target proposal --mode final; CHECK REPORT in final mode.
3. Walk the compliance matrix in RUNBOOK §8: for every row, record the evidence (file and section, or check output). Any row without evidence is blocking.
4. Write SUBMISSION.md: commit hash; PDF sha256; page count, total and before references; the build command; the headline results with their source files; the disclosure checklist with the section where each appears; the compliance-matrix result.
5. Commit and stop. Do not tag or push.
```

**After S6:** read SUBMISSION.md; `git tag report-submitted && git push origin main --tags`; upload the PDF to Canvas.

### GATE notes (append to PROGRESS.md)

```text
## <date> — Isaiah: GATE C
- Read S2. Pilot: P1 <pass/fail>, P4 <pass/fail>. Continuous results look sound: YES / concerns: <...>.
- Proposed I1/N1 parameters: noted; finalized at GATE DESIGN.

## <date> — Isaiah: GATE DESIGN
- Discussed the MIQP design with <instructor> on <date>. Feedback: <summary>.
- integer.yaml / numerics.yaml: APPROVED AS PROPOSED / changes: <exact changes>.
- Proposal submitted on <date>. Run S3: YES.

## <date> — Isaiah: GATE I
- Read S3. Headlines noted. AI-use policy: <answer, source, date>. Writing mode: A / B.

## <date> — Isaiah: GATE R
- Read the build. Open items: <list>.

## <date> — Isaiah: draft | final
- Sections changed since the last pass: <list>.

## <date> — Isaiah: FINAL
- All my sections written; no TODOs; references verified; AI-use paragraph verified against docs/AI_USE.md. Run S6.
```

---

---

## 5. Human work packages

### 5.1 Instructor contact

**Email both instructors tonight:**

```text
Subject: ENGS 104 project: AI-use question before Thursday's proposal

Dear Prof. Ferguson and Prof. Fügenschuh,

My individual project studies the costs (shadow prices) of neutrality constraints in market-neutral portfolio construction. The continuous mandate is a convex program with a risk budget; an MIQP with cardinality and minimum-position constraints (big-M versus perspective formulations) tests how well continuous sensitivity tools hold up once integer constraints enter.

I'm using an AI coding agent (Claude Code) to write and run the code under specifications and acceptance checks I set, with a separate AI checker recomputing the results independently. I'll describe this in the proposal and the report. Before I submit on Thursday, I want to confirm this is within course policy:

1. Is AI-written code acceptable if it is disclosed?
2. May an AI draft any report prose (for example, the problem-setting or results sections) that I then revise, or should all prose be my own?
3. Do references count toward the 6–8 pages, and is a supplementary appendix allowed?

I'd also value a few minutes on the integer-programming design, and plan to come to office hours on Wednesday.

Thank you,
Isaiah
```

**Wednesday office hours (Fügenschuh), about 10 minutes:**
1. A two-minute summary.
2. The AI-use question, if still unanswered.
3. λ\* as the risk budget's multiplier versus an MISOCP with the risk row.
4. K set as fractions of the continuous support size.
5. The I1 constraint-selection rule and the certified-interval approach.
6. Work and WorkLimit as the effort measure.
7. Whether he'd add a fourth estimator, such as a Lagrangian bound on the cardinality constraint.
8. Whether references count toward the pages.

**Tuesday office hours (Ferguson, optional).** The continuous side:
- the risk-budget/mean-variance duality;
- the alignment lemma and √(1 − φ);
- whether the analysis component is sufficient.

**Friday discussion.** Record the feedback in the GATE DESIGN note.

### 5.2 Proposal (due Thu 10/22; written entirely by you)

Write from `proposal/FACTS.md` and your own understanding, inside the S1 scaffold (keep each `% SPEC-ELEMENT n` marker above its section). Two pages at most.

| Element | Words | Claims to make, in your words |
|---|---|---|
| 1. Decision problem and motivation | 150–180 | The pod and its platform; the mandate and why it exists; every constraint costs alpha; mandate design and risk budgeting rely on reading shadow prices as constraint costs, and that reading may break once cardinality and minimum-position rules enter |
| 2. Formulation | 200 + model | Variables; P-RB's objective and constraints; the MIQP additions; assumptions (single period, w₀ = 0, factor covariance, linear costs, alpha as an input, 3% risk budget); problem classes (convex QCQP/SOCP; convex MIQP; MISOCP) |
| 3. Approach | 120–150 | CVXPY with Gurobi and Clarabel; duality and KKT closed forms; the alpha decomposition; parametric sweeps; big-M versus perspective; three estimators versus certified re-solves; scaling; independent checks |
| 4. Expected output and analysis | 160–200 | Cost curves and elasticities; the √(1 − φ) prediction against numerical results; estimator errors with n; root gaps and effort by formulation. Conclusions it can support, and ones it can't (no performance claims; one universe and period) |
| 5. Prior work | 180–220 | Lee–Stefek and Ceria et al. (alignment) → a closed form plus measurement under a realistic mandate; Stubbs–Vandenbussche (attribution through duals) → used in the convex case, its integer analog tested; Frangioni–Gentile and Günlük–Linderoth (perspective) → interaction with neutrality tightness; Geoffrion–Nauss and Wolsey (integer sensitivity theory) → quantified in a realistic instance |
| 6. Contribution | 90–120 | Not a new research result. A worked, measured account of when neutrality is expensive and why (with a testable closed form), and of how far continuous sensitivity tools drift once integrality enters a realistic mandate |
| Status and AI use | 60–90 | What exists as of 10/22 (the core pipeline and preliminary continuous results); that the MIQP design will be finalized after this discussion; how the work is done, accurately |

**Checklist:**
- It builds with `make proposal`.
- It is 1–2 pages.
- At least two references are discussed, not merely cited.
- Every number traces to FACTS.md.
- No TODO remains.
- You can explain every equation in it.

### 5.3 Derivations by hand (they feed Section III and the Q&A)

Work through DESIGN §9 A1–A9 on paper. Hints:

- **A1.** Write the Lagrangian of P-RB, keeping the risk row's multiplier μ. Stationarity is the mean-variance stationarity with λ = μ.
- **A2.** Use Aw = 0 to solve for ν; then the binding risk row gives μ.
- **A3.** Divide A* by the unconstrained value σ_m√(αᵀΣ⁻¹α), and compare with TC computed from w*.
- **A4.** Derive BᵀΣ⁻¹ from Woodbury. Then show Σ⁻¹α⊥ = D⁻¹α⊥, the cross term vanishes, and A2 with A = Bᵀ gives g = α⊥.
- **A5.** Envelope theorem; concavity of the perturbation function (Boyd & Vandenberghe §5.6); Slater's condition with w = 0.
- **A6.** One line: s ≥ w²/z ≥ w² for z ∈ (0, 1].
- **A7.** Solve the one-asset problem on b < ℓ and b ≥ ℓ separately. For the relaxations, minimize s over z ∈ [w/u, w/ℓ].
- **A8.** Monotonicity from feasible-set inclusion. The value function is a max over support patterns of concave functions. The interval endpoints follow from V ≤ U* ≤ B at each point.
- **A9.** Relative error = τ/m; the variance row has m ≈ 7.5e-5.

### 5.4 Writing plan

| Section | Pages | Mode A | Mode B | Target |
|---|---|---|---|---|
| Abstract | 0.3 | You | You | 11/10 |
| I. Introduction | 0.8 | You | You | 11/4 |
| II. Problem Setting | 1.1 | Agent drafts; you revise | You | 10/30 (B) |
| III. Solution Approach and Analysis | 1.3 | Agent drafts; you revise and check against your derivations | You, from §5.3 | 11/4 (B) |
| IV. Results | 2.5 | Agent drafts; you revise | You, from the tables and macros | 11/6 (B) |
| V. Discussion | 1.0 | You | You | 11/8 |
| VI. Conclusion | 0.25 | You | You | 11/10 |
| Disclosures and AI use | 0.2 | You (from the AI_USE.md draft) | You | 11/10 |

### 5.5 Verification chores (before FINAL)

- Verify every reference (authors, title, venue, volume, issue, pages, year) and flip its `% verified` comment.
- Fill `docs/AI_USE.md` with the instructors' policy answer, its source, and its date.
- Check that the proposal's and the report's descriptions of the workflow match `docs/AI_USE.md`.
- Check that no sentence or figure in the report uses a v1 number.

---

---

## 6. ECC in this project

ECC is installed globally, so it shapes every session in this repo. Configure it once (S0 step 6 and `.claude/settings.json`), then use the parts that strengthen this workflow.

**Use:**
- **`tdd-workflow` skill** (S1, S3). For numerical code, "test first" means writing the test against a closed form or a theorem before implementing: A2–A4 closed forms, A7 toy, monotonicity and concavity of value functions, scale invariance. That is what CHECKS CORE verifies.
- **`python-reviewer` agent** (end of S1 and S3). A fresh-context code review, advisory, saved under `results/checks/`. It complements the result-checker: one reads the code, the other recomputes the numbers.
- **`docs-lookup` agent.** Gurobi 13 `WorkLimit`/`Work`, `QCPDual`, `ObjBound`; CVXPY and Clarabel options. Settings allow WebFetch on those documentation domains only.
- **Strategic compaction and the pre-compact hook** for the long S1+S2 session. CLAUDE.md requires writing state to PROGRESS.md before long runs, so a compaction loses nothing. Run `/context-budget` if the session slows.
- **GateGuard** (destructive-command gating). It agrees with this repo's rules.
- **Optional:** `agentshield scan --path .` once after S1, to confirm no credential or license content is in the repo or agent files.

**Turn off or avoid, and why:**
- **SessionStart context injection: off.** Project settings set `ECC_SESSION_START_CONTEXT=off`. PROGRESS.md is the only state the result-checker can audit, and summaries or instincts learned during v1 describe a different project (frozen hypotheses, rerun amendments). S1 step 0 confirms the variable reached the session. If it didn't, launch with `ECC_SESSION_START_CONTEXT=off caffeinate -dims claude …`.
- **Cost warnings: off** (`ECC_CONTEXT_MONITOR_COST_WARNINGS=off`; subscription use).
- **`refactor-cleaner`** would delete "dead" code such as the unused oracle alpha or `reference/`.
- **`doc-updater`** would edit DESIGN or README.
- **`article-writing` and content skills** are not for graded prose.
- **`/astra-review`** sends code to a third-party model.
- **`multi-*`** commands need an extra runtime.
- **Agent Teams**: one session per repo, and the token cost is high.
- **ECC's token-optimization defaults** (`model: sonnet`, subagents on Haiku) don't fit this repo:
  - Use Opus for S1–S4 (numerical reasoning, derivations, verification); Sonnet is fine for S5 integration passes.
  - The result-checker's frontmatter pins `model: opus`. If your global settings force subagents to Haiku, override that there (S0 step 6).
- **ECC rules, if installed globally** (for example, 80% coverage or commit-message formats). CLAUDE.md makes the project's rules win: tests target CHECKS, not coverage.

**If a hook gets in the way:**
- S1 step 0 audits the active hooks and stops if one would block writing results, proposal, report, or docs files, or block background `make` runs.
- To disable one hook by ID, add `"ECC_DISABLED_HOOKS": "<id>,<id>"` to the `env` block of `.claude/settings.json`. Edit it yourself; the agent is denied edits under `.claude/`. Keep the hook profile at `standard`.

---

## 7. Course themes: where each one genuinely enters

The integration is mostly framing and derivations. The binding constraint is 8 pages, and forced connections cost credibility with instructors who know the material.

| Course topic (week) | Genuine connection | Where |
|---|---|---|
| LP forms, simplex (W1) | Absolute values and costs made linear through w⁺/w⁻ and epigraph variables | II |
| LP duality, shadow prices, sensitivity (W1) | Q1: duals as constraint costs; elasticities; attribution | III, IV-A |
| Dual simplex, reoptimization (W1) | Re-solve slopes as post-optimality reoptimization | III |
| Zero-sum games (W2) | No genuine link; not used | — |
| MIP, big-M, relaxations, B&B (W2) | Q2–Q3: cardinality and minimum position; root gaps; relaxation duals | II, III, IV-B, IV-C |
| Cutting planes (W3) | The perspective reformulation as the closure of perspective cuts | III (A6) |
| Lagrangian relaxation; integer duality gaps (W3) | λ\* is a Lagrangian relaxation of the risk row (zero gap in the convex case); why duals fail once integers enter (Wolsey; Geoffrion–Nauss) | II, III (A8), V |
| Decomposition; distributed optimization (W4, W8) | A platform could coordinate pods by pricing exposure; the duals are those prices | V or VI |
| Least squares, estimation (W5, W9) | The risk model is OLS; α⊥ is a weighted least-squares residual | II, III (A4) |
| Convex sets and functions (W5) | The ellipsoidal risk set; Σ ≻ 0; uniqueness; convexity of the perspective | II, III |
| QP and QCQP; multiobjective, scalarization, Pareto (W6) | P-RB is a QCQP; the risk budget is an ε-constraint and λ its scalarization weight (A1); cost curves are trade-off curves | II, III, IV-A |
| SOCP, conic, robust (W6) | The risk budget as an SOC; the perspective MISOCP; robust alpha as an extension | II, VI |
| Duality I: KKT, constraint qualifications (W7) | KKT closed forms (A2); Slater with w = 0 | III |
| Duality II: shadow prices, envelope theorem, value functions (W7) | The project's center: a concave value function (convex case) versus a piecewise, discontinuous one (MIQP) | III, IV, Fig. 4 |
| Solver tools (W7 TA session) | Gurobi, Clarabel, SCS; tolerances; N2 | III, IV-C |
| Interior-point methods (W8) | Clarabel's primal–dual method for the QCQP cross-check; Gurobi barrier for the perspective relaxations; tolerance semantics. Contrast: dual simplex for exact active sets | III |
| ADMM (W8) | SCS in N2(b) is ADMM-based | IV-C |
| Optimal control, MPC (W9) | Multi-period rebalancing with trading costs as an extension | VI |
| Stochastic optimization, Monte Carlo (W4) | Not used after dropping the Monte Carlo; say nothing | — |
| Population games (W9) | At most a clause: crowding across pods | VI (optional) |

**Learning objectives:**
- LO1 (transcribe and classify): II, the problem classes.
- LO2 (apply solvers): III, which algorithm solved what.
- LO3 (connections to estimation and control): the risk model, the α⊥ regression, the MPC extension.
- LO4 (derive duals and interpret them as penalties, shadow prices, and sensitivity): A1–A5 and A8. This is the project's center.

---

---

## 8. Specification compliance matrix (S6 walks it)

| ID | Requirement (source) | Satisfied by | Verified by |
|---|---|---|---|
| G1 | Identify a decision-making problem (handout) | The pod under a platform mandate; I, II | Cold read; GATE R |
| G2 | Encode it as an optimization problem | P-RB, P-MI; II | K37 |
| G3 | Design or implement a solver or solution approach | Formulations, λ\* by duality, three estimators, certified intervals, scaling; III | CHECK INT; K37 |
| G4 | Analyze properties of the program and solution | A1–A9; III | K4–K10, K24; GATE R |
| G5 | Analysis, computational, and discussion components | III, IV, V | K37 |
| G6 | A problem outside the lectures; more than reproduction | Mandate application; contribution in I | GATE R |
| G7 | A project structure (types 1–3) | Type 2 with type-1 elements, stated in the proposal | Read |
| P0 | Proposal: LaTeX, 1–2 pages, due Week 6, discussed with an instructor | proposal/; 10/22; 10/23 | PR-1, PR-2; GATE DESIGN note |
| P1–P6 | The six proposal elements | §5.2 | PR-3, PR-4; read |
| R0 | 6–8 pages, IEEE conference format | DESIGN §11.2 | RP-2, RP-4–RP-6 |
| R1 | Self-contained for next year's student | DESIGN §11.3 definitions; cold read | K40; GATE R |
| R2–R8 | Abstract, Introduction, Problem Setting, Solution Approach, Results (setup, instances, criteria), Discussion (modeling choices, limitations, trade-offs, unexpected behavior), Conclusion (extensions) | DESIGN §11.1–§11.4 | RP-3, K35, K37 |
| R9 | Formulation, method, evidence, and conclusions connected | Claims table | K34 |
| C1–C4 | Learning objectives 1–4 | §7 | K37; read |
| C5 | Academic Honor Principle; AI-use disclosure | Email; AI_USE.md; writing mode; acknowledgment | GATE I; RP-9 |
| C6 | The project's own disclosures | DESIGN §11.5 | K36 |

Out of scope by request: the presentation, its Q&A, audience participation, presentation sign-up.

---

---

## 9. Risks and contingencies

| Risk | Where it shows | Response |
|---|---|---|
| Root-finding makes C2 slow (about 2,000 points × 10–15 QP solves) | S2 (P1 projection) | Warm-started brackets and 4 workers. If the projection exceeds about 8 h, run C2 on the 8 D12 dates 2008-10, 2011-08, 2015-08, 2017-12, 2020-03, 2022-06, 2023-03, 2025-04 and say so; decide at GATE C |
| Root-found QP and Clarabel QCQP disagree (P1) | S2 | Investigate tolerances; Clarabel as primary for P-RB if needed; disclose |
| Perspective relaxations return SUBOPTIMAL | S3 | Recorded and counted, never fatal; that estimator's n shrinks; reported |
| Formulations disagree even at O(1) scale (P4) | S2 | S2 stops. Tighten tolerances or rescale further, and disclose what was done |
| WorkLimit unavailable | S1/S2 (P5) | TimeLimit with strict-alone N1 runs (S3 handles it) |
| An ECC hook blocks file writes or make runs | S1 step 0 | S1 stops; you add the hook ID to ECC_DISABLED_HOOKS |
| Usage limit mid-chain | S1/S2 | `make` runs continue; resume from PROGRESS.md |
| Data copy doesn't verify | S0 step 3 | Unzip `data_raw_backup.zip` into `data/` instead (same hashes, verified at extraction), then rebuild processed data offline |
| No I1 constraint binds | S2 (P6) | Take the P6 table to office hours |
| S1+S2 not finished by Monday | Mon | Write the proposal without preliminary numbers; it is a proposal |
| An instructor suggests MIQP changes | Wed–Fri | They go into GATE DESIGN before S3 (D9) |
| The policy forbids AI-drafted prose | Any time | Mode B; about 10–15 more hours; start Section II in the week of 10/26 |
| The policy limits AI-written code | Any time | Stop agent work, meet an instructor, disclose |
| No policy answer arrives | GATE I | Mode B, because it is reversible |
| Over or under the page limits | S4, S5 | The DESIGN §11.1 cut order; substance, not layout, if short |
| HW3 (10/30) and HW4 (11/13) compete for time | Weeks 7–9 | Derivations before HW3; the draft finished on 11/12 |

## 10. Going back to v1, if you ever want to

`~/Desktop/engs104-neutrality-v1` (tag `v1-final`, pushed to `IsaiahChoi/engs104-neutrality-v1`) is untouched by everything above. The first runbook's continue-v1 plan still applies there.
