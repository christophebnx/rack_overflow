"""Alembic environment: online mode only, on the connection passed by `storage.migrate`."""

from alembic import context

from rack_overflow.storage import schema

connection = context.config.attributes["connection"]
context.configure(
    connection=connection,
    target_metadata=schema.metadata,
    render_as_batch=True,
    compare_type=True,
)
context.run_migrations()
