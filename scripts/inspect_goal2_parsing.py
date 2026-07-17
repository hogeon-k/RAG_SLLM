from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models.document import DocumentChunk
from app.services.chunk_service import ChunkService
from app.services.excel_parser_service import ExcelParserService

MAIN_WORKBOOK = PROJECT_ROOT / "data" / "test_workbooks" / "goal2_regulations_fixture.xlsx"


def inspect_goal2_parsing(workbook_path: Path = MAIN_WORKBOOK) -> dict[str, object]:
    parsed = ExcelParserService().parse(workbook_path, "DOC-GOAL2-FIXTURE")
    chunks = ChunkService().create_chunks(parsed)
    visible_sheets = [sheet for sheet in parsed.sheets if sheet.sheet_state == "visible"]
    merged_range_count = sum(sheet.merged_range_count for sheet in parsed.sheets)
    articles = sorted({chunk.article for chunk in chunks if chunk.article})
    leave_chunk = next((chunk for chunk in chunks if chunk.sheet_name == "휴가규정" and chunk.article == "제8조"), None)
    emergency_chunk = next((chunk for chunk in chunks if chunk.sheet_name == "휴가규정" and chunk.article == "제8조의2"), None)
    reference_chunk = next((chunk for chunk in chunks if chunk.sheet_name == "휴가규정" and "신청 완료율은 80%" in chunk.content), None)
    long_chunks = [chunk for chunk in chunks if chunk.sheet_name == "장문규정"]
    formula_cell = next((cell for cell in parsed.cells if cell.sheet_name == "데이터유형" and cell.coordinate == "B22"), None)
    hidden_cells = [cell for cell in parsed.cells if cell.sheet_name in {"내부메모", "시스템자료"}]

    return {
        "sheet_count": len(parsed.sheets),
        "visible_sheet_count": len(visible_sheets),
        "skipped_hidden_sheet_count": parsed.skipped_hidden_sheet_count,
        "non_empty_cell_count": len(parsed.cells),
        "merged_range_count": merged_range_count,
        "chunk_count": len(chunks),
        "articles": articles,
        "leave_chunk": _chunk_summary(leave_chunk),
        "leave_chunk_has_3_days": "3일 전" in leave_chunk.content if leave_chunk else False,
        "emergency_chunk": _chunk_summary(emergency_chunk),
        "reference_chunk": _chunk_summary(reference_chunk),
        "reference_chunk_has_numeric_text": ("80%" in reference_chunk.content and "3일" in reference_chunk.content) if reference_chunk else False,
        "long_policy_chunk_count": len(long_chunks),
        "empty_sheet_cell_count": len([cell for cell in parsed.cells if cell.sheet_name == "빈시트"]),
        "hidden_sheet_cells_excluded": len(hidden_cells) == 0,
        "formula": formula_cell.formula if formula_cell else None,
        "formula_cached_value": formula_cell.cached_value if formula_cell else None,
    }


def _chunk_summary(chunk: DocumentChunk | None) -> dict[str, object] | None:
    if chunk is None:
        return None
    return {
        "article": chunk.article,
        "title": chunk.title,
        "cell_range": chunk.cell_range,
        "cell_refs": chunk.cell_refs,
        "content": chunk.content,
    }


def main() -> int:
    if not MAIN_WORKBOOK.exists():
        print("Fixture workbook does not exist. Run scripts/generate_goal2_test_workbooks.py first.")
        return 1
    result = inspect_goal2_parsing(MAIN_WORKBOOK)
    for key, value in result.items():
        print(f"{key}: {value}")
    print("\nNo development database was modified by this inspection.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
