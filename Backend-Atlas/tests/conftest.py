import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    # Pull metadata from the test item (node) and put it in the report
    metadata = getattr(item, "user_metadata", None)
    if metadata is not None:
        report.user_metadata = metadata


def pytest_report_teststatus(report, config):
    if report.when == "call" and hasattr(report, "user_metadata"):
        hit_rate = report.user_metadata.get("hit_rate", 0.0)
        d_average = report.user_metadata.get("average_distance", 0.0)
        if report.passed:
            return (
                "passed",
                ".",
                f"PASSED (hit_rate={hit_rate:.0f}%, d_average={d_average:.2f})",
            )
        elif report.failed:
            return (
                "failed",
                "F",
                f"FAILED (hit_rate={hit_rate:.0f}%, d_average={d_average:.2f})",
            )

    return None


def pytest_collection_modifyitems(config, items):
    """Skip integration/slow tests when running with pytest-xdist workers."""
    if config.getoption("numprocesses", default=None):
        skip_marker = pytest.mark.skip(
            reason="integration tests run sequentially, not with -n"
        )
        for item in items:
            if "integration" in item.keywords or "slow" in item.keywords:
                item.add_marker(skip_marker)


def pytest_configure(config):
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
