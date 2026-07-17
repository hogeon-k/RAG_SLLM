from __future__ import annotations

from datetime import date

import pytest

from app.config.settings import Settings
from app.repositories.document_repository import DocumentRepository
from app.services.document_service import DocumentService
from app.services.exceptions import DuplicateDocumentError
from tests.helpers import create_xlsx


def _settings(tmp_path) -> Settings:
    settings = Settings(
        app_env="test",
        data_dir=tmp_path / "data",
        log_level="INFO",
        ollama_host="http://127.0.0.1:11434",
        max_xlsx_mb=50,
    )
    settings.ensure_directories()
    return settings


def test_register_document_success(tmp_path) -> None:
    settings = _settings(tmp_path)
    source = create_xlsx(tmp_path / "rule.xlsx")
    service = DocumentService(settings)

    document = service.register_document(
        source,
        version="  v1  ",
        effective_date=date(2026, 1, 1),
        revised_date=date(2026, 2, 1),
        department="  HR  ",
    )

    assert document.original_name == "rule.xlsx"
    assert document.version == "v1"
    assert document.department == "HR"
    assert document.status == "UPLOADED"
    assert (settings.data_dir / document.stored_path).exists()
    assert DocumentRepository(settings.database_path).count() == 1


def test_register_duplicate_same_file_rejected(tmp_path) -> None:
    settings = _settings(tmp_path)
    source = create_xlsx(tmp_path / "rule.xlsx")
    service = DocumentService(settings)

    service.register_document(source)

    with pytest.raises(DuplicateDocumentError):
        service.register_document(source)


def test_register_duplicate_same_content_rejected(tmp_path) -> None:
    settings = _settings(tmp_path)
    first = create_xlsx(tmp_path / "first.xlsx", "same")
    second = create_xlsx(tmp_path / "second.xlsx", "same")
    service = DocumentService(settings)

    service.register_document(first)

    with pytest.raises(DuplicateDocumentError):
        service.register_document(second)


def test_empty_metadata_normalized_to_none(tmp_path) -> None:
    settings = _settings(tmp_path)
    source = create_xlsx(tmp_path / "rule.xlsx")
    service = DocumentService(settings)

    document = service.register_document(source, version="   ", department="")

    assert document.version is None
    assert document.department is None

