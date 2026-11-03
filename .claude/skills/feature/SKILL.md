---
name: feature
description: Delivers a feature, fix or roadmap milestone end to end by chaining the architect, ui-designer (UI changes), developer, tester, reviewer and documentation agents. Use for any change request, e.g. "/feature M1" or "/feature add a --json option to the list command".
---

# Feature workflow

Input: a request in natural language, or a milestone id from docs/roadmap.md.

1. **architect** — produce the design note. If it says `NEEDS USER APPROVAL`, show the user a five-line summary and wait for approval before continuing. In **autonomous mode** (called from `/build-roadmap`), continue without waiting unless the note matches a stop condition of `/build-roadmap`; in that case, stop and report.
2. **ui-designer**, design mode — only when the change is user-visible: adds the UI design section to the design note. `NEEDS USER APPROVAL` is handled as in step 1.
3. **developer** — implement the design note, UI design section included.
4. **tester** — write and run unit and integration tests.
5. **reviewer** — review. For a UI change, run the **ui-designer** in review mode at the same time. If either reports a BLOCKING item, send both reports back to the developer (then tester again). At most two loops; after that, stop and report to the user.
6. **documentation** — update docs and Claude Code files.

Rules:
- Keep each agent's output to its ten-line summary. Do not paste logs into the conversation.
- Never push to `main`, never force-push. Pushing a feature branch or `dev` is allowed.

Final report to the user (at most fifteen lines): what was done, commits created, test status, open points, decisions needed.
