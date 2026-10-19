"""Shared machinery for the v2 runners (ported from v1 experiments/common.py; the v1 freeze guard
and fixed-λ book are removed): clean-tree refusal, run directories, resume, write-once chunks,
DONE marker, provenance, and the run log.

A run lives in results/<name>/run_<UTC>/. It starts only from a clean tree (no modified, staged,
or untracked files outside results/), and records that commit (CLAUDE.md rule 6). Each finished
chunk (a date, an instance) is one parquet file written once and never overwritten; a crashed
run resumes in the same directory, skipping finished chunks, but only if the config hash and the
commit match (`run_meta.json`). `finish` writes the combined outputs, their sha256 in
`outputs.json`, and a DONE marker. The run's RUN_LOG row is written when it starts (status
"running") and updated in place when it ends: "ok" (or "pilot" for pilot runs) or "failed"
(CLAUDE.md rule 7).
"""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import subprocess
from pathlib import Path

import pandas as pd
import yaml

from src.utils import ROOT, RUN_LOG_HEADER, utc_timestamp

END_STATUSES = ("ok", "failed", "pilot", "superseded")


# ----- git -----

def tree_is_clean(root: Path = ROOT) -> bool:
    """No modified, staged, or untracked (non-ignored) files outside results/."""
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", ".",
                          ":(exclude)results"], cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"git status failed: {out.stderr.strip()}")
    return out.stdout.strip() == ""


def head_commit(root: Path = ROOT) -> str:
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError("not a git repository with a commit")
    return out.stdout.strip()


def require_clean_tree(root: Path = ROOT) -> str:
    """The HEAD commit, or RuntimeError if the tree is dirty."""
    if not tree_is_clean(root):
        raise RuntimeError("runners refuse a dirty tree (CLAUDE.md rule 6): commit code, configs "
                           "and docs first (`git status --short` outside results/)")
    return head_commit(root)


# ----- provenance -----

def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def provenance() -> dict:
    """Interpreter, machine, and solver/library versions."""
    import clarabel
    import cvxpy
    import gurobipy
    import numpy
    import scipy
    return {"python": platform.python_version(), "platform": platform.platform(),
            "machine": platform.machine(), "numpy": numpy.__version__, "scipy": scipy.__version__,
            "pandas": pd.__version__, "cvxpy": cvxpy.__version__, "clarabel": clarabel.__version__,
            "gurobipy": ".".join(map(str, gurobipy.gurobi.version()))}


# ----- the run log -----

def _log_path(root: Path) -> Path:
    return Path(root) / "results" / "RUN_LOG.csv"


def _rel(path: Path, root: Path) -> str:
    p = Path(path)
    return str(p.relative_to(root)) if p.is_absolute() and p.is_relative_to(root) else str(p)


def log_start(root: Path, commit: str, config_path: str, output_path: str, notes: str) -> None:
    log = _log_path(root)
    log.parent.mkdir(parents=True, exist_ok=True)
    new = not log.exists()
    with log.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(RUN_LOG_HEADER)
        w.writerow([utc_timestamp(), commit, config_path, "running", output_path, notes])


def log_end(root: Path, output_path: str, status: str, note: str) -> None:
    """Update the newest 'running' row for output_path in place (status, notes += note)."""
    if status not in END_STATUSES:
        raise ValueError(status)
    log = _log_path(root)
    with log.open(newline="") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    i_status, i_out, i_notes = (header.index(k) for k in ("status", "output_path", "notes"))
    hits = [k for k, r in enumerate(body) if r[i_out] == output_path and r[i_status] == "running"]
    if not hits:
        raise KeyError(f"no running RUN_LOG row for {output_path}")
    r = body[hits[-1]]
    r[i_status] = status
    r[i_notes] = f"{r[i_notes]}; ended {utc_timestamp()}: {note}" if r[i_notes] else note
    tmp = log.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        csv.writer(f).writerows([header, *body])
    tmp.replace(log)


# ----- runs -----

def config_hash(config_path: str, root: Path = ROOT) -> str:
    return file_sha256(Path(root) / config_path)


def open_run(name: str, config_path: str, root: Path = ROOT, status: str = "ok",
             extra_meta: dict | None = None) -> tuple[Path, dict]:
    """Refuse a dirty tree; resume the newest unfinished, unfailed run with the same config and
    commit, or start a new one. `status` is the RUN_LOG status written by `finish`."""
    root = Path(root)
    commit = require_clean_tree(root)
    cfg_hash = config_hash(config_path, root)
    base = root / "results" / name
    base.mkdir(parents=True, exist_ok=True)
    for d in sorted(base.glob("run_*"), reverse=True):
        meta_path = d / "run_meta.json"
        if (d / "DONE").exists() or (d / "FAILED").exists() or not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        if meta["config_sha256"] == cfg_hash and meta["git_commit"] == commit:
            print(f"resuming {d.name}", flush=True)
            return d, meta
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    d = base / f"run_{stamp}"
    k = 1
    while d.exists():                                   # two runs started in the same second
        d, k = base / f"run_{stamp}_{k}", k + 1
    d.mkdir()
    meta = {"name": name, "created_utc": utc_timestamp(), "git_commit": commit,
            "config_path": config_path, "config_sha256": cfg_hash,
            "config": yaml.safe_load((root / config_path).read_text()),
            "finish_status": status, "provenance": provenance(), **(extra_meta or {})}
    (d / "run_meta.json").write_text(json.dumps(meta, indent=1, default=str))
    log_start(root, commit, config_path, _rel(d, root), f"{name} {d.name}")
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


def run_meta(run: Path) -> dict:
    return json.loads((run / "run_meta.json").read_text())


def finish(run: Path, config_path: str, outputs: dict[str, pd.DataFrame], note: str,
           root: Path = ROOT) -> None:
    """Write each output once, record their sha256, write DONE, close the RUN_LOG row."""
    hashes = {}
    for name, df in outputs.items():
        out = run / f"{name}.parquet"
        if out.exists():
            raise FileExistsError(out)
        df.to_parquet(out, index=False)
        hashes[out.name] = file_sha256(out)
    (run / "outputs.json").write_text(json.dumps(hashes, indent=1))
    (run / "DONE").write_text(utc_timestamp() + "\n")
    log_end(Path(root), _rel(run, Path(root)), run_meta(run).get("finish_status", "ok"), note)


def fail(run: Path | None, config_path: str, err: BaseException, root: Path = ROOT) -> None:
    """Mark the run failed (FAILED marker; RUN_LOG row updated). A failure before the run
    directory exists gets its own row."""
    msg = f"{type(err).__name__}: {err}"
    root = Path(root)
    if run is None:
        log_start(root, head_commit(root), config_path, "", "failed before the run started")
        log_end(root, "", "failed", msg)
        return
    (run / "FAILED").write_text(utc_timestamp() + "\n" + msg + "\n")
    log_end(root, _rel(run, root), "failed", msg)


def latest_done(name: str, root: Path = ROOT) -> Path:
    runs = [d for d in sorted((Path(root) / "results" / name).glob("run_*")) if (d / "DONE").exists()]
    if not runs:
        raise FileNotFoundError(f"no finished {name} run")
    return runs[-1]
