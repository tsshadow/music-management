"""Dunne laag over de events-stroom, voor de vier plekken die een mijlpaal melden.

De signatuur blijft precies wat hij was, zodat de bestaande aanroepers niet
hoeven te veranderen. Wat wél verandert: de melding gaat nu eerst de database
in en pas daarna naar ntfy, in plaats van uitsluitend naar ntfy.
"""

from __future__ import annotations

from services.common.Helpers.EventService import event_service

DEFAULT_SOURCE = 'music-manager'


class NotificationService:
    def __init__(self, source: str = DEFAULT_SOURCE) -> None:
        self._source = source

    def notify(self, message: str, title: str = 'Music Management') -> bool:
        """Meld een mijlpaal: een INFO-event dat wél de telefoon mag halen."""
        return event_service.emit(level='INFO', title=title, message=message, source=self._source, push=True)


notification_service = NotificationService()
