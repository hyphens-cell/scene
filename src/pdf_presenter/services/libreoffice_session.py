"""LibreOffice UNO Automation bridge, confined to the Office STA helper.

This optional engine uses the installed LibreOffice COM bridge. Conversion is a
separate backend; native failures never silently claim PDF playback has media.
"""

from __future__ import annotations

import hashlib
import tempfile
import time
from pathlib import Path

from pdf_presenter.i18n import tr

from ..core.capability_model import PresentationDocument
from ..core.media_inspector import inspect_media
from ..core.presentation_file import validate_presentation_file
from ..core.render_service import Raster
from .native_window import position_window, running_office_pids


class LibreOfficeSession:
    def __init__(self) -> None:
        self.manager = self.desktop = None
        self.documents = {}
        self.shows = {}
        self.controllers = {}
        self.positions = {}
        self.handles = {}
        self.frames = {}
        self.owned_application = False
        self.directory = tempfile.TemporaryDirectory(prefix="pdfpresenter-impress-")

    def _application(self):
        if self.manager is None:
            import win32com.client

            previous = running_office_pids("soffice.bin")
            self.manager = win32com.client.Dispatch("com.sun.star.ServiceManager")
            self.desktop = self.manager.createInstance("com.sun.star.frame.Desktop")
            self.owned_application = not previous and not self.desktop.getComponents().hasElements()
        return self.desktop

    def _property(self, name: str, value):
        # This bridge extension is absent from UNO's reflected type information;
        # otherwise pywin32 first invokes it as a zero-argument property getter.
        self.manager._FlagAsMethod("Bridge_GetStruct")
        prop = self.manager.Bridge_GetStruct("com.sun.star.beans.PropertyValue")
        prop.Name, prop.Value = name, value
        return prop

    def _typed_value(self, type_name: str, value):
        # An Any containing a sequence needs its concrete UNO element type;
        # a raw Python tuple would become sequence<any> through Automation.
        self.manager._FlagAsMethod("Bridge_GetValueObject")
        typed = self.manager.Bridge_GetValueObject()
        typed._FlagAsMethod("Set")
        typed.Set(type_name, value)
        return typed

    def execute(self, document_id: str, method: str, arguments: dict):
        operations = {
            "load": self.load,
            "preview": self.preview,
            "start": self.start,
            "stop": self.stop,
            "next": self.next,
            "previous": self.previous,
            "goto": self.go_to,
            "status": self.status,
            "blank": self.blank,
            "place": self.place,
            "dispose": self.dispose,
        }
        if method not in operations:
            raise ValueError("Unsupported Office command")
        return operations[method](document_id, **arguments)

    def load(self, document_id: str, path: str):
        source = Path(path).resolve()
        validate_presentation_file(source)
        with source.open("rb") as stream:
            fingerprint = hashlib.file_digest(stream, "sha256").hexdigest()
        desktop = self._application()
        enumeration = desktop.getComponents().createEnumeration()
        while enumeration.hasMoreElements():
            document = enumeration.nextElement()
            if document.getURL() == source.as_uri():
                raise RuntimeError(
                    tr(
                        "Презентация уже открыта в LibreOffice. Закройте её там перед загрузкой в Сцена."
                    )
                )
        properties = tuple(
            self._property(name, value)
            for name, value in (
                ("Hidden", True),
                ("ReadOnly", True),
                ("MacroExecutionMode", 0),
                ("UpdateDocMode", 0),
            )
        )
        document = desktop.loadComponentFromURL(source.as_uri(), "_blank", 0, properties)
        if document is None:
            raise RuntimeError(
                tr(
                    "LibreOffice не открыл файл. Проверьте пароль, целостность и поддержку формата; доступен режим преобразования в PDF."
                )
            )
        try:
            if not document.supportsService("com.sun.star.presentation.PresentationDocument"):
                raise RuntimeError(
                    tr("LibreOffice открыл документ, который не является презентацией Impress.")
                )
            pages = document.getDrawPages()
            count = int(pages.getCount())
            if count < 1:
                raise RuntimeError(tr("Презентация не содержит слайдов."))
            sizes, notes = [], []
            warnings = list(inspect_media(str(source)).warnings)
            warnings.append(
                tr("Режим LibreOffice: совместимость анимаций, переходов и медиа не гарантируется.")
            )
            for index in range(count):
                page = pages.getByIndex(index)
                sizes.append(
                    (float(page.getPropertyValue("Width")), float(page.getPropertyValue("Height")))
                )
                text = []
                try:
                    note_page = page.getNotesPage()
                    for n in range(note_page.getCount()):
                        shape = note_page.getByIndex(n)
                        if shape.getShapeType() == "com.sun.star.presentation.NotesShape":
                            text.append(str(shape.getString()))
                except Exception:
                    pass
                notes.append("\n".join(text))
            self.documents[document_id] = document
            self.positions[document_id] = 0
            return PresentationDocument(
                str(source),
                fingerprint,
                count,
                source.stem,
                tuple(sizes),
                tuple(notes),
                tuple(warnings),
            )
        except Exception:
            document.close(True)
            raise

    def preview(self, document_id: str, index: int, width: int, height: int):
        import pymupdf

        page = self.documents[document_id].getDrawPages().getByIndex(index)
        ratio = float(page.getPropertyValue("Width")) / max(
            1, float(page.getPropertyValue("Height"))
        )
        if width / height > ratio:
            width = max(16, round(height * ratio))
        else:
            height = max(16, round(width / ratio))
        target = Path(self.directory.name) / f"{document_id}-{index}.png"
        exporter = self.manager.createInstance("com.sun.star.drawing.GraphicExportFilter")
        exporter.setSourceDocument(page)
        options = (self._property("PixelWidth", width), self._property("PixelHeight", height))
        if not exporter.filter(
            (
                self._property("URL", target.as_uri()),
                self._property("MediaType", "image/png"),
                self._property(
                    "FilterData", self._typed_value("[]com.sun.star.beans.PropertyValue", options)
                ),
            )
        ):
            raise RuntimeError(tr("LibreOffice не создал предпросмотр слайда."))
        pixmap = pymupdf.Pixmap(str(target))
        if pixmap.alpha:
            pixmap = pymupdf.Pixmap(pixmap, 0)
        if pixmap.colorspace.n != 3:
            pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
        raster = Raster(pixmap.width, pixmap.height, pixmap.stride, pixmap.samples)
        target.unlink(missing_ok=True)
        return raster

    @staticmethod
    def _windows() -> set[int]:
        import win32gui
        import win32process

        pids = running_office_pids("soffice.bin")
        handles = set()

        def visit(hwnd, _):
            if (
                win32gui.IsWindowVisible(hwnd)
                and win32process.GetWindowThreadProcessId(hwnd)[1] in pids
                and win32gui.GetClassName(hwnd).upper() in {"SALFRAME", "SALTMPSUBFRAME"}
            ):
                handles.add(hwnd)

        win32gui.EnumWindows(visit, None)
        return handles

    def start(self, document_id: str, index: int, target):
        import pythoncom
        import win32gui

        if target.preview:
            raise RuntimeError(
                tr(
                    "Для нативного показа LibreOffice выберите отдельный экран. На одном экране доступен безопасный PDF-режим совместимости."
                )
            )
        configuration = self.manager.createInstance(
            "com.sun.star.configuration.ConfigurationProvider"
        )
        options = configuration.createInstanceWithArguments(
            "com.sun.star.configuration.ConfigurationAccess",
            (self._property("nodepath", "/org.openoffice.Office.Impress/Misc/Start"),),
        )
        if options.getPropertyValue("EnablePresenterScreen"):
            raise RuntimeError(
                tr(
                    "В LibreOffice включена собственная консоль докладчика. Отключите её в настройках Impress → Общие либо выберите «LibreOffice → PDF». Это необходимо, чтобы заметки не попали на экран аудитории."
                )
            )
        if document_id in self.shows:
            self.go_to(document_id, index)
            return self.place(document_id, target)
        document = self.documents[document_id]
        if document.getCurrentController() is None:
            raise RuntimeError(
                tr(
                    "LibreOffice не создал представление для нативного показа. Выберите «LibreOffice → PDF»."
                )
            )
        frame = document.getCurrentController().getFrame()
        self.frames[document_id] = frame
        editor = frame.getContainerWindow()
        # Impress needs a visible, non-minimized ViewShell. The coordinator's
        # topmost audience cover remains in place until this own read-only editor
        # is hidden again and the native show has been positioned and verified.
        editor.IsMinimized = False
        editor.setVisible(True)
        presentation = document.getPresentation()
        presentation.setPropertyValue("IsFullScreen", True)
        presentation.setPropertyValue("IsEndless", False)
        presentation.setPropertyValue("StartWithNavigator", False)
        presentation.setPropertyValue("AllowAnimations", True)
        presentation.setPropertyValue("IsShowAll", True)
        presentation.setPropertyValue(
            "FirstPage", document.getDrawPages().getByIndex(index).getName()
        )
        previous = self._windows()
        self.shows[document_id] = presentation
        try:
            presentation.start()
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                pythoncom.PumpWaitingMessages()
                controller = presentation.getController()
                created = self._windows() - previous
                ready = []
                for hwnd in created:
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    if right - left > 100 and bottom - top > 100:
                        ready.append(hwnd)
                if controller is not None and len(ready) == 1:
                    self.controllers[document_id] = controller
                    self.handles[document_id] = ready[0]
                    editor.setVisible(False)
                    controller.gotoSlideIndex(index)
                    position_window(self.handles[document_id], target)
                    return self.status(document_id)
                time.sleep(0.03)
            raise RuntimeError(
                tr("Не удалось подтвердить готовность окна Impress. Выберите преобразование в PDF.")
            )
        except Exception:
            self.stop(document_id)
            raise

    def stop(self, document_id: str):
        presentation = self.shows.pop(document_id, None)
        self.controllers.pop(document_id, None)
        self.handles.pop(document_id, None)
        if presentation is not None:
            presentation.end()
        if document_id in self.frames:
            self.frames[document_id].getContainerWindow().setVisible(False)
        return {"active": False, "index": self.positions.get(document_id, 0), "hwnd": 0}

    def next(self, document_id: str):
        controller = self.controllers.get(document_id)
        if controller is not None:
            controller.gotoNextEffect()
        else:
            self.positions[document_id] = min(
                self.documents[document_id].getDrawPages().getCount() - 1,
                self.positions[document_id] + 1,
            )
        return self.status(document_id)

    def previous(self, document_id: str):
        controller = self.controllers.get(document_id)
        if controller is not None:
            controller.gotoPreviousEffect()
        else:
            self.positions[document_id] = max(0, self.positions[document_id] - 1)
        return self.status(document_id)

    def go_to(self, document_id: str, index: int):
        if not 0 <= index < self.documents[document_id].getDrawPages().getCount():
            raise ValueError(tr("Номер слайда вне диапазона."))
        if document_id in self.controllers:
            self.controllers[document_id].gotoSlideIndex(index)
        self.positions[document_id] = index
        return self.status(document_id)

    def status(self, document_id: str):
        presentation = self.shows.get(document_id)
        if presentation is None or not presentation.isRunning():
            ended = presentation is not None
            self.shows.pop(document_id, None)
            self.controllers.pop(document_id, None)
            self.handles.pop(document_id, None)
            return {
                "active": False,
                "ended": ended,
                "index": self.positions.get(document_id, 0),
                "hwnd": 0,
            }
        controller = self.controllers[document_id]
        index = int(controller.getCurrentSlideIndex())
        if index >= 0:
            self.positions[document_id] = index
        return {
            "active": True,
            "index": self.positions[document_id],
            "hwnd": self.handles[document_id],
        }

    def blank(self, document_id: str, color: str):
        controller = self.controllers.get(document_id)
        if controller is not None:
            if color == "pause":
                controller.pause()
            elif color:
                # Impress ignores a new blank color while its blank mode is
                # already active. The Qt audience cover stays above this reset.
                if controller.isPaused():
                    controller.resume()
                controller.blankScreen(0 if color == "black" else 0xFFFFFF)
            else:
                controller.resume()
        return self.status(document_id)

    def place(self, document_id: str, target):
        if document_id in self.handles:
            position_window(self.handles[document_id], target)
        return self.status(document_id)

    def dispose(self, document_id: str):
        self.stop(document_id)
        document = self.documents.pop(document_id, None)
        self.positions.pop(document_id, None)
        if document is not None:
            document.setModified(False)
            document.close(True)
        self.frames.pop(document_id, None)
        return True

    def close(self) -> None:
        for document_id in list(self.documents):
            self.dispose(document_id)
        if (
            self.desktop is not None
            and self.owned_application
            and not self.desktop.getComponents().hasElements()
        ):
            self.desktop.terminate()
        self.desktop = self.manager = None
        self.directory.cleanup()
