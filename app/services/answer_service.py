from __future__ import annotations

import json
import re
import time
from typing import Any

from app.config.settings import Settings
from app.models.document import AnswerResponse, Evidence, SearchResponse, SearchResult, VerifiedSource
from app.repositories.document_repository import DocumentRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.services.exceptions import AnswerGenerationError, RetrievalError
from app.services.ollama_client import OllamaClient
from app.services.retrieval_service import RetrievalService


SYSTEM_PROMPT = """You answer only from the supplied evidence.
If one or more supplied evidence items directly answer the question, answer from those items and cite their IDs.
If the supplied evidence does not answer the question, return insufficient_evidence=true.
You may translate English evidence into Korean.
Do not invent file names, sheet names, cell ranges, paths, or sources.
Return only JSON. Do not use Markdown fences.
Only include evidence IDs that were supplied in used_evidence_ids.
Write the answer in Korean.
Separate action items or exceptions when the evidence explicitly supports them."""


class AnswerService:
    def __init__(
        self,
        settings: Settings,
        retrieval_service: RetrievalService,
        ollama_client: OllamaClient | None = None,
        document_repository: DocumentRepository | None = None,
        extraction_repository: ExtractionRepository | None = None,
    ) -> None:
        self._settings = settings
        self._retrieval = retrieval_service
        self._ollama = ollama_client or OllamaClient(settings)
        self._documents = document_repository or DocumentRepository(settings.database_path)
        self._extraction = extraction_repository or ExtractionRepository(settings.database_path)

    def answer(self, question: str, mode: str = "hybrid") -> AnswerResponse:
        started = time.perf_counter()
        cleaned = " ".join(question.strip().split())
        if not cleaned:
            raise AnswerGenerationError("EMPTY_QUESTION", "Please enter a question.")

        try:
            retrieval = self._retrieval.search(cleaned, mode=mode, top_k=self._settings.retrieval_top_k)
        except RetrievalError:
            raise
        except Exception as exc:
            raise AnswerGenerationError("INTERNAL_ERROR", "Search failed before answer generation.") from exc

        evidences = build_evidence(retrieval.results)
        if not evidences:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return AnswerResponse(
                question=cleaned,
                answer="",
                insufficient_evidence=True,
                reason="No evidence was found for the question.",
                used_evidence=[],
                verified_sources=[],
                retrieval=retrieval,
                generation_succeeded=False,
                elapsed_time_ms=elapsed_ms,
                error_code="NO_EVIDENCE",
            )

        status = self._ollama.check_status()
        if not status.server_available:
            raise AnswerGenerationError("OLLAMA_UNAVAILABLE", "Ollama server is unavailable.")
        if not status.model_available:
            raise AnswerGenerationError("OLLAMA_MODEL_NOT_FOUND", "Configured Ollama model was not found.")

        evidence_by_id = {item.evidence_id: item for item in evidences}
        answer_text, insufficient, reason, used_ids, action_items, exceptions = self._generate_validated_payload(cleaned, evidences, evidence_by_id)

        unique_used_ids = _dedupe_preserve_order(used_ids)
        if not insufficient and not unique_used_ids:
            raise AnswerGenerationError("INVALID_RESPONSE_SCHEMA", "The model did not cite any evidence.")
        if insufficient:
            unique_used_ids = []

        used_evidence = [evidence_by_id[evidence_id] for evidence_id in unique_used_ids]
        verified_sources = self._verified_sources(used_evidence)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return AnswerResponse(
            question=cleaned,
            answer=answer_text,
            insufficient_evidence=insufficient,
            reason=reason,
            used_evidence=used_evidence,
            verified_sources=verified_sources,
            retrieval=retrieval,
            generation_succeeded=not insufficient,
            elapsed_time_ms=elapsed_ms,
            action_items=tuple(action_items),
            exceptions=tuple(exceptions),
        )

    def _generate_validated_payload(
        self,
        question: str,
        evidences: list[Evidence],
        evidence_by_id: dict[str, Evidence],
    ) -> tuple[str, bool, str, list[str], list[str], list[str]]:
        prompt = build_user_prompt(question, evidences)
        last_error: AnswerGenerationError | None = None
        for attempt in range(2):
            try:
                raw_response = self._ollama.generate_json(SYSTEM_PROMPT, prompt)
                payload = parse_llm_json(raw_response)
                validated = validate_llm_payload(payload)
                invalid_ids = [item for item in validated[3] if item not in evidence_by_id]
                if invalid_ids:
                    raise AnswerGenerationError("INVALID_EVIDENCE_ID", "The model returned an unknown evidence ID.")
                return validated
            except AnswerGenerationError as exc:
                last_error = exc
                if attempt == 1 or not _is_retryable_generation_error(exc):
                    raise
                prompt = build_retry_prompt(question, evidences, exc.code)
        if last_error:
            raise last_error
        raise AnswerGenerationError("INVALID_RESPONSE_SCHEMA", "The model response schema is invalid.")

    def _verified_sources(self, evidences: list[Evidence]) -> list[VerifiedSource]:
        if not evidences:
            return []
        chunks = {chunk.id: chunk for chunk in self._extraction.get_chunks_by_ids([item.chunk_id for item in evidences])}
        sources: list[VerifiedSource] = []
        for evidence in evidences:
            chunk = chunks.get(evidence.chunk_id)
            if chunk is None:
                raise AnswerGenerationError("STALE_EVIDENCE", "A cited evidence chunk is no longer available.")
            document = self._documents.get_by_id(chunk.document_id)
            if document is None:
                raise AnswerGenerationError("STALE_EVIDENCE", "A cited evidence document is no longer available.")
            sources.append(
                VerifiedSource(
                    evidence.evidence_id,
                    chunk.id,
                    chunk.document_id,
                    document.original_name,
                    chunk.sheet_name,
                    chunk.article,
                    chunk.title,
                    chunk.cell_range,
                    chunk.cell_refs,
                    chunk.content,
                    True,
                )
            )
        return sources


def build_evidence(results: list[SearchResult]) -> list[Evidence]:
    return [
        Evidence(
            evidence_id=f"E{index}",
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            rank=result.rank,
            retrieval_score=result.final_score,
            article=result.article,
            title=result.title,
            content=result.content,
        )
        for index, result in enumerate(results, 1)
    ]


def build_user_prompt(question: str, evidences: list[Evidence]) -> str:
    evidence_payload = [
        {
            "evidence_id": evidence.evidence_id,
            "article": evidence.article or "",
            "title": evidence.title or "",
            "content": evidence.content,
        }
        for evidence in evidences
    ]
    schema = {
        "answer": "string",
        "action_items": ["string"],
        "exceptions": ["string"],
        "insufficient_evidence": False,
        "used_evidence_ids": ["E1"],
        "reason": "string",
    }
    return (
        "Question:\n"
        f"{question}\n\n"
        "Evidence:\n"
        f"{json.dumps(evidence_payload, ensure_ascii=False)}\n\n"
        "Use only the evidence IDs listed above. If an evidence item contains the requested fact in English, translate it into Korean.\n"
        "Return JSON with this schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}"
    )


def build_retry_prompt(question: str, evidences: list[Evidence], error_code: str) -> str:
    return (
        build_user_prompt(question, evidences)
        + "\n\n"
        "The previous model output failed validation with this error code only:\n"
        f"{error_code}\n"
        "Regenerate one valid JSON object that exactly follows the schema. "
        "Use only the supplied evidence IDs. Do not include Markdown, explanations, paths, or source labels."
    )


def parse_llm_json(raw_response: str) -> dict[str, Any]:
    text = raw_response.strip()
    if not text:
        raise AnswerGenerationError("OLLAMA_EMPTY_RESPONSE", "Ollama returned an empty response.")
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnswerGenerationError("INVALID_JSON", "The model response was not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise AnswerGenerationError("INVALID_RESPONSE_SCHEMA", "The model response JSON must be an object.")
    return payload


def validate_llm_payload(payload: dict[str, Any]) -> tuple[str, bool, str, list[str], list[str], list[str]]:
    answer = payload.get("answer")
    insufficient = payload.get("insufficient_evidence")
    used_ids = payload.get("used_evidence_ids")
    reason = payload.get("reason", "")
    action_items = payload.get("action_items", [])
    exceptions = payload.get("exceptions", [])
    if not isinstance(answer, str) or not isinstance(insufficient, bool) or not isinstance(used_ids, list):
        raise AnswerGenerationError("INVALID_RESPONSE_SCHEMA", "The model response schema is invalid.")
    if not isinstance(reason, str):
        raise AnswerGenerationError("INVALID_RESPONSE_SCHEMA", "The model response reason must be a string.")
    if not _is_string_list(used_ids) or not _is_string_list(action_items) or not _is_string_list(exceptions):
        raise AnswerGenerationError("INVALID_RESPONSE_SCHEMA", "The model response arrays must contain only strings.")
    if not insufficient and not answer.strip():
        raise AnswerGenerationError("INVALID_RESPONSE_SCHEMA", "The model response is missing an answer.")
    return answer.strip(), insufficient, reason.strip(), list(used_ids), list(action_items), list(exceptions)


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _is_retryable_generation_error(exc: AnswerGenerationError) -> bool:
    return exc.code in {
        "OLLAMA_EMPTY_RESPONSE",
        "INVALID_JSON",
        "INVALID_RESPONSE_SCHEMA",
        "INVALID_EVIDENCE_ID",
    }
