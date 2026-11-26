"""Back up SQLite, verify the backup, rehearse migration, optionally apply.

No app imports: importing the app can initialize storage/settings. PostgreSQL deployments
should use the offline SQL and their managed backup/transaction process.
"""
import argparse
import hashlib
import sqlite3
import uuid
from pathlib import Path
from sqlalchemy import create_engine
from alembic.config import Config
from alembic import command


def upgrade(path, expected=None, expected_columns=None):
    engine = create_engine("sqlite:///" + path.as_posix())
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    try:
        with engine.begin() as connection:
            # pysqlite otherwise autocommits DDL. Hold one explicit write lock so
            # a failed migration rolls back and no application write can race us.
            connection.exec_driver_sql("BEGIN EXCLUSIVE")
            if expected_columns is not None and column_inventory(connection.connection.driver_connection) != expected_columns:
                raise RuntimeError("Database schema changed since backup. Migration refused.")
            if expected is not None and fingerprint(connection.connection.driver_connection, expected_columns) != expected:
                raise RuntimeError("Database changed since backup. Migration refused without writing schema.")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            if expected is not None:
                after = fingerprint(connection.connection.driver_connection, expected_columns)
                if any(after.get(k) != v for k, v in expected.items() if k != "alembic_version"):
                    raise RuntimeError("Existing records changed. Migration transaction rolled back.")
    finally:
        engine.dispose()


def column_inventory(connection):
    names = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {name: [r[1] for r in connection.execute('PRAGMA table_info("'+name.replace('"','""')+'")')] for name in names}


def fingerprint(connection, columns=None):
    names = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    result = {}
    for name in names:
        if columns is not None and name not in columns:
            continue
        escaped = name.replace('"', '""')
        selection = ','.join('"'+c.replace('"','""')+'"' for c in columns[name]) if columns is not None else '*'
        rows = sorted(repr(r) for r in connection.execute(f'SELECT {selection} FROM "{escaped}"'))
        result[name] = hashlib.sha256("\n".join(rows).encode()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--backup-dir", type=Path, default=Path("migration_backups"))
    parser.add_argument("--apply", action="store_true", help="Apply only after backup and rehearsal succeed")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    database = args.database.resolve()
    backup_dir = args.backup_dir.resolve()
    if not database.is_relative_to(root) or not backup_dir.is_relative_to(root):
        parser.error("Database and backup directory must be inside this project.")
    if not database.is_file():
        parser.error("Existing database file required; no database will be created or seeded.")
    backup_dir.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex
    backup = backup_dir / f"learnsphere-{suffix}.backup.db"
    rehearsal = backup_dir / f"learnsphere-{suffix}.rehearsal.db"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as source:
        before = fingerprint(source)
        original_columns = column_inventory(source)
        for destination in (backup, rehearsal):
            with sqlite3.connect(destination) as target:
                source.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or fingerprint(target) != before:
                    raise RuntimeError("Backup verification failed. Original database was not changed.")
    upgrade(rehearsal)
    with sqlite3.connect(rehearsal) as check:
        after = fingerprint(check, original_columns)
        if any(after.get(k) != v for k, v in before.items() if k != "alembic_version"):
            raise RuntimeError("Rehearsal changed existing data. Original database was not changed.")
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Rehearsal integrity check failed.")
    print(f"Verified backup: {backup}\nValidated migration: {rehearsal}")
    if args.apply:
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as source:
            if fingerprint(source) != before:
                raise RuntimeError("Database changed during rehearsal. Stop application writes and retry.")
        upgrade(database, expected=before, expected_columns=original_columns)
        print("Additive migration applied. Existing records preserved.")
    else:
        print("Validation only. Original database was not modified. Use --apply after stopping the application.")


if __name__ == "__main__":
    main()
