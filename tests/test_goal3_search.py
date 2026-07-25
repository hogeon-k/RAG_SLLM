from __future__ import annotations

import math
from datetime import datetime

import pytest

from app.config.settings import Settings
from app.models.document import Document, DocumentChunk, ParsedCell, ParsedSheet
from app.repositories.document_repository import DocumentRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.keyword_search_repository import KeywordSearchRepository, extract_article_numbers
from app.repositories.search_index_repository import SearchIndexRepository
from app.services.embedding_service import EmbeddingService
from app.services.exceptions import RetrievalError, SearchIndexError
from app.services.retrieval_service import RetrievalService
from app.services.search_index_service import SearchIndexService
from app.storage.vector_storage import ChromaVectorRepository


class FakeEmbeddingService:
    model_name = "fake-e5"

    def __init__(self) -> None:
        self.document_inputs: list[str] = []
        self.query_inputs: list[str] = []

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_inputs.extend(texts)
        return [_vector_for_text(text) for text in texts]

    def encode_query(self, query: str) -> list[float]:
        self.query_inputs.append(query)
        return _vector_for_text(query)

    def get_dimension(self) -> int:
        return 4

    def get_model_fingerprint(self) -> str:
        return "fake-fingerprint"


def _vector_for_text(text: str) -> list[float]:
    features = [
        3.0 if "연차" in text or "휴가" in text else 0.1,
        3.0 if "긴급" in text or "당일" in text else 0.1,
        3.0 if "출장" in text or "영수증" in text else 0.1,
        1.0,
    ]
    norm = math.sqrt(sum(value * value for value in features))
    return [value / norm for value in features]


def _settings(tmp_path) -> Settings:
    settings = Settings(
        app_env="test",
        data_dir=tmp_path / "data",
        log_level="INFO",
        ollama_host="http://127.0.0.1:11434",
        embedding_model="fake-e5",
        vector_collection="test_chunks",
    )
    settings.ensure_directories()
    return settings


def _document(document_id: str = "DOC-1") -> Document:
    return Document(
        id=document_id,
        original_name="fixture.xlsx",
        stored_path=f"uploads/{document_id}/document.xlsx",
        file_hash=f"hash-{document_id}",
        file_size_bytes=100,
        version="2.0",
        effective_date=None,
        revised_date=None,
        department=None,
        is_latest=True,
        status="PARSED",
        error_message=None,
        uploaded_at=datetime(2026, 1, 1, 10, 0, 0),
        parsed_at=datetime(2026, 1, 1, 10, 1, 0),
    )


def _chunks(document_id: str = "DOC-1") -> list[DocumentChunk]:
    return [
        DocumentChunk(
            f"{document_id}-S001-C0000",
            document_id,
            f"{document_id}-S001",
            "휴가규정",
            "A13",
            "F16",
            "A13:F16",
            ("A13", "B13:F13", "A14", "B14:F14"),
            13,
            16,
            "제1절",
            "제8조",
            None,
            "연차휴가 신청",
            "제8조 | 연차휴가 신청\n① | 연차휴가는 사용 예정일 3일 전까지 신청해야 한다.",
            0,
            "hash-a",
            datetime(2026, 1, 1),
        ),
        DocumentChunk(
            f"{document_id}-S001-C0001",
            document_id,
            f"{document_id}-S001",
            "휴가규정",
            "A18",
            "F20",
            "A18:F20",
            ("A18:F18", "A19", "B19:F19"),
            18,
            20,
            "제1절",
            "제8조의2",
            None,
            "긴급휴가",
            "제8조의2(긴급휴가)\n① | 긴급한 사유가 있으면 당일 신청할 수 있다.",
            1,
            "hash-b",
            datetime(2026, 1, 1),
        ),
        DocumentChunk(
            f"{document_id}-S002-C0000",
            document_id,
            f"{document_id}-S002",
            "출장규정",
            "A10",
            "G18",
            "A10:G18",
            ("A10", "B10:G10"),
            10,
            18,
            None,
            "제3조",
            None,
            "제출 서류",
            "출장자는 영수증과 출장보고서를 제출해야 한다.",
            0,
            "hash-c",
            datetime(2026, 1, 1),
        ),
    ]


def _seed_extraction(settings: Settings, document_id: str = "DOC-1") -> None:
    document = _document(document_id)
    DocumentRepository(settings.database_path).create(document)
    sheets = [
        ParsedSheet(f"{document_id}-S001", document_id, "휴가규정", 0, "visible", 20, 6, 10, 4, datetime(2026, 1, 1)),
        ParsedSheet(f"{document_id}-S002", document_id, "출장규정", 1, "visible", 18, 7, 5, 2, datetime(2026, 1, 1)),
    ]
    cells = [
        ParsedCell(f"{document_id}-S001-A13", document_id, f"{document_id}-S001", "휴가규정", "A13", 13, 1, "string", "제8조", None, None, None, False, False),
        ParsedCell(f"{document_id}-S001-B14", document_id, f"{document_id}-S001", "휴가규정", "B14", 14, 2, "string", "3일 전", None, None, "B14:F14", True, False),
    ]
    ExtractionRepository(settings.database_path).replace_extraction(document_id, sheets, cells, _chunks(document_id))


def test_fts_keyword_index_and_search(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed_extraction(settings)
    document = DocumentRepository(settings.database_path).get_by_id("DOC-1")
    chunks = ExtractionRepository(settings.database_path).list_chunks("DOC-1")
    repository = KeywordSearchRepository(settings.database_path)

    assert repository.index_document(document, chunks) == 3
    results = repository.search("연차휴가", ["DOC-1"], 5)

    assert results
    assert results[0].chunk_id.endswith("C0000")


def test_embedding_service_rejects_empty_and_bad_vectors() -> None:
    service = EmbeddingService("unused", "cpu")
    with pytest.raises(SearchIndexError):
        service.encode_query("")


def test_chroma_vector_repository_upsert_query_and_replace(tmp_path) -> None:
    settings = _settings(tmp_path)
    document = _document()
    chunks = _chunks()
    repository = ChromaVectorRepository(settings.vector_db_dir, "test_collection", "fake-fingerprint")
    embeddings = [_vector_for_text(chunk.content) for chunk in chunks]

    assert repository.upsert_document(document, chunks, embeddings) == 3
    assert repository.count_document(document.id) == 3
    assert repository.upsert_document(document, chunks[:2], embeddings[:2]) == 2
    assert repository.count_document(document.id) == 2

    results = repository.query(_vector_for_text("연차휴가"), [document.id], 2)
    assert results


def test_search_index_service_indexes_document(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed_extraction(settings)
    embedding = FakeEmbeddingService()
    vector = ChromaVectorRepository(settings.vector_db_dir, "index_collection", "fake-fingerprint")
    service = SearchIndexService(settings, embedding_service=embedding, vector_repository=vector)

    result = service.index_document("DOC-1")

    assert result.status == "READY"
    assert result.fts_count == 3
    assert result.vector_count == 3
    assert SearchIndexRepository(settings.database_path).get("DOC-1").status == "READY"
    assert DocumentRepository(settings.database_path).get_by_id("DOC-1").status == "COMPLETED"


def test_replacing_extraction_marks_search_index_stale(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed_extraction(settings)
    embedding = FakeEmbeddingService()
    vector = ChromaVectorRepository(settings.vector_db_dir, "stale_collection", "fake-fingerprint")
    SearchIndexService(settings, embedding_service=embedding, vector_repository=vector).index_document("DOC-1")

    repository = ExtractionRepository(settings.database_path)
    repository.replace_extraction(
        "DOC-1",
        [
            ParsedSheet("DOC-1-S001", "DOC-1", "Sheet1", 0, "visible", 1, 1, 1, 0, datetime(2026, 1, 1)),
        ],
        [
            ParsedCell(
                "DOC-1-S001-A1",
                "DOC-1",
                "DOC-1-S001",
                "Sheet1",
                "A1",
                1,
                1,
                "string",
                "updated",
                None,
                None,
                None,
                False,
                False,
            ),
        ],
        [
            DocumentChunk(
                "DOC-1-S001-C0000",
                "DOC-1",
                "DOC-1-S001",
                "Sheet1",
                "A1",
                "A1",
                "A1:A1",
                ("A1",),
                1,
                1,
                None,
                None,
                None,
                None,
                "updated",
                0,
                "hash-updated",
                datetime(2026, 1, 1),
            ),
        ],
    )

    assert SearchIndexRepository(settings.database_path).get("DOC-1").status == "STALE"
    assert DocumentRepository(settings.database_path).get_by_id("DOC-1").status == "PARSED"


def test_retrieval_keyword_vector_and_hybrid(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed_extraction(settings)
    embedding = FakeEmbeddingService()
    vector = ChromaVectorRepository(settings.vector_db_dir, "retrieval_collection", "fake-fingerprint")
    SearchIndexService(settings, embedding_service=embedding, vector_repository=vector).index_document("DOC-1")
    retrieval = RetrievalService(settings, embedding_service=embedding, vector_repository=vector)

    keyword = retrieval.search("연차휴가", mode="keyword")
    vector_response = retrieval.search("긴급 당일 신청", mode="vector")
    hybrid = retrieval.search("제8조 연차휴가", mode="hybrid")

    assert keyword.results[0].article == "제8조"
    assert vector_response.results[0].article == "제8조의2"
    assert hybrid.results[0].cell_range == "A13:F16"


def test_retrieval_empty_query_rejected(tmp_path) -> None:
    settings = _settings(tmp_path)
    with pytest.raises(RetrievalError):
        RetrievalService(settings, embedding_service=FakeEmbeddingService()).search(" ")


def test_article_numbers_are_normalized_and_distinguished() -> None:
    assert extract_article_numbers("제8조") == ["제8조"]
    assert extract_article_numbers("제 8 조") == ["제8조"]
    assert extract_article_numbers("제8조의2") == ["제8조의2"]
    assert extract_article_numbers("제8조의 2") == ["제8조의2"]
    assert extract_article_numbers("8") == []


def test_keyword_search_fallbacks_for_korean_short_terms_and_natural_queries(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed_extraction(settings)
    document = DocumentRepository(settings.database_path).get_by_id("DOC-1")
    chunks = ExtractionRepository(settings.database_path).list_chunks("DOC-1")
    repository = KeywordSearchRepository(settings.database_path)
    repository.index_document(document, chunks)

    assert repository.search("제8조", ["DOC-1"], 5)[0].chunk_id.endswith("C0000")
    assert repository.search("제8조의2", ["DOC-1"], 5)[0].chunk_id.endswith("C0001")
    assert repository.search("휴가 신청", ["DOC-1"], 5)
    assert repository.search("3일", ["DOC-1"], 5)
    assert repository.search("당일 신청", ["DOC-1"], 5)[0].chunk_id.endswith("C0001")
    assert repository.search("긴급한 사유가 있으면 당일 신청 가능한가", ["DOC-1"], 5)[0].chunk_id.endswith("C0001")
    assert repository.search("출장 때 필요한 서류는 무엇인가", ["DOC-1"], 5)


def test_keyword_search_escapes_like_and_fts_input(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed_extraction(settings)
    document = DocumentRepository(settings.database_path).get_by_id("DOC-1")
    chunks = ExtractionRepository(settings.database_path).list_chunks("DOC-1")
    repository = KeywordSearchRepository(settings.database_path)
    repository.index_document(document, chunks)

    assert repository.search("%", ["DOC-1"], 5) == []
    assert repository.search("_", ["DOC-1"], 5) == []
    assert repository.search("\\", ["DOC-1"], 5) == []
    assert repository.search('"제8조" OR document_id:DOC-2', ["DOC-1"], 5)


def test_embedding_service_reports_configured_and_resolved_device_without_loading() -> None:
    service = EmbeddingService("unused", "cpu")

    assert service.get_status()["configured_device"] == "cpu"
    assert service.get_status()["resolved_device"] is None
    assert service._resolve_device() == "cpu"


def test_retrieval_prioritizes_exact_article_in_keyword_and_hybrid(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed_extraction(settings)
    embedding = FakeEmbeddingService()
    vector = ChromaVectorRepository(settings.vector_db_dir, "exact_article_collection", "fake-fingerprint")
    SearchIndexService(settings, embedding_service=embedding, vector_repository=vector).index_document("DOC-1")
    retrieval = RetrievalService(settings, embedding_service=embedding, vector_repository=vector)

    assert retrieval.search("제8조", mode="keyword").results[0].cell_range == "A13:F16"
    assert retrieval.search("제8조의2", mode="keyword").results[0].cell_range == "A18:F20"
    assert retrieval.search("제8조", mode="hybrid").results[0].cell_range == "A13:F16"
    assert retrieval.search("제8조의2", mode="hybrid").results[0].cell_range == "A18:F20"


def test_hybrid_prioritizes_lane_violation_type_chunk(tmp_path) -> None:
    settings = _settings(tmp_path)
    document = _document("DOC-LANE")
    DocumentRepository(settings.database_path).create(document)
    chunks = [
        DocumentChunk(
            "DOC-LANE-S001-C0000",
            "DOC-LANE",
            "DOC-LANE-S001",
            "영업실무",
            "A1",
            "B3",
            "A1:B3",
            ("A1", "B1"),
            1,
            3,
            None,
            None,
            None,
            "출구위반처리",
            "출구위반처리 | 출구 하이패스 차로에서 발생되는 위반차량을 조회하며 처리유형 적정성을 심사한다.",
            0,
            "hash-lane-bad",
            datetime(2026, 1, 1),
        ),
        DocumentChunk(
            "DOC-LANE-S001-C0001",
            "DOC-LANE",
            "DOC-LANE-S001",
            "영업실무",
            "A4",
            "B8",
            "A4:B8",
            ("A4", "B4"),
            4,
            8,
            None,
            None,
            None,
            "하이패스 위반 유형",
            "하이패스 위반 유형 | 입구정보이상은 입구에서 일반차로 이용, 하이패스 차로에서 단말기 미작동, 휴게소에서 단말기 구입후 진출 등이다.",
            1,
            "hash-lane-good",
            datetime(2026, 1, 1),
        ),
    ]
    ExtractionRepository(settings.database_path).replace_extraction(
        document.id,
        [ParsedSheet("DOC-LANE-S001", document.id, "영업실무", 0, "visible", 8, 2, 2, 0, datetime(2026, 1, 1))],
        [],
        chunks,
    )
    embedding = FakeEmbeddingService()
    vector = ChromaVectorRepository(settings.vector_db_dir, "lane_collection", "fake-fingerprint")
    SearchIndexService(settings, embedding_service=embedding, vector_repository=vector).index_document(document.id)
    retrieval = RetrievalService(settings, embedding_service=embedding, vector_repository=vector)

    response = retrieval.search("일반차로 위반 유형은?", mode="hybrid")

    assert response.results[0].chunk_id == "DOC-LANE-S001-C0001"

