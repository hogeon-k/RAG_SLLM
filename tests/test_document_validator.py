from __future__ import annotations

import shutil

import pytest

from app.services.document_validator import DocumentValidator
from app.services.exceptions import DocumentValidationError
from tests.helpers import create_xlsx


def test_valid_xlsx_passes(tmp_path) -> None:
    path = create_xlsx(tmp_path / "valid.xlsx")
    DocumentValidator(max_file_size_bytes=1024 * 1024).validate(path)


def test_missing_file_rejected(tmp_path) -> None:
    with pytest.raises(DocumentValidationError):
        DocumentValidator(max_file_size_bytes=1024).validate(tmp_path / "missing.xlsx")


@pytest.mark.parametrize("name", ["bad.xls", "bad.xlsm", "bad.txt"])
def test_unsupported_extensions_rejected(tmp_path, name) -> None:
    path = tmp_path / name
    path.write_text("not supported", encoding="utf-8")
    with pytest.raises(DocumentValidationError):
        DocumentValidator(max_file_size_bytes=1024).validate(path)


def test_extension_only_xlsx_rejected(tmp_path) -> None:
    path = tmp_path / "fake.xlsx"
    path.write_text("not a workbook", encoding="utf-8")
    with pytest.raises(DocumentValidationError):
        DocumentValidator(max_file_size_bytes=1024).validate(path)


def test_empty_file_rejected(tmp_path) -> None:
    path = tmp_path / "empty.xlsx"
    path.touch()
    with pytest.raises(DocumentValidationError):
        DocumentValidator(max_file_size_bytes=1024).validate(path)


def test_size_limit_rejected(tmp_path) -> None:
    source = create_xlsx(tmp_path / "large.xlsx")
    oversized = tmp_path / "oversized.xlsx"
    shutil.copyfile(source, oversized)
    with oversized.open("ab") as file:
        file.write(b"0" * 2048)

    with pytest.raises(DocumentValidationError):
        DocumentValidator(max_file_size_bytes=100).validate(oversized)

