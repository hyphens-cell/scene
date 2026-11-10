import pytest

from pdf_presenter.core.settings_manager import SettingsManager
from pdf_presenter.core.storage import StorageError


def test_settings_and_recent_limit(tmp_path):
    settings = SettingsManager(tmp_path)
    for i in range(12):
        settings.add_recent(tmp_path / f"{i}.pdf")
    settings.add_recent(tmp_path / "7.pdf")
    settings.set("notes_font", 22)
    settings.save()
    loaded = SettingsManager(tmp_path)
    assert loaded.get("notes_font") == 22
    assert len(loaded.get("recent_files")) == 10
    assert loaded.get("recent_files")[0].endswith("7.pdf")


def test_corrupt_settings_read_only(tmp_path):
    (tmp_path / "settings.json").write_text('{"version": 1, "settings": {"notes_font": "oops"}}')
    settings = SettingsManager(tmp_path)
    assert settings.warning and settings.read_only
    with pytest.raises(StorageError):
        settings.save()


def test_settings_backup(tmp_path):
    settings = SettingsManager(tmp_path)
    settings.set("notes_font", 18)
    settings.save()
    settings.set("notes_font", 20)
    settings.save()
    settings.path.write_bytes(b"\xff")
    restored = SettingsManager(tmp_path)
    assert restored.get("notes_font") == 18
    assert restored.warning
