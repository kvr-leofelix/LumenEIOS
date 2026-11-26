"""Online migration connections must be supplied by the backup/validation runner."""
from alembic import context

config = context.config
if context.is_offline_mode():
    context.configure(url=config.get_main_option("sqlalchemy.url"), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    connection = config.attributes.get("connection")
    if connection is None:
        raise RuntimeError("Use python -B -m backend.scripts.migrate_learnsphere; direct online upgrades are disabled.")
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
