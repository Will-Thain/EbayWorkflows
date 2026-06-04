from __future__ import annotations

from ebay_workflows.cli_launch import project_root, resolve_cli_launch
from ebay_workflows.gui.workflow_catalog import build_argv


def test_project_root_contains_pyproject() -> None:
    assert (project_root() / "pyproject.toml").is_file()


def test_resolve_cli_launch_includes_phase_command() -> None:
    argv = build_argv("phase2", {"top_k": 5})
    program, args = resolve_cli_launch(argv)
    assert program
    assert "phase2-match-title" in args
    assert "5" in args


def test_build_argv_export() -> None:
    argv = build_argv("export", {"limit": 100, "output": "./data/out.json"})
    assert "export-rankings" in argv
    assert "100" in argv
    assert "./data/out.json" in argv
