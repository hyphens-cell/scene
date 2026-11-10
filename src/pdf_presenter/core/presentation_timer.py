import time
from collections.abc import Callable


class PresentationTimer:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._accumulated = 0.0
        self._started: float | None = None

    @property
    def running(self) -> bool:
        return self._started is not None

    @property
    def elapsed(self) -> float:
        return self._accumulated + (
            self._clock() - self._started if self._started is not None else 0
        )

    def start(self) -> None:
        self._accumulated = 0
        self._started = self._clock()

    def pause(self) -> None:
        self._accumulated = self.elapsed
        self._started = None

    def resume(self) -> None:
        if not self.running:
            self._started = self._clock()

    def reset(self) -> None:
        self._accumulated = 0
        if self.running:
            self._started = self._clock()

    def formatted(self) -> str:
        seconds = max(0, int(self.elapsed))
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"
