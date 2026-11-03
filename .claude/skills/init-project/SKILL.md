---
name: init-project
description: Turns this template into a real project: renames the package, distribution and CLI, then fills the TODO(project) markers with the user. Use once, right after creating a repository from the template, or when the user says "initialise", "set up the project", "rename the package".
---

# Initialise a project from the template

1. Ask the user (only what is not already given): the import package name (snake_case), a one-line description, the user language of the app, whether it has a UI (keep or delete the `ui-designer` agent).
2. Run `uv run python tools/init_project.py --name <package> --description "<text>"`. It renames `src/template_python/`, the distribution and CLI (`<package>` with hyphens) and every reference in the tree. Then `git grep -n -e template_python -e template-python` must list nothing.
3. Work through `git grep -n "TODO(project)"` with the user: CLAUDE.md (what this is, invariants, user language, out of scope), docs/architecture.md (overview, layers), docs/roadmap.md (milestones after B0), README.md. Do not invent business rules: ask.
4. Record the choices as decisions with `/add-decision` (app language, UI or not, anything settled in step 3).
5. Run `uv sync`, `uv run pre-commit install`, `uv run pytest -q -n auto`, `uv run ruff check .`.
6. Commit on a branch (never `main`): `chore(claude): initialise project from template` with the footer `Milestone: B0`. Mark B0 `done` in docs/progress.md once CI is green.

Final report (at most ten lines): names chosen, files changed, TODO markers left, next step (`/build-roadmap`).
