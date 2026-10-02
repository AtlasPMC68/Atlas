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


def pytest_report_teststatus(report: Any, config: Any) -> tuple[str, str, str] | None:
    """Format test execution status with hit_rate and average_distance metrics."""
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


def pytest_configure(config: Any) -> None:
    """Configure custom markers, warnings and custom summary reporter for pytest."""
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "slow: slow running tests")
    config.addinivalue_line(
        "filterwarnings",
        "ignore:.*Please use `import python_multipart` instead.*:PendingDeprecationWarning",
    )
    config.addinivalue_line(
        "filterwarnings",
        "ignore::PendingDeprecationWarning:starlette.formparsers",
    )

    terminalreporter = config.pluginmanager.get_plugin("terminalreporter")
    if terminalreporter is not None:
        original_short_test_summary = terminalreporter.short_test_summary

        def custom_short_test_summary():
            failed_reports = terminalreporter.stats.get("failed", [])
            for rep in failed_reports:
                if hasattr(rep, "user_metadata") and "card_name" in rep.user_metadata:
                    m = rep.user_metadata
                    card = m.get("card_name", "")
                    hit = m.get("hit_rate", 0.0)
                    min_hit = m.get("min_hit_rate", 0.0)
                    dist = m.get("average_distance", 0.0)
                    max_d = m.get("max_dist", 0.0)
                    rep.nodeid = card
                    if hasattr(rep, "longrepr") and hasattr(rep.longrepr, "reprcrash"):
                        rep.longrepr.reprcrash.message = ""
                    rep._custom_display_line = (
                        f"FAILED (hit_rate={hit:3.0f}% VS {min_hit:.0f}%, d_average={dist:4.2f} vs {max_d:4.2f}): {card}"
                    )

            import _pytest.terminal as pt
            original_get_line = pt._get_line_with_reprcrash_message

            def custom_get_line(cfg, rep, tw, word_markup):
                if hasattr(rep, "_custom_display_line"):
                    return tw.markup(rep._custom_display_line, red=True, bold=True)
                return original_get_line(cfg, rep, tw, word_markup)

            pt._get_line_with_reprcrash_message = custom_get_line
            try:
                original_short_test_summary()
            finally:
                pt._get_line_with_reprcrash_message = original_get_line

        terminalreporter.short_test_summary = custom_short_test_summary
