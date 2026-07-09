import requests
import json
import threading
import time
import logging
from services.common.api.config_store import ConfigStore
from services.music_manager.database import get_db_connection

logger = logging.getLogger("ntfy-listener")

def listen_to_ntfy():
    config = ConfigStore()
    
    def get_url():
        url = config.get("notify_url")
        topic = config.get("notify_topic")
        if not url or not topic:
            return None
        return f"{url.rstrip('/')}/{topic}/json"

    while True:
        url = get_url()
        if not url:
            logger.warning("ntfy-listener: notify_url or notify_topic not configured. Retrying in 30s...")
            time.sleep(30)
            continue
            
        try:
            logger.info(f"Connecting to ntfy.sh at {url}")
            with requests.get(url, stream=True, timeout=None) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if data.get("event") == "message":
                                title = data.get("title", "Music Management")
                                message = data.get("message", "")
                                topic = data.get("topic", "")
                                logger.info(f"Received notification: {title} - {message[:50]}")
                                
                                # Store in DB
                                conn = get_db_connection()
                                if conn:
                                    try:
                                        with conn.cursor() as cursor:
                                            cursor.execute(
                                                "INSERT INTO notifications (title, message, topic) VALUES (%s, %s, %s)",
                                                (title, message, topic)
                                            )
                                        conn.commit()
                                    finally:
                                        conn.close()
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"ntfy-listener error: {e}. Retrying in 10s...")
            time.sleep(10)

def start_ntfy_listener():
    thread = threading.Thread(target=listen_to_ntfy, daemon=True)
    thread.start()
    return thread
