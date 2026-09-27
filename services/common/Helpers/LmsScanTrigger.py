import logging
import os
import queue
import threading
import time
from collections.abc import Iterable

import requests

from services.common.config_store import ConfigStore
from services.common.Helpers.LmsEndpoint import (
    LmsNotConfigured,
    lms_base_url,
    normalise_host,
    redact_url,
    resolve_lms_api_key,
)


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

    `notify` never blocks its caller. A tagger round produces hundreds of calls; a move must
    not wait on a music server. The paths go on a bounded queue that a daemon thread drains,
    and a full queue loses its oldest entry rather than holding up the move -- the periodic
    scan is the backstop for anything dropped here.

    A request that does not get through (timeout, connection error) is retried once after a
    short pause. If that fails too, nothing is thrown away: the paths of a notify are carried
    and sent with the next one, and a failed library-wide trigger is sent again with the next
    request of either kind that reaches LMS. If no further request comes at all, LMS's own
    periodic scan picks the change up (bug report 120). An LMS that stops answering is one
    WARNING when it starts; every further failure of the same outage is INFO, and the first
    success afterwards says so.
    """

    #: (connect, read) in seconds. LMS answers a scan request as soon as it is queued -- a
    #: library-wide one joins a running scan instead of aborting it and waiting for that to
    #: unwind (bug report 120) -- so the read budget only has to cover a busy server.
    TIMEOUT = (5, 30)
    #: Pause before the single retry.
    RETRY_DELAY_SECONDS = 2.0
    #: Paths kept for the next notify after a failed one; the oldest go first.
    MAX_CARRIED_PATHS = 1000

    def __init__(self, queue_size: int = 1000):
        self._config = ConfigStore()
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._worker: threading.Thread | None = None
        self._worker_lock = threading.Lock()
        self._warned_unconfigured = False
        # Guarded by _state_lock: trigger() runs on the caller's thread, _send on the worker.
        self._state_lock = threading.Lock()
        self._carried: dict[str, None] = {}
        self._trigger_pending = False
        self._failing = False

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

        api_key = resolve_lms_api_key(self._config)

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
        """Ask every configured LMS for a library-wide scan; never raises, never loses it quietly."""
        hosts, api_key = self._endpoint()
        if not hosts:
            return
        params = {'apiKey': api_key, 'v': '1.16.1', 'c': 'music-manager', 'f': 'json'}
        if full_scan:
            params['fullScan'] = 'true'
        # Every host is asked, even after one fails -- hence the list, not a short-circuit.
        results = [self._request(host, params, f'trigger LMS scan (fullScan={full_scan})') for host in hosts]
        delivered = all(results)
        with self._state_lock:
            self._trigger_pending = not delivered
        if delivered:
            logging.info('Triggered LMS scan on %s (fullScan=%s)', ', '.join(hosts), full_scan)

    @staticmethod
    def _scan_url(host: str) -> str:
        return f'{normalise_host(host)}/rest/startScan.view'

    def _request(self, host: str, params: dict, what: str) -> bool:
        """One startScan request with a single retry on a transient failure. True when LMS took it.

        Only a timeout or a refused connection is worth a second try; a 4xx/5xx will say the
        same thing again two seconds later.
        """
        last_error: Exception | None = None
        for attempt in range(2):
            if attempt:
                time.sleep(self.RETRY_DELAY_SECONDS)
            try:
                response = requests.get(self._scan_url(host), params=params, timeout=self.TIMEOUT)
                response.raise_for_status()
            except (requests.Timeout, requests.ConnectionError) as e:
                last_error = e
                continue
            except Exception as e:  # never let a music server break a move or a round
                last_error = e
                break
            self._mark_reachable(host)
            return True
        self._mark_failing(host, what, last_error)
        return False

    def _mark_failing(self, host: str, what: str, error: Exception | None) -> None:
        """WARNING when LMS starts failing, INFO for every further failure of the same outage.

        Each failure used to be its own WARNING, and every WARNING is a push on the alerts
        topic: ~90 a night, for requests that were, as it turned out, only slow.
        """
        with self._state_lock:
            first = not self._failing
            self._failing = True
        level = logging.WARNING if first else logging.INFO
        logging.log(
            level,
            'Failed to %s on %s after a retry, will resend with the next request: %s',
            what,
            host,
            redact_url(str(error)),
        )

    def _mark_reachable(self, host: str) -> None:
        with self._state_lock:
            recovered = self._failing
            self._failing = False
        if recovered:
            logging.info('LMS on %s answers scan requests again', host)

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

    # A tagger round finishes a folder every fifth of a second, and each one used to be its
    # own HTTP request: LMS logged five scan requests per second for hours after 0.49.0 made
    # the notification arrive at all. It survives that -- its own collector merges the paths
    # anyway -- but every request occupies a Wt thread, and a starved Wt thread pool is how
    # this server has produced site-wide 504s before. Merging here costs nothing and the scan
    # is identical. Only what is already queued is taken; nothing waits for more, because the
    # point of the queue is that a move never blocks on a music server.
    def _drain(self) -> None:
        while True:
            paths = self._queue.get()
            taken = 1
            try:
                merged = dict.fromkeys(paths)
                while True:
                    try:
                        more = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    merged.update(dict.fromkeys(more))
                    taken += 1
                self._send(list(merged))
            except Exception as e:  # never let a music server break an import
                logging.warning('LmsScanTrigger: failed to notify LMS: %s', e)
            finally:
                for _ in range(taken):
                    self._queue.task_done()

    def flush_for_test(self) -> None:
        """Drains the queue synchronously. Only for tests -- production never waits."""
        while not self._queue.empty():
            merged = dict.fromkeys(self._queue.get_nowait())
            while not self._queue.empty():
                merged.update(dict.fromkeys(self._queue.get_nowait()))
            self._send(list(merged))

    def _send(self, paths: list) -> None:
        """Send the paths, plus whatever an earlier failed notify left behind, to every host."""
        hosts, api_key = self._endpoint()
        if not hosts:
            return
        with self._state_lock:
            merged = list(dict.fromkeys([*self._carried, *paths]))
            self._carried = {}
            resend_trigger = self._trigger_pending
        delivered = True
        for host in hosts:
            params = {'apiKey': api_key, 'v': '1.16.1', 'c': 'music-manager', 'f': 'json', 'path': merged}
            if self._request(host, params, f'notify LMS of {len(merged)} path(s)'):
                logging.info('Notified LMS on %s of %d path(s)', host, len(merged))
            else:
                delivered = False
        if not delivered:
            self._carry(merged)
            return
        # LMS answers again: a library-wide trigger that failed earlier goes out now rather
        # than waiting for the next round to ask.
        if resend_trigger:
            self.trigger()

    def _carry(self, paths: list) -> None:
        """Keep failed paths for the next notify, bounded; the oldest go first."""
        with self._state_lock:
            carried = dict.fromkeys([*self._carried, *paths])
            overflow = len(carried) - self.MAX_CARRIED_PATHS
            if overflow > 0:
                carried = dict.fromkeys(list(carried)[overflow:])
            self._carried = carried
        if overflow > 0:
            logging.info('LmsScanTrigger: dropped %d carried path(s); the periodic scan covers them', overflow)


lms_scan_trigger = LmsScanTrigger()
