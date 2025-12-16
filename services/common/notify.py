import logging
import os
import requests
from typing import Optional


class NotifyService:
    """
    Service for sending notifications via ntfy.

    Sends push notifications when new music is downloaded.
    """

    def __init__(self):
        self.ntfy_url = os.getenv('NTFY_URL', 'https://ntfy.teunschriks.nl')
        self.enabled = os.getenv('NTFY_ENABLED', 'true').lower() == 'true'

        if not self.enabled:
            logging.info('Ntfy notifications are disabled')

    def send_notification(
        self,
        topic: str,
        message: str,
        title: Optional[str] = None,
        priority: str = 'default',
        tags: Optional[list[str]] = None
    ) -> bool:
        """
        Send a notification to ntfy.

        Args:
            topic: The ntfy topic to send to
            message: The notification message
            title: Optional notification title
            priority: Priority level (min, low, default, high, urgent)
            tags: Optional list of tags/emojis

        Returns:
            bool: True if notification was sent successfully, False otherwise
        """
        if not self.enabled:
            logging.debug('Notifications disabled, skipping: %s', message)
            return False

        try:
            url = f'{self.ntfy_url}/{topic}'
            headers = {}

            if title:
                headers['Title'] = title

            if priority:
                headers['Priority'] = priority

            if tags:
                headers['Tags'] = ','.join(tags)

            response = requests.post(
                url,
                data=message.encode('utf-8'),
                headers=headers,
                timeout=10
            )

            response.raise_for_status()
            logging.debug('Notification sent successfully to %s', topic)
            return True

        except requests.exceptions.RequestException as e:
            logging.error('Failed to send notification to %s: %s', topic, e)
            return False
        except Exception as e:
            logging.error('Unexpected error sending notification: %s', e)
            return False

    def notify_download(
        self,
        source: str,
        title: str,
        artist: Optional[str] = None,
        account: Optional[str] = None,
        genres: Optional[list[str]] = None,
        label: Optional[str] = None
    ) -> bool:
        """
        Send a notification about a newly downloaded track.

        Args:
            source: Download source (youtube, soundcloud, telegram)
            title: Track title
            artist: Optional artist name
            account: Optional account/channel name
            genres: Optional list of genres
            label: Optional label/publisher name

        Returns:
            bool: True if notification was sent successfully
        """
        topic = f'music-management-downloader'

        # Build message
        parts = [f'📥 New track from {source.upper()}']

        # Artist and title
        if artist:
            parts.append(f'🎵 {artist} - {title}')
        else:
            parts.append(f'🎵 {title}')

        # Genres
        if genres and len(genres) > 0:
            genre_str = ', '.join(genres[:3])  # Limit to first 3 genres
            if len(genres) > 3:
                genre_str += f' (+{len(genres) - 3})'
            parts.append(f'🎼 {genre_str}')

        # Label/Publisher
        if label:
            parts.append(f'🏷️ {label}')

        # Account/Channel
        if account:
            parts.append(f'📺 {account}')

        message = '\n'.join(parts)

        # Determine emoji tag based on source
        tags = []
        if source.lower() == 'youtube':
            tags = ['red_circle', 'musical_note']
        elif source.lower() == 'soundcloud':
            tags = ['orange_circle', 'musical_note']
        elif source.lower() == 'telegram':
            tags = ['blue_circle', 'musical_note']
        else:
            tags = ['musical_note']

        return self.send_notification(
            topic=topic,
            message=message,
            title='New Music Downloaded',
            priority='default',
            tags=tags
        )
