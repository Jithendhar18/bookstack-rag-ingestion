from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.logging import get_logger, setup_logging
from app.config.settings import get_settings
from app.db.migration_runner import MigrationRunner

logger = get_logger(__name__)


def main() -> None:
    settings = get_settings()
    setup_logging(log_level=settings.log_level, json_output=settings.log_json)

    runner = MigrationRunner(settings=settings)
    applied = runner.run()

    if not applied:
        logger.info("migrations.none_pending")
        return

    logger.info("migrations.applied", count=len(applied), versions=applied)


if __name__ == "__main__":
    main()
