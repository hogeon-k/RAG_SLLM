from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import Settings
from app.services.document_extraction_service import DocumentExtractionService
from app.services.document_service import DocumentService
from app.services.retrieval_service import RetrievalService
from app.services.search_index_service import SearchIndexService


FIXTURE = PROJECT_ROOT / "data" / "test_workbooks" / "goal2_regulations_fixture.xlsx"


def main() -> int:
    if not FIXTURE.exists():
        print("Run scripts/generate_goal2_test_workbooks.py first.")
        return 1
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        root = Path(temp_dir)
        settings = Settings(
            app_env="test",
            data_dir=root / "data",
            log_level="INFO",
            ollama_host="http://127.0.0.1:11434",
            embedding_model="intfloat/multilingual-e5-small",
            embedding_device="auto",
            vector_collection="goal3_smoke",
        )
        settings.ensure_directories()
        source = root / "fixture.xlsx"
        shutil.copy2(FIXTURE, source)
        try:
            document = DocumentService(settings).register_document(source)
            DocumentExtractionService(settings).extract_document(document.id)
            index_result = SearchIndexService(settings).index_document(document.id)
            response = RetrievalService(settings).search("연차휴가는 며칠 전에 신청해야 하나", mode="hybrid", top_k=3)
        except Exception as exc:
            print("Real model smoke test was not completed.")
            print(f"Reason: {exc}")
            print("This can happen when the Hugging Face model is not downloaded or network access is unavailable.")
            return 0

        print(f"Index status: {index_result.status}, vectors: {index_result.vector_count}")
        for result in response.results:
            print(f"{result.rank}. {result.sheet_name} {result.article or ''} {result.title or ''} {result.cell_range} score={result.final_score:.3f}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
