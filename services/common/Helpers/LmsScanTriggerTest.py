import time
import unittest
from unittest.mock import MagicMock, patch

from services.common.Helpers.LmsScanTrigger import LmsScanTrigger


class LmsScanTriggerTest(unittest.TestCase):
    def setUp(self):
        patcher = patch('services.common.Helpers.LmsScanTrigger.ConfigStore')
        self.addCleanup(patcher.stop)
        self.mock_config_cls = patcher.start()
        self.mock_config = MagicMock()
        self.mock_config_cls.return_value = self.mock_config
        # The worker thread is off by default so flush_for_test() is the only thing that
        # sends: a background drain racing the assertions leaks requests into the next test.
        self.worker_patcher = patch.object(LmsScanTrigger, '_ensure_worker')
        self.addCleanup(self.worker_patcher.stop)
        self.worker_patcher.start()
        # The environment is a real fallback now, so a test that means "nothing is
        # configured" has to clear it -- otherwise the developer's own .env decides.
        env = patch.dict(
            'os.environ',
            dict.fromkeys(
                ('LMS_URL', 'LMS_HOSTS', 'MUMA_SERVER_HOSTS', 'MUMA_SERVER_SUBSONIC_API_KEY', 'LMS_SUBSONIC_API_KEY'),
                '',
            ),
        )
        self.addCleanup(env.stop)
        env.start()
        self.trigger = LmsScanTrigger()

    def _configure(self, hosts, api_key, music_folder='/mnt/music'):
        self.mock_config.get.side_effect = lambda key: {
            'lms_hosts': hosts,
            'lms_subsonic_api_key': api_key,
            'music_folder_path': music_folder,
        }.get(key)

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_skips_when_not_configured(self, mock_get):
        self._configure('', '')
        self.trigger.trigger()
        mock_get.assert_not_called()

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_skips_when_api_key_missing(self, mock_get):
        self._configure('lms:5082', '')
        self.trigger.trigger()
        mock_get.assert_not_called()

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_calls_start_scan_for_each_host(self, mock_get):
        self._configure('lms:5082, alpha-lms:5082', 'my-api-key')
        mock_get.return_value = MagicMock(raise_for_status=MagicMock())
        self.trigger.trigger()
        self.assertEqual(mock_get.call_count, 2)
        first_call = mock_get.call_args_list[0]
        self.assertEqual(first_call.args[0], 'http://lms:5082/rest/startScan.view')
        self.assertEqual(first_call.kwargs['params']['apiKey'], 'my-api-key')
        self.assertNotIn('fullScan', first_call.kwargs['params'])

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_everything_already_queued_leaves_in_one_request(self, mock_get):
        """A tagger round notified per folder; LMS logged five scan requests a second.

        Its own collector merges them, so sending them separately bought nothing and cost a
        Wt thread each -- and a starved Wt pool is how this server has 504'd before.
        """
        self._configure('lms:5082', 'my-api-key')
        mock_get.return_value = MagicMock(raise_for_status=MagicMock())

        self.trigger.notify(['/mnt/music/EPs/Label/One'])
        self.trigger.notify(['/mnt/music/EPs/Label/Two'])
        self.trigger.notify(['/mnt/music/EPs/Label/Three'])
        self.trigger.flush_for_test()

        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(
            mock_get.call_args.kwargs['params']['path'],
            ['EPs/Label/One', 'EPs/Label/Two', 'EPs/Label/Three'],
        )

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_the_same_folder_twice_is_one_path(self, mock_get):
        self._configure('lms:5082', 'my-api-key')
        mock_get.return_value = MagicMock(raise_for_status=MagicMock())

        self.trigger.notify(['/mnt/music/EPs/Label/One'])
        self.trigger.notify(['/mnt/music/EPs/Label/One'])
        self.trigger.flush_for_test()

        self.assertEqual(mock_get.call_args.kwargs['params']['path'], ['EPs/Label/One'])

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_falls_back_to_the_environment_when_the_setting_is_empty(self, mock_get):
        """Nothing sets LMS_HOSTS in compose, so the setting is empty on a fresh deployment.

        It was empty on production for as long as the trigger existed, and because the
        send path returned early without logging, a library that never picked up a moved
        folder read as an LMS fault. The radio scheduler meanwhile worked fine off
        MUMA_SERVER_HOSTS -- the same server, a different variable.
        """
        self._configure('', '')
        mock_get.return_value = MagicMock(raise_for_status=MagicMock())
        with patch.dict(
            'os.environ',
            {
                'LMS_URL': '',
                'LMS_HOSTS': '',
                'MUMA_SERVER_HOSTS': 'lms:5082',
                'MUMA_SERVER_SUBSONIC_API_KEY': 'env-key',
            },
        ):
            self.trigger.trigger()
        self.assertEqual(mock_get.call_args.args[0], 'http://lms:5082/rest/startScan.view')
        self.assertEqual(mock_get.call_args.kwargs['params']['apiKey'], 'env-key')

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_the_setting_still_wins_over_the_environment(self, mock_get):
        self._configure('configured:5082', 'configured-key')
        mock_get.return_value = MagicMock(raise_for_status=MagicMock())
        with patch.dict(
            'os.environ', {'MUMA_SERVER_HOSTS': 'from-env:5082', 'MUMA_SERVER_SUBSONIC_API_KEY': 'env-key'}
        ):
            self.trigger.trigger()
        self.assertEqual(mock_get.call_args.args[0], 'http://configured:5082/rest/startScan.view')
        self.assertEqual(mock_get.call_args.kwargs['params']['apiKey'], 'configured-key')

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_says_so_once_when_there_is_nowhere_to_send(self, mock_get):
        """The failure that hid for months was that this path said nothing at all."""
        self._configure('', '')
        cleared = dict.fromkeys(
            ('LMS_URL', 'LMS_HOSTS', 'MUMA_SERVER_HOSTS', 'MUMA_SERVER_SUBSONIC_API_KEY', 'LMS_SUBSONIC_API_KEY'), ''
        )
        with patch.dict('os.environ', cleared), self.assertLogs(level='WARNING') as logs:
            self.trigger.notify(['/mnt/music/EPs/Label/Release'])
            self.trigger.flush_for_test()
            self.trigger.trigger()
        mock_get.assert_not_called()
        self.assertEqual(len([line for line in logs.output if 'not configured' in line]), 1)

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_a_failed_request_is_logged_without_the_api_key(self, mock_get):
        """requests puts the whole URL, apiKey included, into its error; a WARNING is an alert."""
        self._configure('lms:5082', 'my-api-key')
        mock_get.side_effect = RuntimeError(
            '500 Server Error for url: http://lms:5082/rest/startScan.view?apiKey=my-api-key&v=1.16.1'
        )
        with self.assertLogs(level='WARNING') as logs:
            self.trigger.trigger()
            self.trigger.notify(['/mnt/music/EPs/Label/Release'])
            self.trigger.flush_for_test()
        text = '\n'.join(logs.output)
        self.assertNotIn('my-api-key', text)
        self.assertIn('startScan.view?<redacted>', text)

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_a_host_with_its_own_scheme_is_used_as_given(self, mock_get):
        """lms_hosts is free text, and an https URL in it used to become http://https://..."""
        self._configure('https://lms.example.org/, http://plain:5082', 'my-api-key')
        mock_get.return_value = MagicMock(raise_for_status=MagicMock())
        self.trigger.trigger()
        urls = [call.args[0] for call in mock_get.call_args_list]
        self.assertEqual(
            urls,
            ['https://lms.example.org/rest/startScan.view', 'http://plain:5082/rest/startScan.view'],
        )

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_notify_uses_the_same_url_as_trigger(self, mock_get):
        self._configure('https://lms.example.org', 'my-api-key')
        mock_get.return_value = MagicMock(raise_for_status=MagicMock())
        self.trigger.notify(['/mnt/music/EPs/Label/Release'])
        self.trigger.flush_for_test()
        self.assertEqual(mock_get.call_args.args[0], 'https://lms.example.org/rest/startScan.view')

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_full_scan_param_passed_through(self, mock_get):
        self._configure('lms:5082', 'my-api-key')
        mock_get.return_value = MagicMock(raise_for_status=MagicMock())
        self.trigger.trigger(full_scan=True)
        self.assertEqual(mock_get.call_args.kwargs['params']['fullScan'], 'true')

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_does_not_raise_on_request_failure(self, mock_get):
        self._configure('lms:5082', 'my-api-key')
        mock_get.side_effect = Exception('connection refused')
        self.trigger.trigger()  # should not raise

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_notify_sends_each_path_as_a_repeated_parameter(self, mock_get):
        self._configure('lms:5082', 'my-api-key')
        mock_get.return_value = MagicMock(raise_for_status=MagicMock())

        self.trigger.notify(['/mnt/music/EPs/Evolve AU', '/mnt/music/EPs/__TODO/EVAU021E'])
        self.trigger.flush_for_test()

        self.assertEqual(mock_get.call_args.kwargs['params']['path'], ['EPs/Evolve AU', 'EPs/__TODO/EVAU021E'])

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_notify_skips_a_path_outside_the_library(self, mock_get):
        self._configure('lms:5082', 'my-api-key')

        self.trigger.notify(['/var/tmp/somewhere-else'])
        self.trigger.flush_for_test()

        mock_get.assert_not_called()

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_notify_does_not_block_the_caller(self, mock_get):
        # A tagger round produces hundreds of these and the HTTP timeout is ten seconds, so a
        # move must never wait on the music server. This one runs the real worker thread.
        self.worker_patcher.stop()
        self.addCleanup(self.worker_patcher.start)
        self._configure('lms:5082', 'my-api-key')
        mock_get.side_effect = lambda *args, **kwargs: time.sleep(1)

        started = time.monotonic()
        self.trigger.notify(['/mnt/music/EPs/Evolve AU'])
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.5)
        self.trigger._queue.join()  # let the worker finish while requests is still patched

    def test_notify_drops_the_oldest_when_the_queue_is_full(self):
        trigger = LmsScanTrigger(queue_size=2)
        trigger._config = self.mock_config
        self._configure('lms:5082', 'my-api-key')
        trigger._queue.put_nowait(['a'])
        trigger._queue.put_nowait(['b'])

        trigger.notify(['/mnt/music/c'])  # must neither raise nor block

        self.assertEqual(trigger._queue.qsize(), 2)

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_notify_survives_an_lms_that_does_not_answer(self, mock_get):
        self._configure('lms:5082', 'my-api-key')
        mock_get.side_effect = OSError('connection refused')

        self.trigger.notify(['/mnt/music/EPs/Evolve AU'])
        self.trigger.flush_for_test()  # must not raise

    @patch('services.common.Helpers.LmsScanTrigger.requests.get')
    def test_notify_without_configuration_is_a_no_op(self, mock_get):
        self._configure('', '')

        self.trigger.notify(['/mnt/music/EPs/Evolve AU'])
        self.trigger.flush_for_test()

        mock_get.assert_not_called()


if __name__ == '__main__':
    unittest.main()
