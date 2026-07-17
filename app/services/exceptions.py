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

