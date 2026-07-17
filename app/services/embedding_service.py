from __future__ import annotations

import hashlib
import math
import threading

import numpy as np

from app.services.exceptions import SearchIndexError


class EmbeddingService:
    def __init__(self, model_name: str, device: str = "auto", batch_size: int = 16) -> None:
        self.model_name = model_name
        self.device = device
        self.resolved_device: str | None = None
        self.batch_size = batch_size
        self._model = None
        self._lock = threading.Lock()

    def load_model(self):
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                resolved_device = self._resolve_device()
                self.resolved_device = resolved_device
                self._model = SentenceTransformer(self.model_name, device=resolved_device)
            return self._model

    def get_status(self) -> dict[str, str | int | None]:
        return {
            "model_name": self.model_name,
            "configured_device": self.device,
            "resolved_device": self.resolved_device,
            "loaded": self._model is not None,
            "dimension": self.get_dimension() if self._model is not None else None,
        }

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        cleaned = [_clean_text(text) for text in texts]
        if any(not text for text in cleaned):
            raise SearchIndexError("빈 문서는 임베딩할 수 없습니다.")
        return self._encode([f"passage: {text}" for text in cleaned])

    def encode_query(self, query: str) -> list[float]:
        cleaned = _clean_text(query)
        if not cleaned:
            raise SearchIndexError("빈 질문은 임베딩할 수 없습니다.")
        return self._encode([f"query: {cleaned}"])[0]

    def get_dimension(self) -> int:
        model = self.load_model()
        if hasattr(model, "get_embedding_dimension"):
            return int(model.get_embedding_dimension())
        return int(model.get_sentence_embedding_dimension())

    def get_model_fingerprint(self) -> str:
        raw = f"{self.model_name}|{self.get_dimension()}|normalize=True"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _encode(self, texts: list[str]) -> list[list[float]]:
        model = self.load_model()
        vectors = model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        if vectors.ndim == 1:
            vectors = np.expand_dims(vectors, axis=0)
        result = vectors.astype(float).tolist()
        for vector in result:
            _validate_vector(vector)
        return result

    def _resolve_device(self) -> str:
        if self.device == "cpu":
            return "cpu"
        if self.device == "cuda":
            import torch

            if not torch.cuda.is_available():
                raise SearchIndexError("CUDA를 사용할 수 없습니다.")
            return "cuda"
        if self.device == "auto":
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        raise SearchIndexError("APP_EMBEDDING_DEVICE는 auto, cpu, cuda 중 하나여야 합니다.")


def _clean_text(text: str) -> str:
    return " ".join(str(text).strip().split())


def _validate_vector(vector: list[float]) -> None:
    if not vector:
        raise SearchIndexError("임베딩 벡터가 비어 있습니다.")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        raise SearchIndexError("임베딩 벡터 정규화에 실패했습니다.")
    for value in vector:
        if math.isnan(value) or math.isinf(value):
            raise SearchIndexError("임베딩 벡터에 NaN 또는 inf가 포함되어 있습니다.")
