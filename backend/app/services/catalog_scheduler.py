"""Periodic Mangakol catalog sync scheduler (P26).

A single daemon thread that asks the catalog sync to start on a fixed
interval. It implements none of the sync machinery itself — the only
entry point it uses is ``routes.catalog.try_start_sync``, the same start
point the manual ``POST /catalog/sync`` endpoint uses, so the write-gate
/ running-flag handling has exactly one implementation.

Timing contract: the first run happens one full interval after the
scheduler starts (there is deliberately NO catch-up run at process
start); each subsequent tick fires one interval after the previous tick.
Restarting the process resets the countdown, which keeps the gap between
completed syncs within ``[interval, 2*interval)``.

Failure policy: a tick that raises is logged and the loop continues —
the scheduler thread must never die silently. While a store import holds
the catalog write gate the tick re-tries for up to ``gate_wait_seconds``
(a manual endpoint would answer 409 and let a human retry; the scheduler
has no human, so it waits the import out instead of skipping a day).
``stop()`` is prompt even mid gate-wait because all sleeps go through
the stop event.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

logger = logging.getLogger("yomiba.catalog.scheduler")

#: ``routes.catalog.try_start_sync`` — returns "started" | "already_running"
#: | "gate_held".
StartSync = Callable[[], str]


class CatalogSyncScheduler:
    """Starts a catalog sync every ``interval_seconds`` seconds.

    ``start_sync`` must be callable with no arguments and return one of
    ``"started"``, ``"already_running"`` or ``"gate_held"``.
    """

    def __init__(
        self,
        start_sync: StartSync,
        interval_seconds: float,
        *,
        gate_wait_seconds: float = 900.0,
        poll_seconds: float = 60.0,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._start_sync = start_sync
        self._interval_seconds = interval_seconds
        self._gate_wait_seconds = gate_wait_seconds
        self._poll_seconds = poll_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # -- lifecycle -------------------------------------------------------------
    def start(self) -> None:
        """Start the worker thread (idempotent — a second start is ignored)."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("catalog scheduler already running; start() ignored")
            return
        self._stop_event.clear()
        thread = threading.Thread(
            target=self._loop, name="catalog-sync-scheduler", daemon=True
        )
        self._thread = thread
        thread.start()
        logger.info(
            "catalog scheduler started (first run in %.1fh, then every %.1fh)",
            self._interval_seconds / 3600, self._interval_seconds / 3600,
        )

    def stop(self, timeout: float = 10.0) -> None:
        """Signal the worker to stop and join it.

        Prompt even while the worker is waiting on the catalog gate: the
        stop event is what the worker sleeps on.
        """
        thread = self._thread
        if thread is None:
            return
        self._stop_event.set()
        thread.join(timeout)
        if thread.is_alive():
            logger.warning(
                "catalog scheduler thread still alive after %.1fs", timeout
            )
        else:
            self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- worker ----------------------------------------------------------------
    def _loop(self) -> None:
        # First tick after one full interval — no catch-up at startup.
        while not self._stop_event.wait(self._interval_seconds):
            self._tick()

    def _tick(self) -> None:
        try:
            result = self._try_start_with_gate_wait()
            if result == "started":
                logger.info("scheduled catalog sync started")
            elif result == "already_running":
                logger.info(
                    "scheduled catalog sync tick skipped: a sync is "
                    "already running"
                )
            elif result is None:
                logger.info(
                    "scheduled catalog sync tick aborted: shutdown in progress"
                )
            # "gate_held" (budget exhausted) is already logged in the wait.
        except Exception:  # noqa: BLE001 - the scheduler must not die
            logger.exception("catalog scheduler tick crashed; continuing")

    def _try_start_with_gate_wait(self) -> str | None:
        """Call ``start_sync``, waiting out a held catalog gate (bounded).

        Returns the start result, or ``None`` when shutdown was signalled
        while waiting.
        """
        deadline = time.monotonic() + max(0.0, self._gate_wait_seconds)
        while True:
            result = self._start_sync()
            if result != "gate_held":
                return result
            if self._stop_event.is_set():
                return None
            if time.monotonic() >= deadline:
                logger.warning(
                    "scheduled catalog sync skipped: a store import still "
                    "holds the catalog write gate after %.0fs",
                    max(0.0, self._gate_wait_seconds),
                )
                return "gate_held"
            if self._stop_event.wait(self._poll_seconds):
                return None
