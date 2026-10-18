"""Shared helpers: repository paths, git provenance, and the run log (CLAUDE.md rule 6)."""
from __future__ import annotations

import csv
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
RUN_LOG = RESULTS / "RUN_LOG.csv"
RUN_LOG_HEADER = ["timestamp", "git_commit", "config_path", "status", "output_path", "notes"]


def git_commit() -> str:
    """Current HEAD commit, with a '-dirty' suffix if tracked files outside results/ (code,
    configs, docs) have uncommitted changes. Generated outputs in results/ do not count."""
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    if head.returncode != 0:
        return "unknown"
    dirty = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", ".", ":(exclude)results"],
                           cwd=ROOT).returncode != 0
    return head.stdout.strip() + ("-dirty" if dirty else "")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_run_log(config_path: str, status: str, output_path: str, notes: str = "",
                   commit: str | None = None) -> None:
    """Append one row to results/RUN_LOG.csv (successes and failures alike). `commit` is the code
    commit that ran; default: the current HEAD (right for short runs; long runs pass the commit
    recorded when they started, since HEAD can move while they run)."""
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not RUN_LOG.exists()
    with RUN_LOG.open("a", newline="") as f:
        writer = csv.writer(f)
        if new:
            writer.writerow(RUN_LOG_HEADER)
        out = Path(output_path)
        if out.is_absolute() and out.is_relative_to(ROOT):
            output_path = str(out.relative_to(ROOT))
        writer.writerow([utc_timestamp(), commit or git_commit(), config_path, status, output_path,
                         notes])
