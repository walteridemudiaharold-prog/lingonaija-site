from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from exceptions import InvalidAnswerError, LessonNotFoundError, LingoNaijaError


class LingoNaijaExceptionTests(unittest.TestCase):
    def test_custom_errors_inherit_from_application_base(self):
        self.assertTrue(issubclass(InvalidAnswerError, LingoNaijaError))
        self.assertTrue(issubclass(LessonNotFoundError, LingoNaijaError))

    def test_custom_errors_preserve_their_message(self):
        cases = (
            (InvalidAnswerError, "Answer is required"),
            (LessonNotFoundError, "Lesson not found: greetings"),
        )
        for error_type, message in cases:
            with self.subTest(error_type=error_type.__name__):
                with self.assertRaisesRegex(error_type, message):
                    raise error_type(message)

    def test_application_base_catches_custom_errors(self):
        for error_type in (InvalidAnswerError, LessonNotFoundError):
            with self.subTest(error_type=error_type.__name__):
                with self.assertRaises(LingoNaijaError):
                    raise error_type("Expected test error")


if __name__ == "__main__":
    unittest.main()
