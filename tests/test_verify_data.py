"""tools/verify_data.py (MIGRATION §3 item 2; CHECKS K2): the comparison logic on synthetic
directories, so a missing, extra, or altered raw file and a changed metadata field are caught."""
from __future__ import annotations

import hashlib

from tools.verify_data import compare_meta, compare_raw


def _hash(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _tree(tmp_path, files: dict[str, bytes]):
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    return tmp_path


def test_compare_raw_clean(tmp_path):
    files = {"prices/A.parquet": b"a", "factors/f.csv": b"f"}
    raw = _tree(tmp_path, files)
    r = compare_raw(raw, {k: _hash(v) for k, v in files.items()})
    assert r == {"n_manifest": 2, "n_disk": 2, "missing": [], "extra": [], "mismatched": []}


def test_compare_raw_flags_missing_extra_and_mismatched(tmp_path):
    raw = _tree(tmp_path, {"a": b"a", "b": b"changed", ".DS_Store": b"x"})
    manifest = {"a": _hash(b"a"), "b": _hash(b"b"), "c": _hash(b"c")}
    r = compare_raw(raw, manifest)
    assert r["missing"] == ["c"]
    assert r["extra"] == [".DS_Store"]          # Finder files count as extra
    assert r["mismatched"] == ["b"]


def test_compare_meta_ignores_timestamps_and_reports_provenance():
    manifest = {"n_dates": 241, "built_utc": "2026-10-16T06:27:41Z", "git_commit": "44ea3ba",
                "config": {"window": 252}}
    same = {**manifest, "built_utc": "2026-10-18T22:51:37Z", "git_commit": "unknown"}
    diffs, prov = compare_meta(same, manifest)
    assert diffs == {}
    assert prov == {"git_commit": ("unknown", "44ea3ba")}
    changed = {**same, "config": {"window": 126}, "extra_key": 1}
    diffs, _ = compare_meta(changed, manifest)
    assert set(diffs) == {"config", "extra_key"}
