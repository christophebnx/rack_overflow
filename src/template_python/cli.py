"""Command-line entry point.

Exit codes: 0 success, 1 error, 2 usage (no command, unknown command, bad option).
Errors print `template-python: error: <message>` on stderr. Tests call `main([...])` in-process.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from template_python import __version__
from template_python.domain.errors import DomainError
from template_python.domain.greeting import greeting

PROG = "template-python"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROG, description="TODO(project) one-line description.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="<command>")
    hello = commands.add_parser("hello", help="print a greeting (example command, replace it)")
    hello.add_argument("name", nargs="?", default="world")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_usage(sys.stderr)
        return 2
    try:
        if args.command == "hello":
            print(greeting(args.name))
    except DomainError as error:
        print(f"{PROG}: error: {error}", file=sys.stderr)
        return 1
    return 0
