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
from app.repositories.document_repository import DocumentRepository
from app.repositories.extraction_repository import ExtractionRepository
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
        embedding = FakeEmbeddingService()
        vector = ChromaVectorRepository(settings.vector_db_dir, "goal3_eval", embedding.get_model_fingerprint())
        SearchIndexService(settings, embedding_service=embedding, vector_repository=vector).index_document(document.id)
        retrieval = RetrievalService(settings, embedding_service=embedding, vector_repository=vector)

        rows = []
        hit_at_1 = hit_at_3 = hit_at_5 = 0
        started_all = time.perf_counter()
        for case in CASES:
            started = time.perf_counter()
            response = retrieval.search(case["query"], mode="hybrid", top_k=5)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            ranks = [
                index + 1
                for index, result in enumerate(response.results)
                if _matches(result, case["expected_sheet"], case["expected_article"])
            ]
            rank = ranks[0] if ranks else None
            hit_at_1 += 1 if rank and rank <= 1 else 0
            hit_at_3 += 1 if rank and rank <= 3 else 0
            hit_at_5 += 1 if rank and rank <= 5 else 0
            top = response.results[0] if response.results else None
            rows.append(
                {
                    "query": case["query"],
                    "expected_sheet": case["expected_sheet"],
                    "expected_article": case["expected_article"],
                    "rank": rank,
                    "top_sheet": top.sheet_name if top else None,
                    "top_article": top.article if top else None,
                    "top_cell_range": top.cell_range if top else None,
                    "elapsed_ms": elapsed_ms,
                }
            )
        total = len(CASES)
        return {
            "cases": rows,
            "recall_at_1": hit_at_1 / total,
            "recall_at_3": hit_at_3 / total,
            "recall_at_5": hit_at_5 / total,
            "elapsed_ms": int((time.perf_counter() - started_all) * 1000),
            "note": "FakeEmbeddingService 기반 평가입니다. 실제 모델 성능 보장이 아닙니다.",
        }


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
