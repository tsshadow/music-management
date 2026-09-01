import logging

import requests

from services.common.config_store import ConfigStore


class LmsScanTrigger:
    """
    Best-effort trigger for an immediate LMS (Logitech Media Server) library scan,
    via the Subsonic `startScan.view` endpoint.

    This is meant to be called once per download/import/tag run (not once per file):
    LMS's incremental scan already only reprocesses new/changed files (same mtime/size
    check as its periodic schedule), so triggering it after a batch is cheap, and lets
    LMS's own background schedule be turned down (e.g. hourly -> daily) without losing
    freshness.
    """

    def __init__(self):
        self._config = ConfigStore()

    def trigger(self, full_scan: bool = False) -> None:
        hosts = self._config.get('lms_hosts')
        api_key = self._config.get('lms_subsonic_api_key')
        if not hosts or not api_key:
            logging.debug('LmsScanTrigger: lms_hosts or lms_subsonic_api_key not configured, skipping scan trigger.')
            return
        for host in hosts.split(','):
            host = host.strip()
            if not host:
                continue
            self._trigger_host(host, api_key, full_scan)

    def _trigger_host(self, host: str, api_key: str, full_scan: bool) -> None:
        url = f'http://{host}/rest/startScan.view'
        params = {'apiKey': api_key, 'v': '1.16.1', 'c': 'music-manager', 'f': 'json'}
        if full_scan:
            params['fullScan'] = 'true'
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            logging.info('Triggered LMS scan on %s (fullScan=%s)', host, full_scan)
        except Exception as e:
            logging.warning('Failed to trigger LMS scan on %s: %s', host, e)


lms_scan_trigger = LmsScanTrigger()
