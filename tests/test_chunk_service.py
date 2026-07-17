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


def test_article_title_from_adjacent_merged_cell() -> None:
    parsed = _parsed([
        _cell("A13", 13, 1, "제8조"),
        _cell("B13", 13, 2, "연차휴가 신청", "B13:F13"),
        _cell("A14", 14, 1, "①"),
        _cell("B14", 14, 2, "연차휴가는 사용 예정일 3일 전까지 신청해야 한다.", "B14:F14"),
        _cell("A15", 15, 1, "②"),
        _cell("B15", 15, 2, "신청자는 가상 인사시스템에서 신청서를 작성해야 한다.", "B15:F15"),
        _cell("A16", 16, 1, "③"),
        _cell("B16", 16, 2, "부서장의 승인이 완료된 이후 사용할 수 있다.", "B16:F16"),
    ])

    chunk = ChunkService().create_chunks(parsed)[0]

    assert chunk.article == "제8조"
    assert chunk.title == "연차휴가 신청"
    assert chunk.cell_range == "A13:F16"


def test_reference_row_after_blank_gap_is_separate_general_chunk() -> None:
    parsed = _parsed([
        _cell("A18", 18, 1, "제8조의2(긴급휴가)", "A18:F18"),
        _cell("A19", 19, 1, "①"),
        _cell("B19", 19, 2, "질병이나 가족 사고 등 긴급한 사유가 있으면 당일 신청할 수 있다.", "B19:F19"),
        _cell("A20", 20, 1, "②"),
        _cell("B20", 20, 2, "당일 신청자는 업무 시작 전까지 담당자에게 사유를 알려야 한다.", "B20:F20"),
        _cell("A23", 23, 1, "참고"),
        _cell("B23", 23, 2, "신청 완료율은 80%이며 처리 시간은 평균 3일이다."),
    ])

    chunks = ChunkService().create_chunks(parsed)
    emergency = next(chunk for chunk in chunks if chunk.article == "제8조의2")
    reference = next(chunk for chunk in chunks if "80%" in chunk.content)

    assert emergency.title == "긴급휴가"
    assert emergency.cell_range == "A18:F20"
    assert "A23" not in emergency.cell_refs
    assert "B23" not in emergency.cell_refs
    assert reference.article is None
    assert reference.cell_range == "A23:B23"
    assert reference.cell_refs == ("A23", "B23")
    assert "80%" in reference.content
    assert "3일" in reference.content
