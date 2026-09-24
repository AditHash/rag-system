"""Small PostgreSQL connection and schema migration helpers."""

import os
from pathlib import Path

import psycopg

_MIGRATIONS = Path(__file__).parent / "migrations"


def connect_database(database_url: str | None = None) -> psycopg.Connection:
    """Open PostgreSQL using the given URL or the DATABASE_URL environment variable."""
    database_url = database_url or os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is required")
    return psycopg.connect(database_url)


def apply_schema(connection: psycopg.Connection) -> None:
    """Create the initial tables and indexes in one transaction."""
    migration = (_MIGRATIONS / "initial_schema.sql").read_text(encoding="utf-8")
    with connection.transaction():
        connection.execute(migration, prepare=False)


def rollback_schema(connection: psycopg.Connection) -> None:
    """Drop the tables and indexes created by the initial migration."""
    migration = (_MIGRATIONS / "rollback.sql").read_text(encoding="utf-8")
    with connection.transaction():
        connection.execute(migration, prepare=False)
