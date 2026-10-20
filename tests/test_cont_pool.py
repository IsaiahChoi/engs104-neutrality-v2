"""experiments.cont.pool_chunks resume (S2d item 5: the N2 smoke run's kill landed between an item's
chunk writes). Each item writes its kinds in reverse order, the first kind last as the completion
marker; an item without that marker is unfinished and recomputed on resume. A secondary chunk it
left behind is moved to chunks/_incomplete/<kind>/ (kept, never deleted) instead of blocking the
write-once rewrite."""
from __future__ import annotations

import pandas as pd

from experiments.common import chunk_path, write_chunk
from experiments.cont import pool_chunks

KINDS = ("first", "second")


def make(item: str) -> dict[str, pd.DataFrame]:
    return {"first": pd.DataFrame({"item": [item], "v": [1.0]}),
            "second": pd.DataFrame({"item": [item], "w": [2.0]})}


def test_leftover_secondary_chunk_is_moved_aside_and_recomputed(tmp_path):
    run = tmp_path / "run_x"
    run.mkdir()
    stale = pd.DataFrame({"item": ["a"], "w": [-9.0]})
    write_chunk(chunk_path(run, "second", "a"), stale)            # killed before "first" was written
    out = pool_chunks(run, KINDS, ["a", "b"], str, make, workers=1)
    assert sorted(out["first"]["item"]) == ["a", "b"]
    assert sorted(out["second"]["w"]) == [2.0, 2.0]                # recomputed, not the stale row
    kept = list((run / "chunks" / "_incomplete" / "second").glob("a*.parquet"))
    assert len(kept) == 1 and pd.read_parquet(kept[0])["w"].tolist() == [-9.0]
    assert not (run / "chunks" / "_incomplete" / "first").exists()


def test_finished_items_are_skipped(tmp_path):
    run = tmp_path / "run_y"
    run.mkdir()
    write_chunk(chunk_path(run, "second", "a"), pd.DataFrame({"item": ["a"], "w": [5.0]}))
    write_chunk(chunk_path(run, "first", "a"), pd.DataFrame({"item": ["a"], "v": [7.0]}))
    out = pool_chunks(run, KINDS, ["a", "b"], str, make, workers=1)
    assert out["first"].set_index("item").loc["a", "v"] == 7.0      # not recomputed
    assert out["first"].set_index("item").loc["b", "v"] == 1.0
    assert not (run / "chunks" / "_incomplete").exists()
