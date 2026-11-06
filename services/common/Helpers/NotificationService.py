"""Thin layer over the events stream, for the four places that report a milestone.

The signature stays exactly what it was, so the existing callers do not have
to change. What does change: the notification now goes into the database first
and then to ntfy, instead of only to ntfy.
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
