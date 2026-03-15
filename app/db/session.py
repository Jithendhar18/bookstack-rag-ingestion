from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import Settings


class SessionManager:
    def __init__(self, settings: Settings) -> None:
        self.engine = create_engine(settings.postgres_sqlalchemy_url, pool_pre_ping=True)
        self._session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)

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
