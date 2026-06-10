"""Enforce ADR 0002: only recognition/ and adapters/ may import mtg_card_recognition."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "ebay_workflows"
ALLOWED_PREFIXES = (
    SRC / "recognition",
    SRC / "adapters",
)
FORBIDDEN_PREFIXES = (
    SRC / "workflows",
    SRC / "candidates",
    SRC / "scoring",
    SRC / "operations",
    SRC / "gui",
    SRC / "cli",
    SRC / "integrations",
    SRC / "persistence",
)


def _imports_mtg(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "mtg_card_recognition" or alias.name.startswith("mtg_card_recognition."):
                    hits.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "mtg_card_recognition" or node.module.startswith("mtg_card_recognition."):
                hits.append((node.lineno, f"from {node.module} import ..."))
    return hits


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def test_only_recognition_and_adapters_import_mtg_library() -> None:
    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if _under(path, SRC / "recognition") or _under(path, SRC / "adapters"):
            continue
        hits = _imports_mtg(path)
        if not hits:
            continue
        rel = path.relative_to(SRC.parent.parent)
        for lineno, stmt in hits:
            violations.append(f"{rel}:{lineno}: {stmt}")

    assert not violations, "Direct mtg_card_recognition imports outside recognition/adapters:\n" + "\n".join(
        violations
    )


def test_workflows_package_has_no_direct_mtg_imports() -> None:
    violations: list[str] = []
    for path in sorted((SRC / "workflows").glob("*.py")):
        for lineno, stmt in _imports_mtg(path):
            violations.append(f"{path.name}:{lineno}: {stmt}")
    assert not violations, "workflows/ must not import mtg_card_recognition directly:\n" + "\n".join(violations)
