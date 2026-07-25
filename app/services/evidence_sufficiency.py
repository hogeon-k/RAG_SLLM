from __future__ import annotations

import re

from app.models.document import EvidenceSufficiencyResult, SearchResponse, SearchResult
from app.repositories.keyword_search_repository import extract_article_numbers


_LOW_REASON = {
    "NO_RELEVANT_EVIDENCE": "제공된 근거를 찾지 못해 답변을 생성할 수 없습니다.",
    "WEAK_VECTOR_ONLY_MATCH": "질문에 답하기에는 검색된 근거가 충분하지 않습니다.",
    "LEXICAL_COVERAGE_TOO_LOW": "질문과 검색된 근거의 핵심 표현이 충분히 맞지 않습니다.",
    "SOURCE_HINT_MISMATCH": "질문에서 요구한 조항이나 출처와 맞는 근거를 찾지 못했습니다.",
    "VERSION_INTENT_MISMATCH": "질문에서 요구한 현행/이전 규정 의도와 근거가 맞지 않습니다.",
    "AMBIGUOUS_EVIDENCE": "검색된 근거가 여러 규정으로 갈려 명확한 답변을 생성하기 어렵습니다.",
    "ADVERSARIAL_INSTRUCTION": "근거를 무시하거나 시스템 정보를 요구하는 질문에는 답변할 수 없습니다.",
    "PROMPT_INJECTION": "시스템 지시나 내부 정보를 요청하는 질문에는 답변할 수 없습니다.",
}


def assess_evidence_sufficiency(question: str, retrieval: SearchResponse) -> EvidenceSufficiencyResult:
    results = retrieval.results
    if not results:
        return _result(False, "LOW", "NO_RELEVANT_EVIDENCE", None, False, False, 0.0, None, False, True, False, 0)

    attack_reason = _attack_reason(question)
    if attack_reason:
        best = results[0]
        return _result(
            False,
            "LOW",
            attack_reason,
            best,
            "keyword" in best.matched_by,
            _exact_article_hit(question, best),
            _lexical_coverage(question, best),
            best.vector_score,
            _source_hint_match(question, best),
            _version_intent_match(question, best),
            _conflicting_evidence(results),
            len(results),
        )

    best = results[0]
    keyword_hit = "keyword" in best.matched_by
    vector_hit = "vector" in best.matched_by
    exact_article_hit = _exact_article_hit(question, best)
    source_hint_match = _source_hint_match(question, best)
    lexical_coverage = _lexical_coverage(question, best)
    vector_similarity = best.vector_score
    version_intent_match = _version_intent_match(question, best)
    conflicting = _conflicting_evidence(results)
    phrase_hit = _strong_phrase_hit(question, best)
    cross_supported = keyword_hit and vector_hit
    has_source_hint = _has_source_hint(question)

    if not version_intent_match:
        reason_code = "VERSION_INTENT_MISMATCH"
        return _result(False, "LOW", reason_code, best, keyword_hit, exact_article_hit, lexical_coverage, vector_similarity, source_hint_match, False, conflicting, len(results))
    if has_source_hint and not (source_hint_match or exact_article_hit or phrase_hit):
        reason_code = "SOURCE_HINT_MISMATCH"
        return _result(False, "LOW", reason_code, best, keyword_hit, exact_article_hit, lexical_coverage, vector_similarity, source_hint_match, version_intent_match, conflicting, len(results))
    if conflicting and not (exact_article_hit or phrase_hit):
        reason_code = "AMBIGUOUS_EVIDENCE"
        return _result(False, "LOW", reason_code, best, keyword_hit, exact_article_hit, lexical_coverage, vector_similarity, source_hint_match, version_intent_match, conflicting, len(results))
    if _domain_hint_mismatch(question, best):
        reason_code = "LEXICAL_COVERAGE_TOO_LOW"
        return _result(False, "LOW", reason_code, best, keyword_hit, exact_article_hit, lexical_coverage, vector_similarity, source_hint_match, version_intent_match, conflicting, len(results))

    if exact_article_hit or phrase_hit or (cross_supported and lexical_coverage >= 0.34) or (keyword_hit and lexical_coverage >= 0.5):
        return _result(True, "HIGH", "STRONG_EVIDENCE", best, keyword_hit, exact_article_hit, lexical_coverage, vector_similarity, source_hint_match, version_intent_match, conflicting, len(results))
    if cross_supported and lexical_coverage >= 0.22:
        return _result(True, "MEDIUM", "SUPPORTED_EVIDENCE", best, keyword_hit, exact_article_hit, lexical_coverage, vector_similarity, source_hint_match, version_intent_match, conflicting, len(results))
    if cross_supported and (vector_similarity or 0.0) >= 0.85:
        return _result(True, "MEDIUM", "CROSS_RETRIEVAL_SUPPORT", best, keyword_hit, exact_article_hit, lexical_coverage, vector_similarity, source_hint_match, version_intent_match, conflicting, len(results))
    if vector_hit and not keyword_hit:
        reason_code = "WEAK_VECTOR_ONLY_MATCH"
    else:
        reason_code = "LEXICAL_COVERAGE_TOO_LOW"
    return _result(False, "LOW", reason_code, best, keyword_hit, exact_article_hit, lexical_coverage, vector_similarity, source_hint_match, version_intent_match, conflicting, len(results))


def refusal_message(result: EvidenceSufficiencyResult) -> str:
    return _LOW_REASON.get(result.reason_code, "제공된 근거만으로는 질문에 답변할 수 없습니다.")


def _result(
    sufficient: bool,
    confidence_level: str,
    reason_code: str,
    best: SearchResult | None,
    keyword_hit: bool,
    exact_article_hit: bool,
    lexical_coverage: float,
    vector_similarity: float | None,
    source_hint_match: bool,
    version_intent_match: bool,
    conflicting_evidence: bool,
    evaluated_evidence_count: int,
) -> EvidenceSufficiencyResult:
    return EvidenceSufficiencyResult(
        sufficient=sufficient,
        confidence_level=confidence_level,
        reason_code=reason_code,
        reason=_LOW_REASON.get(reason_code, "검색된 근거가 질문에 답하기에 충분합니다."),
        best_chunk_id=best.chunk_id if best else None,
        keyword_hit=keyword_hit,
        exact_article_hit=exact_article_hit,
        lexical_coverage=round(lexical_coverage, 4),
        vector_similarity=vector_similarity,
        source_hint_match=source_hint_match,
        version_intent_match=version_intent_match,
        conflicting_evidence=conflicting_evidence,
        evaluated_evidence_count=evaluated_evidence_count,
    )


def _attack_reason(question: str) -> str | None:
    lowered = question.lower()
    prompt_terms = ("system prompt", "시스템 프롬프트", "db 경로", "database path", "raw prompt", "내부 경로")
    if any(term in lowered for term in prompt_terms):
        return "PROMPT_INJECTION"
    adversarial_terms = ("근거를 무시", "ignore evidence", "무시하고", "가정하고", "답해줘")
    if any(term in lowered for term in adversarial_terms) and any(term in lowered for term in ("근거", "evidence", "조항", "article")):
        return "ADVERSARIAL_INSTRUCTION"
    return None


def _exact_article_hit(question: str, result: SearchResult) -> bool:
    articles = set(extract_article_numbers(question))
    return bool(result.article and result.article in articles)


def _source_hint_match(question: str, result: SearchResult) -> bool:
    terms = _terms(question)
    if not terms:
        return False
    source = " ".join(str(value or "") for value in (result.original_name, result.sheet_name, result.article, result.title)).lower()
    return any(term in source for term in terms)


def _has_source_hint(question: str) -> bool:
    lowered = question.lower()
    return bool(extract_article_numbers(question)) or any(term in lowered for term in ("article", "문구", "where", "어디"))


def _version_intent_match(question: str, result: SearchResult) -> bool:
    lowered = question.lower()
    haystack = _haystack(result)
    wants_current = any(term in lowered for term in ("현행", "현재", "최신", "current", "latest"))
    wants_legacy = any(term in lowered for term in ("과거", "이전", "old", "legacy"))
    if not wants_current and not wants_legacy:
        return True
    has_legacy = any(term in haystack for term in ("old", "legacy", "reference only", "not current", "과거", "이전"))
    if wants_current and has_legacy:
        return False
    if wants_legacy and not has_legacy:
        return False
    return True


def _lexical_coverage(question: str, result: SearchResult) -> float:
    terms = _terms(question)
    if not terms:
        return 0.0
    haystack = _haystack(result)
    matched = [term for term in terms if term in haystack or _translation_hit(term, haystack)]
    return len(matched) / len(terms)


def _strong_phrase_hit(question: str, result: SearchResult) -> bool:
    lowered = question.lower().strip()
    haystack = _haystack(result)
    quoted = re.findall(r"[A-Za-z][A-Za-z0-9, _%\\-]*(?:\s+[A-Za-z0-9, _%\\-]+){2,}", lowered)
    return any(phrase.strip() and phrase.strip() in haystack for phrase in quoted)


def _conflicting_evidence(results: list[SearchResult]) -> bool:
    top = results[:3]
    if len(top) < 2:
        return False
    source_keys = {(item.original_name, item.sheet_name, item.article, item.title) for item in top}
    if len(source_keys) <= 1:
        return False
    close_scores = max(item.final_score for item in top) - min(item.final_score for item in top) <= 0.08
    return close_scores and not any("keyword" in item.matched_by for item in top[:1])


def _terms(text: str) -> list[str]:
    terms: list[str] = []
    for raw in re.findall(r"[0-9A-Za-z가-힣_%\\]+", text.lower()):
        term = _strip_particle(raw)
        if len(term) < 2 or term in _STOPWORDS:
            continue
        if term not in terms:
            terms.append(term)
    return terms


def _strip_particle(term: str) -> str:
    for suffix in ("해야", "해야하나요", "하나요", "인가요", "인가", "에서", "으로", "에게", "까지", "에는", "전에", "은", "는", "이", "가", "을", "를", "과", "와", "의"):
        if len(term) > len(suffix) + 1 and term.endswith(suffix):
            return term[: -len(suffix)]
    return term


def _translation_hit(term: str, haystack: str) -> bool:
    aliases = {
        "주차장": ("parking",),
        "주차": ("parking",),
        "배정": ("allocation", "assigned"),
        "학비": ("tuition",),
        "차량": ("car", "vehicle"),
        "세차": ("wash",),
        "출장": ("travel", "trip", "business trip"),
        "연차": ("annual", "leave", "vacation"),
        "신청": ("request", "requested"),
        "며칠": ("days",),
        "전": ("before", "in advance"),
        "긴급": ("emergency", "urgent"),
        "재택": ("remote", "work"),
        "보안": ("security",),
        "문서": ("document", "record"),
        "계약": ("contract",),
        "승인": ("approval", "approved"),
        "영수증": ("receipt", "receipts"),
        "보고서": ("report",),
        "비밀번호": ("password",),
        "특수문자": ("special character", "%", "_", "backslash"),
    }
    return any(alias in haystack for alias in aliases.get(term, ()))


def _domain_hint_mismatch(question: str, result: SearchResult) -> bool:
    terms = [term for term in _terms(question) if term in _DOMAIN_HINT_TERMS]
    if not terms:
        return False
    haystack = _haystack(result)
    return not any(term in haystack or _translation_hit(term, haystack) for term in terms)


def _haystack(result: SearchResult) -> str:
    return " ".join(
        str(value or "")
        for value in (
            result.original_name,
            result.version,
            result.sheet_name,
            result.section,
            result.article,
            result.title,
            result.content,
        )
    ).lower()


_STOPWORDS = {
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

_DOMAIN_HINT_TERMS = {
    "주차장",
    "주차",
    "배정",
    "학비",
    "차량",
    "세차",
    "출장",
    "연차",
    "긴급",
    "재택",
    "보안",
    "문서",
    "계약",
    "승인",
    "영수증",
    "보고서",
    "비밀번호",
    "특수문자",
}
