from __future__ import annotations

from app.config.settings import Settings
from app.repositories.document_repository import DocumentRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.services.document_extraction_service import DocumentExtractionService
from app.services.document_service import DocumentService
from tests.helpers import create_xlsx


def _settings(tmp_path) -> Settings:
    settings = Settings(
        app_env="test",
        data_dir=tmp_path / "data",
        log_level="INFO",
        ollama_host="http://127.0.0.1:11434",
        max_xlsx_mb=50,
        chunk_max_chars=1500,
        chunk_min_chars=80,
        max_extracted_cells=200000,
        include_hidden_sheets=False,
    )
    settings.ensure_directories()
    return settings


def test_extract_document_transitions_to_parsed(tmp_path) -> None:
    settings = _settings(tmp_path)
    source = create_xlsx(tmp_path / "rule.xlsx")
    document = DocumentService(settings).register_document(source)

    result = DocumentExtractionService(settings).extract_document(document.id)

    refreshed = DocumentRepository(settings.database_path).get_by_id(document.id)
    assert result.status == "PARSED"
    assert result.chunk_count >= 1
    assert refreshed.status == "PARSED"
    assert refreshed.parsed_at is not None
    assert ExtractionRepository(settings.database_path).count_chunks(document.id) >= 1


def test_reextract_replaces_without_duplicates(tmp_path) -> None:
    settings = _settings(tmp_path)
    source = create_xlsx(tmp_path / "rule.xlsx")
    document = DocumentService(settings).register_document(source)
    service = DocumentExtractionService(settings)

    first = service.extract_document(document.id)
    second = service.extract_document(document.id)

    assert first.chunk_count == second.chunk_count
    assert ExtractionRepository(settings.database_path).count_chunks(document.id) == second.chunk_count
