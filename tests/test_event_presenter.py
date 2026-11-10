import json
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication

from pdf_presenter.backends.converted_pdf_backend import ConvertedPDFBackend
from pdf_presenter.core.audience_display_manager import AudienceMode
from pdf_presenter.core.backend_manager import BackendManager, EngineAvailability
from pdf_presenter.core.presentation_queue import QueueState
from pdf_presenter.ui.presenter_window import PresenterWindow


@pytest.fixture
def event_window(qtbot, tmp_path, monkeypatch):
    window = PresenterWindow(tmp_path / "data")
    qtbot.addWidget(window)
    errors = []
    monkeypatch.setattr(window, "_warning", errors.append)
    window.errors = errors
    window.show()
    yield window
    window._project_dirty = False
    window.close()


def wait_document(qtbot, window, path):
    qtbot.waitUntil(
        lambda: (
            window.document is not None and window.document.path == str(path) and not window.loading
        ),
        timeout=15000,
    )
    qtbot.waitUntil(lambda: not window.current_slide.image.isNull(), timeout=15000)


def test_live_pdf_queue_switch_restores_slides_notes_and_timer(event_window, qtbot, pdf_factory):
    window = event_window
    first, second = pdf_factory(5, "first.pdf"), pdf_factory(4, "second.pdf")
    entries = window.queue.add([first, second])
    window.load_item(entries[0].id)
    wait_document(qtbot, window, first)
    window.slides.go_to(3)
    window.notes_panel.editor.setPlainText("First private note")
    assert window.save_notes()
    window.start_presentation(True)
    assert not window.navigation.play_video.isEnabled(), "PDF does not support native video"
    started = window.timer._started
    window.adjacent_file(1)
    wait_document(qtbot, window, second)
    assert window.presentation.active and window.audience.isVisible()
    assert window.timer._started == started
    window.slides.go_to(2)
    window.notes_panel.editor.setPlainText("Second private note")
    assert window.save_notes()
    window.adjacent_file(-1)
    wait_document(qtbot, window, first)
    assert window.slides.current == 3
    assert window.notes_panel.editor.toPlainText() == "First private note"
    assert window.queue.get(entries[1].id).last_slide == 2
    assert window.timer._started == started and not window.errors


def test_multiple_drop_and_project_restore(event_window, qtbot, pdf_factory, tmp_path, monkeypatch):
    window = event_window
    paths = [pdf_factory(2, "one.pdf"), pdf_factory(3, "two.pdf")]
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    drag = QDragEnterEvent(
        QPoint(30, 30),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(window, drag)
    drop = QDropEvent(
        QPointF(30, 30),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(window, drop)
    wait_document(qtbot, window, paths[0])
    assert drop.isAccepted() and len(window.queue.items) == 2
    second = window.queue.items[1]
    window.queue.move(second.id, 0)
    window.project.path = tmp_path / "event.pdfpresenter"
    window.project.name = "Lecture"
    assert window.save_project()
    values = json.loads(window.project.path.read_text(encoding="utf-8"))
    assert values["presentations"][0]["path"] == "two.pdf"
    path = str(window.project.path)
    window.open_project(path)
    assert [item.name for item in window.queue.items] == ["two.pdf", "one.pdf"]
    assert window.document is None and not window.presentation.active
    assert not window.errors


def test_preflight_continues_after_missing_file_without_show(
    event_window, qtbot, pdf_factory, tmp_path
):
    window = event_window
    entries = window.queue.add([tmp_path / "missing.pptx", pdf_factory(3)])
    window.backend_manager.availability = EngineAvailability()
    window.preflight_all()
    qtbot.waitUntil(lambda: not window._preflight_running, timeout=15000)
    assert entries[0].state == QueueState.ERROR
    assert entries[1].state == QueueState.READY
    assert entries[1].slide_count == 3
    assert not window.presentation.active and not window.audience.isVisible()
    assert not window.errors
    window._preflight_dialog.close()


def test_failed_file_can_be_retried_without_interrupting_current_show(
    event_window, qtbot, pdf_factory, tmp_path
):
    window = event_window
    original = pdf_factory(3, "original.pdf")
    broken = tmp_path / "repaired.pdf"
    broken.write_bytes(b"not a PDF")
    entries = window.queue.add([original, broken])
    window.load_item(entries[0].id)
    wait_document(qtbot, window, original)
    window.start_presentation()
    started = window.timer._started

    window.load_item(entries[1].id)
    qtbot.waitUntil(lambda: entries[1].state == QueueState.ERROR and not window.loading)
    assert window.document.path == str(original)
    assert window.presentation.active and window.audience.isVisible()

    pdf_factory(2, "repaired.pdf")
    window.load_item(entries[1].id)
    wait_document(qtbot, window, broken)
    assert window.queue.active_id == entries[1].id
    assert window.presentation.active and window.audience.isVisible()
    assert window.timer._started == started
    assert len(window.errors) == 1


def test_audience_modes_and_automatic_next_file(event_window, qtbot, pdf_factory):
    window = event_window
    first, second = pdf_factory(1, "short.pdf"), pdf_factory(2, "next.pdf")
    entries = window.queue.add([first, second])
    window.load_item(entries[0].id)
    wait_document(qtbot, window, first)
    window.start_presentation()
    window.set_audience_mode(AudienceMode.SPLASH)
    assert not window.audience.slide.image.isNull()
    assert window.audience_display.mode == AudienceMode.SPLASH
    window.set_audience_mode(AudienceMode.HOLD)
    assert window.audience_display.mode == AudienceMode.HOLD
    window.set_audience_mode(AudienceMode.SLIDE)
    window.presentation.toggle_blank("white")
    assert window.audience.slide.blank == "white"
    window.presentation.toggle_blank("white")
    window.project.auto_advance = True
    window.slides.next()
    wait_document(qtbot, window, second)
    assert window.presentation.active and window.queue.active_id == entries[1].id


def test_no_office_pdf_copy_uses_source_identity_and_static_capabilities(
    qtbot, pdf_factory, tmp_path
):
    source = tmp_path / "fallback.pptx"
    source.write_bytes(b"placeholder PPTX")
    pdf_factory(3, "fallback.pdf")
    manager = BackendManager(EngineAvailability())
    backend = manager.create(manager.choose(str(source)))
    assert isinstance(backend, ConvertedPDFBackend)
    failures = []
    backend.load_failed.connect(lambda *args: failures.append(args))
    try:
        backend.load(str(source))
        qtbot.waitUntil(lambda: backend.document is not None or bool(failures), timeout=15000)
        assert not failures
        assert Path(backend.document.path) == source
        assert backend.document.page_count == 3
        capabilities = backend.get_capabilities()
        assert capabilities.compatibility and not capabilities.video and not capabilities.animations
        assert any("не воспроизводятся" in warning for warning in backend.document.warnings)
    finally:
        backend.dispose()


def test_native_commands_use_same_navigation_and_do_not_expose_digits(
    event_window, qtbot, pdf_factory
):
    window = event_window
    path = pdf_factory(50)
    window.load_pdf(str(path))
    wait_document(qtbot, window, path)
    window.start_presentation()
    window._native_command("digit:3")
    window._native_command("digit:5")
    assert window.slides.current == 0
    window._native_command("submit")
    assert window.slides.current == 34
    window._native_command("black")
    assert window.audience.slide.blank == "black"
    window._native_command("escape")
    assert not window.presentation.active


def test_encrypted_pdf_copy_accepts_password_on_retry(qtbot, pdf_factory, tmp_path):
    source = tmp_path / "locked.pptx"
    source.write_bytes(b"source used only for identity")
    pdf_factory(3, "locked.pdf", password="presenter-password")
    backend = ConvertedPDFBackend()
    failures = []
    backend.load_failed.connect(lambda *args: failures.append(args))
    try:
        backend.load(str(source))
        qtbot.waitUntil(lambda: bool(failures), timeout=15000)
        assert failures[-1][0] == "password"
        failures.clear()
        backend.load(str(source), "presenter-password")
        qtbot.waitUntil(lambda: backend.document is not None or bool(failures), timeout=15000)
        assert not failures and backend.document.page_count == 3
        assert backend._password == ""
    finally:
        backend.dispose()
