from __future__ import annotations

from src.results import (
    ITEM_FAILED,
    ITEM_SKIPPED,
    ITEM_SUCCESS,
    RUN_FAILED,
    RUN_PARTIAL,
    RUN_SUCCESS,
    ScrapeItemResult,
    ScrapeRunSummary,
)


def _summary(successes=0, failures=0, skips=0):
    s = ScrapeRunSummary.start()
    for i in range(successes):
        s.record(ScrapeItemResult(goods_id=str(i), status=ITEM_SUCCESS))
    for i in range(failures):
        s.record(
            ScrapeItemResult(
                goods_id=f"f{i}", status=ITEM_FAILED, error_type="http", error_message="500"
            )
        )
    for i in range(skips):
        s.record(ScrapeItemResult(goods_id=f"s{i}", status=ITEM_SKIPPED))
    return s


def test_counts_are_correct():
    s = _summary(successes=4, failures=2, skips=1)
    assert s.attempted == 7
    assert s.succeeded == 4
    assert s.failed == 2
    assert s.skipped == 1


def test_status_all_success():
    assert _summary(successes=3).finalize().status == RUN_SUCCESS


def test_status_partial_success():
    assert _summary(successes=2, failures=2).finalize().status == RUN_PARTIAL


def test_status_all_failed():
    assert _summary(failures=3).finalize().status == RUN_FAILED


def test_status_empty_run_is_success():
    assert _summary().finalize().status == RUN_SUCCESS


def test_exit_code_partial_is_zero():
    assert _summary(successes=1, failures=5).finalize().exit_code() == 0


def test_exit_code_all_failed_is_one():
    assert _summary(failures=3).finalize().exit_code() == 1


def test_exit_code_empty_is_zero():
    assert _summary().finalize().exit_code() == 0


def test_errors_collected_only_for_non_success():
    s = _summary(successes=1, failures=2)
    assert len(s.errors) == 2


def test_log_line_format():
    line = _summary(successes=2, failures=1).finalize().log_line()
    assert line.startswith("Scraper run finished: status=partial_success")
    assert "attempted=3" in line
    assert "succeeded=2" in line
    assert "failed=1" in line
    assert "duration_seconds=" in line
