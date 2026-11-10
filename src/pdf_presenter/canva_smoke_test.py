"""Opt-in verification of the packaged WebView2 worker and public Canva viewer."""

import json
import sys
import time
import traceback
from pathlib import Path

import pymupdf
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest

from . import __version__
from .core.audience_display_manager import AudienceMode
from .ui.presenter_window import PresenterWindow


def run_canva_smoke_test(app, output: Path, source: str) -> int:
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "success": False,
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
    }
    errors = []
    window = PresenterWindow(output / "appdata")
    window._warning = errors.append
    app.setQuitOnLastWindowClosed(False)

    def wait_for(predicate, timeout=20):
        deadline = time.monotonic() + timeout
        while not predicate():
            if errors:
                raise AssertionError(errors)
            if time.monotonic() > deadline:
                raise TimeoutError("Canva acceptance step timed out")
            QTest.qWait(50)

    def scenario():
        service = None
        try:
            assert (Path(__file__).parent / "resources" / "canva_adapter.js").is_file()
            pdf = output / "next.pdf"
            with pymupdf.open() as document:
                page = document.new_page()
                page.insert_text((80, 80), "Canva -> PDF handoff")
                document.save(pdf)
            entries = window.queue.add([source, pdf])
            entries[0].media_settings = {"volume": 0}
            window.show()
            window.load_item(entries[0].id)
            wait_for(lambda: window.document is not None and not window.loading, 85)
            backend = window.renderer
            service = backend.service
            backend.failed.connect(errors.append)
            report["pages"] = window.document.page_count
            window.start_presentation()
            wait_for(lambda: backend.active and not window.handoff.busy)
            wait_for(lambda: not backend._preview.isNull())
            backend._preview.save(str(output / "audience.png"))
            target = min(4, window.document.page_count - 1)
            window.slides.go_to(target)
            wait_for(lambda: backend.current == target and not backend._preview.isNull())
            QTest.qWait(1000)
            window.resize(1024, 768)
            QTest.qWait(300)
            window.grab().save(str(output / "presenter.png"))
            window.set_audience_mode(AudienceMode.BLACK)
            wait_for(lambda: service.pending == 0)
            assert backend._covered and backend.active
            window.set_audience_mode(AudienceMode.SLIDE)
            wait_for(lambda: service.pending == 0)
            timer_started = window.timer._started
            window.load_item(entries[1].id)
            wait_for(lambda: window.queue.active_id == entries[1].id and not window.handoff.busy)
            wait_for(lambda: not service.process.is_alive())
            assert window.presentation.active and window.renderer.kind == "pdf"
            assert window.timer._started == timer_started and not errors
            report.update(
                success=True,
                navigation=True,
                preview=True,
                cover=True,
                queue="Canva -> PDF",
                timer_preserved=True,
                worker_cleanup=True,
                video="Media controls separately tested using an owned H.264 fixture",
            )
        except Exception:
            report["error"] = traceback.format_exc()
        finally:
            window._project_dirty = False
            window.close()
            if service:
                deadline = time.monotonic() + 7
                while service.process.is_alive() and time.monotonic() < deadline:
                    QTest.qWait(50)
            report["errors"] = errors
            (output / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            app.exit(0 if report["success"] else 1)

    QTimer.singleShot(0, scenario)
    return app.exec()
