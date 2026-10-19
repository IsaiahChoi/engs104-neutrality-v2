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
