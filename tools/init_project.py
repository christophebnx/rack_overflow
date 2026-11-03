"""Turn the template into a project: rename the package, the distribution and the CLI.

    uv run python tools/init_project.py --name my_project [--description "..."] [--dry-run]

`template_python` becomes `my_project` (import package, folder `src/my_project/`) and
`template-python` becomes `my-project` (distribution and CLI) in every tracked text file.
Run it once, on a clean working tree, then `uv sync` (the lock file is rewritten by uv).
Once done, it removes itself, its test and the `/init-project` skill: they are template-only.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

OLD_PACKAGE = "template_python"
OLD_DIST = "template-python"
OLD_DESCRIPTION = "Python project template with a Claude Code workflow (agents, skills, hooks)."
PACKAGE = re.compile(r"^[a-z][a-z0-9_]*[a-z0-9]$")
# Never rewritten: binary or generated files, and this script (it must keep the old names).
TEMPLATE_ONLY = ("tools/init_project.py", "tests/unit/test_init_project.py", ".claude/skills/init-project")
SKIPPED = {"uv.lock", "LICENSE", *TEMPLATE_ONLY}


class InitError(Exception):
    """The project cannot be initialised as asked."""


def tracked_files(root: Path) -> list[Path]:
    """Files git tracks plus untracked ones not ignored (a fresh template may not be committed yet)."""
    command = ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    result = subprocess.run(command, cwd=root, capture_output=True, check=True)
    names = [name for name in result.stdout.decode("utf-8").split("\0") if name]
    return [root / name for name in sorted(set(names)) if not skipped(name) and (root / name).is_file()]


def renamed(path: Path, package: str) -> Path:
    """Where `path` lives once the package folder is renamed."""
    parts = path.parts
    if parts[:2] == ("src", OLD_PACKAGE):
        return Path("src", package, *parts[2:])
    return path


def skipped(name: str) -> bool:
    return any(name == path or name.startswith(f"{path}/") for path in SKIPPED)


def rewrite(text: str, package: str, description: str | None) -> str:
    text = text.replace(OLD_PACKAGE, package).replace(OLD_DIST, package.replace("_", "-"))
    if description:
        text = text.replace(OLD_DESCRIPTION, description)
    return text


def init_project(root: Path, package: str, description: str | None, dry_run: bool) -> list[Path]:
    """Rename everything; return the files changed (relative to `root`)."""
    if not PACKAGE.match(package) or "__" in package:
        raise InitError(f"'{package}' is not a valid package name (snake_case, starting with a letter)")
    if package == OLD_PACKAGE:
        raise InitError("choose a name other than the template's")
    source = root / "src" / OLD_PACKAGE
    if not source.is_dir():
        raise InitError(f"{source.relative_to(root)} not found: was the project already initialised?")
    changed: list[Path] = []
    for path in tracked_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new = rewrite(text, package, description)
        if new != text:
            changed.append(renamed(path.relative_to(root), package))
            if not dry_run:
                path.write_text(new, encoding="utf-8", newline="")
    if not dry_run:
        source.rename(source.with_name(package))
        remove_template_only(root)
    return changed


def remove_template_only(root: Path) -> None:
    for name in TEMPLATE_ONLY:
        path = root / name
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--name", required=True, help="import package name, snake_case")
    parser.add_argument("--description", help="one-line description for pyproject.toml")
    parser.add_argument("--dry-run", action="store_true", help="list the files that would change")
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1], help=argparse.SUPPRESS
    )
    args = parser.parse_args(argv)
    try:
        changed = init_project(args.root, args.name, args.description, args.dry_run)
    except InitError as error:
        print(f"init_project: error: {error}", file=sys.stderr)
        return 1
    verb = "would change" if args.dry_run else "changed"
    print(f"{verb} {len(changed)} files; package src/{OLD_PACKAGE} -> src/{args.name}")
    for path in changed:
        print(f"  {path.as_posix()}")
    if not args.dry_run:
        print("next: uv sync, then fill the TODO(project) markers (git grep -n 'TODO(project)')")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
