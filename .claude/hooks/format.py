"""PostToolUse hook: format and lint-fix the Python file that was just edited.

Never blocks: formatting problems are reported by the reviewer and CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    call = json.load(sys.stdin)
    raw = (call.get("tool_input") or {}).get("file_path")
    if not raw or not raw.endswith(".py"):
        return
    path = Path(raw)
    if not path.exists():
        return
    for args in (["format", str(path)], ["check", "--fix", "--quiet", str(path)]):
        subprocess.run([sys.executable, "-m", "ruff", *args], check=False, capture_output=True)


if __name__ == "__main__":
    main()
