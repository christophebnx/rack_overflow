"""Text normalisation (D-056): one folding for search, aliases, uniqueness and codes."""

from __future__ import annotations

import pytest

from rack_overflow.domain.text import normalise, slug


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Développé couché (barre)", "developpe couche barre"),
        ("  DÉVELOPPÉ--Couché  ", "developpe couche"),
        ("Œuf", "oeuf"),
        ("ex æquo", "ex aequo"),
        ("Relevé d\u2019épaule", "releve d epaule"),
        ("l'haltère", "l haltere"),
        ("Straße", "strasse"),
        ("snake_case", "snake case"),
        ("½ squat", "1 2 squat"),
        ("", ""),
        ("!!! ???", ""),
    ],
)
def test_normalise(raw: str, expected: str) -> None:
    assert normalise(raw) == expected


def test_normalise_is_idempotent() -> None:
    once = normalise("Hip thrust à la Smith")
    assert normalise(once) == once


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Siège", "siege"), ("Hauteur du siège", "hauteur_du_siege"), ("10", "10"), ("—", "")],
)
def test_slug(raw: str, expected: str) -> None:
    assert slug(raw) == expected
