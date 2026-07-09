import logging
import requests
from services.common.api.config_store import ConfigStore

class NotificationService:
    def __init__(self):
        self._config = ConfigStore()
        try:
            self.notify_url = self._config.get("notify_url")
            self.notify_topic = self._config.get("notify_topic")

            # Subscribe to config changes
            self._config.subscribe("notify_url", lambda v: setattr(self, 'notify_url', v))
            self._config.subscribe("notify_topic", lambda v: setattr(self, 'notify_topic', v))
        except (KeyError, AttributeError):
            logging.warning("NotificationService: notify_url or notify_topic not found in ConfigStore. Notifications will be disabled.")
            self.notify_url = None
            self.notify_topic = None

    def notify(self, message: str, title: str = "Music Management"):
        """Sends a notification via ntfy.sh"""
        if not self.notify_url or not self.notify_topic:
            logging.warning("NotificationService: notify_url or notify_topic not configured.")
            return False

        url = self.notify_url.rstrip('/') + '/' + self.notify_topic
        try:
            logging.info(f"Sending notification to {url}: {title} - {message[:50]}...")
            response = requests.post(
                url,
                data=message.encode('utf-8'),
                headers={
                    "Title": title,
                },
                timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logging.error(f"Failed to send notification: {e}")
            return False

# Global instance
logging.info("Initializing global NotificationService instance")
notification_service = NotificationService()
