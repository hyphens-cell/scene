from itertools import count

from PySide6.QtCore import QObject, Signal

from pdf_presenter.backends.powerpoint_com_backend import PowerPointCOMBackend
from pdf_presenter.core.capability_model import DisplayTarget, PresentationDocument
from pdf_presenter.core.render_service import Raster


class FakeOfficeService(QObject):
    completed = Signal(str, str, object)
    failed = Signal(str, str, str)
    disconnected = Signal(str)

    def __init__(self):
        super().__init__()
        self.ids = count()
        self.commands = {}

    def call(self, document_id, method, arguments=None, **kwargs):
        request = str(next(self.ids))
        self.commands[request] = (document_id, method, arguments)
        return request

    def cancel_methods(self, document_id, methods=None):
        removed = {
            key
            for key, value in self.commands.items()
            if value[0] == document_id and (methods is None or value[1] in methods)
        }
        for key in removed:
            self.commands.pop(key)
        return removed

    def cancel_previews(self, document_id):
        return self.cancel_methods(document_id, {"preview"})

    def cancel_document(self, document_id):
        return self.cancel_methods(document_id)

    def reply(self, method, result):
        key, value = next(
            (key, value) for key, value in self.commands.items() if value[1] == method
        )
        self.commands.pop(key)
        self.completed.emit(value[0], key, result)


def loaded_backend():
    service = FakeOfficeService()
    backend = PowerPointCOMBackend(service)
    backend.load("talk.pptx")
    service.reply("load", PresentationDocument("talk.pptx", "a" * 64, 4, "Talk", ((960, 540),) * 4))
    return service, backend


def test_next_animation_reports_actual_slide_without_guessing(qapp):
    service, backend = loaded_backend()
    backend.set_display_target(DisplayTarget("screen", 0, 0, 1920, 1080))
    backend.start(1)
    service.reply("start", {"active": True, "index": 1, "hwnd": 123})
    backend.next()
    service.reply("next", {"active": True, "index": 1, "hwnd": 123, "click_index": 1})
    assert backend.current == 1 and backend.click_index == 1
    backend.next()
    service.reply("next", {"active": True, "index": 2, "hwnd": 123})
    assert backend.current == 2
    backend.dispose()


def test_stop_cancels_queued_start_and_fast_navigation(qapp):
    service, backend = loaded_backend()
    backend.set_display_target(DisplayTarget("screen", 0, 0, 1920, 1080))
    backend.start(0)
    backend.next()
    backend.stop()
    assert [value[1] for value in service.commands.values()] == ["stop"]
    backend.dispose()


def test_stale_preview_does_not_consume_new_frame_request(qapp):
    service, backend = loaded_backend()
    backend.request("current", 0, 100, 100)
    request, value = next(iter(service.commands.items()))
    service.commands.pop(request)  # This command is already in flight.
    backend.begin_frame()
    backend.request("current", 0, 100, 100)
    received = []
    backend.ready.connect(lambda *result: received.append(result))
    raster = Raster(1, 1, 3, b"\x00\x00\x00")
    service.completed.emit(value[0], request, raster)
    assert not received
    service.reply("preview", raster)
    assert received[0][:2] == ("current", 0)
    backend.dispose()


def test_end_screen_stays_owned_until_handoff_and_notifies_once(qapp):
    service, backend = loaded_backend()
    backend.set_display_target(DisplayTarget("screen", 0, 0, 1920, 1080))
    backend.start(3)
    service.reply("start", {"active": True, "index": 3, "hwnd": 123})
    ended = []
    backend.ended.connect(lambda: ended.append(True))
    for _ in range(2):
        backend.next()
        service.reply("next", {"active": True, "ended": True, "index": 3, "hwnd": 123})
    assert backend.active and backend.native_hwnd == 123
    assert ended == [True]
    backend.dispose()


def test_native_failure_stops_reporting_live_and_preserves_last_slide(qapp):
    service, backend = loaded_backend()
    backend.set_display_target(DisplayTarget("screen", 0, 0, 1920, 1080))
    backend.start(2)
    service.reply("start", {"active": True, "index": 2, "hwnd": 123})
    backend.next()
    request = next(key for key, value in service.commands.items() if value[1] == "next")
    errors = []
    backend.failed.connect(errors.append)
    service.failed.emit(backend.document_id, request, "RPC server unavailable")
    assert errors and not backend.active and backend.current == 2
    backend.dispose()


def test_video_failure_keeps_live_show_and_stop_cancels_playback_request(qapp):
    service, backend = loaded_backend()
    backend.active, backend.current, backend.native_hwnd = True, 2, 123
    video_errors, show_errors = [], []
    backend.video_failed.connect(video_errors.append)
    backend.failed.connect(show_errors.append)
    assert backend.play_video()
    assert not backend.play_video(), "Repeated clicks must not enqueue duplicate playback"
    request, (_, method, arguments) = next(iter(service.commands.items()))
    assert method == "play_video" and arguments == {"index": 2, "shape_id": 0}
    service.commands.pop(request)
    service.failed.emit(backend.document_id, request, "На текущем слайде нет видео.")
    assert video_errors and not show_errors
    assert backend.active and backend.current == 2 and backend.native_hwnd == 123
    assert backend.play_video(7, slide_index=2)
    backend.stop()
    assert [value[1] for value in service.commands.values()] == ["stop"]
    backend.dispose()
