"""Bounded admission in front of the model.

The API replicas can accept far more requests than one local model can answer in time. Without a
bound, the surplus queues inside the model server, where nothing measures it, and a request whose
caller gave up long ago still gets its turn.

The gate makes that queue explicit and short:

- `concurrency` model calls run at once in this process, `queue` more may wait;
- a call that finds the line full is refused at once (`Overloaded`), which costs nothing;
- a call still waiting when the request deadline passes is dropped before the model is asked
  (`DeadlineExceeded`);
- the time spent waiting is recorded on its own, apart from the model's execution time.

The bound is per process: N replicas admit N times as much. It limits what one replica sends,
it is not a global rate limit.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

from ..telemetry.genai import RagMetrics

REASON = "rag.admission.reason"


class Overloaded(Exception):
    """The waiting line is full: the request is refused before any work is done."""


class DeadlineExceeded(Exception):
    """The request deadline passed before the model could be asked, or while it was answering."""


class Admission:
    def __init__(self, concurrency: int, queue: int, metrics: RagMetrics):
        self.concurrency, self.queue, self.metrics = concurrency, queue, metrics
        self._slots = threading.Semaphore(concurrency)
        self._lock = threading.Lock()
        self._inside = 0            # calls holding a slot or waiting for one

    @contextmanager
    def slot(self, step: str, deadline: float | None = None) -> Iterator[float]:
        """Hold one model slot for the duration of the block. Yields the seconds spent waiting.
        `deadline` is a time.monotonic() value; None means wait as long as it takes."""
        with self._lock:
            if self._inside >= self.concurrency + self.queue:
                self.metrics.admission_rejections.add(1, {REASON: "queue_full"})
                raise Overloaded(f"{self._inside} model calls already running or waiting")
            self._inside += 1
        self.metrics.admission_waiting.add(1)
        start = time.monotonic()
        try:
            remaining = None if deadline is None else max(deadline - start, 0.0)
            admitted = self._slots.acquire(timeout=remaining)
        finally:
            self.metrics.admission_waiting.add(-1)
        waited = time.monotonic() - start
        self.metrics.admission_wait.record(waited, {"langgraph.node": step})
        if admitted and deadline is not None and time.monotonic() >= deadline:
            self._slots.release()               # the slot came at the very last moment: too late to start
            admitted = False
        if not admitted:
            with self._lock:
                self._inside -= 1
            self.metrics.admission_rejections.add(1, {REASON: "deadline"})
            raise DeadlineExceeded(f"waited {waited:.1f}s for the model, past the request deadline")
        try:
            yield waited
        finally:
            self._slots.release()
            with self._lock:
                self._inside -= 1
