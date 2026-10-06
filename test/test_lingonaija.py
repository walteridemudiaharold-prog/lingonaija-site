"""Tests for LingoNaija: validator, models, file handling, and service errors.

Run from the project folder with:
    python -m unittest discover -s tests -v

No internet, API key, or GUI is needed. Files are written to a temporary folder,
so the real users.json and results.csv are never touched.
"""
import csv
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Let the tests import the app modules that sit one folder above tests/
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from exceptions import (DataFileError, InvalidAnswerError, LessonNotFoundError,  # noqa: E402
                        TranslationError, TutorError)
from file_manager import FileManager  # noqa: E402
from gemini_service import GeminiService  # noqa: E402
from models import (Lesson, MultipleChoiceQuestion, ProgressTracker, Quiz,  # noqa: E402
                    TranslationQuestion)
from regex_validator import Validator  # noqa: E402
from translation_service import TranslationService  # noqa: E402


class ValidatorTests(unittest.TestCase):
    def test_valid_usernames(self):
        for name in ["Gbemi_01", "Ada", "a_b_c", "A" * 16]:
            self.assertTrue(Validator.validate_username(name), name)

    def test_invalid_usernames(self):
        for name in ["1gbemi", "ab", "has space", "bad!", "A" * 17, "", None]:
            self.assertFalse(Validator.validate_username(name), repr(name))

    def test_normalize_removes_accents_and_punctuation(self):
        self.assertEqual(Validator.normalize_answer("  Ẹ kú àárọ̀!! "), "e ku aaro")
        self.assertEqual(Validator.normalize_answer("Ọmọ"), "omo")

    def test_normalize_hausa_letters(self):
        self.assertEqual(Validator.normalize_answer("ƙofa, ɗaki"), "kofa daki")

    def test_normalize_non_string_returns_empty(self):
        self.assertEqual(Validator.normalize_answer(None), "")
        self.assertEqual(Validator.normalize_answer(42), "")

    def test_answers_match_is_lenient(self):
        self.assertTrue(Validator.answers_match("Ẹ kú àárọ̀", "e ku aaro"))
        self.assertTrue(Validator.answers_match("E KU AARO", "ẹ kú àárọ̀"))
        self.assertFalse(Validator.answers_match("e ku irole", "e ku aaro"))

    def test_clean_translation_input(self):
        self.assertEqual(Validator.clean_translation_input("  Good   morning,  Grandma! "),
                         "Good morning, Grandma!")
        self.assertEqual(Validator.clean_translation_input("   "), "")
        self.assertEqual(Validator.clean_translation_input("123 !!!"), "")
        self.assertEqual(Validator.clean_translation_input(None), "")
        self.assertEqual(len(Validator.clean_translation_input("a" * 600)), 500)

    def test_extract_words(self):
        self.assertEqual(Validator.extract_words("Nna, 3 ụmụ-nwa o'ma!"),
                         ["Nna", "ụmụ-nwa", "o'ma"])
        self.assertEqual(Validator.extract_words(None), [])


class ModelTests(unittest.TestCase):
    def setUp(self):
        items = [{"english": f"word{i}", "native": f"native{i}"} for i in range(8)]
        self.lesson = Lesson.from_data("yoruba", "test", items)

    def test_lesson_builds_words(self):
        self.assertEqual(len(self.lesson.words), 8)
        self.assertEqual(str(self.lesson.words[0]), "word0 = native0")

    def test_multiple_choice_question(self):
        q = MultipleChoiceQuestion("Q?", "a", ["a", "b", "c"])
        self.assertTrue(q.check_answer("a"))
        self.assertFalse(q.check_answer("b"))
        with self.assertRaises(InvalidAnswerError):
            q.check_answer("")

    def test_translation_question_is_lenient(self):
        q = TranslationQuestion("Q?", "Ẹ kú àárọ̀")
        self.assertTrue(q.check_answer("e ku aaro"))
        self.assertFalse(q.check_answer("wrong"))
        with self.assertRaises(InvalidAnswerError):
            q.check_answer("   ")

    def test_quiz_has_both_question_types(self):
        quiz = Quiz(self.lesson, size=6)
        self.assertEqual(quiz.total, 6)
        kinds = {type(q) for q in quiz.questions}
        self.assertEqual(kinds, {MultipleChoiceQuestion, TranslationQuestion})

    def test_quiz_multiple_choice_includes_correct_option(self):
        quiz = Quiz(self.lesson, size=6)
        for q in quiz.questions:
            if isinstance(q, MultipleChoiceQuestion):
                self.assertIn(q.correct_answer, q.options)

    def test_quiz_scoring(self):
        quiz = Quiz(self.lesson, size=6)
        while quiz.current is not None:
            quiz.submit(quiz.current.correct_answer)
        self.assertEqual(quiz.score, 6)
        self.assertIsNone(quiz.current)

    def test_quiz_wrong_answers_score_zero(self):
        quiz = Quiz(self.lesson, size=4)
        while quiz.current is not None:
            quiz.submit("definitely wrong")
        self.assertEqual(quiz.score, 0)

    def test_quiz_size_is_capped_by_lesson_length(self):
        small = Lesson.from_data("igbo", "tiny", [{"english": "a", "native": "b"}])
        self.assertEqual(Quiz(small, size=6).total, 1)

    def test_empty_answer_does_not_advance_quiz(self):
        quiz = Quiz(self.lesson, size=4)
        with self.assertRaises(InvalidAnswerError):
            quiz.submit("")
        self.assertEqual(quiz.index, 0)


class FileManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.fm = FileManager(base_dir=self.tmp)

    def _copy_real_lessons(self):
        shutil.copy(PROJECT_DIR / "lessons.json", self.tmp)

    def test_real_lessons_file_loads_all_languages(self):
        self._copy_real_lessons()
        lessons = self.fm.load_lessons()
        self.assertEqual(set(lessons), {"yoruba", "igbo", "hausa"})
        for language, topics in lessons.items():
            self.assertTrue(topics, language)
            for topic, items in topics.items():
                for item in items:
                    self.assertIn("english", item)
                    self.assertIn("native", item)

    def test_every_lesson_can_make_a_quiz(self):
        self._copy_real_lessons()
        for language, topics in self.fm.load_lessons().items():
            for topic, items in topics.items():
                quiz = Quiz(Lesson.from_data(language, topic, items))
                self.assertGreater(quiz.total, 0, f"{language}/{topic}")

    def test_missing_lessons_file_raises(self):
        with self.assertRaises(LessonNotFoundError):
            self.fm.load_lessons()

    def test_damaged_lessons_file_raises(self):
        Path(self.tmp, "lessons.json").write_text("{not valid json", encoding="utf-8")
        with self.assertRaises(LessonNotFoundError):
            self.fm.load_lessons()

    def test_load_users_defaults_to_empty(self):
        self.assertEqual(self.fm.load_users(), {})

    def test_damaged_users_file_raises(self):
        Path(self.tmp, "users.json").write_text("oops", encoding="utf-8")
        with self.assertRaises(DataFileError):
            self.fm.load_users()

    def test_save_result_writes_json_and_csv(self):
        entry = {"language": "yoruba", "topic": "greetings", "question_type": "Mixed",
                 "score": 4, "total": 6, "timestamp": "2026-01-01T10:00:00"}
        self.fm.save_result("Ada", entry)
        users = json.loads(Path(self.tmp, "users.json").read_text(encoding="utf-8"))
        self.assertEqual(users["Ada"]["history"][0]["score"], 4)
        with open(Path(self.tmp, "results.csv"), newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], FileManager.CSV_HEADER)
        self.assertEqual(rows[1][:2], ["Ada", "yoruba"])

    def test_old_csv_with_different_header_is_kept_as_backup(self):
        Path(self.tmp, "results.csv").write_text("old,header\n1,2\n", encoding="utf-8")
        entry = {"language": "igbo", "topic": "food", "question_type": "Mixed",
                 "score": 1, "total": 2, "timestamp": "2026-01-01T10:00:00"}
        self.fm.save_result("Ada", entry)
        self.assertTrue(Path(self.tmp, "results_old.csv").exists())
        with open(Path(self.tmp, "results.csv"), newline="", encoding="utf-8") as f:
            self.assertEqual(next(csv.reader(f)), FileManager.CSV_HEADER)

    def test_progress_tracker_saves_and_reloads_history(self):
        tracker = ProgressTracker(self.fm)
        user = tracker.load_user("Ada")
        self.assertEqual(user.history, [])
        tracker.record(user, "hausa", "family", 5, 6)
        reloaded = ProgressTracker(FileManager(base_dir=self.tmp)).load_user("Ada")
        self.assertEqual(len(reloaded.history), 1)
        self.assertEqual(reloaded.history[0]["language"], "hausa")


class ServiceErrorTests(unittest.TestCase):
    """The services must fail with a clear error, never crash the app."""

    def test_translator_rejects_unsupported_language(self):
        with self.assertRaises(TranslationError):
            TranslationService().translate("hello", "french")

    def test_tutor_needs_api_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(TutorError):
                GeminiService().answer_question("yoruba", "How do I greet someone?")
            with self.assertRaises(TutorError):
                GeminiService().explain_wrong_answer("igbo", "Q?", "x", "y")


if __name__ == "__main__":
    unittest.main()
