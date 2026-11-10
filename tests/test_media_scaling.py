import json
import struct
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from pdf_presenter.backends.image_backend import ImageBackend
from pdf_presenter.core.media_layout import media_rect
from pdf_presenter.core.presentation_queue import PresentationItem
from pdf_presenter.core.project_manager import EventProject, ProjectManager
from pdf_presenter.core.storage import StorageError
from pdf_presenter.ui.presenter_window import PresenterWindow
from pdf_presenter.ui.slide_widget import SlideWidget, raster_image


def striped_image():
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    image.fill(QColor("green"))
    painter = QPainter(image)
    painter.fillRect(0, 0, 100, 200, QColor("red"))
    painter.fillRect(300, 0, 100, 200, QColor("blue"))
    painter.end()
    return image


def test_audience_crop_preview_and_panning_match(qtbot):
    audience, preview = SlideWidget(True), SlideWidget()
    for widget in (audience, preview):
        qtbot.addWidget(widget)
        widget.image = striped_image()
        widget.resize(200, 200)
        widget.show()
    preview.resize(400, 200)
    settings = {"scale": "fill"}
    audience.set_media_view((400, 200), settings)
    preview.set_media_view((400, 200), settings, (200, 200))
    assert audience.grab().toImage().pixelColor(5, 100) == QColor("green")
    assert preview.grab().toImage().pixelColor(105, 100) == QColor("green")
    moved = []
    preview.panned.connect(lambda x, y: moved.append((x, y)))
    qtbot.mousePress(preview, Qt.MouseButton.LeftButton, pos=QPoint(150, 100))
    qtbot.mouseMove(preview, QPoint(250, 100))
    qtbot.mouseRelease(preview, Qt.MouseButton.LeftButton, pos=QPoint(250, 100))
    assert moved[-1] == (-1, 0)
    audience.set_media_view((400, 200), preview.view_settings)
    assert audience.grab().toImage().pixelColor(5, 100) == QColor("red")
    assert preview.grab().toImage().pixelColor(105, 100) == QColor("red")
    for mode, expected in [
        ("fit", (200, 100)),
        ("fill", (400, 200)),
        ("stretch", (200, 200)),
        ("actual", (400, 200)),
        ("zoom", (800, 400)),
    ]:
        rect = media_rect(QRectF(0, 0, 200, 200), (400, 200), {"scale": mode, "zoom": 200})
        assert (rect.width(), rect.height()) == expected
    assert media_rect(QRectF(0, 0, 200, 200), (400, 200), {"scale": "actual"}, 2).width() == 200


def test_media_settings_project_roundtrip_and_legacy_default(tmp_path):
    settings = {"scale": "zoom", "zoom": 250, "volume": 24, "pan_x": -0.5, "pan_y": 1}
    item = PresentationItem(str(tmp_path / "clip.mp4"), media_settings=settings)
    manager = ProjectManager()
    path = manager.save(EventProject(items=[item]), tmp_path / "event.pdfpresenter")
    restored, warning = manager.load(path)
    assert not warning and restored.items[0].media_settings == settings
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["presentations"][0]["media_settings"]
    legacy = tmp_path / "legacy.pdfpresenter"
    legacy.write_text(json.dumps(data), encoding="utf-8")
    assert manager.load(legacy)[0].items[0].media_settings == {}


@pytest.mark.parametrize(
    "settings",
    [
        {"scale": []},
        {"scale": "bad"},
        {"zoom": 0},
        {"zoom": True},
        {"volume": 101},
        {"pan_x": 2},
        {"pan_y": float("nan")},
    ],
)
def test_invalid_media_settings_are_rejected(tmp_path, settings):
    item = PresentationItem(str(tmp_path / "a.png"), media_settings=settings)
    with pytest.raises(StorageError):
        ProjectManager().save(EventProject(items=[item]), tmp_path / "invalid.pdfpresenter")


def test_image_decoder_handles_exif_svg_alpha_and_damage(qtbot, tmp_path):
    jpeg = tmp_path / "rotated.jpg"
    assert striped_image().save(str(jpeg))
    # A minimal EXIF orientation tag, 6 = rotate 90 degrees clockwise.
    tiff = b"II" + struct.pack("<HIH", 42, 8, 1) + struct.pack("<HHIHHI", 274, 3, 1, 6, 0, 0)
    exif = b"Exif\0\0" + tiff
    data = jpeg.read_bytes()
    jpeg.write_bytes(data[:2] + b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif + data[2:])
    svg = tmp_path / "vector.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
        '<rect width="100" height="100" fill="#00ff00"/><text x="110" y="40">SVG</text></svg>'
    )
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"broken image")
    for path, dimensions in [(jpeg, (200, 400)), (svg, (200, 100)), (broken, None)]:
        backend = ImageBackend()
        errors, frames = [], []
        backend.load_failed.connect(lambda *args, errors=errors: errors.append(args))
        backend.ready.connect(lambda *args, frames=frames: frames.append(args))
        try:
            backend.load(str(path))
            qtbot.waitUntil(
                lambda backend=backend, errors=errors: backend.document is not None or bool(errors),
                timeout=15000,
            )
            if dimensions is None:
                assert errors and backend.document is None
                continue
            assert not errors and backend.document.page_sizes == (dimensions,)
            backend.request("current", 0, *dimensions)
            qtbot.waitUntil(lambda frames=frames: bool(frames), timeout=10000)
            if path == svg:
                image = raster_image(frames[0][2])
                assert image.pixelColor(20, 80) == QColor("#00ff00")
                assert image.pixelColor(180, 80) == QColor("black")
        finally:
            backend.dispose()


def test_image_pdf_queue_scale_hold_and_restore(qtbot, tmp_path, pdf_factory, monkeypatch):
    path = tmp_path / "picture.png"
    striped_image().save(str(path))
    window = PresenterWindow(tmp_path / "data")
    qtbot.addWidget(window)
    errors = []
    monkeypatch.setattr(window, "_warning", errors.append)
    window.show()
    entries = window.queue.add([path, pdf_factory(2)])
    try:
        window.load_item(entries[0].id)
        qtbot.waitUntil(lambda: window.document is not None and not window.loading, timeout=15000)
        window.navigation.scale.mode.setCurrentIndex(window.navigation.scale.mode.findData("zoom"))
        window.navigation.scale.zoom.setValue(350)
        assert entries[0].media_settings["zoom"] == 350
        window.start_presentation()
        qtbot.waitUntil(lambda: not window.audience.slide.image.isNull(), timeout=10000)
        window.set_audience_mode("hold")
        assert window.audience.slide.view_source is None, "A held crop must not be zoomed twice"
        window.set_audience_mode("slide")
        assert window.audience.slide.view_settings["zoom"] == 350
        started = window.timer._started
        window.load_item(entries[1].id)
        qtbot.waitUntil(lambda: window.queue.active_id == entries[1].id, timeout=15000)
        assert (
            window.current_slide.view_source is None and window.audience.slide.view_source is None
        )
        assert not window.navigation.scale.isVisible()
        window.load_item(entries[0].id)
        qtbot.waitUntil(lambda: window.queue.active_id == entries[0].id, timeout=15000)
        assert window.navigation.scale.zoom.value() == 350
        assert window.timer._started == started and not errors
        window.resize(1024, 768)
        qtbot.wait(100)
        output = Path("artifacts/scene-ui")
        output.mkdir(exist_ok=True)
        window.grab().save(str(output / "image-small.png"))
    finally:
        window._project_dirty = False
        window.close()
