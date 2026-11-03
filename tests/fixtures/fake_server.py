"""A fake `rack serve` for supervisor tests: records its start, prints lines, exits with a code.

Usage: fake_server.py RECORD_DIR [--lines N] [--line-bytes B] [--run-s S] [--exit CODE] [--ignore-term]
Each start creates `RECORD_DIR/start-<n>` (n = 1, 2, ...) holding the PID, after printing its lines.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("record", type=Path)
    parser.add_argument("--lines", type=int, default=1)
    parser.add_argument("--line-bytes", type=int, default=0)
    parser.add_argument("--run-s", type=float, default=0.0)
    parser.add_argument("--exit", type=int, default=1)
    parser.add_argument("--ignore-term", action="store_true")
    args = parser.parse_args()
    if args.ignore_term:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    starts = len(list(args.record.glob("start-*"))) + 1
    for index in range(args.lines):
        print(f"fake line {starts}.{index} {'x' * args.line_bytes}".rstrip(), flush=True)
    (args.record / f"start-{starts}").write_text(str(os.getpid()), encoding="ascii")
    time.sleep(args.run_s)
    return args.exit


if __name__ == "__main__":
    sys.exit(main())
