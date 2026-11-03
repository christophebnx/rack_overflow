# Architecture

How the system is built. Why it is built that way: `docs/decisions.md`. Design notes of each change: `docs/architecture/`.

## Overview

TODO(project): what runs where, the main flows (one short paragraph or a diagram each).

## Layers

| Package | Role | May import (project packages) |
|---|---|---|
| `domain/` | Pure business logic: models, rules, validation. No I/O, no clock, no environment (D-003). | nothing |
| `storage/` | File system and persistence; the single atomic writer. | `domain` |
| `cli.py` | Command-line entry point: parses arguments, calls the layers, maps errors to exit codes (D-004). | everything |

Add a row when adding a package, and the matching entry in `ALLOWED` of `tests/unit/test_layering.py`. Each package has a `CLAUDE.md` with its rules and module table.

## Responsibility map

One responsibility, one implementation (CLAUDE.md invariant 2). Check here before writing code; update this table when adding a cross-cutting responsibility.

| Responsibility | Implementation |
|---|---|
| Base class of business errors | `domain/errors.DomainError` |
| Write a file atomically (temp + fsync + rename) | `storage/files.atomic_write` |
| Map an error to a CLI exit code and message | `cli.main` |
| Check a commit message | `tools/check_commit_message.problems` |
| Block secrets, protected folders, commits and pushes on `main` (Claude Code) | `.claude/hooks/guard_paths.py` |
| Format and lint-fix an edited file (Claude Code) | `.claude/hooks/format.py` |

## Configuration

TODO(project): where settings live. Convention of this template: secrets in `.env` (git-ignored, template in `.env.example`), machine-specific settings in `config.toml` (git-ignored), local runtime data in `.local/` (git-ignored; `.local/dev-data/` for development, `.local/credentials/` never read by Claude Code).
