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
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.models.document import Document, DocumentChunk
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


class ExtractionPreviewDialog(QDialog):
    def __init__(self, document: Document, chunks: list[DocumentChunk], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("추출 결과 미리보기")
        self.resize(900, 640)
        self._chunks = chunks

        summary = QLabel(
            f"문서명: {document.original_name}\n"
            f"처리 상태: {_display_status(document.status)}\n"
            f"청크 수: {len(chunks)}"
        )
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.chunk_list = QListWidget()
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)

        for chunk in chunks:
            label = f"{chunk.chunk_index + 1}. {chunk.sheet_name} | {chunk.article or '일반'} | {chunk.cell_range} | {len(chunk.content)}자"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, chunk.id)
            self.chunk_list.addItem(item)

        self.chunk_list.currentRowChanged.connect(self._show_chunk)

        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(summary)
        layout.addWidget(self.chunk_list, 1)
        layout.addWidget(self.detail, 2)
        layout.addWidget(close_buttons)

        if chunks:
            self.chunk_list.setCurrentRow(0)
        else:
            self.detail.setPlainText("저장된 추출 결과가 없습니다.")

    def _show_chunk(self, row: int) -> None:
        if row < 0 or row >= len(self._chunks):
            return
        chunk = self._chunks[row]
        self.detail.setPlainText(
            f"시트: {chunk.sheet_name}\n"
            f"조항: {chunk.article or '미분류'}\n"
            f"제목: {chunk.title or '미입력'}\n"
            f"셀 범위: {chunk.cell_range}\n"
            f"개별 셀 참조: {', '.join(chunk.cell_refs)}\n\n"
            f"{chunk.content}"
        )


class DocumentView(QWidget):
    HEADERS = (
        "원본 파일명",
        "버전",
        "시행일",
        "개정일",
        "담당 부서",
        "파일 크기",
        "등록 일시",
        "처리 상태",
        "시트",
        "셀",
        "청크",
        "추출 일시",
        "업무 상태",
        "버전 라벨",
        "문서 계열",
    )

    def __init__(self, view_model: DocumentViewModel) -> None:
        super().__init__()
        self._view_model = view_model
        self._documents: list[Document] = []
        self._is_busy = False

        self.title = QLabel("문서 관리")
        self.title.setObjectName("page_title")
        self.description = QLabel("규정, 법령, 업무 지침 엑셀 문서를 등록하고 구조화된 원문 청크로 추출합니다.")
        self.description.setWordWrap(True)

        self.register_button = QPushButton("엑셀 문서 등록")
        self.extract_button = QPushButton("내용 추출")
        self.preview_button = QPushButton("추출 결과 보기")
        self.reextract_button = QPushButton("재추출")
        self.index_button = QPushButton("검색 인덱싱")
        self.reindex_button = QPushButton("재인덱싱")
        self.current_button = QPushButton("현행 문서로 설정")
        self.archive_button = QPushButton("보관 문서로 설정")
        self.delete_button = QPushButton("선택 문서 삭제")
        self.refresh_button = QPushButton("새로고침")
        self.status_label = QLabel("")
        self.status_label.setObjectName("status_label")

        button_layout = QHBoxLayout()
        for button in (
            self.register_button,
            self.extract_button,
            self.preview_button,
            self.reextract_button,
            self.index_button,
            self.reindex_button,
            self.current_button,
            self.archive_button,
            self.delete_button,
            self.refresh_button,
        ):
            button_layout.addWidget(button)
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
        self.extract_button.clicked.connect(self._extract_selected_document)
        self.reextract_button.clicked.connect(self._extract_selected_document)
        self.preview_button.clicked.connect(self._preview_selected_document)
        self.index_button.clicked.connect(self._index_selected_document)
        self.reindex_button.clicked.connect(self._reindex_selected_document)
        self.current_button.clicked.connect(self._set_selected_current)
        self.archive_button.clicked.connect(self._set_selected_archived)
        self.delete_button.clicked.connect(self._delete_selected_document)
        self.refresh_button.clicked.connect(self._view_model.load_documents)
        self.table.itemSelectionChanged.connect(self._update_action_buttons)
        self._view_model.documents_changed.connect(self._render_documents)
        self._view_model.registration_started.connect(self._on_registration_started)
        self._view_model.registration_succeeded.connect(self._on_registration_succeeded)
        self._view_model.registration_failed.connect(self._on_registration_failed)
        self._view_model.registration_finished.connect(self._on_registration_finished)
        self._view_model.extraction_started.connect(self._on_extraction_started)
        self._view_model.extraction_progress.connect(self._on_extraction_progress)
        self._view_model.extraction_succeeded.connect(self._on_extraction_succeeded)
        self._view_model.extraction_failed.connect(self._on_extraction_failed)
        self._view_model.extraction_finished.connect(self._on_extraction_finished)
        self._view_model.indexing_started.connect(self._on_indexing_started)
        self._view_model.indexing_succeeded.connect(self._on_indexing_succeeded)
        self._view_model.indexing_failed.connect(self._on_indexing_failed)
        self._view_model.indexing_finished.connect(self._on_indexing_finished)
        self._view_model.lifecycle_changed.connect(self._on_lifecycle_changed)
        self._view_model.lifecycle_failed.connect(self._on_lifecycle_failed)
        self._view_model.document_deletion_started.connect(self._on_deletion_started)
        self._view_model.document_deletion_succeeded.connect(self._on_deletion_succeeded)
        self._view_model.document_deletion_failed.connect(self._on_deletion_failed)
        self._view_model.document_deletion_finished.connect(self._on_deletion_finished)

        self._view_model.load_documents()
        self._update_action_buttons()

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
        selected_document_id = self._selected_document().id if self._selected_document() else None
        self._documents = documents
        self.table.setRowCount(len(documents))
        for row, document in enumerate(documents):
            sheet_count, cell_count, chunk_count = self._view_model.extraction_counts(document.id)
            values = (
                document.original_name,
                document.version or "미입력",
                document.effective_date.isoformat() if document.effective_date else "미입력",
                document.revised_date.isoformat() if document.revised_date else "미입력",
                document.department or "미입력",
                _format_file_size(document.file_size_bytes),
                document.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
                _display_status(document.status),
                str(sheet_count),
                str(cell_count),
                str(chunk_count),
                document.parsed_at.strftime("%Y-%m-%d %H:%M:%S") if document.parsed_at else "미입력",
                document.lifecycle_status,
                document.version_label or "미입력",
                document.document_family or "미입력",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, document.id)
                self.table.setItem(row, column, item)

        has_documents = bool(documents)
        self.table.setVisible(has_documents)
        self.empty_label.setVisible(not has_documents)
        if selected_document_id:
            for row, document in enumerate(documents):
                if document.id == selected_document_id:
                    self.table.selectRow(row)
                    break
        self._update_action_buttons()

    def _selected_document(self) -> Document | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._documents):
            return None
        return self._documents[row]

    def _extract_selected_document(self) -> None:
        document = self._selected_document()
        if document is None:
            QMessageBox.information(self, "문서 선택", "먼저 문서를 선택해 주세요.")
            return
        if not self._view_model.extract_document(document.id):
            QMessageBox.information(self, "추출 진행 중", "이미 문서 추출이 진행 중입니다.")

    def _preview_selected_document(self) -> None:
        document = self._selected_document()
        if document is None:
            QMessageBox.information(self, "문서 선택", "먼저 문서를 선택해 주세요.")
            return
        chunks = self._view_model.load_chunks(document.id)
        dialog = ExtractionPreviewDialog(document, chunks, self)
        dialog.exec()

    def _index_selected_document(self) -> None:
        document = self._selected_document()
        if document is None:
            QMessageBox.information(self, "문서 선택", "먼저 문서를 선택해 주세요.")
            return
        if not self._view_model.index_document(document.id):
            QMessageBox.information(self, "인덱싱 진행 중", "이미 검색 인덱싱이 진행 중입니다.")

    def _reindex_selected_document(self) -> None:
        document = self._selected_document()
        if document is None:
            QMessageBox.information(self, "문서 선택", "먼저 문서를 선택해 주세요.")
            return
        if not self._view_model.index_document(document.id, force=True):
            QMessageBox.information(self, "인덱싱 진행 중", "이미 검색 인덱싱이 진행 중입니다.")

    def _set_selected_current(self) -> None:
        document = self._selected_document()
        if document is None:
            QMessageBox.information(self, "문서 선택", "먼저 문서를 선택해 주세요.")
            return
        message = "이 문서를 기본 검색 대상인 CURRENT로 설정합니다."
        if document.document_family:
            message += "\n같은 문서 계열의 다른 CURRENT 문서는 ARCHIVED로 전환될 수 있습니다."
        if QMessageBox.question(self, "현행 문서 설정", message) != QMessageBox.StandardButton.Yes:
            return
        self._set_busy(True)
        if not self._view_model.promote_current(document.id):
            self._set_busy(False)
            self._update_action_buttons()

    def _set_selected_archived(self) -> None:
        document = self._selected_document()
        if document is None:
            QMessageBox.information(self, "문서 선택", "먼저 문서를 선택해 주세요.")
            return
        message = "이 문서를 ARCHIVED로 설정합니다.\n기본 질문 검색에서는 제외됩니다."
        if QMessageBox.question(self, "보관 문서 설정", message) != QMessageBox.StandardButton.Yes:
            return
        self._set_busy(True)
        if not self._view_model.set_lifecycle_status(document.id, "ARCHIVED"):
            self._set_busy(False)
            self._update_action_buttons()

    def _delete_selected_document(self) -> None:
        document = self._selected_document()
        if document is None:
            QMessageBox.information(self, "문서 선택", "먼저 삭제할 문서를 선택해 주세요.")
            return
        if document.status in {"PARSING", "INDEXING"}:
            QMessageBox.information(self, "삭제 불가", "문서가 처리 중이어서 삭제할 수 없습니다.")
            return

        sheet_count, cell_count, chunk_count = self._view_model.extraction_counts(document.id)
        message = (
            "선택한 문서의 내부 등록 데이터를 삭제합니다.\n\n"
            f"파일명: {document.original_name}\n"
            f"업무 상태: {document.lifecycle_status}\n"
            f"처리 상태: {_display_status(document.status)}\n"
            f"시트: {sheet_count}\n"
            f"셀: {cell_count}\n"
            f"청크: {chunk_count}\n\n"
            "내부 복사본, 추출 데이터, 키워드/벡터 검색 인덱스가 삭제됩니다.\n"
            "질문 이력과 검증 출처 스냅샷은 유지되며, 처음 선택했던 원본 엑셀 파일은 삭제하지 않습니다."
        )
        if document.lifecycle_status == "CURRENT":
            message += "\nCURRENT 문서를 삭제해도 같은 계열의 보관 문서가 자동으로 승격되지는 않습니다."
        if QMessageBox.question(self, "문서 삭제 확인", message) != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True)
        if not self._view_model.delete_document(document.id):
            self._set_busy(False)
            self._update_action_buttons()
            QMessageBox.information(self, "삭제 진행 중", "다른 문서 작업이 진행 중이어서 삭제를 시작할 수 없습니다.")

    def _update_action_buttons(self) -> None:
        document = self._selected_document()
        has_document = document is not None
        status = document.status if document else ""
        busy = self._is_busy or status in {"PARSING", "INDEXING"}
        self.extract_button.setEnabled(has_document and status in {"UPLOADED", "FAILED"} and not busy)
        self.reextract_button.setEnabled(has_document and status in {"PARSED", "FAILED"} and not busy)
        self.preview_button.setEnabled(has_document and status in {"PARSED", "COMPLETED"} and not busy)
        self.index_button.setEnabled(has_document and status == "PARSED" and not busy)
        self.reindex_button.setEnabled(has_document and status == "COMPLETED" and not busy)
        self.current_button.setEnabled(has_document and document.lifecycle_status != "CURRENT" and not busy)
        self.archive_button.setEnabled(has_document and document.lifecycle_status != "ARCHIVED" and not busy)
        self.delete_button.setEnabled(has_document and not busy)

    def _set_busy(self, is_busy: bool) -> None:
        self._is_busy = is_busy
        self.register_button.setEnabled(not is_busy)
        self.extract_button.setEnabled(not is_busy)
        self.reextract_button.setEnabled(not is_busy)
        self.preview_button.setEnabled(not is_busy)
        self.index_button.setEnabled(not is_busy)
        self.reindex_button.setEnabled(not is_busy)
        self.current_button.setEnabled(not is_busy)
        self.archive_button.setEnabled(not is_busy)
        self.delete_button.setEnabled(not is_busy)
        self.refresh_button.setEnabled(not is_busy)

    def _on_registration_started(self) -> None:
        self._set_busy(True)
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
        self._set_busy(False)
        self._update_action_buttons()

    def _on_extraction_started(self) -> None:
        self._set_busy(True)
        self.status_label.setText("문서 내용을 추출하는 중입니다.")

    def _on_extraction_progress(self, percent: int, message: str) -> None:
        self.status_label.setText(f"{message} ({percent}%)")

    def _on_extraction_succeeded(self, result) -> None:
        self.status_label.setText("추출 완료")
        QMessageBox.information(
            self,
            "추출 완료",
            "문서 내용 추출이 완료되었습니다.\n"
            f"시트: {result.sheet_count}\n"
            f"셀: {result.non_empty_cell_count}\n"
            f"청크: {result.chunk_count}",
        )

    def _on_extraction_failed(self, message: str) -> None:
        self.status_label.setText("추출 실패")
        QMessageBox.warning(self, "추출 실패", message)

    def _on_extraction_finished(self) -> None:
        self._set_busy(False)
        self._update_action_buttons()

    def _on_indexing_started(self) -> None:
        self._set_busy(True)
        self.status_label.setText("검색 인덱스를 생성하는 중입니다.")

    def _on_indexing_succeeded(self, result) -> None:
        self.status_label.setText("검색 인덱싱 완료")
        QMessageBox.information(
            self,
            "검색 인덱싱 완료",
            "검색 인덱싱이 완료되었습니다.\n"
            f"FTS 청크: {result.fts_count}\n"
            f"벡터 청크: {result.vector_count}\n"
            f"모델: {result.embedding_model}",
        )

    def _on_indexing_failed(self, message: str) -> None:
        self.status_label.setText("검색 인덱싱 실패")
        QMessageBox.warning(self, "검색 인덱싱 실패", message)

    def _on_indexing_finished(self) -> None:
        self._set_busy(False)
        self._view_model.load_documents()
        self._update_action_buttons()

    def _on_lifecycle_changed(self, document: Document) -> None:
        self.status_label.setText(f"업무 상태 변경 완료: {document.lifecycle_status}")
        self._set_busy(False)
        self._update_action_buttons()

    def _on_lifecycle_failed(self, message: str) -> None:
        self.status_label.setText("업무 상태 변경 실패")
        self._set_busy(False)
        self._update_action_buttons()
        QMessageBox.warning(self, "업무 상태 변경 실패", message)

    def _on_deletion_started(self) -> None:
        self._set_busy(True)
        self.status_label.setText("문서를 삭제하는 중입니다.")

    def _on_deletion_succeeded(self, result) -> None:
        self.status_label.setText("문서 삭제 완료")
        self.table.clearSelection()
        message = (
            "문서 삭제가 완료되었습니다.\n"
            f"파일명: {result.display_name}\n"
            f"문서 레코드: {result.deleted_document_count}\n"
            f"시트: {result.deleted_sheet_count}\n"
            f"셀: {result.deleted_cell_count}\n"
            f"청크: {result.deleted_chunk_count}\n"
            f"FTS 청크: {result.deleted_fts_count}\n"
            f"벡터 청크: {result.deleted_vector_count}\n"
            "질문 이력과 검증 출처 스냅샷은 유지되었습니다."
        )
        if result.warning_code == "FILE_FINALIZE_FAILED":
            message += "\n내부 파일 정리는 재시도 대상입니다."
        QMessageBox.information(self, "문서 삭제 완료", message)

    def _on_deletion_failed(self, message: str) -> None:
        self.status_label.setText("문서 삭제 실패")
        QMessageBox.warning(self, "문서 삭제 실패", message)

    def _on_deletion_finished(self) -> None:
        self._set_busy(False)
        self._update_action_buttons()


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
    labels = {
        "UPLOADED": "등록 완료",
        "PARSING": "추출 중",
        "PARSED": "추출 완료",
        "INDEXING": "인덱싱 중",
        "COMPLETED": "검색 가능",
        "FAILED": "추출 실패",
    }
    return labels.get(status, status)
