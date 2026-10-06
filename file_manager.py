"""file_manager.py - All file handling for LingoNaija."""
import csv
import json
import logging
import os

from exceptions import DataFileError, LessonNotFoundError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    filename=os.path.join(BASE_DIR, "lingonaija.log"),
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s %(message)s",
)


class FileManager:
    """Reads and writes lessons.json, users.json and results.csv."""

    CSV_HEADER = ["username", "language", "topic", "question_type", "score", "total", "timestamp"]

    def __init__(self, base_dir=BASE_DIR):
        self.lessons_path = os.path.join(base_dir, "lessons.json")
        self.users_path = os.path.join(base_dir, "users.json")
        self.results_path = os.path.join(base_dir, "results.csv")

    # ---------- JSON helpers ----------
    def _read_json(self, path, default=None):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            if default is not None:
                return default
            logging.error("File not found: %s", path)
            raise DataFileError(f"File not found: {os.path.basename(path)}")
        except json.JSONDecodeError as exc:
            logging.error("Bad JSON in %s: %s", path, exc)
            raise DataFileError(f"{os.path.basename(path)} is damaged or not valid JSON.")

    def _write_json(self, path, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            logging.error("Could not write %s: %s", path, exc)
            raise DataFileError(f"Could not save {os.path.basename(path)}.")

    # ---------- Lessons ----------
    def load_lessons(self):
        """Return {language: {topic: [{"english":..,"native":..}, ...]}}."""
        try:
            return self._read_json(self.lessons_path)
        except DataFileError as exc:
            raise LessonNotFoundError(str(exc))

    # ---------- Users and progress ----------
    def load_users(self):
        return self._read_json(self.users_path, default={})

    def save_result(self, username, entry):
        """Save one quiz result to users.json and append it to results.csv."""
        users = self.load_users()
        users.setdefault(username, {"history": []})["history"].append(entry)
        self._write_json(self.users_path, users)
        self._append_csv(username, entry)

    def _append_csv(self, username, entry):
        self._rotate_old_csv()
        new_file = not os.path.exists(self.results_path) or os.path.getsize(self.results_path) == 0
        try:
            with open(self.results_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if new_file:
                    writer.writerow(self.CSV_HEADER)
                writer.writerow([username, entry["language"], entry["topic"],
                                 entry["question_type"], entry["score"], entry["total"],
                                 entry["timestamp"]])
        except OSError as exc:
            logging.error("Could not write results.csv: %s", exc)
            raise DataFileError("Could not save results.csv.")

    def _rotate_old_csv(self):
        """If results.csv has an old/different header, keep it as results_old.csv."""
        if not os.path.exists(self.results_path) or os.path.getsize(self.results_path) == 0:
            return
        try:
            with open(self.results_path, newline="", encoding="utf-8") as f:
                header = next(csv.reader(f), [])
            if header != self.CSV_HEADER:
                os.replace(self.results_path,
                           os.path.join(os.path.dirname(self.results_path), "results_old.csv"))
        except (OSError, csv.Error) as exc:
            logging.error("Could not check results.csv header: %s", exc)
            raise DataFileError("Could not read results.csv.")
