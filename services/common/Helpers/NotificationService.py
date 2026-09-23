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

    def notify(self, message: str, title: str = 'Music Management', push: bool = True) -> bool:
        """Report a milestone as an INFO event, pushed to the phone unless `push` is False.

        `push=False` keeps the event in the log without a notification, for detail that
        belongs to a milestone pushed once elsewhere -- every track of an imported release,
        whose release gets the single push.
        """
        return event_service.emit(level='INFO', title=title, message=message, source=self._source, push=push)


notification_service = NotificationService()
