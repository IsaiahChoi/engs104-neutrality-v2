"""Suite-wide fixtures. S5 pass 3, 0c: figure and table outputs written during the suite go to a
temporary directory, not to the tracked figures/ and report/tables/ (`make figures` writes those).
Only where the tests write changes; what they assert does not."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _outputs_to_tmp(tmp_path_factory, monkeypatch):
    from src.figures import fig_s3, numbers, style
    out = tmp_path_factory.mktemp("outputs")
    monkeypatch.setattr(style, "FIGURES", out / "figures")
    monkeypatch.setattr(numbers, "TABLES", out / "tables")
    monkeypatch.setattr(fig_s3, "TABLES", out / "tables")
