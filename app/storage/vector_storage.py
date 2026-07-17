from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chromadb

from app.models.document import Document, DocumentChunk
from app.services.exceptions import SearchIndexError


@dataclass(frozen=True)
class VectorCandidate:
    chunk_id: str
    document_id: str
    similarity: float
    rank: int


class ChromaVectorRepository:
    def __init__(self, persist_dir: Path, collection_name: str, model_fingerprint: str) -> None:
        self._persist_dir = persist_dir
        self._collection_name = collection_name
        self._model_fingerprint = model_fingerprint
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"model_fingerprint": model_fingerprint},
            embedding_function=None,
        )

    def upsert_document(self, document: Document, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> int:
        if len(chunks) != len(embeddings):
            raise SearchIndexError("청크 수와 임베딩 수가 일치하지 않습니다.")
        self.delete_document(document.id)
        if not chunks:
            return 0
        dimension = len(embeddings[0])
        if any(len(vector) != dimension for vector in embeddings):
            raise SearchIndexError("서로 다른 차원의 벡터를 같은 collection에 저장할 수 없습니다.")
        self._collection.upsert(
            ids=[chunk.id for chunk in chunks],
            embeddings=embeddings,
            documents=[chunk.content for chunk in chunks],
            metadatas=[
                {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "original_name": document.original_name,
                    "sheet_name": chunk.sheet_name,
                    "article": chunk.article or "",
                    "title": chunk.title or "",
                    "cell_range": chunk.cell_range,
                    "content_hash": chunk.content_hash,
                    "model_fingerprint": self._model_fingerprint,
                }
                for chunk in chunks
            ],
        )
        return len(chunks)

    def delete_document(self, document_id: str) -> None:
        existing = self._collection.get(where={"document_id": document_id}, include=[])
        ids = existing.get("ids", [])
        if ids:
            self._collection.delete(ids=ids)

    def query(self, query_embedding: list[float], document_ids: list[str] | None, limit: int) -> list[VectorCandidate]:
        where = {"document_id": {"$in": document_ids}} if document_ids else None
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=where,
            include=["metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        candidates: list[VectorCandidate] = []
        for index, (chunk_id, distance, metadata) in enumerate(zip(ids, distances, metadatas), 1):
            similarity = max(0.0, 1.0 - float(distance))
            candidates.append(VectorCandidate(chunk_id, metadata["document_id"], similarity, index))
        return candidates

    def count_document(self, document_id: str) -> int:
        return len(self._collection.get(where={"document_id": document_id}, include=[]).get("ids", []))

    def collection_status(self) -> dict[str, object]:
        return {
            "name": self._collection_name,
            "count": self._collection.count(),
            "model_fingerprint": self._model_fingerprint,
            "path": str(self._persist_dir),
        }
