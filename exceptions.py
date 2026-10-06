"""Custom exceptions shared by the LingoNaija application."""


class LingoNaijaError(Exception):
    """Base class for application-specific errors."""


class InvalidAnswerError(LingoNaijaError):
    """Raised when an answer cannot be accepted by a quiz."""


class LessonNotFoundError(LingoNaijaError):
    """Raised when a requested lesson does not exist."""

class DataFileError(LingoNaijaError):
    """A data file (users.json, results.csv) could not be read or written."""


class TranslationError(LingoNaijaError):
    """The translation API failed or returned an error."""


class TutorError(LingoNaijaError):
    """The Gemini tutor failed or no API key was set."""

