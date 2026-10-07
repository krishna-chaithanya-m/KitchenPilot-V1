"""Database session management, connection pooling, and lifecycle helpers."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.config import get_database_url

logger = logging.getLogger("kitchenpilot.db")

_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker[Session]] = None


def get_engine() -> Engine:
    """Retrieve or initialize the singleton SQLAlchemy engine."""
    global _engine
    if _engine is None:
        db_url = get_database_url()
        # Configure robust connection pooling
        is_sqlite = db_url.startswith("sqlite")
        connect_args = {"check_same_thread": False} if is_sqlite else {}

        _engine = create_engine(
            db_url,
            pool_pre_ping=True,
            connect_args=connect_args,
            pool_timeout=10,
        )
        logger.info("Initialized database engine for %s", db_url.split("@")[-1] if "@" in db_url else db_url)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Retrieve or initialize the sessionmaker factory."""
    global _SessionFactory
    if _SessionFactory is None:
        engine = get_engine()
        _SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionFactory


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Provide a transactional database session context with automatic rollback."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_db_connection(db_url: Optional[str] = None, timeout_seconds: int = 2) -> tuple[bool, Optional[str]]:
    """Check if the configured database is reachable within timeout_seconds."""
    target_url = db_url or get_database_url()
    try:
        is_sqlite = target_url.startswith("sqlite")
        connect_args = {"check_same_thread": False} if is_sqlite else {"connect_timeout": timeout_seconds}
        test_engine = create_engine(
            target_url,
            connect_args=connect_args,
            pool_pre_ping=False,
        )
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        test_engine.dispose()
        return True, None
    except Exception as exc:
        logger.warning("Database connectivity check failed: %s", exc)
        return False, str(exc)

