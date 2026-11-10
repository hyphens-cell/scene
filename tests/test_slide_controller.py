import pytest

from pdf_presenter.core.slide_controller import SlideController


def test_navigation_bounds_and_no_duplicates(qtbot):
    controller = SlideController()
    changes = []
    controller.changed.connect(changes.append)
    assert not controller.next()
    controller.set_document(50)
    assert controller.go_to_number(17)
    assert controller.current == 16
    assert controller.go_to_number(17)
    assert changes == [0, 16]
    assert not controller.go_to_number(0)
    assert not controller.go_to_number(51)
    controller.go_to(49)
    assert not controller.next()
    assert controller.previous()
    controller.set_document(2)
    assert controller.current == 0
    assert not controller.previous()


def test_negative_count():
    with pytest.raises(ValueError):
        SlideController().set_document(-1)
