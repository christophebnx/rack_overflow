"""Soft-deleted template slots, seed keys on exercises, unique template names (D-058, D-060).

- `template_slot.deleted_at`: removing a slot sets it, so history keeps its slot reference.
- `exercise.seed_key` + unique index `(user_id, seed_key)`: stable identity of seeded exercises.
- unique index `template (user_id, name)`: backstop of the template name rule.

Additive: nullable columns and unique indexes on tables holding no template data before L3.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-03

Frozen once committed: never edit, add a new revision instead (D-046).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_KEY_INDEX = "uq_exercise_user_id_seed_key"
TEMPLATE_NAME_INDEX = "uq_template_user_id_name"


def upgrade() -> None:
    with op.batch_alter_table("template_slot", schema=None) as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.Text(), nullable=True))
    with op.batch_alter_table("exercise", schema=None) as batch_op:
        batch_op.add_column(sa.Column("seed_key", sa.Text(), nullable=True))
    op.create_index(SEED_KEY_INDEX, "exercise", ["user_id", "seed_key"], unique=True)
    op.create_index(TEMPLATE_NAME_INDEX, "template", ["user_id", "name"], unique=True)


def downgrade() -> None:
    op.drop_index(TEMPLATE_NAME_INDEX, table_name="template")
    op.drop_index(SEED_KEY_INDEX, table_name="exercise")
    with op.batch_alter_table("exercise", schema=None) as batch_op:
        batch_op.drop_column("seed_key")
    with op.batch_alter_table("template_slot", schema=None) as batch_op:
        batch_op.drop_column("deleted_at")
