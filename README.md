# template_python

Python project template with a ready-made [Claude Code](https://claude.com/claude-code) workflow: project rules, specialised agents, skills that chain them, and hooks that keep secrets and `main` safe. Derived from the way of working built for `equinox_management`.

## Start a project from it

1. Create a repository from this template (GitHub "Use this template") and clone it.
2. Install [uv](https://docs.astral.sh/uv/), then open Claude Code in the folder and run:
   ```
   /init-project
   ```
   It renames the package (`template_python` → yours), the distribution and the CLI, then fills the `TODO(project)` markers with you. Without Claude Code: `uv run python tools/init_project.py --name my_project --description "..."`.
3. Describe the milestones in `docs/roadmap.md`, then build them one by one with `/feature M1`, or all in a row with `/build-roadmap`.

## What is inside

| Path | Role |
|---|---|
| `CLAUDE.md` | Project rules read at the start of every session: invariants, commands, language, git workflow, definition of done |
| `src/template_python/<package>/CLAUDE.md` | Rules and module table of each package |
| `.claude/agents/` | `architect` (design note), `ui-designer` (UI design and review), `developer`, `tester`, `reviewer` (read-only), `documentation` |
| `.claude/skills/` | `/init-project`, `/feature` (chains the agents), `/build-roadmap` (autonomous, resumable), `/release`, `/add-fixture`, `/add-decision` |
| `.claude/hooks/` | `guard_paths.py` blocks secrets, protected folders, commits and pushes on `main`; `format.py` runs ruff on each edited file |
| `.claude/settings.json` | Allowed and denied commands, hook wiring |
| `docs/` | `architecture.md` (layers, responsibility map), `decisions.md` (D-NNN log), `roadmap.md`, `progress.md`, `architecture/` (design notes) |
| `tools/check_commit_message.py` | commit-msg hook: Conventional Commits + `Milestone:` footer |
| `.pre-commit-config.yaml`, `.github/workflows/ci.yml` | ruff, duplicate code, gitleaks; tests on Ubuntu, Windows, macOS |

## The workflow

```
/feature <request or milestone>
  architect      → docs/architecture/<date>-<slug>.md   (stops for approval if a decision is superseded)
  ui-designer    → UI design section                    (user-visible changes only)
  developer      → code + commits on dev
  tester         → tests/unit, tests/integration
  reviewer       → BLOCKING / TO FIX / SUGGESTION        (≤ 2 loops back to the developer)
  documentation  → docs, CLAUDE.md files, CHANGELOG
```

Every agent answers in at most ten lines; the details live in `docs/`.

## Development

```bash
uv sync
uv run pre-commit install
uv run pytest -q -n auto
uv run ruff check . && uv run ruff format --check .
uv run pylint --disable=all --enable=duplicate-code src
uv run template-python hello Ada
```

## License

MIT, see `LICENSE`.
