"""Base error of the domain layer."""


class DomainError(ValueError):
    """A business rule refused an input. Every domain module's error class derives from it."""
