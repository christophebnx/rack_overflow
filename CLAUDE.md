# template_python — project rules

Read this file at the start of every session. It is the source of truth for how to work on this repository. When a rule here conflicts with your own habit, the rule wins. When a request conflicts with a rule, say so before doing anything.

> **Template.** This repository is a starting point. Run `/init-project` once (or `uv run python tools/init_project.py --name <package>`) to rename the package, then replace every `TODO(project)` marker in this file and in `docs/`. Delete this note when done.

## What this is

TODO(project): one paragraph on what the application does, for whom, and where it runs. Then a numbered list of its main capabilities.

Read next: `docs/architecture.md` (how), `docs/decisions.md` (why), `docs/roadmap.md` (what to build, in order), `docs/progress.md` (where the build stands).

## Commands

```bash
uv sync                                   # install (creates .venv and uv.lock)
uv run pre-commit install                 # pre-commit and commit-msg hooks
uv run pytest -q -n auto -m "not live"    # tests in parallel; drop -n auto to debug one test
uv run ruff check . && uv run ruff format --check .
uv run pylint --disable=all --enable=duplicate-code src
uv run template-python --version          # the CLI
```

## Invariants — never violate

1. **Layering.** `domain/` is pure business logic: it imports nothing from other packages of `template_python`, does no I/O, reads no clock or environment implicitly (pass `now`, paths and values in). Everything else may depend on `domain/`. `tests/unit/test_layering.py` enforces this.
2. **One responsibility, one implementation.** Before writing a function, check the responsibility map in `docs/architecture.md` and search the codebase. Reuse or extend; write new code only when nothing fits, and say why in your summary. Similar-looking code with a different responsibility is fine.
3. **File writes are atomic.** Every write of a user or state file goes through `storage/files.atomic_write` (temp file + fsync + rename). No partial state on failure.
4. **Never read secrets.** Never read `.env`, `config.toml`, `.local/credentials/`, or any real user data. Work only with `.local/dev-data/` and `tests/fixtures/`. A hook enforces this.
5. **Tests never call paid or remote services by default.** Such tests carry `@pytest.mark.live` and are excluded by `addopts`.
6. **Decisions are recorded.** A decision that changes how the system behaves goes into `docs/decisions.md`. A decision is never reversed silently: add an entry that supersedes it.
7. TODO(project): add the business invariants of this project (units, identifiers, data formats, what may never be deleted…).

## Language convention

- English: code, identifiers, JSON keys, file and folder names, every `.md` in the repo, prompts, skills, agents, commit messages.
- User language (TODO(project): French by default?): UI strings, exported content, messages shown to the end user.

## How to work

- For any feature or change, use the `/feature` skill: architect → ui-designer (UI changes only) → developer → tester → reviewer (+ ui-designer review for UI changes) → documentation.
- To build the roadmap autonomously, or resume it, use `/build-roadmap`. Progress and blocking questions live in `docs/progress.md`.
- Each agent returns at most ten lines. Details go into `docs/`, not into the conversation.
- Definition of done: tests green (`not live`), ruff clean, no new duplicate-code finding, docs and the relevant `CLAUDE.md` updated, `CHANGELOG.md` entry added.
- Each package under `src/template_python/` has its own `CLAUDE.md` (rules and module table). Read it before touching the package; keep it true after.

## Git workflow

- **Never commit on `main`.** Work on a feature branch or on `dev`. The user merges into `main` through a pull request.
- **Clean commits.** One commit per coherent unit of work (a module and its tests, a fix, a docs update), never one commit per agent and never "WIP". Every commit leaves the tree green.
- **Message format** (Conventional Commits, English):
  ```
  <type>(<scope>): <imperative summary, max 72 chars>

  <why and what, wrapped at 72 chars>

  Milestone: <id from docs/roadmap.md, e.g. B0, M1, S2.3>
  ```
  Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`. Scope: the layer or area (`domain`, `storage`, `cli`, `docs`, `claude`, `ci`, `deps`…).
- Code and the docs it changes go in the same commit. Milestone-wide doc updates (roadmap, progress, changelog) go in a final `docs` commit for that milestone.
- To correct the last unpushed commit, use `git commit --amend`. Never rewrite earlier history, never force-push, never delete a branch.
- Stage files explicitly (`git add <paths>`); never commit `.env`, `config.toml` or anything under `.local/`.
- Enforced: a Claude Code hook blocks `git commit` and `git push` on `main`; the `commit-msg` hook (`tools/check_commit_message.py`) rejects malformed messages; pre-commit runs ruff, duplicate detection and gitleaks.

## Out of scope (do not build unless asked)

- TODO(project): list what is explicitly not part of this version.
