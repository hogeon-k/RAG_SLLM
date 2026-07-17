from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.config.settings import Settings
from app.viewmodels.settings_viewmodel import SettingsViewModel


class _SettingsPlaceholder(QWidget):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        text = (
            "Ollama와 데이터 저장 설정을 확인하는 화면입니다.\n\n"
            f"환경: {settings.app_env}\n"
            f"데이터 경로: {settings.data_dir}\n"
            f"Ollama: {settings.ollama_host}"
        )
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)


class SettingsView(QWidget):
    def __init__(self, settings: Settings, view_model: SettingsViewModel | None = None) -> None:
        super().__init__()
        self._view_model = view_model
        layout = QVBoxLayout(self)
        text = (
            "System settings\n\n"
            f"environment: {settings.app_env}\n"
            f"data_dir: {settings.data_dir}\n"
            f"sqlite: {settings.database_path}\n"
            f"vector_db: {settings.vector_db_dir}\n"
            f"ollama_host: {settings.ollama_host}\n"
            f"ollama_model: {settings.ollama_model}\n"
            f"retrieval_top_k: {settings.retrieval_top_k}\n"
            f"keyword_weight: {settings.keyword_weight}\n"
            f"vector_weight: {settings.vector_weight}\n"
            f"timeout: {settings.ollama_timeout_seconds}\n"
            f"num_ctx: {settings.ollama_num_ctx}\n"
            f"num_predict: {settings.ollama_num_predict}\n"
            f"temperature: {settings.ollama_temperature}\n"
            f"embedding_model: {settings.embedding_model}\n"
            f"embedding_device: {settings.embedding_device}"
        )
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        self.status_button = QPushButton("Check Ollama Status")
        self.status_output = QTextEdit()
        self.status_output.setReadOnly(True)
        layout.addWidget(label)
        layout.addWidget(self.status_button)
        layout.addWidget(self.status_output)

        self.status_button.clicked.connect(self._check_status)
        if self._view_model is not None:
            self._view_model.status_started.connect(self._on_status_started)
            self._view_model.status_succeeded.connect(self._on_status_succeeded)
            self._view_model.status_failed.connect(self._on_status_failed)
            self._view_model.status_finished.connect(self._on_status_finished)

    def _check_status(self) -> None:
        if self._view_model is None:
            self.status_output.setPlainText("Status checker is not connected.")
            return
        if not self._view_model.check_status():
            self.status_output.setPlainText("Status check is already running.")

    def _on_status_started(self) -> None:
        self.status_button.setEnabled(False)
        self.status_output.setPlainText("Checking...")

    def _on_status_succeeded(self, status: dict) -> None:
        self.status_output.setPlainText(
            "\n".join(
                (
                    f"sqlite_ok={status.get('sqlite_ok')}",
                    f"server_available={status.get('server_available')}",
                    f"model_available={status.get('model_available')}",
                    f"message={status.get('message')}",
                )
            )
        )

    def _on_status_failed(self, message: str) -> None:
        self.status_output.setPlainText(message)

    def _on_status_finished(self) -> None:
        self.status_button.setEnabled(True)
