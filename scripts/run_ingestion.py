from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import get_settings
from app.pipelines.ingestion_pipeline import IngestionPipeline


def main() -> None:
    settings = get_settings()
    pipeline = IngestionPipeline(settings=settings)
    pipeline.run()


if __name__ == "__main__":
    main()
