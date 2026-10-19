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
