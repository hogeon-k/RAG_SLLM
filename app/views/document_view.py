from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.document import Document
from app.viewmodels.document_viewmodel import DocumentViewModel


@dataclass(frozen=True)
class DocumentMetadata:
    version: str | None
    effective_date: date | None
    revised_date: date | None
    department: str | None


class DocumentMetadataDialog(QDialog):
    def __init__(self, source_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("문서 메타데이터")

        self.version_edit = QLineEdit()
        self.department_edit = QLineEdit()
        self.effective_enabled = QCheckBox("시행일 입력")
        self.revised_enabled = QCheckBox("개정일 입력")
        self.effective_date_edit = QDateEdit()
        self.revised_date_edit = QDateEdit()

        today = QDate.currentDate()
        for date_edit in (self.effective_date_edit, self.revised_date_edit):
            date_edit.setCalendarPopup(True)
            date_edit.setDate(today)
            date_edit.setEnabled(False)

        self.effective_enabled.toggled.connect(self.effective_date_edit.setEnabled)
        self.revised_enabled.toggled.connect(self.revised_date_edit.setEnabled)

        form = QFormLayout()
        file_label = QLabel(source_path.name)
        file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("선택 파일", file_label)
        form.addRow("버전", self.version_edit)
        form.addRow(self.effective_enabled, self.effective_date_edit)
        form.addRow(self.revised_enabled, self.revised_date_edit)
        form.addRow("담당 부서", self.department_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def metadata(self) -> DocumentMetadata:
        return DocumentMetadata(
            version=_clean_text(self.version_edit.text()),
            effective_date=_qdate_to_date(self.effective_date_edit.date()) if self.effective_enabled.isChecked() else None,
            revised_date=_qdate_to_date(self.revised_date_edit.date()) if self.revised_enabled.isChecked() else None,
            department=_clean_text(self.department_edit.text()),
        )


class DocumentView(QWidget):
    HEADERS = ("원본 파일명", "버전", "시행일", "개정일", "담당 부서", "파일 크기", "등록 일시", "처리 상태")

    def __init__(self, view_model: DocumentViewModel) -> None:
        super().__init__()
        self._view_model = view_model

        self.title = QLabel("문서 관리")
        self.title.setObjectName("page_title")
        self.description = QLabel("규정, 법령, 업무 지침 엑셀 문서를 등록하고 관리합니다.")
        self.description.setWordWrap(True)

        self.register_button = QPushButton("엑셀 문서 등록")
        self.refresh_button = QPushButton("새로고침")
        self.status_label = QLabel("")
        self.status_label.setObjectName("status_label")

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.register_button)
        button_layout.addWidget(self.refresh_button)
        button_layout.addStretch(1)

        self.empty_label = QLabel("등록된 문서가 없습니다.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.description)
        layout.addLayout(button_layout)
        layout.addWidget(self.status_label)
        layout.addWidget(self.empty_label, 1)
        layout.addWidget(self.table, 1)

        self.register_button.clicked.connect(self._select_document)
        self.refresh_button.clicked.connect(self._view_model.load_documents)
        self._view_model.documents_changed.connect(self._render_documents)
        self._view_model.registration_started.connect(self._on_registration_started)
        self._view_model.registration_succeeded.connect(self._on_registration_succeeded)
        self._view_model.registration_failed.connect(self._on_registration_failed)
        self._view_model.registration_finished.connect(self._on_registration_finished)

        self._view_model.load_documents()

    def _select_document(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "엑셀 문서 선택",
            "",
            "Excel Workbook (*.xlsx)",
        )
        if not file_name:
            return

        source_path = Path(file_name)
        dialog = DocumentMetadataDialog(source_path, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        metadata = dialog.metadata()
        started = self._view_model.register_document(
            source_path,
            version=metadata.version,
            effective_date=metadata.effective_date,
            revised_date=metadata.revised_date,
            department=metadata.department,
        )
        if not started:
            QMessageBox.information(self, "등록 진행 중", "이미 문서 등록이 진행 중입니다.")

    def _render_documents(self, documents: list[Document]) -> None:
        self.table.setRowCount(len(documents))
        for row, document in enumerate(documents):
            values = (
                document.original_name,
                document.version or "미입력",
                document.effective_date.isoformat() if document.effective_date else "미입력",
                document.revised_date.isoformat() if document.revised_date else "미입력",
                document.department or "미입력",
                _format_file_size(document.file_size_bytes),
                document.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
                _display_status(document.status),
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))

        has_documents = bool(documents)
        self.table.setVisible(has_documents)
        self.empty_label.setVisible(not has_documents)

    def _on_registration_started(self) -> None:
        self.register_button.setEnabled(False)
        self.status_label.setText("문서를 등록하는 중입니다.")

    def _on_registration_succeeded(self, document: Document) -> None:
        self.status_label.setText("등록 완료")
        QMessageBox.information(
            self,
            "등록 완료",
            f"문서가 등록되었습니다.\n파일명: {document.original_name}\n상태: 등록 완료",
        )

    def _on_registration_failed(self, message: str) -> None:
        self.status_label.setText("등록 실패")
        QMessageBox.warning(self, "등록 실패", message)

    def _on_registration_finished(self) -> None:
        self.register_button.setEnabled(True)


def _clean_text(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None


def _qdate_to_date(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def _format_file_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / 1024:.1f} KB"


def _display_status(status: str) -> str:
    return "등록 완료" if status == "UPLOADED" else status
