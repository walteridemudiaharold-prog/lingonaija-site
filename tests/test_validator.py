import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "regex & validator.py"
SPEC = importlib.util.spec_from_file_location("lingonaija_validator", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"Could not load validator module from {MODULE_PATH}")

validator_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator_module)
Validator = validator_module.Validator


class ValidateUsernameTests(unittest.TestCase):
    def test_accepts_valid_username(self):
        self.assertTrue(Validator.validate_username("Gbemi_01"))

    def test_rejects_invalid_usernames(self):
        for username in ("1gbemi", "ab", "has space", None):
            with self.subTest(username=username):
                self.assertFalse(Validator.validate_username(username))


class NormalizeAnswerTests(unittest.TestCase):
    def test_normalizes_accents_punctuation_and_whitespace(self):
        self.assertEqual(Validator.normalize_answer("  Ẹ kú àárọ̀!! "), "e ku aaro")

    def test_normalizes_hausa_letters(self):
        self.assertEqual(Validator.normalize_answer("ƙofa, ɗaki"), "kofa daki")

    def test_non_string_input_returns_empty_string(self):
        self.assertEqual(Validator.normalize_answer(None), "")

    def test_answers_match_normalized_text(self):
        self.assertTrue(Validator.answers_match("Ẹ kú àárọ̀", "e ku aaro"))
        self.assertFalse(Validator.answers_match("e ku irole", "e ku aaro"))


class CleanTranslationInputTests(unittest.TestCase):
    def test_normalizes_whitespace_and_preserves_punctuation(self):
        self.assertEqual(
            Validator.clean_translation_input("  Good   morning,  Grandma! "),
            "Good morning, Grandma!",
        )

    def test_rejects_text_without_letters(self):
        for text in ("   ", "123 !!!", None):
            with self.subTest(text=text):
                self.assertEqual(Validator.clean_translation_input(text), "")

    def test_truncates_to_maximum_length(self):
        self.assertEqual(len(Validator.clean_translation_input("a" * 600)), 500)


class ExtractWordsTests(unittest.TestCase):
    def test_extracts_words_with_apostrophes_and_hyphens(self):
        self.assertEqual(
            Validator.extract_words("Nna, 3 ụmụ-nwa o'ma!"),
            ["Nna", "ụmụ-nwa", "o'ma"],
        )


if __name__ == "__main__":
    unittest.main()
