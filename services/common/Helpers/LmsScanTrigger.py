import logging
import os
import queue
import threading
from collections.abc import Iterable

import requests

from services.common.config_store import ConfigStore
from services.common.Helpers.LmsEndpoint import LmsNotConfigured, lms_api_key, lms_base_url, normalise_host


class LmsScanTrigger:
    """
    Best-effort trigger for an LMS (Logitech Media Server) library scan, via the Subsonic
    `startScan.view` endpoint.

    Two verbs, and the difference matters.

    `trigger()` asks for a library-wide scan and is meant to be called once per
    download/import/tag run (not once per file): LMS's incremental scan only reprocesses
    new/changed files, so triggering it after a batch is cheap.

    `notify(paths)` asks for one or more folders and is called per move. LMS merges and
    debounces those, pauses a running periodic scan for them, and resumes it afterwards, so a
    moved release shows up in seconds instead of after the next library-wide scan.

    `notify` never blocks its caller. A tagger round produces hundreds of calls and the HTTP
    timeout is ten seconds; a move must not wait on a music server. The paths go on a bounded
    queue that a daemon thread drains, and a full queue loses its oldest entry rather than
    holding up the move -- the periodic scan is the backstop for anything dropped here.
    """

    def __init__(self, queue_size: int = 1000):
        self._config = ConfigStore()
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._worker: threading.Thread | None = None
        self._worker_lock = threading.Lock()
        self._warned_unconfigured = False

    def _endpoint(self) -> tuple[list[str], str]:
        """The hosts to notify and the key to do it with, or nothing.

        The setting wins, because that is the settings page doing its job. The
        environment is the fallback -- and on this deployment it is the only source
        there is: `docker/docker-compose.yml` never sets `LMS_HOSTS`, so the setting
        is empty unless somebody typed a host into the page, and for as long as this
        class existed nobody had. It returned here without a word, so a library that
        never picked up a moved folder looked like a fault in LMS.
        """
        configured = self._config.get('lms_hosts')
        hosts = [host.strip() for host in str(configured or '').split(',') if host.strip()]
        if not hosts:
            try:
                hosts = [lms_base_url()]
            except LmsNotConfigured:
                hosts = []

        api_key = str(self._config.get('lms_subsonic_api_key') or '') or lms_api_key()

        if not hosts or not api_key:
            if not self._warned_unconfigured:
                self._warned_unconfigured = True
                missing = ' and '.join(
                    part
                    for part in (
                        'no host (lms_hosts, LMS_URL, LMS_HOSTS or MUMA_SERVER_HOSTS)' if not hosts else '',
                        'no API key (lms_subsonic_api_key, MUMA_SERVER_SUBSONIC_API_KEY or LMS_SUBSONIC_API_KEY)'
                        if not api_key
                        else '',
                    )
                    if part
                )
                logging.warning(
                    'LmsScanTrigger: not configured, LMS will not be told about changes -- %s. '
                    'Scans fall back to whatever schedule LMS runs on its own.',
                    missing,
                )
            return [], ''

        self._warned_unconfigured = False
        return hosts, api_key

    def trigger(self, full_scan: bool = False) -> None:
        hosts, api_key = self._endpoint()
        for host in hosts:
            self._trigger_host(host, api_key, full_scan)

    @staticmethod
    def _scan_url(host: str) -> str:
        return f'{normalise_host(host)}/rest/startScan.view'

    def _trigger_host(self, host: str, api_key: str, full_scan: bool) -> None:
        url = self._scan_url(host)
        params = {'apiKey': api_key, 'v': '1.16.1', 'c': 'music-manager', 'f': 'json'}
        if full_scan:
            params['fullScan'] = 'true'
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            logging.info('Triggered LMS scan on %s (fullScan=%s)', host, full_scan)
        except Exception as e:
            logging.warning('Failed to trigger LMS scan on %s: %s', host, e)

    def notify(self, paths: Iterable) -> None:
        try:
            relative = [p for p in (self._to_library_relative(str(path)) for path in paths) if p]
        except Exception as e:  # a notification must never break the move that triggered it
            logging.warning('LmsScanTrigger: could not resolve %s: %s', paths, e)
            return
        if not relative:
            return

        self._ensure_worker()
        while True:
            try:
                self._queue.put_nowait(relative)
                return
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    return

    def _to_library_relative(self, path: str) -> str:
        """
        muma mounts the library at music_folder_path and LMS sees it at its own root, so an
        absolute path from here names a directory LMS does not have. Everything is sent
        relative to the library root instead.
        """
        root = self._config.get('music_folder_path')
        if not isinstance(root, str) or not root:
            return ''
        root = root.rstrip(os.sep)
        normalised = os.path.normpath(path)
        if normalised == root:
            return ''
        if not normalised.startswith(root + os.sep):
            logging.debug('LmsScanTrigger: %s is outside %s, not notifying', normalised, root)
            return ''
        return normalised[len(root) + 1 :]

    def _ensure_worker(self) -> None:
        with self._worker_lock:
            if self._worker and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._drain, name='lms-scan-notify', daemon=True)
            self._worker.start()

    def _drain(self) -> None:
        while True:
            paths = self._queue.get()
            try:
                self._send(paths)
            except Exception as e:  # never let a music server break an import
                logging.warning('LmsScanTrigger: failed to notify LMS: %s', e)
            finally:
                self._queue.task_done()

    def flush_for_test(self) -> None:
        """Drains the queue synchronously. Only for tests -- production never waits."""
        while not self._queue.empty():
            self._send(self._queue.get_nowait())

    def _send(self, paths: list) -> None:
        hosts, api_key = self._endpoint()
        for host in hosts:
            params = {'apiKey': api_key, 'v': '1.16.1', 'c': 'music-manager', 'f': 'json', 'path': paths}
            try:
                response = requests.get(self._scan_url(host), params=params, timeout=10)
                response.raise_for_status()
                logging.info('Notified LMS on %s of %d path(s)', host, len(paths))
            except Exception as e:
                logging.warning('Failed to notify LMS on %s: %s', host, e)


lms_scan_trigger = LmsScanTrigger()
