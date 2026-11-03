---
name: add-decision
description: Records a decision taken in conversation in docs/decisions.md (new or superseding entry) and propagates it to the docs it affects. Use when the user settles a question, changes a rule, or says "note that", "from now on", "we decided".
---

# Add a decision

1. Read docs/decisions.md and find the next free id (`D-NNN`) and the section it belongs to.
2. Search for decisions it touches. A decision is never reversed silently: if it changes an existing one, mark the old one `**Superseded by D-NNN**` (keep its text) and say so in the new entry.
3. Write the entry: `**D-NNN — <the decision in one line>.**`, then why, then what it rules out (`Rejected: …`). Add the date and "user decision" when the user took it.
4. Propagate: CLAUDE.md invariants, the relevant package CLAUDE.md, docs/architecture.md, agents and skills if the way of working changes. Link to the decision instead of copying it.
5. Commit as `docs(docs): record D-NNN <short summary>` with the `Milestone:` footer of the current milestone.

Return at most five lines: the id, the superseded entries, the files updated.
