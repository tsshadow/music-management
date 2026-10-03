"""A stop event that ends a background loop after an exact number of pauses (bug report 099).

Loop tests used to end `run_forever` by patching `time.sleep` with a finite `side_effect`
list whose last item raised. `time.sleep` is one function for the whole process, so any
other thread that slept during the test -- the event writer retrying a database write --
consumed items from that list, and the test died on `StopIteration`. `run_forever` waits on
its `stop` event instead of sleeping, so a test hands it one of these and gets exactly the
number of rounds it asked for, without real waiting and without touching anything shared.
"""

from __future__ import annotations

import threading


class StopAfter(threading.Event):
    """A `threading.Event` whose `wait` never blocks and sets the event on the `rounds`-th call.

    `delays` records every timeout the loop asked to wait, in order, so a test can assert
    the backoff and interval arithmetic the way it used to on the patched sleep.
    """

    def __init__(self, rounds: int) -> None:
        super().__init__()
        if rounds < 1:
            raise ValueError('rounds must be at least 1')
        self._rounds = rounds
        self.delays: list[float | None] = []

    def wait(self, timeout: float | None = None) -> bool:
        """Record `timeout`, set the event once `rounds` waits have been made, return whether it is set."""
        if not self.is_set():
            self.delays.append(timeout)
            if len(self.delays) >= self._rounds:
                self.set()
        return self.is_set()
