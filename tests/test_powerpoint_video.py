from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pdf_presenter.services.powerpoint_session import PowerPointSession


@pytest.fixture
def video_session():
    session = PowerPointSession()
    shapes = [
        SimpleNamespace(Type=16, MediaType=2, Id=8, Name="Audio"),
        SimpleNamespace(Type=16, MediaType=3, Id=9, Name="First video"),
        SimpleNamespace(Type=16, MediaType=3, Id=10, Name="Second video"),
    ]
    view = MagicMock()
    view.State = 1
    view.Slide.SlideIndex = 2
    view.Slide.Shapes.Count = len(shapes)
    view.Slide.Shapes.Item.side_effect = lambda index: shapes[index - 1]
    view.GetClickIndex.return_value = 0
    session.shows["test"] = SimpleNamespace(View=view)
    yield session, view, shapes
    session.cache_directory.cleanup()


def test_video_choice_ignores_audio_and_plays_only_selected_movie(video_session):
    session, view, _ = video_session
    result = session.play_video("test", index=1)
    assert result["video_choices"] == [
        {"id": 9, "name": "First video"},
        {"id": 10, "name": "Second video"},
    ]
    view.Player.assert_not_called()
    session.play_video("test", index=1, shape_id=10)
    view.Player.assert_called_once_with(10)
    view.Player.return_value.Play.assert_called_once_with()
    view.Next.assert_not_called()


def test_video_rejects_stale_slide_and_audio_selection(video_session):
    session, view, _ = video_session
    with pytest.raises(RuntimeError, match="Слайд изменился"):
        session.play_video("test", index=0, shape_id=9)
    with pytest.raises(RuntimeError, match="больше недоступно"):
        session.play_video("test", index=1, shape_id=8)
    view.Player.assert_not_called()


def test_video_errors_preserve_show(video_session):
    session, view, shapes = video_session
    view.Slide.Shapes.Count = 1  # Audio only.
    with pytest.raises(RuntimeError, match="нет видео"):
        session.play_video("test", index=1)
    view.Slide.Shapes.Count = 2  # Exactly one movie is selected automatically.
    view.Player.return_value.Play.side_effect = RuntimeError("Missing linked file")
    with pytest.raises(RuntimeError, match="не смог запустить видео"):
        session.play_video("test", index=1)
    view.Player.assert_called_once_with(shapes[1].Id)
    assert session.shows["test"].View is view
    view.Exit.assert_not_called()


def test_repeat_changes_only_selected_movie_and_rejects_stale_slide(video_session):
    session, view, shapes = video_session
    for shape in shapes:
        shape.AnimationSettings = SimpleNamespace(PlaySettings=SimpleNamespace(LoopUntilStopped=0))
    session.video_control("test", 1, 9, "loop", 1)
    assert shapes[1].AnimationSettings.PlaySettings.LoopUntilStopped == -1
    assert shapes[2].AnimationSettings.PlaySettings.LoopUntilStopped == 0
    view.Player.assert_not_called()
    with pytest.raises(RuntimeError, match="Слайд изменился"):
        session.video_control("test", 0, 9, "loop", 0)
    session.video_control("test", 1, 9, "loop", 0)
    assert shapes[1].AnimationSettings.PlaySettings.LoopUntilStopped == 0
