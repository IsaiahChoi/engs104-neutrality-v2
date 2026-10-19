"""Shared machinery for the v2 runners (ported from v1 experiments/common.py; the v1 freeze guard
and fixed-λ book are removed): clean-tree refusal, run directories, resume, write-once chunks,
DONE marker, provenance, and the run log.

A run lives in results/<name>/run_<UTC>/. It starts only from a clean tree (no modified, staged,
or untracked files outside results/), and records that commit (CLAUDE.md rule 6) plus a
fingerprint of the processed data (data/ is gitignored, so git cannot see it); a processed panel
whose recorded hash differs from the committed manifest is refused. Each finished chunk (a date,
an instance) is one parquet file written once and never overwritten. A run that was killed
(crash, kill, power loss) resumes in the same directory, skipping finished chunks, but only if
the config hash, the commit, the finish status, the run arguments (extra_meta) and the data
fingerprint all match (`run_meta.json`). A run whose runner raised is marked FAILED by `fail`
and is not resumed: rerunning starts a new run. `finish` writes the combined outputs (via
temporary files), their sha256 in `outputs.json`, closes the RUN_LOG row, and only then writes
DONE. The run's RUN_LOG row is written when it starts (status "running") and updated in place
when it ends: "ok" (or "pilot" for pilot runs), "failed", or later "superseded" (CLAUDE.md
rule 7). Every RUN_LOG access holds an exclusive lock on results/RUN_LOG.lock.
"""
from __future__ import annotations

import csv
import fcntl
import hashlib
import json
import platform
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import yaml

from src.utils import ROOT, RUN_LOG_HEADER, utc_timestamp

END_STATUSES = ("ok", "failed", "pilot", "superseded")
DATA_FILES = ("data/processed/panel.parquet", "data/processed/factors_daily.parquet",
              "data/processed/risk/w252_loadings.parquet",
              "data/processed/risk/w252_factor_cov.parquet")


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
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


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


def data_fingerprint(root: Path = ROOT) -> dict:
    """sha256 of the processed inputs the runners read, and the panel hash recorded in
    build_meta.json against the committed manifest. RuntimeError if those two differ."""
    root = Path(root)

    def read(rel):
        p = root / rel
        return json.loads(p.read_text()) if p.exists() else {}

    manifest = read("data/MANIFEST_data.json").get("panel_sha256")
    built = read("data/processed/build_meta.json").get("panel_sha256")
    if manifest is not None and built is not None and manifest != built:
        raise RuntimeError(f"processed panel hash {built[:16]} does not match the committed "
                           f"manifest {manifest[:16]} (run `make data-verify`)")
    return {"panel_sha256_manifest": manifest, "panel_sha256_build_meta": built,
            "files": {rel: file_sha256(root / rel) for rel in DATA_FILES if (root / rel).exists()}}


# ----- the run log -----

def _log_path(root: Path) -> Path:
    return Path(root) / "results" / "RUN_LOG.csv"


@contextmanager
def _locked(root: Path):
    lock = Path(root) / "results" / "RUN_LOG.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _rel(path: Path, root: Path) -> str:
    p = Path(path)
    return str(p.relative_to(root)) if p.is_absolute() and p.is_relative_to(root) else str(p)


def _append(root: Path, row: list) -> None:
    log = _log_path(root)
    new = not log.exists() or log.stat().st_size == 0
    with log.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(RUN_LOG_HEADER)
        w.writerow(row)


def log_start(root: Path, commit: str, config_path: str, output_path: str, notes: str) -> None:
    with _locked(root):
        _append(root, [utc_timestamp(), commit, config_path, "running", output_path, notes])


def log_end(root: Path, output_path: str, status: str, note: str,
            from_status: tuple[str, ...] = ("running",)) -> bool:
    """Update the newest row for output_path whose status is in from_status, in place
    (status; notes += note). Returns False if there is no such row."""
    if status not in END_STATUSES:
        raise ValueError(status)
    with _locked(root):
        log = _log_path(root)
        if not log.exists():
            return False
        with log.open(newline="") as f:
            rows = list(csv.reader(f))
        if not rows:
            return False
        header, body = rows[0], rows[1:]
        i_status, i_out, i_notes = (header.index(k) for k in ("status", "output_path", "notes"))
        hits = [k for k, r in enumerate(body) if r[i_out] == output_path and r[i_status] in from_status]
        if not hits:
            return False
        r = body[hits[-1]]
        r[i_status] = status
        r[i_notes] = f"{r[i_notes]}; {status} {utc_timestamp()}: {note}" if r[i_notes] else note
        tmp = log.with_suffix(".tmp")
        with tmp.open("w", newline="") as f:
            csv.writer(f).writerows([header, *body])
        tmp.replace(log)
        return True


# ----- runs -----

def config_hash(config_path: str, root: Path = ROOT) -> str:
    return file_sha256(Path(root) / config_path)


def _canon(x) -> str:
    return json.dumps(x, sort_keys=True, default=str)


def open_run(name: str, config_path: str, root: Path = ROOT, status: str = "ok",
             extra_meta: dict | None = None) -> tuple[Path, dict]:
    """Refuse a dirty tree or a data/manifest mismatch; resume the newest killed run with the same
    config, commit, finish status, arguments and data, or start a new one. `status` is the
    RUN_LOG status written by `finish`."""
    root = Path(root)
    commit = require_clean_tree(root)
    data = data_fingerprint(root)
    cfg_hash = config_hash(config_path, root)
    args = extra_meta or {}
    base = root / "results" / name
    base.mkdir(parents=True, exist_ok=True)
    for d in sorted(base.glob("run_*"), reverse=True):
        meta_path = d / "run_meta.json"
        if any((d / m).exists() for m in ("DONE", "FAILED", "SUPERSEDED")) or not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        if (meta["config_sha256"] == cfg_hash and meta["git_commit"] == commit
                and meta.get("finish_status") == status and _canon(meta.get("args", {})) == _canon(args)
                and _canon(meta.get("data")) == _canon(data)):
            print(f"resuming {d.name}", flush=True)
            return d, meta
    meta = {"name": name, "created_utc": utc_timestamp(), "git_commit": commit,
            "config_path": config_path, "config_sha256": cfg_hash,
            "config": yaml.safe_load((root / config_path).read_text()),
            "finish_status": status, "args": args, "data": data, "provenance": provenance(),
            **args}
    stamp = meta["created_utc"].replace(":", "").replace("-", "")
    d = base / f"run_{stamp}"
    k = 1
    while d.exists():                                   # two runs started in the same second
        d, k = base / f"run_{stamp}_{k}", k + 1
    d.mkdir()
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
           root: Path = ROOT, extra_files=()) -> None:
    """Write each output (temporary file, then rename; outputs are derived from the chunks, so a
    finish interrupted before DONE may rewrite them), record their sha256 together with those of
    extra_files (other files the runner wrote inside the run directory), close the RUN_LOG row,
    then write DONE. If the RUN_LOG row cannot be closed, no DONE is written."""
    root = Path(root)
    if (run / "DONE").exists():
        raise FileExistsError(run / "DONE")
    extra = [Path(f) for f in extra_files]
    for f in extra:
        if f.resolve().parent != Path(run).resolve() or not f.is_file():
            raise ValueError(f"extra output {f} is not a file in the run directory {run}")
    hashes = {}
    for name, df in outputs.items():
        out = run / f"{name}.parquet"
        tmp = out.with_suffix(".parquet.tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(out)
        hashes[out.name] = file_sha256(out)
    hashes.update({f.name: file_sha256(f) for f in extra})
    (run / "outputs.json").write_text(json.dumps(hashes, indent=1))
    if not log_end(root, _rel(run, root), run_meta(run).get("finish_status", "ok"), note):
        raise RuntimeError(f"no running RUN_LOG row for {_rel(run, root)}; DONE not written")
    (run / "DONE").write_text(utc_timestamp() + "\n")


def fail(run: Path | None, config_path: str, err: BaseException, root: Path = ROOT) -> None:
    """Mark the run failed (FAILED marker; its RUN_LOG row updated, or a new failed row if it has
    none in "running", e.g. a failure after finish). Never raises over the original error."""
    msg = f"{type(err).__name__}: {err}"
    root = Path(root)
    out = _rel(run, root) if run is not None else ""
    try:
        commit = head_commit(root)
    except RuntimeError:
        commit = "unknown"
    if run is not None:
        (run / "FAILED").write_text(utc_timestamp() + "\n" + msg + "\n")
    if run is None or not log_end(root, out, "failed", msg):
        with _locked(root):
            _append(root, [utc_timestamp(), commit, config_path, "failed", out,
                           msg if run is not None else f"failed before the run started: {msg}"])


def supersede(run: Path, note: str, root: Path = ROOT) -> None:
    """Mark a finished run superseded (SUPERSEDED marker; its RUN_LOG row's status set)."""
    root = Path(root)
    (run / "SUPERSEDED").write_text(utc_timestamp() + "\n" + note + "\n")
    if not log_end(root, _rel(run, root), "superseded", note, from_status=("ok", "pilot", "failed")):
        with _locked(root):
            _append(root, [utc_timestamp(), run_meta(run)["git_commit"], run_meta(run)["config_path"],
                           "superseded", _rel(run, root), note])


def latest_done(name: str, root: Path = ROOT, status: str = "ok") -> Path:
    """The newest run of `name` with DONE, no FAILED or SUPERSEDED marker, and finish status
    `status` (pilot runs are never returned for "ok")."""
    runs = [d for d in sorted((Path(root) / "results" / name).glob("run_*"))
            if (d / "DONE").exists() and not (d / "FAILED").exists()
            and not (d / "SUPERSEDED").exists()
            and run_meta(d).get("finish_status", "ok") == status]
    if not runs:
        raise FileNotFoundError(f"no finished {name} run with status {status}")
    return runs[-1]
