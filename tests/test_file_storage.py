from __future__ import annotations

from app.storage.file_storage import FileStorage
from app.utils.hashing import calculate_sha256
from tests.helpers import create_xlsx


def test_store_document_copies_to_document_id_folder(tmp_path) -> None:
    source = create_xlsx(tmp_path / "source.xlsx")
    storage = FileStorage(tmp_path / "data")

    stored_path = storage.store_document(source, "DOC-1234", calculate_sha256(source))

    stored = tmp_path / "data" / stored_path
    assert stored.exists()
    assert stored.name == "document.xlsx"
    assert stored.parent.name == "DOC-1234"


def test_store_document_does_not_modify_source(tmp_path) -> None:
    source = create_xlsx(tmp_path / "source.xlsx")
    before = source.read_bytes()
    storage = FileStorage(tmp_path / "data")

    storage.store_document(source, "DOC-1234", calculate_sha256(source))

    assert source.read_bytes() == before


def test_part_file_removed_after_success(tmp_path) -> None:
    source = create_xlsx(tmp_path / "source.xlsx")
    storage = FileStorage(tmp_path / "data")

    storage.store_document(source, "DOC-1234", calculate_sha256(source))

    assert not (tmp_path / "data" / "uploads" / "DOC-1234" / "document.xlsx.part").exists()


def test_stored_path_stays_under_uploads(tmp_path) -> None:
    source = create_xlsx(tmp_path / "source.xlsx")
    storage = FileStorage(tmp_path / "data")

    stored_path = storage.store_document(source, "DOC-1234", calculate_sha256(source))

    assert stored_path == "uploads/DOC-1234/document.xlsx"

