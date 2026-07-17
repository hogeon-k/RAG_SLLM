from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.config.settings import Settings
from app.services.exceptions import AnswerGenerationError


@dataclass(frozen=True)
class OllamaModelStatus:
    server_available: bool
    model_available: bool
    message: str


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def check_status(self) -> OllamaModelStatus:
        try:
            payload = self._request("/api/tags", {}, method="GET")
        except AnswerGenerationError as exc:
            return OllamaModelStatus(False, False, exc.user_message)
        models = payload.get("models")
        if not isinstance(models, list):
            return OllamaModelStatus(True, False, "Ollama returned an invalid model list.")
        model_names = {str(item.get("name", "")) for item in models if isinstance(item, dict)}
        if self._settings.ollama_model not in model_names:
            return OllamaModelStatus(True, False, "Configured Ollama model was not found.")
        return OllamaModelStatus(True, True, "Ollama model is available.")

    def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self._settings.ollama_model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "format": "json",
            "options": {
                "num_ctx": self._settings.ollama_num_ctx,
                "num_predict": self._settings.ollama_num_predict,
                "temperature": self._settings.ollama_temperature,
                "top_p": self._settings.ollama_top_p,
                "top_k": self._settings.ollama_top_k,
                "repeat_penalty": self._settings.ollama_repeat_penalty,
            },
        }
        response = self._request("/api/generate", payload)
        if response.get("done") is not True:
            raise AnswerGenerationError("OLLAMA_INCOMPLETE_RESPONSE", "Ollama response was incomplete.")
        text = response.get("response")
        if not isinstance(text, str) or not text.strip():
            raise AnswerGenerationError("OLLAMA_EMPTY_RESPONSE", "Ollama returned an empty response.")
        return text

    def _request(self, path: str, payload: dict, method: str = "POST") -> dict:
        data = None if method == "GET" else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self._settings.ollama_host}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self._settings.ollama_timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except TimeoutError as exc:
            raise AnswerGenerationError("OLLAMA_TIMEOUT", "Ollama request timed out.") from exc
        except socket.timeout as exc:
            raise AnswerGenerationError("OLLAMA_TIMEOUT", "Ollama request timed out.") from exc
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise AnswerGenerationError("OLLAMA_MODEL_NOT_FOUND", "Configured Ollama model was not found.") from exc
            raise AnswerGenerationError("OLLAMA_HTTP_ERROR", "Ollama returned an HTTP error.") from exc
        except urllib.error.URLError as exc:
            raise AnswerGenerationError("OLLAMA_UNAVAILABLE", "Ollama server is unavailable.") from exc
        if not body.strip():
            raise AnswerGenerationError("OLLAMA_EMPTY_RESPONSE", "Ollama returned an empty response.")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AnswerGenerationError("INVALID_JSON", "Ollama returned invalid JSON.") from exc
        if not isinstance(parsed, dict):
            raise AnswerGenerationError("INVALID_RESPONSE_SCHEMA", "Ollama returned an invalid response.")
        return parsed
