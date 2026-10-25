import time
from typing import Dict


class StageTimer:
    """Context manager to measure and log execution latencies across pipeline stages."""

    def __init__(self):
        self.timings: Dict[str, float] = {}
        self._current_stage: str = ""
        self._start_time: float = 0.0

    def start(self, stage_name: str):
        self._current_stage = stage_name
        self._start_time = time.perf_counter()

    def stop(self):
        if self._current_stage:
            elapsed = time.perf_counter() - self._start_time
            self.timings[self._current_stage] = round(elapsed, 4)
            self._current_stage = ""

    def stage(self, stage_name: str):
        return _StageContext(self, stage_name)


class _StageContext:
    def __init__(self, timer: StageTimer, stage_name: str):
        self.timer = timer
        self.stage_name = stage_name

    def __enter__(self):
        self.timer.start(self.stage_name)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.timer.stop()
