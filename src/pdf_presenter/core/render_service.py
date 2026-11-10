"""A killable, isolated MuPDF process with a prioritized, bounded GUI-side queue.

Only one job crosses the pipe at a time. A new frame drops pending work; results
from the in-flight old frame can enter the cache but cannot update a widget.
"""

from __future__ import annotations

import math
import multiprocessing as mp
import time
from collections import OrderedDict
from dataclasses import dataclass
from multiprocessing.connection import Connection
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from pdf_presenter.i18n import tr

from .pdf_document import PasswordRequired, PdfDocument, open_pdf


@dataclass(frozen=True)
class Raster:
    width: int
    height: int
    stride: int
    samples: bytes


class RasterCache:
    def __init__(self, budget: int = 192 * 1024 * 1024) -> None:
        self.budget = budget
        self.used = 0
        self._items: OrderedDict[tuple[int, int, int], Raster] = OrderedDict()

    def get(self, key: tuple[int, int, int]) -> Raster | None:
        value = self._items.get(key)
        if value is not None:
            self._items.move_to_end(key)
        return value

    def put(self, key: tuple[int, int, int], value: Raster) -> None:
        old = self._items.pop(key, None)
        if old:
            self.used -= len(old.samples)
        size = len(value.samples)
        if size > self.budget:
            return
        while self.used + size > self.budget:
            _, removed = self._items.popitem(last=False)
            self.used -= len(removed.samples)
        self._items[key] = value
        self.used += size

    def clear(self) -> None:
        self._items.clear()
        self.used = 0


def render_page(document: Any, key: tuple[int, int, int]) -> Raster:
    import pymupdf

    index, width, height = key
    page = document[index]
    rect = page.rect
    scale = min(width / max(rect.width, 1), height / max(rect.height, 1))
    scale = min(scale, math.sqrt(12_000_000 / max(1, rect.width * rect.height)))
    pix = page.get_pixmap(
        matrix=pymupdf.Matrix(scale, scale), alpha=False, colorspace=pymupdf.csRGB, annots=True
    )
    return Raster(pix.width, pix.height, pix.stride, pix.samples)


def _worker(pipe: Connection, path: str, password: str, kind="pdf") -> None:
    document = None
    try:
        if kind == "image":
            import os
            from pathlib import Path

            from PySide6.QtGui import QFontDatabase, QGuiApplication

            from .image_document import open_image, render_image

            # SVG text needs a font database, even in the isolated image worker.
            _application = QGuiApplication.instance() or QGuiApplication(
                ["scene-image", "-platform", "offscreen"]
            )
            font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"
            if font.is_file():
                QFontDatabase.addApplicationFont(str(font))
            info, document = open_image(path)
            render = render_image
        else:
            info, document = open_pdf(path, password)
            render = render_page
        password = ""
        pipe.send(("loaded", info))
        while True:
            command = pipe.recv()
            if command is None:
                break
            try:
                pipe.send(("rendered", render(document, command)))
            except Exception as exc:
                pipe.send(("render_error", str(exc)))
    except PasswordRequired as exc:
        pipe.send(("open_error", "password", str(exc)))
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            pipe.send(("open_error", "document", str(exc)))
        except (EOFError, BrokenPipeError, OSError):
            pass
    finally:
        if document is not None and kind == "pdf":
            document.close()
        pipe.close()


@dataclass
class Worker:
    process: Any
    pipe: Connection
    since: float

    def close(self) -> None:
        # Termination also closes file handles held by a hung native renderer.
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=0.25)
        self.pipe.close()
        if not self.process.is_alive():
            self.process.close()


class RenderService(QObject):
    loaded = Signal(object)
    load_failed = Signal(str, str)
    ready = Signal(str, int, object)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None, budget: int = 192 * 1024 * 1024) -> None:
        super().__init__(parent)
        self.cache = RasterCache(budget)
        self.document: PdfDocument | None = None
        self._worker: Worker | None = None
        self._candidate: Worker | None = None
        self._pending: dict[tuple[int, int, int], tuple[int, list[str]]] = {}
        self._busy: tuple[int, tuple[int, int, int], list[str]] | None = None
        self._epoch = 0
        self._poller = QTimer(self)
        self._poller.setInterval(15)
        self._poller.timeout.connect(self._poll)
        self._poller.start()

    @property
    def pending_count(self) -> int:
        return len(self._pending) + int(self._busy is not None)

    def load(self, path: str, password: str = "", *, kind="pdf") -> None:
        if self._candidate:
            self._candidate.close()
        context = mp.get_context("spawn")
        parent, child = context.Pipe()
        process = context.Process(target=_worker, args=(child, path, password, kind), daemon=True)
        try:
            process.start()
        except Exception:
            parent.close()
            child.close()
            raise
        child.close()
        self._candidate = Worker(process, parent, time.monotonic())

    def begin_frame(self) -> None:
        self._epoch += 1
        self._pending.clear()

    def request(self, tag: str, page: int, width: int, height: int, priority: int = 0) -> None:
        if self.document is None or not 0 <= page < self.document.page_count:
            return
        key = (page, max(16, min(width, 4096)), max(16, min(height, 4096)))
        cached = self.cache.get(key)
        if cached is not None:
            self.ready.emit(tag, page, cached)
            return
        if self._busy and self._busy[0] == self._epoch and self._busy[1] == key:
            if tag not in self._busy[2]:
                self._busy[2].append(tag)
            return
        previous = self._pending.get(key)
        if previous:
            if tag not in previous[1]:
                previous[1].append(tag)
            self._pending[key] = (min(priority, previous[0]), previous[1])
        else:
            self._pending[key] = (priority, [tag])

    def _poll(self) -> None:
        candidate = self._candidate
        if candidate:
            try:
                if candidate.pipe.poll():
                    result = candidate.pipe.recv()
                    self._candidate = None
                    if result[0] == "loaded":
                        if self._worker:
                            self._worker.close()
                        self._worker = candidate
                        self._busy = None
                        self.begin_frame()
                        self.cache.clear()
                        self.document = result[1]
                        self.loaded.emit(self.document)
                    else:
                        candidate.close()
                        self.load_failed.emit(result[1], result[2])
                elif not candidate.process.is_alive() or time.monotonic() - candidate.since > 90:
                    raise RuntimeError(tr("Загрузка файла прервана или превысила 90 секунд."))
            except (OSError, EOFError, RuntimeError) as exc:
                candidate.close()
                self._candidate = None
                self.load_failed.emit("document", str(exc))
        worker = self._worker
        if worker is None:
            return
        try:
            if self._busy and worker.pipe.poll():
                result = worker.pipe.recv()
                epoch, key, tags = self._busy
                self._busy = None
                if result[0] == "rendered":
                    self.cache.put(key, result[1])
                    if epoch == self._epoch:
                        for tag in tags:
                            self.ready.emit(tag, key[0], result[1])
                            if self._worker is not worker:
                                return  # A receiver may dispose the prepared backend synchronously.
                elif epoch == self._epoch:
                    self.failed.emit(
                        tr("Не удалось отобразить слайд {p0}: {p1}", p0=key[0] + 1, p1=result[1])
                    )
            if not worker.process.is_alive():
                raise RuntimeError(tr("Процесс рендеринга завершился. Откройте файл повторно."))
            if self._busy and time.monotonic() - worker.since > 30:
                raise RuntimeError(tr("Рендеринг превысил 30 секунд. Откройте файл повторно."))
            if self._busy is None and self._pending:
                key = min(self._pending, key=lambda item: self._pending[item][0])
                _, tags = self._pending.pop(key)
                cached = self.cache.get(key)
                if cached is not None:
                    for tag in tags:
                        self.ready.emit(tag, key[0], cached)
                        if self._worker is not worker:
                            return
                else:
                    worker.pipe.send(key)
                    worker.since = time.monotonic()
                    self._busy = (self._epoch, key, tags)
        except (OSError, EOFError, RuntimeError) as exc:
            worker.close()
            self._worker = None
            self._pending.clear()
            self._busy = None
            self.failed.emit(str(exc))

    def close(self) -> None:
        self._poller.stop()
        for worker in (self._candidate, self._worker):
            if worker:
                worker.close()
        self._candidate = self._worker = None
        self._pending.clear()
        self._busy = None
        self.cache.clear()
