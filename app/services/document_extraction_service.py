from __future__ import annotations

import logging
import time
from datetime import datetime

from app.config.settings import Settings
from app.models.document import ExtractionResult
from app.repositories.document_repository import DocumentRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.services.chunk_service import ChunkService
from app.services.exceptions import DocumentExtractionError
from app.services.excel_parser_service import ExcelParserService
from app.storage.file_storage import FileStorage


class DocumentExtractionService:
    def __init__(
        self,
        settings: Settings,
        document_repository: DocumentRepository | None = None,
        extraction_repository: ExtractionRepository | None = None,
        file_storage: FileStorage | None = None,
        parser: ExcelParserService | None = None,
        chunk_service: ChunkService | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._settings = settings
        self._document_repository = document_repository or DocumentRepository(settings.database_path)
        self._extraction_repository = extraction_repository or ExtractionRepository(settings.database_path)
        self._file_storage = file_storage or FileStorage(settings.data_dir)
        self._parser = parser or ExcelParserService(settings.max_extracted_cells, settings.include_hidden_sheets)
        self._chunk_service = chunk_service or ChunkService(settings.chunk_max_chars, settings.chunk_min_chars)
        self._logger = logger or logging.getLogger("rag_sllm")

    def extract_document(self, document_id: str) -> ExtractionResult:
        started = time.perf_counter()
        document = self._document_repository.get_by_id(document_id)
        if not document:
            raise DocumentExtractionError("등록된 문서를 찾을 수 없습니다.")

        self._document_repository.update_parse_status(document_id, "PARSING", parse_error=None)
        try:
            stored_file = self._file_storage.resolve(document.stored_path)
            if not stored_file.exists():
                raise DocumentExtractionError("저장된 원본 파일을 찾을 수 없습니다.")

            parsed_workbook = self._parser.parse(stored_file, document_id)
            chunks = self._chunk_service.create_chunks(parsed_workbook)
            if not chunks:
                raise DocumentExtractionError("생성된 청크가 없습니다. 문서 내용을 확인해 주세요.")

            self._extraction_repository.replace_extraction(
                document_id,
                parsed_workbook.sheets,
                parsed_workbook.cells,
                chunks,
            )
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return ExtractionResult(
                document_id=document_id,
                sheet_count=len(parsed_workbook.sheets),
                skipped_hidden_sheet_count=parsed_workbook.skipped_hidden_sheet_count,
                non_empty_cell_count=len(parsed_workbook.cells),
                merged_range_count=sum(sheet.merged_range_count for sheet in parsed_workbook.sheets),
                chunk_count=len(chunks),
                status="PARSED",
                elapsed_time_ms=elapsed_ms,
                warnings=parsed_workbook.warnings,
            )
        except DocumentExtractionError as exc:
            self._document_repository.update_parse_status(document_id, "FAILED", parse_error=exc.user_message)
            raise
        except Exception as exc:
            message = "문서 내용을 추출하는 중 예상하지 못한 오류가 발생했습니다."
            self._document_repository.update_parse_status(document_id, "FAILED", parse_error=message)
            self._logger.exception("Unexpected extraction failure for document %s", document_id)
            raise DocumentExtractionError(message) from exc

    def list_chunks(self, document_id: str):
        return self._extraction_repository.list_chunks(document_id)

    def list_sheets(self, document_id: str):
        return self._extraction_repository.list_sheets(document_id)

    def counts_by_document(self, document_id: str) -> tuple[int, int, int]:
        return self._extraction_repository.counts_by_document(document_id)
