# PROGRESS (v2)

Append-only. The v1 log is in the v1 repository (tag `v1-final`).

## 2026-10-18 — v2 extracted (Claude in chat); Isaiah: decisions
- Fresh repository extracted from v1 commit 05468f2: kept core plus v2 docs; see docs/MIGRATION.md. Raw data verified against the manifest at extraction.
- Decisions (docs/RUNBOOK.md §2): D1–D15 as recommended. [Isaiah: edit this line if you chose differently.]
- Writing mode: PENDING the AI-use policy. Mode B until a GATE note says otherwise.

## Decisions needed
- (none yet)

## 2026-10-18 — S1 (in progress; Claude Code, Opus 5.5)
State checkpoint (written mid-session so it survives compaction; the final S1 entry follows).
- Step 0 audit: `echo $ECC_SESSION_START_CONTEXT` → `off`. Tree clean at d835b83 = tag v2-start (`git log --decorate`; `git tag` is denied by settings). `make check-license` exit 0 (gurobipy 13.0.3, full license). ECC 2.2.3 hooks firing on Write/Edit/Bash: pre:bash:dispatcher (block-no-verify, auto-tmux-dev [npm/pnpm/yarn/bun dev only], gateguard-fact-force), pre:write:doc-file-warning (warn only, exit 0), pre:edit-write:suggest-compact (advisory), pre:observe (async, logs to ~/.claude), pre:governance-capture (off unless ECC_GOVERNANCE_CAPTURE=1), pre:config-protection (blocks only linter/formatter configs, not pyproject.toml), pre:edit-write:gateguard-fact-force, pre:hookify-runtime (no project rules), PostToolUse dispatchers (quality-gate runs `ruff format --check` only, since ECC_QUALITY_GATE_FIX is unset; design-quality-check: frontend files only; accumulator/console-warn: JS/TS), Stop hooks (format-typecheck: JS/TS only). None rewrites files under results/, proposal/, report/, docs/; none blocks background `make` (GateGuard's destructive classifier returns nothing for `make c1 > log 2>&1`, `nohup make … &`, `mv … results/scratch/trash/`, `git add/commit`). GateGuard denies the FIRST Edit/Write of each file once (fact-forcing questions; the retry passes; subagents are gated only for sensitive/hard-linked targets) and the first routine Bash command per session. That is friction, not a block, so no ECC_DISABLED_HOOKS entry is needed. GateGuard state lives in ~/.gateguard, not the repo.
- Note for Isaiah: the repo is at ~/Desktop/engs_104_final_project/engs104-neutrality-v2, not ~/code as RUNBOOK §3 step 2 suggests (Desktop may be iCloud-synced).
- Step 1: tools/verify_data.py written (test first: tests/test_verify_data.py, RED at import → GREEN 3/3). `make data-verify` exit 0: raw files 507 in manifest / 507 on disk, missing 0, extra 0, mismatched 0; build_meta raw hashes = manifest (507); build_meta panel hash = manifest; panel content hash recomputed = 1c331f6590b35997… = manifest; build_meta and risk meta fields equal except timestamps; both record git_commit "unknown" (S0 offline rebuild ran before `git init`; RUN_LOG rows 3–4 say so) versus v1's 44ea3ba in the manifests, printed as a provenance NOTE and not counted as a content difference. Rebuild-identical and raw-hash pytest: 2 passed. `make risk-verify`: 2 passed. Baseline `make test` at v2-start: 115 passed (17.9 s).
- Step 2: MIGRATION §3 item 1, tools/page_count.py (kept core) now exits 1 out of range. Reason: a page-limit violation must fail `make proposal/report`. Test first: tests/test_page_count.py RED (3 out-of-range cases exited 0) → GREEN 5/5. Item 3, experiments/configs/base_mandate.yaml (kept core): added `risk_budget` {target_annual_vol 0.03, lambda_min 1e-6, root_rtol 1e-10} as plain decimals (PyYAML reads `1e-6` as text) and marked `risk_aversion` fields unused in v2. Reason: the P-RB settings of DESIGN §6. Test: tests/test_risk_budget.py::test_risk_budget_config.
- Kept-core change, src/opt/feasibility.py: additive only (new risk_violation, integer_violations, prb_violations, pmi_violations; constraint_values and violations unchanged). Reason: extend the independent checker to P-RB and P-MI (CHECKS K11). It still imports no optimizer code.
- New: src/opt/risk_budget.py (P-RB root-found QP + Clarabel cross-check), src/alpha/decompose.py, src/opt/closed_form.py, src/opt/sensitivity.py with tests test_risk_budget (K4 on 2008-10, 2017-12, 2020-03), test_decompose (K5), test_closed_form (K6), test_sensitivity (K7 on 2017-12, 2020-03 at δ = 1%): all RED at import, then GREEN.
- Finding (numerics; affects DESIGN §6 wording): Clarabel on the QCQP written as variance/σ_m² ≤ 1 (CVXPY converts it to a rotated cone) never reports OPTIMAL at tolerances ≤ 1e-9 on real dates (2017-12, 2008-10); at 1e-8 its weights are off by ‖Δw‖₁/‖w‖₁ = 8.1e-5 (K4 allows 1e-5). The same set written as a second-order cone ‖(L_F'y, √d∘w)‖/σ_m ≤ 1 agrees with the root-found QP on 3 dates to ‖Δw‖₁/‖w‖₁ ≤ 2.9e-6, ΔA* ≤ 3.3e-10, Δλ ≤ 6.2e-8 at tolerance 1e-12, but Clarabel often reports AlmostSolved (CVXPY optimal_inaccurate) there. Implemented: the cross-check uses the SOC form at 1e-12, accepts optimal or optimal_inaccurate and records the status, and raises on anything else; the quadratic form stays available (risk_form="quadratic") for N2(b). See Decisions needed.
- Finding (K5 wording): α∥ := α − α⊥ makes the split exact by definition, but the floating-point sum α⊥ + α∥ is not bitwise α where α⊥_i and α∥_i nearly cancel (40–64 of ~470 names per date; error ≤ 104 ulp of the small α_i, below one ulp of max|α|). Bitwise equality would need more than 53 bits. The test asserts |α⊥ + α∥ − α| ≤ spacing(max component). See Decisions needed.
- TDD under CLAUDE.md precedence: each component's test is run RED before the code is written and GREEN after. No RED checkpoint commits (rule 6: a passing suite at every commit); coverage is not a target (tests target CHECKS).

## 2026-10-19 — S1 entry (Claude Code, Opus 5.5): kept core verified, v1 infrastructure ported, v2 foundations built
Commits since v2-start (d835b83): a5f1159 (foundations and ports), 5489a1e (spec_check, scaffolds, refs.bib, make_all, PLAN), c23289c (python-reviewer fixes, S1 core-verification runner), then the results/PROGRESS commit that follows this entry.

**Verification of the kept core (step 1).** `make data-verify`: 6/6 (507/507 raw files, 0 missing, 0 extra, 0 mismatched; panel content hash recomputed = manifest 1c331f6590b35997…; build_meta and risk meta equal the manifests except timestamps; git_commit differs only as provenance, see the checkpoint above); rebuild-identical + raw-hash tests 2 passed. `make risk-verify`: 2 passed. `make check-license`: exit 0. Test suite: 115 passed at v2-start → **201 passed** at c23289c (48.5 s; logs/test_s1_post_review_*.log). No pre-existing test was changed or removed (`git diff v2-start -- tests/` adds files only); `git diff v2-start -- reference/` is empty.

**Every kept-core change since v2-start, with its reason** (CLAUDE.md rule 14; the pre-existing tests pass unmodified):
- tools/page_count.py: exit 1 when the page count is out of range (MIGRATION §3 item 1), so a page-limit violation fails `make proposal/report`.
- experiments/configs/base_mandate.yaml: `risk_budget` block added (target 0.03, λ_min 1e-6, root rtol 1e-10; MIGRATION §3 item 3, DESIGN §6) and the v1 `risk_aversion` fields commented "unused in v2". The `mandate` block is unchanged.
- src/opt/feasibility.py: additive only. New `risk_violation`, `_cap_vector`, `integer_violations`, `prb_violations` (with optional per-factor `style_bounds` for single-style sweeps) and `pmi_violations`. Reason: extend the independent checker to P-RB and P-MI (CHECKS K11). `constraint_values` and `violations` are unchanged, and the module still imports nothing from the optimizer (tests enforce it).
- src/opt/miqp.py: additive only. `MIQPModel.solve(work_limit=None)` sets Gurobi WorkLimit; `MIQPResult` gains `work` and `root_bound` (defaulted); `_continuous` records Work; `_status_name` knows WORK_LIMIT. Reason: DESIGN §6 (record Work next to Runtime; WorkLimit support; root bound for N1).
- New files inside kept-core directories (no existing file changed): src/alpha/decompose.py; src/opt/{risk_budget,sensitivity,closed_form,integer,certified,toy}.py; src/figures/make_all.py.

**Work and WorkLimit (confirmed).** gurobipy 13.0.3: `GRB.Param.WorkLimit` exists (getParamInfo: float, default ∞, range [0, ∞)) and `GRB.WORK_LIMIT` = status 16. docs.gurobi.com (model attributes, Work) states that Work is deterministic: the same result every time for the same model, hardware, parameters and attributes; one work unit is roughly one second on one thread. Tested: WorkLimit stops a solve with status WORK_LIMIT, and two identical solves give identical Work, nodes and V (tests/test_integer.py).

**Ports (step 3), each with tests:**
- experiments/common.py: from v1 common, with no freeze guard and no λ book. Clean-tree refusal (untracked code counts; results/ does not), resume keyed on config, commit, status, arguments and a data fingerprint, write-once chunks, DONE, RUN_LOG rows updated in place under a lock, fail/supersede, latest_done.
- experiments/designs.py: month → rebalance date.
- experiments/instances.py: subsample by top-N 63-day ADV with stable ties; alpha restricted from the full universe; restricted; miqp_mandate.
- experiments/sweep.py: build, snapshot, apply_point and reset on P-RB; records before reset; C2 grids = DESIGN §7. **K12 regression re-created, with a negative control**: reading the duals after a reset is 3.0% off at θ = 0.025 on 2020-03.
- experiments/check_envelope.py: seeded FD self-check, with a corrupted-price negative control.

**Foundations (step 4), each test RED before its code:**
- P-RB: root-found λ (Brent on log λ, |vol/target − 1| ≤ 1e-10, warm start, slack flag at λ_min) plus a Clarabel cross-check.
- λ*.
- P-MI wrapper (src/opt/integer.py): s_obj, V, both relaxation duals with failures recorded, fixed-integer duals, Work and WorkLimit.
- Alpha decomposition, φ, and IR normalization.
- Elasticities and FD slopes.
- Closed-form equality case, plus the A7 toy closed forms and certified intervals (NaN refused).
- Checker extension.
- Runners refuse a dirty tree.

Tests cover K4–K13.

**Scaffolds and tools (step 5).**
- tools/spec_check.py covers PR-1–5 and RP-1–11. The static checks pass on the scaffolds. PR-1/2/4 and RP-1/4 FAIL until the PDFs are built and Isaiah adds citations: expected, see Decisions needed.
- proposal/proposal.tex: six headings with SPEC-ELEMENT 1–6 and a bibliography; no prose.
- report/main.tex: IEEEtran conference, DESIGN §11.1 sections, `\label{refs:start}` before the bibliography; Mode B, no prose.
- report/refs.bib: the 19 DESIGN §13 entries, fields only as DESIGN states them, each `% verified: no`.
- src/figures/make_all.py writes report/numbers.tex: 14 design-constant macros, each with source file and sha256, byte-identical on regeneration.
- PLAN.md for v2 (step 6).

**S1 core-verification run** (evidence for CHECK CORE; nothing here is reported): results/core/run_20261019T003108Z, commit c23289c, RUN_LOG row "ok", DONE present. The runner's own summary (the result-checker recomputes independently):
- K4: ‖Δw‖₁/‖w‖₁ ≤ 4.4e-7, |ΔA*| ≤ 1.2e-10, |Δλ| ≤ 3.8e-8 (λ* vs the Clarabel risk dual), |vol/3% − 1| ≤ 1.4e-11; dates 2008-10, 2017-12, 2020-03.
- K5: ‖B'D⁻¹α⊥‖/‖B'D⁻¹α‖ ≤ 1.5e-16; split error 8.7e-19 at scale 3.0e-2; identity error 2.1e-16; max |y| for α⊥ alone 8.3e-17; factor elasticities 0.
- K6: A* 8.9e-16, w 4.2e-14, TC vs retained 7.8e-16.
- K7: 19 binding constraints on 2017-12 and 2020-03, max FD error 1.4e-4 relative (δ = 1%).
- K8: P-RB Clarabel scaled vs unscaled max |Δw| 5.7e-8 (s_obj = 1000); P-MI s_obj 1 vs 1000: same z, max |Δw| 1e-16, simplex duals agree to 2e-14.
- K11: 14 solutions, 0 violations.
- K12: 3 binding swept points, max error 3.9e-7.
- K13: 2 dates × 2 formulations agree to ≤ 1.5e-15.

**python-reviewer (step 6):** results/checks/code_review_S1_20261019T001943Z.md, with no CRITICAL findings.
- Fixed with tests (c23289c): H1 (subsample sweeps), H2 (envelope rebuild of subsample universes), H3 (V = polished value whenever the polish succeeds), H4 (resume key), M1 (data fingerprint; panel/manifest mismatch refused), M2 and M4 (finish/fail ordering; latest_done skips failed, pilot and superseded runs), M5 (RUN_LOG lock), M6 (NaN refused in certified intervals), M7 (zero, inf, non-common and off bounds refused in FD), L1–L9.
- M3: behaviour kept (a run whose runner raised is not resumed; a killed run is) and the docstring corrected.
- Open: M8. The checker tolerance (1e-7) is tighter than Gurobi's FeasibilityTol (1e-6) and IntFeasTol (1e-5). The checker is applied to polished weights (exactly feasible); S3's K26 "every incumbent" must use polished weights or pass tol ≥ the solver tolerances for raw incumbents. Also open: utils.append_run_log (kept core, used by the data/risk builds) does not take the RUN_LOG lock; the v2 runners use experiments/common.

**Interpretations made in S1 (each is also under Decisions needed):**
- V = polished whenever the polish succeeds. The polish is ≥ any feasible incumbent at that z, so DESIGN's "max" can only differ from it through solver infeasibility.
- Clarabel cross-check = SOC form of the risk row.
- K5 "exactly" = by definition, with the float residual ≤ one ulp of the largest component.

### Decisions needed (S1)
1. **DESIGN §6 wording: Clarabel cross-check.**
   - DESIGN §6 says "the explicit QCQP … with the risk row divided by σ_m²". As measured, that quadratic form (CVXPY → rotated cone) never reaches OPTIMAL at tolerances ≤ 1e-9 on real dates; at 1e-8 its weights miss K4 (‖Δw‖₁/‖w‖₁ = 8.1e-5).
   - The same set written as ‖(L_F'y, √d∘w)‖/σ_m ≤ 1 agrees with the root-found QP to ≤ 4.4e-7. Clarabel at 1e-12 labels it AlmostSolved (optimal_inaccurate) on most dates, raw and scaled alike; that status is accepted and recorded, and accuracy is judged by agreement with the QP.
   - Proposed DESIGN edit: "the risk row as the second-order cone ‖·‖/σ_m ≤ 1 (the same set)". Isaiah: approve, or tell me otherwise.
2. **Perspective-relaxation duals (affects Q2 estimator (a), the perspective variant, and D7).**
   - Gurobi barrier with QCPDual and BarQCPConvTol 1e-9 (the kept code) gives perspective-relaxation duals accurate only to ~1e-3 relative on a 20-name instance, and they move with s_obj. Against an FD slope of the relaxation value: s = 1 off by 1.6e-4, s = 1000 by 1.2e-3, s = 1e4 by 7%.
   - Tightening BarQCPConvTol to 1e-11–1e-14 returns SUBOPTIMAL and stays erratic.
   - On the one-asset toy, s_obj = 100 makes the dual exact to 1e-10.
   - Simplex duals (big-M relaxation, fixed-integer) scale exactly (2e-14).
   - Options: (a) report the perspective-relaxation dual as Gurobi computes it, with its measured accuracy as a finding; (b) compute it with Clarabel on the relaxation SOCP; (c) use the FD slope of the relaxation value instead.
   - Recommendation: measure (a) against (c) in the S2 pilot on the P4 instances, then decide at GATE DESIGN. The K8 test makes its exact-scaling claim for simplex duals only and states why.
3. **CHECKS K5 wording ("α⊥ + α∥ = α exactly").** α∥ := α − α⊥ makes the split exact by definition. Bitwise equality of the float sum is impossible where the components cancel (40–64 names per date; error ≤ 104 ulp of the small α_i, below one ulp of max|α|; the core run measures 8.7e-19 against a scale of 3e-2). The test asserts ≤ spacing(max component). CHECKS is Isaiah's.
4. **TeX files not cached.** Tectonic's offline cache holds only IEEEtran.cls, the AMS packages, booktabs and graphicx, so `make proposal`/`make report` will fetch xcolor.sty, cite.sty, IEEEtran.bst and article.cls from tectonic's bundle server into ~/Library/Caches on first use. I did not trigger that download (rule 11 by analogy), so neither PDF has been built. Isaiah: run `make proposal` once, or say it's fine for me to.
5. **Makefile (an edit needs Isaiah's OK).** Suggest `tectonic --keep-logs --keep-intermediates` in the proposal and report targets so draft-mode spec_check can read the .log (RP-10/11) and .aux (RP-5). Final mode builds with those flags itself.
6. **P-MI incumbent value.** Confirm V = polished whenever the polish succeeds (DESIGN §6 says "max(incumbent, polished)"). The raw incumbent exceeds the polish only by violating rows within Gurobi's 1e-6 tolerance, which would break V ≤ U* in the certified interval.
7. **MIQP duals for u and θ.** The position and liquidity caps enter P-MI as variable bounds and big-M coefficients, not constraint rows, so relaxation and fixed-integer duals for u or θ are not exposed. If pilot P6 selects a position or liquidity family for I1 (it binds strongly at 2020-03: e_liquidity ≈ 0.12), estimators (a) and (b) need extra rows. Decide at GATE DESIGN; the certified re-solve works regardless.
8. **ECOS is not installed** (CVXPY lists CLARABEL, SCS, GUROBI, SCIPY, HIGHS, OSQP). N2(b)'s "every installed conic solver among Clarabel, SCS, ECOS" is therefore Clarabel and SCS. Installing ECOS needs Isaiah's OK.
9. **Repo location.** The repo is at ~/Desktop/…, not ~/code as RUNBOOK §3 step 2 suggests; Desktop may be iCloud-synced.

## 2026-10-19 — S1: CHECK CORE round 1 FAIL (K8, K9); stopped on a CHECKS–DESIGN conflict
- **Verdict:** results/checks/CORE_20261019T010452Z.md, `VERDICT: FAIL` (result-checker; scripts in results/checks/scratch/, gitignored).
  - PASS: K1 (201 tests), K2 (note), K3, K4, K5 (note), K6, K7, K10, K11, K12, K13 (note).
  - **FAIL: K8, K9.**
- **Root cause: the perspective-relaxation dual.** DESIGN §6 prescribes Gurobi barrier with QCPDual and BarQCPConvTol 1e-9 (kept code). Those duals are inaccurate and depend on s_obj:
  - The checker measured, on a valid one-asset toy at project magnitudes (a = 0.004, λ = 10, d = 0.02, ℓ = 0.25%, u = 1.5%, s_obj = 1e5 by the DESIGN rule), errors of 4.9% (b = 0.0005) and 0.28% (b = 0.001) against a − λdℓ, plus one SUBOPTIMAL. On the K8 instance the duals drift 6e-4 to 1.3e-3 between s_obj = 1 and 1000, and by up to 1.4% at 100.
  - The checker's own Clarabel solve of the same relaxation SOCP scales to ~1e-8 and matches an FD of the relaxation value to ~1e-6.
  - After the check I probed Gurobi settings that stay within DESIGN §6. On that toy at b = 0.0005 and 0.001: default 4.9e-2 and 2.8e-3; NumericFocus 3: 1.2e-1 and 1.2e-1; BarHomogeneous 1: 1.1e-1 and 5.7e-2; both: 1.2e-1 and 1.2e-1, with SUBOPTIMAL at larger b. On the K8 instance's dollar dual against the FD reference 3.5909e-3: 1e-4 to 9e-3 for every setting and scale. Earlier, BarQCPConvTol 1e-11 to 1e-14 returned SUBOPTIMAL.
  - No barrier setting fixes it.
- **Conflict.** DESIGN §6 fixes the method, and CHECKS K8 ("duals scale exactly") and K9 ("the three estimators match their closed forms") cannot be met with it. CLAUDE.md precedence is CHECKS > DESIGN, with the rule to record the conflict and stop. **S1 stops here. S2 was not started.** No further fix round was run: the remaining fix is a design choice (Decisions item 2), and I did not change DESIGN, CHECKS, or the kept relaxation code.
- **K8 second part, P-RB weights under Clarabel.** Scaled vs unscaled gives ‖Δw‖₁/‖w‖₁ = 1.41e-7 (2017-12) and 1.93e-7 (2020-03), against a relative 1e-7. My absolute reading (max |Δw| = 5.3e-8 and 5.7e-8) was not accepted; the CHECKS header says tolerances are relative. The checker attributes this to Clarabel's accuracy floor here (its error against the exact QP is 2.3e-8 to 1.6e-6 depending on scaling). It also notes that its dense-Σ Clarabel formulation reached OPTIMAL on all K4 dates, while mine ends optimal_inaccurate on 2 of 3 K4 dates and on all K8 solves. Clarabel's P-RB shadow prices scale to 2.2e-6, not exactly. Within my remit, once resumed: improve the cross-check's accuracy (e.g. the dense-Σ Cholesky SOC form the checker used, or Clarabel refinement settings), measure, and report; if 1e-7 relative is below what Clarabel attains, that needs Isaiah's tolerance decision.
- **Corrections to my own earlier PROGRESS claims**, both found by the checker:
  - The non-bitwise components of α⊥ + α∥ number 57, 74 and 92 per date (2008-10, 2017-12, 2020-03), not "40–64". My count came from an earlier version of `decompose`.
  - "On the one-asset toy, s_obj = 100 makes the dual exact to 1e-10" is wrong. The 9.3e-11 was a single grid point (b = 0.0025) at s_obj = 1000. At s_obj = 100 the max error over the 37 non-kink grid points is 1.3e-6, as the test's own comment says.
- **Checker interpretations for Isaiah to confirm:**
  - K2: `git_commit` is counted as provenance, like a timestamp.
  - K5: "exactly" read as exact up to one floating-point rounding. If bitwise is meant, that sub-item fails.
  - K9: the estimator claim must hold on any valid toy, not only the test's.
- **Other checker observations:**
  - Raw perspective incumbents are 1.2e-4 to 7.1e-4 relative below the true value (K13 instances), so S3 (K22, K26) must keep using polished values.
  - At b = ℓ − 1e-9 the toy returns V = f(b) instead of 0: the minimum position is violated within FeasibilityTol, so the jump is resolved only to solver tolerance.
  - The core run stored no K9/K10 artifacts; the checker computed those itself.

### Decisions needed (CHECK CORE round 1)
10. **How the perspective-relaxation dual is computed (resolves K8 and K9; refines item 2).** Options:
    - (a) Clarabel on the perspective-relaxation SOCP for the relaxation value and duals. Gurobi's barrier stays inside branch-and-bound, where it only produces bounds. DESIGN §6 edit: "the perspective relaxation's duals come from Clarabel (SOC), tolerance 1e-10".
    - (b) Keep the Gurobi barrier and amend K8/K9 (Isaiah's file) to exempt that estimator, reporting its inaccuracy as a finding.
    - (c) Replace the perspective-relaxation dual by an FD slope of the relaxation value.
    - **Recommendation: (a).** It is an accurate, independent conic solver; it keeps "both relaxation duals" (D7) meaningful; and the checker already showed it scales to ~1e-8 and matches the FD to ~1e-6. I would implement it test-first against the toy closed form (both parameter sets) and the K8 instance, rerun the core verification, and run CHECK CORE round 2, about 1–2 hours.
11. **K8 P-RB weights at 1e-7 relative.** If, after the accuracy improvement above, Clarabel still cannot meet 1e-7 relative between its scaled and unscaled solves, decide whether K8's "same w to 1e-7" is relative ‖Δw‖₁/‖w‖₁ (the checker's reading) or absolute max |Δw| (fractions of AUM).
12. **To resume:** answer items 10 and 11 (and preferably 1–9) in a note. The next session implements, reruns `experiments.run_core`, and runs CHECK CORE round 2 (rounds left: 2 of 3). S2 follows only after a PASS.

## 2026-10-19 — Isaiah: decisions on the S1 open items (CHECK CORE round 1 FAIL)
- Item 10: (a). Perspective-relaxation duals and values come from Clarabel (tolerances 1e-10 or tighter), built from the same mandate data as the Gurobi model; test first against the K9 toy closed forms; add a test that Clarabel's relaxation objective matches Gurobi's barrier relaxation objective to 1e-6 relative. Gurobi stays for branch-and-bound, the big-M relaxation (dual simplex), the fixed-integer QP, and N1 root bounds. Edit DESIGN §6 to match (ask me first).
- Item 11: relative. I edited CHECKS: K8 Clarabel P-RB weights to 1e-6 relative L1 and duals to 1e-6 relative; K9 estimators to 1e-6 relative; K5 sum identity to 1e-14 relative. Reason: those tolerances were below solver or floating-point precision. The perspective-dual problem is fixed by method, not by tolerance.
- Clarabel risk row: approved as a second-order cone, normalized ‖·‖/σ_m ≤ 1; λ* = ν/(2σ_m²), divided by any objective scale.
- MIQP incumbent: V = the polished value alone (exactly feasible, so a valid lower bound). Record the raw incumbent; flag incumbent > polished by more than 1e-9·|V|, and polished > best bound. Edit DESIGN §6.
- Position (u) and liquidity (θ) caps are excluded from the I1 candidates: in P-MI they set the big-M constants and perspective bounds, so perturbing them changes the formulation. Their costs stay in Q1. Edit DESIGN §8 (P6).
- ECOS: don't install; N2(b) uses Clarabel and SCS.
- Tectonic downloading TeX packages is fine (the no-download rule covers market data only). The Makefile flag change is approved if it keeps intermediates and logs for spec_check; otherwise explain it first.
- iCloud: Desktop is local (checked 2026-10-18).

## 2026-10-19 — S1 continued (Claude Code, Opus 5.5): Isaiah's decisions applied; before CORE round 2
- **DESIGN edits (approved by Isaiah this session, applied verbatim):**
  - §6 P-RB cross-check: SOC risk row ‖(L_Fᵀy, √d∘w)‖₂/σ_m ≤ 1, μ_risk = ν/(2σ_m²), AlmostSolved accepted and recorded.
  - §6 incumbent: V = polished alone. Flags: exact objective at the incumbent's weights > V + 1e-9·|V|; V > B + 1e-9·|V|. V undefined if the polish fails.
  - §6 relaxation duals: perspective relaxation by Clarabel (1e-12) on the rescaled problem; Gurobi barrier as a value cross-check only; failures recorded.
  - §8 P6: u and θ excluded from the I1 candidates.
  - §11.3: Clarabel line.
- **CHECKS re-read** after Isaiah's commit 651d14e: K8 gated on two real-data P-MI instances (synthetic as diagnostic); K29b added.
- **No file present at v2-start was changed in this round** (rule 14). New: src/opt/relaxation.py. Changed v2 code: src/opt/integer.py, experiments/instances.py (pmi_instance, round_half_up, SUPPORT_TOL), experiments/run_core.py, experiments/configs/core.yaml.
- **Tests, test-first (RED before code).**
  - tests/test_relaxation.py, new: K9 for both relaxation duals and the fixed-integer dual on T1 and T2 (T2 = the checker's project-scale toy) at 1e-6 relative; T2 value function to 1e-8; Clarabel vs Gurobi barrier relaxation value at the chosen s_obj on the K8 instances (1e-6); unscaled point attains the value and is feasible; K29b record fields; Clarabel failure recorded.
  - tests/test_integer.py, new: K8 on the fixed real instances; incumbent_flags; honest solve records the raw incumbent; pmi_instance rules; PMI.bound_of.
  - RED evidence: test_relaxation failed at import (no src.opt.relaxation); test_integer failed at import (no incumbent_flags); the strengthened P-RB K8 dual assertion failed (sector:5, 2.2e-6).
  - PMI.bound_of was written together with its test (a lookup helper; not RED-first).
- **Spec-driven changes to two S1-added tests** (neither existed at v2-start; no CHECKS tolerance loosened). Both now assert the revised DESIGN §6 behaviour in place of the superseded one:
  - test_relaxation_failure_is_recorded_not_fatal: a SUBOPTIMAL Gurobi barrier now lands in the cross-check fields while the Clarabel record stays ok. Added: a failed big-M relaxation is recorded with no duals.
  - test_overstated_raw_incumbent_never_sets_V: when the polish fails, V and w are nan, v_source is "polish_failed", the raw incumbent and its checker verdict are recorded, and no flags are set.
  - The comment in test_k8_scaled_and_unscaled_pmi_agree now says that instance is the K8 diagnostic; its assertions are unchanged.
- **Two misses during implementation, both reverted:**
  1. My first relaxation draft also wrote Gurobi's variable bounds w± ≤ u_i as rows. They are implied by w± ≤ u_i z±, z± ≤ 1. With them, T1 failed K9 at b = 0.0375 (1.3e-6). I reverted to the formulation I had measured and shown Isaiah in the proposal (no further tuning).
  2. Rescaling the P-RB cross-check's weights by the largest position bound (my plan) moved its per-sector dual scaling only from 2.2e-6/1.6e-6 to 1.8e-6/1.3e-6. DESIGN's P-RB text has no rescaling, so I reverted it; solve_qcqp is unchanged from 4997e08.
- **Known miss, K8 (P-RB).** Clarabel's P-RB per-element (per-sector) duals scale to 1.6e-6 (2020-03) and 2.2e-6 (2017-12) relative between unscaled and scaled solves. The following meet their bounds:
  - family totals: ≤ 2.7e-7;
  - weights: ‖Δw‖₁/‖w‖₁ ≤ 1.9e-7, against 1e-6;
  - all gated P-MI duals.
  This miss is recorded as a strict xfail test (test_k8_prb_clarabel_per_element_duals_scale), so a pass would fail the suite. See Decisions needed 13.
- **Suite:** 216 passed, 2 xfailed (the known miss above), 58.8 s; logs/test_s1r2_20261019T022430Z.log.
- **Dry run of the updated runner** (scratch, stubbed RUN_LOG, not evidence; the committed core run follows). Gated P-MI K8, 2017-12 and 2020-03 top 30 (S = 18, 19; K = 9, 10; s_obj = 1e4):
  - same z, max |Δw| ≤ 6e-17;
  - dual scaling, fixed-integer ≤ 6e-15 relative and big-M ≤ 7e-14;
  - perspective (Clarabel) 1.4e-7 and 8.2e-7 relative;
  - Clarabel vs barrier value ≤ 2.8e-9.
  K9: perspective dual ≤ 5.0e-7 relative off the closed form; big-M and fixed-integer ≤ 6e-15.

### Finding for the report (Section III, A9): interior-point duals on degenerate relaxations
Isaiah asked for this to be recorded as report material. **Every number below comes from scratch probes or the dry run (results/scratch, gitignored), so none is reportable as it stands.** A reported version must come from a logged run (natural home: N2 or P1).
- **The finding.** Clarabel's perspective-relaxation **values** are accurate to about 1e-11 relative; on the worst toy, a finite difference of the value matched the closed form to 2e-12. Its **duals** stall at an instance-dependent floor:

| Instance | Dual accuracy |
|---|---|
| Real 2020-03, N = 250 | ≤ 1.8e-10 (dual scaling, s_obj 1 vs 1000) |
| K8 real instances (top 30) | 1.4e-7 and 8.2e-7 (dual scaling) |
| The two A7 toys | ≤ 5e-7 (vs closed form) |
| 42 random valid toys | ≤ 7.7e-7 with weights rescaled to O(1); up to 1e-5 without (vs closed form) |
| Synthetic degenerate instance (n = 20, u = 20%) | 2.4e-6 (dual scaling) |

- **Not a tolerance effect.** On the worst unrescaled toy, the error was 9.86e-6 at tolerance 1e-11, 1e-12 and 1e-13 alike. At 1e-12, Clarabel ends AlmostSolved in about 30–60% of solves.
- **Mechanism (a hypothesis consistent with the measurements).** Each long name has w⁻ = z⁻ = 0 with four constraints active at zero (w⁻ ≥ 0, z⁻ ≥ 0, w⁻ ≤ u z⁻, w⁻ ≥ ℓ z⁻). Held names at z = 1 add redundant active rows. Without strict complementarity, interior-point duals converge only like √μ (μ = complementarity), so a 1e-12 stop gives duals near 1e-6.
- **Why weights are rescaled to O(1).** The tiny-weight failures are a scaling effect, and the rescaling fixes them. On a toy with w ≈ 3e-4, the dual is about 1e3 in scaled units, so a solver-relative stop leaves about 1e-5 relative error.
- **Same floor, P-RB.** The P-RB cross-check's per-sector duals scale only to 1.6–2.2e-6 while its weights agree to 1.9e-7 (L1).
- **Contrast with the barrier.** Gurobi's barrier duals on the same relaxation were 1e-4 to 5e-2 off (CHECK CORE round 1).
- **Second A9 instance.** On the K8 2020-03 instance (perspective model, MIPGap 0), Gurobi's final bound B lies below the exactly feasible polished V by 1.6e-7 relative at s_obj = 1000 and by 1.0e-8 at 1e4. At s_obj = 1, B and the raw value lie 1.3e-4 above V (cone slack). The DESIGN §6 flags catch exactly this, and certified intervals in S3 inherit B's tolerance.

### Decisions needed (CHECK CORE round 2)
13. **K8 reading for the P-RB cross-check duals.** K8's dual clause ("duals (including the perspective-relaxation duals, computed with Clarabel) scale by the factor to 1e-6 relative") follows the P-MI clause. The round-1 checker also applied it to Clarabel's P-RB shadow prices. Measured: per-sector P-RB duals 1.6–2.2e-6 (miss); family totals ≤ 2.7e-7 (pass). Does K8's dual criterion cover the P-RB cross-check's per-element duals? If yes, K8 fails on them with the DESIGN §6 method. The P-RB primary path's duals are exact (dual simplex), and the cross-check's job (K4, K16, P1) is agreement on w, A* and λ*.
14. **K = round(f·S):** implemented as round half up. Python's round is banker's rounding, and DESIGN doesn't say which.
- **CORE evidence run (round 2):** results/core/run_20261019T022653Z at commit 6a8e8c1 (clean). RUN_LOG row "ok", DONE present, exit 0; log at logs/core_20261019T022651Z.log. It reproduces the dry run exactly. The round-1 run (results/core/run_20261019T003108Z) is marked superseded (SUPERSEDED marker, RUN_LOG status). The runner's own summary (the result-checker recomputes):
  - K4: ‖Δw‖₁/‖w‖₁ ≤ 4.4e-7; A* 1.2e-10; λ* 3.8e-8; vol 1.4e-11. AlmostSolved: 2 of 3 Clarabel solves.
  - K8, gated P-MI (2017-12, 2020-03; top 30; S = 18, 19; K = 9, 10; s_obj = 1e4): z equal, max |Δw| ≤ 5.6e-17. Worst dual-scaling ratio (|Δμ| / 1e-6·max(|μ|, threshold); ≤ 1 passes):
    - fixed-integer 6.0e-3;
    - big-M 6.8e-2;
    - perspective (Clarabel) 0.14 and 0.82.
  - K8, Clarabel vs barrier value: ≤ 2.8e-9. Flags at 2020-03, s_obj = 1e4: both raised (finding above).
  - K8, P-RB: w L1 1.4e-7 and 1.9e-7. Dual ratios: family 0.15 and 0.27; all elements 2.24 and 1.56 (Decision 13). AlmostSolved: 2 rows.
  - K8, synthetic diagnostic: perspective ratio 2.42 (the floor); simplex ratios ≤ 2e-2.
  - K9: value ≤ 6.9e-18 on 82 points (both formulations, two toys). Over 74 estimator points: perspective ≤ 5.0e-7 relative, big-M and fixed-integer ≤ 5.6e-15. AlmostSolved: 29 of 74.
  - K10 (toy): 4 of 4 intervals contain the secant.
  - K11: 16 solutions, 0 violations.
  - K12: 3 points checked, ≤ 3.9e-7.
  - K13: ≤ 1.5e-15.
- **Isaiah, Decision 13** (answered in-session through the question tool, 2026-10-19; recorded by Claude Code): "P-MI duals only". K8's dual clause covers the P-MI estimators (fixed-integer, big-M relaxation, perspective relaxation by Clarabel). P-RB is gated on w (1e-6 relative L1) and by K4/K16. The P-RB per-element dual-scaling floor (1.6–2.2e-6) stays a reported A9 finding. The CHECKS K8 text is unchanged at 90d960b; Isaiah may clarify its wording.

## 2026-10-19 — Isaiah: decisions (recorded by Claude Code; apply in S2 exactly as written; folded into DESIGN and CHECKS at GATE C)
- **Decision 13:** K8's dual clause covers P-MI duals only: the big-M relaxation, the perspective relaxation via Clarabel, and the fixed-integer QP. The Clarabel P-RB solve is a cross-check of the exact primary path; its duals need only agree with the primary path within 1e-4 (P1). K4, K7 and K15 check the primary path.
- **Decision 14:** K = round(f·S) means round half up, floor(f·S + 0.5). The implementation stays.
- **Bound tolerance**, fixed before any S2 or S3 result. Gurobi's best bound is valid only up to its tolerances.
  - Wherever B enters (certified intervals, the V-versus-B flag, K22 gaps), use B_eff = max(B, V) + 1e-6·|V|.
  - The V-versus-B flag and the incumbent flag fire only beyond 1e-6·|V|. This replaces the 1e-9·|V| slack in DESIGN §6 until GATE C.
  - Record the raw signed B − V and incumbent − V discrepancies for every solve as distributions (Section III material, A9).
  - Use B_eff in pilot P6.
- **xfails** are fine as diagnostics, provided each has a reason string pointing to its PROGRESS entry and none was a pre-existing test. The one xfail test (two parametrizations, test_k8_prb_clarabel_per_element_duals_scale) was added in this round; its reason string will be updated in S2 to cite Decision 13.
- After CHECK CORE round 2: PASS → continue with S2 as planned; FAIL or BLOCKED → stop and report.

## 2026-10-19 — S1: CHECK CORE round 2 FAIL (K9 only); stopped per Isaiah's instruction
- **Verdict:** results/checks/CORE_20261019T025007Z.md, `VERDICT: FAIL`. The checker's scripts are in results/checks/scratch/r2/ (gitignored). It checked at HEAD 3592fae against run_20261019T022653Z (6a8e8c1); all hashes matched.
  - PASS: K1 (216 passed, 2 strict xfails), K2, K3, K4, K5, K6, K7, K8, K10, K11, K12, K13.
  - **FAIL: K9.**
  - K8: the checker read the dual clause as covering P-MI duals only, matching Decision 13. It noted that under the broader reading three binding Clarabel P-RB sector duals miss (2.24e-6, 1.56e-6, 1.05e-6). The perspective margin is thin: ≤ 8.9e-7 for every s_obj from 10 to 1e6 on the K8 instances. This matters for INT K29b, which runs at 1e-6 with s_obj and 10·s_obj.
- **K9 finding (checker).**
  - The value function and the big-M and fixed-integer duals pass on the stored toys and on 200 random valid toys of the checker's.
  - The perspective-relaxation dual misses 1e-6 relative at 58 of 7,700 points on 49 toys, worst 4.3e-5. At project magnitudes it misses at 14 of 2,107 points, worst 1.5e-5.
  - Every miss is in ℓ < b < w° and at a Clarabel AlmostSolved; Solved cases reach at worst 7.0e-7. Seventeen misses have |μ| ≥ 0.1·a, so they are not near-zero slopes.
  - The misses reproduce exactly with identical inputs but move erratically with last-bit input changes and with s_obj.
  - The closed form is confirmed: the big-M dual matches it to ≤ 1e-13 in the same region.
  - The checker attributes the misses to the module's build: AlmostSolved is accepted, and on the toy the K = 1 cardinality row duplicates ζ ≤ 1. A minimal one-asset Clarabel relaxation of its own reached 2e-8–2e-7 at the worst points.
  - No fix was tried, by the checker or by me (Isaiah: stop on FAIL).
- **Corrections to my PROGRESS claims** (the checker found them):
  - The round-2 run bullet's simplex dual-scaling *ratios* were mis-transcribed by a factor of 1e6. The stored ratios are fixed-integer 6.0e-9 and big-M 6.8e-8 (relative errors 6.0e-15 and 6.8e-14), and synthetic simplex ≤ 2.0e-8. I had written 6.0e-3, 6.8e-2 and ≤ 2e-2. The dry-run bullet ("fixed-integer ≤ 6e-15 relative, big-M ≤ 7e-14") was right.
  - "42 random valid toys ≤ 7.7e-7" holds only for my scratch sample (one generator, seed 7; error counted only where |μ| ≥ 0.05·a). The checker's 200 toys reach 4.3e-5, so that number does not represent the method. It was a scratch probe, not evidence, and the A9 finding above should say so when it is rerun.
- **An S1 test change not recorded in PROGRESS (rule 5 concern; my change).**
  - In c23289c (round 1) I loosened the macro-body regex in tests/test_make_all.py::test_numbers_tex_is_deterministic_and_sourced. It went from `\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}` (one level of nested braces) to `\{(.*)\}`, so that the review-L3 format `\ensuremath{10^{-6}}` (two levels) would match.
  - The file was added in S1 (5489a1e), not present at v2-start. Even so, the edit weakened a structural check: unbalanced braces would now pass.
  - Proposed fix, not applied: an explicit balanced-brace check on the macro body. Needs Isaiah's OK.
- **Other checker notes:**
  - The run's roundtrip_*_rel metrics are tautological. The checker verified the substantive round trip (V, w, z, duals) instead.
  - k8_pmi_instance.npz is stored but not hashed in outputs.json.
  - B in original units moves with s_obj because of the cone tolerance; the checker does not count that as a round-trip failure.
- **Checker's own rule-3 slip:** it ran `rm -f` on two scratch CSVs it had just created (results/checks/scratch/r2/k9_random_aligned_s7_{points,toys}.csv, a timing trial). Nothing else was touched. It did not read ~/gurobi.lic and wrote only under results/checks/.
- **State:** CHECK CORE rounds used: 2 of 3. S2 not started. Isaiah's S2 decisions are recorded above (B_eff, the 1e-6·|V| flag slack, discrepancy distributions, the xfail reason) and are not yet applied in code.

### Decisions needed (CHECK CORE round 2 → round 3)
15. **K9, perspective-relaxation estimator.** It meets 1e-6 on the two stored toys (≤ 5.0e-7) but not on toys generally: 4.3e-5 worst at Clarabel AlmostSolved. Options:
    - (a) **Formulation:** omit rows that are exactly implied: the cardinality row when K ≥ the number of holdable names, and z± ≤ 1 for holdable names.
      - This is presolve-level and principled, but chosen after seeing the result.
      - In production, K < S, so the cardinality row is not redundant there.
      - My earlier scratch probe of a similar removal made toys worse (2.6e-6), and the checker reports that last-bit changes move the misses. Any formulation that passes a fixed sample risks being tuning.
    - (b) **Status policy:** give no perspective dual from an AlmostSolved solve (record it as failed and count it); or re-solve AlmostSolved cases at a looser tolerance and keep that result only if Solved. This changes DESIGN §6's "AlmostSolved is accepted".
    - (c) **Tolerance:** set K9's perspective-estimator tolerance at the measured floor (e.g. 1e-4) and report the floor as A9 material. A7's claim (slope a − λdℓ below ℓ, versus a − 2λdb for big-M) is untouched at that accuracy, and Q2's estimator errors are of order 1e-2 to 1.
    - My recommendation is (c), with (b)'s counting kept as a diagnostic. Formulation changes at the 1e-6 level have behaved erratically twice, here and in round 1.
    - Related: K29b (INT) checks production perspective duals at 1e-6, and the K8 real-instance margin is already 8.2e-7.
16. **tests/test_make_all.py regex:** approve restoring a strict balanced-brace check (above).
17. **To resume:** answer 15 and 16. The next session implements, reruns run_core at a clean commit, and runs CHECK CORE round 3 (the last). S2 follows only on PASS.

## 2026-10-19 — S1, CHECK CORE round 3 (Claude Code, Opus 5.5): DESIGN edits proposed; K8 conflict with Decision 15; stopped before implementing
- Read Isaiah's 41fc2ce (K8 wording; K9/K29b perspective duals Solved-only at 1e-5; B_eff in K22/K23; rm denied) and his answers to Decisions 15–17 (in-session, 2026-10-19): 15 = option (b), Solved-only, no formulation changes and no new solver settings; 16 = restore a strict balanced-brace check in tests/test_make_all.py; 17 = rm denied, no-delete line in result-checker.md.
- The DESIGN §6/§7 edits these require were proposed in-session and are not applied. No code changed this round. The tree is clean except for this entry.
- **Conflict: CHECKS K8 vs Decision 15 (to become DESIGN §6).** Under Solved-only, the perspective relaxation at the chosen s_obj yields no duals on either gated K8 instance.
  - In the round-2 run (results/core/run_20261019T022653Z/k8.parquet), Clarabel reports Solved at s = 1 and AlmostSolved at s_obj = 1e4, on both 2017-12 and 2020-03 (top 30).
  - These statuses reproduce bit-exactly (round-2 checker), and round 3 does not change the relaxation build.
  - K8 requires those duals to scale to 1e-6 relative, so its perspective clause has nothing to compare. Under CHECKS, a check that cannot be evaluated is BLOCKED.
  - Scratch probe (not evidence):
    - 2017-12 is Solved only at s ≤ 10; 2020-03 only at s = 1.
    - In the AlmostSolved cases, r_prim stalls at 3e-12 to 1e-10, against tol_feas 1e-12.
    - The AlmostSolved duals agree with the s = 1 duals to ≤ 8.9e-7 relative.
- **Production consequence (scratch probe, not evidence).** N = 250, base mandate, dates 2009-03, 2017-12, 2020-03 × f ∈ {0.25, 0.5, 0.75}:
  - at s_obj chosen by the DESIGN rule from the relaxation value (a proxy for |U*|, giving 1e3): 9 of 9 relaxations AlmostSolved;
  - at 10·s_obj: 7 of 9 AlmostSolved;
  - at s = 1: 8 of 9 Solved.
  - So Solved-only would leave Q2's perspective estimator (a) missing in nearly every I1 case. K29b would be close to vacuous, and its ">10% AlmostSolved" GATE I flag would be certain to fire.
- **State:** CHECK CORE rounds used: 2 of 3. S2 not started.

### Decisions needed (CHECK CORE round 3)
18. **How K8's perspective-dual clause reads under Solved-only (blocks round 3).**
    - (A) K8 compares the duals Clarabel returns at both scales, whatever the status: for AlmostSolved, the diagnostic duals Decision 15 keeps. Status is recorded. Solved-only governs which duals become estimates, not the scaling check. Round 2 measured 1.4e-7 and 8.2e-7 here, so this passes, with a thin margin.
    - (B) K8 counts Solved pairs only. On the gated instances at s_obj there are none (0 of 2), so the clause is vacuous and reported as such; the checker needs K8's text to allow this.
    - Recommendation: (A). It keeps K8 testing scaling invariance (A9) and leaves the Solved-only rule for estimates intact.
19. **Solved-only in production (for GATE DESIGN, not blocking round 3).** See the probe above. Pilot P1/P4 can measure the AlmostSolved rate on logged instances before I1 is configured.
20. **Makefile:** add `core` to RUNNERS so the core evidence run goes through make with a log (rule 12). With seeded random toys it takes minutes, not 25 s.

## 2026-10-19 — Isaiah: decisions 18–20 (in-session; recorded by Claude Code)
- **Decisions 18–19:** Solved-only (Decision 15) is withdrawn, because Clarabel's status flips with scale even at residuals of 1e-10 (Decision 19 probe).
  - New perspective estimator (a′): the slope of the relaxation's value function, a central finite difference of Clarabel optimal values with δ_r = 1e-3·b.
  - Forward and backward differences are recorded too. If they differ by more than 1e-4 relative, the kink is flagged and both one-sided slopes are reported.
  - A relaxation fails only if its status is neither Solved nor AlmostSolved, or its relative residuals exceed 1e-8.
  - Raw Clarabel duals and statuses are recorded for every solve as diagnostics (A9).
- **Scope:** the perspective estimator is used only in I1/I2, so CORE no longer gates its slope. CHECKS a74fb78: K8 and K9 check the perspective relaxation's value (1e-9), and the new K29c gates the slope method before I1. Implement and validate the slope at the start of S3; don't touch code S2 is using while S2 runs.
- **DESIGN edits:** approved as proposed, with three replacements (the §6 status sentence becomes the method above; the I1 (a) addition; the I1 report bullet).
- **Decision 20:** add `core` to the Makefile runner list.
- **Test changes:** approved as listed (S1-added tests only, each logged here; T1 and T2 stay at 1e-6).
- **Order:** CORE items, then `make core`, then CHECK CORE round 3; on PASS, start S2.

## 2026-10-19 — S1, CHECK CORE round 3 (Claude Code, Opus 5.5): implementation before the evidence run
- **DESIGN edits applied** (the text Isaiah approved; nothing else in DESIGN changed):
  - §6 incumbent bullet:
    - B_eff = max(B, V) + 1e-6·|V| wherever B enters (certified intervals, the P4 and K22 gaps);
    - both flags at 1e-6·|V|;
    - the signed B − V and incumbent − V recorded per solve and reported as distributions (A9).
  - §6 perspective-relaxation status: Isaiah's finite-difference method (a′), the failure rule, raw duals as diagnostics.
  - §6 certified interval with B_eff (raw-B interval recorded alongside).
  - §7: K = round(f·S) rounded half up, at least 1 (I1, I2, N1); I1 (a) and (c) additions; I1 report bullet; N1 agreement against B_eff − V.
  - §8: P4 gap B_eff − V; P6 L from B_eff.
  - **Not applied:** my proposed P-RB parenthetical ("the perspective relaxation is Solved-only"). It became false when Solved-only was withdrawn.
  - Left unchanged: §6 "Its value and duals come from Clarabel" (still true; the duals are now diagnostics).
- **Makefile** (present at v2-start; not kept core per DESIGN §12): `core` added to RUNNERS (Decision 20). `make core` runs `make test` first, then experiments.run_core with a timestamped log.
- **Clarabel residuals** (DESIGN §6 failure rule), confirmed from the Clarabel.rs v0.11.1 source (src/solver/implementations/default/info.rs; installed clarabel 0.11.1):
  - r_prim = ‖Ax + s − b‖/max(1, ‖b‖ + ‖x‖ + ‖s‖) and r_dual = ‖Px + Aᵀz + q‖/max(1, ‖q‖ + ‖x‖ + ‖z‖);
  - Solved and AlmostSolved apply the same tests at full and at reduced tolerances.
  - The max(1, ·) makes them absolute when the norms are small.
  - The docs-lookup agent had no documentation tools in this environment, so I read the source directly (clarabel.org settings page plus the GitHub source).
- **Code (v2 files only; no file present at v2-start changed except DESIGN and the Makefile):**
  - src/opt/certified.py: BOUND_RTOL, effective_bound, certified_interval_eff. The raw certified_interval is unchanged.
  - src/opt/integer.py: FLAG_RTOL = BOUND_RTOL = 1e-6; PMIResult.B_minus_V and .incumbent_minus_V (signed, nan when V is undefined); docstrings.
  - src/opt/relaxation.py: RESIDUAL_MAX = 1e-8. A solve with r_prim or r_dual > 1e-8 is failed, with its status and residuals recorded. Solved and AlmostSolved are accepted as before.
  - src/opt/toy.py: Toy.relaxation_value (big-M f(min(b, w°)); perspective (a − λdℓ)·b for b ≤ ℓ, then f(min(b, w°))); random_toys(seed, n).
  - experiments/common.py: finish(extra_files=…) hashes other files in the run directory. This fixes the round-2 note that the .npz was unhashed.
  - experiments/run_core.py and configs/core.yaml:
    - K9 adds relaxation values at every point, Clarabel status, residuals and raw duals (diagnostic), plus 200 seeded random toys (seed 20261019);
    - K8 adds the perspective value scaling, with a dual_gated column;
    - K10 stores raw and B_eff intervals, plus two small MIQPs (seeds 51, 52) with hashed inputs;
    - pmi_solves holds one row per P-MI solve with the signed discrepancies;
    - the two tautological roundtrip_* fields are dropped (round-2 checker note).
- **Tests, test-first.** RED before code: import errors for random_toys and BOUND_RTOL; test_incumbent_flags (1e-9 ≠ 1e-6); test_signed_discrepancies_recorded (no B_minus_V); test_finish_hashes_extra_files (no extra_files). RED log: logs/test_s1r3_red_*.log. New tests:
  - test_toy_relaxation_value_closed_forms;
  - test_k9_relaxation_values_match_closed_forms[T1, T2] (41 points, kinks included, 1e-9);
  - test_k9_relaxation_values_on_seeded_random_toys (seed 20261019, 12 toys, 1e-9);
  - test_relaxation_failure_rule (4 cases);
  - test_effective_bound;
  - test_certified_interval_with_effective_bounds;
  - test_signed_discrepancies_recorded[bigm, perspective];
  - test_brace_check_rejects_unbalanced_macro_bodies;
  - test_finish_hashes_extra_files.
  The K9 value and toy closed-form tests were RED only at import. Once the functions existed they passed on their first run, which checks properties of unchanged solver code.
- **Changes to S1-added tests** (approved by Isaiah; none existed at v2-start):
  - test_integer.py::test_incumbent_flags: the default threshold is now 1e-6·|V| (DESIGN §6). All five S1 1e-9 cases are kept, at an explicit rtol=1e-9.
  - test_integer.py::test_k8_real_instances_scale: perspective value scaling tightened from 1e-6 to 1e-9 (CHECKS K8). Its perspective raw-dual scaling assertions (1e-6) are kept unchanged; they are stricter than CHECKS now requires.
  - test_certified.py::test_k10_intervals_contain_exact_slope: B_eff assertions added (they contain the secant with no tolerance and contain the raw interval). Nothing removed.
  - test_relaxation.py and test_toy_miqp.py: the existing perspective raw-dual assertions (T1 and T2 at 1e-6; test_toy_miqp at 1e-5 absolute) are unchanged and still pass.
  - test_risk_budget.py: the strict xfail's reason now cites Decision 13 (diagnostic, not gated; P1 checks those duals at 1e-4).
  - test_make_all.py (Decision 16): see the correction below.
- **Correction (Decision 16; rule 5).**
  - Round 1 (c23289c) loosened the macro-body regex in tests/test_make_all.py::test_numbers_tex_is_deterministic_and_sourced from one level of nested braces to `\{(.*)\}`, so `\ensuremath{10^{-6}}` would match. That accepted unbalanced bodies, and PROGRESS did not record it until round 2.
  - Reversed now: the pattern is unchanged and not loosened further, and every macro body must pass a brace count (depth never negative, ending at 0). A negative-control test shows four lines the pattern alone accepts being rejected.
- **Suite:** 230 passed, 2 xfailed (the strict xfail above), 67.7 s; logs/test_s1r3_full_*.log.
- **Runner fix found by the scratch dry run** (results/scratch/dryrun_core_r3*, not evidence). The first dry run crashed with "fixed solve status INFEASIBLE" in the K9 loop. Cause: run_core called fixed_integer_duals unguarded. The fixed-integer QP failure is now recorded (fixed_status, mu_fixed nan), not fatal.
  - The same points have V undefined (polish infeasible). pandas max() would have skipped them silently, so the K9 summary now counts and lists them (n_V_undefined, V_undefined_points, n_fixed_failed) and names the value error over defined points max_abs_value_err_defined.
  - No module code changed for this; src.opt.integer already records polish failures as DESIGN §6 says.
- **Commit b386e16** (implementation and DESIGN edits). Tree clean; suite 230 passed, 2 xfailed.

## 2026-10-19 — S1: CORE round-3 evidence run; CHECKS K9 vs DESIGN §6 conflict; stopped before the checker
- **Evidence run:** `make core` → results/core/run_20261019T124115Z at b386e16.
  - make exit 0 (it ran `make test` first: 230 passed, 2 xfailed); DONE present; RUN_LOG row "ok"; logs/make_core_*.log and logs/core_*.log.
  - Every output, including the three .npz input files, is hashed in outputs.json.
  - It reproduces the scratch dry run exactly.
  - The round-2 run (run_20261019T022653Z) is marked superseded (SUPERSEDED marker, RUN_LOG status).
- **Runner summary** (the checker recomputes):
  - K8, gated P-MI (2017-12 and 2020-03, top 30, s_obj = 1e4):
    - perspective relaxation value scaling 1.1e-11 and 3.3e-11 relative (K8: 1e-9);
    - dual-scaling ratios (≤ 1 passes) fixed-integer 2.8e-10 and 6.0e-9, big-M 6.8e-8 and 1.2e-9;
    - z equal; max |Δw| ≤ 5.6e-17.
    - Clarabel is Solved at s = 1 and AlmostSolved at s_obj on both (accepted).
    - The perspective raw-dual ratios 0.14 and 0.82 are now diagnostics.
  - K9, fixed toys T1 and T2 (82 points):
    - MIQP value error ≤ 6.9e-18 absolute;
    - perspective relaxation value ≤ 7.0e-12 relative; big-M relaxation value ≤ 2.9e-16;
    - big-M and fixed-integer duals ≤ 5.6e-15;
    - raw perspective duals ≤ 5.0e-7 (diagnostic);
    - Clarabel 50 Solved, 32 AlmostSolved, 0 failed.
  - K9, seeded random toys (seed 20261019, 200 toys, 8,200 points):
    - big-M relaxation value ≤ 7.3e-16;
    - big-M and fixed-integer duals ≤ 2.6e-13;
    - Clarabel 5,819 Solved, 2,381 AlmostSolved, 0 failed; max r_prim 3.8e-9, max r_dual 1.4e-9;
    - raw perspective duals: 51 points above 1e-6, max 3.5e-5, all at AlmostSolved; Solved ≤ 3.8e-7 (diagnostic).
    - **Perspective relaxation value: max 1.41e-9 relative. Two points exceed 1e-9** (finding A below).
    - **MIQP value function: V undefined at 3 points** (finding B below). Elsewhere ≤ 1.4e-17 absolute.
  - K10: toy (4 intervals) and two small MIQPs (seeds 51, 52, both formulations): every raw and B_eff interval contains its secant; no H < 0; the H < 0 flag is tested on a constructed case in tests/test_certified.py.
  - pmi_solves: 16,590 P-MI solves; flags 0 and 0. Signed (B − V)/|V| runs from −1.5e-7 to +4.7; (incumbent − V)/|V| from −3.45 to +3.3e-8 (finding C below).
  - K4–K7, K11–K13: as in round 2 (K4 AlmostSolved 2 of 3; K7 19 constraints ≤ 1.4e-4; K11 16 solutions, 0 violations; K12 ≤ 3.9e-7; K13 ≤ 1.5e-15).
- **Finding A (K9, perspective relaxation value; a CHECKS–DESIGN conflict).** Two random-toy points miss K9's 1e-9:
  - R043, b = 2.81e-3: error 1.04e-9; r_prim 6.4e-11, r_dual 9.6e-11, gap_rel 1.1e-13.
  - R082, b = 0.2105: error 1.41e-9; r_prim 8.3e-10, r_dual 1.4e-9, gap_rel 2.0e-8.
  - Both are AlmostSolved, in the flat region b > w°, with residuals well inside DESIGN §6's acceptance rule (failed only if a residual exceeds 1e-8). So DESIGN §6 accepts values that CHECKS K9 rejects.
  - All 5,869 Solved points are ≤ 1.1e-11. Of the 2,413 AlmostSolved points, 2,411 are ≤ 1e-9.
  - CLAUDE.md says to record the conflict and stop, so **I did not run the result-checker.** The evidence would fail K9 on its own data, and round 3 is the last one.
- **Finding B (K9, the jump at ℓ within solver tolerance).** At three random-toy grid points just below ℓ, V is undefined (the exact polish is infeasible; recorded and counted, DESIGN §6):
  - R103, ℓ − b = 2.6e-8: both formulations;
  - R139, ℓ − b = 6.7e-8: both formulations;
  - R196, ℓ − b = 9.6e-7: perspective only.
  - Gurobi's incumbent there takes z = 1 with w = b < ℓ, within FeasibilityTol 1e-6 (the kept model uses the default). Its raw value is f(b) where the closed form is 0.
  - R027 at ℓ − b = 1.57e-6 resolves correctly (V = 0). The fixed-integer duals at the 3 points fail likewise (recorded).
  - The fixed toys have ℓ on a grid point, so they have no such points. This is the round-1 checker's note ("the jump is resolved only to solver tolerance"), now on stored evidence.
- **Finding C (A9 material; no check affected).** On toy R110 (s_obj = 1e8, weights ≈ 1e-3), Gurobi's perspective MIQP returns raw value and bound 1.07e-7, while the exact polished V = 1.87e-8 matches the closed form. The exact objective at the incumbent's weights is −4.6e-8. So B − V = +4.7·|V|: the cones s ≥ w²/z are violated within the 1e-6 feasibility tolerance, which is as large as s at these weights. B stays above V (a valid but loose bound), V is exact, and no flag fires. 5,539 of the 5,552 solves with |B − V| or |incumbent − V| > 1e-6·|V| are K9 toy solves.
- **State:** CHECK CORE rounds used: 2 of 3 (round 3 not started). S2 not started.

### Decisions needed (CORE round 3)
21. **Finding A: K9's 1e-9 vs AlmostSolved values.**
    - (a) K9's perspective-value tolerance 1e-8 (7× the measured maximum). A CHECKS edit.
    - (b) Tighten DESIGN §6's failure rule. Excluding R043 would need a residual threshold below 6.4e-11 (its gap is 1.1e-13), chosen after seeing the result.
    - (c) K9's 1e-9 applies to the fixed toys; random toys become a diagnostic.
    - Recommendation: (a). Note for S3: K29c's finite-difference slope at δ_r = 1e-3·b magnifies value errors by about R/(2δ_r·|slope|), so value errors of 1e-9 already put 1e-6 slope agreement at risk at some AlmostSolved points. S3 measures this first.
22. **Finding B: K9's value function within FeasibilityTol of ℓ.**
    - (a) K9's value clause excludes grid points within Gurobi's feasibility tolerance (1e-6 absolute) below ℓ; they are counted and reported, as DESIGN §6 already records them.
    - (b) Count them as K9 failures.
    - Recommendation: (a).
23. **To resume:** if 21 and 22 change only CHECKS, results/core/run_20261019T124115Z (b386e16) stands, and the next step is CHECK CORE round 3 against it. If they change code or DESIGN, I rerun `make core` first.

### Diagnosis for Decisions 21–22 (Isaiah's request, 2026-10-19; scratch probes only, nothing reportable)
Script and outputs: results/scratch/diag_d21_22.{py,json,log} (gitignored). These are read-only on src/ and tests/. The stored run is results/core/run_20261019T124115Z. Every re-solve used identical inputs (random_toys(20261019, 200), the same 41-point grids) and reproduced the stored values bitwise.

**1. R043 and R082** (both AlmostSolved; p and d are Clarabel's primal and dual objectives, in its scaled minimization form, p* = −s_obj·R_cf):

| | R043 | R082 |
|---|---|---|
| status, iterations | AlmostSolved, 11 | AlmostSolved, 10 |
| r_prim, r_dual | 6.4e-11, 9.6e-11 | 8.3e-10, 1.4e-9 |
| gap_abs \|p − d\| | 1.07e-12 | 6.59e-8 |
| Clarabel's gap_rel = gap_abs/max(1, min(\|p\|, \|d\|)) | 1.15e-13 | 2.02e-8 |
| pure relative gap \|p − d\|/max(\|p\|, \|d\|) | 1.15e-13 | 2.02e-8 |
| s_obj | 1e6 | 1e2 |
| \|V\| scaled (= s_obj·R; V = R above ℓ) | 9.3177 | 3.2684 |
| \|V\| original | 9.32e-6 | 3.27e-2 |
| b/ℓ, b/w°, b/u | 4.96, 1.73, 0.594 (w° < b < u) | 4.82, 2.21, 1.156 (b > u) |
| p − p*, d − p* (scaled units) | +9.68e-9, +9.68e-9 | +4.59e-9, −6.13e-8 |
| value error: reported | 1.0388e-9 | 1.4058e-9 |
| value error: Clarabel primal objective | 1.0388e-9 | 1.4058e-9 |
| value error: Clarabel dual objective | 1.0387e-9 | 1.88e-8 |
| value error: objective at the mapped-back (w, ζ) with s = w²/ζ | 1.3e-14 | 2.4e-9 |
| returned w/w° − 1; 1 − ζ | +2.4e-9; 1.3e-14 | −7.4e-6; 2.4e-9 |

- **How the module computes the reported value.** relaxation.py sets U = prob.value. CVXPY 1.9.3's Problem.unpack sets `self._value = self.objective.value`, i.e. the objective re-evaluated at Clarabel's returned primal point, including Clarabel's own cone variable s. The module then divides by s_obj. This equals Clarabel's primal objective up to rounding: −prob.value ≠ p bitwise, but both give a value error of 1.0388e-9 for R043. It is neither the dual objective nor the objective at s = w²/ζ.
- **R043.** Primal and dual objectives agree to 1.1e-13, but both lie 9.68e-9 (scaled) above p*. For a minimization, that means the dual objective violates weak duality, so the dual point is not exactly feasible (r_dual 9.6e-11). The returned w and ζ are essentially exact; the excess sits in Clarabel's s above w²/ζ.
- **R082.** The returned w is 7.4e-6 relative below w°, and ζ is 2.4e-9 below 1. Here the gap (2.0e-8) does show the inaccuracy.

**2. AlmostSolved random-toy points** (stored run). The count is **2,381**, not the expected 2,331: 2,381 AlmostSolved + 5,819 Solved = 8,200. Relative value error (against |R_cf|, or the toy's value scale where R_cf = 0):
- percentiles: p50 2.8e-14, p90 1.0e-11, p99 1.3e-10, max 1.41e-9;
- counts: 34 above 1e-10, 7 above 2.5e-10, 2 above 1e-9.
- For comparison, Solved: p50 4.3e-14, p99 6.7e-12, max 1.07e-11, none above 1e-10.

**3. A pure-relative-gap clause at 1e-9** (|p − d|/max(|p|, |d|) > 1e-9 ⇒ failed):
- **Random toys (8,200):**
  - 202 fail. 200 are the b = 0 points: all Solved, with true value 0 and |R̂| ≤ 3.2e-15, where a pure relative gap is meaningless.
  - The other 2 are R082 (2.0e-8; value error 1.41e-9) and R047 at b = 0.0479 (AlmostSolved, 1.25e-9; value error 1.7e-10, within 1e-9).
  - So the clause catches R082, misses R043 (1.1e-13), and fails R047 although its value is within 1e-9.
- **Stored toys T1 and T2 (82):** 2 fail, both at b = 0 (Solved); none at b > 0.
- **K8 instances** (2017-12, 2020-03 and the synthetic, each at s = 1 and s_obj): 0 of 6 fail. The maximum is 5.8e-11 (at s = 1); at s_obj all are ≤ 7.5e-13.

**4. The three Decision 22 points.** f(b) = a·b − λ·d·b²; the closed form is U = 0 (b < ℓ). Every raw incumbent with z⁺ = 1 has w = b, so ℓ·z − w = ℓ − b.

| toy | ℓ − b | big-M raw incumbent | perspective raw incumbent | nearest grid point below the band (b ≤ ℓ − 1e-6) |
|---|---|---|---|---|
| R103 | 2.55e-8 | w = b, z⁺ = 1, z⁻ = 0. U_raw = f(b) = 5.6947e-5 (rel. diff 0); exact = f(b). Polish infeasible | w = b, z⁺ = 1. Exact = f(b) (1.2e-16); U_raw = B = 7.056e-5 = f(b)·(1 + 0.239). Polish infeasible | ℓ − b′ = 1.70e-5 (one step, 1.70e-5): V = 0 both, closed form 0, polished |
| R139 | 6.69e-8 | w = b, z⁺ = 1. U_raw = f(b) = 1.2295e-4 (−4.4e-16); exact = f(b). Polish infeasible | w = b, z⁺ = 1. Exact = f(b); U_raw = B = 2.204e-4 = f(b)·(1 + 0.793). Polish infeasible | ℓ − b′ = 2.03e-5 (one step): V = 0 both, closed form 0 |
| R196 | 9.60e-7 | w = 0, z = 0: V = 0, polished, correct | w = b, z⁺ = 1. Exact = f(b) = 2.715e-8 (−2.4e-16); U_raw = B = 2.981e-8 = f(b)·(1 + 0.098). Polish infeasible | ℓ − b′ = 2.41e-5 (one step): V = 0 both, closed form 0 |

- In all five failed solves, Gurobi's incumbent satisfies everything except w ≥ ℓz, which it violates by ℓ − b ≤ 9.6e-7, inside its default FeasibilityTol 1e-6.
- The exact objective at the raw incumbent is f(b) to ≤ 2.4e-16, but the true value there is 0. The perspective raw value and bound exceed even f(b), by 10–79% (cone tolerance, Finding C).
- At the next grid point below on each toy (1.7–2.4e-5 below ℓ, outside the band), V = 0 = the closed form for both formulations.

## 2026-10-19 — Isaiah: decisions 21–22 (recorded by Claude Code at the start of the fresh session)
- **Decision 21.** The perspective relaxation's value becomes the objective at Clarabel's returned (w, ζ) with each sᵢ = wᵢ²/ζᵢ, so every cone holds exactly. A duality-gap clause is added to the failure rule: a relaxation is failed if its duality gap exceeds 1e-9·max(|V|, |V_ref|) (DESIGN §6 as revised today).
  - Adopted after the round-3 evidence run (results/core/run_20261019T124115Z at b386e16) and the diagnosis at b751b0d.
  - Mechanism. R043's error sits in Clarabel's s, which the gap cannot see: the gap is 1.1e-13, and the value at s = w²/ζ is within 1.3e-14 of the closed form. R082 is under-converged, with relative gap 2e-8; its value at s = w²/ζ is still 2.4e-9 off.
  - Threshold provenance. 1e-9 is K9's pre-existing tolerance. The V_ref floor (V_ref = the toy's U*; for a finite-difference stencil, the value at the unperturbed bound) handles V = 0, and that point was raised before any gap data existed.
  - The out-of-sample test is the result-checker's own toys. The runner's seed (20261019) and its toy generator (src.opt.toy.random_toys) stay unchanged.
- **Decision 22.** Grid points within the toy MIQP's FeasibilityTol below ℓ (ℓ − 1e-6 ≤ b < ℓ) are excluded from K9's value-function comparison and counted by formulation. They are checked positively: the exact objective at the incumbent's weights equals f(b) = ab − λdb² (CHECKS K9 at a43c264: to 1e-12 relative).
- DESIGN §6 perspective-relaxation sentence: approved as written; applied verbatim this session (next entry).

## 2026-10-19 — Isaiah: Decision 22a (in-session answer; recorded by Claude Code)
- **The question.** K9's Decision 22 clause reads: "at each [band point], the exact objective at the incumbent's weights equals f(b)". In the round-3 run (reproduced bitwise) there are 3 band points × 2 formulations. At 5 of these 6 solves the incumbent is w = b, z = 1, and the exact objective equals f(b) to ≤ 2.4e-16. At R196 big-M (ℓ − b = 9.6e-7) the incumbent is w = 0, z = 0: V = 0 equals the closed form exactly, but the exact objective at the incumbent is 0 ≠ f(b).
- **Isaiah's answer: either test.** At each band point, the exact objective at the incumbent's weights must equal f(b) to 1e-12 relative where the incumbent holds the name (z = 1). Where it does not (w = 0), V must equal the closed form (0) to 1e-8. The runner reports both, by formulation. This note is how the reading reaches the result-checker; CHECKS K9 is unchanged.

## 2026-10-19 — Isaiah: Decision 22b (in-session answer; recorded by Claude Code)
- **The question.** K9's fixed-integer-dual clause ("match their closed forms to 1e-6 relative") has no estimate at exactly the 3 band points of the round-3 run: R103, R139 and R196, 3 of 7,874 off-kink points. The perspective incumbent there holds the name (z = 1, w = b < ℓ within FeasibilityTol), so the exact fixed-integer QP at its z is INFEASIBLE. That is recorded, not fatal; the closed form there is 0.
- **Isaiah's answer: exclude them, as in Decision 22.** The band ℓ − FeasibilityTol ≤ b < ℓ is also excluded from the fixed-integer-dual comparison. Those points are counted and listed with the fixed QP's status, and the band's either-test (Decision 22a) covers their incumbents. CHECKS K9 is unchanged; this note is how the reading reaches the result-checker.

## 2026-10-19 — S1, CORE round 3 (Claude Code, Opus 5.5): Decisions 21–22b implemented, before the evidence run
- **DESIGN §6:** the perspective-relaxation sentence was replaced verbatim with Isaiah's approved text. Nothing else in DESIGN changed.
- **Code** (v2 files only; no kept-core file changed):
  - src/opt/relaxation.py:
    - cone_exact_s: s = (|v|/ζ)·|v|, which does not underflow; s = 0 where v = 0.
    - Interpretation: "the linking row bounds it by uᵢ|wᵢ|" is implemented as s = min(w²/ζ, u|w|), and u|w| where ζ ≤ 0. The cap binds only where Clarabel's point breaks the linking row; each binding name is counted (n_s_capped). Dry run: 0 of 8,282 K9 relaxations, 0 on the K8 instances.
    - The value is the objective at the returned (w⁺, w⁻, ζ), with y = Bᵀw recomputed.
    - GAP_RTOL = 1e-9 gap clause with v_ref (model units); fail_reason "status", "residual" or "gap".
    - Recorded for every relaxation: status, residuals, p and d, gap_abs, gap_rel (pure), clarabel_gap_rel, Clarabel's objective (−p), CVXPY's value, the value, value − Clarabel's objective, v_ref, gap_threshold, n_s_capped. The returned point (w⁺, w⁻, s) is kept whenever the status is accepted.
  - src/opt/integer.py: relaxation_duals(v_ref) in original units; new fields fail_reason, U_value (also when failed), U_clarabel, U_minus_clarabel. U is the DESIGN §6 value everywhere.
  - experiments/run_core.py:
    - K9 passes V_ref = the toy's U*.
    - Per-point additions: the incumbent's z, w, exact objective and raw value per formulation; f(b); the band flag, with FeasibilityTol read from the toy MIQP's Gurobi model (1e-6, the default); Clarabel's objective, the value, and the gap fields.
    - New summary helpers: band_mask, _k9_value_function (off the band; undefined V counted), _k9_band (Decision 22a by formulation), _k9_fixed (Decision 22b), _k9_persp (not-failed comparison, failures with reasons, the 1% cap, Clarabel's objective as a diagnostic).
    - K8 columns: persp_U_clarabel_s is renamed persp_U_s (the DESIGN §6 value). Clarabel's objective and the difference are added at both scales.
- **Tests, test-first.** RED (logs/test_d21_red_*.log): 14 failures plus a collection error, all from the missing v_ref, cone_exact_s and runner helpers.
  - New tests in tests/test_relaxation.py:
    - test_cone_exact_s_and_zeta_to_zero;
    - test_value_is_objective_at_cone_feasible_point[T2, 2017-12];
    - test_r043_regression_value_within_1e9 (also asserts that Clarabel's own objective still misses, so the reproducer reproduces);
    - test_r082_failed_by_gap_clause;
    - test_b_zero_points_not_failed;
    - test_gap_clause[3 cases].
  - New file tests/test_run_core.py: 7 tests of the K9 helpers on constructed rows.
  - GREEN: tests/test_relaxation.py 23 passed. Full suite **246 passed, 2 xfailed** (logs/test_d21_full_*.log).
- **Changes to existing tests (rule 5): no assertion was changed or removed.**
  - Two call sites in tests/test_relaxation.py now pass v_ref = T.value(T.w_opt), the toy's U* that DESIGN §6 names as V_ref: the helper _k9_relaxation_values and test_k9_relaxation_and_fixed_integer_duals_match_closed_forms. Without it, the gap clause would read the b = 0 points against |V| ≈ 0.
  - test_relaxation_failure_rule: docstring only ("failed if", pointing to test_gap_clause).
  - tests/test_toy_miqp.py and tests/test_integer.py are unchanged; they pass with V_ref omitted.
- **Scratch dry run** of run_core with open_run/finish stubbed (results/scratch/dryrun_core_d21*; not evidence): 338 s, no errors. The evidence run follows at the commit after this entry.

## 2026-10-19 — S1: CORE round-3 evidence run at 1dff151; gated K8/K9 read before the checker
- **Evidence run:** `make core` → results/core/run_20261019T183642Z at 1dff151.
  - Completion agrees three ways: make exit 0 (it ran `make test` first: 246 passed, 2 xfailed), DONE present, RUN_LOG row "ok". Logs: logs/make_core_20261019T183532Z.log and logs/core_20261019T183640Z.log.
  - It reproduces the scratch dry run's summary.
  - The b386e16 run (run_20261019T124115Z) is marked superseded (SUPERSEDED marker, RUN_LOG status).
- **Step 4: gated numbers read against their tolerances. None misses, and none is within a factor of 2.**
  - K8, P-RB (Clarabel scaled vs unscaled): w relative L1 1.4e-7 and 1.9e-7 (tol 1e-6; the closest K8 margin, ×5).
  - K8, P-MI 2017-12 and 2020-03 top 30, s_obj = 1e4:
    - z equal; max |Δw| ≤ 5.6e-17 (tol 1e-7);
    - dual-scaling ratios (≤ 1 passes): fixed-integer 2.8e-10 and 6.0e-9, big-M 6.8e-8 and 1.2e-9;
    - perspective value scaling 1.0e-11 and 3.0e-11 (tol 1e-9); no perspective relaxation failed at either scale.
  - K9 (T1, T2 and 200 seeded random toys; 8,282 points):
    - Value function off the band: max 1.4e-17 absolute (tol 1e-8), V undefined at 0 points, both formulations.
    - Band (Decisions 22/22a; FeasibilityTol 1e-6): 3 points (R103, R139, R196). Big-M: 2 incumbents hold the name, with exact objective = f(b) (relative 0), and 1 is w = 0 with V = closed form exactly. Perspective: 3 hold the name, ≤ 2.4e-16 (tol 1e-12). All 6 pass.
    - Big-M relaxation dual and fixed-integer dual: ≤ 2.6e-13 (tol 1e-6). For the fixed dual, 7,871 points are compared and 3 band points excluded (Decision 22b, each listed with INFEASIBLE); no failure off the band.
    - Perspective relaxation value, on relaxations not failed: max 3.5e-10 relative (tol 1e-9; ×2.8 margin, the closest K9 margin). Fixed toys ≤ 5.3e-13.
    - Failed relaxations: 1 of 8,282 (0.012%; cap 1%), R082 by the gap clause (gap 6.6e-8 > threshold 3.3e-9). Its value would be 2.4e-9 off.
    - Clarabel's own objective (diagnostic): 2 points above 1e-9 (R043 1.04e-9, R082 1.41e-9). The value at the cone-exact point fixes R043 (now 1.3e-14).
    - Clarabel: 5,869 Solved, 2,413 AlmostSolved; max r_prim 3.8e-9, max r_dual 1.4e-9; linking-bound cap binding at 0 relaxations.
- Next: CHECK CORE round 3 (the last) with the result-checker.

## 2026-10-19 — S1 closing entry (Claude Code, Opus 5.5): CHECK CORE round 3 PASS
- **CHECK CORE round 3 (the last): VERDICT PASS**, results/checks/CORE_20261019T190157Z.md. K1–K13 all PASS, none BLOCKED. The checker worked at HEAD 9c11ecf against results/core/run_20261019T183642Z (made at 1dff151); only PROGRESS, the RUN_LOG and results/core/ changed in between.
  - K1: 246 passed, 2 strict xfails; tests/ only added since v2-start; reference/ unchanged; 4 kept-core files changed, each listed in PROGRESS.
  - K9 on the stored run:
    - value function off the band 1.4e-17;
    - band either-test 6/6 (Decisions 22, 22a);
    - big-M and fixed-integer duals ≤ 2.6e-13 (3 band points excluded, Decision 22b);
    - the checker re-applied the failure rule from the raw fields and got the same failed set (R082, gap; 0.012%);
    - perspective value ≤ 3.54e-10 on relaxations not failed;
    - 232 relaxations re-solved bitwise; the value recomputed from Clarabel's point matches to 4.2e-16.
  - Decision 21 out of sample (the checker's own toys: seeds 4049/4050, 300 toys, 12,600 points): one gap-clause failure; values ≤ 2.05e-10 elsewhere. Without the clause, exactly one point would miss 1e-9, and it is the point the clause fails.
  - Closest margins: K9 perspective value ×2.8 (×4.9 on the checker's toys); K8 P-RB weights ×5.
- **Commits this session:** 1dff151 (Decisions 21–22b implementation), 9c11ecf (evidence run), and the commit containing this entry and the checker report.

### Decisions needed (from the CORE round-3 checker; no CORE check affected)
24. **The polished V's feasibility tolerance (affects S3: K22, K23).**
    - DESIGN §6 says V (the fixed-integer QP at the incumbent's z) is exactly feasible and hence a valid lower bound. But src/opt/miqp.py's fixed_integer (kept core) sets only Method = 1, so it runs at Gurobi's default FeasibilityTol of 1e-6.
    - In the checker's probe inside the band, the polish returned w = b with w ≥ ℓ violated by up to 5e-7. V was then f(b) > 0 where the true value is 0: 164 big-M and 162 perspective probe points (e.g. toy G000 at δ = 5e-7, V = 2.35e-5). No flag fires.
    - In the evidence run every band polish either failed or had w = 0, so nothing reported is affected.
    - Options:
      - (a) Polish at FeasibilityTol = OptimalityTol = 1e-9, as the P-RB QP does. This is a kept-core change; logged here per rule 14.
      - (b) Check V's weights with the independent checker at 1e-9 before V is used, and count failures as excluded.
      - (c) Both.
    - Until Isaiah decides, S2 records the independent checker's verdict on every pilot V at 1e-7 and at 1e-9 (recording only; V is unchanged).
25. **Raw duals of a failed perspective relaxation.** The module drops them on failure: R082 has none recorded, although Clarabel returned them. K9 calls them a diagnostic. Should they be kept for failed relaxations too (diagnostic only, never used)?

## 2026-10-19 — S2 (Claude Code, Opus 5.5): code for the pilot and C1–C3, before `make pilot`
- **New code** (v2 files; no kept-core file changed):
  - src/opt/integer.py: solve_mip_with_cones, a line-for-line port of the kept MIQPModel.solve (polish off) that also reads the perspective model's s and ζ at the raw incumbent; cone_violation_effect = λ·Σ d_i·max(0, w_i²/ζ_i − s_i), with w²/ζ from cone_exact_s; PMI.solve(cone_diag=False by default); PMIResult.cone_effect, cone_n_capped. This is Isaiah's P4 A9 instruction.
    - Test-first. A first RED was invalid: a SyntaxError in my test file (logs/test_s2_cones_red_*.log, first run). After fixing the test, the committed integer.py was put back temporarily, giving a valid RED on the missing name (ImportError), and then the implementation, GREEN (logs/test_s2_cones_green_*.log).
    - New tests: test_cone_diag_solve_is_the_kept_solve[bigm, perspective] (bitwise equal to the kept solve), test_cone_violation_effect_formula, test_cone_violation_effect_on_r110 (round-3 Finding C toy: the effect equals U_raw − U_incumbent, and is > |V|).
  - experiments/run_pilot.py + configs/pilot.yaml (P1–P7, DESIGN §8; module docstring). Rules fixed before any pilot solve:
    - s_obj is the power of 10 that puts the geometric mean of the P3 proxies |U_mv| closest to 10, the log-centre of [1, 100]. U_mv is the P-MI objective at the P-RB solution, an upper bound on U*. Whether every proxy and every P4 V lands in [1, 100] is recorded. This is my rule; DESIGN asks only for [1, 100].
    - P4 runs under TimeLimit 300 s, because W* is unknown before P5 (DESIGN §6's fallback value), with 4 solves at once. P5's Work rate is measured under that same concurrency, as S3 will run.
    - P6 candidates: constraint keys (families and single style factors; position, liquidity and single sectors excluded), ranked by median α_mom elasticity at the I1 dates in P2. P2's solves are the same as C1's at those dates. The Mom bound at 0.025 is added. Selection keeps L > 0 in candidate order, at most 4, and a factor bound replaces the last kept one if none is kept but one has L > 0.
    - Decision 24 interim: the independent checker's verdict on every pilot V is recorded at 1e-7 and at 1e-9.
    - tests/test_pilot.py (6) covers these rules. Written after the draft, so not RED-first.
  - experiments/cont.py (shared helpers; check_p_rb refuses a continuous.yaml whose P-RB block differs from src/opt/risk_budget.py), run_c1.py, run_c2.py, run_c3.py, check_cont.py (K16, K19), configs/continuous.yaml (s_obj: null until the pilot sets it).
- **Smoke tests** (scratch, not evidence):
  - P1 at 2017-12: A 1.2e-10, λ 2.2e-8, binding duals 3.1e-6; 8 QP solves; 0.4 s.
  - P3: S = 188, 133, 158 at N = 250 (2009-03, 2017-12, 2020-03); s_obj = 1e4, with proxies scaled to 9.1–20.5.
  - One P4 perspective solve: OPTIMAL in 0.5 s.
  - C1 at 2017-12: 3 alphas, idealized, envelope ≤ 6.4e-5.
  - C2: one (date, alpha) sweep in 6 s.
  - C3 chunk; the process pool with resume.
- **Findings for Isaiah (no check affected; for GATE C):**
  - **C3 covers 240 of the 241 month-ends.** α_mom needs 252 trading days before the date, so 2005-12-30 has no momentum alpha. DESIGN §7 says "all 241 month-ends". The runner records the excluded date and the reason in c3_skipped.
  - **The risk budget can be slack under α∥.** At 2017-12, base, α∥ holds 20 names, risk_binding = false, solved at λ_min = 1e-6. The Stubbs–Vandenbussche attribution at λ = μ_risk = 1e-6 is then degenerate (total "loss" 1.3e5). C1 records it with the risk_binding flag; P2 lists every exception. Fig. 3 is α_mom only.
- **Suite:** 256 passed, 2 xfailed (logs/test_s2_pre_pilot_*.log).
- Next: commit, then `make pilot` in the background.

## 2026-10-19 — S2: pilot P1–P7 done (results/pilot/run_20261019T191206Z at 00eff1c; RUN_LOG "pilot")
- **Completion** agrees: make exit 0 (suite 256 passed, 2 xfailed), DONE present, RUN_LOG status "pilot". The pilot took 40 s; N = 250 MIQPs solve in 0.5–2 s.
- **P1 PASS** (12/12 D12 dates): A* ≤ 2.1e-10 relative (tol 1e-6); λ* vs Clarabel's risk dual ≤ 1.6e-7 (tol 1e-5); binding duals ≤ 1.8e-5 (tol 1e-4). Root-finder: 6–9 QP solves, 0.35–0.73 s per point. Clarabel AlmostSolved at 6 of 12 (accepted, DESIGN §6).
- **s_obj = 1e4.** The P3 proxies scale to 9.1–20.5; every P4 |V|·s_obj lies in [10.1, 13.6].
- **P2:** 36 solves. The risk budget is slack at 4, all α∥: 2011-08 (vol 2.61%), 2013-06 (2.31%), 2015-08 (2.70%), 2017-12 (2.21%).
- **P3:** S at (date, N):
  - 2009-03/250: 188
  - 2017-12: 100 → 50, 250 → 133, full (466) → 217
  - 2020-03: 100 → 61, 250 → 158, full (477) → 316
  - K grids are in configs/integer.yaml and numerics.yaml.
- **P4 PASS (8/8).** All 16 solves OPTIMAL at MIPGap 1e-4; 0 checker violations at 1e-7 and at 1e-9; 0 flags. |V_bigM − V_persp| is 0 at 5 instances. 2020-03 K40 tight: 8.6e-7 vs allowed 2.0e-6. 2020-03 K79 base: 4.0e-6 vs allowed 4.49e-6 (ratio 0.89, the tightest).
- **A9 finding for GATE DESIGN (P4 diagnostic, Isaiah's instruction): the perspective MIQP's cones are violated within Gurobi's tolerances by enough to distort its gap.**
  - At the raw incumbent, λ*·Σ d_i·max(0, w_i²/ζ_i − s_i) runs from 0 to 4.8e-3·|V| (median 1.7e-3) across the 8 perspective solves.
  - Gurobi measures MIPGap 1e-4 against that inflated raw value. So the perspective's B − V against the exact polished V reaches 3.4e-3·|V| (2020-03), against ≤ 1e-4 for big-M.
  - At 2020-03 the perspective stops on a support whose exact V is 0.08–0.3% below big-M's. P4 still passes, because the inflated perspective bound sets the allowance.
  - Mechanism, as in round-3 Finding C: FeasibilityTol 1e-6 is absolute, and s ~ w² is ~1e-6 to 4e-3 at these weights.
  - Relevant to N1 (DESIGN: default tolerances) and K22; a candidate topic for Q3/A9.
- **P5:** Gurobi 13.0.3; Work recorded on every solve. WorkLimit works: a P4 instance at limit 0.001 stopped with WORK_LIMIT. Work/s median 1.124 (range 1.04–1.31; 4 concurrent solves). **W* = 340.**
- **P6:**
  - Candidates by median α_mom elasticity at the I1 dates (P2): sector 0.0137, dollar 9.6e-4, then beta and gross. beta and gross are tied at median 0 with every style key, and the tie was broken alphabetically. Position and liquidity, the two largest, are excluded by the rule. The Mom bound at 0.025 is added.
  - Certified intervals (B_eff) at 2017-12, N = 250, K = 67, MIPGap 1e-6, WorkLimit 680; all 10 solves OPTIMAL:
    - sector L 1.23e-3 > 0;
    - Mom@0.025 L 1.77e-3 > 0;
    - dollar L −2.1e-5;
    - beta L −3.0e-5;
    - gross L −1.1e-6.
  - **Proposed I1 constraints: sector (b = 0.02) and Mom (b = 0.025).** A factor bound (Mom) is included. The tie-break does not matter here: the tied candidates have L ≤ 0.
- **P7** (Work at the median per solve; wall time at 4 workers; WorkLimit-capped worst case in brackets): I1 57 solves 0.005 h (2.4 h); I2 82 solves 0.007 h (3.5 h); N1 96 solves 0.008 h (2.0 h); N2(a) 16 solves 0.001 h (0.3 h). N1 Work at N = 100 and full is extrapolated from N = 250.
- **Configs:** continuous.yaml s_obj = 1e4. integer.yaml and numerics.yaml drafted, marked "proposed, pending GATE DESIGN". ECOS is not installed, so N2(b)'s solvers are Gurobi barrier, Clarabel and SCS.
- **Figures:** src/figures/fig_c.py drafts Figs. 1–3 and the C3 summary ("_preliminary" names), registered in make_all.FIGURES. The palette was validated with the dataviz validator; slots 3–4 have contrast < 3:1, so markers, line styles and hatching carry identity too. Text is 8 pt in these figures, overriding style.py's 7 pt tick and legend sizes, because DESIGN §10 says ≥ 8 pt.
- Next: commit; `make c1 c2 c3` in the background.

## 2026-10-19 — Isaiah: Decision 26 (in-session answer; recorded by Claude Code): how K15 is measured
- **The question.** C1 (run_20261019T191553Z at 12c45aa) passed 114 of 115 envelope checks to ≤ 0.19%. One missed: 2011-08 style:CMA, barely binding (e = 1.02e-4), where the central difference at δ = 1% is 2.25% off μ.
  - The CMA bound stops binding inside the step: μ(b + δ) = 0, μ(b − δ) = 5.6e-6.
  - Smaller steps converge to μ (scratch probe, results/scratch/s2_draft/probe_k15.py): 0.3% → 7.7e-5, 0.1% → 2.4e-5, 0.01% → 2.6e-6.
  - I chose δ = 1% (as in K7) before any run; K15 does not fix δ.
- **Isaiah's answer: 1% plus kink refinement.** Keep δ = 1%. Where the stencil crosses an active-set change (the constraint's dual is 0 at b + δ or b − δ, or the forward and backward differences differ by more than 1% of the central one), the point is flagged as a kink and checked at δ = 0.1%. Both values are recorded; flagged points are counted and listed. C1 is rerun at a new commit.

## 2026-10-19 — S2: C2 failed on A* = 0; K15 rule implemented; C1–C3 to rerun
- **C2 run_20261019T191622Z failed** (RUN_LOG "failed", FAILED marker), so make stopped and C3 never started.
  - Cause: src.opt.sensitivity.elasticities divided by A* = 0. Under α∥ with all styles at 0 the optimum is w = 0, with no names held and the risk budget slack. This happens at 3 of the 576 α∥ points: 2009-03, 2015-08 and 2018-12 (scratch check, results/scratch/s2_draft/c2_par_check.py).
  - Fix, test-first (RED logs/test_s2_k15_red_*.log: the ZeroDivisionError and the missing envelope_point): e_j is nan where A* = 0. sensitivity.py is an S1 file, not kept core. New test test_elasticities_undefined_at_zero_value.
- **Decision 26 implemented, test-first:** src.opt.sensitivity.envelope_point and KINK_RTOL = 1e-2; run_c1 uses it; continuous.yaml envelope_fine_step = 0.001.
  - New test test_envelope_point_refines_a_stencil_that_crosses_an_active_set_change, on the 2011-08 CMA case. The flag fires, the 1% difference misses, the 0.1% one matches, and the bounds are restored.
  - Smoke test, 2011-08: 4 of 15 binding constraints are flagged; all are within 1% after refinement (sector:3: 1.9e-3 coarse → 1.9e-11 fine).
- **C1 summary:** the idealized A* comparison is now relative only where the closed form is nonzero, absolute where it is 0. The α∥ full-neutrality case has A* = 0 both numerically and in closed form, so the old max_A_rel = 1.0 was a 0/≈0 artifact.
- C1 run_20261019T191553Z will be marked superseded by the rerun. Order: commit; `make c1`; the preliminary proposal/FACTS.md (tools/make_facts.py; generated, with sha256 per fact) and a commit; then `make c2 c3`, so that every runner starts from a clean tree.
