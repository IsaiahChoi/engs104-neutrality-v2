# CHECKS — acceptance criteria (v2)

Owner: Isaiah only; Claude Code never edits this file. The `result-checker` subagent evaluates the checks for a phase by recomputing from outputs and inputs, and writes `results/checks/<phase>_<UTC stamp>.md` ending in `VERDICT: PASS | FAIL | BLOCKED`. A check that can't be evaluated is BLOCKED, never PASS. On FAIL, the builder fixes and re-checks, at most 3 rounds, then stops. Tolerances below are relative unless stated.

These checks verify that the numbers are real, reproducible, and consistent with theory. None of them concerns whether a result is interesting.

## CORE (session S1: restructure and v2 foundations)

| ID | Check | Criterion |
|---|---|---|
| K1 | Test suite and import integrity | `make test` passes; the count is reported. `git diff v2-start -- tests/` shows only additions, never a removed test or a weakened assertion. `git diff v2-start -- reference/` is empty. Every change to a kept-core file since `v2-start` is listed in PROGRESS.md with its reason |
| K2 | Data integrity | Every file in data/raw matches data/MANIFEST_data.json (sha256, no missing or extra files); the panel's content hash (`src.data.panel.panel_hash`) matches the manifest; the offline rebuild is identical; data/processed/risk/w252_meta.json matches data/MANIFEST_risk.json except timestamps |
| K3 | License | `make check-license` exits 0 |
| K4 | Risk budget ↔ mean-variance (A1) | On ≥ 3 dates at base: the root-found QP and the Clarabel QCQP give ‖Δw‖₁/‖w‖₁ ≤ 1e-5 and A* within 1e-7; λ* equals Clarabel's (unscaled) risk-row dual within 1e-5; the root-found volatility is within 1e-10 of 3%/yr |
| K5 | Alpha decomposition (A4) | ‖BᵀD⁻¹α⊥‖ ≤ 1e-10·‖BᵀD⁻¹α‖; α⊥ + α∥ = α to 1e-14 relative before normalization (floating point); for α⊥ under the risk budget alone, max \|y_k\| ≤ 1e-8 and every factor-bound elasticity ≤ 1e-6; αᵀΣ⁻¹α = α⊥ᵀD⁻¹α⊥ + α∥ᵀΣ⁻¹α∥ to 1e-10 |
| K6 | Closed forms (A2, A3) | Equality-constrained, risk-binding instances on ≥ 3 dates: numerical A* and w match the closed form to 1e-6; TC equals the retained fraction to 1e-6; under full factor neutrality the retained fraction equals √(1 − φ) to 1e-6 |
| K7 | Envelope (A5) | P-RB at base on 2 dates: for every constraint with e_j ≥ 1e-4, the central-difference slope (δ = 1% of the bound) matches μ_j within 1% |
| K8 | Scaling invariance (A9) | Scaled and unscaled P-RB (Clarabel cross-check) give the same w to 1e-6 relative L1 (Clarabel's weight precision; K4 allows 1e-5); P-MI scaled and unscaled, solved to MIPGap 0 on two small real-data instances fixed in advance (2017-12 and 2020-03; the top 30 names by ADV; u = 6%, ℓ = 0.25%, K = round(0.5·S); base mandate), give the same z and w within 1e-7; P-MI duals (big-M relaxation and fixed-integer QP) scale by the factor to 1e-6 relative, and the perspective relaxation's optimal value scales to 1e-9 relative (its slope is checked in K29c) (the Clarabel P-RB cross-check's duals are checked against the exact primary path in P1, within 1e-4); unscaling round-trips. The degenerate synthetic instance (n = 20, u = 20%) is run and its dual-accuracy floor reported as a diagnostic, not gated |
| K9 | Toy MIQP (A7) | The one-asset value function on a 41-point grid matches the closed form, including the jump at ℓ, to 1e-8; the big-M relaxation dual and the fixed-integer dual match their closed forms to 1e-6 relative; the perspective relaxation's optimal value matches its closed form to 1e-9 relative (its slope is checked in K29c); Clarabel's raw perspective duals and statuses are recorded as a diagnostic. Random toys use a recorded seed |
| K10 | Certified interval (A8) | On the toy and on 2 small MIQPs solved to MIPGap 0, every interval contains the exact slope; flags for H < 0 work on a constructed case |
| K11 | Feasibility checker | Shares no code with the optimizer; covers the risk row, every mandate constraint, cardinality, minimum position, and linking; passes on every S1 solution and fails on 3 constructed violations |
| K12 | Swept-cap shadow prices (ported v1 regression) | In the v2 sweep runner, at swept u and θ values, the recorded position and liquidity shadow prices match central finite differences of the objective within 1% (at least 2 binding points checked) |
| K13 | Consistency chain | P-MI with K ≥ N and ℓ = 0 equals mean-variance at λ*, which equals P-RB at u = 6%, to 1e-6 on 2 instances |

## CONT (session S2: pilot and continuous experiments)

| ID | Check | Criterion |
|---|---|---|
| K14 | Solve status | Every C1–C3 solve is optimal, or flagged with a reason; the independent feasibility checker passes on every solution |
| K15 | Envelope on C1 | Every constraint with e_j ≥ 1e-4 at every D12 date (α_mom): the finite-difference slope matches μ_j within 1% |
| K16 | Solver cross-check | 30 random C1/C2 solves: \|ΔA*\| between the root-found QP and the Clarabel QCQP ≤ 1e-6 (relative) |
| K17 | Theory shape (A5) | Along every C2 sweep, A* is nondecreasing as the bound loosens (tolerance 1e-8·A*), and successive secant slopes are nonincreasing in b (concavity of the convex value function) within 1e-6·A* per unit of bound |
| K18 | Attribution identity | Attributed losses plus any stated residual sum to A*(unconstrained) − A*(base) to 1e-8, per the identity attribution.py claims |
| K19 | Reproducibility | 5 random C solves rerun at the same commit match to 1e-10 |
| K20 | Pilot completeness | P1–P7 each answered with numbers and source files; P4 passed (else BLOCKED) |
| K21 | Risk flag | Each solve records whether the risk row binds; at base, exceptions are listed |

## INT (session S3: integer sensitivity, formulations, numerics)

| ID | Check | Criterion |
|---|---|---|
| K22 | Formulation agreement | Every N1 instance where both formulations reach the gap: \|V_bigM − V_persp\| ≤ the larger of the two certified gaps B_eff − V, with B_eff = max(B, V) + 1e-6·|V| (DESIGN §6). Any failure → BLOCKED |
| K23 | Certified intervals | Every I1 case has [L, H], computed with B_eff = max(B, V) + 1e-6·|V|; no case has H < 0 (else BLOCKED, as solver error) |
| K24 | Perspective tightness (A6) | On every N1 instance, the perspective root bound ≤ the big-M root bound + 1e-8·\|V\| (maximization) |
| K25 | Determinism | 3 N1 instances rerun under WorkLimit give identical Work, node count, and incumbent value |
| K26 | MIQP feasibility | The independent checker passes on every incumbent (cardinality, minimum position, linking, mandate) |
| K27 | Convex baseline | In I1 and I2, the continuous-baseline dual matches its slope within 1% wherever it binds |
| K28 | Counts | Every I1 statistic reports n; excluded and non-binding cases are counted with the breakdown in DESIGN §7; nothing is dropped silently |
| K29 | Provenance | Every S3 run has a RUN_LOG row at a clean commit with the scale factors, settings, and worker count; output hashes recorded |
| K29b | Production dual accuracy | On the first 3 I1 instances by sorted instance id, perspective-relaxation slopes (K29c method) at s_obj and 10·s_obj agree to 1e-5 relative; Clarabel status, residuals, and raw duals are recorded for every relaxation; failed relaxations and flagged kinks are counted; if more than 10% of I1 perspective relaxations fail, flag it at GATE I |
| K29c | Perspective slope method (gates I1) | Before I1 runs: the perspective-relaxation slope, a central finite difference of Clarabel's optimal values with δ_r = 1e-3·b (DESIGN §6), matches the toy closed forms to 1e-6 relative on a seeded family of at least 200 random toys (points within 2δ_r of a kink are checked by their one-sided slopes instead), and agrees across s_obj ∈ {1, 1e2, 1e4} to 1e-6 relative on the K8 instances. Raw Clarabel duals are compared and reported as a diagnostic |

## REPORT (sessions S4–S6)

| ID | Check | Criterion |
|---|---|---|
| K30 | Spec check | `tools/spec_check.py` passes in the stated mode for report and proposal |
| K31 | No hand-typed numbers | Every numeric literal in prose is a numbers.tex macro or sits in a generated table (equation, section, and citation-year numerals excepted) |
| K32 | Macro provenance | Every macro recomputes from its named source; its sha256 comment matches |
| K33 | Regeneration | `make figures` regenerates every figure, table, and numbers.tex byte-identically |
| K34 | Claims table | Every result claim in the Abstract, Introduction, Discussion, and Conclusion maps to a macro, figure, table, or result file; unmapped claims listed (FAIL in final mode if any) |
| K35 | Sample statements | Every statistic in Results states its instance set and n; every Results subsection opens with setup, instances, and evaluation criterion |
| K36 | Disclosures | Every item in DESIGN §11.5 present |
| K37 | Coverage | Discussion (prose or outline) covers every item in DESIGN §11.4; Sections II–III contain DESIGN §11.3 items and A1–A9 |
| K38 | References | Every `\cite` resolves; refs.bib ⊆ DESIGN §13; final mode: every entry `% verified: yes` |
| K39 | No v1 numbers | No number in the report or proposal traces to a v1 result or to reference/v1 |
| K40 | Cold read | A cold-read report exists for the current build |
