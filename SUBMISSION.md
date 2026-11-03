# SUBMISSION — ENGS 104 final report, "The Shadow Price of Neutrality"

Written by Claude Code (Opus 5.5) in session S6, 2026-11-03, under Isaiah's note "— Isaiah: S5 pass 3 read; final edits; II–IV approved (Decision 65); FINAL; run S6" (0f41969). Not tagged, not pushed: Isaiah tags `report-submitted`, pushes, and uploads the PDF (by Fri 2026-11-20).

**One item to confirm before tagging:** compliance-matrix row P0. Its "discussed with an instructor" element has no record in the repo (see below). The row concerns the proposal, which was accepted on 2026-10-24, and nothing in the report depends on it.

## Build
| Item | Value |
|---|---|
| Commit (the build) | `6fac8de9db4674c6b3e5f874429ec4ed1d6d1b88` (S6 steps 1–2). The S6 closing commit that adds this file changes only SUBMISSION.md, PLAN.md, PROGRESS.md and results/checks/; report/ is unchanged |
| PDF | `report/main.pdf`, sha256 `f0129e05b2cc25401ab8ea7b95cc8303f26fa257ecffab85ad0e9656ecd6e56c` |
| Source | `report/main.tex`, sha256 `5caf80c2dd4a86aa958294d08459ca1ac181e6a5725378a562e84b3a45949850`: Isaiah's FINAL text, unchanged in S6 (no mechanical LaTeX fix was needed) |
| Pages | **9 in total**. **Text before the references: 7.76 pages**, ending on page 8 (refs:start on page 8; page 9 is references only). The references do not count toward the 8 (Decision 63, Prof. Ferguson). Sources: RP-4/RP-5 and tools/page_sections.py (results/scratch/s6/pages_s6.txt) |
| Test suite | 574 passed, 1 skipped, 2 xfailed (logs/test_full_s6_20261103T203050Z.log; \TestsPassed = 574) |

**Build command** (from the repo root, with the gitignored data/raw/, data/processed/ and logs/ present):

```
uv sync --offline --frozen
make test
make figures
make report
uv run python tools/spec_check.py --target report --mode final
uv run python tools/spec_check.py --target proposal --mode final
```

`make figures` regenerates every figure, table and report/numbers.tex byte-identically. Twice in the working repo, once in a clean clone, and twice in the checker's clone, all 21 tracked outputs were sha-identical.

tectonic rebuilds of the PDF are not byte-identical, but they agree on page count and extracted text: the ec2cca5 build (d2c99bfd…), this build (f0129e05…), the S6 clean-clone build and the checker's clone build all have 9 pages and identical pypdf text on every page. A final-mode spec_check rebuilds the PDF (RP-1), so running it changes main.pdf's bytes again.

## Verification
| Step | Result | Record |
|---|---|---|
| 0. Suite; `make figures` ×2; `make report` | PASS: 574 passed. Figures byte-identical across runs. Only \TestsPassed's source comment changed (value 574). RP-4 PASS | PROGRESS S6 step-0 entry; commit ec2cca5 |
| 1. Clean-checkout build of ec2cca5 | PASS. Inputs supplied: data/raw/, data/processed/, logs/, with no .lic. `make test` 574 passed; 21 outputs byte-identical; PDF 9 = 9 pages with identical text | PROGRESS S6 steps 1–2 entry; results/scratch/s6/ |
| 2a. spec_check, final mode | Report PASS (RP-1–RP-11); proposal PASS (PR-1–PR-5) | results/scratch/s6/spec_report_final.txt, spec_proposal_final.txt |
| 2b. CHECK REPORT (K30–K40), final mode | **PASS**, with no FAIL item | results/checks/REPORT_20261103T204948Z.md |
| 2c. Cold read of this PDF (K40) | MOSTLY | results/checks/cold_read_20261103T204218Z.md |
| 3. RUNBOOK §8 compliance matrix | 15 of 16 rows met with evidence. P0 is met except "discussed with an instructor" (open for Isaiah) | results/checks/S6_matrix_20261103T205701Z.md |

## Headline results (every number is a numbers.tex macro; the source files are named in numbers.tex with their sha256)
| Claim (Abstract / Conclusion) | Value | Source file |
|---|---|---|
| Risk budget | \RiskBudgetPct = 3 %/yr | experiments/configs/base_mandate.yaml |
| The liquidity cap has the largest marginal cost (median elasticity) | \ELiqMed = 0.16 | results/c1/run_20261019T192500Z/c1_points.parquet |
| Trading and borrow, as shares of gross alpha | \SplitTradeMed = 0.16, \SplitBorrowMed = 0.039 | results/c1/run_20261019T192500Z/c1_weights.parquet |
| Idealized full factor neutrality keeps at least this fraction of the unconstrained, costless optimum | \IdealRetMomMin = 0.964 | results/c1/run_20261019T192500Z/c1_idealized.parquet |
| Mom at zero (the costliest single factor bound) keeps | \CTwoMomTight = 0.968 | results/c2/run_20261019T192722Z/c2_points.parquet |
| Fixed-integer dual error with holdings and active set fixed: maximum (n) | \PredOneMax = 6.7×10⁻¹² (\PredOneN = 7) | results/s3b_analysis/s3b_analysis.json |
| Fixed-integer dual error once the holdings change (median) | \PredThreeMed = 0.056 | results/s3b_analysis/s3b_analysis.json |
| Forced outer approximation reproduces the default-scaling perspective root bound | \NThreeEOneDef = 29 of \NThreeN = 36 instances | results/n3/run_20261024T092033Z/summary.json |

CHECK REPORT K32 recomputed every macro used in the Abstract, I, V and VI independently from raw outputs, and all agree at the printed rounding.

## Disclosure checklist (DESIGN §11.5; K36 PASS)
| # | Disclosure | Where it appears |
|---|---|---|
| 1 | Current S&P 500 constituents (survivorship, look-ahead); GICS sectors not point-in-time | Disclosures and AI-Use Acknowledgment (main.tex:283) |
| 2 | Yahoo adjusted data; JCI and DHR masked; the $1M valid-day and 80% window rules; multi-session returns (\MultiSessionReturns = 1) | Disclosures (main.tex:283); the rules in II-B "Data and risk model" (main.tex:63) |
| 3 | One-pass winsorization leaves \|z\| above 3 (maximum \DisclosureMaxZ = 5.47) | Disclosures (main.tex:283) |
| 4 | Single period, w₀ = 0; borrow and trading costs are assumptions | Disclosures (main.tex:283) |
| 5 | No backtest, no performance claims; the alpha is a simple input signal | Disclosures (main.tex:283) |
| 6 | The parameter-setting rules (DESIGN §8) | Disclosures (main.tex:283), pointing to Sec. III |
| 7 | The AI-assisted workflow | AI-use acknowledgment (main.tex:286); agrees with docs/AI_USE.md |
| 8 | The earlier iteration, without numbers | Disclosures (main.tex:283); V (main.tex:271) |

## Compliance-matrix result (RUNBOOK §8; results/checks/S6_matrix_20261103T205701Z.md)
- **Met with evidence: 15 of 16 rows.** G1–G7, P1–P6, R0, R1, R2–R8, R9, C1–C4, C5 and C6.
- **P0: met except one element.** "LaTeX, 1–2 pages" and "submitted" have evidence (PR-1, PR-2; accepted 2026-10-24, PROGRESS:2144). **"Discussed with an instructor" has no record in the repo.** The 10/21 Fügenschuh meeting did not take place (PROGRESS:2140), and no note records the 10/23 class discussion or another discussion of the proposal. Isaiah to confirm.

## Not in this package
- **proposal/proposal.pdf** sits untracked in the working tree, written by the final-mode proposal spec_check (PR-1). It is not part of the submission. The submitted proposal is the one recorded at PROGRESS:2144 (sha256 6a87bf00…).
- **Optional wording notes O1–O3** for Isaiah's judgement (main.tex:35/48, 277, 268) are in REPORT_20261103T204948Z.md. None is required, and none was applied.
