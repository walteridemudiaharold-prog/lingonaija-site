"""models.py - OOP classes for LingoNaija (Member 4)."""
import random
from abc import ABC, abstractmethod
from datetime import datetime

from exceptions import InvalidAnswerError
from regex_validator import Validator


class Word:
    def __init__(self, english, native):
        self.english = english
        self.native = native

    def __str__(self):
        return f"{self.english} = {self.native}"


class Lesson:
    """A topic in one language, made of Word objects (composition)."""

    def __init__(self, language, topic, words):
        self.language = language
        self.topic = topic
        self.words = words

    @classmethod
    def from_data(cls, language, topic, items):
        return cls(language, topic, [Word(i["english"], i["native"]) for i in items])


class User:
    def __init__(self, username):
        self.username = username
        self._history = []          # private: use the property below

    @property
    def history(self):
        return list(self._history)

    def add_result(self, entry):
        self._history.append(entry)


class Question(ABC):
    """Base class: every question type must implement check_answer()."""

    def __init__(self, prompt, correct):
        self.prompt = prompt
        self._correct = correct

    @property
    def correct_answer(self):
        return self._correct

    @abstractmethod
    def check_answer(self, answer):
        """Return True/False, or raise InvalidAnswerError for empty input."""


class MultipleChoiceQuestion(Question):
    def __init__(self, prompt, correct, options):
        super().__init__(prompt, correct)
        self.options = options

    def check_answer(self, answer):
        if not answer:
            raise InvalidAnswerError("Please choose an option.")
        return answer == self.correct_answer


class TranslationQuestion(Question):
    def check_answer(self, answer):
        if not Validator.normalize_answer(answer):
            raise InvalidAnswerError("Please type an answer.")
        return Validator.answers_match(answer, self.correct_answer)


class Quiz:
    """Builds a mix of multiple-choice and translation questions from a Lesson."""

    def __init__(self, lesson, size=6):
        words = random.sample(lesson.words, min(size, len(lesson.words)))
        self.questions = []
        for i, word in enumerate(words):
            prompt = f"How do you say '{word.english}' in {lesson.language.title()}?"
            if i % 2 == 0:
                others = [w.native for w in lesson.words if w is not word]
                options = random.sample(others, min(3, len(others))) + [word.native]
                random.shuffle(options)
                self.questions.append(MultipleChoiceQuestion(prompt, word.native, options))
            else:
                self.questions.append(TranslationQuestion(prompt, word.native))
        self._score = 0
        self._index = 0

    @property
    def current(self):
        return self.questions[self._index] if self._index < len(self.questions) else None

    @property
    def index(self):
        return self._index

    @property
    def score(self):
        return self._score

    @property
    def total(self):
        return len(self.questions)

    def submit(self, answer):
        """Check the answer, move on, return True/False. Raises InvalidAnswerError."""
        correct = self.current.check_answer(answer)     # polymorphism
        if correct:
            self._score += 1
        self._index += 1
        return correct


class ProgressTracker:
    """Connects User objects to FileManager for saving and loading progress."""

    def __init__(self, file_manager):
        self._files = file_manager

    def load_user(self, username):
        user = User(username)
        for entry in self._files.load_users().get(username, {}).get("history", []):
            user.add_result(entry)
        return user

    def record(self, user, language, topic, score, total, question_type="Mixed"):
        entry = {
            "language": language,
            "topic": topic,
            "question_type": question_type,
            "score": score,
            "total": total,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        user.add_result(entry)
        self._files.save_result(user.username, entry)
