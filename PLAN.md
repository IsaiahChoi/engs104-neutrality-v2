# PLAN (v2) — phases and tasks

From docs/RUNBOOK.md §1 (calendar) and §4 (session prompts). Claude Code ticks tasks and CHECKs; **only Isaiah ticks GATEs**. Precedence: CHECKS > DESIGN > RUNBOOK > PLAN. Evidence for every tick is in PROGRESS.md and results/.

## S0 — Pre-flight (Isaiah, Sun 10/18)
- [x] v1 tagged `v1-final` and archived; v2 unpacked; data copied and verified; `uv sync`; first commit, tag `v2-start` (RUNBOOK §3; PROGRESS 2026-10-18)

## S1 — Verify the kept core, port v1 infrastructure, v2 foundations (Claude Code, Sun 10/18)
- [x] 0. Audit: ECC_SESSION_START_CONTEXT, active hooks, clean tree at v2-start, `make check-license`
- [x] 1. tools/verify_data.py; `make data-verify`, `make risk-verify`, `make test`; counts in PROGRESS
- [x] 2. MIGRATION §3 items 1 (page_count exit 1) and 3 (risk_budget block)
- [x] 3. Ports with tests: experiments/common.py (no freeze guard, no λ book), designs.py, sweep machinery + K12 regression, instances.py (subsample, restricted), check_envelope.py
- [x] 4. v2 foundations with tests first: P-RB root-found QP + Clarabel cross-check; λ*; P-MI scaling, V, both relaxation duals (failures recorded); decomposition, φ, normalization; elasticities; closed-form predictor; certified intervals; Work/WorkLimit (confirmed); feasibility checker for P-RB and P-MI; runners refuse a dirty tree (K4–K13)
- [x] 5. tools/spec_check.py; scaffolds proposal/proposal.tex, report/main.tex, report/refs.bib; src/figures/make_all.py → report/numbers.tex
- [x] 6. This PLAN; python-reviewer review saved to results/checks/code_review_S1_<UTC>.md; clear bugs fixed, the rest listed in PROGRESS
- [ ] 7. **CHECK CORE** (K1–K13) by the result-checker — round 1 FAIL (K8, K9; results/checks/CORE_20261019T010452Z.md); stopped on a CHECKS–DESIGN conflict, awaiting Isaiah (PROGRESS Decisions 10–12)
- [ ] 8. S1 entry in PROGRESS; commit; continue with S2 if CHECK CORE is PASS

## S2 — Design pilot and continuous experiments (Claude Code, Sun 10/18 night, inside S1)
- [ ] 1. Pilot P1–P7 (DESIGN §8) → results/pilot/<UTC>/, RUN_LOG status "pilot"; stop after the pilot if P1 or P4 fails
- [ ] 2. experiments/configs/continuous.yaml (P-RB settings, s_obj); integer.yaml and numerics.yaml drafted "proposed, pending GATE DESIGN"
- [ ] 3. C1, C2, C3 via `make c1 c2 c3` in the background (≤ 4 workers)
- [ ] 4. Figs. 1–3 and the C3 summary, "preliminary" in file names until GATE C
- [ ] 5. proposal/FACTS.md (each fact with source file and sha256)
- [ ] 6. **CHECK CONT** (K14–K21) by the result-checker
- [ ] Stop at GATE C with the pilot table, proposed I1/N1 parameters, C1/C2 headlines, the CHECK CONT verdict, the S3 projection

## GATE C — Isaiah (Mon 10/19)
- [ ] GATE C note in PROGRESS (pilot P1/P4; continuous results sound; proposed parameters noted)

## Proposal — Isaiah (Mon 10/19 – Thu 10/22)
- [ ] Written by Isaiah from proposal/FACTS.md inside the scaffold; `make proposal`; spec_check --target proposal --mode final; submitted Thu 10/22
- [ ] Discussion with an instructor (Fri 10/23)

## GATE DESIGN — Isaiah (Fri 10/23)
- [ ] GATE DESIGN note: instructor feedback; integer.yaml / numerics.yaml approved or changed; run S3

## S3 — Integer sensitivity, formulations, numerics (Claude Code, Fri 10/23 – Sun 10/25)
- [ ] 1. Finalize integer.yaml and numerics.yaml per the GATE DESIGN note (DESIGN edits proposed and approved first); commit
- [ ] 2. I1, I2, N1 (+ presolve-off robustness), N2 (≤ 4 workers; Work is the effort metric)
- [ ] 3. Analysis per DESIGN §7 (estimator errors with n, certified intervals, non-binding breakdown, convex baseline; root gaps and Work; numerics tables)
- [ ] 4. Figs. 4–5, Tables II–III; finalize Figs. 1–3
- [ ] 5. python-reviewer review of the S3 code saved under results/checks/
- [ ] 6. **CHECK INT** (K22–K29); stop if K22 or K23 is BLOCKED
- [ ] Stop at GATE I with headlines (n, source files), the verdict, surprises, open questions

## GATE I — Isaiah (Mon 10/26)
- [ ] GATE I note: AI-use policy answer and source; writing mode A or B

## S4 — Report build (Claude Code, Mon 10/26)
- [ ] 1. Writing mode per DESIGN §11.6 (default B)
- [ ] 2. report/main.tex per DESIGN §11 (sections, A1–A9, figures and tables, disclosures; outlines by mode)
- [ ] 3. numbers.tex: every number a macro with source file and sha256; design constants from the configs
- [ ] 4. `make figures && make report`; spec_check report (draft) and proposal (final)
- [ ] 5. **CHECK REPORT** (K30–K39, draft mode); cold-reader saved to results/checks/cold_read_<UTC>.md
- [ ] Stop at GATE R with the spec_check table, verdict, cold-read top five, page count by section, open items

## GATE R — Isaiah (10/27 – 10/30)
- [ ] GATE R note: derivations done (RUNBOOK §5.3); open items

## S5 — Integration passes (Claude Code, 11/2 – 11/12, repeatable)
- [ ] Pass 1: regenerate, spec_check, CHECK REPORT (K30–K40), literal list, claims table, cold read
- [ ] Pass 2: same

## FINAL — Isaiah (Mon 11/16)
- [ ] FINAL note: all sections written, no TODOs, references verified, AI-use paragraph verified

## S6 — Final build and submission package (Claude Code, Mon 11/16)
- [ ] 1. Clean-checkout build; byte-identical figures and numbers.tex; same page count and text
- [ ] 2. spec_check report and proposal (final); CHECK REPORT (final)
- [ ] 3. Compliance matrix walk (RUNBOOK §8)
- [ ] 4. SUBMISSION.md
- [ ] 5. Commit and stop (no tag, no push)

## Submit — Isaiah (Fri 11/20)
- [ ] Tag `report-submitted`, push, upload the PDF
