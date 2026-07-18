from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FactEvaluation:
    required_fact_total: int
    matched_fact_ids: list[str]
    missing_fact_ids: list[str]
    forbidden_fact_ids: list[str]
    required_fact_rate: float
    forbidden_fact_pass: bool
    manual_review_required: bool
    manual_review_reason: str | None


def evaluate_answer_facts(question: dict[str, Any], answer: str, insufficient_evidence: bool) -> FactEvaluation:
    required_groups = _fact_groups(question, "required_fact_groups", "expected_answer_facts")
    forbidden_groups = _fact_groups(question, "forbidden_fact_groups", "forbidden_answer_facts")
    if not question.get("answerable") or insufficient_evidence:
        required_groups = []

    normalized_answer = normalize_fact_text(answer)
    matched: list[str] = []
    missing: list[str] = []
    for group in required_groups:
        fact_id = str(group["fact_id"])
        if _group_matches(normalized_answer, group):
            matched.append(fact_id)
        else:
            missing.append(fact_id)

    forbidden = [str(group["fact_id"]) for group in forbidden_groups if _group_matches(normalized_answer, group)]
    total = len(required_groups)
    manual = bool(missing or forbidden)
    if not question.get("answerable") and not insufficient_evidence:
        manual = True
    return FactEvaluation(
        required_fact_total=total,
        matched_fact_ids=matched,
        missing_fact_ids=missing,
        forbidden_fact_ids=forbidden,
        required_fact_rate=(len(matched) / total) if total else 1.0,
        forbidden_fact_pass=not forbidden,
        manual_review_required=manual,
        manual_review_reason=_manual_review_reason(question, insufficient_evidence, missing, forbidden),
    )


def validate_fact_groups(questions: list[dict[str, Any]]) -> None:
    for question in questions:
        seen: set[str] = set()
        for key in ("required_fact_groups", "forbidden_fact_groups"):
            for group in question.get(key, []):
                fact_id = str(group.get("fact_id", "")).strip()
                if not fact_id:
                    raise ValueError(f"Missing fact_id: {question.get('question_id')}")
                scoped_id = f"{key}:{fact_id}"
                if scoped_id in seen:
                    raise ValueError(f"Duplicate fact_id: {question.get('question_id')} {fact_id}")
                seen.add(scoped_id)
                aliases = group.get("aliases")
                if not isinstance(aliases, list) or not aliases or any(not str(alias).strip() for alias in aliases):
                    raise ValueError(f"Empty fact alias: {question.get('question_id')} {fact_id}")
        required_aliases = {
            normalize_fact_text(alias)
            for group in question.get("required_fact_groups", [])
            for alias in group.get("aliases", [])
        }
        forbidden_aliases = {
            normalize_fact_text(alias)
            for group in question.get("forbidden_fact_groups", [])
            for alias in group.get("aliases", [])
        }
        conflict = required_aliases & forbidden_aliases
        if conflict:
            raise ValueError(f"Conflicting fact alias: {question.get('question_id')} {sorted(conflict)[0]}")


def normalize_fact_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = normalized.replace("\u00a0", " ")
    normalized = re.sub(r"(\d),(\d)", r"\1\2", normalized)
    normalized = re.sub(r"(\d)\s+(?=(days?|business|hours?|characters?|years?|krw|%|원|일|시간|년|자|개))", r"\1", normalized)
    normalized = re.sub(r"\s+%", "%", normalized)
    normalized = re.sub(r"[%]", " percent ", normalized)
    normalized = re.sub(r"[()\[\]{}.,;:!?\"'`~]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def fact_group(fact_id: str, aliases: list[str], description: str | None = None, match: str = "any") -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "description": description or fact_id.replace("_", " "),
        "match": match,
        "aliases": aliases,
    }


def _fact_groups(question: dict[str, Any], group_key: str, legacy_key: str) -> list[dict[str, Any]]:
    groups = question.get(group_key)
    if groups:
        return list(groups)
    return [
        fact_group(_legacy_fact_id(legacy_key, index, value), [str(value)])
        for index, value in enumerate(question.get(legacy_key, []), 1)
    ]


def _legacy_fact_id(key: str, index: int, value: object) -> str:
    stem = re.sub(r"[^0-9a-zA-Z가-힣]+", "_", str(value).strip()).strip("_").lower()
    return f"{key}_{index}_{stem or 'fact'}"


def _group_matches(normalized_answer: str, group: dict[str, Any]) -> bool:
    aliases = [normalize_fact_text(str(alias)) for alias in group.get("aliases", [])]
    aliases = [alias for alias in aliases if alias]
    if not aliases:
        return False
    if group.get("match", "any") == "all":
        return all(_alias_matches(normalized_answer, alias) for alias in aliases)
    return any(_alias_matches(normalized_answer, alias) for alias in aliases)


def _alias_matches(normalized_answer: str, alias: str) -> bool:
    if not alias:
        return False
    pattern = r"(?<![0-9a-zA-Z가-힣])" + re.escape(alias) + r"(?![0-9a-zA-Z가-힣])"
    if re.search(pattern, normalized_answer):
        return True
    if re.search(r"[a-zA-Z]", alias) and alias in normalized_answer:
        return True
    return alias in normalized_answer if any(char.isdigit() for char in alias) else False


def _manual_review_reason(
    question: dict[str, Any],
    insufficient_evidence: bool,
    missing: list[str],
    forbidden: list[str],
) -> str | None:
    if not question.get("answerable") and not insufficient_evidence:
        return "unanswerable_question_received_answer"
    if forbidden:
        return "forbidden_fact_detected"
    if missing:
        return "required_fact_missing"
    return None
