"""
GUI_1.py - LingoNaija main window (run this file).

    pip install requests
    python GUI_1.py

Responsibilities:
- Main application window and navigation
- Login, Dashboard, Lesson screens
- Registers the GUI 2 screens (Quiz, Translator, AI Tutor, Progress)
"""

import tkinter as tk
from tkinter import ttk, messagebox

from exceptions import DataFileError, LessonNotFoundError
from file_manager import FileManager
from GUI_2 import (ProgressScreen, QuizScreen, TranslatorScreen, TutorScreen,
                   build_services)
from models import Lesson
from regex_validator import Validator

DEFAULT_LANGUAGE = "Yoruba"
DEFAULT_TOPIC = "Greetings"
LANGUAGES = ("Yoruba", "Igbo", "Hausa")
# Must match the keys in lessons.json (shown with a capital letter).
TOPICS = ("Greetings", "Food", "Family", "Numbers", "Body", "Animals")


# ==============================================================================
# MAIN APPLICATION
# ==============================================================================

class LingoNaijaApp(tk.Tk):
    """Main window and navigation controller."""

    def __init__(self):
        super().__init__()

        self.title("LingoNaija - Nigerian Language Learning Platform")
        self.geometry("1000x720")
        self.minsize(900, 660)

        # Shared application state
        self.current_user = None
        self.selected_language = DEFAULT_LANGUAGE
        self.selected_topic = DEFAULT_TOPIC
        self.current_frame = None

        # Shared services (FileManager is the only class that touches files)
        self.file_manager = FileManager()
        self.services = build_services(self.file_manager)

        self._configure_styles()

        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        # Screens are stored by class name. The dashboard cards use these names.
        self.frames = {}
        for ScreenClass in (LoginScreen, DashboardScreen, LessonScreen,
                            QuizScreen, TranslatorScreen, TutorScreen,
                            ProgressScreen):
            frame = ScreenClass(self.container, self)
            self.frames[ScreenClass.__name__] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("LoginScreen")

    # --------------------------------------------------------------------------
    # Styling (one theme for the whole app, GUI 2 screens use these styles too)
    # --------------------------------------------------------------------------

    def _configure_styles(self):
        self.style = style = ttk.Style()
        style.theme_use("clam")

        GREEN_PRIMARY = "#008751"
        GREEN_HOVER = "#006B40"
        GREEN_SOFT = "#BBE5CF"
        BG_LIGHT = "#F5F7F8"
        TEXT_DARK = "#1E293B"

        self.configure(bg=BG_LIGHT)

        style.configure(".", background=BG_LIGHT, foreground=TEXT_DARK,
                        font=("Segoe UI", 10))
        style.configure("TFrame", background=BG_LIGHT)
        style.configure("TLabel", background=BG_LIGHT, foreground=TEXT_DARK)

        style.configure("MainTitle.TLabel", font=("Segoe UI", 24, "bold"),
                        foreground=GREEN_PRIMARY, background=BG_LIGHT)
        style.configure("SubTitle.TLabel", font=("Segoe UI", 12),
                        foreground="#64748B", background=BG_LIGHT)
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"),
                        foreground=TEXT_DARK, background=BG_LIGHT)
        style.configure("Body.TLabel", font=("Segoe UI", 11),
                        foreground=TEXT_DARK, background=BG_LIGHT)

        style.configure("TButton", padding=6)
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"),
                        background=GREEN_PRIMARY, foreground="white",
                        borderwidth=0, padding=10)
        style.map("Primary.TButton",
                  background=[("disabled", "#A7C7B8"), ("active", GREEN_HOVER)],
                  foreground=[("disabled", "#F5F7F8")])
        style.configure("Secondary.TButton", font=("Segoe UI", 10), padding=6)
        style.configure("Nav.TButton", font=("Segoe UI", 11, "bold"), padding=12)

        style.configure("Card.TFrame", background="#FFFFFF", relief="solid",
                        borderwidth=1)

        # Widgets used by the GUI 2 screens
        style.configure("TLabelframe", background=BG_LIGHT, bordercolor="#CBD5E1")
        style.configure("TLabelframe.Label", background=BG_LIGHT,
                        foreground=TEXT_DARK, font=("Segoe UI", 10, "bold"))
        style.configure("TRadiobutton", background=BG_LIGHT, foreground=TEXT_DARK,
                        font=("Segoe UI", 11))
        style.map("TRadiobutton", background=[("active", BG_LIGHT)],
                  foreground=[("disabled", "#94A3B8")])
        style.configure("TCombobox", fieldbackground="white", foreground=TEXT_DARK)
        style.map("TCombobox", fieldbackground=[("readonly", "white")],
                  foreground=[("readonly", TEXT_DARK)])
        style.configure("TEntry", fieldbackground="white")
        style.configure("TProgressbar", background=GREEN_PRIMARY,
                        troughcolor="#E2E8F0", bordercolor=BG_LIGHT)
        style.configure("Treeview", background="white", fieldbackground="white",
                        foreground=TEXT_DARK, rowheight=26)
        style.map("Treeview", background=[("selected", GREEN_SOFT)],
                  foreground=[("selected", TEXT_DARK)])
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"),
                        background="#E2E8F0", foreground=TEXT_DARK)

    # --------------------------------------------------------------------------
    # Navigation
    # --------------------------------------------------------------------------

    def show_frame(self, page_name: str):
        """Show a screen by name, calling on_hide / on_show hooks if present."""
        frame = self.frames.get(page_name)

        if frame is None:
            messagebox.showinfo("Module Pending",
                                f"Screen '{page_name}' has not been integrated yet.")
            return

        previous = self.current_frame
        if previous is not None and previous is not frame and hasattr(previous, "on_hide"):
            previous.on_hide()

        self.current_frame = frame
        if hasattr(frame, "on_show"):
            frame.on_show()
        frame.tkraise()

    def logout(self):
        """Clear the current user and return to Login."""
        self.current_user = None
        self.selected_language = DEFAULT_LANGUAGE
        self.selected_topic = DEFAULT_TOPIC
        self.show_frame("LoginScreen")


# ==============================================================================
# LOGIN SCREEN
# ==============================================================================

class LoginScreen(ttk.Frame):
    """Login screen. Uses the shared Validator for the username."""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        content_frame = ttk.Frame(self)
        content_frame.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(content_frame, text="LingoNaija",
                  style="MainTitle.TLabel").pack(pady=(0, 5))
        ttk.Label(content_frame, text="Learn Yoruba, Igbo, and Hausa effortlessly",
                  style="SubTitle.TLabel").pack(pady=(0, 30))

        card = ttk.Frame(content_frame, style="Card.TFrame", padding=30)
        card.pack(fill="x")

        ttk.Label(card, text="Welcome Learner!", style="Header.TLabel",
                  background="#FFFFFF").pack(anchor="w", pady=(0, 15))
        ttk.Label(card, text="Enter your Username:", style="Body.TLabel",
                  background="#FFFFFF").pack(anchor="w", pady=(0, 5))

        self.username_entry = ttk.Entry(card, font=("Segoe UI", 11), width=30)
        self.username_entry.pack(fill="x", pady=(0, 15))

        ttk.Button(card, text="Start Learning →", style="Primary.TButton",
                   command=self.handle_login).pack(fill="x", pady=(10, 0))

        self.status_label = ttk.Label(card, text="", font=("Segoe UI", 9),
                                      foreground="red", background="#FFFFFF",
                                      wraplength=320)
        self.status_label.pack(pady=(10, 0))

        self.username_entry.bind("<Return>", lambda event: self.handle_login())

    def on_show(self):
        self.username_entry.focus()

    def handle_login(self):
        """Validate username and open the dashboard."""
        username = self.username_entry.get().strip()

        if not Validator.validate_username(username):
            self.status_label.config(
                text=("Username must be 3-16 characters, start with a letter, "
                      "and contain only letters, numbers or underscores."))
            return

        self.controller.current_user = username
        self.username_entry.delete(0, tk.END)
        self.status_label.config(text="")
        self.controller.show_frame("DashboardScreen")


# ==============================================================================
# DASHBOARD SCREEN
# ==============================================================================

class DashboardScreen(ttk.Frame):
    """Home screen: choose a language and open any feature."""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        main_layout = ttk.Frame(self, padding=30)
        main_layout.pack(fill="both", expand=True)

        # Top bar
        top_bar = ttk.Frame(main_layout)
        top_bar.pack(fill="x", pady=(0, 20))

        self.welcome_label = ttk.Label(top_bar, text="Welcome, Learner!",
                                       style="Header.TLabel")
        self.welcome_label.pack(side="left")

        ttk.Button(top_bar, text="Logout", style="Secondary.TButton",
                   command=self.controller.logout).pack(side="right")
        ttk.Button(top_bar, text="📊 My Progress", style="Secondary.TButton",
                   command=lambda: self.controller.show_frame("ProgressScreen")
                   ).pack(side="right", padx=(0, 10))

        # Language selection
        lang_section = ttk.Frame(main_layout)
        lang_section.pack(fill="x", pady=(0, 25))

        ttk.Label(lang_section, text="Select Language:",
                  style="Body.TLabel").pack(anchor="w", pady=(0, 8))

        self.selected_lang_var = tk.StringVar(value=self.controller.selected_language)

        lang_btn_frame = ttk.Frame(lang_section)
        lang_btn_frame.pack(fill="x")

        for language in LANGUAGES:
            ttk.Radiobutton(lang_btn_frame, text=language, value=language,
                            variable=self.selected_lang_var,
                            command=self.on_language_change
                            ).pack(side="left", padx=(0, 20))

        # Navigation cards
        grid_frame = ttk.Frame(main_layout)
        grid_frame.pack(fill="both", expand=True)

        grid_frame.rowconfigure(0, weight=1)
        grid_frame.rowconfigure(1, weight=1)
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)

        cards = (
            (0, 0, "📖 Browse Lessons", "Study vocabulary grouped by topics", "LessonScreen"),
            (0, 1, "📝 Practice Quiz", "Test your knowledge and earn scores", "QuizScreen"),
            (1, 0, "🌐 Instant Translator",
             "Translate English phrases using MyMemory API", "TranslatorScreen"),
            (1, 1, "🤖 AI Tutor", "Ask grammar questions and get feedback", "TutorScreen"),
        )
        for row, col, title, description, target in cards:
            self._create_nav_card(grid_frame, row, col, title, description,
                                  lambda name=target: self.controller.show_frame(name))

    def _create_nav_card(self, parent, row, col, title, description, command):
        """Create a dashboard navigation card."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=20)
        card.grid(row=row, column=col, sticky="nsew", padx=10, pady=10)

        ttk.Label(card, text=title, font=("Segoe UI", 13, "bold"),
                  background="#FFFFFF").pack(anchor="w", pady=(0, 5))
        ttk.Label(card, text=description, font=("Segoe UI", 10),
                  foreground="#64748B", background="#FFFFFF",
                  wraplength=300).pack(anchor="w", pady=(0, 15))
        ttk.Button(card, text="Open", style="Primary.TButton",
                   command=command).pack(anchor="e")

    def on_show(self):
        if self.controller.current_user:
            self.welcome_label.config(text=f"Welcome, {self.controller.current_user}!")
        self.selected_lang_var.set(self.controller.selected_language)

    def on_language_change(self):
        """Save the selected language globally."""
        self.controller.selected_language = self.selected_lang_var.get()


# ==============================================================================
# LESSON SCREEN
# ==============================================================================

class LessonScreen(ttk.Frame):
    """
    Lesson screen. Flow:
        LessonScreen -> FileManager -> lessons.json -> Lesson/Word objects -> Treeview
    """

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        main_layout = ttk.Frame(self, padding=25)
        main_layout.pack(fill="both", expand=True)

        # Header
        header_frame = ttk.Frame(main_layout)
        header_frame.pack(fill="x", pady=(0, 15))

        ttk.Button(header_frame, text="← Dashboard", style="Secondary.TButton",
                   command=lambda: self.controller.show_frame("DashboardScreen")
                   ).pack(side="left")

        self.title_label = ttk.Label(header_frame, text="Vocabulary Lessons",
                                     style="Header.TLabel")
        self.title_label.pack(side="left", padx=20)

        # Topic selector
        topic_frame = ttk.Frame(main_layout)
        topic_frame.pack(fill="x", pady=(0, 15))

        ttk.Label(topic_frame, text="Select Topic:",
                  style="Body.TLabel").pack(side="left")

        self.topic_var = tk.StringVar(value=self.controller.selected_topic)

        for topic in TOPICS:
            ttk.Radiobutton(topic_frame, text=topic, value=topic,
                            variable=self.topic_var,
                            command=self.load_lessons).pack(side="left", padx=10)

        # Error/status message
        self.status_label = ttk.Label(main_layout, text="", foreground="red",
                                      font=("Segoe UI", 10))
        self.status_label.pack(fill="x", pady=(0, 8))

        # Vocabulary table
        table_frame = ttk.Frame(main_layout)
        table_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(table_frame, columns=("english", "translation"),
                                 show="headings", selectmode="browse")
        self.tree.heading("english", text="English Word")
        self.tree.heading("translation", text="Translation")
        self.tree.column("english", width=300, anchor="w")
        self.tree.column("translation", width=300, anchor="w")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical",
                                  command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def on_show(self):
        """Refresh lessons when this screen becomes visible."""
        self.topic_var.set(self.controller.selected_topic)
        self.load_lessons()

    def load_lessons(self):
        """Load the selected language and topic into the table."""
        for row in self.tree.get_children():
            self.tree.delete(row)

        self.status_label.config(text="")

        language = self.controller.selected_language
        topic = self.topic_var.get()
        self.controller.selected_topic = topic
        self.title_label.config(text=f"{language} - {topic}")

        try:
            lessons_data = self.controller.file_manager.load_lessons()

            # lessons.json uses lowercase language/topic keys
            language_key = language.lower()
            topic_key = topic.lower()

            if language_key not in lessons_data:
                raise LessonNotFoundError(f"No lessons found for {language}.")
            if topic_key not in lessons_data[language_key]:
                raise LessonNotFoundError(f"No {topic} lessons found for {language}.")

            lesson = Lesson.from_data(language, topic, lessons_data[language_key][topic_key])

            for word in lesson.words:
                self.tree.insert("", "end", values=(word.english, word.native))

        except LessonNotFoundError as error:
            self.status_label.config(text=str(error))

        except DataFileError as error:
            self.status_label.config(text=f"Could not load lessons: {error}")

        except (KeyError, TypeError, ValueError):
            self.status_label.config(text="The lesson data is not in the expected format.")


# ==============================================================================
# ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    app = LingoNaijaApp()
    app.mainloop()
