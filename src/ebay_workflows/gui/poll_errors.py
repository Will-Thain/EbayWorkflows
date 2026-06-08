from __future__ import annotations

from collections.abc import Callable

import structlog
from sqlalchemy.exc import SQLAlchemyError

logger = structlog.get_logger(__name__)


def is_poll_recoverable_error(exc: BaseException) -> bool:
    return isinstance(exc, (SQLAlchemyError, OSError))


class GuiPollErrorReporter:
    """Surface recoverable DB poll failures in the status bar and logs."""

    def __init__(self, on_message: Callable[[str | None], None] | None = None) -> None:
        self._on_message = on_message
        self._active_message: str | None = None

    def report_failure(self, exc: BaseException, *, context: str) -> None:
        if is_poll_recoverable_error(exc):
            logger.warning("gui_poll_failed", context=context, error=str(exc), exc_info=exc)
            message = f"{context}: database unavailable — retrying…"
        else:
            logger.error("gui_poll_unexpected", context=context, error=str(exc), exc_info=exc)
            message = f"{context}: refresh failed — retrying…"
        if message != self._active_message:
            self._active_message = message
            if self._on_message is not None:
                self._on_message(message)

    def report_success(self) -> None:
        if self._active_message is not None:
            self._active_message = None
            if self._on_message is not None:
                self._on_message(None)


def handle_poll_error(
    reporter: GuiPollErrorReporter | None,
    exc: BaseException,
    *,
    context: str,
) -> None:
    if reporter is None:
        if is_poll_recoverable_error(exc):
            logger.warning("gui_poll_failed", context=context, error=str(exc), exc_info=exc)
        else:
            logger.error("gui_poll_unexpected", context=context, error=str(exc), exc_info=exc)
        return
    reporter.report_failure(exc, context=context)
