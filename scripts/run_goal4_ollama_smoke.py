from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import load_settings
from app.services.ollama_client import OllamaClient


def main() -> None:
    settings = load_settings()
    client = OllamaClient(settings)
    status = client.check_status()
    print(f"server_available={status.server_available}")
    print(f"model_available={status.model_available}")
    print(f"model={settings.ollama_model}")
    print(f"message={status.message}")
    if not status.server_available or not status.model_available:
        return
    response = client.generate_json(
        "Return only JSON with keys answer, insufficient_evidence, used_evidence_ids, reason.",
        (
            'Question: smoke test\n'
            'Evidence: [{"evidence_id":"E1","article":"","title":"Smoke","content":"Smoke test evidence."}]\n'
            'Return {"answer":"ok","insufficient_evidence":false,"used_evidence_ids":["E1"],"reason":""}.'
        ),
    )
    print(f"response_length={len(response)}")


if __name__ == "__main__":
    main()
