from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import get_settings
from app.db.migration_runner import MigrationRunner


def main() -> None:
    settings = get_settings()
    runner = MigrationRunner(settings=settings)
    applied = runner.run()

    if not applied:
        print("No pending migrations.")
        return

    print("Applied migrations:")
    for version in applied:
        print(f"- {version}")


if __name__ == "__main__":
    main()
