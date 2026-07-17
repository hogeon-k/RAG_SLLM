from __future__ import annotations

import time

from app.config.settings import Settings
from app.models.document import SearchResponse, SearchResult
from app.repositories.document_repository import DocumentRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.keyword_search_repository import KeywordCandidate, KeywordSearchRepository, extract_article_numbers
from app.repositories.search_index_repository import SearchIndexRepository
from app.services.embedding_service import EmbeddingService
from app.services.exceptions import RetrievalError
from app.storage.vector_storage import ChromaVectorRepository, VectorCandidate


class RetrievalService:
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
        self._embedding = embedding_service or EmbeddingService(settings.embedding_model, settings.embedding_device, settings.embedding_batch_size)
        self._vector = vector_repository

    def search(
        self,
        query: str,
        mode: str = "hybrid",
        document_ids: list[str] | None = None,
        top_k: int | None = None,
    ) -> SearchResponse:
        started = time.perf_counter()
        cleaned = " ".join(query.strip().split())
        if not cleaned:
            raise RetrievalError("검색어를 입력해 주세요.")
        if mode not in {"keyword", "vector", "hybrid"}:
            raise RetrievalError("검색 모드는 keyword, vector, hybrid 중 하나여야 합니다.")
        requested_top_k = top_k or self._settings.search_top_k
        ready_ids = self._index.ready_document_ids(document_ids)
        if not ready_ids:
            return SearchResponse(cleaned, mode, [], requested_top_k, 0, 0, 0, tuple(), ("READY 상태의 검색 인덱스가 없습니다.",))

        keyword_candidates: list[KeywordCandidate] = []
        vector_candidates: list[VectorCandidate] = []
        if mode in {"keyword", "hybrid"}:
            keyword_candidates = self._keyword.search(cleaned, ready_ids, self._settings.keyword_candidate_k)
        if mode in {"vector", "hybrid"}:
            fingerprint = self._embedding.get_model_fingerprint()
            vector = self._vector or ChromaVectorRepository(self._settings.vector_db_dir, self._settings.vector_collection, fingerprint)
            query_embedding = self._embedding.encode_query(cleaned)
            vector_candidates = [
                candidate
                for candidate in vector.query(query_embedding, ready_ids, self._settings.vector_candidate_k)
                if candidate.similarity >= self._settings.vector_min_similarity
            ]

        results = self._merge(cleaned, keyword_candidates, vector_candidates, requested_top_k)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return SearchResponse(
            cleaned,
            mode,
            results,
            requested_top_k,
            elapsed_ms,
            len(keyword_candidates),
            len(vector_candidates),
            tuple(ready_ids),
        )

    def _merge(
        self,
        query: str,
        keyword_candidates: list[KeywordCandidate],
        vector_candidates: list[VectorCandidate],
        top_k: int,
    ) -> list[SearchResult]:
        exact_articles = set(extract_article_numbers(query))
        article_exact_ids = {candidate.chunk_id for candidate in keyword_candidates if candidate.article_exact}
        keyword_scores = _normalize_scores({candidate.chunk_id: candidate.score for candidate in keyword_candidates})
        vector_scores = _normalize_scores({candidate.chunk_id: candidate.similarity for candidate in vector_candidates})
        chunk_ids = sorted(set(keyword_scores) | set(vector_scores))
        weighted: list[tuple[str, float, bool]] = []
        for chunk_id in chunk_ids:
            chunk = self._extraction.get_chunk(chunk_id)
            score = self._settings.keyword_weight * keyword_scores.get(chunk_id, 0.0)
            score += self._settings.vector_weight * vector_scores.get(chunk_id, 0.0)
            score += _article_boost(query, chunk)
            is_article_exact = bool(chunk and chunk.article in exact_articles) or chunk_id in article_exact_ids
            weighted.append((chunk_id, score, is_article_exact))
        weighted.sort(key=lambda item: (not item[2], -item[1], item[0]))
        top_ids = [chunk_id for chunk_id, _score, _article_exact in weighted[:top_k]]
        chunks = {chunk.id: chunk for chunk in self._extraction.get_chunks_by_ids(top_ids)}
        results: list[SearchResult] = []
        for rank, (chunk_id, final_score, _article_exact) in enumerate(weighted[:top_k], 1):
            chunk = chunks.get(chunk_id)
            if not chunk:
                continue
            document = self._documents.get_by_id(chunk.document_id)
            if not document:
                continue
            matched_by = tuple(name for name, scores in (("keyword", keyword_scores), ("vector", vector_scores)) if chunk_id in scores)
            results.append(
                SearchResult(
                    chunk.id,
                    chunk.document_id,
                    document.original_name,
                    document.version,
                    chunk.sheet_name,
                    chunk.section,
                    chunk.article,
                    chunk.title,
                    chunk.content,
                    chunk.cell_range,
                    chunk.cell_refs,
                    keyword_scores.get(chunk_id),
                    vector_scores.get(chunk_id),
                    final_score,
                    matched_by,
                    rank,
                )
            )
        return results


def _normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    min_value = min(values)
    max_value = max(values)
    if max_value == min_value:
        return {key: 1.0 for key in scores}
    return {key: (value - min_value) / (max_value - min_value) for key, value in scores.items()}


def _article_boost(query: str, chunk) -> float:
    if not chunk or not chunk.article:
        return 0.0
    if chunk.article in set(extract_article_numbers(query)):
        return 0.35
    if query in chunk.content:
        return 0.05
    return 0.0
