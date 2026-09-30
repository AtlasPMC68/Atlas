from typing import Any, Generator
import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Generator[None, None, None]:
    """
    Hook implementation to capture custom test item metadata.
    Transfers user_metadata attribute from test items onto the test execution report.
    """
    outcome = yield
    report = outcome.get_result()
    metadata = getattr(item, "user_metadata", None)
    if metadata is not None:
        report.user_metadata = metadata


def pytest_report_teststatus(report: Any, config: Any) -> tuple[str, str, str] | None:
    """
    Custom status reporting formatter for pytest execution.
    Formats pass/fail test status messages with hit_rate and average_distance metadata metrics.
    """
    if report.when == "call" and hasattr(report, "user_metadata"):
        hit_rate = report.user_metadata.get("hit_rate", 0.0)
        d_average = report.user_metadata.get("average_distance", 0.0)
        if report.passed:
            return (
                "passed",
                ".",
                f"PASSED (hit_rate={hit_rate:3.0f}%, d_average={d_average:4.2f})",
            )
        elif report.failed:
            return (
                "failed",
                "F",
                f"FAILED (hit_rate={hit_rate:3.0f}%, d_average={d_average:4.2f})",
            )

    return None


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """
    Modify collected test items prior to test execution.
    Skips integration and slow tests when running with parallel pytest-xdist workers.
    """
    if config.getoption("numprocesses", default=None):
        skip_marker = pytest.mark.skip(
            reason="integration tests run sequentially, not with -n"
        )
        for item in items:
            if "integration" in item.keywords or "slow" in item.keywords:
                item.add_marker(skip_marker)


def pytest_configure(config: Any) -> None:
    """
    Configure custom markers and warning filters for test session initialization.
    Registers 'integration' and 'slow' markers and suppresses known deprecation warnings.
    """
    config.addinivalue_line("markers", "integration: marks tests as integration")
    config.addinivalue_line("markers", "slow: marks tests as slow-running")
    config.addinivalue_line(
        "filterwarnings",
        "ignore:.*Please use `import python_multipart` instead.*:PendingDeprecationWarning",
    )
    config.addinivalue_line(
        "filterwarnings",
        "ignore::PendingDeprecationWarning:starlette.formparsers",
    )
