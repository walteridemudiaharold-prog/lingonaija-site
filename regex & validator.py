"""validator.py - Regex helpers for LingoNaija (Member 6)."""
import re
import unicodedata


class Validator:
    """Input validation and answer normalisation using regular expressions."""

    # Username: starts with a letter, then letters/digits/underscore, 3-16 chars total
    USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,15}$")
    # Combining accent marks (tone marks, underdots) left after Unicode decomposition
    ACCENT_PATTERN = re.compile(r"[\u0300-\u036f]")
    # Anything that is not a word character or whitespace (punctuation, symbols)
    PUNCT_PATTERN = re.compile(r"[^\w\s]")
    WHITESPACE_PATTERN = re.compile(r"\s+")
    # At least one letter (not a digit, not underscore, not a symbol)
    LETTER_PATTERN = re.compile(r"[^\W\d_]")
    # A word made of letters only; allows an inner apostrophe or hyphen (e.g. o'ma, a-ma)
    WORD_PATTERN = re.compile(r"[^\W\d_]+(?:['\u2019-][^\W\d_]+)*")
    # Hausa letters that Unicode cannot decompose into base letter + accent
    HAUSA_MAP = str.maketrans({"\u0253": "b", "\u0257": "d", "\u0199": "k"})  # ɓ ɗ ƙ

    @classmethod
    def validate_username(cls, username):
        """Return True if the username is valid, else False."""
        return bool(cls.USERNAME_PATTERN.fullmatch(username or ""))

    @classmethod
    def normalize_answer(cls, text):
        """Make a quiz answer lenient for comparison: 'Ẹ kú àárọ̀!' -> 'e ku aaro'."""
        if not isinstance(text, str):
            return ""
        text = text.lower().translate(cls.HAUSA_MAP)
        text = unicodedata.normalize("NFD", text)       # split letters from accents
        text = cls.ACCENT_PATTERN.sub("", text)         # remove tone marks / underdots
        text = cls.PUNCT_PATTERN.sub("", text)          # remove punctuation
        return cls.WHITESPACE_PATTERN.sub(" ", text).strip()

    @classmethod
    def answers_match(cls, user_answer, correct_answer):
        """Lenient comparison used by Question.check_answer()."""
        return cls.normalize_answer(user_answer) == cls.normalize_answer(correct_answer)

    @classmethod
    def clean_translation_input(cls, text, max_length=500):
        """Return tidy text for the translator, or "" if it is not usable.

        Only whitespace is tidied: punctuation and accents are kept because
        they are part of the meaning of the text being translated.
        """
        if not isinstance(text, str):
            return ""
        text = cls.WHITESPACE_PATTERN.sub(" ", text).strip()
        if not cls.LETTER_PATTERN.search(text):         # needs at least one letter
            return ""
        return text[:max_length]

    @classmethod
    def extract_words(cls, text):
        """Return the list of words found in pasted text."""
        return cls.WORD_PATTERN.findall(text or "")


if __name__ == "__main__":
    v = Validator

    # Usernames
    assert v.validate_username("Gbemi_01")
    assert not v.validate_username("1gbemi")
    assert not v.validate_username("ab")
    assert not v.validate_username("has space")
    assert not v.validate_username(None)

    # Quiz answers
    assert v.normalize_answer("  Ẹ kú àárọ̀!! ") == "e ku aaro"
    assert v.normalize_answer("Ọmọ") == "omo"
    assert v.normalize_answer("ƙofa, ɗaki") == "kofa daki"
    assert v.normalize_answer(None) == ""
    assert v.answers_match("Ẹ kú àárọ̀", "e ku aaro")
    assert not v.answers_match("e ku irole", "e ku aaro")

    # Translator input
    assert v.clean_translation_input("  Good   morning,  Grandma! ") == "Good morning, Grandma!"
    assert v.clean_translation_input("   ") == ""
    assert v.clean_translation_input("123 !!!") == ""
    assert v.clean_translation_input(None) == ""
    assert len(v.clean_translation_input("a" * 600)) == 500

    # Word extraction
    assert v.extract_words("Nna, 3 ụmụ-nwa o'ma!") == ["Nna", "ụmụ-nwa", "o'ma"]

    print("All validator tests passed")
