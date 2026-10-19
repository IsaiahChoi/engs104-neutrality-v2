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
    again, _ = common.open_run("c1", cfg, root=repo, extra_meta={"workers": 4})   # resume it
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


def test_resume_requires_same_status_and_arguments(repo):
    """Review H4: a different finish status or different extra_meta never resumes a run."""
    cfg = "experiments/configs/x.yaml"
    a, _ = common.open_run("c2", cfg, root=repo, extra_meta={"dates": ["2020-03"]})
    b, _ = common.open_run("c2", cfg, root=repo, extra_meta={"dates": ["2017-12"]})
    c, _ = common.open_run("c2", cfg, root=repo, status="pilot", extra_meta={"dates": ["2020-03"]})
    d, _ = common.open_run("c2", cfg, root=repo, extra_meta={"dates": ["2020-03"]})
    assert len({a, b, c}) == 3 and d == a


def test_latest_done_skips_failed_pilot_and_superseded(repo):
    """Review M2/M4: latest_done returns the newest finished "ok" run that has not failed and
    has not been superseded; fail() after finish() does not raise."""
    cfg = "experiments/configs/x.yaml"
    ok1, _ = common.open_run("c1", cfg, root=repo, extra_meta={"k": 1})
    common.finish(ok1, cfg, {}, "first", root=repo)
    pilot, _ = common.open_run("c1", cfg, root=repo, status="pilot", extra_meta={"k": 2})
    common.finish(pilot, cfg, {}, "pilot", root=repo)
    assert common.latest_done("c1", root=repo) == ok1
    ok2, _ = common.open_run("c1", cfg, root=repo, extra_meta={"k": 3})
    common.finish(ok2, cfg, {}, "second", root=repo)
    common.fail(ok2, cfg, RuntimeError("late failure"), root=repo)    # tolerated, recorded
    assert common.latest_done("c1", root=repo) == ok1                 # ok2 now has FAILED
    common.supersede(ok1, "rerun after a fix", root=repo)
    with pytest.raises(FileNotFoundError):
        common.latest_done("c1", root=repo)
    statuses = [r["status"] for r in _rows(repo)]
    assert "superseded" in statuses and "failed" in statuses


def test_data_fingerprint_recorded_and_manifest_mismatch_refused(repo):
    """Review M1: run_meta records the processed-data fingerprint; a build_meta whose panel hash
    differs from the committed manifest is refused."""
    cfg = "experiments/configs/x.yaml"
    run, meta = common.open_run("c1", cfg, root=repo)
    assert "data" in meta and set(meta["data"]) >= {"panel_sha256_manifest", "files"}
    (repo / "data" / "processed").mkdir(parents=True)
    (repo / "data" / "MANIFEST_data.json").write_text(json.dumps({"panel_sha256": "aa"}))
    (repo / "data" / "processed" / "build_meta.json").write_text(json.dumps({"panel_sha256": "bb"}))
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "data manifests")
    with pytest.raises(RuntimeError, match="manifest"):
        common.open_run("c1", cfg, root=repo, extra_meta={"x": 1})
