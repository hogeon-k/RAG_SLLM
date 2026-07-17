from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    app_env: str
    data_dir: Path
    log_level: str
    ollama_host: str
    max_xlsx_mb: int = 50

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def vector_db_dir(self) -> Path:
        return self.data_dir / "vector_db"

    @property
    def database_dir(self) -> Path:
        return self.data_dir / "database"

    @property
    def logs_dir(self) -> Path:
        return PROJECT_ROOT / "logs"

    @property
    def database_path(self) -> Path:
        return self.database_dir / "app.sqlite3"

    @property
    def allowed_document_extensions(self) -> tuple[str, ...]:
        return (".xlsx",)

    @property
    def max_xlsx_bytes(self) -> int:
        return self.max_xlsx_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.uploads_dir, self.vector_db_dir, self.database_dir, self.logs_dir):
            path.mkdir(parents=True, exist_ok=True)


def _default_data_dir(app_env: str) -> Path:
    if app_env.lower() == "production":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "RAG_SLLM"
    return PROJECT_ROOT / "data"


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    app_env = os.environ.get("APP_ENV", "development").strip() or "development"
    data_dir_value = os.environ.get("APP_DATA_DIR", "").strip()
    data_dir = Path(data_dir_value).expanduser() if data_dir_value else _default_data_dir(app_env)
    max_xlsx_value = os.environ.get("APP_MAX_XLSX_MB", "50").strip() or "50"
    try:
        max_xlsx_mb = int(max_xlsx_value)
    except ValueError as exc:
        raise ValueError("APP_MAX_XLSX_MB must be an integer.") from exc
    if max_xlsx_mb <= 0:
        raise ValueError("APP_MAX_XLSX_MB must be greater than 0.")

    settings = Settings(
        app_env=app_env,
        data_dir=data_dir.resolve(),
        log_level=os.environ.get("APP_LOG_LEVEL", "INFO").strip().upper() or "INFO",
        ollama_host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").strip(),
        max_xlsx_mb=max_xlsx_mb,
    )
    settings.ensure_directories()
    return settings
