LingoNaija

A Python desktop app for learning Nigerian languages: Yoruba, Igbo, and Hausa. Built with Python and Tkinter as a group project (Group 1).

Why LingoNaija?

Most language apps ignore Nigerian languages. Many young Nigerians and people in the diaspora cannot speak, read, or write their heritage languages, and few tools give instant feedback and explanations. LingoNaija makes these languages easy to practise.

Features
Lessons: vocabulary grouped into topics (greetings, food, family) for each language
Quizzes: multiple-choice and translation questions, with scores
Translator: English to Yoruba, Igbo, or Hausa. It checks a built-in offline dictionary first, then the MyMemory Translation API
AI Tutor: uses the Google Gemini API to explain wrong answers and answer questions about words and grammar. If the API is unavailable, the app shows an error message and keeps working
Progress tracking: quiz scores are saved per username so learners can come back later
Requirements
Python 3.10 or newer
Tkinter (included with the standard Python installer on Windows and macOS; on Linux run sudo apt install python3-tk)
The requests library (listed in requirements.txt)
A Google Gemini API key (only needed for the AI Tutor)
Installation
Clone the repository:
   git clone https://github.com/walteridemudiaharold-prog/lingonaija-site.git
   cd lingonaija-site
Install the dependencies:
   pip install -r requirements.txt
Set your Gemini API key as an environment variable so it is never committed to GitHub. Windows (PowerShell):
   $env:GEMINI_API_KEY="your-key-here"

macOS / Linux:

   export GEMINI_API_KEY="your-key-here"

Optional: set GEMINI_MODEL to use a different Gemini model than the default.

How to run

From the project folder:

python main.py

The LingoNaija window opens on the login screen. Enter a username to start. If no API key is set, the app still works, but the AI Tutor shows an error message.

When you take a quiz, the app creates users.json and results.csv in the project folder to store progress. It also writes errors to lingonaija.log. These files are ignored by Git.

Running the tests

From the project folder:

python -m unittest discover -s tests -v

The tests need no internet, API key, or GUI. They cover username and answer validation, quiz scoring, loading every lesson, saving and reloading progress, damaged or missing data files, and the error messages the translator and AI Tutor give when they fail. Test data is written to a temporary folder, so your real users.json and results.csv are never touched.

Project structure
main.py                 Starts the app
GUI_1.py                Main window, navigation, Login, Dashboard, Lesson screens
GUI_2.py                Quiz, Translator, Tutor, and Progress screens
models.py               OOP models: User, Lesson, Word, Quiz, ProgressTracker, Question types
file_manager.py         Reads and writes lessons, users, and results (JSON/CSV)
translation_service.py  MyMemory translation API calls
gemini_service.py       Gemini AI tutor calls
regex_validator.py      Input validation and answer normalisation (regex)
exceptions.py           Custom exception classes
lessons.json            Lesson vocabulary data
requirements.txt        Python dependencies
tests/test_lingonaija.py  Automated tests (validator, models, files, service errors)
Architecture

The app has four layers, and each layer only talks to the one below it:

GUI layer: Login, Dashboard, Lesson, Quiz, Translator, Tutor, and Progress screens
Logic layer (OOP): User, Lesson, Word, Quiz, ProgressTracker, and the Question base class with MultipleChoiceQuestion and TranslationQuestion
Services layer: TranslationService, GeminiService, and Validator
Data layer: FileManager reads and writes lessons, users, and results
Course topics applied
Topic	Where it is used
File handling	Load lessons from JSON; save users and progress; export results to CSV; write an error log
Exception handling	Custom exceptions; handling of missing files, bad JSON, network timeouts, and API failures
Regex	Username validation and lenient answer matching
OOP	Inheritance, polymorphism, encapsulation, composition
GUI	Multi-screen Tkinter app
Tech stack

Python 3, Tkinter (ttk), JSON and CSV storage, MyMemory Translation API, Google Gemini API, Git and GitHub.

Team (Group 1)
Member	Role
Adzimeh Anzewu	Project Lead / Integration
Sambo Daniel	GUI 1
Walter Idemudia Harold	GUI 2
Aruwa Muhammed Ma'aruf	OOP Models
Joseph Anumodu	File Handling
Faith Aduloju	Regex and Validation
Muhammed-Nazeer Garba	Exception Handling and Testing
Abigail Angakuru	APIs and AI
