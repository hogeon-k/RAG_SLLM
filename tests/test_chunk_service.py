from __future__ import annotations

from datetime import datetime

from app.models.document import ParsedCell, ParsedSheet, ParsedWorkbook
from app.services.chunk_service import ChunkService


def _sheet() -> ParsedSheet:
    return ParsedSheet("DOC-1-S001", "DOC-1", "규정", 0, "visible", 10, 5, 4, 1, datetime(2026, 1, 1))


def _cell(coordinate: str, row: int, column: int, text: str, merged_range: str | None = None) -> ParsedCell:
    return ParsedCell(
        id=f"DOC-1-S001-{coordinate}",
        document_id="DOC-1",
        sheet_id="DOC-1-S001",
        sheet_name="규정",
        coordinate=coordinate,
        row_index=row,
        column_index=column,
        value_type="string",
        text_value=text,
        formula=None,
        cached_value=None,
        merged_range=merged_range,
        is_merged_anchor=merged_range is not None,
        is_hidden=False,
    )


def _parsed(cells) -> ParsedWorkbook:
    return ParsedWorkbook("DOC-1", (_sheet(),), tuple(cells), 0)


def test_chunks_split_at_next_article() -> None:
    parsed = _parsed([
        _cell("A1", 1, 1, "제1조(목적)"),
        _cell("A2", 2, 1, "이 규정은 목적을 정한다."),
        _cell("A3", 3, 1, "제2조(정의)"),
        _cell("A4", 4, 1, "용어를 정의한다."),
    ])

    chunks = ChunkService().create_chunks(parsed)

    assert len(chunks) == 2
    assert chunks[0].article == "제1조"
    assert chunks[0].title == "목적"
    assert chunks[1].article == "제2조"


def test_different_sheets_are_not_merged() -> None:
    second = ParsedSheet("DOC-1-S002", "DOC-1", "별표", 1, "visible", 1, 1, 1, 0, datetime(2026, 1, 1))
    parsed = ParsedWorkbook(
        "DOC-1",
        (_sheet(), second),
        (
            _cell("A1", 1, 1, "제1조(목적)"),
            ParsedCell("DOC-1-S002-A1", "DOC-1", "DOC-1-S002", "별표", "A1", 1, 1, "string", "별표 내용", None, None, None, False, False),
        ),
        0,
    )

    chunks = ChunkService().create_chunks(parsed)

    assert {chunk.sheet_name for chunk in chunks} == {"규정", "별표"}


def test_long_content_splits_by_max_chars() -> None:
    parsed = _parsed([
        _cell("A1", 1, 1, "제1조(목적)"),
        _cell("A2", 2, 1, "가" * 50),
        _cell("A3", 3, 1, "나" * 50),
    ])

    chunks = ChunkService(max_chars=60).create_chunks(parsed)

    assert len(chunks) >= 2


def test_merged_range_affects_chunk_range_and_refs() -> None:
    parsed = _parsed([
        _cell("B2", 2, 2, "제1조(목적)", "B2:F2"),
        _cell("B3", 3, 2, "내용"),
    ])

    chunk = ChunkService().create_chunks(parsed)[0]

    assert chunk.cell_start == "B2"
    assert chunk.cell_end == "F3"
    assert chunk.cell_range == "B2:F3"
    assert "B2:F2" in chunk.cell_refs


def test_chunk_hash_is_deterministic() -> None:
    parsed = _parsed([_cell("A1", 1, 1, "제1조(목적)")])

    first = ChunkService().create_chunks(parsed)[0]
    second = ChunkService().create_chunks(parsed)[0]

    assert first.content_hash == second.content_hash
    assert first.id == second.id

