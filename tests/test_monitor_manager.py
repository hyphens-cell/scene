from pdf_presenter.core.monitor_manager import MonitorManager


def test_single_screen_and_disconnect_policy(qapp, monkeypatch):
    manager = MonitorManager()
    first, second = object(), object()
    monkeypatch.setattr(manager, "screens", lambda: [first, second])
    assert manager.default_audience(first) is second
    assert not manager.requires_preview(second, first)
    assert manager.requires_preview(first, first)
    monkeypatch.setattr(manager, "screens", lambda: [first])
    assert manager.default_audience(first) is first
    assert manager.requires_preview(first, first)
