"""LingoNaija - GUI 2: Quiz, Dashboard, Translator and AI Tutor screens.

Run from the project root:
    pip install requests
    python GUI_2.py --username Walter

File layout (top to bottom): configuration, theme, lesson data, quiz logic,
results, services, application context, screens, main window, entry point.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import tkinter as tk
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Sequence

from exceptions import DataFileError, InvalidAnswerError, TranslationError, TutorError
from file_manager import FileManager
from gemini_service import GeminiService
from models import MultipleChoiceQuestion, Question, TranslationQuestion
from translation_service import TranslationService
from validator import Validator

logger = logging.getLogger(__name__)


# ===========================================================================
# CONFIGURATION
# ===========================================================================

PROJECT_ROOT = Path(__file__).resolve().parent
LESSONS_FILE = PROJECT_ROOT / "lessons.json"

APP_TITLE = "LingoNaija"
WINDOW_SIZE = "1000x720"
MIN_WINDOW_SIZE = (850, 600)

LANGUAGES = ("Yoruba", "Igbo", "Hausa")
DEFAULT_LANGUAGE = LANGUAGES[0]
QUESTION_TYPES = ("Multiple Choice", "Translation")
ALL_TOPICS = "All Topics"

QUESTIONS_PER_QUIZ = 10
CHOICES_PER_QUESTION = 4
AUTO_ADVANCE_MS = 1800
DASHBOARD_REFRESH_MS = 3000
RECENT_RESULTS_SHOWN = 7


# ===========================================================================
# THEME (fonts, colours, ttk styling)
# ===========================================================================

FONT_FAMILY = "Segoe UI"
FONT_TITLE = (FONT_FAMILY, 24, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 11)
FONT_SECTION = (FONT_FAMILY, 13, "bold")
FONT_LABEL = (FONT_FAMILY, 12, "bold")
FONT_BODY = (FONT_FAMILY, 11)
FONT_INPUT = (FONT_FAMILY, 12)
FONT_QUESTION = (FONT_FAMILY, 16, "bold")
FONT_STAT = (FONT_FAMILY, 16, "bold")

COLORS = {
    "background": "#ffffff",
    "surface": "#f3f9ff",
    "blue": "#b9e1ff",
    "blue_dark": "#78bdf2",
    "navy": "#14243a",
    "black": "#080d14",
    "text": "#18212e",
    "white": "#ffffff",
    "disabled_bg": "#dceaf5",
    "disabled_fg": "#718096",
    "trough": "#e6f3ff",
}

# Options for tk.Text boxes (ttk has no multi-line text widget).
TEXT_BOX_OPTIONS = {
    "bg": "#f5faff",
    "fg": "#172033",
    "insertbackground": "#172033",
    "selectbackground": "#91ccf5",
    "selectforeground": "#ffffff",
}


def apply_theme(root: tk.Tk) -> None:
    """Configure the 'clam' theme with the LingoNaija navy and blue palette."""
    c = COLORS
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=c["background"])
    style.configure(".", background=c["background"], foreground=c["text"],
                    font=(FONT_FAMILY, 10))
    style.configure("TFrame", background=c["background"])
    style.configure("Header.TFrame", background=c["navy"])
    style.configure("Nav.TFrame", background=c["black"])
    style.configure("TLabel", background=c["background"], foreground=c["text"])
    style.configure("Header.TLabel", background=c["navy"], foreground=c["white"])
    style.configure("Title.TLabel", font=FONT_TITLE)

    style.configure("TLabelframe", background=c["surface"], bordercolor=c["blue"])
    style.configure("TLabelframe.Label", background=c["surface"],
                    foreground=c["text"], font=(FONT_FAMILY, 10, "bold"))

    style.configure("TButton", background=c["blue"], foreground=c["text"], padding=8)
    style.map("TButton",
              background=[("disabled", c["disabled_bg"]),
                          ("pressed", c["blue_dark"]), ("active", c["blue_dark"])],
              foreground=[("disabled", c["disabled_fg"])])
    style.configure("Nav.TButton", background=c["navy"], foreground=c["white"],
                    font=(FONT_FAMILY, 10, "bold"), padding=(15, 10))
    style.map("Nav.TButton",
              background=[("pressed", c["black"]), ("active", c["blue_dark"])],
              foreground=[("active", c["black"])])

    style.configure("TEntry", fieldbackground=c["white"], foreground=c["text"],
                    insertcolor=c["navy"])
    style.configure("TCombobox", fieldbackground=c["white"], foreground=c["text"],
                    arrowcolor=c["navy"])
    style.map("TCombobox", fieldbackground=[("readonly", c["white"])],
              foreground=[("readonly", c["text"])])
    style.configure("TRadiobutton", background=c["surface"], foreground=c["text"])
    style.map("TRadiobutton", background=[("active", c["surface"])],
              foreground=[("active", c["blue_dark"])])
    style.configure("TProgressbar", background=c["blue"], troughcolor=c["trough"],
                    bordercolor=c["background"])

    style.configure("Treeview", background=c["white"], fieldbackground=c["white"],
                    foreground=c["text"], rowheight=26)
    style.map("Treeview", background=[("selected", c["blue"])],
              foreground=[("selected", c["text"])])
    style.configure("Treeview.Heading", background=c["black"],
                    foreground=c["white"], font=(FONT_FAMILY, 10, "bold"))


# ===========================================================================
# LESSON DATA (loads lessons.json, lookups)
# ===========================================================================

# Used only if lessons.json is missing or damaged.
FALLBACK_WORDS: dict[str, dict[str, str]] = {
    "Yoruba": {"Hello": "Bawo ni", "Thank you": "O ṣeun", "Family": "Ìdílé",
               "Mother": "Ìyá", "Father": "Bàbá", "Food": "Oúnjẹ", "Water": "Omi",
               "Good morning": "Ẹ káàárọ̀", "Good night": "Ó dàárọ̀", "Friend": "Ọ̀rẹ́"},
    "Igbo": {"Hello": "Ndewo", "Thank you": "Daalụ", "Family": "Ezinụlọ",
             "Mother": "Nne", "Father": "Nna", "Food": "Nri", "Water": "Mmiri",
             "Good morning": "Ụtụtụ ọma", "Good night": "Ka chi foo", "Friend": "Enyi"},
    "Hausa": {"Hello": "Sannu", "Thank you": "Na gode", "Family": "Iyali",
              "Mother": "Uwa", "Father": "Uba", "Food": "Abinci", "Water": "Ruwa",
              "Good morning": "Ina kwana", "Good night": "Sai anjima", "Friend": "Aboki"},
}

# Words learners commonly type instead of the lesson phrase.
ALIASES = {"thanks": "thank you", "thank": "thank you"}


@dataclass(frozen=True)
class WordMatch:
    english: str
    native: str


class LessonData:
    """All words per language (topics merged), with lenient lookups."""

    def __init__(self, words_by_language: dict[str, dict[str, str]]) -> None:
        self._words = words_by_language
        self._index = {
            language: {Validator.normalize_answer(english): WordMatch(english, native)
                       for english, native in words.items()}
            for language, words in words_by_language.items()
        }

    @classmethod
    def from_file(cls, path: Path = LESSONS_FILE) -> "LessonData":
        """Load lessons.json, falling back to built-in words on any problem."""
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return cls(cls._merge_topics(raw))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.error("Could not load %s (%s); using built-in words.", path, exc)
            return cls(FALLBACK_WORDS)

    @staticmethod
    def _merge_topics(raw: dict) -> dict[str, dict[str, str]]:
        merged: dict[str, dict[str, str]] = {}
        for language in LANGUAGES:
            words: dict[str, str] = {}
            for topic_words in raw[language.lower()].values():
                for item in topic_words:
                    words[item["english"]] = item["native"]
            merged[language] = words
        return merged

    def words(self, language: str) -> dict[str, str]:
        """Return a copy of {english: native} for the language."""
        return dict(self._words[language])

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
        for english_key, match in self._index[language].items():
            if re.search(rf"\b{re.escape(english_key)}\b", sentence):
                return match
        return None


# ===========================================================================
# QUIZ LOGIC (no Tkinter, easy to test)
# ===========================================================================

class QuizSession:
    """One quiz run: builds questions, checks answers and keeps the score."""

    def __init__(self, language: str, words: dict[str, str], question_type: str,
                 size: int = QUESTIONS_PER_QUIZ,
                 rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        pairs = list(words.items())
        self._rng.shuffle(pairs)
        self._questions: list[Question] = [
            self._build_question(language, english, native, words, question_type)
            for english, native in pairs[:size]
        ]
        self._index = 0
        self._score = 0

    def _build_question(self, language: str, english: str, native: str,
                        words: dict[str, str], question_type: str) -> Question:
        if question_type == "Translation":
            return TranslationQuestion(
                f'Translate into {language}:\n\n"{english}"', native)
        others = [other for other in words.values() if other != native]
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
# RESULTS AND DASHBOARD STATS
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
class DashboardStats:
    quiz_count: int
    accuracy: float
    best: QuizResult | None
    latest: QuizResult | None
    languages: tuple[str, ...]


def summarise(results: Sequence[QuizResult]) -> DashboardStats:
    """Compute the numbers shown on the dashboard."""
    if not results:
        return DashboardStats(0, 0.0, None, None, ())
    correct = sum(r.score for r in results)
    asked = sum(r.total for r in results)
    return DashboardStats(
        quiz_count=len(results),
        accuracy=correct / asked * 100,
        best=max(results, key=lambda r: r.ratio),
        latest=results[-1],
        languages=tuple(sorted({r.language for r in results})),
    )


class ResultsStore:
    """Saves and loads a user's quiz history. FileManager is the only file writer."""

    def __init__(self, files: FileManager | None = None) -> None:
        self._files = files or FileManager()

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

    def _offline_reply(self, question: str, language: str) -> str:
        match = self._lessons.find_in_text(question, language)
        if match:
            return f"In {language}, '{match.english}' is '{match.native}'."
        return ("The AI Tutor is currently offline. "
                f"For {language}, try asking about a basic greeting, "
                "family word, food word, or translation.")


# ===========================================================================
# APPLICATION CONTEXT
# ===========================================================================

@dataclass
class AppContext:
    username: str
    lessons: LessonData
    results: ResultsStore
    translation: TranslationFlow
    tutor: TutorFlow


def build_context(username: str) -> AppContext:
    """Create the real services for the running app."""
    lessons = LessonData.from_file()
    return AppContext(
        username=username,
        lessons=lessons,
        results=ResultsStore(),
        translation=TranslationFlow(lessons, TranslationService()),
        tutor=TutorFlow(lessons, GeminiService()),
    )


# ===========================================================================
# SCREENS: shared base
# ===========================================================================

class Screen(ttk.Frame):
    """A screen with a title and subtitle, plus show/hide hooks for the window."""

    def __init__(self, parent: tk.Misc, *, title: str, subtitle: str,
                 subtitle_gap: int = 20) -> None:
        super().__init__(parent, padding=25)
        ttk.Label(self, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text=subtitle, font=FONT_SUBTITLE).pack(
            anchor="w", pady=(0, subtitle_gap))

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

WRAP_WIDTH = 650


class QuizScreen(Screen):
    def __init__(self, parent: tk.Misc, context: AppContext,
                 on_finished: Callable[[], None]) -> None:
        super().__init__(parent, title="Quiz",
                         subtitle="Test your Nigerian language knowledge.")
        self._context = context
        self._on_finished = on_finished

        self._language = tk.StringVar(value=DEFAULT_LANGUAGE)
        self._question_type = tk.StringVar(value=QUESTION_TYPES[0])
        self._typed_answer = tk.StringVar()
        self._chosen_option = tk.StringVar()

        self._session: QuizSession | None = None
        self._answered = False
        self._auto_advance_id: str | None = None

        self._build_controls()
        self._build_question_card()
        self._build_footer()
        self.start_quiz()

    # ---------- layout ----------
    def _build_controls(self) -> None:
        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(0, 20))

        ttk.Label(controls, text="Language:").grid(row=0, column=0, padx=5)
        self._add_combobox(controls, self._language, LANGUAGES, 14, column=1)
        ttk.Label(controls, text="Type:").grid(row=0, column=2, padx=5)
        self._add_combobox(controls, self._question_type, QUESTION_TYPES, 18, column=3)
        ttk.Button(controls, text="New Quiz", command=self.start_quiz).grid(
            row=0, column=4, padx=10)

        self._progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self._progress.pack(fill="x", pady=(0, 20))

    def _add_combobox(self, parent: tk.Misc, variable: tk.StringVar,
                      values: tuple[str, ...], width: int, column: int) -> None:
        box = ttk.Combobox(parent, textvariable=variable, values=list(values),
                           state="readonly", width=width)
        box.grid(row=0, column=column, padx=5)
        box.bind("<<ComboboxSelected>>", lambda event: self.start_quiz())

    def _build_question_card(self) -> None:
        card = ttk.LabelFrame(self, text="Question", padding=25)
        card.pack(fill="both", expand=True)
        self._question_label = ttk.Label(card, font=FONT_QUESTION, wraplength=WRAP_WIDTH)
        self._question_label.pack(anchor="w", pady=(0, 20))
        self._answer_area = ttk.Frame(card)
        self._answer_area.pack(fill="x")
        self._feedback = ttk.Label(card, font=FONT_BODY, wraplength=WRAP_WIDTH)
        self._feedback.pack(anchor="w", pady=15)

    def _build_footer(self) -> None:
        footer = ttk.Frame(self)
        footer.pack(fill="x", pady=(15, 0))
        self._score_label = ttk.Label(footer, text="Score: 0/0", font=FONT_BODY)
        self._score_label.pack(side="left")
        self._submit_button = ttk.Button(footer, text="Submit Answer",
                                         command=self._submit_answer)
        self._submit_button.pack(side="right", padx=5)
        self._next_button = ttk.Button(footer, text="Next", command=self._next_question,
                                       state="disabled")
        self._next_button.pack(side="right")

    # ---------- quiz flow ----------
    def start_quiz(self) -> None:
        self._cancel_auto_advance()
        language = self._language.get()
        self._session = QuizSession(language, self._context.lessons.words(language),
                                    self._question_type.get())
        self._show_question()

    def _show_question(self) -> None:
        for widget in self._answer_area.winfo_children():
            widget.destroy()
        session = self._session
        if session.total == 0:
            self._question_label.config(text="No questions available.")
            return
        if session.is_finished:
            self._finish_quiz()
            return

        self._answered = False
        self._typed_answer.set("")
        self._chosen_option.set("")
        self._feedback.config(text="")
        self._submit_button.config(state="normal")
        self._next_button.config(state="disabled")
        self._progress["value"] = session.index / session.total * 100
        self._update_score_label()

        question = session.current
        self._question_label.config(text=question.prompt)
        if isinstance(question, MultipleChoiceQuestion):
            for option in question.options:
                ttk.Radiobutton(self._answer_area, text=option, value=option,
                                variable=self._chosen_option,
                                command=self._submit_answer).pack(anchor="w", pady=5)
        else:
            entry = ttk.Entry(self._answer_area, textvariable=self._typed_answer,
                              font=(FONT_INPUT[0], 13))
            entry.pack(fill="x", ipady=7)
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
        except InvalidAnswerError:
            messagebox.showwarning("Answer required",
                                   "Please enter or select an answer.")
            return

        self._answered = True
        self._submit_button.config(state="disabled")
        self._next_button.config(state="normal")
        for widget in self._answer_area.winfo_children():
            widget.config(state="disabled")

        if correct:
            self._feedback.config(text="Correct! 🎉")
        else:
            self._feedback.config(
                text=f"Not quite. Correct answer: {question.correct_answer}\n"
                     "Use the Tutor screen if you want an explanation.")
        self._update_score_label()
        self._progress["value"] = (session.index + 1) / session.total * 100
        self._auto_advance_id = self.after(AUTO_ADVANCE_MS, self._next_question)

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
        self._save_result()
        self._on_finished()

    def _save_result(self) -> None:
        session = self._session
        result = QuizResult(language=self._language.get(), topic=ALL_TOPICS,
                            question_type=self._question_type.get(),
                            score=session.score, total=session.total)
        try:
            self._context.results.save(self._context.username, result)
        except DataFileError as exc:
            logger.error("Could not save quiz result: %s", exc)
            messagebox.showwarning("Result not saved",
                                   f"Your score could not be saved: {exc}")


# ===========================================================================
# SCREEN: DASHBOARD
# ===========================================================================

STAT_CARDS = (("quizzes", "Quizzes completed"), ("accuracy", "Overall accuracy"),
              ("best", "Best score"), ("latest", "Latest score"))
HISTORY_COLUMNS = (("language", "Language", 150, "w"), ("type", "Quiz type", 180, "w"),
                   ("score", "Score", 100, "center"), ("accuracy", "Accuracy", 110, "center"))
EMPTY = "—"


def _format_score(result: QuizResult) -> str:
    return f"{result.score}/{result.total} ({result.ratio:.0%})"


class DashboardScreen(Screen):
    def __init__(self, parent: tk.Misc, context: AppContext) -> None:
        super().__init__(parent, title="Your Dashboard",
                         subtitle="Your profile and language-learning progress.",
                         subtitle_gap=18)
        self._context = context
        self._refresh_id: str | None = None
        self._auto_refresh = False
        self._stat_labels: dict[str, ttk.Label] = {}
        self._build_profile()
        self._build_stats()
        self._build_history()

    # ---------- layout ----------
    def _build_profile(self) -> None:
        profile = ttk.LabelFrame(self, text="Profile", padding=15)
        profile.pack(fill="x", pady=(0, 15))
        self._profile_label = ttk.Label(profile, font=(FONT_STAT[0], 14, "bold"))
        self._profile_label.pack(anchor="w")
        self._profile_detail = ttk.Label(profile)
        self._profile_detail.pack(anchor="w", pady=(5, 0))

    def _build_stats(self) -> None:
        stats = ttk.Frame(self)
        stats.pack(fill="x", pady=(0, 15))
        for key, title in STAT_CARDS:
            card = ttk.LabelFrame(stats, text=title, padding=12)
            card.pack(side="left", fill="both", expand=True, padx=(0, 8))
            label = ttk.Label(card, text=EMPTY, font=FONT_STAT)
            label.pack(anchor="w")
            self._stat_labels[key] = label

    def _build_history(self) -> None:
        ttk.Label(self, text="Recent quiz results", font=FONT_SECTION).pack(
            anchor="w", pady=(0, 7))
        self._history = ttk.Treeview(self, columns=[c[0] for c in HISTORY_COLUMNS],
                                     show="headings", height=7)
        for column, heading, width, anchor in HISTORY_COLUMNS:
            self._history.heading(column, text=heading)
            self._history.column(column, width=width, anchor=anchor)
        self._history.pack(fill="both", expand=True)

        self._status = ttk.Label(self)
        self._status.pack(anchor="w", pady=(8, 0))
        ttk.Button(self, text="Refresh", command=self.refresh).pack(anchor="e", pady=(8, 0))

    # ---------- data ----------
    def refresh(self) -> None:
        self._profile_label.config(text=self._context.username)
        self._history.delete(*self._history.get_children())
        try:
            results = self._context.results.load(self._context.username)
        except DataFileError as exc:
            self._show_error(str(exc))
            return

        stats = summarise(results)
        languages = ", ".join(stats.languages) or "None yet"
        noun = "quiz" if stats.quiz_count == 1 else "quizzes"
        self._profile_detail.config(
            text=f"Languages practiced: {languages}  •  {stats.quiz_count} {noun} completed")

        if not results:
            self._set_stats("0", "0%", EMPTY, EMPTY)
            self._status.config(
                text="Complete a quiz to see your results and progress here.")
            return

        self._set_stats(str(stats.quiz_count), f"{stats.accuracy:.0f}%",
                        _format_score(stats.best), _format_score(stats.latest))
        for result in reversed(results[-RECENT_RESULTS_SHOWN:]):
            self._history.insert("", "end", values=(
                result.language, result.question_type,
                f"{result.score}/{result.total}", f"{result.ratio:.0%}"))
        self._status.config(text="")

    def _set_stats(self, quizzes: str, accuracy: str, best: str, latest: str) -> None:
        for key, value in zip(("quizzes", "accuracy", "best", "latest"),
                              (quizzes, accuracy, best, latest)):
            self._stat_labels[key].config(text=value)

    def _show_error(self, message: str) -> None:
        self._profile_detail.config(text="Quiz history unavailable.")
        self._status.config(text=f"Could not load quiz history: {message}")
        self._set_stats(EMPTY, EMPTY, EMPTY, EMPTY)

    # ---------- auto refresh ----------
    def on_show(self) -> None:
        self._stop_auto_refresh()
        self._auto_refresh = True
        self.refresh()
        self._schedule_refresh()

    def on_hide(self) -> None:
        self._stop_auto_refresh()

    def _stop_auto_refresh(self) -> None:
        self._auto_refresh = False
        if self._refresh_id is not None:
            self.after_cancel(self._refresh_id)
            self._refresh_id = None

    def _schedule_refresh(self) -> None:
        if self._auto_refresh:
            self._refresh_id = self.after(DASHBOARD_REFRESH_MS, self._tick)

    def _tick(self) -> None:
        self._refresh_id = None
        if self._auto_refresh:
            self.refresh()
            self._schedule_refresh()


# ===========================================================================
# SCREEN: TRANSLATOR
# ===========================================================================

class TranslatorScreen(Screen):
    def __init__(self, parent: tk.Misc, context: AppContext) -> None:
        super().__init__(parent, title="Translator",
                         subtitle="Translate English phrases into a Nigerian language.")
        self._context = context
        self._target = tk.StringVar(value=DEFAULT_LANGUAGE)
        self._build_controls()
        self._build_boxes()

    def _build_controls(self) -> None:
        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(0, 15))
        ttk.Label(controls, text="Translate English →").pack(side="left")
        ttk.Combobox(controls, textvariable=self._target, values=list(LANGUAGES),
                     state="readonly", width=15).pack(side="left", padx=10)
        ttk.Button(controls, text="Translate", command=self._translate).pack(side="left")

    def _build_boxes(self) -> None:
        ttk.Label(self, text="English", font=FONT_LABEL).pack(anchor="w")
        self._input = create_text_box(self, height=7)
        self._input.pack(fill="x", pady=(5, 15))
        ttk.Label(self, text="Translation", font=FONT_LABEL).pack(anchor="w")
        self._output = create_text_box(self, height=7, read_only=True)
        self._output.pack(fill="x", pady=(5, 15))
        self._status = ttk.Label(self)
        self._status.pack(anchor="w")

    def _translate(self) -> None:
        text = Validator.clean_translation_input(self._input.get("1.0", "end"))
        if not text:
            messagebox.showwarning("Text required",
                                   "Enter an English word or phrase first.")
            return
        self._status.config(text="Translating...")
        set_text(self._output, "")
        self.update_idletasks()
        result = self._context.translation.translate(text, self._target.get())
        set_text(self._output, result.text)
        self._status.config(text=result.status)


# ===========================================================================
# SCREEN: AI TUTOR
# ===========================================================================

GREETING = "Hello! Ask me anything about Yoruba, Igbo, or Hausa."


class TutorScreen(Screen):
    def __init__(self, parent: tk.Misc, context: AppContext) -> None:
        super().__init__(parent, title="AI Tutor",
                         subtitle="Ask questions about Nigerian words, phrases, or grammar.",
                         subtitle_gap=15)
        self._context = context
        self._language = tk.StringVar(value=DEFAULT_LANGUAGE)
        self._build_language_picker()
        self._chat = create_text_box(self, height=18, font=FONT_BODY, read_only=True)
        self._chat.pack(fill="both", expand=True)
        self._build_input_row()
        self._say("Tutor", GREETING)

    def _build_language_picker(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Language context:").pack(side="left")
        ttk.Combobox(top, textvariable=self._language, values=list(LANGUAGES),
                     state="readonly", width=15).pack(side="left", padx=10)

    def _build_input_row(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(10, 0))
        self._entry = ttk.Entry(row, font=FONT_INPUT)
        self._entry.pack(side="left", fill="x", expand=True, ipady=7)
        self._entry.bind("<Return>", lambda event: self._ask())
        ttk.Button(row, text="Ask Tutor", command=self._ask).pack(side="left", padx=(10, 0))

    def _say(self, speaker: str, text: str) -> None:
        append_text(self._chat, f"{speaker}: {text}\n\n")

    def _ask(self) -> None:
        question = Validator.clean_translation_input(self._entry.get())
        if not question:
            return
        self._entry.delete(0, "end")
        self._say("You", question)
        self.update_idletasks()
        self._say("Tutor", self._context.tutor.ask(question, self._language.get()))


# ===========================================================================
# MAIN WINDOW
# ===========================================================================

NAV_ITEMS = (("Quiz", "quiz"), ("Dashboard", "dashboard"),
             ("Translator", "translator"), ("AI Tutor", "tutor"))


class MainWindow(tk.Tk):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self._context = context
        self._active: Screen | None = None

        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(*MIN_WINDOW_SIZE)
        apply_theme(self)

        self._build_header()
        self._build_navigation()
        self._build_screens()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.show_screen("quiz")

    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(20, 15), style="Header.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, font=(FONT_FAMILY, 22, "bold"),
                  style="Header.TLabel").pack(side="left")
        ttk.Label(header, text=self._context.username, font=(FONT_FAMILY, 10),
                  style="Header.TLabel").pack(side="right")

    def _build_navigation(self) -> None:
        nav = ttk.Frame(self, padding=(20, 0, 20, 10), style="Nav.TFrame")
        nav.pack(fill="x")
        for index, (label, name) in enumerate(NAV_ITEMS):
            ttk.Button(nav, text=label, style="Nav.TButton",
                       command=lambda n=name: self.show_screen(n)).pack(
                side="left", padx=(0 if index == 0 else 5, 0))

    def _build_screens(self) -> None:
        container = ttk.Frame(self, padding=(20, 0, 20, 20))
        container.pack(fill="both", expand=True)
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        dashboard = DashboardScreen(container, self._context)
        self._screens: dict[str, Screen] = {
            "dashboard": dashboard,
            "quiz": QuizScreen(container, self._context, on_finished=dashboard.refresh),
            "translator": TranslatorScreen(container, self._context),
            "tutor": TutorScreen(container, self._context),
        }
        for screen in self._screens.values():
            screen.grid(row=0, column=0, sticky="nsew")

    def show_screen(self, name: str) -> None:
        screen = self._screens[name]
        if self._active is not None and self._active is not screen:
            self._active.on_hide()
        self._active = screen
        screen.tkraise()
        screen.on_show()

    def _close(self) -> None:
        if self._active is not None:
            self._active.on_hide()
        self.destroy()


# ===========================================================================
# ENTRY POINT
# ===========================================================================

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python GUI_2.py",
                                     description="LingoNaija GUI 2")
    parser.add_argument("--username", default="Guest",
                        help="3-16 letters, numbers or underscores, starting with a letter")
    args = parser.parse_args(argv)
    if not Validator.validate_username(args.username):
        parser.error("invalid username (use 3-16 letters, numbers or underscores, "
                     "starting with a letter)")
    MainWindow(build_context(args.username)).mainloop()


if __name__ == "__main__":
    main()
