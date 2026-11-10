import pytest
from PySide6.QtCore import QObject, Signal

from pdf_presenter.core.display_handoff import DisplayHandoffCoordinator


class Backend(QObject):
    started = Signal()
    stopped = Signal()
    failed = Signal(str)

    def __init__(self, events, name, active=False):
        super().__init__()
        self.events, self.name, self.active = events, name, active
        self.reject_target = False
        self.reject_stop = False

    def set_display_target(self, target):
        if self.reject_target:
            raise RuntimeError("Display disappeared")
        self.events.append((self.name, "target", target))

    def start(self, index):
        self.events.append((self.name, "start", index))

    def stop(self):
        if self.reject_stop:
            raise RuntimeError("Engine lost")
        self.events.append((self.name, "stop"))


class Audience:
    def __init__(self, events):
        self.events = events
        self.handoff = False

    def hold(self):
        self.handoff = True
        self.events.append("cover")

    def attach(self, backend):
        self.handoff = False
        self.events.append(("release", backend.name))

    def apply_mode(self, mode):
        self.events.append(("mode", mode))


def test_handoff_keeps_cover_until_old_stops_and_new_document_is_committed(qapp):
    events = []
    old, new = Backend(events, "old", True), Backend(events, "new")
    audience = Audience(events)
    coordinator = DisplayHandoffCoordinator(audience)
    coordinator.completed.connect(lambda backend: events.append(("commit", backend.name)))
    coordinator.switch(old, new, 16, "second screen")
    assert events == ["cover", ("old", "stop")]
    assert coordinator.busy and audience.handoff
    old.stopped.emit()
    assert events[-1] == ("new", "start", 16)
    assert coordinator.busy and audience.handoff
    new.started.emit()
    assert events[-2:] == [("commit", "new"), ("release", "new")]
    assert not coordinator.busy and not audience.handoff


def test_previous_engine_failure_never_starts_candidate(qapp):
    events, failures = [], []
    old, new = Backend(events, "old", True), Backend(events, "new")
    coordinator = DisplayHandoffCoordinator(Audience(events))
    coordinator.failed.connect(failures.append)
    coordinator.switch(old, new, 0, "screen")
    old.failed.emit("COM stop failed")
    assert failures == ["COM stop failed"]
    assert not coordinator.busy
    assert events == ["cover", ("old", "stop"), ("new", "stop"), ("mode", "black")]
    old.stopped.emit()  # A delayed response must not revive the failed switch.
    new.started.emit()
    assert not any(isinstance(item, tuple) and "start" in item for item in events)


@pytest.mark.parametrize("reject_stop", [False, True])
def test_lost_display_and_cleanup_failure_still_leave_black_cover(qapp, reject_stop):
    events, failures = [], []
    new = Backend(events, "new")
    new.reject_target, new.reject_stop = True, reject_stop
    coordinator = DisplayHandoffCoordinator(Audience(events))
    coordinator.failed.connect(failures.append)
    coordinator.switch(None, new, 0, "unplugged screen")
    assert failures == ["Display disappeared"]
    assert events[-1] == ("mode", "black")
    assert not coordinator.busy
