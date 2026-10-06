"""exceptions.py - Custom exceptions for LingoNaija (Member 7)."""


class LingoNaijaError(Exception):
    """Base class for every error raised by this app."""


class InvalidAnswerError(LingoNaijaError):
    """The user submitted an empty or unusable answer."""


class LessonNotFoundError(LingoNaijaError):
    """lessons.json is missing or unreadable."""


class DataFileError(LingoNaijaError):
    """A data file (users.json, results.csv) could not be read or written."""


class TranslationError(LingoNaijaError):
    """The translation API failed or returned an error."""


class TutorError(LingoNaijaError):
    """The Gemini tutor failed or no API key was set."""
