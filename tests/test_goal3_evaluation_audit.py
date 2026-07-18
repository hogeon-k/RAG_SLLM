from __future__ import annotations

from scripts.evaluate_goal3_retrieval import evaluate


def test_goal3_retrieval_audit_keeps_original7_and_extended8_separate() -> None:
    result = evaluate()

    assert result["question_sets"]["original7"]["question_count"] == 7
    assert result["question_sets"]["extended8"]["question_count"] == 8
    assert result["question_sets"]["extended8"]["unanswerable_count"] == 1

    index = result["index"]
    assert index["chunk_count"] == 16
    assert index["fts_count"] == index["chunk_count"]
    assert index["vector_count_after_index"] == index["chunk_count"]
    assert index["duplicate_vector_id_count"] == 0
    assert index["index_status"] == "READY"

    for mode in ("keyword", "vector", "hybrid"):
        original = result["metrics"][mode]["original7"]
        assert original["denominator"] == 7
        assert original["recall_at_1"] == 1.0
        assert original["recall_at_3"] == 1.0
        assert original["recall_at_5"] == 1.0

    extended_hybrid = result["metrics"]["hybrid"]["extended8_including_unanswerable"]
    assert extended_hybrid["denominator"] == 8
    assert extended_hybrid["hit_count_at_5"] == 7
    assert extended_hybrid["recall_at_5"] == 0.875

    trace = result["legacy_0_875_trace"]
    assert trace["search_mode"] == "hybrid"
    assert trace["k"] == 5
    assert trace["numerator"] == 7
    assert trace["denominator"] == 8
    assert trace["failed_question_id"] == "G3-X01"

    rows = {row["question_id"]: row for row in result["cases"]}
    assert rows["G3-X01"]["failure_reason"] == "unanswerable_probe_not_part_of_original_goal3_recall"
