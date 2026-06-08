from __future__ import annotations

from ebay_workflows.gui.poll_errors import GuiPollErrorReporter, is_poll_recoverable_error
from sqlalchemy.exc import OperationalError


def test_is_poll_recoverable_error() -> None:
    assert is_poll_recoverable_error(OSError("connection reset")) is True
    assert is_poll_recoverable_error(OperationalError("stmt", {}, Exception())) is True
    assert is_poll_recoverable_error(ValueError("bad")) is False


def test_gui_poll_error_reporter_messages() -> None:
    messages: list[str | None] = []
    reporter = GuiPollErrorReporter(on_message=messages.append)
    reporter.report_failure(OSError("down"), context="Dashboard")
    assert messages[-1] == "Dashboard: database unavailable — retrying…"
    reporter.report_success()
    assert messages[-1] is None
