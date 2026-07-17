from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.services.exceptions import DocumentStorageError
from app.utils.hashing import calculate_sha256


class FileStorage:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._uploads_dir = data_dir / "uploads"
        self._uploads_dir.mkdir(parents=True, exist_ok=True)

    def store_document(self, source_path: Path, document_id: str, expected_hash: str) -> str:
        document_dir = self._safe_document_dir(document_id)
        if document_dir.exists():
            raise DocumentStorageError("문서 저장 폴더가 이미 존재합니다.")
        document_dir.mkdir(parents=True, exist_ok=False)
        part_path = document_dir / "document.xlsx.part"
        final_path = document_dir / "document.xlsx"

        try:
            shutil.copyfile(source_path, part_path)
            if part_path.stat().st_size != source_path.stat().st_size:
                raise DocumentStorageError("파일 복사 중 크기가 일치하지 않습니다.")
            if calculate_sha256(part_path) != expected_hash:
                raise DocumentStorageError("파일 복사 중 해시가 일치하지 않습니다.")
            os.replace(part_path, final_path)
            return final_path.relative_to(self._data_dir).as_posix()
        except Exception as exc:
            self.cleanup_document(document_id)
            if isinstance(exc, DocumentStorageError):
                raise
            raise DocumentStorageError("원본 파일을 저장하는 중 오류가 발생했습니다.") from exc

    def cleanup_document(self, document_id: str) -> None:
        document_dir = self._safe_document_dir(document_id)
        if document_dir.exists():
            shutil.rmtree(document_dir)

    def resolve(self, stored_path: str) -> Path:
        path = (self._data_dir / stored_path).resolve()
        uploads_root = self._uploads_dir.resolve()
        if uploads_root not in path.parents:
            raise DocumentStorageError("저장 경로가 업로드 폴더 밖에 있습니다.")
        return path

    def _safe_document_dir(self, document_id: str) -> Path:
        if "/" in document_id or "\\" in document_id or not document_id.startswith("DOC-"):
            raise DocumentStorageError("문서 저장 ID가 올바르지 않습니다.")
        path = (self._uploads_dir / document_id).resolve()
        uploads_root = self._uploads_dir.resolve()
        if uploads_root not in path.parents:
            raise DocumentStorageError("저장 경로가 업로드 폴더 밖에 있습니다.")
        return path
