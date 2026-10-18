# reference/v1 — read-only copies of v1 code

Copied unchanged from the v1 repository at commit 05468f2 (tag `v1-final`). Nothing here is imported, collected by pytest, or edited (`.claude/settings.json` denies edits). Port what you need into `src/` or `experiments/`, with tests, and record the port in PROGRESS.md. Most files depend on v1-only machinery (the freeze guard `tools/check_frozen.py` and the fixed-λ book `src/opt/lambda_policy.py`); remove those dependencies when porting.

| File | Worth porting |
|---|---|
| `experiments/common.py` | Run directories, resume-on-crash, write-once chunks, DONE marker, provenance, RUN_LOG rows |
| `experiments/designs.py` | Month → rebalance-date resolution; config loading |
| `experiments/run_rq1.py` | Sweep machinery: `build`, `snapshot`, `apply_point`, `reset`; shadow prices recorded *before* resetting swept caps |
| `experiments/check_rq1_envelope.py` | Finite-difference envelope self-check |
| `experiments/run_rq3.py` | `subsample` (top-N by 63-day ADV, `restrict` alpha), `restricted`, `miqp_mandate`; H3/F4 loop structure; failed relaxations recorded, not fatal |
| `experiments/analyze_rq3.py` | Q8-style formulation agreement check (fix its 0/0 handling) |
| `experiments/run_calibration.py` | λ calibration records (v2 replaces fixed λ by a root-found λ per point) |
| `src/opt/lambda_policy.py` | v1 fixed-λ book; reference only |
| `src/figures/*.py` | Layouts of v1 F1, F2, F4, F5 and the table generator |
| `results/scratch/q8_numerics_diag.py` | The diagnosis of v1's MIQP failure (objective scale vs absolute tolerances); basis for N2 |
| `results/scratch/rootgap_check.py` | Root-gap measurement cross-check |
| `tests/removed_from_test_opt.py` | Six tests removed at extraction; the last one guards a real bug (port it: CHECKS K12) |
