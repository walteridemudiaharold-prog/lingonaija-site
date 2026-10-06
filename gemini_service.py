"""gemini_service.py - Gemini AI tutor (Member 8).

Set your key first (Command Prompt):  set GEMINI_API_KEY=your_key
                      (PowerShell):      $env:GEMINI_API_KEY="your_key"
                      (Mac/Linux):       export GEMINI_API_KEY=your_key

The default model is gemini-3.5-flash. If Google retires it, switch without
editing code by setting GEMINI_MODEL (for example gemini-3.1-flash-lite).
Current names: https://ai.google.dev/gemini-api/docs/deprecations
"""
import os

import requests

from exceptions import TutorError

DEFAULT_MODEL = "gemini-3.5-flash"
URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiService:
    def _ask(self, prompt):
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise TutorError("No GEMINI_API_KEY set.")
        try:
            model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
            response = requests.post(
                URL_TEMPLATE.format(model=model),
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=20,
            )
            response.raise_for_status()
            return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except requests.Timeout:
            raise TutorError("The AI tutor timed out.")
        except requests.RequestException:
            raise TutorError("The AI tutor is not reachable (check your key and internet).")
        except (KeyError, IndexError, ValueError):
            raise TutorError("The AI tutor sent an unexpected reply.")

    def explain_wrong_answer(self, language, question, user_answer, correct):
        prompt = (
            f"You are a friendly {language.title()} tutor for a beginner. "
            f"Question: {question} The learner answered '{user_answer}' but the correct "
            f"answer is '{correct}'. In under 60 words, explain the difference "
            f"and give one tip to remember it."
        )
        return self._ask(prompt)

    def answer_question(self, language, question):
        prompt = (
            f"You are a friendly {language.title()} tutor for a beginner. "
            f"Answer in under 100 words, with a simple example: {question}"
        )
        return self._ask(prompt)
