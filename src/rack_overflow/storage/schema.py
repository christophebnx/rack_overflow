"""The database schema (brief section 7.2) as SQLAlchemy Core tables (D-016, D-046).

Conventions: integer ids from the database, `user_id` on root tables (no FK until V2), UTC ISO 8601
text timestamps, nullable `archived_at` / `deleted_at` / `revoked_at`, `position` for order, JSON
only for definition lists, enumerated values from `domain.vocabulary` as `CHECK`, no `ON DELETE`.
Migrations never import this module: `storage/migrations/versions/` holds frozen snapshots.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from rack_overflow.domain import vocabulary

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
}

metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


def _one_of(column: str, values: Sequence[str]) -> sa.CheckConstraint:
    listed = ", ".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({listed})", name=column)


def _exactly_one(first: str, second: str, name: str) -> sa.CheckConstraint:
    rule = f"({first} IS NOT NULL AND {second} IS NULL) OR ({first} IS NULL AND {second} IS NOT NULL)"
    return sa.CheckConstraint(rule, name=name)


def _id() -> sa.Column[int]:
    return sa.Column("id", sa.Integer, primary_key=True)


def _user_id() -> sa.Column[int]:
    return sa.Column("user_id", sa.Integer, nullable=False, index=True)


def _fk(name: str, target: str, *, nullable: bool = False) -> sa.Column[int]:
    return sa.Column(name, sa.Integer, sa.ForeignKey(f"{target}.id"), nullable=nullable)


def _text(name: str, *, nullable: bool = False) -> sa.Column[str]:
    return sa.Column(name, sa.Text, nullable=nullable)


def _int(name: str, *, nullable: bool = True) -> sa.Column[int]:
    return sa.Column(name, sa.Integer, nullable=nullable)


def _position() -> sa.Column[int]:
    return sa.Column("position", sa.Integer, nullable=False)


def _values() -> list[sa.SchemaItem]:
    """`value_int` / `value_text`, exactly one set (setting and measure value tables)."""
    return [
        _int("value_int"),
        _text("value_text", nullable=True),
        _exactly_one("value_int", "value_text", "one_value"),
    ]


variable = sa.Table(
    "variable",
    metadata,
    _id(),
    _user_id(),
    _text("code"),
    _text("label"),
    _text("type"),
    _text("unit", nullable=True),
    _text("scope"),
    sa.Column("enum_values", sa.JSON, nullable=True),
    _int("decimal_scale"),
    _text("archived_at", nullable=True),
    sa.UniqueConstraint("user_id", "code"),
    _one_of("type", vocabulary.VARIABLE_TYPES),
    _one_of("scope", vocabulary.VARIABLE_SCOPES),
    sa.CheckConstraint(
        "(type = 'enum' AND enum_values IS NOT NULL) OR (type != 'enum' AND enum_values IS NULL)",
        name="enum_values",
    ),
    sa.CheckConstraint(
        "(type = 'decimal' AND decimal_scale IS NOT NULL AND decimal_scale BETWEEN 1 AND 6) OR "
        "(type != 'decimal' AND decimal_scale IS NULL)",
        name="decimal_scale",
    ),
)

exercise = sa.Table(
    "exercise",
    metadata,
    _id(),
    _user_id(),
    _text("name"),
    _text("category"),
    _text("movement_pattern", nullable=True),
    _text("equipment", nullable=True),
    _text("location"),
    _text("archived_at", nullable=True),
    sa.UniqueConstraint("user_id", "name"),
    _one_of("category", vocabulary.EXERCISE_CATEGORIES),
    _one_of("location", vocabulary.LOCATIONS),
)

exercise_field = sa.Table(
    "exercise_field",
    metadata,
    _id(),
    _fk("exercise_id", "exercise"),
    _text("core_quantity", nullable=True),
    _fk("variable_id", "variable", nullable=True),
    sa.Column(
        "required",
        sa.Boolean(create_constraint=True, name="required"),
        nullable=False,
        server_default=sa.false(),
    ),
    _int("increment"),
    _int("default_int"),
    _text("default_text", nullable=True),
    sa.Column("discrete_values", sa.JSON, nullable=True),
    _position(),
    _exactly_one("core_quantity", "variable_id", "one_source"),
    _one_of("core_quantity", vocabulary.CORE_QUANTITIES),
    sa.CheckConstraint("increment > 0", name="increment"),
    sa.CheckConstraint("default_int IS NULL OR default_text IS NULL", name="one_default"),
    sa.UniqueConstraint("exercise_id", "core_quantity"),
    sa.UniqueConstraint("exercise_id", "variable_id"),
)

exercise_alias = sa.Table(
    "exercise_alias",
    metadata,
    _id(),
    _fk("exercise_id", "exercise"),
    _text("alias"),
    _text("alias_normalised", nullable=False),
    sa.UniqueConstraint("exercise_id", "alias_normalised"),
    sa.Index(None, "alias_normalised"),
)

template = sa.Table(
    "template",
    metadata,
    _id(),
    _user_id(),
    _text("name"),
    _text("location"),
    _position(),
    _text("archived_at", nullable=True),
    _one_of("location", vocabulary.LOCATIONS),
)

template_slot = sa.Table(
    "template_slot",
    metadata,
    _id(),
    _fk("template_id", "template"),
    _position(),
    _fk("exercise_id", "exercise", nullable=True),
    _text("movement_pattern", nullable=True),
    _int("target_sets"),
    _int("target_reps_min"),
    _int("target_reps_max"),
    _int("target_duration_s"),
    _int("target_distance_m"),
    _text("target_note", nullable=True),
    _exactly_one("exercise_id", "movement_pattern", "one_source"),
    sa.CheckConstraint("target_sets > 0", name="target_sets"),
    sa.CheckConstraint("target_reps_min >= 0", name="target_reps_min"),
    sa.CheckConstraint("target_reps_max >= 0", name="target_reps_max"),
    sa.CheckConstraint("target_duration_s > 0", name="target_duration_s"),
    sa.CheckConstraint("target_distance_m > 0", name="target_distance_m"),
    sa.CheckConstraint("target_reps_min <= target_reps_max", name="target_reps_order"),
)

template_slot_option = sa.Table(
    "template_slot_option",
    metadata,
    _id(),
    _fk("template_slot_id", "template_slot"),
    _fk("exercise_id", "exercise"),
    _position(),
    sa.UniqueConstraint("template_slot_id", "exercise_id"),
)

session = sa.Table(
    "session",
    metadata,
    _id(),
    _user_id(),
    _text("local_date"),
    _text("time_zone"),
    _text("started_at"),
    _text("ended_at", nullable=True),
    _text("location"),
    _fk("template_id", "template", nullable=True),
    _text("notes", nullable=True),
    _text("status"),
    _text("deleted_at", nullable=True),
    _one_of("location", vocabulary.SESSION_LOCATIONS),
    _one_of("status", vocabulary.SESSION_STATUSES),
    sa.CheckConstraint(
        "(status = 'open' AND ended_at IS NULL) OR (status = 'closed' AND ended_at IS NOT NULL)",
        name="status_ended_at",
    ),
    sa.Index(
        "uq_session_one_open",
        "user_id",
        unique=True,
        sqlite_where=sa.text("status = 'open' AND deleted_at IS NULL"),
        postgresql_where=sa.text("status = 'open' AND deleted_at IS NULL"),
    ),
)

session_exercise = sa.Table(
    "session_exercise",
    metadata,
    _id(),
    _fk("session_id", "session"),
    _fk("exercise_id", "exercise"),
    _fk("template_slot_id", "template_slot", nullable=True),
    _position(),
    _text("notes", nullable=True),
    sa.Index(None, "session_id"),
)

exercise_setting = sa.Table(
    "exercise_setting",
    metadata,
    _id(),
    _fk("session_exercise_id", "session_exercise"),
    _fk("variable_id", "variable"),
    *_values(),
    sa.UniqueConstraint("session_exercise_id", "variable_id"),
)

set_entry = sa.Table(
    "set_entry",
    metadata,
    _id(),
    _fk("session_exercise_id", "session_exercise"),
    _position(),
    sa.Column("type", sa.Text, nullable=False, server_default="work"),
    _int("reps"),
    _int("weight_g"),
    _int("duration_s"),
    _int("distance_m"),
    _text("completed_at", nullable=True),
    _text("deleted_at", nullable=True),
    _one_of("type", vocabulary.SET_TYPES),
    *(
        sa.CheckConstraint(f"{name} >= 0", name=name)
        for name in ("reps", "weight_g", "duration_s", "distance_m")
    ),
    sa.Index(None, "session_exercise_id"),
)

set_value = sa.Table(
    "set_value",
    metadata,
    _id(),
    _fk("set_entry_id", "set_entry"),
    _fk("variable_id", "variable"),
    *_values(),
    sa.UniqueConstraint("set_entry_id", "variable_id"),
)

rm_measured = sa.Table(
    "rm_measured",
    metadata,
    _id(),
    _user_id(),
    _fk("exercise_id", "exercise"),
    _int("n", nullable=False),
    _int("weight_g", nullable=False),
    _text("measured_on"),
    _text("created_at"),
    _text("deleted_at", nullable=True),
    sa.CheckConstraint("n >= 1", name="n"),
    sa.CheckConstraint("weight_g > 0", name="weight_g"),
)

device = sa.Table(
    "device",
    metadata,
    _id(),
    _user_id(),
    _text("name"),
    _text("token_hash", nullable=True),
    _text("created_at"),
    _text("last_seen_at", nullable=True),
    _text("revoked_at", nullable=True),
    sa.UniqueConstraint("token_hash"),
    sa.Index(
        "uq_device_active_name",
        "user_id",
        "name",
        unique=True,
        sqlite_where=sa.text("revoked_at IS NULL"),
        postgresql_where=sa.text("revoked_at IS NULL"),
    ),
)

pairing_code = sa.Table(
    "pairing_code",
    metadata,
    _id(),
    _fk("device_id", "device"),
    _text("code_hash"),
    _text("expires_at"),
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    _text("used_at", nullable=True),
    sa.CheckConstraint("attempts >= 0", name="attempts"),
)

app_setting = sa.Table(
    "app_setting",
    metadata,
    _id(),
    _user_id(),
    _text("key"),
    _text("value"),
    sa.UniqueConstraint("user_id", "key"),
)
