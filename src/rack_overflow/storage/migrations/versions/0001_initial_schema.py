"""Initial schema: every table of brief section 7.2 (frozen snapshot, literal value lists).

Revision ID: 0001
Revises: none
Create Date: 2026-11-03

Frozen once committed: never edit, add a new revision instead (D-046).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_setting",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_setting")),
        sa.UniqueConstraint("user_id", "key", name=op.f("uq_app_setting_user_id_key")),
    )
    with op.batch_alter_table("app_setting", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_app_setting_user_id"), ["user_id"], unique=False)

    op.create_table(
        "device",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("last_seen_at", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_device_token_hash")),
    )
    with op.batch_alter_table("device", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_device_user_id"), ["user_id"], unique=False)
        batch_op.create_index(
            "uq_device_active_name",
            ["user_id", "name"],
            unique=True,
            sqlite_where=sa.text("revoked_at IS NULL"),
            postgresql_where=sa.text("revoked_at IS NULL"),
        )

    op.create_table(
        "exercise",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("movement_pattern", sa.Text(), nullable=True),
        sa.Column("equipment", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("archived_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "category IN ('strength', 'kettlebell', 'bodyweight', 'cardio', 'intervals')",
            name=op.f("ck_exercise_category"),
        ),
        sa.CheckConstraint("location IN ('gym', 'home', 'both')", name=op.f("ck_exercise_location")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exercise")),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_exercise_user_id_name")),
    )
    with op.batch_alter_table("exercise", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_exercise_user_id"), ["user_id"], unique=False)

    op.create_table(
        "template",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.Text(), nullable=True),
        sa.CheckConstraint("location IN ('gym', 'home', 'both')", name=op.f("ck_template_location")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_template")),
    )
    with op.batch_alter_table("template", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_template_user_id"), ["user_id"], unique=False)

    op.create_table(
        "variable",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("enum_values", sa.JSON(), nullable=True),
        sa.Column("decimal_scale", sa.Integer(), nullable=True),
        sa.Column("archived_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(type = 'decimal' AND decimal_scale BETWEEN 1 AND 6) OR "
            "(type != 'decimal' AND decimal_scale IS NULL)",
            name=op.f("ck_variable_decimal_scale"),
        ),
        sa.CheckConstraint(
            "(type = 'enum' AND enum_values IS NOT NULL) OR (type != 'enum' AND enum_values IS NULL)",
            name=op.f("ck_variable_enum_values"),
        ),
        sa.CheckConstraint("scope IN ('set', 'setting')", name=op.f("ck_variable_scope")),
        sa.CheckConstraint(
            "type IN ('int', 'decimal', 'duration', 'distance', 'weight', 'enum', 'bool', 'text')",
            name=op.f("ck_variable_type"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_variable")),
        sa.UniqueConstraint("user_id", "code", name=op.f("uq_variable_user_id_code")),
    )
    with op.batch_alter_table("variable", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_variable_user_id"), ["user_id"], unique=False)

    op.create_table(
        "exercise_alias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("alias_normalised", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["exercise.id"], name=op.f("fk_exercise_alias_exercise_id_exercise")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exercise_alias")),
        sa.UniqueConstraint(
            "exercise_id", "alias_normalised", name=op.f("uq_exercise_alias_exercise_id_alias_normalised")
        ),
    )
    with op.batch_alter_table("exercise_alias", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_exercise_alias_alias_normalised"), ["alias_normalised"], unique=False
        )

    op.create_table(
        "exercise_field",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("core_quantity", sa.Text(), nullable=True),
        sa.Column("variable_id", sa.Integer(), nullable=True),
        sa.Column(
            "required",
            sa.Boolean(create_constraint=True, name=op.f("ck_exercise_field_required")),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("increment", sa.Integer(), nullable=True),
        sa.Column("default_int", sa.Integer(), nullable=True),
        sa.Column("default_text", sa.Text(), nullable=True),
        sa.Column("discrete_values", sa.JSON(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "core_quantity IN ('reps', 'weight', 'duration', 'distance')",
            name=op.f("ck_exercise_field_core_quantity"),
        ),
        sa.CheckConstraint(
            "(core_quantity IS NOT NULL AND variable_id IS NULL) OR "
            "(core_quantity IS NULL AND variable_id IS NOT NULL)",
            name=op.f("ck_exercise_field_one_source"),
        ),
        sa.CheckConstraint(
            "default_int IS NULL OR default_text IS NULL", name=op.f("ck_exercise_field_one_default")
        ),
        sa.CheckConstraint("increment > 0", name=op.f("ck_exercise_field_increment")),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["exercise.id"], name=op.f("fk_exercise_field_exercise_id_exercise")
        ),
        sa.ForeignKeyConstraint(
            ["variable_id"], ["variable.id"], name=op.f("fk_exercise_field_variable_id_variable")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exercise_field")),
        sa.UniqueConstraint(
            "exercise_id", "core_quantity", name=op.f("uq_exercise_field_exercise_id_core_quantity")
        ),
        sa.UniqueConstraint(
            "exercise_id", "variable_id", name=op.f("uq_exercise_field_exercise_id_variable_id")
        ),
    )
    op.create_table(
        "pairing_code",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("used_at", sa.Text(), nullable=True),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_pairing_code_attempts")),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"], name=op.f("fk_pairing_code_device_id_device")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pairing_code")),
    )
    op.create_table(
        "rm_measured",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("weight_g", sa.Integer(), nullable=False),
        sa.Column("measured_on", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.CheckConstraint("n >= 1", name=op.f("ck_rm_measured_n")),
        sa.CheckConstraint("weight_g > 0", name=op.f("ck_rm_measured_weight_g")),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["exercise.id"], name=op.f("fk_rm_measured_exercise_id_exercise")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rm_measured")),
    )
    with op.batch_alter_table("rm_measured", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_rm_measured_user_id"), ["user_id"], unique=False)

    op.create_table(
        "session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("local_date", sa.Text(), nullable=False),
        sa.Column("time_zone", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("ended_at", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(status = 'open' AND ended_at IS NULL) OR (status = 'closed' AND ended_at IS NOT NULL)",
            name=op.f("ck_session_status_ended_at"),
        ),
        sa.CheckConstraint("location IN ('gym', 'home')", name=op.f("ck_session_location")),
        sa.CheckConstraint("status IN ('open', 'closed')", name=op.f("ck_session_status")),
        sa.ForeignKeyConstraint(
            ["template_id"], ["template.id"], name=op.f("fk_session_template_id_template")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session")),
    )
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_session_user_id"), ["user_id"], unique=False)
        batch_op.create_index(
            "uq_session_one_open",
            ["user_id"],
            unique=True,
            sqlite_where=sa.text("status = 'open' AND deleted_at IS NULL"),
            postgresql_where=sa.text("status = 'open' AND deleted_at IS NULL"),
        )

    op.create_table(
        "template_slot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=True),
        sa.Column("movement_pattern", sa.Text(), nullable=True),
        sa.Column("target_sets", sa.Integer(), nullable=True),
        sa.Column("target_reps_min", sa.Integer(), nullable=True),
        sa.Column("target_reps_max", sa.Integer(), nullable=True),
        sa.Column("target_duration_s", sa.Integer(), nullable=True),
        sa.Column("target_distance_m", sa.Integer(), nullable=True),
        sa.Column("target_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(exercise_id IS NOT NULL AND movement_pattern IS NULL) OR "
            "(exercise_id IS NULL AND movement_pattern IS NOT NULL)",
            name=op.f("ck_template_slot_one_source"),
        ),
        sa.CheckConstraint("target_distance_m > 0", name=op.f("ck_template_slot_target_distance_m")),
        sa.CheckConstraint("target_duration_s > 0", name=op.f("ck_template_slot_target_duration_s")),
        sa.CheckConstraint("target_reps_max >= 0", name=op.f("ck_template_slot_target_reps_max")),
        sa.CheckConstraint(
            "target_reps_min <= target_reps_max", name=op.f("ck_template_slot_target_reps_order")
        ),
        sa.CheckConstraint("target_reps_min >= 0", name=op.f("ck_template_slot_target_reps_min")),
        sa.CheckConstraint("target_sets > 0", name=op.f("ck_template_slot_target_sets")),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["exercise.id"], name=op.f("fk_template_slot_exercise_id_exercise")
        ),
        sa.ForeignKeyConstraint(
            ["template_id"], ["template.id"], name=op.f("fk_template_slot_template_id_template")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_template_slot")),
    )
    op.create_table(
        "session_exercise",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("template_slot_id", sa.Integer(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["exercise.id"], name=op.f("fk_session_exercise_exercise_id_exercise")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["session.id"], name=op.f("fk_session_exercise_session_id_session")
        ),
        sa.ForeignKeyConstraint(
            ["template_slot_id"],
            ["template_slot.id"],
            name=op.f("fk_session_exercise_template_slot_id_template_slot"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_exercise")),
    )
    with op.batch_alter_table("session_exercise", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_session_exercise_session_id"), ["session_id"], unique=False)

    op.create_table(
        "template_slot_option",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_slot_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["exercise.id"], name=op.f("fk_template_slot_option_exercise_id_exercise")
        ),
        sa.ForeignKeyConstraint(
            ["template_slot_id"],
            ["template_slot.id"],
            name=op.f("fk_template_slot_option_template_slot_id_template_slot"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_template_slot_option")),
        sa.UniqueConstraint(
            "template_slot_id",
            "exercise_id",
            name=op.f("uq_template_slot_option_template_slot_id_exercise_id"),
        ),
    )
    op.create_table(
        "exercise_setting",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_exercise_id", sa.Integer(), nullable=False),
        sa.Column("variable_id", sa.Integer(), nullable=False),
        sa.Column("value_int", sa.Integer(), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(value_int IS NOT NULL AND value_text IS NULL) OR "
            "(value_int IS NULL AND value_text IS NOT NULL)",
            name=op.f("ck_exercise_setting_one_value"),
        ),
        sa.ForeignKeyConstraint(
            ["session_exercise_id"],
            ["session_exercise.id"],
            name=op.f("fk_exercise_setting_session_exercise_id_session_exercise"),
        ),
        sa.ForeignKeyConstraint(
            ["variable_id"], ["variable.id"], name=op.f("fk_exercise_setting_variable_id_variable")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exercise_setting")),
        sa.UniqueConstraint(
            "session_exercise_id",
            "variable_id",
            name=op.f("uq_exercise_setting_session_exercise_id_variable_id"),
        ),
    )
    op.create_table(
        "set_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_exercise_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), server_default="work", nullable=False),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("weight_g", sa.Integer(), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column("distance_m", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.CheckConstraint("type IN ('warmup', 'work', 'rm_test')", name=op.f("ck_set_entry_type")),
        sa.CheckConstraint("distance_m >= 0", name=op.f("ck_set_entry_distance_m")),
        sa.CheckConstraint("duration_s >= 0", name=op.f("ck_set_entry_duration_s")),
        sa.CheckConstraint("reps >= 0", name=op.f("ck_set_entry_reps")),
        sa.CheckConstraint("weight_g >= 0", name=op.f("ck_set_entry_weight_g")),
        sa.ForeignKeyConstraint(
            ["session_exercise_id"],
            ["session_exercise.id"],
            name=op.f("fk_set_entry_session_exercise_id_session_exercise"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_set_entry")),
    )
    with op.batch_alter_table("set_entry", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_set_entry_session_exercise_id"), ["session_exercise_id"], unique=False
        )

    op.create_table(
        "set_value",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("set_entry_id", sa.Integer(), nullable=False),
        sa.Column("variable_id", sa.Integer(), nullable=False),
        sa.Column("value_int", sa.Integer(), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(value_int IS NOT NULL AND value_text IS NULL) OR "
            "(value_int IS NULL AND value_text IS NOT NULL)",
            name=op.f("ck_set_value_one_value"),
        ),
        sa.ForeignKeyConstraint(
            ["set_entry_id"], ["set_entry.id"], name=op.f("fk_set_value_set_entry_id_set_entry")
        ),
        sa.ForeignKeyConstraint(
            ["variable_id"], ["variable.id"], name=op.f("fk_set_value_variable_id_variable")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_set_value")),
        sa.UniqueConstraint(
            "set_entry_id", "variable_id", name=op.f("uq_set_value_set_entry_id_variable_id")
        ),
    )


def downgrade() -> None:
    op.drop_table("set_value")
    with op.batch_alter_table("set_entry", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_set_entry_session_exercise_id"))

    op.drop_table("set_entry")
    op.drop_table("exercise_setting")
    op.drop_table("template_slot_option")
    with op.batch_alter_table("session_exercise", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_session_exercise_session_id"))

    op.drop_table("session_exercise")
    op.drop_table("template_slot")
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_session_one_open",
            sqlite_where=sa.text("status = 'open' AND deleted_at IS NULL"),
            postgresql_where=sa.text("status = 'open' AND deleted_at IS NULL"),
        )
        batch_op.drop_index(batch_op.f("ix_session_user_id"))

    op.drop_table("session")
    with op.batch_alter_table("rm_measured", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_rm_measured_user_id"))

    op.drop_table("rm_measured")
    op.drop_table("pairing_code")
    op.drop_table("exercise_field")
    with op.batch_alter_table("exercise_alias", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_exercise_alias_alias_normalised"))

    op.drop_table("exercise_alias")
    with op.batch_alter_table("variable", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_variable_user_id"))

    op.drop_table("variable")
    with op.batch_alter_table("template", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_template_user_id"))

    op.drop_table("template")
    with op.batch_alter_table("exercise", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_exercise_user_id"))

    op.drop_table("exercise")
    with op.batch_alter_table("device", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_device_active_name",
            sqlite_where=sa.text("revoked_at IS NULL"),
            postgresql_where=sa.text("revoked_at IS NULL"),
        )
        batch_op.drop_index(batch_op.f("ix_device_user_id"))

    op.drop_table("device")
    with op.batch_alter_table("app_setting", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_app_setting_user_id"))

    op.drop_table("app_setting")
