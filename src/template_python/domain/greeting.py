"""Example domain module: shows the shape of a pure function with its own error. Replace it."""

from template_python.domain.errors import DomainError

NAME_LIMIT = 64


class GreetingError(DomainError):
    """The name cannot be greeted."""


def greeting(name: str) -> str:
    """Return the greeting for `name` (stripped, 1 to `NAME_LIMIT` characters)."""
    clean = name.strip()
    if not clean:
        raise GreetingError("name is empty")
    if len(clean) > NAME_LIMIT:
        raise GreetingError(f"name is longer than {NAME_LIMIT} characters")
    return f"Hello, {clean}!"
