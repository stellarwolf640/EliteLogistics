from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    elite_journal_dir: Path
    spansh_base_url: str = "https://www.spansh.co.uk/api"
    request_timeout_seconds: float = 12.0
    remote_concurrency: int = 6


def get_settings() -> Settings:
    data_dir = Path(os.getenv("ELITE_LOGISTICS_DATA_DIR", Path.cwd() / "data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    database_url = os.getenv(
        "ELITE_LOGISTICS_DATABASE_URL",
        f"sqlite:///{(data_dir / 'elite-logistics.db').as_posix()}",
    )
    return Settings(
        data_dir=data_dir,
        database_url=database_url,
        elite_journal_dir=Path(
            os.getenv(
                "ELITE_DANGEROUS_JOURNAL_DIR",
                Path.home() / "Saved Games" / "Frontier Developments" / "Elite Dangerous",
            )
        ).resolve(),
        spansh_base_url=os.getenv("SPANSH_BASE_URL", "https://www.spansh.co.uk/api").rstrip("/"),
    )

