from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.config.settings import Settings


class SettingsView(QWidget):
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

