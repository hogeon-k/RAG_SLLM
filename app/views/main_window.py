from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from app.config.settings import Settings
from app.repositories.database_repository import DatabaseRepository
from app.services.document_service import DocumentService
from app.services.question_service import QuestionService
from app.viewmodels.document_viewmodel import DocumentViewModel
from app.viewmodels.question_viewmodel import QuestionViewModel
from app.views.document_view import DocumentView
from app.views.history_view import HistoryView
from app.views.question_view import QuestionView
from app.views.settings_view import SettingsView


class MainWindow(QMainWindow):
    MENU_LABELS = ("질의응답", "문서 관리", "질문 이력", "시스템 설정")

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.setWindowTitle("업무 RAG 규정 검색")
        self.resize(1200, 760)

        database_repository = DatabaseRepository(settings.database_path)
        question_service = QuestionService(database_repository)
        document_service = DocumentService()

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(180)
        self.sidebar.setSpacing(4)

        for label in self.MENU_LABELS:
            item = QListWidgetItem(label)
            item.setSizeHint(QSize(160, 44))
            self.sidebar.addItem(item)

        self.stack = QStackedWidget()
        self.stack.setObjectName("content_stack")
        self.stack.addWidget(QuestionView(QuestionViewModel(question_service)))
        self.stack.addWidget(DocumentView(DocumentViewModel(document_service)))
        self.stack.addWidget(HistoryView())
        self.stack.addWidget(SettingsView(settings))

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #f7f7f5; }
            QListWidget {
                background: #ffffff;
                border: 1px solid #d8d8d2;
                border-radius: 6px;
                padding: 6px;
            }
            QListWidget::item {
                border-radius: 4px;
                padding: 8px 10px;
            }
            QListWidget::item:selected {
                background: #254f4a;
                color: #ffffff;
            }
            QLabel {
                color: #242623;
                font-size: 18px;
            }
            """
        )
        self.stack.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

