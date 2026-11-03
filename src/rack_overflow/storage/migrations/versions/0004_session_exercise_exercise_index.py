"""Index session rows by exercise (D-066).

- index `ix_session_exercise_exercise_id` on `session_exercise (exercise_id)`: every per-exercise
  read of session logging (last performance, last settings, record history, recent exercises)
  starts from an exercise id.

Additive: one non-unique index, no table rebuild.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-03

Frozen once committed: never edit, add a new revision instead (D-046).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXERCISE_INDEX = "ix_session_exercise_exercise_id"


def upgrade() -> None:
    op.create_index(EXERCISE_INDEX, "session_exercise", ["exercise_id"], unique=False)


def downgrade() -> None:
    op.drop_index(EXERCISE_INDEX, table_name="session_exercise")
