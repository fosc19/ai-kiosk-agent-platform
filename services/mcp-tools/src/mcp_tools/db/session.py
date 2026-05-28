"""Database session and engine management."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from mcp_tools.config import settings

_engine = None
_SessionLocal = None


def get_engine():
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        database_url = settings.database_url

        # Configure based on database type
        if database_url.startswith("postgresql://"):
            # Use psycopg v3 driver for PostgreSQL
            database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
            _engine = create_engine(
                database_url,
                echo=settings.log_level == "DEBUG",
                pool_pre_ping=True,
            )
        elif database_url.startswith("sqlite"):
            # SQLite configuration
            from pathlib import Path

            # Ensure data directory exists for SQLite
            if ":///" in database_url:
                db_path = database_url.split(":///")[1]
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)

            _engine = create_engine(
                database_url,
                echo=settings.log_level == "DEBUG",
                connect_args={"check_same_thread": False},  # Allow multi-thread access
            )
        else:
            _engine = create_engine(
                database_url,
                echo=settings.log_level == "DEBUG",
            )
    return _engine


def get_session_factory():
    """Get or create the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
        )
    return _SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager for database sessions."""
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Initialize database tables.

    For SQLite: creates tables directly using SQLAlchemy.
    For PostgreSQL: assumes Alembic migrations handle schema.
    """
    from mcp_tools.db.models import Base

    engine = get_engine()

    # For SQLite, create all tables directly
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)


def init_db_and_seed() -> None:
    """Initialize database and run seeds if needed.

    Convenient for local development startup.
    """
    init_db()

    # Run seeds
    from mcp_tools.db.seeds import run_seeds
    run_seeds()
