"""Interactive, source-only audio/display check with isolated application data."""

import argparse
import json
import multiprocessing
import subprocess
import time
from pathlib import Path


def main(source=None, destination=None):
    import imageio_ffmpeg
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from pdf_presenter.app import configure_logging
    from pdf_presenter.ui.presenter_window import PresenterWindow
    from pdf_presenter.ui.styles import apply_theme

    output = Path(destination or "artifacts/scene-hardware-check").resolve()
    output.mkdir(parents=True, exist_ok=True)
    clip = Path(source).resolve() if source else output / "audio-display-180s.mp4"
    if not source and not clip.exists():
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-stream_loop",
                "-1",
                "-i",
                str(Path("artifacts/v2-media-audible/moving-pattern.mp4").resolve()),
                "-t",
                "180",
                "-c",
                "copy",
                str(clip),
            ],
            check=True,
            timeout=30,
        )
    (output / "close-request").unlink(missing_ok=True)
    root = output / time.strftime("data-%Y%m%d-%H%M%S")
    configure_logging(root)
    app = QApplication([])
    app.setApplicationName("Сцена — проверка экранов и звука")
    apply_theme(app)
    window = PresenterWindow(root)
    window.show()
    window.monitors.move_presenter(window, app.primaryScreen())
    screen = window.monitors.default_audience(window.screen())
    window.monitor_combo.setCurrentIndex(window.monitor_combo.findData(screen.name()))
    item = window.queue.add([clip])[0]
    item.media_settings = {"volume": 75}
    window.load_item(item.id)
    started = False
    previous = None
    began = time.monotonic()

    def finish():
        timer.stop()
        window._project_dirty = False
        window.close()

    def tick():
        nonlocal started, previous
        if not started and window.document is not None and not window.loading:
            started = True
            window.notes_panel.editor.setPlainText(
                "ТЕСТОВЫЕ ЗАМЕТКИ — видны только докладчику.\n"
                "На втором экране должен быть только движущийся тестовый рисунок.\n"
                "Проверьте Пуск / Пауза, Стоп, перемотку и громкость."
            )
            window.start_presentation()
        backend = window.renderer
        player = getattr(backend, "player", None)
        surface = getattr(backend, "surface", None)
        state = {
            "elapsed": round(time.monotonic() - began, 1),
            "screens": [s.name() for s in app.screens()],
            "presenter_screen": window.screen().name(),
            "audience_selection": window.monitor_combo.currentData(),
            "presentation_active": window.presentation.active,
            "backend_active": backend.active,
            "timer_running": window.timer.running,
            "player_state": player.playbackState().name if player else None,
            "position": player.position() if player else None,
            "surface_visible": surface.isVisible() if surface else False,
            "status": window.statusBar().currentMessage(),
        }
        (output / "state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        signature = {k: v for k, v in state.items() if k not in {"elapsed", "position"}}
        if signature != previous:
            with (output / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(state, ensure_ascii=False) + "\n")
            previous = signature
        if (output / "close-request").exists():
            finish()

    timer = QTimer(window)
    timer.timeout.connect(tick)
    timer.start(500)
    QTimer.singleShot(15 * 60 * 1000, finish)
    return app.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    raise SystemExit(main(arguments.source, arguments.output))
