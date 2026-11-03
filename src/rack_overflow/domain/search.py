"""Fuzzy ranking of exercises by name and aliases (D-056), pure Python over about a hundred strings.

Each text of a candidate (its name and each alias, normalised) gets the score of the first tier it
matches; the candidate keeps its best score. Ties: position in `recent` (L4), then name, then id.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from rack_overflow.domain.text import normalise

LIMIT = 20
STOP_WORDS = frozenset(
    {"a", "au", "aux", "d", "de", "des", "du", "en", "et", "l", "la", "le", "les", "un", "une"}
)
FUZZY_MIN = 4
"""Query tokens shorter than this must prefix-match exactly."""
FUZZY_WIDE = 7
"""From this length a query token tolerates two edits, below it one (« devlope » → « developpe »)."""

EXACT, PREFIX, TOKENS, INITIALS, SUBSTRING, FUZZY = 100, 90, 80, 70, 60, 40


@dataclass(frozen=True)
class Candidate:
    """An exercise as search sees it."""

    id: int
    name: str
    aliases: tuple[str, ...] = ()


def rank(
    query: str, candidates: Iterable[Candidate], *, limit: int = LIMIT, recent: Sequence[int] = ()
) -> list[int]:
    """Ids of the candidates matching `query`, best first; an empty query lists every candidate."""
    q = normalise(query)
    order = {exercise_id: position for position, exercise_id in enumerate(recent)}
    scored: list[tuple[int, int, str, int]] = []
    for candidate in candidates:
        name = normalise(candidate.name)
        best = 1 if not q else max(score(q, text) for text in (name, *map(normalise, candidate.aliases)))
        if best > 0:
            scored.append((-best, order.get(candidate.id, len(order)), name, candidate.id))
    scored.sort()
    ids = [entry[3] for entry in scored]
    return ids if not q else ids[:limit]


def score(q: str, text: str) -> int:
    """Score of one normalised text for the normalised query `q` (0: no match)."""
    if not text:
        return 0
    if text == q:
        return EXACT
    if text.startswith(q):
        return PREFIX
    q_tokens, tokens = q.split(), text.split()
    if _tokens_prefix(q_tokens, tokens):
        return TOKENS
    if " " not in q and len(q) >= 2 and _initials(tokens).startswith(q):
        return INITIALS
    if q in text:
        return SUBSTRING
    if all(_fuzzy_token(token, tokens) for token in q_tokens):
        return FUZZY
    return 0


def _tokens_prefix(q_tokens: Sequence[str], tokens: Sequence[str]) -> bool:
    """Every query token is a prefix of a distinct text token, in any order."""
    if not q_tokens:
        return True
    head, rest = q_tokens[0], q_tokens[1:]
    for index, token in enumerate(tokens):
        if token.startswith(head) and _tokens_prefix(rest, [*tokens[:index], *tokens[index + 1 :]]):
            return True
    return False


def _initials(tokens: Sequence[str]) -> str:
    return "".join(token[0] for token in tokens if token not in STOP_WORDS)


def _fuzzy_token(q_token: str, tokens: Sequence[str]) -> bool:
    if len(q_token) < FUZZY_MIN:
        return any(token.startswith(q_token) for token in tokens)
    bound = 2 if len(q_token) >= FUZZY_WIDE else 1
    return any(prefix_distance(q_token, token, bound) <= bound for token in tokens)


def prefix_distance(q: str, text: str, bound: int) -> int:
    """Smallest Levenshtein distance between `q` and a prefix of `text`, or `bound + 1` once it
    is certain to exceed `bound` (early exit)."""
    previous = list(range(len(text) + 1))
    for row, q_char in enumerate(q, start=1):
        current = [row]
        for column, char in enumerate(text, start=1):
            cost = 0 if q_char == char else 1
            current.append(min(previous[column] + 1, current[column - 1] + 1, previous[column - 1] + cost))
        if min(current) > bound:
            return bound + 1
        previous = current
    return min(min(previous), bound + 1)
