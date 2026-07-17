from __future__ import annotations

from app.services.document_service import DocumentService


class DocumentViewModel:
    def __init__(self, service: DocumentService) -> None:
        self._service = service

    def description(self) -> str:
        return self._service.status_message()

