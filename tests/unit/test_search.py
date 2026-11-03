"""Fuzzy ranking (D-056)."""

from __future__ import annotations

import pytest

from rack_overflow.domain import search
from rack_overflow.domain.search import Candidate, rank, score

BENCH = Candidate(1, "Développé couché (barre)", ("DC", "Bench press"))
DUMBBELL = Candidate(2, "Développé couché haltères", ("DC haltères",))
SQUAT = Candidate(3, "Squat au rack (barre)", ("Back squat",))
SWING = Candidate(4, "Kettlebell swing", ("Swing", "KB swing"))
CANDIDATES = [BENCH, DUMBBELL, SQUAT, SWING]


@pytest.mark.parametrize(
    ("query", "text", "expected"),
    [
        ("developpe couche barre", "developpe couche barre", search.EXACT),
        ("devel", "developpe couche barre", search.PREFIX),
        ("couch dev", "developpe couche barre", search.TOKENS),
        ("dcb", "developpe couche barre", search.INITIALS),
        ("srb", "squat au rack barre", search.INITIALS),
        ("ouch", "developpe couche barre", search.SUBSTRING),
        ("devlope", "developpe couche barre", search.FUZZY),
        ("devlope cuche", "developpe couche barre", search.FUZZY),
        ("swnig", "kettlebell swing", 0),
        ("swign", "kettlebell swing", search.FUZZY),
        ("kettlebel swign", "kettlebell swing", search.FUZZY),
        ("zzz", "developpe couche barre", 0),
        ("d", "squat au rack barre", 0),
        ("x", "", 0),
    ],
)
def test_score_tiers(query: str, text: str, expected: int) -> None:
    assert score(query, text) == expected


def test_tokens_must_match_distinct_tokens() -> None:
    assert score("dev dev", "developpe couche") < search.TOKENS
    assert score("c d", "developpe couche") == search.TOKENS


def test_initials_skip_stop_words_and_need_two_letters() -> None:
    assert score("sr", "squat au rack barre") == search.INITIALS
    assert score("s", "squat au rack barre") == search.PREFIX
    assert score("q", "squat au rack barre") == search.SUBSTRING


@pytest.mark.parametrize(
    "query", ["DC", "dc", "bench", "Bench Press", "developpe", "DÉVELOPPÉ couché", "devlope"]
)
def test_roadmap_queries_find_the_bench_press(query: str) -> None:
    assert rank(query, CANDIDATES)[0] == BENCH.id


def test_best_text_of_a_candidate_counts() -> None:
    # « DC » is an exact alias of the bench press and only a prefix of « DC haltères »
    assert rank("dc", CANDIDATES) == [BENCH.id, DUMBBELL.id]


def test_ties_by_recent_then_name_then_id() -> None:
    twins = [Candidate(9, "B"), Candidate(8, "A"), Candidate(7, "A")]
    assert rank("", twins) == [7, 8, 9]
    assert rank("", twins, recent=[9]) == [9, 7, 8]
    assert rank("devel", CANDIDATES, recent=[DUMBBELL.id]) == [DUMBBELL.id, BENCH.id]


def test_empty_query_lists_everything_by_name_without_limit() -> None:
    many = [Candidate(i, f"Exercice {i:03d}") for i in range(30)]
    assert rank("  ", many) == list(range(30))


def test_limit() -> None:
    many = [Candidate(i, f"Exercice {i:03d}") for i in range(30)]
    assert len(rank("exercice", many)) == search.LIMIT
    assert rank("exercice", many, limit=3) == [0, 1, 2]


def test_no_match() -> None:
    assert rank("tapis", CANDIDATES) == []


@pytest.mark.parametrize(
    ("q", "text", "bound", "expected"),
    [
        ("abc", "abcdef", 1, 0),
        ("abd", "abcdef", 1, 1),
        ("xyz", "abcdef", 1, 2),
        ("devlope", "developpe", 2, 2),
    ],
)
def test_prefix_distance(q: str, text: str, bound: int, expected: int) -> None:
    assert search.prefix_distance(q, text, bound) == expected
