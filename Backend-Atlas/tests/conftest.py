from typing import Any, Generator, Dict
import pytest

metadata_key = pytest.StashKey[Dict[str, float]]()

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Generator[None, None, None]:
    """Transfer test item metadata to test execution report."""
    outcome = yield
    report = outcome.get_result()
    metadata = item.stash.get(metadata_key, None)
    if metadata is not None:
        report.user_metadata = metadata
        
    if report.when == "call" and report.failed:
        if "test_text_extraction_accuracy" in item.name or "test_florence_raw_detection_count" in item.name:
            report.sections = []


def pytest_report_teststatus(report: Any, config: Any) -> tuple[str, str, str] | None:
    """Format test execution status with hit_rate and average_distance metrics."""
    if report.when == "call" and hasattr(report, "user_metadata"):
        hit_rate = report.user_metadata.get("hit_rate", 0.0)
        d_average = report.user_metadata.get("average_distance", 0.0)
        if report.passed:
            return (
                "passed",
                ".",
                f"PASSED (hit_rate={hit_rate:4.1f}%, d_average={d_average:4.2f})",
            )
        elif report.failed:
            return (
                "failed",
                "F",
                f"FAILED (hit_rate={hit_rate:4.1f}%, d_average={d_average:4.2f})",
            )

    return None


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """Skip integration and slow tests when running with parallel xdist workers."""
    if config.getoption("numprocesses", default=None):
        skip_marker = pytest.mark.skip(
            reason="integration tests run sequentially, not with -n"
        )
        for item in items:
            if "integration" in item.keywords or "slow" in item.keywords:
                item.add_marker(skip_marker)


def pytest_addoption(parser: Any) -> None:
    """Register extraction_log_info ini option."""
    parser.addini(
        "extraction_log_info",
        type="bool",
        default=True,
        help="Enable detailed logs for text extraction",
    )



