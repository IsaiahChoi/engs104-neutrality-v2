# Makefile (v2) — single entry point. Runner modules and tools marked (S1)/(S2) are created by
# Claude Code in those sessions (docs/RUNBOOK.md). make 3.81 ignores .SHELLFLAGS, so every piped
# recipe line starts with `set -o pipefail;` and a failing runner makes `make` fail.
SHELL := /bin/bash
PY := uv run python
MODE ?= draft
RUNNERS := core pilot pilot_s2b pilot_s2d c1 c2 c3 i1 i2 n1 n2
RUNARGS ?=

.PHONY: help setup check-license test data-verify risk-verify $(RUNNERS) figures proposal report spec-check

help:
	@echo 'Targets: setup check-license test data-verify risk-verify $(RUNNERS) figures proposal report spec-check [MODE=draft|final]'

setup:
	uv sync

check-license:
	$(PY) tools/check_gurobi_size.py

test:
	uv run pytest -q

# Read-only data checks. The data are never downloaded again: there is deliberately no target
# that runs src.data.build_all without --offline.
data-verify:
	$(PY) tools/verify_data.py                                  # (S1)
	uv run pytest -q tests/test_data.py -k "rebuild_from_cache_is_identical or raw_hashes_recorded"

risk-verify:
	uv run pytest -q tests/test_risk.py -k "built_model_every_date or built_model_reestimates_identically"

# Experiments: tests first, then the runner; one timestamped log per run. RUNARGS passes runner
# arguments, e.g. make i1 RUNARGS="--config experiments/configs/smoke_i1.yaml" (S2d smoke runs).
$(RUNNERS): test
	mkdir -p logs
	set -o pipefail; $(PY) -m experiments.run_$@ $(RUNARGS) 2>&1 | tee logs/$@_$$(date -u +%Y%m%dT%H%M%SZ).log   # (S1/S2)

figures:
	$(PY) -m src.figures.make_all                               # (S1) also writes report/numbers.tex

proposal:
	cd proposal && tectonic proposal.tex
	$(PY) tools/page_count.py proposal/proposal.pdf --min 1 --max 2
	$(PY) tools/spec_check.py --target proposal --mode $(MODE)  # (S1)

report: figures
	cd report && tectonic main.tex
	$(PY) tools/page_count.py report/main.pdf --min 1 --max 8
	$(PY) tools/spec_check.py --target report --mode $(MODE)    # (S1)

spec-check:
	$(PY) tools/spec_check.py --target report --mode $(MODE)
	$(PY) tools/spec_check.py --target proposal --mode $(MODE)
