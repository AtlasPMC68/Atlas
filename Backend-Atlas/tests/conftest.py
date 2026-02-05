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
        m_count = report.user_metadata.get("match_count", 0)
        t_count = report.user_metadata.get("total_count", 0)
        if report.passed:
            return "passed", ".", f"PASSED {m_count}/{t_count}"
    return None