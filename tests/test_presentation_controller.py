from pdf_presenter.core.presentation_controller import PresentationController
from pdf_presenter.core.presentation_timer import PresentationTimer
from pdf_presenter.core.slide_controller import SlideController


def test_required_acceptance_sequence():
    now = [0.0]
    slides = SlideController()
    timer = PresentationTimer(lambda: now[0])
    show = PresentationController(slides, timer)
    assert not show.start()
    slides.set_document(50)
    slides.go_to_number(17)
    assert show.start(from_current=True)
    assert slides.current == 16 and timer.running
    now[0] += 12
    show.digit("3")
    show.digit("5")
    assert show.number == "35"
    assert show.submit_number()
    assert slides.current == 34 and timer.elapsed == 12
    slides.go_to_number(8)
    now[0] += 8
    assert timer.elapsed == 20
    show.stop()
    assert not timer.running
    show.start()
    assert slides.current == 0 and timer.elapsed == 0


def test_escape_invalid_numbers_blanking_restart():
    slides = SlideController()
    slides.set_document(3)
    show = PresentationController(slides, PresentationTimer())
    show.start()
    show.digit("9")
    assert not show.submit_number()
    assert slides.current == 0
    show.escape()
    assert show.active and not show.number
    show.toggle_blank("black")
    assert show.blank == "black"
    show.toggle_blank("white")
    assert show.blank == "white"
    show.toggle_blank("white")
    assert show.blank == ""
    show.toggle_blank("black")
    show.start(True)
    assert show.blank == ""
    show.escape()
    assert not show.active
