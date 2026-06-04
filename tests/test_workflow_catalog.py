from __future__ import annotations

from ebay_workflows.gui.job_runner import project_root, resolve_cli_launch
from ebay_workflows.gui.workflow_catalog import build_argv


def test_build_argv_phase3() -> None:
    argv = build_argv("phase3")
    assert argv[0] == "ebay-workflows"
    assert "phase3-join-prices" in argv


def test_resolve_cli_launch() -> None:
    argv = build_argv("integrity")
    program, args = resolve_cli_launch(argv)
    assert program
    assert "data-integrity-check" in args


def test_project_root_is_repo() -> None:
    root = project_root()
    assert (root / "pyproject.toml").is_file()
