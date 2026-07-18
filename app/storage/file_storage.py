from __future__ import annotations

import os
import shutil
import uuid
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

    def quarantine_document(self, document_id: str, stored_path: str) -> Path | None:
        document_dir = self._safe_document_dir(document_id)
        stored_file = self.resolve(stored_path)
        if not stored_file.exists() and not document_dir.exists():
            return None
        if stored_file.exists() and document_dir not in stored_file.parents:
            raise DocumentStorageError("문서 내부 파일 경로를 안전하게 확인할 수 없어 삭제를 중단했습니다.")
        quarantine_dir = self._safe_quarantine_dir(document_id)
        if document_dir.exists():
            os.replace(document_dir, quarantine_dir)
            return quarantine_dir
        return None

    def restore_quarantine(self, quarantine_dir: Path | None, document_id: str) -> None:
        if quarantine_dir is None:
            return
        document_dir = self._safe_document_dir(document_id)
        quarantine_dir = quarantine_dir.resolve()
        uploads_root = self._uploads_dir.resolve()
        if uploads_root not in quarantine_dir.parents or document_dir.exists():
            raise DocumentStorageError("삭제 롤백 중 내부 파일을 복원할 수 없습니다.")
        os.replace(quarantine_dir, document_dir)

    def finalize_quarantine(self, quarantine_dir: Path | None) -> bool:
        if quarantine_dir is None:
            return False
        quarantine_dir = quarantine_dir.resolve()
        uploads_root = self._uploads_dir.resolve()
        if uploads_root not in quarantine_dir.parents or quarantine_dir == uploads_root:
            raise DocumentStorageError("삭제 대상 내부 파일 경로가 안전하지 않습니다.")
        if quarantine_dir.exists():
            shutil.rmtree(quarantine_dir)
            return True
        return False

    def resolve(self, stored_path: str) -> Path:
        path = (self._data_dir / stored_path).resolve()
        uploads_root = self._uploads_dir.resolve()
        if uploads_root not in path.parents:
            raise DocumentStorageError("저장 경로가 업로드 폴더 밖에 있습니다.")
        return path

    def uploads_root(self) -> Path:
        return self._uploads_dir.resolve()

    def _safe_document_dir(self, document_id: str) -> Path:
        if "/" in document_id or "\\" in document_id or not document_id.startswith("DOC-"):
            raise DocumentStorageError("문서 저장 ID가 올바르지 않습니다.")
        path = (self._uploads_dir / document_id).resolve()
        uploads_root = self._uploads_dir.resolve()
        if uploads_root not in path.parents:
            raise DocumentStorageError("저장 경로가 업로드 폴더 밖에 있습니다.")
        return path

    def _safe_quarantine_dir(self, document_id: str) -> Path:
        base = self._safe_document_dir(document_id)
        path = base.with_name(f".deleting-{document_id}-{uuid.uuid4().hex}").resolve()
        uploads_root = self._uploads_dir.resolve()
        if uploads_root not in path.parents:
            raise DocumentStorageError("삭제 격리 경로가 업로드 폴더 밖에 있습니다.")
        return path
