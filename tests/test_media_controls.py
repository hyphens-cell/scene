from PySide6.QtCore import Qt

from pdf_presenter.ui.media_controls import MediaControls


def test_controls_select_clip_and_keep_programmatic_refresh_silent(qtbot):
    panel = MediaControls()
    qtbot.addWidget(panel)
    panel.show()
    events = []
    panel.command_requested.connect(lambda *args: events.append(args))
    videos = [
        {
            "id": n,
            "name": f"Video {n}",
            "state": 1,
            "position": 2000,
            "duration": 12000,
            "volume": 75,
            "seekable": True,
            "loop": False,
        }
        for n in (3, 4)
    ]
    panel.set_available(True)
    panel.update_state(2, videos)
    assert not events and panel.time.text() == "00:02 / 00:12"
    panel.choice.setCurrentIndex(1)
    qtbot.mouseClick(panel.play, Qt.MouseButton.LeftButton)
    panel.seek.setValue(7000)
    panel.volume.setValue(30)
    panel.repeat.click()
    assert events == [
        (2, 4, "play", 0),
        (2, 4, "seek", 7000),
        (2, 4, "volume", 30),
        (2, 4, "loop", 1),
    ]
    videos[1]["loop"] = True
    panel.update_state(2, videos)
    assert panel.repeat.isChecked() and len(events) == 4
    panel.reset(3)
    assert not panel.play.isEnabled() and not panel.seek.isEnabled()
    qtbot.mouseClick(panel.stop, Qt.MouseButton.LeftButton)
    assert len(events) == 4 and not panel.repeat.isEnabled()


def test_hidden_audience_disables_all_media_commands(qtbot):
    panel = MediaControls()
    qtbot.addWidget(panel)
    panel.update_state(
        0,
        [
            {
                "id": 3,
                "name": "Video",
                "state": 0,
                "position": 1000,
                "duration": 12000,
                "volume": None,
                "seekable": True,
            }
        ],
    )
    assert not panel.play.isEnabled() and not panel.seek.isEnabled()
    panel.set_available(True)
    assert panel.play.text() == "Пауза" and panel.seek.isEnabled()
    assert not panel.volume.isEnabled()
    panel.set_available(False)
    assert not panel.play.isEnabled() and not panel.stop.isEnabled()
