import json
import shutil
import zipfile

import pytest

from pdf_presenter.backends.base_backend import PresentationBackend
from pdf_presenter.backends.pdf_backend import PDFBackend
from pdf_presenter.core.backend_manager import BackendManager, EngineAvailability
from pdf_presenter.core.capability_model import BackendUnavailable
from pdf_presenter.core.media_inspector import inspect_media
from pdf_presenter.core.presentation_queue import PresentationQueueManager, QueueState
from pdf_presenter.core.project_manager import EventProject, ProjectManager
from pdf_presenter.core.storage import StorageError


def test_abstract_backend_cannot_be_instantiated(qapp):
    with pytest.raises(TypeError, match="abstract"):
        PresentationBackend()


def test_backend_selection_and_missing_office(tmp_path):
    path = tmp_path / "talk.pptx"
    manager = BackendManager(EngineAvailability())
    assert manager.choose(str(path.with_suffix(".pdf"))).kind == "pdf"
    with pytest.raises(BackendUnavailable, match="LibreOffice"):
        manager.choose(str(path))
    path.with_suffix(".pdf").touch()
    assert manager.choose(str(path)).kind == "pdf_copy"
    assert manager.choose(str(path)).warning
    with pytest.raises(BackendUnavailable):
        manager.choose(str(path), "powerpoint")
    manager.availability = EngineAvailability(True, "soffice.exe", True)
    assert manager.choose(str(path)).kind == "powerpoint"
    assert manager.choose(str(path), "libreoffice").kind == "libreoffice"
    assert manager.choose(str(path), "libreoffice_pdf").kind == "libreoffice_pdf"
    manager.availability = EngineAvailability(False, "soffice.exe", True)
    assert manager.choose(str(path)).kind == "libreoffice_pdf"
    assert manager.choose(str(path), "libreoffice").kind == "libreoffice"
    manager.availability = EngineAvailability(False, "soffice.exe", False)
    assert manager.choose(str(path)).kind == "libreoffice_pdf"


def test_queue_reorder_remove_resume_and_error_isolation(qapp, tmp_path):
    queue = PresentationQueueManager()
    first, second, third = queue.add(
        [tmp_path / "a.pdf", tmp_path / "b.pptx", tmp_path / "c.ppt", tmp_path / "ignored.txt"]
    )
    queue.update(second.id, state=QueueState.ERROR, error="broken")
    queue.activate(first.id)
    queue.update(first.id, last_slide=16)
    assert not queue.remove(first.id)
    assert queue.move(third.id, 1)
    assert queue.adjacent(1) is third
    queue.activate(third.id)
    assert first.state == QueueState.COMPLETED
    queue.activate(first.id)
    assert first.last_slide == 16
    assert queue.remove(second.id)
    assert [item.name for item in queue.items] == ["a.pdf", "c.ppt"]


def test_project_roundtrip_and_relocation(qapp, tmp_path):
    directory = tmp_path / "event"
    directory.mkdir()
    document = directory / "lecture.pdf"
    document.write_bytes(b"test document")
    queue = PresentationQueueManager()
    item = queue.add([document], "libreoffice_pdf")[0]
    item.last_slide = 34
    item.notes_ref = "a" * 64
    project = EventProject(
        "Конференция",
        queue.items,
        {"splash_text": "Перерыв"},
        {"audience_monitor": "screen2"},
        True,
    )
    manager = ProjectManager()
    path = manager.save(project, directory / "agenda.pdfpresenter")
    serialized = json.loads(path.read_text(encoding="utf-8"))
    assert serialized["presentations"][0]["path"] == "lecture.pdf"
    moved = tmp_path / "moved"
    shutil.copytree(directory, moved)
    restored, warning = manager.load(moved / path.name)
    assert warning is None
    assert restored.name == "Конференция" and restored.auto_advance
    assert restored.items[0].path == str(moved / "lecture.pdf")
    assert restored.items[0].last_slide == 34 and restored.items[0].notes_ref == "a" * 64
    assert restored.items[0].preferred_backend == "libreoffice_pdf"
    assert restored.items[0].state == QueueState.WAITING
    assert restored.monitor_settings["audience_monitor"] == "screen2"
    serialized["presentations"][0]["last_slide"] = -1
    bad = tmp_path / "bad.pdfpresenter"
    bad.write_text(json.dumps(serialized), encoding="utf-8")
    with pytest.raises(StorageError):
        manager.load(bad)


def test_media_inspection_does_not_play_or_download(tmp_path):
    path = tmp_path / "media.pptx"
    (tmp_path / "present.mp4").write_bytes(b"fake media")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ppt/media/video1.mp4", b"embedded")
        archive.writestr(
            "ppt/slides/slide1.xml", '<p:sld xmlns:p="urn:p"><p:timing/><p:transition/></p:sld>'
        )
        archive.writestr(
            "ppt/slides/_rels/slide1.xml.rels",
            """<Relationships>
            <Relationship Type="urn/video" TargetMode="External" Target="present.mp4"/>
            <Relationship Type="urn/video" TargetMode="External" Target="missing.mp4"/>
            <Relationship Type="urn/audio" TargetMode="External" Target="https://example.invalid/sound.mp3"/>
        </Relationships>""",
        )
    report = inspect_media(str(path))
    assert report.animations and report.transitions
    assert report.embedded == ["ppt/media/video1.mp4"]
    assert report.missing == ["missing.mp4"]
    assert len(report.linked) == 3
    assert any("офлайн" in warning for warning in report.warnings)


def test_pdf_backend_real_render_navigation_and_dispose(qtbot, pdf_factory):
    backend = PDFBackend()
    images = []
    backend.ready.connect(lambda tag, page, raster: images.append((tag, page, raster)))
    backend.load(str(pdf_factory(3)))
    qtbot.waitUntil(lambda: backend.document is not None, timeout=15000)
    assert backend.get_slide_count() == 3
    assert not backend.get_capabilities().video
    backend.start(1)
    assert backend.active and backend.get_current_slide() == 1
    backend.get_preview(1)
    qtbot.waitUntil(lambda: bool(images), timeout=10000)
    assert images[0][1] == 1 and images[0][2].samples
    assert backend.next() and backend.current == 2
    assert not backend.next()
    assert backend.previous() and backend.current == 1
    backend.dispose()
    assert backend.disposed and not backend.active
    assert backend.renderer._worker is None
