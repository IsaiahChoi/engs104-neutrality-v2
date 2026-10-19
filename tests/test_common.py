"""Runner machinery (ported from v1 experiments/common.py without the freeze guard and the λ
book): clean-tree refusal, run directories, resume, write-once chunks, DONE, provenance, and a
RUN_LOG row written at the start and updated in place at the end (CLAUDE.md rules 6, 7, 12)."""
from __future__ import annotations

import csv
import json
import subprocess

import pandas as pd
import pytest

from experiments import common
from experiments.designs import month_end


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "results").mkdir(parents=True)
    (root / "experiments" / "configs").mkdir(parents=True)
    (root / "experiments" / "configs" / "x.yaml").write_text("a: 1\n")
    (root / "code.py").write_text("x = 1\n")
    _git(root, "init", "-q")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return root


def _rows(root):
    with open(root / "results" / "RUN_LOG.csv") as f:
        return list(csv.DictReader(f))


def test_tree_is_clean(repo):
    assert common.tree_is_clean(repo)
    (repo / "results" / "out.parquet").write_text("generated")       # results/ does not count
    assert common.tree_is_clean(repo)
    (repo / "new_module.py").write_text("y = 2\n")                  # untracked code counts
    assert not common.tree_is_clean(repo)
    (repo / "new_module.py").unlink()
    (repo / "code.py").write_text("x = 2\n")                        # modified tracked file
    assert not common.tree_is_clean(repo)


def test_runner_refuses_a_dirty_tree(repo):
    (repo / "code.py").write_text("x = 3\n")
    with pytest.raises(RuntimeError, match="dirty"):
        common.open_run("c1", "experiments/configs/x.yaml", root=repo)


def test_run_lifecycle_resume_chunks_done_and_log(repo):
    cfg = "experiments/configs/x.yaml"
    run, meta = common.open_run("c1", cfg, root=repo, extra_meta={"workers": 4})
    assert run.parent == repo / "results" / "c1" and (run / "run_meta.json").exists()
    assert meta["git_commit"] == common.head_commit(repo) and meta["workers"] == 4
    assert {"python", "gurobipy", "cvxpy", "clarabel", "numpy"} <= set(meta["provenance"])
    rows = _rows(repo)
    assert len(rows) == 1 and rows[0]["status"] == "running"
    p = common.chunk_path(run, "points", "2020-03-31")
    common.write_chunk(p, pd.DataFrame({"a": [1, 2]}))
    with pytest.raises(FileExistsError):
        common.write_chunk(p, pd.DataFrame({"a": [3]}))
    again, _ = common.open_run("c1", cfg, root=repo)                 # resume the unfinished run
    assert again == run and len(_rows(repo)) == 1
    common.finish(run, cfg, {"points": common.combine(run, "points")}, "1 date", root=repo)
    assert (run / "DONE").exists() and (run / "points.parquet").exists()
    outs = json.loads((run / "outputs.json").read_text())
    assert set(outs) == {"points.parquet"} and len(outs["points.parquet"]) == 64
    rows = _rows(repo)
    assert len(rows) == 1 and rows[0]["status"] == "ok" and "1 date" in rows[0]["notes"]
    assert common.latest_done("c1", root=repo) == run
    new, _ = common.open_run("c1", cfg, root=repo)                   # finished runs are not resumed
    assert new != run


def test_failed_and_pilot_status(repo):
    cfg = "experiments/configs/x.yaml"
    run, _ = common.open_run("pilot", cfg, root=repo, status="pilot")
    common.fail(run, cfg, ValueError("boom"), root=repo)
    r = _rows(repo)[-1]
    assert r["status"] == "failed" and "ValueError: boom" in r["notes"]
    run2, _ = common.open_run("pilot", cfg, root=repo, status="pilot")
    assert run2 != run                                                # a failed run is not resumed
    common.finish(run2, cfg, {}, "pilot items", root=repo)
    assert _rows(repo)[-1]["status"] == "pilot"


def test_month_end():
    assert month_end("2020-03") == pd.Timestamp("2020-03-31")
    assert month_end("2017-12") == pd.Timestamp("2017-12-29")
    with pytest.raises(ValueError):
        month_end("2030-01")
