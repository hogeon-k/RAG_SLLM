from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.models.document import HistoryListResult, QuestionHistory
from app.viewmodels.history_viewmodel import HistoryViewModel


class _HistoryPlaceholder(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel("이전에 질문과 답변을 확인하는 화면입니다.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)


class HistoryView(QWidget):
    HEADERS = ("created", "question", "status", "sources", "model", "duration")

    def __init__(self, view_model: HistoryViewModel) -> None:
        super().__init__()
        self._view_model = view_model
        self._histories: list[QuestionHistory] = []
        self._selected_id: str | None = None

        self.title = QLabel("Question History")
        self.title.setObjectName("page_title")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search question, answer, document, sheet, article, title")
        self.status_combo = QComboBox()
        self.status_combo.addItems(("", "SUCCESS", "INSUFFICIENT_EVIDENCE", "NO_EVIDENCE", "FAILED"))
        self.start_date_edit = QLineEdit()
        self.start_date_edit.setPlaceholderText("Start YYYY-MM-DD")
        self.end_date_edit = QLineEdit()
        self.end_date_edit.setPlaceholderText("End YYYY-MM-DD")
        self.refresh_button = QPushButton("Refresh")
        self.reset_button = QPushButton("Reset")
        self.delete_button = QPushButton("Delete Selected")
        self.delete_all_button = QPushButton("Delete All")
        self.status_label = QLabel("")
        self.status_label.setObjectName("status_label")

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(self.search_edit, 1)
        filter_layout.addWidget(self.status_combo)
        filter_layout.addWidget(self.start_date_edit)
        filter_layout.addWidget(self.end_date_edit)
        filter_layout.addWidget(self.refresh_button)
        filter_layout.addWidget(self.reset_button)
        filter_layout.addWidget(self.delete_button)
        filter_layout.addWidget(self.delete_all_button)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addLayout(filter_layout)
        layout.addWidget(self.status_label)
        layout.addWidget(self.table, 2)
        layout.addWidget(self.detail, 2)

        self.refresh_button.clicked.connect(self._load)
        self.search_edit.returnPressed.connect(self._load)
        self.start_date_edit.returnPressed.connect(self._load)
        self.end_date_edit.returnPressed.connect(self._load)
        self.status_combo.currentIndexChanged.connect(self._load)
        self.reset_button.clicked.connect(self._reset_filters)
        self.table.itemSelectionChanged.connect(self._load_selected_detail)
        self.delete_button.clicked.connect(self._delete_selected)
        self.delete_all_button.clicked.connect(self._delete_all)

        self._view_model.operation_started.connect(self._on_started)
        self._view_model.list_succeeded.connect(self._on_list_succeeded)
        self._view_model.detail_succeeded.connect(self._on_detail_succeeded)
        self._view_model.delete_succeeded.connect(self._on_delete_succeeded)
        self._view_model.operation_failed.connect(self._on_failed)
        self._view_model.operation_finished.connect(self._on_finished)
        self.delete_button.setEnabled(False)
        self.delete_all_button.setEnabled(False)

    def _load(self) -> None:
        if not self._view_model.load_histories(
            self.search_edit.text().strip(),
            self.status_combo.currentText(),
            self.start_date_edit.text().strip(),
            self.end_date_edit.text().strip(),
        ):
            self.status_label.setText("History operation is already running.")

    def _reset_filters(self) -> None:
        self.search_edit.clear()
        self.start_date_edit.clear()
        self.end_date_edit.clear()
        self.status_combo.setCurrentIndex(0)
        self._load()

    def _load_selected_detail(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._histories):
            self._selected_id = None
            self.delete_button.setEnabled(False)
            return
        self._selected_id = self._histories[row].history_id
        self.delete_button.setEnabled(True)
        self._view_model.load_detail(self._selected_id)

    def _delete_selected(self) -> None:
        if not self._selected_id:
            return
        history = self._histories[self.table.currentRow()]
        if QMessageBox.question(self, "Delete history", f"Delete this history?\n{history.created_at}\n{_short(history.question, 80)}") != QMessageBox.StandardButton.Yes:
            return
        self._view_model.delete_history(self._selected_id)

    def _delete_all(self) -> None:
        if not self._histories:
            return
        if QMessageBox.question(self, "Delete all histories", "Delete all question histories and source snapshots?") != QMessageBox.StandardButton.Yes:
            return
        self._view_model.delete_all()

    def _on_started(self) -> None:
        self.refresh_button.setEnabled(False)
        self.reset_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.delete_all_button.setEnabled(False)
        self.status_label.setText("Working...")

    def _on_finished(self) -> None:
        self.refresh_button.setEnabled(True)
        self.reset_button.setEnabled(True)
        self.delete_button.setEnabled(self._selected_id is not None)
        self.delete_all_button.setEnabled(bool(self._histories))

    def _on_list_succeeded(self, result: HistoryListResult) -> None:
        self._histories = result.items
        self.table.setRowCount(len(result.items))
        for row, history in enumerate(result.items):
            values = (
                history.created_at.isoformat(sep=" ", timespec="seconds"),
                _short(history.question, 80),
                history.status,
                str(history.used_evidence_count),
                history.ollama_model or "",
                f"{history.total_duration_ms}ms",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, history.history_id)
                self.table.setItem(row, column, item)
        self._selected_id = None
        self.detail.setPlainText("")
        self.status_label.setText(f"{len(result.items)} shown / {result.total_count} total")

    def _on_detail_succeeded(self, history: QuestionHistory) -> None:
        source_blocks = []
        for source in history.sources:
            source_blocks.append(
                "\n".join(
                    (
                        f"[{source.evidence_id}] {source.document_display_name}",
                        f"sheet: {source.sheet_name}",
                        f"article: {source.article or ''}",
                        f"title: {source.title or ''}",
                        f"cell_range: {source.cell_range}",
                        f"cell_refs: {', '.join(source.cell_refs)}",
                        f"content: {source.content}",
                    )
                )
            )
        self.detail.setPlainText(
            "\n".join(
                (
                    f"question:\n{history.question}",
                    "",
                    f"answer:\n{history.answer}",
                    "",
                    f"status: {history.status}",
                    f"error: {history.error_code or ''} {history.error_message or ''}".strip(),
                    f"search_mode: {history.search_mode}",
                    f"requested_top_k: {history.requested_top_k}",
                    f"retrieved_count: {history.retrieved_count}",
                    f"used_evidence_count: {history.used_evidence_count}",
                    f"model: {history.ollama_model or ''}",
                    f"duration: {history.total_duration_ms}ms",
                    "",
                    "verified source snapshots:",
                    "\n\n".join(source_blocks) if source_blocks else "none",
                )
            )
        )

    def _on_delete_succeeded(self, deleted_count: int) -> None:
        self.status_label.setText(f"Deleted {deleted_count} history row(s).")
        self._load()

    def _on_failed(self, message: str) -> None:
        QMessageBox.warning(self, "History error", message)


def _short(value: str, limit: int) -> str:
    cleaned = " ".join(value.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "..."
