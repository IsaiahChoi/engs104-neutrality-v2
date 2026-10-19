#!/usr/bin/env python3
"""Read-only data verification (MIGRATION §3 item 2; CHECKS K2). `make data-verify` runs it.

Checks, each PASS/FAIL:
- raw: every file under data/raw matches data/MANIFEST_data.json `raw_sha256` (sha256; no
  missing or extra files; Finder .DS_Store files count as extra);
- build_meta raw hashes: data/processed/build_meta.json `raw_sha256` equals the manifest's;
- build_meta panel hash: its `panel_sha256` equals the manifest's;
- panel content hash: src.data.panel.panel_hash of data/processed/panel.parquet equals the manifest's;
- build_meta / risk meta fields: build_meta.json vs MANIFEST_data.json and
  data/processed/risk/w252_meta.json vs MANIFEST_risk.json, every field except timestamps.
`git_commit` is provenance, not content: a difference is printed as NOTE and does not fail
(the S0 offline rebuild ran before the v2 repository existed, so it records "unknown").
Exits 1 on any FAIL. Writes nothing.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TIMESTAMP_FIELDS = frozenset({"built_utc", "created_utc"})
PROVENANCE_FIELDS = frozenset({"git_commit"})


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def compare_raw(raw_dir: Path, manifest: dict[str, str]) -> dict:
    """Files under raw_dir (relative paths) against manifest {relative path: sha256}."""
    raw_dir = Path(raw_dir)
    disk = {str(p.relative_to(raw_dir)) for p in raw_dir.rglob("*") if p.is_file()}
    return {"n_manifest": len(manifest), "n_disk": len(disk),
            "missing": sorted(set(manifest) - disk), "extra": sorted(disk - set(manifest)),
            "mismatched": sorted(f for f in set(manifest) & disk
                                 if sha256_file(raw_dir / f) != manifest[f])}


def compare_meta(meta: dict, manifest: dict) -> tuple[dict, dict]:
    """(content diffs, provenance diffs), each {field: (meta value, manifest value)}; timestamp
    fields are ignored."""
    diffs, prov = {}, {}
    for k in sorted(set(meta) | set(manifest)):
        if k in TIMESTAMP_FIELDS:
            continue
        a, b = meta.get(k, "<absent>"), manifest.get(k, "<absent>")
        if a != b:
            (prov if k in PROVENANCE_FIELDS else diffs)[k] = (a, b)
    return diffs, prov


def _short(v) -> str:
    s = json.dumps(v, default=str) if not isinstance(v, str) else v
    return s if len(s) <= 60 else s[:57] + "..."


def main() -> int:
    from src.data.build_all import META_PATH, PANEL_PATH
    from src.risk.build_all import model_paths
    from src.utils import DATA_RAW

    man_data = json.loads((ROOT / "data" / "MANIFEST_data.json").read_text())
    man_risk = json.loads((ROOT / "data" / "MANIFEST_risk.json").read_text())
    build_meta = json.loads(META_PATH.read_text())
    risk_meta = json.loads(model_paths(man_risk["config"]["window"])[2].read_text())
    rows: list[tuple[str, bool, str]] = []
    notes: list[str] = []

    r = compare_raw(DATA_RAW, man_data["raw_sha256"])
    ok = not (r["missing"] or r["extra"] or r["mismatched"])
    rows.append(("raw files vs manifest", ok,
                 f"manifest {r['n_manifest']}, on disk {r['n_disk']}, missing {r['missing'][:5]}, "
                 f"extra {r['extra'][:5]}, mismatched {r['mismatched'][:5]}"))
    rows.append(("build_meta raw hashes", build_meta.get("raw_sha256") == man_data["raw_sha256"],
                 f"{len(build_meta.get('raw_sha256', {}))} entries"))
    rows.append(("build_meta panel hash", build_meta.get("panel_sha256") == man_data["panel_sha256"],
                 man_data["panel_sha256"][:16]))

    import pandas as pd
    from src.data.panel import panel_hash
    h = panel_hash(pd.read_parquet(PANEL_PATH))
    rows.append(("panel content hash", h == man_data["panel_sha256"], f"recomputed {h[:16]}"))

    for name, meta, man in (("build_meta fields", build_meta, man_data),
                            ("risk meta fields", risk_meta, man_risk)):
        diffs, prov = compare_meta(meta, man)
        rows.append((name, not diffs,
                     "; ".join(f"{k}: {_short(a)} != {_short(b)}" for k, (a, b) in diffs.items())
                     or "all content fields equal (timestamps ignored)"))
        notes += [f"{name}: {k} = {_short(a)} (manifest {_short(b)})" for k, (a, b) in prov.items()]

    width = max(len(n) for n, _, _ in rows)
    for name, ok, detail in rows:
        print(f"{name:<{width}}  {'PASS' if ok else 'FAIL'}  {detail}")
    for n in notes:
        print(f"NOTE (provenance, not content): {n}")
    n_fail = sum(not ok for _, ok, _ in rows)
    print(f"{len(rows) - n_fail}/{len(rows)} checks pass")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
