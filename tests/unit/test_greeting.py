import pytest

from rack_overflow.domain.errors import DomainError
from rack_overflow.domain.greeting import NAME_LIMIT, GreetingError, greeting


def test_greeting_strips_the_name() -> None:
    assert greeting("  Ada ") == "Hello, Ada!"


@pytest.mark.parametrize("name", ["", "   ", "x" * (NAME_LIMIT + 1)])
def test_greeting_refuses_empty_or_long_names(name: str) -> None:
    with pytest.raises(GreetingError):
        greeting(name)


def test_greeting_error_is_a_domain_error() -> None:
    assert issubclass(GreetingError, DomainError)
