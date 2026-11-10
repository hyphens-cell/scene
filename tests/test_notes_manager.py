import json

import pytest

from pdf_presenter.core.notes_manager import NotesManager
from pdf_presenter.core.storage import StorageError

DIGEST = "a" * 64


def test_notes_round_trip_unicode_and_delete(tmp_path):
    notes = NotesManager(DIGEST, tmp_path)
    notes.set(16, "Заметки\nҚазақша — текст")
    notes.set(34, "Slide 35")
    notes.save()
    assert not notes.dirty
    loaded = NotesManager(DIGEST, tmp_path)
    assert loaded.get(16) == "Заметки\nҚазақша — текст"
    assert loaded.get(34) == "Slide 35"
    loaded.set(16, "")
    loaded.save()
    assert NotesManager(DIGEST, tmp_path).get(16) == ""
    assert json.loads(loaded.path.read_text(encoding="utf-8"))["document_sha256"] == DIGEST


def test_backup_recovery_preserves_corrupt_file(tmp_path):
    notes = NotesManager(DIGEST, tmp_path)
    notes.set(0, "first")
    notes.save()
    notes.set(0, "second")
    notes.save()
    notes.path.write_text("broken", encoding="utf-8")
    restored = NotesManager(DIGEST, tmp_path)
    assert restored.get(0) == "first" and restored.warning
    assert notes.path.read_text() == "broken"


def test_corrupt_without_backup_is_not_overwritten(tmp_path):
    path = tmp_path / "notes" / f"{DIGEST}.json"
    path.parent.mkdir()
    path.write_text("broken")
    with pytest.raises(StorageError):
        NotesManager(DIGEST, tmp_path)
    assert path.read_text() == "broken"


def test_failed_atomic_replace_retains_previous_and_dirty(tmp_path, monkeypatch):
    notes = NotesManager(DIGEST, tmp_path)
    notes.set(0, "old")
    notes.save()
    notes.set(0, "new")

    def fail(*args):
        raise PermissionError("locked")

    monkeypatch.setattr("pdf_presenter.core.storage.os.replace", fail)
    with pytest.raises(StorageError):
        notes.save()
    assert notes.dirty
    assert NotesManager(DIGEST, tmp_path).get(0) == "old"
    assert not list(notes.path.parent.glob("*.tmp"))


@pytest.mark.parametrize("digest", ["../escape", "g" * 64, "a" * 63])
def test_fingerprint_validation(digest, tmp_path):
    with pytest.raises(ValueError):
        NotesManager(digest, tmp_path)
