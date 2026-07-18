from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import Settings
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.keyword_search_repository import KeywordSearchRepository
from app.services.document_extraction_service import DocumentExtractionService
from app.services.document_service import DocumentService
from app.services.retrieval_service import RetrievalService
from app.services.search_index_service import SearchIndexService
from app.storage.vector_storage import ChromaVectorRepository


FIXTURE = PROJECT_ROOT / "data" / "test_workbooks" / "goal2_regulations_fixture.xlsx"


class FakeEmbeddingService:
    model_name = "fake-e5"

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        return [_vector(text) for text in texts]

    def encode_query(self, query: str) -> list[float]:
        return _vector(query)

    def get_dimension(self) -> int:
        return 5

    def get_model_fingerprint(self) -> str:
        return "fake-goal3-fingerprint"


def _vector(text: str) -> list[float]:
    features = [
        3.0 if "연차" in text or "휴가" in text else 0.1,
        3.0 if "긴급" in text or "당일" in text else 0.1,
        3.0 if "출장" in text or "영수증" in text or "보고서" in text else 0.1,
        3.0 if "시행일" in text or "문서정보" in text else 0.1,
        1.0,
    ]
    norm = math.sqrt(sum(value * value for value in features))
    return [value / norm for value in features]


CASES = [
    {"query": "제8조", "expected_sheet": "휴가규정", "expected_article": "제8조"},
    {"query": "연차휴가 며칠 전에 신청해야 하나", "expected_sheet": "휴가규정", "expected_article": "제8조"},
    {"query": "휴가신청서는 어디서 작성하나", "expected_sheet": "휴가규정", "expected_article": "제8조"},
    {"query": "긴급한 사유가 있으면 당일 신청 가능한가", "expected_sheet": "휴가규정", "expected_article": "제8조의2"},
    {"query": "출장 때 필요한 서류는 무엇인가", "expected_sheet": "출장규정", "expected_article": "제3조"},
    {"query": "영수증과 출장보고서", "expected_sheet": "출장규정", "expected_article": "제4조"},
    {"query": "문서 시행일", "expected_sheet": "문서정보", "expected_article": None},
    {"query": "존재하지 않는 구내식당 주차 규정", "expected_sheet": None, "expected_article": None},
]

ORIGINAL_GOAL3_CASE_COUNT = 7
SEARCH_MODES = ("keyword", "vector", "hybrid")


def evaluate() -> dict[str, object]:
    if not FIXTURE.exists():
        raise SystemExit("Run scripts/generate_goal2_test_workbooks.py first.")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        root = Path(temp_dir)
        settings = Settings(
            app_env="test",
            data_dir=root / "data",
            log_level="INFO",
            ollama_host="http://127.0.0.1:11434",
            embedding_model="fake-e5",
            vector_collection="goal3_eval",
        )
        settings.ensure_directories()
        source = root / "fixture.xlsx"
        shutil.copy2(FIXTURE, source)
        document = DocumentService(settings).register_document(source)
        DocumentExtractionService(settings).extract_document(document.id)
        chunks = ExtractionRepository(settings.database_path).list_chunks(document.id)
        embedding = FakeEmbeddingService()
        vector = ChromaVectorRepository(settings.vector_db_dir, "goal3_eval", embedding.get_model_fingerprint())
        vector_count_before_index = vector.count_document(document.id)
        index_result = SearchIndexService(settings, embedding_service=embedding, vector_repository=vector).index_document(document.id)
        fts_count = KeywordSearchRepository(settings.database_path).count(document.id)
        vector_count = vector.count_document(document.id)
        vector_ids = vector._collection.get(where={"document_id": document.id}, include=[]).get("ids", [])
        retrieval = RetrievalService(settings, embedding_service=embedding, vector_repository=vector)

        started_all = time.perf_counter()
        mode_results = {mode: _evaluate_mode(retrieval, mode) for mode in SEARCH_MODES}
        hybrid_original = mode_results["hybrid"]["metrics"]["original7"]
        legacy_hybrid = mode_results["hybrid"]["metrics"]["extended8_including_unanswerable"]
        rows = _merge_case_rows(mode_results)
        hit_at_1 = hybrid_original["hit_count_at_1"]
        hit_at_3 = hybrid_original["hit_count_at_3"]
        hit_at_5 = hybrid_original["hit_count_at_5"]
        total = hybrid_original["denominator"]
        legacy_total = legacy_hybrid["denominator"]
        legacy_hit_at_5 = legacy_hybrid["hit_count_at_5"]
        return {
            "question_sets": {
                "original7": {
                    "description": "Goal 3 original answerable questions.",
                    "question_count": total,
                },
                "extended8": {
                    "description": "Original 7 plus one unanswerable smoke probe.",
                    "question_count": legacy_total,
                    "unanswerable_count": legacy_total - total,
                },
            },
            "index": {
                "chunk_count": len(chunks),
                "fts_count": fts_count,
                "vector_count_before_index": vector_count_before_index,
                "vector_count_after_index": vector_count,
                "duplicate_vector_id_count": len(vector_ids) - len(set(vector_ids)),
                "index_status": index_result.status,
                "index_fts_count": index_result.fts_count,
                "index_vector_count": index_result.vector_count,
            },
            "settings": {
                "top_k": 5,
                "embedding_model": settings.embedding_model,
                "embedding_device": settings.embedding_device,
                "keyword_candidate_k": settings.keyword_candidate_k,
                "vector_candidate_k": settings.vector_candidate_k,
                "keyword_weight": settings.keyword_weight,
                "vector_weight": settings.vector_weight,
            },
            "metrics": {mode: result["metrics"] for mode, result in mode_results.items()},
            "cases": rows,
            "legacy_0_875_trace": {
                "meaning": "Old script divided seven original hits by all eight CASES, including the unanswerable probe.",
                "search_mode": "hybrid",
                "k": 5,
                "numerator": legacy_hit_at_5,
                "denominator": legacy_total,
                "calculation": f"{legacy_hit_at_5} / {legacy_total} = {legacy_hit_at_5 / legacy_total:.3f}",
                "failed_question_id": "G3-X01",
            },
            "recall_at_1": hit_at_1 / total,
            "recall_at_3": hit_at_3 / total,
            "recall_at_5": hit_at_5 / total,
            "elapsed_ms": int((time.perf_counter() - started_all) * 1000),
            "note": "FakeEmbeddingService 기반 평가입니다. 실제 모델 성능 보장이 아닙니다.",
        }


def _evaluate_mode(retrieval: RetrievalService, mode: str) -> dict[str, object]:
    rows = []
    for index, case in enumerate(CASES, 1):
        question_id = f"G3-{index:02d}" if index <= ORIGINAL_GOAL3_CASE_COUNT else "G3-X01"
        started = time.perf_counter()
        response = retrieval.search(case["query"], mode=mode, top_k=5)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        ranks = [
            rank + 1
            for rank, result in enumerate(response.results)
            if _matches(result, case["expected_sheet"], case["expected_article"])
        ]
        rank = ranks[0] if ranks else None
        rows.append(
            {
                "question_id": question_id,
                "question": case["query"],
                "set": "original7" if index <= ORIGINAL_GOAL3_CASE_COUNT else "extended_unanswerable",
                "expected_source": {
                    "sheet": case["expected_sheet"],
                    "article": case["expected_article"],
                },
                "rank": rank,
                "hit_at_1": bool(rank and rank <= 1),
                "hit_at_3": bool(rank and rank <= 3),
                "hit_at_5": bool(rank and rank <= 5),
                "top5": [_source_summary(result) for result in response.results[:5]],
                "elapsed_ms": elapsed_ms,
                "failure_reason": _failure_reason(case, rank),
            }
        )
    return {
        "metrics": {
            "original7": _metrics(rows[:ORIGINAL_GOAL3_CASE_COUNT]),
            "extended8_including_unanswerable": _metrics(rows),
        },
        "rows": rows,
    }


def _metrics(rows: list[dict[str, object]]) -> dict[str, object]:
    denominator = len(rows)
    hit_at_1 = sum(1 for row in rows if row["hit_at_1"])
    hit_at_3 = sum(1 for row in rows if row["hit_at_3"])
    hit_at_5 = sum(1 for row in rows if row["hit_at_5"])
    return {
        "denominator": denominator,
        "hit_count_at_1": hit_at_1,
        "hit_count_at_3": hit_at_3,
        "hit_count_at_5": hit_at_5,
        "recall_at_1": hit_at_1 / denominator,
        "recall_at_3": hit_at_3 / denominator,
        "recall_at_5": hit_at_5 / denominator,
    }


def _merge_case_rows(mode_results: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for index in range(len(CASES)):
        keyword = mode_results["keyword"]["rows"][index]
        vector = mode_results["vector"]["rows"][index]
        hybrid = mode_results["hybrid"]["rows"][index]
        rows.append(
            {
                "question_id": hybrid["question_id"],
                "question": hybrid["question"],
                "set": hybrid["set"],
                "expected_source": hybrid["expected_source"],
                "keyword_rank": keyword["rank"],
                "vector_rank": vector["rank"],
                "hybrid_rank": hybrid["rank"],
                "keyword_hit": keyword["hit_at_5"],
                "vector_hit": vector["hit_at_5"],
                "hybrid_hit": hybrid["hit_at_5"],
                "actual_top5": {
                    "keyword": keyword["top5"],
                    "vector": vector["top5"],
                    "hybrid": hybrid["top5"],
                },
                "failure_reason": hybrid["failure_reason"],
            }
        )
    return rows


def _source_summary(result) -> dict[str, object]:
    return {
        "rank": result.rank,
        "sheet": result.sheet_name,
        "article": result.article,
        "title": result.title,
        "cell_range": result.cell_range,
    }


def _failure_reason(case: dict[str, object], rank: int | None) -> str | None:
    if rank:
        return None
    if case["expected_sheet"] is None:
        return "unanswerable_probe_not_part_of_original_goal3_recall"
    return "expected_source_not_in_top5"


def _matches(result, expected_sheet: str | None, expected_article: str | None) -> bool:
    if expected_sheet is None:
        return False
    return result.sheet_name == expected_sheet and (expected_article is None or result.article == expected_article)


def main() -> int:
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
