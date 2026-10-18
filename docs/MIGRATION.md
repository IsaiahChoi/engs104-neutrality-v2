# MIGRATION — how this repository was extracted from v1

Source: the v1 repository at commit `05468f26bc293e16ca670bb800351507dca6739b` (clean tree; tags `hypotheses-frozen`, `pre-3b`; S0 adds `v1-final`). Extracted 2026-10-18 by Claude in chat from the uploaded repo zip and data backup.

## 1. Verified at extraction

- All 507 raw data files in the repo zip and in `data_raw_backup.zip` match the sha256 values recorded in v1's `data/processed/build_meta.json` (no missing, extra, or mismatched files). That manifest is committed here as `data/MANIFEST_data.json`; the risk-model metadata as `data/MANIFEST_risk.json`.
- The kept core (`src/data`, `src/risk`, `src/alpha`, `src/opt` minus `lambda_policy.py`) imports nothing from `experiments/`, `tools/check_frozen.py`, or `results/`. Only `src/figures` (v1 figure scripts) and the v1 runners did.
- The Makefile already carried per-recipe `pipefail` in v1 (commit e890448). The v2 Makefile keeps it and has no target that downloads data.
- Not verifiable here (no Gurobi license or network in the extraction sandbox): the test suite, the panel content hash, the license check. S1 runs them (CHECKS K1–K3).

## 2. Files

**Kept unchanged:**
- `.python-version`, `pyproject.toml`, `uv.lock`;
- `src/__init__.py`, `src/utils.py`;
- `src/data/*`, `src/risk/*`, `src/alpha/*`;
- `src/opt/{__init__,attribution,continuous,feasibility,gurobi_env,inputs,miqp}.py`;
- `src/figures/{__init__,style,fig_bias}.py`;
- `tests/{__init__,test_data,test_environment,test_miqp,test_risk}.py`;
- `tools/{__init__,page_count,check_gurobi_size}.py`, `tools/latex_smoke/ieee_smoke.tex`;
- `experiments/__init__.py`, `experiments/configs/{base_mandate,risk}.yaml`;
- `results/data_report.md`, `results/risk/bias_w252_20261016T062739Z.{parquet,_summary.json}`;
- `docs/AI_USE.md` (a v2 section appended); `docs/course/ENGS104_Project.pdf`.

**The one edit:** `tests/test_opt.py` had six v1-only items removed (unchanged copies in `reference/v1/tests/removed_from_test_opt.py`):
- `test_lambda_calibration_target_and_fallback` and the `temp_book` fixture (v1 λ book);
- `test_lambda_held_fixed_across_sweep_and_e2_configurations`;
- `test_alpha_seed_is_one_value_everywhere`;
- `test_e3_subsample_alpha_options`;
- `test_e1_runner_shadow_prices_at_swept_caps` (v1 runners; this last one must be re-created for v2, CHECKS K12).

Nothing else in the file changed; it still parses, and no remaining test references `experiments` or `lambda_policy`.

**New for v2:** `CLAUDE.md`, `README.md`, `Makefile`, `.gitignore` (v1's plus additions), `.claude/settings.json`, `.claude/agents/{result-checker,cold-reader}.md`, `docs/{DESIGN,CHECKS,RUNBOOK,MIGRATION}.md`, `docs/course/{ENGS104_Syllabus,ENGS_104_Overview}.pdf`, `PROGRESS.md`, `results/RUN_LOG.csv` (header plus two import rows), `reference/v1/` (read-only copies), empty `logs/ results/scratch/ figures/ report/ proposal/` with `.gitkeep`.

**Left in v1 only:**
- The v1 governance: `hypotheses*.md`, `PLAN.md`, `PROGRESS.md`, `docs/{PROJECT_BRIEF,GATE_CRITERIA,CHAT_EXPORT}.md`, `SETUP.md`, the gate-verifier agent, `tools/check_frozen.py`.
- All v1 results (`results/rq1–rq3`, `lambda`, `verification`, `scratch`), the v1 figures, and the v1 proposal draft.
- `experiments/run_rq2.py`, `analyze_rq1.py`, `analyze_rq2.py`, `run_prelim.py`, configs `rq1–rq3.yaml` and `prelim.yaml`.
- `logs/`, `.venv/`, `.pytest_cache/`, `__pycache__/`, `.DS_Store`, `.claude/settings.local.json` (machine-specific).

## 3. Small fixes for S1 (logged in PROGRESS.md when done)

1. `tools/page_count.py` prints a warning but exits 0 when the page count is out of range; make it exit 1.
2. `tools/verify_data.py` (new, read-only), as the Makefile `data-verify` target expects: compare `data/raw` with `data/MANIFEST_data.json`, and `data/processed/build_meta.json` with the manifest's raw hashes and panel hash.
3. `experiments/configs/base_mandate.yaml` keeps v1's `risk_aversion` block (fallback rule, bracket). Add a `risk_budget` block for P-RB (target 0.03, λ_min 1e-6, root tolerance 1e-10) and mark the fallback fields unused in v2.
4. Port the v1 infrastructure listed in `reference/v1/README.md` and DESIGN §12.
