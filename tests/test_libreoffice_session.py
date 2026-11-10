"""Audience privacy guard, independent of an installed LibreOffice."""

from unittest.mock import MagicMock

import pytest

from pdf_presenter.core.capability_model import DisplayTarget
from pdf_presenter.services.libreoffice_session import LibreOfficeSession


def test_presenter_console_cannot_be_started_over_audience():
    session = LibreOfficeSession()
    session.manager = MagicMock()
    options = session.manager.createInstance.return_value.createInstanceWithArguments.return_value
    options.getPropertyValue.return_value = True
    presentation = MagicMock()
    session.documents["owned"] = presentation
    try:
        with pytest.raises(RuntimeError, match="консоль докладчика"):
            session.start("owned", 0, DisplayTarget("screen", 1920, 0, 1920, 1080))
        presentation.getPresentation.assert_not_called()
        presentation.getCurrentController.assert_not_called()
        assert not session.shows and not session.frames
    finally:
        session.directory.cleanup()


def test_native_blank_color_can_change_while_paused():
    class Controller:
        color = None
        paused = False

        def isPaused(self):
            return self.paused

        def getCurrentSlideIndex(self):
            return 0

        def blankScreen(self, color):
            # Impress's existing blank mode does not accept a replacement color.
            if self.color is None:
                self.color, self.paused = color, True

        def resume(self):
            self.color, self.paused = None, False

    session = LibreOfficeSession()
    controller = Controller()
    session.controllers["owned"] = controller
    session.shows["owned"] = MagicMock()
    session.shows["owned"].isRunning.return_value = True
    session.handles["owned"] = 1
    try:
        session.blank("owned", "black")
        assert controller.color == 0
        session.blank("owned", "white")
        assert controller.color == 0xFFFFFF and controller.paused
        session.blank("owned", "")
        assert controller.color is None and not controller.paused
    finally:
        session.directory.cleanup()
