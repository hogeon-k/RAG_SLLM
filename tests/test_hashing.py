from __future__ import annotations

from app.utils.hashing import calculate_sha256


def test_same_content_has_same_sha256(tmp_path) -> None:
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(b"same")
    second.write_bytes(b"same")

    assert calculate_sha256(first) == calculate_sha256(second)


def test_different_content_has_different_sha256(tmp_path) -> None:
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(b"one")
    second.write_bytes(b"two")

    assert calculate_sha256(first) != calculate_sha256(second)

