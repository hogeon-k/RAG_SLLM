from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path

from app.config.settings import Settings
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.services.document_validator import DocumentValidator
from app.services.exceptions import (
    DocumentRegistrationError,
    DocumentStorageError,
    DuplicateDocumentError,
)
from app.storage.file_storage import FileStorage
from app.utils.hashing import calculate_sha256


class DocumentService:
    def __init__(
        self,
        settings: Settings,
        repository: DocumentRepository | None = None,
        storage: FileStorage | None = None,
        validator: DocumentValidator | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._settings = settings
        self._repository = repository or DocumentRepository(settings.database_path)
        self._storage = storage or FileStorage(settings.data_dir)
        self._validator = validator or DocumentValidator(
            settings.max_xlsx_bytes,
            settings.allowed_document_extensions,
        )
        self._logger = logger or logging.getLogger("rag_sllm")

    def status_message(self) -> str:
        return "엑셀과 규정 문서를 등록하고 관리하는 화면입니다."

    def register_document(
        self,
        source_path: Path,
        version: str | None = None,
        effective_date: date | None = None,
        revised_date: date | None = None,
        department: str | None = None,
    ) -> Document:
        source_path = Path(source_path)
        version = _clean_optional_text(version)
        department = _clean_optional_text(department)
        document_id = f"DOC-{uuid.uuid4()}"

        self._validator.validate(source_path)
        file_hash = calculate_sha256(source_path)
        duplicate = self._repository.get_by_hash(file_hash)
        if duplicate:
            raise DuplicateDocumentError(
                "동일한 내용의 문서가 이미 등록되어 있습니다.\n"
                f"등록 문서: {duplicate.original_name}"
            )

        stored_path = ""
        try:
            stored_path = self._storage.store_document(source_path, document_id, file_hash)
            document = Document(
                id=document_id,
                original_name=source_path.name,
                stored_path=stored_path,
                file_hash=file_hash,
                file_size_bytes=source_path.stat().st_size,
                version=version,
                effective_date=effective_date,
                revised_date=revised_date,
                department=department,
                is_latest=True,
                status="UPLOADED",
                error_message=None,
                uploaded_at=datetime.now().replace(microsecond=0),
            )
            return self._repository.create(document)
        except sqlite3.IntegrityError as exc:
            self._storage.cleanup_document(document_id)
            self._logger.warning("Duplicate document hash blocked for %s", source_path.name)
            raise DuplicateDocumentError("동일한 내용의 문서가 이미 등록되어 있습니다.") from exc
        except DocumentRegistrationError:
            if stored_path:
                self._storage.cleanup_document(document_id)
            raise
        except Exception as exc:
            self._storage.cleanup_document(document_id)
            self._logger.exception("Unexpected document registration failure for %s", source_path.name)
            raise DocumentStorageError("문서를 등록하는 중 예상하지 못한 오류가 발생했습니다.") from exc

    def list_documents(self) -> list[Document]:
        return self._repository.list_all()


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
