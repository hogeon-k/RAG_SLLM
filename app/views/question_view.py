from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
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

from app.models.document import AnswerResponse, SearchResult
from app.viewmodels.question_viewmodel import QuestionViewModel


class QuestionView(QWidget):
    HEADERS = ("순위", "문서", "시트", "조항", "제목", "셀 범위", "점수", "검색")

    def __init__(self, view_model: QuestionViewModel) -> None:
        super().__init__()
        self._view_model = view_model
        self._results: list[SearchResult] = []

        self.title = QLabel("질의응답")
        self.title.setObjectName("page_title")
        self.description = QLabel(view_model.description())
        self.description.setWordWrap(True)

        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText("검색할 규정 내용이나 조항 번호를 입력하세요")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(("hybrid", "keyword", "vector"))
        self.include_archived_check = QCheckBox("Include archived")
        self.search_button = QPushButton("검색")
        self.status_label = QLabel("")
        self.status_label.setObjectName("status_label")

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.query_edit, 1)
        search_layout.addWidget(self.mode_combo)
        search_layout.addWidget(self.include_archived_check)
        search_layout.addWidget(self.search_button)

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
        layout.addWidget(self.description)
        layout.addLayout(search_layout)
        layout.addWidget(self.status_label)
        layout.addWidget(self.table, 2)
        layout.addWidget(self.detail, 1)

        self.search_button.clicked.connect(self._search)
        self.query_edit.returnPressed.connect(self._search)
        self.table.itemSelectionChanged.connect(self._show_selected_result)
        self._view_model.answer_started.connect(self._on_answer_started)
        self._view_model.answer_succeeded.connect(self._on_answer_succeeded)
        self._view_model.answer_failed.connect(self._on_answer_failed)
        self._view_model.answer_finished.connect(self._on_answer_finished)

    def _search(self) -> None:
        query = self.query_edit.text().strip()
        mode = self.mode_combo.currentText()
        if not query:
            QMessageBox.information(self, "Question", "Please enter a question.")
            return
        if not self._view_model.start_answer(query, mode, include_archived=self.include_archived_check.isChecked()):
            QMessageBox.information(self, "Busy", "A question is already being processed.")
            return

    def _on_answer_started(self) -> None:
        self.search_button.setEnabled(False)
        self.query_edit.setEnabled(False)
        self.mode_combo.setEnabled(False)
        self.include_archived_check.setEnabled(False)
        self.status_label.setText("Answer generation is running.")

    def _on_answer_succeeded(self, response: AnswerResponse) -> None:
        self._results = response.retrieval.results
        self.table.setRowCount(len(response.retrieval.results))
        for row, result in enumerate(response.retrieval.results):
            values = (
                str(result.rank),
                result.original_name,
                result.sheet_name,
                result.article or "",
                result.title or "",
                result.cell_range,
                f"{result.final_score:.3f}",
                "+".join(result.matched_by),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, result.chunk_id)
                self.table.setItem(row, column, item)
        if response.insufficient_evidence:
            self.detail.setPlainText(f"Insufficient evidence.\n{response.reason}\n\n{_format_sources(response)}")
        else:
            sections = [response.answer]
            if response.action_items:
                sections.append("Action items:\n" + "\n".join(f"- {item}" for item in response.action_items))
            if response.exceptions:
                sections.append("Exceptions:\n" + "\n".join(f"- {item}" for item in response.exceptions))
            sections.append(_format_sources(response))
            self.detail.setPlainText("\n\n".join(section for section in sections if section))
        if response.retrieval.results:
            self.table.setCurrentCell(0, 0)
        self.status_label.setText(
            f"Answer ready: {len(response.verified_sources)} verified sources, {response.elapsed_time_ms}ms"
        )

    def _on_answer_failed(self, message: str) -> None:
        self.status_label.setText("Answer generation failed.")
        QMessageBox.warning(self, "Answer failed", message)

    def _on_answer_finished(self) -> None:
        self.search_button.setEnabled(True)
        self.query_edit.setEnabled(True)
        self.mode_combo.setEnabled(True)
        self.include_archived_check.setEnabled(True)

    def _show_selected_result(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._results):
            return
        result = self._results[row]
        self.detail.setPlainText(
            f"문서: {result.original_name}\n"
            f"시트: {result.sheet_name}\n"
            f"조항: {result.article or '일반'}\n"
            f"제목: {result.title or ''}\n"
            f"셀 범위: {result.cell_range}\n"
            f"셀 참조: {', '.join(result.cell_refs)}\n"
            f"키워드 점수: {_format_optional_score(result.keyword_score)}\n"
            f"벡터 점수: {_format_optional_score(result.vector_score)}\n"
            f"최종 점수: {result.final_score:.3f}\n\n"
            f"{result.content}"
        )


def _format_optional_score(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def _format_sources(response: AnswerResponse) -> str:
    if not response.verified_sources:
        return "Verified sources: none"
    blocks = ["Verified sources:"]
    for source in response.verified_sources:
        blocks.append(
            "\n".join(
                (
                    f"[{source.evidence_id}]",
                    f"document: {source.original_name}",
                    f"sheet: {source.sheet_name}",
                    f"article: {source.article or ''}",
                    f"title: {source.title or ''}",
                    f"cell_range: {source.cell_range}",
                    f"cell_refs: {', '.join(source.cell_refs)}",
                    f"content: {source.content}",
                )
            )
        )
    return "\n\n".join(blocks)
