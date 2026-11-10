"""Isolated, cancellable LibreOffice conversion. Never uses a user's LO profile."""

from __future__ import annotations

import hashlib
import logging
import multiprocessing as mp
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from pdf_presenter.i18n import tr

from ..core.media_inspector import inspect_media
from ..core.presentation_file import validate_presentation_file


def _run_converter(arguments: list[str], timeout: float = 120) -> None:
    if sys.platform != "win32":
        subprocess.run(
            arguments,
            check=True,
            timeout=timeout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    import win32api
    import win32con
    import win32event
    import win32job
    import win32process

    # Assign the suspended converter to an owned job BEFORE it can spawn soffice.bin.
    # Closing the job also stops its children on cancellation/crash of our helper.
    job = win32job.CreateJobObject(None, "")
    limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    limits["BasicLimitInformation"]["LimitFlags"] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
    process = thread = None
    try:
        startup = win32process.STARTUPINFO()
        startup.dwFlags |= win32con.STARTF_USESHOWWINDOW
        startup.wShowWindow = win32con.SW_HIDE
        process, thread, _, _ = win32process.CreateProcess(
            arguments[0],
            subprocess.list2cmdline(arguments),
            None,
            None,
            False,
            win32con.CREATE_SUSPENDED | win32con.CREATE_NO_WINDOW,
            None,
            None,
            startup,
        )
        try:
            win32job.AssignProcessToJobObject(job, process)
        except Exception:
            win32process.TerminateProcess(process, 1)
            raise
        win32process.ResumeThread(thread)
        if win32event.WaitForSingleObject(process, int(timeout * 1000)) != win32con.WAIT_OBJECT_0:
            raise TimeoutError(tr("LibreOffice не завершил преобразование за 120 секунд."))
        code = win32process.GetExitCodeProcess(process)
        if code:
            raise RuntimeError(tr("LibreOffice завершил преобразование с кодом {p0}.", p0=code))
    finally:
        win32api.CloseHandle(job)
        if thread is not None:
            win32api.CloseHandle(thread)
        if process is not None:
            win32api.CloseHandle(process)


def _convert(pipe, source: str, executable: str, directory: str, pdf_copy: bool) -> None:
    try:
        path = Path(source).resolve()
        with path.open("rb") as stream:
            fingerprint = hashlib.file_digest(stream, "sha256").hexdigest()
        warnings = inspect_media(source).warnings
        if pdf_copy:
            target = path.with_suffix(".pdf")
            if not target.is_file():
                raise FileNotFoundError(
                    tr("PDF-копия с тем же именем рядом с презентацией не найдена.")
                )
        else:
            validate_presentation_file(path)
            if not executable or not Path(executable).is_file():
                raise FileNotFoundError(
                    tr("LibreOffice не найден. Установите его либо подготовьте PDF-копию.")
                )
            root = Path(directory)
            profile = root / "profile"
            output = root / "output"
            output.mkdir()
            _run_converter(
                [
                    executable,
                    f"-env:UserInstallation={profile.as_uri()}",
                    "--headless",
                    "--nologo",
                    "--nodefault",
                    "--norestore",
                    "--convert-to",
                    "pdf:impress_pdf_Export",
                    "--outdir",
                    str(output),
                    str(path),
                ]
            )
            target = output / path.with_suffix(".pdf").name
            if not target.is_file() or target.stat().st_size == 0:
                raise RuntimeError(
                    tr("LibreOffice не создал PDF. Файл может быть повреждён или защищён паролем.")
                )
        pipe.send((True, (str(target), fingerprint, warnings)))
    except Exception as exc:
        logging.getLogger(__name__).exception("Presentation conversion failed")
        pipe.send((False, str(exc)))
    finally:
        pipe.close()


class ConversionService(QObject):
    completed = Signal(str, str, object)
    failed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._process = self._pipe = None
        self._directory = None
        self._since = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._poll)

    def start(self, source: str, executable: str = "", pdf_copy: bool = False) -> None:
        self.close()
        self._directory = tempfile.TemporaryDirectory(prefix="pdfpresenter-convert-")
        context = mp.get_context("spawn")
        parent, child = context.Pipe()
        self._process = context.Process(
            target=_convert,
            args=(child, source, executable, self._directory.name, pdf_copy),
            daemon=True,
        )
        try:
            self._process.start()
        except Exception:
            parent.close()
            child.close()
            self._process = None
            raise
        child.close()
        self._pipe = parent
        self._since = time.monotonic()
        self._timer.start()

    def _poll(self) -> None:
        if self._process is None:
            return
        try:
            if self._pipe.poll():
                success, result = self._pipe.recv()
                self._release_process()
                if success:
                    self.completed.emit(*result)
                else:
                    self.failed.emit(result)
            elif not self._process.is_alive() or time.monotonic() - self._since > 130:
                raise RuntimeError(tr("Преобразование прервано или превысило допустимое время."))
        except (OSError, EOFError, RuntimeError) as exc:
            self._release_process()
            self.failed.emit(str(exc))

    def _release_process(self) -> None:
        self._timer.stop()
        if self._process is not None:
            self._process.join(timeout=0.05)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=0.2)
            if not self._process.is_alive():
                self._process.close()
        if self._pipe is not None:
            self._pipe.close()
        self._process = self._pipe = None

    def close(self) -> None:
        self._release_process()
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None
