"""Register van de threads die horen te blijven draaien.

Alleen oneindige lussen horen hier thuis. Eenmalige achtergrondtaken zoals
run_fetch_missing geven na afloop netjes terug; die zouden de liveness-controle
permanent rood zetten.

Two things are tracked per loop, because liveness alone proved to say too little:

- whether the thread is still alive, and
- when the loop last *completed* a tick (its heartbeat), registered by `run_forever`.

A loop whose thread is alive but whose heartbeat is older than its own `stale_after`
is reported unhealthy just like a dead one: it is stuck, and a stuck loop does as much
work as a dead one. A thread started without `run_forever` has no heartbeat and is
judged on liveness alone.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger('music-manager.threads')

# First retry after a failed tick; doubles per consecutive failure up to the loop's own
# interval, so a MariaDB restart costs seconds instead of a full (possibly daily) round.
FIRST_BACKOFF_SECONDS = 10.0
# The shortest staleness window any loop gets. A loop with a five-second interval must
# not flip /health red because one tick took a minute.
MIN_STALE_AFTER_SECONDS = 3600.0


@dataclass
class _Heartbeat:
    """The last completed tick of one loop, and how old it may get before it counts as stuck."""

    stale_after: float
    last_beat_monotonic: float
    last_beat_wall: float
    ticks: int = 0
    failures: int = 0


_threads: dict[str, threading.Thread] = {}
_heartbeats: dict[str, _Heartbeat] = {}
_lock = threading.Lock()


def start_thread(name: str, target, args: tuple = ()) -> threading.Thread:
    """Start `target` as a daemon thread and register it under `name` for /health."""
    thread = threading.Thread(target=target, args=args, name=name, daemon=True)
    with _lock:
        _threads[name] = thread
    thread.start()
    return thread


def default_stale_after(interval: float) -> float:
    """Three missed rounds, but never less than an hour."""
    return max(3.0 * interval, MIN_STALE_AFTER_SECONDS)


def register_heartbeat(name: str, stale_after: float) -> None:
    """Start tracking `name`'s heartbeat, counting from now.

    Counting from registration rather than from nothing is what keeps /health green right
    after startup: the first tick (the tagger's first round, a full scan) is allowed its
    whole `stale_after` window before it counts as overdue.
    """
    with _lock:
        _heartbeats[name] = _Heartbeat(
            stale_after=float(stale_after),
            last_beat_monotonic=time.monotonic(),
            last_beat_wall=time.time(),
        )


def beat(name: str) -> None:
    """Record that `name` completed a tick just now."""
    with _lock:
        heartbeat = _heartbeats.get(name)
        if heartbeat is None:
            return
        heartbeat.last_beat_monotonic = time.monotonic()
        heartbeat.last_beat_wall = time.time()
        heartbeat.ticks += 1
        heartbeat.failures = 0


def _record_failure(name: str) -> int:
    """Count one more consecutive failed tick for `name` and return the running total."""
    with _lock:
        heartbeat = _heartbeats.get(name)
        if heartbeat is None:
            return 1
        heartbeat.failures += 1
        return heartbeat.failures


def run_forever(
    name: str,
    tick: Callable[[], float | None],
    interval: float,
    *,
    stale_after: float | None = None,
    backoff: bool = True,
    stop: threading.Event | None = None,
) -> None:
    """Run `tick` for the lifetime of the process: tick, sleep, tick, and never die on an exception.

    Every background loop used to be its own `while True`, and several had nothing around
    the body: one MariaDB restart or CIFS hiccup ended the loop for the lifetime of the
    process. Here each iteration is wrapped in a catch-all that logs with
    `logger.exception` -- so the failure reaches the events pipeline as an ERROR -- and
    carries on.

    `tick` may return a number of seconds to override the next sleep (the news recorder
    uses that for its own schedule); `None` means `interval`. After a failed tick the
    loop sleeps FIRST_BACKOFF_SECONDS, doubling per consecutive failure up to `interval`,
    unless `backoff=False`, in which case a failure is followed by the normal interval
    (for loops whose next attempt must not come sooner, such as the lms.db sync).

    Only `Exception` is caught: KeyboardInterrupt and SystemExit still end the loop. The
    pause between ticks is always `stop.wait(delay)`, and the loop returns as soon as `stop`
    is set; without a `stop` the loop gets a private event nobody sets, which makes the wait
    a plain sleep. Never `time.sleep`: that is one function shared by every thread in the
    process, and tests used to end this loop by patching it with a finite `side_effect`
    list -- which any other thread sleeping at that moment (the event writer retrying a
    database write) consumed as well (bug report 099). Tests pass a `stop` event instead
    and drive an exact number of rounds through it.
    """
    register_heartbeat(name, stale_after if stale_after is not None else default_stale_after(interval))
    if stop is None:
        stop = threading.Event()
    while not stop.is_set():
        try:
            requested = tick()
        except Exception:  # pylint: disable=broad-except  # the loop must outlive any one tick
            failures = _record_failure(name)
            delay = min(FIRST_BACKOFF_SECONDS * 2 ** (failures - 1), interval) if backoff else interval
            logger.exception('%s: tick failed (%d in a row), retrying in %.0fs', name, failures, delay)
        else:
            beat(name)
            delay = interval if requested is None else max(0.0, requested)
        if stop.wait(delay):
            return


def _is_fresh(name: str, now: float) -> bool:
    """False when `name` has a heartbeat that is older than its staleness window."""
    heartbeat = _heartbeats.get(name)
    if heartbeat is None:
        return True
    return now - heartbeat.last_beat_monotonic <= heartbeat.stale_after


def thread_status() -> dict[str, bool]:
    """Per registered loop: True when its thread is alive and its heartbeat is not stale."""
    now = time.monotonic()
    with _lock:
        return {name: thread.is_alive() and _is_fresh(name, now) for name, thread in _threads.items()}


def thread_heartbeats() -> dict[str, dict]:
    """The detail behind thread_status(): liveness and heartbeat age per registered loop.

    `last_tick_age_seconds` is None for a thread that has no heartbeat (not started through
    `run_forever`, or not yet at its first line), which is then judged on liveness alone.
    """
    now = time.monotonic()
    result: dict[str, dict] = {}
    with _lock:
        for name, thread in _threads.items():
            heartbeat = _heartbeats.get(name)
            entry: dict = {'alive': thread.is_alive(), 'stale': not _is_fresh(name, now)}
            if heartbeat is None:
                entry.update(last_tick_age_seconds=None, stale_after_seconds=None, ticks=0, failures=0)
            else:
                entry.update(
                    last_tick_age_seconds=round(now - heartbeat.last_beat_monotonic, 1),
                    stale_after_seconds=heartbeat.stale_after,
                    ticks=heartbeat.ticks,
                    failures=heartbeat.failures,
                )
            result[name] = entry
    return result


def reset() -> None:
    """Alleen voor tests: leeg het register."""
    with _lock:
        _threads.clear()
        _heartbeats.clear()
