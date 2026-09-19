"""Coverage for services/tagger/announce.py: the three things a worker does after tagging."""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SOURCE = Path(__file__).resolve().parent / 'announce.py'


def load_module():
    # mock_base replaces the helpers this imports; load the real source under its own name
    # and patch what it reaches for, the way ProcessedFilesHelperTest does.
    spec = importlib.util.spec_from_file_location('_real_announce', _SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AnnounceTest(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / 'Soundcloud' / 'MOTZ' / 'a.mp3'
        self.file.parent.mkdir(parents=True)
        self.file.write_bytes(b'x')
        os.utime(self.file, (1782688928.32, 1782688928.32))
        self.helper = MagicMock()
        self.trigger = MagicMock()
        self.requests = MagicMock()
        for target, value in (
            ('ProcessedFilesHelper', MagicMock(return_value=self.helper)),
            ('lms_scan_trigger', self.trigger),
            ('requests', self.requests),
        ):
            p = patch.object(self.module, target, value)
            p.start()
            self.addCleanup(p.stop)
        # conftest seeds API_KEY; it wins over MUMA_API_KEY, as in api_key.py.
        self.env = patch.dict(
            os.environ, {'AUTH_SERVICE_URL': 'http://music-manager:8000', 'API_KEY': 'k', 'MUMA_API_KEY': ''}
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_records_the_file_with_the_mtime_after_the_tag_pass(self):
        self.module.announce(self.file)
        self.helper.mark_processed.assert_called_once_with(str(self.file), 1782688928.32)

    def test_tells_lms_about_the_folder_not_the_file(self):
        self.module.announce(self.file)
        self.trigger.notify.assert_called_once_with([str(self.file.parent)])

    def test_asks_the_scanner_with_the_system_key(self):
        self.module.announce(self.file)
        self.requests.post.assert_called_once_with(
            'http://music-manager:8000/api/scanner/scan/file',
            params={'path': str(self.file)},
            headers={'x-api-key': 'k'},
            timeout=self.module.SCAN_TIMEOUT_SECONDS,
        )

    def test_the_api_url_setting_wins_over_the_auth_service_fallback(self):
        with patch.dict(os.environ, {'MUMA_API_URL': 'http://muma:8000/'}):
            self.module.announce(self.file)
        self.assertEqual(self.requests.post.call_args.args[0], 'http://muma:8000/api/scanner/scan/file')

    def test_without_an_api_base_or_key_the_scan_is_left_to_the_hourly_round(self):
        with patch.dict(os.environ, {'AUTH_SERVICE_URL': '', 'MUMA_API_URL': ''}), self.assertLogs(level='WARNING'):
            self.assertFalse(self.module.request_scan(str(self.file)))
        self.requests.post.assert_not_called()

    def test_nothing_here_can_fail_the_download(self):
        self.helper.mark_processed.side_effect = RuntimeError('db')
        self.trigger.notify.side_effect = RuntimeError('lms')
        self.requests.post.side_effect = self.module.requests.RequestException('api')
        self.module.requests.RequestException = Exception
        with self.assertLogs(level='WARNING'):
            self.module.announce(self.file)

    def test_a_file_that_vanished_is_still_announced_to_lms(self):
        self.file.unlink()
        with self.assertLogs(level='WARNING'):
            self.module.announce(self.file)
        self.trigger.notify.assert_called_once()
