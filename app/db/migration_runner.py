from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import ProgrammingError

from app.config.settings import Settings


class MigrationRunner:
    """Runs Alembic database migrations programmatically."""

    def __init__(self, settings: Settings, alembic_ini_path: Path | None = None) -> None:
        self.settings = settings
        self.project_root = Path(__file__).resolve().parents[2]
        self.alembic_ini_path = alembic_ini_path or self.project_root / "alembic.ini"

    def run(self) -> list[str]:
        """Apply all pending Alembic migrations and return applied revisions."""
        before = self._get_current_revision()

        config = Config(str(self.alembic_ini_path))
        config.set_main_option("script_location", str(self.project_root / "db" / "alembic"))
        config.set_main_option("sqlalchemy.url", self.settings.postgres_sqlalchemy_url)

        command.upgrade(config, "head")

        after = self._get_current_revision()
        if after is None or after == before:
            return []

        return [after]

    def bootstrap_if_uninitialized(self) -> list[str]:
        """Run migrations only for fresh databases without Alembic history.

        This keeps day-to-day schema updates manual via scripts/db_migrate.py.
        """
        if self._has_alembic_version_table():
            return []

        return self.run()

    def _has_alembic_version_table(self) -> bool:
        engine = create_engine(self.settings.postgres_sqlalchemy_url, pool_pre_ping=True)
        try:
            with engine.connect() as connection:
                return bool(inspect(connection).has_table("alembic_version"))
        finally:
            engine.dispose()

    def _get_current_revision(self) -> str | None:
        engine = create_engine(self.settings.postgres_sqlalchemy_url, pool_pre_ping=True)

        try:
            with engine.connect() as connection:
                try:
                    row = connection.execute(
                        text("SELECT version_num FROM alembic_version LIMIT 1")
                    )
                except ProgrammingError:
                    connection.rollback()
                    return None

                record = row.first()
                return str(record[0]) if record else None
        finally:
            engine.dispose()
