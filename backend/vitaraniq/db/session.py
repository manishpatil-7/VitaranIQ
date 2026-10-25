import os
import sqlite3
from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "vitaraniq.db"


def get_db_path() -> Path:
    env_path = os.getenv("DB_PATH")
    if env_path:
        p = Path(env_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DB_PATH


def get_sqlite_connection(db_path: Path = None) -> sqlite3.Connection:
    """Return raw sqlite3 connection with strict pragmas."""
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def create_db_engine(db_path: Path = None):
    if db_path is None:
        db_path = get_db_path()
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, echo=False, future=True)

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA synchronous = NORMAL;")
        cursor.execute("PRAGMA busy_timeout = 5000;")
        cursor.close()

    return engine


_engine = None
_SessionFactory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


def get_session_factory():
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionFactory


def get_db_session() -> Generator[Session, None, None]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()
