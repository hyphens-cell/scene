"""Frozen-executable check of pywin32, the STA subprocess and native previews."""

import hashlib
import json
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage

from . import __version__
from .backends.powerpoint_com_backend import PowerPointCOMBackend
from .services.com_worker import OfficeService


def run_office_smoke_test(app, directory: Path, source: Path) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    report = {"success": False, "version": __version__, "source": str(source)}
    service = OfficeService("powerpoint")
    backend = PowerPointCOMBackend(service)
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    closing = False

    def finish(error=""):
        nonlocal closing
        if closing:
            return
        closing = True
        if error:
            report["error"] = str(error)
        backend.dispose()
        service.close()
        await_closed()

    def await_closed():
        if service._process is not None:
            QTimer.singleShot(100, await_closed)
            return
        unchanged = hashlib.sha256(source.read_bytes()).hexdigest() == original
        report["source_unchanged"] = unchanged
        report["success"] = not report.get("error") and unchanged and report.get("preview", False)
        (directory / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        app.exit(0 if report["success"] else 1)

    def loaded(document):
        report.update(
            slides=document.page_count, notes=len(document.native_notes), backend=backend.kind
        )
        backend.get_preview(0)

    def ready(_, page, raster):
        image = QImage(
            raster.samples, raster.width, raster.height, raster.stride, QImage.Format.Format_RGB888
        )
        report["preview"] = image.save(str(directory / "native-preview.png"))
        finish()

    backend.loaded.connect(loaded)
    backend.ready.connect(ready)
    backend.load_failed.connect(lambda _, message: finish(message))
    backend.failed.connect(finish)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(lambda: finish("Office self-test timed out"))
    deadline.start(65000)
    QTimer.singleShot(0, lambda: backend.load(str(source)))
    return app.exec()
