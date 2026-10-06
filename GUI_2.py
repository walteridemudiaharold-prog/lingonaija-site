"""GUI_2.py - LingoNaija GUI 2: Quiz, Translator, AI Tutor and Progress screens.

These screens plug into the main window in GUI_1.py. Run the app with:

    pip install requests
    python GUI_1.py

Every screen takes (parent, controller). The controller (LingoNaijaApp) provides:
    controller.current_user, selected_language, selected_topic,
    controller.services, controller.show_frame(name)

File layout: configuration, lesson data, quiz logic, results, services,
background-task helper, screens.
"""
from __future__ import annotations

import logging
import queue
import random
import re
import threading
import tkinter as tk
from dataclasses import asdict, dataclass, field
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Callable, Sequence

from exceptions import (DataFileError, InvalidAnswerError, LessonNotFoundError,
                        TranslationError, TutorError)
from file_manager import FileManager
from gemini_service import GeminiService
from models import MultipleChoiceQuestion, Question, TranslationQuestion
from translation_service import TranslationService
from validator import Validator

logger = logging.getLogger(__name__)


# ===========================================================================
# CONFIGURATION
# ===========================================================================

LANGUAGES = ("Yoruba", "Igbo", "Hausa")
DEFAULT_LANGUAGE = LANGUAGES[0]
QUESTION_TYPES = ("Multiple Choice", "Translation")
ALL_TOPICS = "All Topics"

QUESTIONS_PER_QUIZ = 10
CHOICES_PER_QUESTION = 4
AUTO_ADVANCE_MS = 1500
RECENT_RESULTS_SHOWN = 7
POLL_MS = 100

FONT_FAMILY = "Segoe UI"
FONT_BODY = (FONT_FAMILY, 11)
FONT_LABEL = (FONT_FAMILY, 12, "bold")
FONT_INPUT = (FONT_FAMILY, 12)
FONT_QUESTION = (FONT_FAMILY, 16, "bold")
FONT_STAT = (FONT_FAMILY, 14, "bold")
FONT_SECTION = (FONT_FAMILY, 13, "bold")
WRAP_WIDTH = 700
EMPTY = "—"

# Options for tk.Text boxes (ttk has no multi-line text widget).
TEXT_BOX_OPTIONS = {
    "bg": "#FFFFFF",
    "fg": "#1E293B",
    "insertbackground": "#1E293B",
    "selectbackground": "#BBE5CF",
    "selectforeground": "#1E293B",
    "relief": "solid",
    "borderwidth": 1,
    "padx": 8,
    "pady": 6,
}


# ===========================================================================
# LESSON DATA (from lessons.json via FileManager)
# ===========================================================================

# Used only if lessons.json is missing or damaged.
FALLBACK_WORDS: dict[str, dict[str, str]] = {
    "Yoruba": {"Hello": "Báwo ni", "Thank you": "O ṣeun", "Family": "Ìdílé",
               "Mother": "Ìyá", "Father": "Bàbá", "Food": "Oúnjẹ", "Water": "Omi",
               "Good morning": "Ẹ káàárọ̀", "Good night": "Ó dàárọ̀", "Friend": "Ọ̀rẹ́"},
    "Igbo": {"Hello": "Ndewo", "Thank you": "Daalụ", "Family": "Ezinụlọ",
             "Mother": "Nne", "Father": "Nna", "Food": "Nri", "Water": "Mmiri",
             "Good morning": "Ụtụtụ ọma", "Good night": "Ka chi fo", "Friend": "Enyi"},
    "Hausa": {"Hello": "Sannu", "Thank you": "Na gode", "Family": "Iyali",
              "Mother": "Uwa", "Father": "Uba", "Food": "Abinci", "Water": "Ruwa",
              "Good morning": "Ina kwana", "Good night": "Sai da safe", "Friend": "Aboki"},
}

# Words learners commonly type instead of the lesson phrase.
ALIASES = {"thanks": "thank you", "thank": "thank you", "hi": "hello", "bye": "goodbye"}


@dataclass(frozen=True)
class WordMatch:
    english: str
    native: str


class LessonData:
    """Words per language and topic, with lenient lookups."""

    def __init__(self, topics: dict[str, dict[str, dict[str, str]]]) -> None:
        # topics[language][topic] = {english: native}
        self._topics = topics
        self._index = {
            language: {
                Validator.normalize_answer(english): WordMatch(english, native)
                for words in topics.get(language, {}).values()
                for english, native in words.items()
            }
            for language in LANGUAGES
        }

    @classmethod
    def from_files(cls, files: FileManager) -> "LessonData":
        """Load lessons through FileManager, falling back to built-in words."""
        try:
            return cls(cls._parse(files.load_lessons()))
        except (LessonNotFoundError, KeyError, TypeError, ValueError, AttributeError) as exc:
            logger.error("Could not load lessons (%s); using built-in words.", exc)
            return cls({language: {"Basics": words}
                        for language, words in FALLBACK_WORDS.items()})

    @staticmethod
    def _parse(raw: dict) -> dict[str, dict[str, dict[str, str]]]:
        return {
            language: {
                topic.title(): {item["english"]: item["native"] for item in items}
                for topic, items in raw.get(language.lower(), {}).items()
            }
            for language in LANGUAGES
        }

    def topics(self) -> tuple[str, ...]:
        """Topic names in file order, without duplicates."""
        seen: dict[str, None] = {}
        for language in LANGUAGES:
            for topic in self._topics.get(language, {}):
                seen.setdefault(topic)
        return tuple(seen)

    def words(self, language: str, topic: str = ALL_TOPICS) -> dict[str, str]:
        """Return a copy of {english: native} for a language and topic."""
        by_topic = self._topics.get(language, {})
        if topic != ALL_TOPICS:
            return dict(by_topic.get(topic, {}))
        merged: dict[str, str] = {}
        for words in by_topic.values():
            merged.update(words)
        return merged

    def lookup(self, text: str, language: str) -> str | None:
        """Exact (lenient) lookup of an English word or phrase."""
        match = self._index[language].get(Validator.normalize_answer(text))
        return match.native if match else None

    def find_in_text(self, text: str, language: str) -> WordMatch | None:
        """Find the first known English word or phrase mentioned inside a sentence."""
        sentence = Validator.normalize_answer(text)
        for alias, phrase in ALIASES.items():
            if alias in sentence.split():
                sentence += f" {phrase}"
        # Longest phrases first so "good morning" wins over shorter words.
        for key, match in sorted(self._index[language].items(), key=lambda kv: -len(kv[0])):
            if re.search(rf"\b{re.escape(key)}\b", sentence):
                return match
        return None


# ===========================================================================
# QUIZ LOGIC (no Tkinter, easy to test)
# ===========================================================================

class QuizSession:
    """One quiz run: builds questions, checks answers and keeps the score."""

    def __init__(self, language: str, words: dict[str, str], pool: dict[str, str],
                 question_type: str, size: int = QUESTIONS_PER_QUIZ,
                 rng: random.Random | None = None) -> None:
        """words: what to ask about. pool: where wrong options may come from."""
        self._rng = rng or random.Random()
        pairs = list(words.items())
        self._rng.shuffle(pairs)
        self._questions: list[Question] = [
            self._build_question(language, english, native, pool, question_type)
            for english, native in pairs[:size]
        ]
        self._index = 0
        self._score = 0

    def _build_question(self, language: str, english: str, native: str,
                        pool: dict[str, str], question_type: str) -> Question:
        if question_type == "Translation":
            return TranslationQuestion(
                f'Translate into {language}:\n\n"{english}"', native)
        others = sorted({value for value in pool.values() if value != native})
        options = [native] + self._rng.sample(
            others, min(CHOICES_PER_QUESTION - 1, len(others)))
        self._rng.shuffle(options)
        return MultipleChoiceQuestion(f'What is "{english}" in {language}?',
                                      native, options)

    @property
    def current(self) -> Question | None:
        return self._questions[self._index] if not self.is_finished else None

    @property
    def index(self) -> int:
        """Zero-based position of the current question."""
        return self._index

    @property
    def total(self) -> int:
        return len(self._questions)

    @property
    def score(self) -> int:
        return self._score

    @property
    def is_finished(self) -> bool:
        return self._index >= len(self._questions)

    def submit(self, answer: str) -> bool:
        """Check the answer for the current question.

        Raises InvalidAnswerError if the answer is empty.
        """
        correct = self.current.check_answer(answer)
        if correct:
            self._score += 1
        return correct

    def advance(self) -> None:
        self._index += 1


# ===========================================================================
# RESULTS AND PROGRESS STATS
# ===========================================================================

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass(frozen=True)
class QuizResult:
    language: str
    topic: str
    question_type: str
    score: int
    total: int
    timestamp: str = field(default_factory=_now)

    @property
    def ratio(self) -> float:
        return self.score / self.total

    @classmethod
    def from_entry(cls, entry: dict) -> "QuizResult | None":
        """Build a result from a saved entry, or None if the entry is invalid."""
        try:
            score, total = int(entry["score"]), int(entry["total"])
        except (KeyError, TypeError, ValueError):
            return None
        if total <= 0 or not 0 <= score <= total:
            return None
        return cls(language=str(entry.get("language", "")),
                   topic=str(entry.get("topic", "")),
                   question_type=str(entry.get("question_type", "Mixed")),
                   score=score, total=total,
                   timestamp=str(entry.get("timestamp", "")))


@dataclass(frozen=True)
class ProgressStats:
    quiz_count: int
    accuracy: float
    best: QuizResult | None
    latest: QuizResult | None
    languages: tuple[str, ...]


def summarise(results: Sequence[QuizResult]) -> ProgressStats:
    """Compute the numbers shown on the progress screen."""
    if not results:
        return ProgressStats(0, 0.0, None, None, ())
    correct = sum(r.score for r in results)
    asked = sum(r.total for r in results)
    return ProgressStats(
        quiz_count=len(results),
        accuracy=correct / asked * 100,
        best=max(results, key=lambda r: r.ratio),
        latest=results[-1],
        languages=tuple(sorted({r.language for r in results})),
    )


class ResultsStore:
    """Saves and loads a user's quiz history. FileManager is the only file writer."""

    def __init__(self, files: FileManager) -> None:
        self._files = files

    def save(self, username: str, result: QuizResult) -> None:
        """Raises DataFileError if the result cannot be saved."""
        self._files.save_result(username, asdict(result))

    def load(self, username: str) -> list[QuizResult]:
        """Return the user's valid results, oldest first. Raises DataFileError."""
        history = self._files.load_users().get(username, {}).get("history", [])
        results = []
        for entry in history:
            result = QuizResult.from_entry(entry)
            if result is None:
                logger.error("Skipping invalid quiz result: %r", entry)
            else:
                results.append(result)
        return results


# ===========================================================================
# SERVICES (translator and tutor with offline fallbacks)
# ===========================================================================

NOT_AVAILABLE = "Offline translation is not available for this phrase."


@dataclass(frozen=True)
class Translation:
    text: str
    status: str


class TranslationFlow:
    """Offline dictionary first, then the translation API, then offline fallback."""

    def __init__(self, lessons: LessonData, api) -> None:
        self._lessons = lessons
        self._api = api

    def translate(self, text: str, language: str) -> Translation:
        offline = self._lessons.lookup(text, language)
        if offline:
            return Translation(offline, "Translated using offline dictionary.")
        try:
            return Translation(self._api.translate(text, language),
                               "Translation complete.")
        except TranslationError as exc:
            logger.error("Translation API error: %s", exc)
            return Translation(NOT_AVAILABLE, "API unavailable; showing offline fallback.")


class TutorFlow:
    """Ask the AI tutor; fall back to a lesson-word answer if it is unavailable."""

    def __init__(self, lessons: LessonData, ai) -> None:
        self._lessons = lessons
        self._ai = ai

    def ask(self, question: str, language: str) -> str:
        try:
            return self._ai.answer_question(language, question)
        except TutorError as exc:
            logger.error("Gemini API error: %s", exc)
            return self._offline_reply(question, language)

    def explain_wrong(self, language: str, question: str, user_answer: str,
                      correct: str) -> str:
        try:
            return self._ai.explain_wrong_answer(language, question, user_answer, correct)
        except TutorError as exc:
            logger.error("Gemini API error: %s", exc)
            return (f"The correct answer is '{correct}'. The AI Tutor is offline, "
                    "so no detailed explanation is available right now.")

    def _offline_reply(self, question: str, language: str) -> str:
        match = self._lessons.find_in_text(question, language)
        if match:
            return f"In {language}, '{match.english}' is '{match.native}'."
        return ("The AI Tutor is currently offline. "
                f"For {language}, try asking about a basic greeting, "
                "family word, food word, or translation.")


@dataclass
class Services:
    """Everything the screens need, built once by the main window."""
    lessons: LessonData
    results: ResultsStore
    translation: TranslationFlow
    tutor: TutorFlow


def build_services(files: FileManager) -> Services:
    lessons = LessonData.from_files(files)
    return Services(
        lessons=lessons,
        results=ResultsStore(files),
        translation=TranslationFlow(lessons, TranslationService()),
        tutor=TutorFlow(lessons, GeminiService()),
    )


# ===========================================================================
# BACKGROUND TASKS (keeps the window responsive during network calls)
# ===========================================================================

def run_async(widget: tk.Misc, work: Callable[[], object],
              done: Callable[[bool, object], None]) -> None:
    """Run work() in a thread; call done(ok, value_or_exception) on the Tk thread.

    Tkinter is not thread-safe, so the worker only puts its result in a queue
    and the main thread picks it up with after().
    """
    results: queue.Queue = queue.Queue()

    def worker() -> None:
        try:
            results.put((True, work()))
        except Exception as exc:  # noqa: BLE001 - reported to the screen
            results.put((False, exc))

    def poll() -> None:
        try:
            ok, value = results.get_nowait()
        except queue.Empty:
            widget.after(POLL_MS, poll)
            return
        done(ok, value)

    threading.Thread(target=worker, daemon=True).start()
    poll()


# ===========================================================================
# SCREENS: shared base and helpers
# ===========================================================================

class Screen(ttk.Frame):
    """A screen with a back button, title and subtitle, plus show/hide hooks."""

    def __init__(self, parent: tk.Misc, controller, *, title: str, subtitle: str) -> None:
        super().__init__(parent, padding=25)
        self.controller = controller
        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Button(header, text="← Dashboard", style="Secondary.TButton",
                   command=lambda: controller.show_frame("DashboardScreen")
                   ).pack(side="left")
        ttk.Label(header, text=title, style="Header.TLabel").pack(side="left", padx=20)
        ttk.Label(self, text=subtitle, style="SubTitle.TLabel").pack(
            anchor="w", pady=(8, 15))

    @property
    def username(self) -> str:
        return self.controller.current_user or "Guest"

    def on_show(self) -> None:
        """Called by the main window when this screen becomes visible."""

    def on_hide(self) -> None:
        """Called by the main window when another screen replaces this one."""


def create_text_box(parent: tk.Misc, *, height: int, font=FONT_INPUT,
                    read_only: bool = False) -> tk.Text:
    box = tk.Text(parent, height=height, font=font, wrap="word", **TEXT_BOX_OPTIONS)
    if read_only:
        box.config(state="disabled")
    return box


def set_text(box: tk.Text, text: str) -> None:
    """Replace the contents of a read-only text box."""
    box.config(state="normal")
    box.delete("1.0", "end")
    box.insert("1.0", text)
    box.config(state="disabled")


def append_text(box: tk.Text, text: str) -> None:
    """Add text to the end of a read-only text box and scroll to it."""
    box.config(state="normal")
    box.insert("end", text)
    box.see("end")
    box.config(state="disabled")


# ===========================================================================
# SCREEN: QUIZ
# ===========================================================================

class QuizScreen(Screen):
    def __init__(self, parent: tk.Misc, controller) -> None:
        super().__init__(parent, controller, title="Practice Quiz",
                         subtitle="Test your Nigerian language knowledge.")
        self._services: Services = controller.services
        self._topic_values = (ALL_TOPICS, *self._services.lessons.topics())

        self._language = tk.StringVar(value=DEFAULT_LANGUAGE)
        self._topic = tk.StringVar(value=ALL_TOPICS)
        self._question_type = tk.StringVar(value=QUESTION_TYPES[0])
        self._typed_answer = tk.StringVar()
        self._chosen_option = tk.StringVar()

        self._session: QuizSession | None = None
        self._quiz_language = DEFAULT_LANGUAGE
        self._answered = False
        self._saved = False
        self._auto_advance_id: str | None = None
        self._explain_token = 0
        self._wrong: tuple[str, str, str] | None = None

        self._build_controls()
        self._build_question_card()
        self._build_footer()

    # ---------- lifecycle ----------
    def on_show(self) -> None:
        self._language.set(self.controller.selected_language)
        topic = self.controller.selected_topic
        self._topic.set(topic if topic in self._topic_values else ALL_TOPICS)
        self.start_quiz()

    def on_hide(self) -> None:
        self._cancel_auto_advance()

    # ---------- layout ----------
    def _build_controls(self) -> None:
        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(0, 12))
        fields = (("Language:", self._language, LANGUAGES, 10),
                  ("Topic:", self._topic, self._topic_values, 12),
                  ("Type:", self._question_type, QUESTION_TYPES, 16))
        for column, (label, variable, values, width) in enumerate(fields):
            ttk.Label(controls, text=label, style="Body.TLabel").grid(
                row=0, column=column * 2, padx=(0 if column == 0 else 12, 5))
            box = ttk.Combobox(controls, textvariable=variable, values=list(values),
                               state="readonly", width=width)
            box.grid(row=0, column=column * 2 + 1)
            box.bind("<<ComboboxSelected>>", lambda event: self.start_quiz())
        ttk.Button(controls, text="New Quiz", style="Secondary.TButton",
                   command=self.start_quiz).grid(row=0, column=6, padx=15)

        self._progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self._progress.pack(fill="x", pady=(0, 12))

    def _build_question_card(self) -> None:
        card = ttk.LabelFrame(self, text="Question", padding=20)
        card.pack(fill="both", expand=True)
        self._question_label = ttk.Label(card, font=FONT_QUESTION, wraplength=WRAP_WIDTH)
        self._question_label.pack(anchor="w", pady=(0, 12))
        self._answer_area = ttk.Frame(card)
        self._answer_area.pack(fill="x")
        self._feedback = ttk.Label(card, font=FONT_BODY, wraplength=WRAP_WIDTH)
        self._feedback.pack(anchor="w", pady=(12, 4))
        self._explanation = ttk.Label(card, font=FONT_BODY, wraplength=WRAP_WIDTH)
        self._explanation.pack(anchor="w", pady=(4, 0))
        self._explain_button = ttk.Button(card, text="Explain with AI Tutor",
                                          style="Secondary.TButton",
                                          command=self._explain)

    def _build_footer(self) -> None:
        footer = ttk.Frame(self)
        footer.pack(fill="x", pady=(12, 0))
        self._score_label = ttk.Label(footer, text="Score: 0/0", style="Body.TLabel")
        self._score_label.pack(side="left")
        self._submit_button = ttk.Button(footer, text="Submit Answer",
                                         style="Primary.TButton",
                                         command=self._submit_answer)
        self._submit_button.pack(side="right", padx=5)
        self._next_button = ttk.Button(footer, text="Next", style="Secondary.TButton",
                                       command=self._next_question, state="disabled")
        self._next_button.pack(side="right")

    # ---------- quiz flow ----------
    def start_quiz(self) -> None:
        self._cancel_auto_advance()
        language, topic = self._language.get(), self._topic.get()
        # Keep the rest of the app in step with what the learner picked here.
        self.controller.selected_language = language
        if topic != ALL_TOPICS:
            self.controller.selected_topic = topic

        lessons = self._services.lessons
        self._quiz_language = language
        self._session = QuizSession(language, lessons.words(language, topic),
                                    lessons.words(language), self._question_type.get())
        self._saved = False
        self._show_question()

    def _show_question(self) -> None:
        for widget in self._answer_area.winfo_children():
            widget.destroy()
        self._hide_explain()
        session = self._session
        self._answered = False
        self._feedback.config(text="")

        if session.total == 0:
            self._question_label.config(text="No questions available for this choice.")
            self._submit_button.config(state="disabled")
            self._next_button.config(state="disabled")
            self._score_label.config(text="Score: 0/0")
            self._progress["value"] = 0
            return
        if session.is_finished:
            self._finish_quiz()
            return

        self._typed_answer.set("")
        self._chosen_option.set("")
        self._submit_button.config(state="normal")
        self._next_button.config(state="disabled", text="Next")
        self._progress["value"] = session.index / session.total * 100
        self._update_score_label()

        question = session.current
        self._question_label.config(text=question.prompt)
        if isinstance(question, MultipleChoiceQuestion):
            for option in question.options:
                ttk.Radiobutton(self._answer_area, text=option, value=option,
                                variable=self._chosen_option,
                                command=self._submit_answer).pack(anchor="w", pady=4)
        else:
            entry = ttk.Entry(self._answer_area, textvariable=self._typed_answer,
                              font=FONT_INPUT)
            entry.pack(fill="x", ipady=6)
            entry.focus()
            entry.bind("<Return>", lambda event: self._submit_answer())

    def _submit_answer(self) -> None:
        session = self._session
        if self._answered or session is None or session.is_finished:
            return
        question = session.current
        answer = (self._chosen_option.get()
                  if isinstance(question, MultipleChoiceQuestion)
                  else self._typed_answer.get())
        try:
            correct = session.submit(answer)
        except InvalidAnswerError as exc:
            messagebox.showwarning("Answer required", str(exc))
            return

        self._answered = True
        self._submit_button.config(state="disabled")
        is_last = session.index + 1 >= session.total
        self._next_button.config(state="normal", text="Finish" if is_last else "Next")
        for widget in self._answer_area.winfo_children():
            widget.config(state="disabled")

        if correct:
            self._feedback.config(text="Correct! 🎉")
            self._auto_advance_id = self.after(AUTO_ADVANCE_MS, self._next_question)
        else:
            self._feedback.config(
                text=f"Not quite. Correct answer: {question.correct_answer}")
            self._wrong = (question.prompt.replace("\n", " "), answer,
                           question.correct_answer)
            self._explain_button.pack(anchor="w", pady=(8, 0))
        self._update_score_label()
        self._progress["value"] = (session.index + 1) / session.total * 100
        if is_last:
            self._save_result()   # save now so leaving the screen cannot lose it

    def _next_question(self) -> None:
        if not self._answered:
            return
        self._cancel_auto_advance()
        self._session.advance()
        self._show_question()

    def _cancel_auto_advance(self) -> None:
        if self._auto_advance_id is not None:
            self.after_cancel(self._auto_advance_id)
            self._auto_advance_id = None

    def _update_score_label(self) -> None:
        session = self._session
        self._score_label.config(
            text=f"Question {session.index + 1}/{session.total}   |   "
                 f"Score: {session.score}/{session.total}")

    def _finish_quiz(self) -> None:
        session = self._session
        percent = session.score / session.total * 100
        self._progress["value"] = 100
        self._question_label.config(
            text=f"Quiz Complete!\n\nYou scored {session.score}/{session.total} "
                 f"({percent:.0f}%).")
        self._feedback.config(text="Great work. Start a new quiz to practise again.")
        self._submit_button.config(state="disabled")
        self._next_button.config(state="disabled")
        self._score_label.config(text=f"Final Score: {session.score}/{session.total}")

    def _save_result(self) -> None:
        if self._saved:
            return
        self._saved = True
        session = self._session
        result = QuizResult(language=self._quiz_language, topic=self._topic.get(),
                            question_type=self._question_type.get(),
                            score=session.score, total=session.total)
        try:
            self._services.results.save(self.username, result)
        except DataFileError as exc:
            logger.error("Could not save quiz result: %s", exc)
            messagebox.showwarning("Result not saved",
                                   f"Your score could not be saved: {exc}")

    # ---------- AI explanation of a wrong answer ----------
    def _hide_explain(self) -> None:
        self._explain_token += 1          # ignore any reply still on its way
        self._wrong = None
        self._explain_button.pack_forget()
        self._explain_button.config(state="normal")
        self._explanation.config(text="")

    def _explain(self) -> None:
        if self._wrong is None:
            return
        question, answer, correct = self._wrong
        language = self._quiz_language
        token = self._explain_token
        self._explain_button.config(state="disabled")
        self._explanation.config(text="Asking the tutor...")

        def done(ok: bool, value: object) -> None:
            if token != self._explain_token:
                return
            self._explanation.config(
                text=value if ok else "Could not get an explanation. Try again later.")

        run_async(self, lambda: self._services.tutor.explain_wrong(
            language, question, answer, correct), done)


# ===========================================================================
# SCREEN: PROGRESS
# ===========================================================================

STAT_CARDS = (("quizzes", "Quizzes completed"), ("accuracy", "Overall accuracy"),
              ("best", "Best score"), ("latest", "Latest score"))
HISTORY_COLUMNS = (("language", "Language", 130, "w"), ("topic", "Topic", 130, "w"),
                   ("type", "Quiz type", 150, "w"), ("score", "Score", 90, "center"),
                   ("accuracy", "Accuracy", 90, "center"))


def _format_score(result: QuizResult) -> str:
    return f"{result.score}/{result.total} ({result.ratio:.0%})"


class ProgressScreen(Screen):
    def __init__(self, parent: tk.Misc, controller) -> None:
        super().__init__(parent, controller, title="My Progress",
                         subtitle="Your profile and language-learning results.")
        self._services: Services = controller.services
        self._stat_labels: dict[str, ttk.Label] = {}
        self._build_profile()
        self._build_stats()
        self._build_history()

    def on_show(self) -> None:
        self.refresh()

    # ---------- layout ----------
    def _build_profile(self) -> None:
        profile = ttk.LabelFrame(self, text="Profile", padding=12)
        profile.pack(fill="x", pady=(0, 12))
        self._profile_label = ttk.Label(profile, font=FONT_STAT)
        self._profile_label.pack(anchor="w")
        self._profile_detail = ttk.Label(profile, style="Body.TLabel")
        self._profile_detail.pack(anchor="w", pady=(4, 0))

    def _build_stats(self) -> None:
        stats = ttk.Frame(self)
        stats.pack(fill="x", pady=(0, 12))
        for key, title in STAT_CARDS:
            card = ttk.LabelFrame(stats, text=title, padding=10)
            card.pack(side="left", fill="both", expand=True, padx=(0, 8))
            label = ttk.Label(card, text=EMPTY, font=FONT_STAT)
            label.pack(anchor="w")
            self._stat_labels[key] = label

    def _build_history(self) -> None:
        ttk.Label(self, text="Recent quiz results", font=FONT_SECTION).pack(
            anchor="w", pady=(0, 6))
        self._history = ttk.Treeview(self, columns=[c[0] for c in HISTORY_COLUMNS],
                                     show="headings", height=7)
        for column, heading, width, anchor in HISTORY_COLUMNS:
            self._history.heading(column, text=heading)
            self._history.column(column, width=width, anchor=anchor)
        self._history.pack(fill="both", expand=True)
        self._status = ttk.Label(self, style="Body.TLabel")
        self._status.pack(anchor="w", pady=(8, 0))

    # ---------- data ----------
    def refresh(self) -> None:
        self._profile_label.config(text=self.username)
        self._history.delete(*self._history.get_children())
        try:
            results = self._services.results.load(self.username)
        except DataFileError as exc:
            self._profile_detail.config(text="Quiz history unavailable.")
            self._status.config(text=f"Could not load quiz history: {exc}")
            self._set_stats(EMPTY, EMPTY, EMPTY, EMPTY)
            return

        stats = summarise(results)
        languages = ", ".join(stats.languages) or "None yet"
        noun = "quiz" if stats.quiz_count == 1 else "quizzes"
        self._profile_detail.config(
            text=f"Languages practised: {languages}  •  {stats.quiz_count} {noun} completed")

        if not results:
            self._set_stats("0", "0%", EMPTY, EMPTY)
            self._status.config(text="Complete a quiz to see your results here.")
            return

        self._set_stats(str(stats.quiz_count), f"{stats.accuracy:.0f}%",
                        _format_score(stats.best), _format_score(stats.latest))
        for result in reversed(results[-RECENT_RESULTS_SHOWN:]):
            self._history.insert("", "end", values=(
                result.language, result.topic, result.question_type,
                f"{result.score}/{result.total}", f"{result.ratio:.0%}"))
        self._status.config(text="")

    def _set_stats(self, quizzes: str, accuracy: str, best: str, latest: str) -> None:
        for key, value in zip(("quizzes", "accuracy", "best", "latest"),
                              (quizzes, accuracy, best, latest)):
            self._stat_labels[key].config(text=value)


# ===========================================================================
# SCREEN: TRANSLATOR
# ===========================================================================

class TranslatorScreen(Screen):
    def __init__(self, parent: tk.Misc, controller) -> None:
        super().__init__(parent, controller, title="Instant Translator",
                         subtitle="Translate English phrases into a Nigerian language.")
        self._target = tk.StringVar(value=DEFAULT_LANGUAGE)
        self._build_controls()
        self._build_boxes()

    def on_show(self) -> None:
        self._target.set(self.controller.selected_language)

    def _build_controls(self) -> None:
        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(0, 12))
        ttk.Label(controls, text="Translate English →", style="Body.TLabel").pack(side="left")
        ttk.Combobox(controls, textvariable=self._target, values=list(LANGUAGES),
                     state="readonly", width=12).pack(side="left", padx=10)
        self._button = ttk.Button(controls, text="Translate", style="Primary.TButton",
                                  command=self._translate)
        self._button.pack(side="left")

    def _build_boxes(self) -> None:
        ttk.Label(self, text="English", font=FONT_LABEL, style="Body.TLabel").pack(anchor="w")
        self._input = create_text_box(self, height=6)
        self._input.pack(fill="x", pady=(5, 12))
        ttk.Label(self, text="Translation", font=FONT_LABEL, style="Body.TLabel").pack(anchor="w")
        self._output = create_text_box(self, height=6, read_only=True)
        self._output.pack(fill="x", pady=(5, 12))
        self._status = ttk.Label(self, style="Body.TLabel")
        self._status.pack(anchor="w")

    def _translate(self) -> None:
        text = Validator.clean_translation_input(self._input.get("1.0", "end"))
        if not text:
            messagebox.showwarning("Text required",
                                   "Enter an English word or phrase first.")
            return
        language = self._target.get()
        self._button.config(state="disabled")
        self._status.config(text="Translating...")
        set_text(self._output, "")

        def done(ok: bool, value: object) -> None:
            self._button.config(state="normal")
            if ok:
                set_text(self._output, value.text)
                self._status.config(text=value.status)
            else:
                logger.error("Translator failed: %s", value)
                self._status.config(text="Something went wrong. Please try again.")

        run_async(self, lambda: self.controller.services.translation.translate(
            text, language), done)


# ===========================================================================
# SCREEN: AI TUTOR
# ===========================================================================

GREETING = "Hello! Ask me anything about Yoruba, Igbo, or Hausa."


class TutorScreen(Screen):
    def __init__(self, parent: tk.Misc, controller) -> None:
        super().__init__(parent, controller, title="AI Tutor",
                         subtitle="Ask questions about Nigerian words, phrases, or grammar.")
        self._language = tk.StringVar(value=DEFAULT_LANGUAGE)
        self._chat_user: str | None = None
        self._busy = False
        self._build_language_picker()
        self._chat = create_text_box(self, height=14, font=FONT_BODY, read_only=True)
        self._chat.pack(fill="both", expand=True)
        self._build_input_row()

    def on_show(self) -> None:
        self._language.set(self.controller.selected_language)
        if self._chat_user != self.username:      # new learner, fresh conversation
            self._chat_user = self.username
            set_text(self._chat, "")
            self._say("Tutor", GREETING)
        self._entry.focus()

    def _build_language_picker(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Language context:", style="Body.TLabel").pack(side="left")
        ttk.Combobox(top, textvariable=self._language, values=list(LANGUAGES),
                     state="readonly", width=12).pack(side="left", padx=10)

    def _build_input_row(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(10, 0))
        self._entry = ttk.Entry(row, font=FONT_INPUT)
        self._entry.pack(side="left", fill="x", expand=True, ipady=6)
        self._entry.bind("<Return>", lambda event: self._ask())
        self._button = ttk.Button(row, text="Ask Tutor", style="Primary.TButton",
                                  command=self._ask)
        self._button.pack(side="left", padx=(10, 0))

    def _say(self, speaker: str, text: str) -> None:
        append_text(self._chat, f"{speaker}: {text}\n\n")

    def _ask(self) -> None:
        if self._busy:
            return
        question = Validator.clean_translation_input(self._entry.get())
        if not question:
            return
        language = self._language.get()
        self._entry.delete(0, "end")
        self._say("You", question)
        self._busy = True
        self._button.config(state="disabled", text="Thinking...")

        def done(ok: bool, value: object) -> None:
            self._busy = False
            self._button.config(state="normal", text="Ask Tutor")
            if ok:
                self._say("Tutor", value)
            else:
                logger.error("Tutor failed: %s", value)
                self._say("Tutor", "Something went wrong. Please try again.")

        run_async(self, lambda: self.controller.services.tutor.ask(question, language),
                  done)
