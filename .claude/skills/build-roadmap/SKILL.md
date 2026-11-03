---
name: build-roadmap
description: Builds the project autonomously, milestone after milestone from docs/roadmap.md, resuming from docs/progress.md. Stops only on the conditions listed here. Use when the user asks to build, continue or resume the roadmap.
---

# Autonomous build

You orchestrate. Delegate each milestone to `/feature` in autonomous mode. Keep only short summaries in this conversation; the state lives in docs/progress.md.

## Start or resume

1. Read CLAUDE.md, docs/roadmap.md and docs/progress.md.
2. If docs/progress.md says `BLOCKED`, show the blocking question to the user and stop until it is answered.
3. Work on the branch `dev` (create it from `main` if missing). Never commit on `main`, never push to `main`, never force-push.
4. If `B0 Bootstrap` is not `done`, run it first, directly (no `/feature`), following docs/roadmap.md. It ends with a stop: push `dev`, then the user confirms CI is green and reruns `/build-roadmap`.
5. Take the first milestone not marked `done`.

## For each milestone

1. Mark it `in progress` in docs/progress.md, then run `/feature <milestone>` in **autonomous mode**: the design note does not wait for approval unless a stop condition below applies.
2. When the milestone's acceptance criteria pass and the definition of done in CLAUDE.md is met, update docs/progress.md: status `done`, commit hash, three-line summary, open points.
3. Check the milestone's commits follow the git workflow in CLAUDE.md, and finish with a `docs` commit for progress, roadmap and changelog. Push `dev` (`git push -u origin dev`). Continue with the next milestone. Use `/compact` between milestones if the conversation grows long.

## Fixtures

If a milestone needs fixtures and tests/fixtures/ has none for a case, build synthetic ones with `/add-fixture` (never from real user data).

## Stop conditions (write `BLOCKED` in docs/progress.md, report, stop)

- Tests still failing after three fix attempts on the same problem.
- The reviewer still reports BLOCKING items after two developer loops.
- The design would supersede a decision in docs/decisions.md, change a data format already released, or add user-visible behaviour the docs do not describe.
- Something only the user can provide: a secret, real data, a manual check on their machine, a choice between options with no documented preference.
- A command needs a permission that is not granted, or would touch anything outside the repository and `.local/`.
- Usage limits reached: record where you are so the next run resumes cleanly.

When stopping, write in docs/progress.md: the milestone, what was tried, the exact question or action needed from the user.

## Never

- Committing on `main`, pushing to `main`, force-pushing, hard reset, rewriting history beyond `--amend` of the last unpushed commit, deleting a branch.
- Calling a paid or remote service (`live` tests), or reading `.env`, `config.toml`, `.local/credentials/` or real user data.
- Weakening a test, an invariant or a hook to get past a failure.

## Final report (at most fifteen lines)

Milestones done, commits, test status, what remains, and any question for the user.
