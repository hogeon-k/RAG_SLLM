from __future__ import annotations

import json

from app.config.settings import Settings
from app.services.ollama_client import OllamaClient


class _FakeHttpResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_ollama_generate_uses_schema_format_and_stream_false(tmp_path, monkeypatch) -> None:
    settings = Settings(app_env="test", data_dir=tmp_path / "data", log_level="INFO", ollama_host="http://ollama.local")
    settings.ensure_directories()
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeHttpResponse(
            {
                "done": True,
                "response": json.dumps(
                    {
                        "answer": "ok",
                        "action_items": [],
                        "exceptions": [],
                        "insufficient_evidence": False,
                        "used_evidence_ids": ["E1"],
                        "reason": "",
                    }
                ),
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    raw = OllamaClient(settings).generate_json("system", "user")

    payload = captured["payload"]
    assert json.loads(raw)["answer"] == "ok"
    assert payload["stream"] is False
    assert payload["format"]["type"] == "object"
    assert payload["format"]["additionalProperties"] is False
    assert "used_evidence_ids" in payload["format"]["required"]
