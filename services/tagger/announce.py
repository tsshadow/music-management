"""What a worker does after it tagged a file it just produced.

The downloader and importer containers tag their own files the moment they land, and
until now that was the end of it: nothing wrote the tagger's bookkeeping, so the next
folder walk in music-manager found a path it did not know and tagged the file a second
time; LMS learned of the file at its next scheduled scan; and the muma scanner saw it on
its hourly round. `announce` closes those three gaps from the worker itself. Every step
is best effort -- a download that succeeded must not fail because a server was slow.

The three steps, and why each is where it is:

- `mark_processed` writes the row the walk consults, with the mtime *after* the tag pass
  wrote the file. The workers have the database; that is all this needs.
- `lms_scan_trigger.notify` hands LMS the folder. It needs the LMS host and key, which
  docker/docker-compose.yml passes to the workers through the `environment-lms` anchor.
- The muma scanner (the `library_*` tables the app and the curation pages read) is a
  thread inside music-manager, so it is asked over HTTP with the system key the workers
  already carry for the auth service.
"""

import logging
import os
from pathlib import Path

import requests

from services.common.Helpers.LmsScanTrigger import lms_scan_trigger
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper

logger = logging.getLogger('tagger.announce')

#: How long to wait for music-manager to scan the one file. It reads the tags it just
#: got and writes a handful of rows; ten seconds is the LMS trigger's budget as well.
SCAN_TIMEOUT_SECONDS = 10


def _api_base() -> str:
    """Where music-manager listens, as the workers already know it for the auth service."""
    base = os.getenv('MUMA_API_URL') or os.getenv('AUTH_SERVICE_URL') or ''
    return base.rstrip('/')


def _system_key() -> str:
    # Same resolution as services/music_manager/api_key.py, which the worker images do
    # not carry: API_KEY wins, MUMA_API_KEY is what the deployment's .env spells.
    return os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or ''


def request_scan(path: str) -> bool:
    """Ask music-manager to read this one file into the library tables. False when it
    could not be asked; the hourly scanner round is the backstop."""
    base, key = _api_base(), _system_key()
    if not base or not key:
        logger.warning('announce: no MUMA_API_URL/AUTH_SERVICE_URL or system key, %s waits for the hourly scan', path)
        return False
    try:
        response = requests.post(
            f'{base}/api/scanner/scan/file',
            params={'path': path},
            headers={'x-api-key': key},
            timeout=SCAN_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.warning('announce: scan request for %s failed: %s', path, e)
        return False


def announce(path: str | Path) -> None:
    """Record, tell LMS, ask the scanner. Never raises."""
    file = Path(path)
    try:
        ProcessedFilesHelper().mark_processed(str(file), file.stat().st_mtime)
    except Exception as e:
        logger.warning('announce: could not record %s as tagged: %s', file, e)
    try:
        lms_scan_trigger.notify([str(file.parent)])
    except Exception as e:
        logger.warning('announce: could not notify LMS about %s: %s', file.parent, e)
    request_scan(str(file))
