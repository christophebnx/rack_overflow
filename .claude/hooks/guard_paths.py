"""PreToolUse hook: block access to secrets and protected folders, and commits or pushes on main.

Claude Code sends the tool call as JSON on stdin. Exit code 2 blocks the call and
shows stderr to Claude. Cross-platform: pure Python, standard library only.

Adapt the three constants below to the project; keep `tests/unit/test_guard_paths.py` in step.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Files that hold secrets or machine-specific settings (relative to the repository).
SECRET_FILES = (".env", "config.toml")
# Folders whose whole content is off limits (OAuth grants, real user data…).
PROTECTED_DIRS = (".local/credentials",)
# Branches that never receive a commit or a push from Claude Code.
PROTECTED_BRANCHES = frozenset({"main", "master"})

SECRET_IN_COMMAND = re.compile(
    r"(?<![\w.])\.env(?![\w.])|(?<![\w.])config\.toml(?![\w.])|\.local[/\\]+credentials"
)
GIT_COMMIT = re.compile(r"(^|[;&|(]\s*)git\s+commit\b")
GIT_PUSH = re.compile(r"(^|[;&|(]\s*)git\s+push\b(?P<args>[^;&|]*)")


def current_branch() -> str:
    command = ["git", "symbolic-ref", "--short", "-q", "HEAD"]
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True, check=False)
    return result.stdout.strip()


def is_inside(path: Path, folder: Path) -> bool:
    try:
        path.relative_to(folder)
    except ValueError:
        return False
    return True


def pushes_protected(args: str, branch: str) -> bool:
    """True when a `git push` targets a protected branch, explicitly or as the current branch."""
    words = [word for word in args.split() if not word.startswith("-")]
    refs = words[1:]  # first word is the remote
    if not refs:
        return branch in PROTECTED_BRANCHES
    targets = {ref.split(":")[-1].removeprefix("refs/heads/") for ref in refs}
    if "HEAD" in targets:
        targets.add(branch)
    return bool(targets & PROTECTED_BRANCHES)


def block(reason: str) -> None:
    print(f"Blocked by guard_paths: {reason}.", file=sys.stderr)
    sys.exit(2)


def check_command(command: str) -> None:
    if SECRET_IN_COMMAND.search(command):
        block("command references a secret file or a protected folder")
    if GIT_COMMIT.search(command) and current_branch() in PROTECTED_BRANCHES:
        block("commits on a protected branch are not allowed; switch to a feature branch")
    for match in GIT_PUSH.finditer(command):
        if pushes_protected(match.group("args"), current_branch()):
            block("pushing to a protected branch is not allowed; push a feature branch")


def check_path(raw: str) -> None:
    path = Path(raw).expanduser()
    path = (path if path.is_absolute() else REPO / path).resolve()
    if path in {(REPO / name).resolve() for name in SECRET_FILES}:
        block(f"{path.name} contains secrets or machine-specific settings")
    for folder in PROTECTED_DIRS:
        if is_inside(path, (REPO / folder).resolve()):
            block(f"path is inside {folder}, which is protected")


def main() -> None:
    call = json.load(sys.stdin)
    args = call.get("tool_input") or {}
    if call.get("tool_name") == "Bash":
        check_command(args.get("command", ""))
        return
    raw = args.get("file_path") or args.get("notebook_path") or args.get("path")
    if raw:
        check_path(raw)


if __name__ == "__main__":
    main()
