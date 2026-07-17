from __future__ import annotations

import hashlib
import time
from datetime import datetime

from app.config.settings import Settings
from app.models.document import DocumentChunk, IndexingResult
from app.repositories.document_repository import DocumentRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.keyword_search_repository import KeywordSearchRepository
from app.repositories.search_index_repository import SearchIndexRepository
from app.services.embedding_service import EmbeddingService
from app.services.exceptions import SearchIndexError
from app.services.search_text import build_search_text
from app.storage.vector_storage import ChromaVectorRepository


class SearchIndexService:
    def __init__(
        self,
        settings: Settings,
        document_repository: DocumentRepository | None = None,
        extraction_repository: ExtractionRepository | None = None,
        keyword_repository: KeywordSearchRepository | None = None,
        index_repository: SearchIndexRepository | None = None,
        embedding_service: EmbeddingService | None = None,
        vector_repository: ChromaVectorRepository | None = None,
    ) -> None:
        self._settings = settings
        self._documents = document_repository or DocumentRepository(settings.database_path)
        self._extraction = extraction_repository or ExtractionRepository(settings.database_path)
        self._keyword = keyword_repository or KeywordSearchRepository(settings.database_path)
        self._index = index_repository or SearchIndexRepository(settings.database_path)
        self._embedding = embedding_service or EmbeddingService(
            settings.embedding_model,
            settings.embedding_device,
            settings.embedding_batch_size,
        )
        self._vector = vector_repository

    def index_document(self, document_id: str, force: bool = False) -> IndexingResult:
        started = time.perf_counter()
        document = self._documents.get_by_id(document_id)
        if not document:
            raise SearchIndexError("등록된 문서를 찾을 수 없습니다.")
        if document.status not in {"PARSED", "COMPLETED"}:
            raise SearchIndexError("먼저 문서 내용 추출을 완료해야 합니다.")
        chunks = self._extraction.list_chunks(document_id)
        if not chunks:
            raise SearchIndexError("검색 인덱스를 만들 청크가 없습니다.")

        content_fingerprint = _content_fingerprint(chunks)
        model_fingerprint = self._embedding.get_model_fingerprint()
        current = self._index.get(document_id)
        if (
            current
            and current.status == "READY"
            and not force
            and current.content_fingerprint == content_fingerprint
            and current.model_fingerprint == model_fingerprint
            and current.chunk_count == len(chunks)
        ):
            return IndexingResult(document_id, current.fts_count, current.vector_count, self._settings.embedding_model, "READY", 0)

        self._index.upsert_status(document_id, "INDEXING", self._settings.embedding_model, model_fingerprint)
        try:
            fts_count = self._keyword.index_document(document, chunks)
            search_texts = [build_search_text(document, chunk) for chunk in chunks]
            embeddings = self._embedding.encode_documents(search_texts)
            vector = self._vector or ChromaVectorRepository(
                self._settings.vector_db_dir,
                self._settings.vector_collection,
                model_fingerprint,
            )
            vector_count = vector.upsert_document(document, chunks, embeddings)
            self._index.upsert_status(
                document_id,
                "READY",
                self._settings.embedding_model,
                model_fingerprint,
                len(chunks),
                fts_count,
                vector_count,
                datetime.now().replace(microsecond=0),
                None,
                content_fingerprint,
            )
            self._documents.update_parse_status(document_id, "COMPLETED", parsed_at=document.parsed_at, parse_error=None)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return IndexingResult(document_id, fts_count, vector_count, self._settings.embedding_model, "READY", elapsed_ms)
        except Exception as exc:
            message = str(exc) or "검색 인덱스 생성 중 오류가 발생했습니다."
            self._index.upsert_status(document_id, "FAILED", self._settings.embedding_model, model_fingerprint, index_error=message)
            self._documents.update_parse_status(document_id, "PARSED", parsed_at=document.parsed_at, parse_error=None)
            if isinstance(exc, SearchIndexError):
                raise
            raise SearchIndexError("검색 인덱스 생성 중 오류가 발생했습니다.") from exc

    def reindex_document(self, document_id: str) -> IndexingResult:
        return self.index_document(document_id, force=True)

    def get_index_status(self, document_id: str):
        return self._index.get(document_id)

    def mark_stale(self, document_id: str) -> None:
        self._index.mark_stale(document_id)


def _content_fingerprint(chunks: list[DocumentChunk]) -> str:
    raw = "\n".join(f"{chunk.id}:{chunk.content_hash}" for chunk in sorted(chunks, key=lambda item: item.id))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
