"""SQLite engine and session management (sync SQLAlchemy 2.0)."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    return engine


settings = get_settings()
settings.resolved_data_dir.mkdir(parents=True, exist_ok=True)
engine = _make_engine(f"sqlite:///{settings.db_path.as_posix()}")
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Additive migrations for columns introduced after a database was first created.
# (SQLAlchemy's create_all never alters existing tables.)
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "edits": {"place_name": "VARCHAR(160)"},
}


def run_migrations() -> None:
    with engine.begin() as conn:
        for table, cols in _ADDED_COLUMNS.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if not existing:
                continue  # table does not exist yet; create_all will build it with all columns
            for name, ddl in cols.items():
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
