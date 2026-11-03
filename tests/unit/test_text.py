"""Text normalisation (D-056): one folding for search, aliases, uniqueness and codes."""

from __future__ import annotations

import pytest

from rack_overflow.domain.text import is_digits, normalise, slug


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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("   ", ""),
        ("---", ""),
        ("\u00a0Siège\u00a0", "siege"),
        ("e\u0301", "e"),  # combining accent, NFD input
        ("\uff24\uff23", "dc"),  # full-width letters
        ("Tirage   horizontal", "tirage horizontal"),
        ("1/2 squat", "1 2 squat"),
    ],
)
def test_normalise_edges(raw: str, expected: str) -> None:
    assert normalise(raw) == expected


def test_slug_of_symbols_is_empty_and_nfc_nfd_agree() -> None:
    assert slug("!!!") == ""
    assert slug("Siège") == slug("Sie\u0300ge") == "siege"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", True),
        ("012", True),
        ("", False),
        ("²", False),
        ("١٢", False),
        ("1 ", False),
        ("-1", False),
        ("1,0", False),
    ],
)
def test_is_digits_reads_ascii_digits_only(raw: str, expected: bool) -> None:
    assert is_digits(raw) is expected
