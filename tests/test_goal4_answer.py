from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.config.settings import Settings
from app.models.document import Document, DocumentChunk, SearchResponse, SearchResult
from app.repositories.document_repository import DocumentRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.models.document import ParsedCell, ParsedSheet
from app.services.answer_service import AnswerService, build_evidence, build_retry_prompt, build_user_prompt, parse_llm_json
from app.services.exceptions import AnswerGenerationError


class FakeRetrievalService:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, str, int | None]] = []

    def search(self, query: str, mode: str = "hybrid", top_k: int | None = None) -> SearchResponse:
        self.calls.append((query, mode, top_k))
        return self.response


class FakeOllamaClient:
    def __init__(self, response: str | list[str]) -> None:
        self.responses = response if isinstance(response, list) else [response]
        self.prompts: list[tuple[str, str]] = []
        self.status = type("Status", (), {"server_available": True, "model_available": True})()

    def check_status(self):
        return self.status

    def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        self.prompts.append((system_prompt, user_prompt))
        index = min(len(self.prompts) - 1, len(self.responses) - 1)
        return self.responses[index]


def _settings(tmp_path) -> Settings:
    settings = Settings(
        app_env="test",
        data_dir=tmp_path / "data",
        log_level="INFO",
        ollama_host="http://127.0.0.1:11434",
        retrieval_top_k=2,
    )
    settings.ensure_directories()
    return settings


def _document() -> Document:
    return Document(
        id="DOC-1",
        original_name="rules.xlsx",
        stored_path="uploads/DOC-1/document.xlsx",
        file_hash="hash",
        file_size_bytes=100,
        version=None,
        effective_date=None,
        revised_date=None,
        department=None,
        is_latest=True,
        status="COMPLETED",
        error_message=None,
        uploaded_at=datetime(2026, 1, 1, 10, 0, 0),
        parsed_at=datetime(2026, 1, 1, 10, 1, 0),
    )


def _chunk(chunk_id: str = "DOC-1-S001-C0000", content: str = "Apply three days before leave.") -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        document_id="DOC-1",
        sheet_id="DOC-1-S001",
        sheet_name="Leave",
        cell_start="A1",
        cell_end="B2",
        cell_range="A1:B2",
        cell_refs=("A1", "B2"),
        row_start=1,
        row_end=2,
        section=None,
        article="Article 8",
        paragraph=None,
        title="Annual leave",
        content=content,
        chunk_index=0,
        content_hash="hash-c",
        created_at=datetime(2026, 1, 1),
    )


def _seed(settings: Settings) -> None:
    document = _document()
    chunk = _chunk()
    DocumentRepository(settings.database_path).create(document)
    ExtractionRepository(settings.database_path).replace_extraction(
        document.id,
        [ParsedSheet("DOC-1-S001", document.id, "Leave", 0, "visible", 2, 2, 2, 0, datetime(2026, 1, 1))],
        [ParsedCell("CELL-1", document.id, "DOC-1-S001", "Leave", "A1", 1, 1, "string", "Article 8", None, None, None, False, False)],
        [chunk],
    )


def _search_response(results: list[SearchResult]) -> SearchResponse:
    return SearchResponse(
        query="leave",
        mode="hybrid",
        results=results,
        requested_top_k=2,
        elapsed_time_ms=1,
        keyword_candidate_count=len(results),
        vector_candidate_count=len(results),
        searched_document_ids=("DOC-1",),
    )


def _result(chunk_id: str = "DOC-1-S001-C0000") -> SearchResult:
    chunk = _chunk(chunk_id)
    return SearchResult(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        original_name="model-must-not-use.xlsx",
        version=None,
        sheet_name="FakeSheet",
        section=None,
        article=chunk.article,
        title=chunk.title,
        content=chunk.content,
        cell_range="Z9:Z9",
        cell_refs=("Z9",),
        keyword_score=1.0,
        vector_score=1.0,
        final_score=0.5,
        matched_by=("keyword", "vector"),
        rank=1,
    )


def test_prompt_contains_only_evidence_fields() -> None:
    prompt = build_user_prompt("question", build_evidence([_result()]))

    assert "E1" in prompt
    assert "Apply three days before leave." in prompt
    assert "Preserve supported numbers" in prompt
    assert "model-must-not-use.xlsx" not in prompt
    assert "FakeSheet" not in prompt
    assert "Z9:Z9" not in prompt
    assert "expected_answer" not in prompt
    assert "required_fact" not in prompt


def test_answer_validates_ids_and_uses_sqlite_sources(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed(settings)
    ollama = FakeOllamaClient(json.dumps({"answer": "Use the rule.", "insufficient_evidence": False, "used_evidence_ids": ["E1"], "reason": ""}))
    service = AnswerService(settings, FakeRetrievalService(_search_response([_result()])), ollama_client=ollama)

    response = service.answer("leave")

    assert response.answer == "Use the rule."
    assert response.verified_sources[0].original_name == "rules.xlsx"
    assert response.verified_sources[0].sheet_name == "Leave"
    assert response.verified_sources[0].cell_range == "A1:B2"


def test_code_fenced_json_is_parsed() -> None:
    payload = parse_llm_json('```json\n{"answer":"ok","insufficient_evidence":false,"used_evidence_ids":["E1"],"reason":""}\n```')

    assert payload["answer"] == "ok"


def test_retry_prompt_does_not_include_raw_response() -> None:
    prompt = build_retry_prompt("question", build_evidence([_result()]), "INVALID_JSON")

    assert "INVALID_JSON" in prompt
    assert "{bad" not in prompt


def test_malformed_json_is_rejected() -> None:
    with pytest.raises(AnswerGenerationError) as exc_info:
        parse_llm_json("{bad")

    assert exc_info.value.code == "INVALID_JSON"


def test_answer_retries_once_for_malformed_json(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed(settings)
    ollama = FakeOllamaClient([
        "{bad",
        json.dumps({"answer": "Use the rule.", "insufficient_evidence": False, "used_evidence_ids": ["E1"], "reason": ""}),
    ])
    service = AnswerService(settings, FakeRetrievalService(_search_response([_result()])), ollama_client=ollama)

    response = service.answer("leave")

    assert response.answer == "Use the rule."
    assert len(ollama.prompts) == 2
    assert "{bad" not in ollama.prompts[1][1]


def test_unknown_evidence_id_is_rejected(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed(settings)
    ollama = FakeOllamaClient(json.dumps({"answer": "Bad cite.", "insufficient_evidence": False, "used_evidence_ids": ["E9"], "reason": ""}))
    service = AnswerService(settings, FakeRetrievalService(_search_response([_result()])), ollama_client=ollama)

    with pytest.raises(AnswerGenerationError) as exc_info:
        service.answer("leave")

    assert exc_info.value.code == "INVALID_EVIDENCE_ID"
    assert len(ollama.prompts) == 2


def test_unknown_evidence_id_can_be_retried_with_valid_id(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed(settings)
    ollama = FakeOllamaClient([
        json.dumps({"answer": "Bad cite.", "insufficient_evidence": False, "used_evidence_ids": ["E9"], "reason": ""}),
        json.dumps({"answer": "Use the rule.", "insufficient_evidence": False, "used_evidence_ids": ["E1", "E1"], "reason": ""}),
    ])
    service = AnswerService(settings, FakeRetrievalService(_search_response([_result()])), ollama_client=ollama)

    response = service.answer("leave")

    assert [item.evidence_id for item in response.used_evidence] == ["E1"]
    assert len(ollama.prompts) == 2


def test_no_evidence_does_not_call_ollama(tmp_path) -> None:
    settings = _settings(tmp_path)
    ollama = FakeOllamaClient("{}")
    service = AnswerService(settings, FakeRetrievalService(_search_response([])), ollama_client=ollama)

    response = service.answer("unknown")

    assert response.insufficient_evidence
    assert response.error_code == "NO_EVIDENCE"
    assert ollama.prompts == []


def test_weak_evidence_is_refused_before_ollama_call(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed(settings)
    ollama = FakeOllamaClient(json.dumps({"answer": "Invented answer.", "insufficient_evidence": False, "used_evidence_ids": ["E1"], "reason": ""}))
    service = AnswerService(settings, FakeRetrievalService(_search_response([_result()])), ollama_client=ollama)

    response = service.answer("사내 주차장 배정 기준은 무엇인가요?")

    assert response.insufficient_evidence
    assert response.error_code == "INSUFFICIENT_EVIDENCE"
    assert response.used_evidence == []
    assert response.verified_sources == []
    assert response.sufficiency is not None
    assert response.sufficiency.confidence_level == "LOW"
    assert ollama.prompts == []


def test_answer_retries_and_falls_back_to_grounded_sentence_for_incomplete_answer(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed(settings)
    result = _result()
    result = SearchResult(
        result.chunk_id,
        result.document_id,
        result.original_name,
        result.version,
        result.sheet_name,
        result.section,
        result.article,
        result.title,
        "Annual leave must be requested three business days before the planned start date.",
        result.cell_range,
        result.cell_refs,
        result.keyword_score,
        result.vector_score,
        result.final_score,
        result.matched_by,
        result.rank,
    )
    ollama = FakeOllamaClient(
        [
            json.dumps({"answer": "3", "insufficient_evidence": False, "used_evidence_ids": ["E1"], "reason": ""}),
            json.dumps({"answer": "3", "insufficient_evidence": False, "used_evidence_ids": ["E1"], "reason": ""}),
        ]
    )
    service = AnswerService(settings, FakeRetrievalService(_search_response([result])), ollama_client=ollama)

    response = service.answer("연차는 며칠 전에 신청해야 하나요?")

    assert "three business days" in response.answer
    assert response.generation_retry_count == 1
    assert response.generation_mode == "evidence_only_fallback"
    assert response.fallback_used is True
    assert len(ollama.prompts) == 2


def test_supported_evidence_retries_model_false_refusal_then_refuses(tmp_path) -> None:
    settings = _settings(tmp_path)
    _seed(settings)
    ollama = FakeOllamaClient(
        [
            json.dumps({"answer": "", "insufficient_evidence": True, "used_evidence_ids": [], "reason": "insufficient"}),
            json.dumps({"answer": "", "insufficient_evidence": True, "used_evidence_ids": [], "reason": "insufficient"}),
        ]
    )
    service = AnswerService(settings, FakeRetrievalService(_search_response([_result()])), ollama_client=ollama)

    response = service.answer("leave")

    assert response.insufficient_evidence is True
    assert response.answer == ""
    assert response.used_evidence == []
    assert response.generation_mode == "safe_refusal"
    assert response.fallback_used is False
    assert response.generation_retry_count == 1
