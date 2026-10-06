"""translation_service.py - MyMemory translation API."""
import requests

from exceptions import TranslationError

API_URL = "https://api.mymemory.translated.net/get"
LANG_CODES = {"yoruba": "yo", "igbo": "ig", "hausa": "ha"}


class TranslationService:
    def translate(self, text, language):
        """Translate English text into the given Nigerian language."""
        code = LANG_CODES.get(language.lower())
        if code is None:
            raise TranslationError(f"Unsupported language: {language}")
        try:
            response = requests.get(
                API_URL, params={"q": text, "langpair": f"en|{code}"}, timeout=10
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout:
            raise TranslationError("The translation service timed out. Try again.")
        except requests.RequestException:
            raise TranslationError("Could not reach the translation service. Check your internet.")
        except ValueError:
            raise TranslationError("The translation service sent an unreadable reply.")

        if int(data.get("responseStatus", 0)) != 200:
            raise TranslationError(str(data.get("responseDetails", "Translation failed.")))
        return data["responseData"]["translatedText"]
