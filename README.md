# lingonaija-website
It's a desktop application built with Python and Tkinter, That translates words and phases between "English" and three major Nigerian languages: "Hausa, Yoruba, Igbo.

## Tests

Run the test suite from the project directory with:

```sh
python -m unittest discover -s tests -v
```

Application-specific errors are defined in `exceptions.py`. Raise
`InvalidAnswerError` for an answer that cannot be accepted and
`LessonNotFoundError` when a requested lesson is unavailable. Both inherit from
`LingoNaijaError`, so callers can catch either a specific error or the shared
application error base.
