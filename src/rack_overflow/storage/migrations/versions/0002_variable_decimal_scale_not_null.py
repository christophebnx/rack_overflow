"""Require a scale on decimal variables: `ck_variable_decimal_scale` refuses a NULL scale.

In 0001 the check was NULL (so it passed) for a decimal variable without scale.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-03

Frozen once committed: never edit, add a new revision instead (D-046).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAME = "ck_variable_decimal_scale"
STRICT = (
    "(type = 'decimal' AND decimal_scale IS NOT NULL AND decimal_scale BETWEEN 1 AND 6) OR "
    "(type != 'decimal' AND decimal_scale IS NULL)"
)
LOOSE = (
    "(type = 'decimal' AND decimal_scale BETWEEN 1 AND 6) OR (type != 'decimal' AND decimal_scale IS NULL)"
)


def _replace_check(condition: str) -> None:
    with op.batch_alter_table("variable", schema=None) as batch_op:
        batch_op.drop_constraint(op.f(NAME), type_="check")
        batch_op.create_check_constraint(op.f(NAME), condition)


def upgrade() -> None:
    _replace_check(STRICT)


def downgrade() -> None:
    _replace_check(LOOSE)
