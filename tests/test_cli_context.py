from __future__ import annotations

from unittest.mock import patch

import pytest
import typer
from pydantic import ValidationError

from ebay_workflows.cli_context import load_settings


def test_load_settings_value_error() -> None:
    with patch("ebay_workflows.cli_context.Settings", side_effect=ValueError("bad policy")):
        with pytest.raises(typer.Exit) as exc:
            load_settings(action="test command")
        assert exc.value.exit_code == 2


def test_load_settings_validation_error() -> None:
    with patch(
        "ebay_workflows.cli_context.Settings",
        side_effect=ValidationError.from_exception_data("Settings", []),
    ):
        with pytest.raises(typer.Exit) as exc:
            load_settings(action="test command")
        assert exc.value.exit_code == 2
