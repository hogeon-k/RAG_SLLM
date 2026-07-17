from __future__ import annotations


class DocumentRegistrationError(Exception):
    """Base exception with a user-safe message."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class DocumentValidationError(DocumentRegistrationError):
    pass


class DuplicateDocumentError(DocumentRegistrationError):
    pass


class DocumentStorageError(DocumentRegistrationError):
    pass


class DocumentExtractionError(DocumentRegistrationError):
    pass


class SearchIndexError(DocumentRegistrationError):
    pass


class RetrievalError(DocumentRegistrationError):
    pass


class AnswerGenerationError(DocumentRegistrationError):
    def __init__(self, code: str, user_message: str) -> None:
        super().__init__(user_message)
        self.code = code
