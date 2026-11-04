"""Base error of the domain layer."""


class DomainError(ValueError):
    """A business rule refused an input. Every domain module's error class derives from it."""


class NotFoundError(DomainError):
    """The requested row does not exist for this user (unknown id, or another user's row)."""
