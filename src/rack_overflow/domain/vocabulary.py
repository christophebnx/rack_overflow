"""Allowed values of the enumerated columns (stable English keys, never labels; D-032, D-046).

The schema turns each tuple into a `CHECK (col IN (...))`. Adding a value needs a migration.
"""

from __future__ import annotations

VARIABLE_TYPES: tuple[str, ...] = ("int", "decimal", "duration", "distance", "weight", "enum", "bool", "text")
"""Value type of a variable (brief section 6, L2); decimal is an integer with a scale, enum a stored key."""

VARIABLE_SCOPES: tuple[str, ...] = ("set", "setting")
"""A measure changes on every set; a setting is fixed for the exercise within a session (D-019)."""

CORE_QUANTITIES: tuple[str, ...] = ("reps", "weight", "duration", "distance")
"""The four quantities stored as `set_entry` columns (D-018)."""

EXERCISE_CATEGORIES: tuple[str, ...] = ("strength", "kettlebell", "bodyweight", "cardio", "intervals")
"""Kind of training of an exercise."""

LOCATIONS: tuple[str, ...] = ("gym", "home", "both")
"""Where an exercise or a template can be done."""

SESSION_LOCATIONS: tuple[str, ...] = ("gym", "home")
"""Where a session took place."""

SESSION_STATUSES: tuple[str, ...] = ("open", "closed")
"""Life cycle of a session; at most one open session per user."""

SET_TYPES: tuple[str, ...] = ("warmup", "work", "rm_test")
"""Type of a set; warm-ups never count for records or volume, work and RM-test sets do (D-064)."""
