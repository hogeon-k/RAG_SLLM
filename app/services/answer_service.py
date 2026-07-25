from __future__ import annotations

import json
import logging
import re
import time
import inspect
from typing import Any

from app.config.settings import Settings
from app.models.document import AnswerResponse, Evidence, SearchResponse, SearchResult, VerifiedSource
from app.repositories.document_repository import DocumentRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.services.evidence_sufficiency import assess_evidence_sufficiency, refusal_message
from app.services.exceptions import AnswerGenerationError, RetrievalError
from app.services.ollama_client import OllamaClient
from app.services.retrieval_service import RetrievalService


logger = logging.getLogger(__name__)


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

    def answer(self, question: str, mode: str = "hybrid", include_archived: bool = False) -> AnswerResponse:
        started = time.perf_counter()
        cleaned = " ".join(question.strip().split())
        if not cleaned:
            raise AnswerGenerationError("EMPTY_QUESTION", "Please enter a question.")

        try:
            retrieval = _call_retrieval_search(
                self._retrieval,
                cleaned,
                mode=mode,
                top_k=self._settings.retrieval_top_k,
                include_archived=include_archived,
            )
        except RetrievalError:
            raise
        except Exception as exc:
            raise AnswerGenerationError("INTERNAL_ERROR", "Search failed before answer generation.") from exc

        evidences = build_evidence(retrieval.results)
        sufficiency = assess_evidence_sufficiency(cleaned, retrieval)
        if not evidences:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return AnswerResponse(
                question=cleaned,
                answer="",
                insufficient_evidence=True,
                reason=refusal_message(sufficiency),
                used_evidence=[],
                verified_sources=[],
                retrieval=retrieval,
                generation_succeeded=False,
                elapsed_time_ms=elapsed_ms,
                error_code="NO_EVIDENCE",
                sufficiency=sufficiency,
                generation_mode="pre_generation_refusal",
            )

        if not sufficiency.sufficient:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return AnswerResponse(
                question=cleaned,
                answer="",
                insufficient_evidence=True,
                reason=refusal_message(sufficiency),
                used_evidence=[],
                verified_sources=[],
                retrieval=retrieval,
                generation_succeeded=False,
                elapsed_time_ms=elapsed_ms,
                error_code="INSUFFICIENT_EVIDENCE",
                sufficiency=sufficiency,
                generation_mode="pre_generation_refusal",
            )

        status = self._ollama.check_status()
        if not status.server_available:
            raise AnswerGenerationError("OLLAMA_UNAVAILABLE", "Ollama server is unavailable.")
        if not status.model_available:
            raise AnswerGenerationError("OLLAMA_MODEL_NOT_FOUND", "Configured Ollama model was not found.")

        evidence_by_id = {item.evidence_id: item for item in evidences}
        answer_text, insufficient, reason, used_ids, action_items, exceptions, retry_count, generation_mode = self._generate_validated_payload(cleaned, evidences, evidence_by_id)

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
            generation_retry_count=retry_count,
            sufficiency=sufficiency,
            generation_mode=generation_mode,
            fallback_used=generation_mode == "evidence_only_fallback",
        )

    def _generate_validated_payload(
        self,
        question: str,
        evidences: list[Evidence],
        evidence_by_id: dict[str, Evidence],
    ) -> tuple[str, bool, str, list[str], list[str], list[str], int, str]:
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
                quality_error = _quality_error(question, validated, evidence_by_id)
                if quality_error and attempt == 0:
                    prompt = build_retry_prompt(question, evidences, quality_error)
                    continue
                if quality_error and attempt == 1:
                    if quality_error == "EVIDENCE_AVAILABLE":
                        return _safe_refusal_payload("제공된 근거만으로는 질문에 답변할 수 없습니다.", attempt)
                    return (*_grounded_fallback_payload(question, validated, evidence_by_id), attempt, "evidence_only_fallback")
                return (*validated, attempt, "retry_success" if attempt else "normal")
            except AnswerGenerationError as exc:
                last_error = exc
                if attempt == 1 and exc.code == "EMPTY_ANSWER":
                    logger.info("answer.empty_answer_fallback")
                    return (*_grounded_fallback_payload(question, ("", False, "", [], [], []), evidence_by_id), attempt, "evidence_only_fallback")
                if attempt == 1 or not _is_retryable_generation_error(exc):
                    raise
                if exc.code == "EMPTY_ANSWER":
                    logger.info("answer.empty_answer_retry")
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


def _call_retrieval_search(retrieval, query: str, *, mode: str, top_k: int, include_archived: bool) -> SearchResponse:
    parameters = inspect.signature(retrieval.search).parameters
    if "include_archived" in parameters:
        return retrieval.search(query, mode=mode, top_k=top_k, include_archived=include_archived)
    return retrieval.search(query, mode=mode, top_k=top_k)


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
        "Answer every part of the question that is directly supported by evidence.\n"
        "Preserve supported numbers, units, deadlines, amounts, percentages, methods, approvers, conditions, and exceptions.\n"
        "For how many/how much/when/deadline questions, include the number and its unit exactly in meaning.\n"
        "If an evidence item says business days, do not shorten it to plain days.\n"
        "If evidence directly answers the question, do not return insufficient_evidence=true.\n"
        "Do not cite evidence that is only legacy/reference unless the question asks for old or archived rules.\n"
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
        "Use only the supplied evidence IDs. Do not include Markdown, explanations, paths, or source labels. "
        "If the error is ANSWER_INCOMPLETE, revise the answer to include all supported numbers, units, conditions, and exceptions. "
        "If the error is WRONG_EVIDENCE_SELECTION, choose the evidence item that best matches the question terms. "
        "If the error is UNREADABLE_ANSWER, answer again in clear Korean. "
        "If the error is EVIDENCE_AVAILABLE, use the supplied evidence when it directly answers the question."
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
        raise AnswerGenerationError("EMPTY_ANSWER", "The model response is missing an answer.")
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
        "EMPTY_ANSWER",
        "INVALID_EVIDENCE_ID",
    }


def _quality_error(
    question: str,
    validated: tuple[str, bool, str, list[str], list[str], list[str]],
    evidence_by_id: dict[str, Evidence],
) -> str | None:
    answer, insufficient, _reason, used_ids, _action_items, _exceptions = validated
    selected = [evidence_by_id[evidence_id] for evidence_id in used_ids if evidence_id in evidence_by_id]
    evidence_text = " ".join(item.content for item in selected) if selected else " ".join(item.content for item in evidence_by_id.values())
    if insufficient and evidence_text:
        return "EVIDENCE_AVAILABLE"
    if not insufficient and _looks_unreadable(answer):
        return "UNREADABLE_ANSWER"
    if not insufficient and _selected_evidence_mismatch(question, used_ids, evidence_by_id):
        return "WRONG_EVIDENCE_SELECTION"
    if not insufficient and _missing_supported_fact(question, answer, evidence_text):
        return "ANSWER_INCOMPLETE"
    return None


def _grounded_fallback_payload(
    question: str,
    validated: tuple[str, bool, str, list[str], list[str], list[str]],
    evidence_by_id: dict[str, Evidence],
) -> tuple[str, bool, str, list[str], list[str], list[str]]:
    _answer, insufficient, reason, used_ids, action_items, exceptions = validated
    selected_ids = [evidence_id for evidence_id in _dedupe_preserve_order(used_ids) if evidence_id in evidence_by_id]
    if (insufficient or not selected_ids) and evidence_by_id:
        selected_ids = [_best_fallback_evidence_id(question, evidence_by_id)]
    if not selected_ids:
        return validated
    fallback_id = _best_grounded_fallback_id(question, selected_ids, evidence_by_id)
    evidence = evidence_by_id[fallback_id]
    sentence = _best_content_sentence(question, evidence.content)
    if not sentence:
        return validated
    return f"근거에 따르면 {sentence}", False, reason, [fallback_id], action_items, exceptions


def _safe_refusal_payload(reason: str, retry_count: int) -> tuple[str, bool, str, list[str], list[str], list[str], int, str]:
    return "", True, reason, [], [], [], retry_count, "safe_refusal"


def _best_fallback_evidence_id(question: str, evidence_by_id: dict[str, Evidence]) -> str:
    ranked = sorted(
        evidence_by_id.values(),
        key=lambda evidence: (
            -_question_evidence_score(question, evidence),
            evidence.rank,
            evidence.evidence_id,
        ),
    )
    return ranked[0].evidence_id


def _best_grounded_fallback_id(question: str, selected_ids: list[str], evidence_by_id: dict[str, Evidence]) -> str:
    selected = {evidence_id: evidence_by_id[evidence_id] for evidence_id in selected_ids if evidence_id in evidence_by_id}
    selected_id = _best_fallback_evidence_id(question, selected) if selected else ""
    best_id = _best_fallback_evidence_id(question, evidence_by_id)
    if not selected_id:
        return best_id
    selected_score = _question_evidence_score(question, evidence_by_id[selected_id])
    best_score = _question_evidence_score(question, evidence_by_id[best_id])
    return best_id if best_score > selected_score + 0.5 else selected_id


def _best_content_sentence(question: str, content: str) -> str:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return ""
    terms = set(_fallback_terms(question))
    scored: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        lowered = line.lower()
        score = sum(1 for term in terms if term in lowered)
        if score:
            scored.append((score, -index, line))
    body = max(scored)[2] if scored else lines[-1]
    return re.split(r"(?<=[.!?。])\s+", body)[0].strip()


def _selected_evidence_mismatch(question: str, used_ids: list[str], evidence_by_id: dict[str, Evidence]) -> bool:
    selected = [evidence_by_id[evidence_id] for evidence_id in used_ids if evidence_id in evidence_by_id]
    if not selected or len(evidence_by_id) < 2:
        return False
    best_id = _best_fallback_evidence_id(question, evidence_by_id)
    best_score = _question_evidence_score(question, evidence_by_id[best_id])
    selected_score = max(_question_evidence_score(question, evidence) for evidence in selected)
    return best_score > selected_score + 0.5


def _question_evidence_score(question: str, evidence: Evidence) -> float:
    terms = _fallback_terms(question)
    haystack = " ".join(str(value or "") for value in (evidence.article, evidence.title, evidence.content)).lower()
    score = 0.0
    for term in terms:
        if term in haystack:
            score += 1.0
            continue
        aliases = _FALLBACK_TERM_ALIASES.get(term, ())
        if any(alias in haystack for alias in aliases):
            score += 1.2 if any(" " in alias and alias in haystack for alias in aliases) else 0.9
    return score + max(0.0, 1.0 - evidence.rank * 0.01)


def _fallback_terms(text: str) -> list[str]:
    terms: list[str] = []
    for raw in re.findall(r"[0-9A-Za-z가-힣_%\\]+", text.lower()):
        term = raw
        for suffix in ("해야", "해야하나요", "하나요", "인가요", "인가", "에서", "으로", "에게", "까지", "에는", "전에", "은", "는", "이", "가", "을", "를", "과", "와", "의"):
            if len(term) > len(suffix) + 1 and term.endswith(suffix):
                term = term[: -len(suffix)]
                break
        if len(term) >= 2 and term not in _FALLBACK_STOPWORDS and term not in terms:
            terms.append(term)
        for compound, parts in _FALLBACK_COMPOUND_TERMS.items():
            if compound in raw:
                for part in parts:
                    if part not in terms:
                        terms.append(part)
    return terms


def _first_content_sentence(content: str) -> str:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return ""
    body = lines[-1]
    parts = re.split(r"(?<=[.!?。])\s+", body)
    return parts[0].strip()


def _question_expects_concrete_fact(question: str) -> bool:
    lowered = question.lower()
    markers = (
        "몇",
        "얼마",
        "언제",
        "기한",
        "까지",
        "무엇",
        "조건",
        "예외",
        "규칙",
        "규정",
        "긴급",
        "휴가",
        "문자",
        "서류",
        "제출",
        "보고서",
        "비교",
        "내용",
        "어디",
        "문구",
        "조항",
        "what",
        "when",
        "where",
        "article",
        "how many",
        "how much",
    )
    return any(marker in lowered for marker in markers)


def _looks_unreadable(answer: str) -> bool:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣]", "", answer)
    if len(cleaned) < 5:
        cjk = re.findall(r"[\u4e00-\u9fff]", answer)
        hangul = re.findall(r"[가-힣]", answer)
        latin = re.findall(r"[A-Za-z]", answer)
        return len(cjk) >= 2 and not hangul and not latin
    cjk = re.findall(r"[\u4e00-\u9fff]", answer)
    hangul = re.findall(r"[가-힣]", answer)
    latin = re.findall(r"[A-Za-z]", answer)
    if len(cjk) >= 2 and not hangul and not latin:
        return True
    evidence_words = ("신청", "제출", "승인", "보고", "보관", "영업", "당일", "이내", "가능", "필요", "제한")
    hangul_syllables = re.findall(r"[가-힣]", cleaned)
    return bool(hangul_syllables) and not any(word in answer for word in evidence_words) and not re.search(r"[0-9A-Za-z]", answer)


def _missing_supported_fact(question: str, answer: str, evidence_text: str) -> bool:
    if _missing_supported_unit(question, answer, evidence_text):
        return True
    if not _question_expects_concrete_fact(question):
        return False
    normalized_answer = answer.lower()
    normalized_evidence = evidence_text.lower()
    numeric_phrases = re.findall(
        r"\b(?:one|two|three|five|twelve|ninety|\d+)\s+(?:business\s+)?(?:days?|hours?|characters?|years?)\b|\b\d+\s*krw\b|\b\d+\s*%",
        normalized_evidence,
    )
    if numeric_phrases and not any(_phrase_or_number_in_answer(phrase, normalized_answer) for phrase in numeric_phrases):
        return True
    phrase_synonyms = {
        "same day": ("same day", "당일", "같은 날"),
        "team lead approval": ("team lead approval", "team leader approval", "팀장", "승인"),
        "receipts": ("receipts", "receipt", "영수증"),
        "trip report": ("trip report", "출장보고", "보고서"),
        "special character": ("special character", "특수문자", "percent", "%", "_", "backslash"),
    }
    for evidence_phrase, synonyms in phrase_synonyms.items():
        if evidence_phrase in normalized_evidence and not any(synonym.lower() in normalized_answer for synonym in synonyms):
            return True
    return False


def _missing_supported_unit(question: str, answer: str, evidence_text: str) -> bool:
    if re.search(r"\bbusiness days?\b", evidence_text, flags=re.IGNORECASE):
        if re.search(r"\b\d+\s*(?:business\s*)?days?\b|[0-9]+\s*일|며칠|언제|기한|까지|전", question, flags=re.IGNORECASE):
            return ("영업" not in answer) and not re.search(r"\bbusiness days?\b", answer, flags=re.IGNORECASE)
    return False


def _phrase_or_number_in_answer(phrase: str, answer: str) -> bool:
    if phrase in answer:
        return True
    word_numbers = {
        "one": "1",
        "two": "2",
        "three": "3",
        "five": "5",
        "twelve": "12",
        "ninety": "90",
    }
    converted = phrase
    for word, digit in word_numbers.items():
        converted = re.sub(rf"\b{word}\b", digit, converted)
    compact_answer = re.sub(r"\s+", "", answer)
    compact_converted = re.sub(r"\s+", "", converted)
    return compact_converted in compact_answer


_FALLBACK_TERM_ALIASES = {
    "연차": ("annual", "leave", "vacation"),
    "휴가": ("leave", "vacation"),
    "긴급": ("emergency", "urgent", "same day"),
    "긴급휴가": ("emergency", "urgent", "same day", "leave"),
    "급히": ("emergency", "urgent", "same day"),
    "당일": ("same day",),
    "출장": ("travel", "trip", "business trip"),
    "보고서": ("report", "trip report"),
    "출장보고서": ("trip report", "business trip report"),
    "영수증": ("receipt", "receipts"),
    "제출": ("submit", "submitted", "submission"),
    "기한": ("deadline", "before", "within", "days"),
    "신청": ("request", "requested"),
    "며칠": ("days",),
    "전": ("before", "in advance"),
    "재택": ("remote", "work"),
    "승인": ("approval", "approved"),
    "식대": ("meal", "dinner", "allowance"),
    "저녁": ("dinner", "meal"),
    "보안": ("security",),
    "비밀번호": ("password",),
    "특수문자": ("special character", "%", "_", "backslash"),
    "문서": ("document", "record"),
    "계약": ("contract",),
    "보관": ("retained", "retention", "preserve"),
    "초안": ("draft",),
    "삭제": ("delete", "deleted"),
}

_FALLBACK_COMPOUND_TERMS = {
    "출장보고서": ("출장", "보고서"),
    "긴급휴가": ("긴급", "휴가"),
    "비밀번호": ("보안",),
    "특수문자": ("문자",),
}

_FALLBACK_STOPWORDS = {
    "무엇",
    "어떻게",
    "알려줘",
    "내용",
    "규정",
    "기준",
    "가능한가요",
    "필요한가요",
    "있나요",
    "where",
    "what",
    "when",
    "how",
    "many",
    "much",
    "the",
    "must",
    "be",
    "is",
    "are",
    "to",
    "for",
}


def _fallback_terms(text: str) -> list[str]:
    terms: list[str] = []
    for raw in re.findall(r"[0-9A-Za-z가-힣%\\]+", text.lower()):
        term = raw
        for suffix in _KOREAN_SUFFIXES:
            if len(term) > len(suffix) + 1 and term.endswith(suffix):
                term = term[: -len(suffix)]
                break
        if len(term) >= 2 and term not in _FALLBACK_STOPWORDS and term not in terms:
            terms.append(term)
        for compound, parts in _FALLBACK_COMPOUND_TERMS.items():
            if compound in raw:
                for part in parts:
                    if part not in terms:
                        terms.append(part)
    return terms


def _question_expects_concrete_fact(question: str) -> bool:
    lowered = question.lower()
    markers = (
        "뭐",
        "무엇",
        "얼마",
        "언제",
        "기한",
        "까지",
        "조건",
        "예외",
        "규칙",
        "규정",
        "유형",
        "종류",
        "긴급",
        "휴가",
        "문자",
        "서류",
        "제출",
        "보고서",
        "비교",
        "내용",
        "어디",
        "문구",
        "조항",
        "what",
        "when",
        "where",
        "article",
        "how many",
        "how much",
    )
    return any(marker in lowered for marker in markers)


def _looks_unreadable(answer: str) -> bool:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣]", "", answer)
    cjk = re.findall(r"[\u4e00-\u9fff]", answer)
    hangul = re.findall(r"[가-힣]", answer)
    latin = re.findall(r"[A-Za-z]", answer)
    if len(cjk) >= 2 and not hangul and not latin:
        return True
    if len(cleaned) < 5:
        return False
    evidence_words = ("신청", "제출", "승인", "보고", "보관", "영업", "당일", "이내", "가능", "필요", "제한", "유형")
    return bool(hangul) and not any(word in answer for word in evidence_words) and not re.search(r"[0-9A-Za-z]", answer)


def _missing_supported_unit(question: str, answer: str, evidence_text: str) -> bool:
    if not re.search(r"\bbusiness days?\b", evidence_text, flags=re.IGNORECASE):
        return False
    expects_deadline = re.search(r"\b\d+\s*(?:business\s*)?days?\b|[0-9]+\s*일|언제|기한|까지|며칠", question, flags=re.IGNORECASE)
    if not expects_deadline:
        return False
    return ("영업" not in answer) and not re.search(r"\bbusiness days?\b", answer, flags=re.IGNORECASE)


_KOREAN_SUFFIXES = (
    "이어야",
    "이어야하나요",
    "하나요",
    "인가요",
    "인가",
    "에서",
    "으로",
    "에게",
    "까지",
    "부터",
    "에는",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "에",
    "와",
    "과",
    "의",
    "도",
    "만",
)

_FALLBACK_TERM_ALIASES = {
    "연차": ("annual", "leave", "vacation"),
    "휴가": ("leave", "vacation"),
    "긴급": ("emergency", "urgent", "same day"),
    "긴급휴가": ("emergency", "urgent", "same day", "leave"),
    "당일": ("same day",),
    "출장": ("travel", "trip", "business trip"),
    "보고서": ("report", "trip report"),
    "출장보고서": ("trip report", "business trip report"),
    "영수증": ("receipt", "receipts"),
    "제출": ("submit", "submitted", "submission"),
    "기한": ("deadline", "before", "within", "days"),
    "신청": ("request", "requested"),
    "며칠": ("days",),
    "전": ("before", "in advance"),
    "재택": ("remote", "work"),
    "승인": ("approval", "approved"),
    "식대": ("meal", "dinner", "allowance"),
    "저녁": ("dinner", "meal"),
    "보안": ("security",),
    "비밀번호": ("password",),
    "특수문자": ("special character", "%", "_", "backslash"),
    "문서": ("document", "record"),
    "계약": ("contract",),
    "보관": ("retained", "retention", "preserve"),
    "초안": ("draft",),
    "삭제": ("delete", "deleted"),
    "일반차로": ("general lane",),
    "하이패스": ("hi-pass", "hipass"),
    "위반": ("violation",),
    "유형": ("type",),
    "입구정보이상": ("entry information",),
    "출구정보이상": ("exit information",),
    "출구위반처리": ("exit violation",),
}

_FALLBACK_COMPOUND_TERMS = {
    "출장보고서": ("출장", "보고서"),
    "긴급휴가": ("긴급", "휴가"),
    "비밀번호": ("보안",),
    "특수문자": ("문자",),
    "일반차로": ("일반", "차로"),
    "위반유형": ("위반", "유형"),
}

_FALLBACK_STOPWORDS = {
    "무엇",
    "어떻게",
    "알려줘",
    "내용",
    "규정",
    "기준",
    "가능한가요",
    "필요한가요",
    "하나요",
    "where",
    "what",
    "when",
    "how",
    "many",
    "much",
    "the",
    "must",
    "be",
    "is",
    "are",
    "to",
    "for",
}
