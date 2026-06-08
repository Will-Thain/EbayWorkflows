from __future__ import annotations

import logging

from ebay_workflows.logging_config import configure_logging


def test_configure_logging_uses_level_constants_not_functions() -> None:
    configure_logging("info")
    assert logging.getLogger().level == logging.INFO
    configure_logging("debug")
    assert logging.getLogger().level == logging.DEBUG
    configure_logging("warning")
    assert logging.getLogger().level == logging.WARNING
