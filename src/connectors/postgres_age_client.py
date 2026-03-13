"""PostgreSQL + Apache AGE client utilities.

This module builds a SQLAlchemy engine using only environment variables.
It intentionally avoids printing secrets in errors or logs.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import find_dotenv, load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine


def _clean_env_value(value: str | None) -> str | None:
    """Normalize values by trimming whitespace and empty strings."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def get_env(*names: str, default: str | None = None) -> str | None:
    """Read the first non-empty value from a list of env var names."""
    for name in names:
        value = _clean_env_value(os.getenv(name))
        if value is not None:
            return value
    return default


def _require_env(*names: str) -> str:
    """Read required env var (supports aliases) and raise error if missing."""
    value = get_env(*names)
    if value is None:
        raise RuntimeError(
            f"Missing required environment variables: {names[0]}"
            f"(aliases checked: {', '.join(names)})"
        )
    return value


def build_db_url() -> URL:
    """Build SQLAlchemy URL from environment variables only."""
    host = _require_env("POSTGRES_HOST", "PGHOST")
    database = _require_env("POSTGRES_DB", "POSTGRES_DATABASE", "PGDATABASE")
    username = _require_env("POSTGRES_USER", "PGUSER")
    password = _require_env("POSTGRES_PASSWORD", "PGPASSWORD")

    port_str = get_env("POSTGRES_PORT", "PGPORT", default="5432")
    try:
        port = int(port_str) if port_str is not None else 5432
    except ValueError as exc:
        raise ValueError("POSTGRES_PORT/PGPORT must be a valid integer") from exc

    sslmode = get_env("POSTGRES_SSLMODE", default=None)
    query: dict[str, str] = {}
    if sslmode:
        query["sslmode"] = sslmode

    return URL.create(
        drivername="postgresql+psycopg2",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        query=query,
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return a cached SQLAlchemy engine configured from env vars.

    Expected env vars:
      - POSTGRES_HOST
      - POSTGRES_PORT (default: 5432)
      - POSTGRES_DB (or POSTGRES_DBNAME / POSTGRES_DATABASE)
      - POSTGRES_USER
      - POSTGRES_PASSWORD
      - POSTGRES_SSLMODE (optional)
    """
    # Load .env if present; still uses env vars as the only config source.
    load_dotenv(find_dotenv(), override=False)

    db_url = build_db_url()
    try:
        return create_engine(
            db_url,
            pool_pre_ping=True,
            pool_recycle=1800,
            future=True,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to create PostgreSQL engine from environment configuration. "
            f"Driver/url setup error: {exc.__class__.__name__}: {exc}"
        ) from exc


def init_age_session(connection) -> None:
    """Initialize AGE for the current DB session/connection."""
    connection.execute(text("LOAD 'age'"))
    connection.execute(text('SET search_path = ag_catalog, "$user", public'))
