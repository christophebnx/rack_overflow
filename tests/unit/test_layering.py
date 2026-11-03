"""Import rules (CLAUDE.md invariant 1), checked by scanning the source with `ast`.

Add a row to `ALLOWED` for every new package: the packages of the project it may import.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_NAME = "template_python"
PACKAGE = Path(__file__).resolve().parents[2] / "src" / PACKAGE_NAME

# package -> project packages it may import (itself always allowed)
ALLOWED: dict[str, set[str]] = {
    "domain": set(),
    "storage": {"domain"},
}


def _imports(path: Path) -> set[str]:
    """Absolute names of every module imported by `path` (relative imports resolved)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    parts = list(path.relative_to(PACKAGE.parent).with_suffix("").parts)
    package = parts[:-1]  # the package a relative import starts from (also right for __init__)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)]
                names.add(".".join(base + ([node.module] if node.module else [])))
            elif node.module:
                names.add(node.module)
    return names


def _project_packages(path: Path) -> set[str]:
    """Top-level project packages imported by `path` (`template_python.x.y` -> `x`)."""
    found = set()
    for name in _imports(path):
        parts = name.split(".")
        if parts[0] == PACKAGE_NAME and len(parts) > 1:
            found.add(parts[1])
    return found


@pytest.mark.parametrize("package", sorted(ALLOWED))
def test_package_imports_only_allowed_layers(package: str) -> None:
    allowed = ALLOWED[package] | {package}
    offenders = {
        f"{path.relative_to(PACKAGE).as_posix()}: {sorted(_project_packages(path) - allowed)}"
        for path in sorted((PACKAGE / package).rglob("*.py"))
        if _project_packages(path) - allowed
    }
    assert not offenders


def test_every_package_has_a_layer_rule_and_a_claude_md() -> None:
    packages = {path.parent.name for path in PACKAGE.glob("*/__init__.py")}
    assert packages == set(ALLOWED)
    assert all((PACKAGE / package / "CLAUDE.md").is_file() for package in packages)


def test_scanner_resolves_relative_imports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / PACKAGE_NAME
    (root / "domain").mkdir(parents=True)
    module = root / "domain" / "bad.py"
    module.write_text("from ..storage import files\nfrom . import errors\n", encoding="utf-8")
    monkeypatch.setattr(f"{__name__}.PACKAGE", root)
    assert _project_packages(module) == {"storage", "domain"}
