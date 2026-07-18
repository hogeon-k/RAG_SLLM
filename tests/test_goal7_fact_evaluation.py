from __future__ import annotations

import pytest

from scripts.goal7_fact_evaluation import evaluate_answer_facts, fact_group, normalize_fact_text, validate_fact_groups


def test_fact_alias_matches_korean_english_and_numbers() -> None:
    question = {
        "question_id": "Q-G7",
        "answerable": True,
        "required_fact_groups": [
            fact_group("deadline", ["three business days", "3 영업일", "3영업일"]),
            fact_group("amount", ["30000 KRW", "30,000원", "30000원"]),
        ],
        "forbidden_fact_groups": [fact_group("old_deadline", ["five days in advance"])],
    }

    result = evaluate_answer_facts(question, "사용 예정일 3영업일 전에 신청하고 한도는 30,000원입니다.", False)

    assert result.required_fact_rate == 1.0
    assert result.matched_fact_ids == ["deadline", "amount"]
    assert result.missing_fact_ids == []
    assert result.forbidden_fact_pass is True


def test_fact_evaluation_detects_partial_coverage_and_forbidden_fact() -> None:
    question = {
        "question_id": "Q-G7",
        "answerable": True,
        "required_fact_groups": [
            fact_group("deadline", ["three business days"]),
            fact_group("system", ["HR system"]),
        ],
        "forbidden_fact_groups": [fact_group("old_deadline", ["five days"])],
    }

    result = evaluate_answer_facts(question, "신청은 three business days 전이며 five days 규정은 현행입니다.", False)

    assert result.required_fact_rate == 0.5
    assert result.missing_fact_ids == ["system"]
    assert result.forbidden_fact_ids == ["old_deadline"]
    assert result.manual_review_required is True


def test_fact_evaluation_does_not_force_required_facts_for_abstention() -> None:
    question = {
        "question_id": "Q-G7",
        "answerable": False,
        "required_fact_groups": [fact_group("deadline", ["three business days"])],
    }

    result = evaluate_answer_facts(question, "", True)

    assert result.required_fact_total == 0
    assert result.required_fact_rate == 1.0
    assert result.manual_review_required is False


def test_fact_validation_rejects_empty_alias_and_conflicts() -> None:
    with pytest.raises(ValueError):
        validate_fact_groups([{"question_id": "Q1", "required_fact_groups": [fact_group("x", [""])]}])

    with pytest.raises(ValueError):
        validate_fact_groups(
            [
                {
                    "question_id": "Q2",
                    "required_fact_groups": [fact_group("required", ["30,000원"])],
                    "forbidden_fact_groups": [fact_group("forbidden", ["30000원"])],
                }
            ]
        )


def test_normalize_fact_text_keeps_negation_distinct() -> None:
    assert normalize_fact_text("가능") != normalize_fact_text("불가능")
    assert normalize_fact_text("필요") != normalize_fact_text("불필요")


def test_english_alias_matches_when_korean_particle_is_attached() -> None:
    question = {
        "question_id": "Q-G7",
        "answerable": True,
        "required_fact_groups": [fact_group("same_day", ["same day"])],
    }

    result = evaluate_answer_facts(question, "same day에 신청할 수 있습니다.", False)

    assert result.required_fact_rate == 1.0
    assert result.matched_fact_ids == ["same_day"]
