"""tools/init_project.py on a copy of the template (removed with the script once a project is initialised)."""

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "init_project.py"
spec = importlib.util.spec_from_file_location("init_project", TOOL)
assert spec and spec.loader
init = importlib.util.module_from_spec(spec)
spec.loader.exec_module(init)


@pytest.fixture
def template(tmp_path: Path) -> Path:
    root = tmp_path / "copy"
    for name in ["pyproject.toml", "CLAUDE.md", "src", "tools", "tests/unit", ".claude/skills/init-project"]:
        source, target = REPO / name, root / name
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


def test_renames_package_distribution_and_cli(template: Path) -> None:
    changed = init.init_project(template, "my_app", "My app.", dry_run=False)
    assert Path("pyproject.toml") in changed
    assert Path("src/my_app/cli.py") in changed
    pyproject = (template / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "my-app"' in pyproject
    assert 'my-app = "my_app.cli:main"' in pyproject
    assert 'description = "My app."' in pyproject
    assert (template / "src" / "my_app" / "cli.py").is_file()
    assert not (template / "src" / "template_python").exists()
    assert 'PROG = "my-app"' in (template / "src" / "my_app" / "cli.py").read_text(encoding="utf-8")


def test_removes_template_only_files(template: Path) -> None:
    init.init_project(template, "my_app", None, dry_run=False)
    assert not (template / "tools" / "init_project.py").exists()
    assert not (template / "tests" / "unit" / "test_init_project.py").exists()
    assert not (template / ".claude" / "skills" / "init-project").exists()
    leftovers = [
        path
        for path in template.rglob("*")
        if path.is_file() and ".git" not in path.parts and "template_python" in path.read_text("utf-8")
    ]
    assert leftovers == []


def test_dry_run_changes_nothing(template: Path) -> None:
    before = (template / "pyproject.toml").read_text(encoding="utf-8")
    assert init.init_project(template, "my_app", None, dry_run=True)
    assert (template / "pyproject.toml").read_text(encoding="utf-8") == before
    assert (template / "src" / "template_python").is_dir()


@pytest.mark.parametrize("name", ["MyApp", "my-app", "1app", "template_python", "a__b", "app_"])
def test_refuses_bad_names(template: Path, name: str) -> None:
    with pytest.raises(init.InitError):
        init.init_project(template, name, None, dry_run=False)


def test_second_run_is_refused(template: Path) -> None:
    init.init_project(template, "my_app", None, dry_run=False)
    with pytest.raises(init.InitError, match="already initialised"):
        init.init_project(template, "other", None, dry_run=False)
