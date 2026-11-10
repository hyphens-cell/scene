import time

from pdf_presenter.services.com_worker import Command, OfficeService


def test_com_timeout_terminates_only_owned_helper_and_notifies_gui(qapp):
    class Helper:
        alive = True
        terminated = False
        closed = False

        def is_alive(self):
            return self.alive

        def terminate(self):
            self.terminated = True
            self.alive = False

        def join(self, timeout):
            pass

        def close(self):
            self.closed = True

    class Pipe:
        closed = False

        def poll(self):
            return False

        def close(self):
            self.closed = True

    service = OfficeService("powerpoint")
    helper, pipe = Helper(), Pipe()
    service._process, service._pipe = helper, pipe
    service._busy = Command("request", "document", "next", {}, 0, 1)
    service._since = time.monotonic() - 2
    failures = []
    service.disconnected.connect(failures.append)
    service._poll()
    assert helper.terminated and helper.closed and pipe.closed
    assert service._process is None and service.idle
    assert len(failures) == 1 and "не отвечает" in failures[0]
    service.close()
