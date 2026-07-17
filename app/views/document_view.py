from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.viewmodels.document_viewmodel import DocumentViewModel


class DocumentView(QWidget):
    def __init__(self, view_model: DocumentViewModel) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel(view_model.description())
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)

