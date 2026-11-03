---
name: release
description: Prepares a new version: version bump, changelog, checks, local annotated tag. Use when the user asks for a release.
---

# Release

1. Run the full suite: `uv run pytest -q -n auto -m "not live"`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pylint --disable=all --enable=duplicate-code src`. Stop on any failure.
2. Ask the user for the version number if not given (semantic versioning).
3. Update `version` in pyproject.toml (`__version__` is read from the installed metadata, nothing else to edit).
4. Move CHANGELOG.md [Unreleased] entries under the new version with today's date.
5. Check that docs/roadmap.md and docs/progress.md reflect what is shipped.
6. Run `uv lock` so `uv.lock` carries the new version. Commit `pyproject.toml`, `uv.lock`, `CHANGELOG.md` and the docs as `chore(release): release vX.Y.Z` (with the `Milestone:` footer). Create the local annotated tag on that commit: `git tag -a vX.Y.Z -m "vX.Y.Z"`.
7. Push the branch only (`git push -u origin <branch>`), never the tag, never to `main`, never forced. Tell the user: after merging the pull request with a merge commit, push the tag (`git push origin vX.Y.Z`); after a squash or rebase merge, re-create the tag on the merged commit of `main` instead.
