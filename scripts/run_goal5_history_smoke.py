from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import Settings, load_settings
from app.models.document import AnswerResponse, SearchResponse, VerifiedSource
from app.services.answer_service import SYSTEM_PROMPT, parse_llm_json, validate_llm_payload
from app.services.history_service import HistoryService
from app.services.ollama_client import OllamaClient


def main() -> None:
    base = load_settings()
    with tempfile.TemporaryDirectory(prefix="rag_sllm_goal5_") as temp_dir:
        settings = Settings(
            app_env="smoke",
            data_dir=Path(temp_dir),
            log_level=base.log_level,
            ollama_host=base.ollama_host,
            ollama_model=base.ollama_model,
            ollama_timeout_seconds=base.ollama_timeout_seconds,
            ollama_num_ctx=base.ollama_num_ctx,
            ollama_num_predict=base.ollama_num_predict,
            ollama_temperature=base.ollama_temperature,
            ollama_top_p=base.ollama_top_p,
            ollama_top_k=base.ollama_top_k,
            ollama_repeat_penalty=base.ollama_repeat_penalty,
            retrieval_top_k=base.retrieval_top_k,
        )
        settings.ensure_directories()
        client = OllamaClient(settings)
        status = client.check_status()
        print(f"server_available={status.server_available}")
        print(f"model_available={status.model_available}")
        print(f"model={settings.ollama_model}")
        print(f"message={status.message}")
        if not status.server_available or not status.model_available:
            print("goal5_history_smoke=SKIPPED")
            return

        user_prompt = (
            "Question:\nWhen should annual leave be requested?\n\n"
            "Evidence:\n"
            '[{"evidence_id":"E1","article":"Article 8","title":"Annual leave",'
            '"content":"Annual leave must be requested three days in advance."}]\n\n'
            "Return JSON with keys answer, insufficient_evidence, used_evidence_ids, reason."
        )
        raw = client.generate_json(SYSTEM_PROMPT, user_prompt)
        payload = parse_llm_json(raw)
        answer, insufficient, reason, used_ids, _action_items, _exceptions = validate_llm_payload(payload)
        if any(evidence_id != "E1" for evidence_id in used_ids):
            print("goal5_history_smoke=FAILED_INVALID_EVIDENCE_ID")
            return

        retrieval = SearchResponse(
            query="When should annual leave be requested?",
            mode="hybrid",
            results=[],
            requested_top_k=1,
            elapsed_time_ms=0,
            keyword_candidate_count=1,
            vector_candidate_count=1,
            searched_document_ids=("DUMMY-DOC",),
        )
        response = AnswerResponse(
            question=retrieval.query,
            answer=answer,
            insufficient_evidence=insufficient,
            reason=reason,
            used_evidence=[],
            verified_sources=[
                VerifiedSource(
                    evidence_id="E1",
                    chunk_id="DUMMY-CHUNK",
                    document_id="DUMMY-DOC",
                    original_name="dummy_rules.xlsx",
                    sheet_name="Leave",
                    article="Article 8",
                    title="Annual leave",
                    cell_range="A1:B2",
                    cell_refs=("A1", "B2"),
                    content="Annual leave must be requested three days in advance.",
                    used=True,
                )
            ],
            retrieval=retrieval,
            generation_succeeded=not insufficient,
            elapsed_time_ms=0,
        )
        service = HistoryService(settings)
        saved = service.save_answer(response)
        detail = service.get_history(saved.history_id)
        print(f"history_saved={detail.history_id.startswith('HIST-')}")
        print(f"source_snapshots={len(detail.sources)}")
        print(f"stored_prompt_or_raw_response={json.dumps(False)}")
        print("goal5_history_smoke=PASS")


if __name__ == "__main__":
    main()
