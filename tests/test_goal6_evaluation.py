from __future__ import annotations

import argparse
import json

from scripts.run_goal6_evaluation import generate_goal6_fixtures, run_evaluation, validate_manifest


def test_goal6_fixture_manifest_schema(tmp_path) -> None:
    manifest_path = generate_goal6_fixtures(tmp_path / "fixtures")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    validate_manifest(manifest)
    assert len(manifest["documents"]) >= 3
    assert len(manifest["questions"]) >= 30
    assert {question["split"] for question in manifest["questions"]} >= {"dev", "test"}
    assert sum(1 for question in manifest["questions"] if not question["answerable"]) >= 6


def test_goal6_retrieval_evaluation_creates_reports(tmp_path) -> None:
    args = argparse.Namespace(
        mode="retrieval-only",
        split="dev",
        search_mode="hybrid",
        fixture_dir=tmp_path / "fixtures",
        output_dir=tmp_path / "reports",
        limit=4,
        question_id=None,
        fail_on_threshold=False,
    )

    result = run_evaluation(args)

    assert result["question_count"] == 4
    assert result["chunk_count"] > 0
    assert result["fts_count"] == result["chunk_count"]
    assert result["vector_count"] == result["chunk_count"]
    assert "recall_at_5" in result["retrieval"]["hybrid"]
    assert list((tmp_path / "reports").glob("*.json"))
    assert list((tmp_path / "reports").glob("*.md"))


def test_goal61_hybrid_retrieval_thresholds(tmp_path) -> None:
    args = argparse.Namespace(
        mode="retrieval-only",
        split="test",
        search_mode="hybrid",
        fixture_dir=tmp_path / "fixtures",
        output_dir=tmp_path / "reports",
        limit=None,
        question_id=None,
        fail_on_threshold=True,
    )

    result = run_evaluation(args)
    hybrid = result["retrieval"]["hybrid"]

    assert hybrid["recall_at_3"] >= 0.85
    assert hybrid["recall_at_5"] >= 0.90
    assert hybrid["category"]["exact_article"]["recall_at_1"] == 1.0
    assert hybrid["duplicate_chunk_result_count"] == 0


def test_goal6_fake_answer_evaluation_is_deterministic(tmp_path) -> None:
    args = argparse.Namespace(
        mode="fake-answer",
        split="dev",
        search_mode="hybrid",
        fixture_dir=tmp_path / "fixtures",
        output_dir=tmp_path / "reports",
        limit=6,
        question_id=None,
        fail_on_threshold=False,
    )

    result = run_evaluation(args)

    assert result["answer"]["json_parse_success_rate"] == 1.0
    assert result["answer"]["schema_success_rate"] == 1.0
    assert result["answer"]["sqlite_source_verification_rate"] == 1.0
    assert result["answer"]["required_fact_rate"] == 1.0
    assert result["answer"]["all_required_facts_success_rate"] == 1.0
    assert result["answer"]["forbidden_fact_detected_count"] == 0
    assert result["answer"]["manual_review_count"] == 0
    assert result["answer"]["invalid_evidence_accepted_count"] == 0
    assert result["answer"]["prompt_or_raw_response_saved"] is False
    assert result["answer"]["ollama_calls_when_no_results"] == 0
    assert "answerability_confusion_matrix" in result["answer"]
    assert "false_refusal_rate" in result["answer"]
    assert "pre_generation_refusal_count" in result["answer"]
    assert "sufficiency_reason_counts" in result["answer"]
    assert "model_call_avoided_count" in result["answer"]
    assert "evidence_only_fallback_count" in result["answer"]
    assert "fallback_false_answer_count" in result["answer"]
    assert "required_fact_rate_given_answer" in result["answer"]
    assert "end_to_end_required_fact_rate" in result["answer"]
    assert "normal_generation_required_fact_rate" in result["answer"]


def test_goal6_question_id_filter(tmp_path) -> None:
    args = argparse.Namespace(
        mode="retrieval-only",
        split="all",
        search_mode="keyword",
        fixture_dir=tmp_path / "fixtures",
        output_dir=tmp_path / "reports",
        limit=None,
        question_id="Q001",
        fail_on_threshold=False,
    )

    result = run_evaluation(args)

    assert result["question_count"] == 1
