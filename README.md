# Rack Overflow

Personal training tracker: exercise catalog with shared variables, session templates organised as menus by movement pattern, fast set logging from the phone, and minimal progress tracking (records, RM, charts). One responsive web app (FastAPI, Jinja2, htmx, SQLite) for a single user, deployed natively on a Synology NAS. The interface is in French.

Status: V1 in development. Scope and milestones: [`docs/release-1.0.0-brief.md`](docs/release-1.0.0-brief.md), [`docs/roadmap.md`](docs/roadmap.md); where the build stands: [`docs/progress.md`](docs/progress.md).

## Documentation

| File | Content |
|---|---|
| `CLAUDE.md` | Project rules: invariants, commands, language, git workflow, definition of done |
| `docs/release-1.0.0-brief.md` | Approved V1 brief: scope, requirements, storage model, milestones, settled questions |
| `docs/roadmap.md` | Milestones B0, L1a … L6 with their acceptance criteria |
| `docs/progress.md` | Build status per milestone |
| `docs/architecture.md` | Layers, flows, responsibility map, configuration |
| `docs/decisions.md` | Decision log (D-NNN) |
| `docs/ui-spec.md` | UI rules and screens |
| `docs/architecture/` | Design notes, one per change |
| `docs/deployment/nas.md` | Install, pairing and update on the Synology NAS (LAN only) |

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pre-commit install
uv run pytest -q -n auto
uv run ruff check . && uv run ruff format --check .
uv run pylint --disable=all --enable=duplicate-code src
uv run rack migrate --config config.example.toml   # create / upgrade the database, seed the exercises and session templates
uv run rack serve --config config.example.toml   # http://127.0.0.1:8765
```

Every page except `/appairage` needs a paired browser: run `uv run rack device add NAME --config config.example.toml` and type the printed code. More commands (backup, devices, supervise, update, browser tests): `CLAUDE.md`, section "Commands". NAS install: [`docs/deployment/nas.md`](docs/deployment/nas.md).

No automatic CI until V1 is done (D-012): checks run locally and in pre-commit.

## Claude Code workflow

Changes go through `/feature` (architect → ui-designer → developer → tester → reviewer → documentation); `/build-roadmap` builds the milestones in order and resumes from `docs/progress.md`. Hooks keep secrets unread and `main` untouched. Details in `CLAUDE.md` and `.claude/`.

## License

MIT, see `LICENSE`.
