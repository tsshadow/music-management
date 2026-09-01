"""Ntfy als afgeleide sink op de events-stroom.

Twee topics, want de ntfy Android-app abonneert per topic en filtert niet
betrouwbaar op priority. Wat aandacht vraagt hoort daarom in een eigen topic,
niet in een header van het topic dat je de hele dag ziet.
"""

from __future__ import annotations

import sys
import time

import requests

from services.common.config_store import ConfigStore
from services.common.Helpers.EventService import Event

ALERT_LEVELS = ('WARNING', 'ERROR', 'CRITICAL')
PRIORITY_BY_LEVEL = {'WARNING': 'high', 'ERROR': 'high', 'CRITICAL': 'urgent'}
TAG_BY_LEVEL = {'WARNING': 'warning', 'ERROR': 'rotating_light', 'CRITICAL': 'sos'}
# De rem sleutelt op (level, source, logger) en bewust niet op de titel. Veel
# routinewaarschuwingen dragen een afteller in hun tekst ('nog 240s afkoelen'),
# waardoor elke herhaling een andere titel oplevert en een titel-sleutel nooit
# tweemaal raakt. Op de logger-naam vallen die herhalingen wel samen. Events die
# rechtstreeks worden ge-emit hebben geen logger; die vallen terug op de titel.
DEDUP_WINDOW_SECONDS = 300
REQUEST_TIMEOUT_SECONDS = 10


class NtfySink:
    def __init__(self, config=None, clock=time.monotonic) -> None:
        self._config = config if config is not None else ConfigStore()
        self._clock = clock
        self._last_sent: dict[tuple[str, str, str], float] = {}

    def handle(self, event: Event) -> None:
        topic = self._topic_for(event)
        if not topic:
            return
        base_url = self._config.get('notify_url')
        if not base_url:
            return
        if self._is_duplicate(event):
            return
        self._post(f"{base_url.rstrip('/')}/{topic}", event)

    def _topic_for(self, event: Event) -> str | None:
        if event.level in ALERT_LEVELS:
            return self._config.get('notify_topic_alerts')
        if event.push:
            return self._config.get('notify_topic')
        return None

    def _is_duplicate(self, event: Event) -> bool:
        """Eén verbroken verbinding produceert honderden identieke events.

        Zonder deze rem staan die allemaal binnen een uur op de telefoon. De
        rij in de database wordt wel geschreven; alleen de push blijft achter.
        """
        now = self._clock()
        self._prune(now)
        key = (event.level, event.source, event.logger or event.title)
        if key in self._last_sent and now - self._last_sent[key] < DEDUP_WINDOW_SECONDS:
            return True
        self._last_sent[key] = now
        return False

    def _prune(self, now: float) -> None:
        stale = [key for key, sent in self._last_sent.items() if now - sent >= DEDUP_WINDOW_SECONDS]
        for key in stale:
            del self._last_sent[key]

    def _post(self, url: str, event: Event) -> None:
        headers = {'Title': event.title}
        if event.level in PRIORITY_BY_LEVEL:
            headers['Priority'] = PRIORITY_BY_LEVEL[event.level]
            headers['Tags'] = TAG_BY_LEVEL[event.level]
        try:
            response = requests.post(
                url, data=event.message.encode('utf-8'), headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
        except Exception as exc:
            # stderr, niet logging: een logregel komt via de handler terug als event
            print(f'NtfySink: push naar {url} mislukt: {exc}', file=sys.stderr)
