from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    app_env: str
    data_dir: Path
    log_level: str
    ollama_host: str
    ollama_model: str = "llama3.2:3b"
    ollama_timeout_seconds: int = 120
    ollama_num_ctx: int = 4096
    ollama_num_predict: int = 512
    ollama_temperature: float = 0.0
    ollama_top_p: float = 0.8
    ollama_top_k: int = 20
    ollama_repeat_penalty: float = 1.1
    retrieval_top_k: int = 5
    max_xlsx_mb: int = 50
    chunk_max_chars: int = 1500
    chunk_min_chars: int = 80
    max_extracted_cells: int = 200000
    include_hidden_sheets: bool = False
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_device: str = "auto"
    embedding_batch_size: int = 16
    vector_collection: str = "rag_sllm_chunks"
    search_top_k: int = 5
    keyword_candidate_k: int = 20
    vector_candidate_k: int = 20
    keyword_weight: float = 0.3
    vector_weight: float = 0.7
    vector_min_similarity: float = 0.0

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
    chunk_max_chars = _positive_int_from_env("APP_CHUNK_MAX_CHARS", 1500)
    chunk_min_chars = _positive_int_from_env("APP_CHUNK_MIN_CHARS", 80)
    max_extracted_cells = _positive_int_from_env("APP_MAX_EXTRACTED_CELLS", 200000)
    include_hidden_sheets = _bool_from_env("APP_INCLUDE_HIDDEN_SHEETS", False)
    embedding_batch_size = _positive_int_from_env("APP_EMBEDDING_BATCH_SIZE", 16)
    search_top_k = _positive_int_from_env("APP_SEARCH_TOP_K", 5)
    keyword_candidate_k = _positive_int_from_env("APP_KEYWORD_CANDIDATE_K", 20)
    vector_candidate_k = _positive_int_from_env("APP_VECTOR_CANDIDATE_K", 20)
    keyword_weight = _non_negative_float_from_env("APP_KEYWORD_WEIGHT", 0.3)
    vector_weight = _non_negative_float_from_env("APP_VECTOR_WEIGHT", 0.7)
    if keyword_weight + vector_weight <= 0:
        raise ValueError("APP_KEYWORD_WEIGHT and APP_VECTOR_WEIGHT cannot both be 0.")

    settings = Settings(
        app_env=app_env,
        data_dir=data_dir.resolve(),
        log_level=os.environ.get("APP_LOG_LEVEL", "INFO").strip().upper() or "INFO",
        ollama_host=_ollama_host_from_env(),
        ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.2:3b").strip() or "llama3.2:3b",
        ollama_timeout_seconds=_positive_int_from_env("OLLAMA_TIMEOUT_SECONDS", 120),
        ollama_num_ctx=_positive_int_from_env("OLLAMA_NUM_CTX", 4096),
        ollama_num_predict=_positive_int_from_env("OLLAMA_NUM_PREDICT", 512),
        ollama_temperature=_non_negative_float_from_env("OLLAMA_TEMPERATURE", 0.0),
        ollama_top_p=_non_negative_float_from_env("OLLAMA_TOP_P", 0.8),
        ollama_top_k=_positive_int_from_env("OLLAMA_TOP_K", 20),
        ollama_repeat_penalty=_non_negative_float_from_env("OLLAMA_REPEAT_PENALTY", 1.1),
        retrieval_top_k=_positive_int_from_env("RETRIEVAL_TOP_K", 5),
        max_xlsx_mb=max_xlsx_mb,
        chunk_max_chars=chunk_max_chars,
        chunk_min_chars=chunk_min_chars,
        max_extracted_cells=max_extracted_cells,
        include_hidden_sheets=include_hidden_sheets,
        embedding_model=os.environ.get("APP_EMBEDDING_MODEL", "intfloat/multilingual-e5-small").strip(),
        embedding_device=os.environ.get("APP_EMBEDDING_DEVICE", "auto").strip().lower() or "auto",
        embedding_batch_size=embedding_batch_size,
        vector_collection=os.environ.get("APP_VECTOR_COLLECTION", "rag_sllm_chunks").strip() or "rag_sllm_chunks",
        search_top_k=search_top_k,
        keyword_candidate_k=keyword_candidate_k,
        vector_candidate_k=vector_candidate_k,
        keyword_weight=keyword_weight,
        vector_weight=vector_weight,
        vector_min_similarity=_non_negative_float_from_env("APP_VECTOR_MIN_SIMILARITY", 0.0),
    )
    settings.ensure_directories()
    return settings


def _positive_int_from_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name, str(default)).strip() or str(default)
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0.")
    return value


def _ollama_host_from_env() -> str:
    value = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("OLLAMA_HOST must be an http or https URL.")
    return value


def _bool_from_env(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be true or false.")


def _non_negative_float_from_env(name: str, default: float) -> float:
    raw_value = os.environ.get(name, str(default)).strip() or str(default)
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc
    if value < 0:
        raise ValueError(f"{name} must be greater than or equal to 0.")
    return value
