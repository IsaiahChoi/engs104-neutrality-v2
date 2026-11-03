"""S5 pass 3 (Isaiah's note "— Isaiah: S5 pass 3 stop read; Decision 69 ..."), steps 0b and 0c.

0b: the log that \\TestsPassed and the facts' software line take their count from must be a
passing run: tools/make_facts.full_suite_log refuses a newest full-suite log that records any
failure or error, instead of reporting its count.
0c: the suite writes no tracked figure or table; tests/conftest.py sends them to a temporary
directory."""
from __future__ import annotations

import pytest

import tools.make_facts as mf
from src.figures import fig_c, fig_s3, numbers, style
from src.utils import ROOT


# ----- 0b: no count from a failing run -----

@pytest.mark.parametrize("summary", [
    "1 failed, 555 passed, 1 skipped, 2 xfailed, 3 warnings in 104.27s (0:01:44)",
    "555 passed, 1 error in 90.1s",
    "555 passed, 2 errors in 90.1s",
    "1 failed, 554 passed, 1 error in 90.1s",
])
def test_newest_log_with_a_failure_or_error_is_refused(tmp_path, summary):
    (tmp_path / "test_full_a_20261103T100000Z.log").write_text("556 passed, 1 skipped in 99s\n")
    (tmp_path / "test_full_b_20261103T110000Z.log").write_text(f"..F.\n{summary}\n")
    with pytest.raises(ValueError, match="test_full_b_20261103T110000Z.log"):
        mf.full_suite_log(tmp_path)


def test_a_run_where_nothing_passed_is_not_skipped_over(tmp_path):
    # without "passed" in its summary, a failing run must still be the newest candidate
    (tmp_path / "test_full_a_20261103T100000Z.log").write_text("556 passed in 99s\n")
    (tmp_path / "test_full_b_20261103T110000Z.log").write_text("3 failed in 2.0s\n")
    with pytest.raises(ValueError, match="failed"):
        mf.full_suite_log(tmp_path)


def test_collection_error_is_refused(tmp_path):
    (tmp_path / "test_full_a_20261103T100000Z.log").write_text("556 passed in 99s\n")
    (tmp_path / "make_figures_20261103T110000Z.out").write_text(
        "!!!!!!!! Interrupted: 1 error during collection !!!!!!!!\n1 error in 1.52s\n")
    with pytest.raises(ValueError):
        mf.full_suite_log(tmp_path)


def test_an_older_failing_log_does_not_matter(tmp_path):
    (tmp_path / "test_full_a_20261103T100000Z.log").write_text("1 failed, 555 passed in 99s\n")
    (tmp_path / "test_full_b_20261103T110000Z.log").write_text("564 passed, 1 skipped, 2 xfailed in 104s\n")
    f, c = mf.full_suite_log(tmp_path)
    assert f.name == "test_full_b_20261103T110000Z.log"
    assert c == {"passed": 564, "skipped": 1, "xfailed": 2}


def test_tests_passed_macro_takes_its_count_through_the_refusing_picker():
    src = (ROOT / "src" / "figures" / "numbers.py").read_text()
    assert "from tools.make_facts import full_suite_log" in src
    assert 'M.add("TestsPassed", i(c.get("passed", 0)), f)' in src


# ----- 0c: the suite writes no tracked output -----

def test_figure_and_table_outputs_go_to_a_temporary_directory():
    assert style.FIGURES != ROOT / "figures"
    assert numbers.TABLES != ROOT / "report" / "tables"
    assert fig_s3.TABLES != ROOT / "report" / "tables"
    assert ROOT not in style.FIGURES.parents and ROOT not in numbers.TABLES.parents


def test_a_rendered_figure_and_table_land_outside_the_repository():
    p = fig_c.fig2_alignment()
    t = numbers.table1_mandate()
    assert p.exists() and t.exists()
    assert ROOT not in p.parents and ROOT not in t.parents
    assert (style.FIGURES / "png" / "fig2_alignment.png").exists()
