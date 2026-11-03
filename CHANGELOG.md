# Changelog

All notable changes are listed here, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow semantic versioning.

## [Unreleased]

- Project template: `src/` layout managed with uv, pure `domain/` layer with a layering test, atomic file writer, example CLI.
- Claude Code workflow: project rules (`CLAUDE.md`), six agents (architect, ui-designer, developer, tester, reviewer, documentation), skills `/init-project`, `/feature`, `/build-roadmap`, `/release`, `/add-fixture`, `/add-decision`, hooks guarding secrets and `main` and formatting edited files.
- Quality gates: commit-msg check, pre-commit (ruff, duplicate code, gitleaks), CI on Ubuntu, Windows and macOS.
