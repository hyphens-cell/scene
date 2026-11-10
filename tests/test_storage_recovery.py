import json

from pdf_presenter.core.notes_manager import NotesManager


def test_valid_json_wrong_schema_cannot_replace_good_backup(tmp_path):
    notes = NotesManager("f" * 64, tmp_path)
    notes.set(0, "good backup")
    notes.save()
    notes.set(0, "second revision")
    notes.save()
    backup = notes.path.with_suffix(".json.bak")
    original_backup = backup.read_bytes()
    notes.path.write_text(json.dumps({"version": 999}), encoding="utf-8")
    recovered = NotesManager("f" * 64, tmp_path)
    assert recovered.get(0) == "good backup"
    recovered.set(0, "new revision")
    recovered.save()
    assert backup.read_bytes() == original_backup
    assert NotesManager("f" * 64, tmp_path).get(0) == "new revision"
