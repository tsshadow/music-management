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
        self.trigger = LmsScanTrigger()

    def _configure(self, hosts, api_key):
        self.mock_config.get.side_effect = lambda key: {'lms_hosts': hosts, 'lms_subsonic_api_key': api_key}.get(key)

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


if __name__ == '__main__':
    unittest.main()
