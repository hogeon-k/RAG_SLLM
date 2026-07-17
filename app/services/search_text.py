from __future__ import annotations

from app.models.document import Document, DocumentChunk


def build_search_text(document: Document, chunk: DocumentChunk) -> str:
    parts = [
        f"문서: {document.original_name}",
        f"버전: {document.version or '미입력'}",
        f"시트: {chunk.sheet_name}",
        f"구역: {chunk.section or ''}",
        f"조항: {chunk.article or ''}",
        f"제목: {chunk.title or ''}",
        "내용:",
        chunk.content,
    ]
    return "\n".join(part for part in parts if part is not None)
