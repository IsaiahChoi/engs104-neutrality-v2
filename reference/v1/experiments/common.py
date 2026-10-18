"""Shared machinery for the hypothesis runners (run_rq1/2/3): run directories, checkpoints,
metadata, the run log.

A run lives in results/<rq>/run_<UTC>/. Each finished chunk (a date, a month, an instance) is
one parquet file written once and never overwritten; a crashed run resumes in the same
directory, skipping finished chunks, but only if the config hash and code commit match
(`run_meta.json`). When every chunk is done, `combine` writes the run's combined files and a
DONE marker.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import yaml

from src.opt.lambda_policy import LambdaBook
from src.utils import RESULTS, ROOT, append_run_log, git_commit, utc_timestamp
from tools.check_frozen import require_frozen


def config_hash(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def open_run(rq: str, config_path: str, extra_meta: dict | None = None) -> tuple[Path, dict]:
    """Require the freeze; resume the newest unfinished run with the same config and code, or
    start a new one. Returns (run directory, metadata)."""
    frozen = require_frozen()
    commit = git_commit()
    if commit.endswith("-dirty"):
        raise RuntimeError("hypothesis runs need a clean tree (commit code and configs first)")
    cfg_hash = config_hash(config_path)
    base = RESULTS / rq
    base.mkdir(parents=True, exist_ok=True)
    for d in sorted(base.glob("run_*"), reverse=True):
        meta_path = d / "run_meta.json"
        if (d / "DONE").exists() or not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        if meta["config_sha256"] == cfg_hash and meta["git_commit"] == commit:
            print(f"resuming {d.name}")
            return d, meta
    book = LambdaBook.latest()
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    d = base / f"run_{stamp}"
    d.mkdir()
    meta = {"rq": rq, "created_utc": utc_timestamp(), "git_commit": commit,
            "frozen_commit": frozen, "config_path": config_path, "config_sha256": cfg_hash,
            "config": yaml.safe_load(open(ROOT / config_path)),
            "lambda_book": str(book.path.relative_to(ROOT)), "lambda_book_sha256": book.sha256,
            **(extra_meta or {})}
    (d / "run_meta.json").write_text(json.dumps(meta, indent=1, default=str))
    append_run_log(config_path, "started", str(d), f"{rq} run {d.name}")
    return d, meta


def chunk_path(run: Path, kind: str, key: str) -> Path:
    p = run / "chunks" / kind
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{key}.parquet"


def write_chunk(path: Path, df: pd.DataFrame) -> None:
    if path.exists():
        raise FileExistsError(path)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.rename(path)


def combine(run: Path, kind: str) -> pd.DataFrame:
    files = sorted((run / "chunks" / kind).glob("*.parquet"))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True) if files else pd.DataFrame()


def run_commit(run: Path | None) -> str | None:
    """The code commit recorded when the run started (HEAD may have moved since)."""
    meta = run / "run_meta.json" if run else None
    return json.loads(meta.read_text())["git_commit"] if meta and meta.exists() else None


def finish(run: Path, config_path: str, outputs: dict[str, pd.DataFrame], note: str) -> None:
    for name, df in outputs.items():
        out = run / f"{name}.parquet"
        if out.exists():
            raise FileExistsError(out)
        df.to_parquet(out, index=False)
    (run / "DONE").write_text(utc_timestamp() + "\n")
    append_run_log(config_path, "ok", str(run), note, commit=run_commit(run))


def fail(run: Path | None, config_path: str, err: Exception) -> None:
    append_run_log(config_path, "failed", str(run) if run else "", f"{type(err).__name__}: {err}",
                   commit=run_commit(run))


def log_timing(config_path: str, note: str) -> None:
    """Every timing slice gets a RUN_LOG row (GATE_CRITERIA I3), even when it writes no output."""
    append_run_log(config_path, "ok", "(none: timing only)", f"timing slice: {note}")


def latest_done(rq: str) -> Path:
    runs = [d for d in sorted((RESULTS / rq).glob("run_*")) if (d / "DONE").exists()]
    if not runs:
        raise FileNotFoundError(f"no finished {rq} run")
    return runs[-1]
