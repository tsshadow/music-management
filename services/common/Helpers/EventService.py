"""Eén stroom van events, met de database als bron van waarheid.

Elke service schrijft hier zijn events in. De aanroep is niet-blokkerend: het
event gaat op een bounded queue die een worker-thread leegtrekt. Synchroon
schrijven zou elke logregel een database-round-trip aan een lopende download
hangen.

Foutmeldingen gaan hier bewust naar stderr en niet via `logging`. Een logregel
zou via EventLogHandler opnieuw als event binnenkomen en zichzelf voeden.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from services.common.Helpers.DatabaseConnector import DatabaseConnector

LEVELS = ('INFO', 'WARNING', 'ERROR', 'CRITICAL')

QUEUE_MAXSIZE = 1000
RETRY_DELAYS = (1, 4, 16)
TITLE_MAX_LENGTH = 255

_INSERT = 'INSERT INTO events (level, source, logger, title, message, context) VALUES (%s, %s, %s, %s, %s, %s)'


@dataclass
class Event:
    level: str
    title: str
    message: str
    source: str
    logger: str | None = None
    context: dict[str, Any] | None = None
    push: bool = False


class EventQueue:
    """Bounded queue waarin INFO wijkt voor wat ernstiger is.

    Bij overloop verdwijnt het oudste INFO-item. Zitten er alleen WARNING en
    hoger in, dan wordt het nieuwe event geweigerd -- liever een geweigerd
    event dan een verloren fout.
    """

    def __init__(self, maxsize: int = QUEUE_MAXSIZE) -> None:
        self._items: deque[Event] = deque()
        self._maxsize = maxsize
        self._condition = threading.Condition()

    def __len__(self) -> int:
        with self._condition:
            return len(self._items)

    def put(self, event: Event) -> bool:
        with self._condition:
            if len(self._items) >= self._maxsize and not self._drop_one_info():
                return False
            self._items.append(event)
            self._condition.notify()
            return True

    def _drop_one_info(self) -> bool:
        for index, item in enumerate(self._items):
            if item.level == 'INFO':
                del self._items[index]
                return True
        return False

    def get(self, timeout: float | None = None) -> Event | None:
        with self._condition:
            if not self._items and not self._condition.wait(timeout):
                return None
            if not self._items:
                return None
            return self._items.popleft()


class EventService:
    def __init__(self, sinks: list | None = None, queue_maxsize: int = QUEUE_MAXSIZE) -> None:
        self._queue = EventQueue(maxsize=queue_maxsize)
        self._sinks = list(sinks) if sinks is not None else []
        self._worker: threading.Thread | None = None
        self._worker_lock = threading.Lock()

    def add_sink(self, sink) -> None:
        self._sinks.append(sink)

    def is_alive(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def emit(
        self,
        level: str,
        title: str,
        message: str,
        source: str,
        logger: str | None = None,
        context: dict[str, Any] | None = None,
        push: bool = False,
    ) -> bool:
        if level not in LEVELS:
            raise ValueError(f'unknown level {level!r}, expected one of {LEVELS}')
        event = Event(
            level=level,
            title=title[:TITLE_MAX_LENGTH],
            message=message,
            source=source,
            logger=logger,
            context=context,
            push=push,
        )
        self._ensure_worker()
        accepted = self._queue.put(event)
        if not accepted:
            print(f'EventService: queue vol, {level} event geweigerd: {title}', file=sys.stderr)
        return accepted

    def _ensure_worker(self) -> None:
        with self._worker_lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._run, name='event-worker', daemon=True)
            self._worker.start()

    def _run(self) -> None:
        while True:
            try:
                event = self._queue.get(timeout=1.0)
                if event is None:
                    continue
                self._write(event)
                self._dispatch(event)
            except Exception as exc:  # de worker mag nooit sterven
                print(f'EventService: worker fout: {exc}', file=sys.stderr)

    def _write(self, event: Event) -> bool:
        attempts = len(RETRY_DELAYS) + 1
        for attempt in range(attempts):
            try:
                conn = DatabaseConnector().connect()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            _INSERT,
                            (
                                event.level,
                                event.source,
                                event.logger,
                                event.title,
                                event.message,
                                json.dumps(event.context) if event.context else None,
                            ),
                        )
                    conn.commit()
                finally:
                    conn.close()
                return True
            except Exception as exc:
                if attempt == attempts - 1:
                    print(
                        f'EventService: {event.level} event verloren na {attempts} pogingen ({exc}): {event.title}',
                        file=sys.stderr,
                    )
                    return False
                time.sleep(RETRY_DELAYS[attempt])
        return False

    def _dispatch(self, event: Event) -> None:
        for sink in self._sinks:
            try:
                sink.handle(event)
            except Exception as exc:
                print(f'EventService: sink {type(sink).__name__} faalde: {exc}', file=sys.stderr)


event_service = EventService()
