import pytest

from test.e2e_browser.harness import studio, studio_server

__all__ = ["studio", "studio_server"]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    report = (yield).get_result()
    if report.when == "call":
        item.call_passed = report.passed
