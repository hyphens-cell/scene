from pdf_presenter.core.presentation_timer import PresentationTimer


def test_monotonic_pause_resume_reset():
    now = [100.0]
    timer = PresentationTimer(lambda: now[0])
    assert timer.formatted() == "00:00:00"
    timer.start()
    now[0] += 3661.9
    assert timer.formatted() == "01:01:01"
    timer.pause()
    now[0] += 100
    assert timer.formatted() == "01:01:01"
    timer.resume()
    timer.resume()
    now[0] += 2
    assert timer.formatted() == "01:01:03"
    timer.reset()
    assert timer.running and timer.elapsed == 0
    timer.pause()
    timer.reset()
    assert not timer.running
    timer.start()
    assert timer.elapsed == 0
