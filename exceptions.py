"""Custom exceptions shared by the LingoNaija application."""


class LingoNaijaError(Exception):
    """Base class for application-specific errors."""


class InvalidAnswerError(LingoNaijaError):
    """Raised when an answer cannot be accepted by a quiz."""


class LessonNotFoundError(LingoNaijaError):
    """Raised when a requested lesson does not exist."""
