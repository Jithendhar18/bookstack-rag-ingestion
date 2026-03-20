from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import Settings, get_settings

# Global session manager instance
_session_manager: SessionManager | None = None


class SessionManager:
    """Manages SQLAlchemy engine and session lifecycle."""

    def __init__(self, settings: Settings) -> None:
        self.engine = create_engine(
            settings.postgres_sqlalchemy_url,
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_pool_overflow,
            pool_timeout=30,
            connect_args={"options": "-c statement_timeout=30000"},
        )
        self._session_factory = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False
        )

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def get_session_manager() -> SessionManager:
    """Get or create global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(get_settings())
    return _session_manager


def get_db() -> Iterator[Session]:
    """FastAPI dependency for database session."""
    manager = get_session_manager()
    session = manager._session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
