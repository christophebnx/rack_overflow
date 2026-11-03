# Roadmap

Run each milestone through `/feature` (or all of them with `/build-roadmap`), on the branch `dev`. A milestone is done when its acceptance criteria pass, tests are green, docs are updated and its commits follow the git workflow in CLAUDE.md. Claude Code pushes `dev` at the end of each milestone; the user reviews and merges.

Milestone ids are used in the `Milestone:` footer of every commit: `B0`, `M0`, `M1`… (any id starting with a capital letter, e.g. `S2.3`, is accepted).

## B0 — Bootstrap (first run in a new repository)

- Run `/init-project` (renames the package, fills the `TODO(project)` markers with the user).
- `uv sync` to create `uv.lock` (versioned), then `uv run pre-commit install`.
- Check that both Claude Code hooks run on this machine: a read of `.env` is blocked; an edited Python file is formatted; `git commit` on `main` is blocked. If a hook command fails (OS, shell), adapt `.claude/settings.json` and record it in `docs/decisions.md`.
- Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q -n auto`.
- Commit on `dev` in clean commits with the footer `Milestone: B0`, push `dev`, then stop and ask the user to check CI is green.

Done when: the B0 commits exist on `dev`, tests and lint pass locally, the hooks are confirmed working, and `dev` is pushed with CI green.

## M0 — Skeleton

TODO(project): replace the example `hello` command and `domain/greeting.py` with the first real command and domain module.

- Configuration loading (`config.py`): settings file, data folder, secrets loaded lazily only where needed.
- CLI commands as stubs (exit 1 "not implemented yet").

Done when: TODO(project) acceptance criteria.

## M1 — TODO(project)

- …

Done when: …
