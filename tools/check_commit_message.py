"""commit-msg hook: enforce the commit format described in CLAUDE.md.

<type>(<scope>): <summary, max 72 chars>
<blank line>
<body>
Milestone: <id from docs/roadmap.md>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TYPES = "feat|fix|refactor|test|docs|chore|ci"
HEADER = re.compile(rf"^({TYPES})\([a-z][a-z0-9-]*\): \S.*$")
HEADER_LIMIT = 72
MILESTONE = re.compile(r"^Milestone: [A-Z][A-Za-z0-9.-]*$", re.MULTILINE)
# Messages git writes itself; they are not checked.
GENERATED = re.compile(r"^(Merge|Revert|fixup!|squash!|amend!) ")


def problems(text: str) -> list[str]:
    """Every rule the message breaks (empty when it is valid)."""
    lines = [line for line in text.splitlines() if not line.startswith("#")]
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and GENERATED.match(lines[0]):
        return []
    errors = []
    if not lines or not HEADER.match(lines[0]):
        errors.append(f"first line must be '<type>(<scope>): <summary>' (types: {TYPES.replace('|', ', ')})")
    elif len(lines[0]) > HEADER_LIMIT:
        errors.append(f"first line must be at most {HEADER_LIMIT} characters")
    if len(lines) > 1 and lines[1].strip():
        errors.append("second line must be blank")
    if not MILESTONE.search("\n".join(lines)):
        errors.append("missing footer 'Milestone: <id>' (an id from docs/roadmap.md, e.g. B0, M1, S2.3)")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    errors = problems(Path(args[0]).read_text(encoding="utf-8"))
    for error in errors:
        print(f"commit message: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
