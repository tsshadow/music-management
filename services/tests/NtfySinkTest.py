import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql'):
    sys.modules.setdefault(_mod_name, MagicMock())

from services.common.Helpers.EventService import Event
from services.common.Helpers.ntfy_sink import NtfySink


class FakeClock:

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def fake_config(values=None):
    defaults = {
        'notify_url': 'https://ntfy.example.nl',
        'notify_topic': 'music-management',
        'notify_topic_alerts': 'music-management-alerts',
    }
    defaults.update(values or {})
    config = MagicMock()
    config.get.side_effect = lambda key: defaults.get(key)
    return config


def make_event(level='INFO', title='t', push=False, source='downloader', logger=None):
    return Event(level=level, title=title, message='bericht', source=source, push=push,
                 logger=logger)


class NtfySinkTest(unittest.TestCase):

    def setUp(self):
        self.clock = FakeClock()
        self.sink = NtfySink(config=fake_config(), clock=self.clock)

    @patch('services.common.Helpers.ntfy_sink.requests')
    def test_warning_goes_to_alerts_topic(self, mock_requests):
        self.sink.handle(make_event(level='WARNING'))

        url = mock_requests.post.call_args[0][0]
        headers = mock_requests.post.call_args[1]['headers']
        self.assertEqual(url, 'https://ntfy.example.nl/music-management-alerts')
        self.assertEqual(headers['Priority'], 'high')
        self.assertEqual(headers['Tags'], 'warning')

    @patch('services.common.Helpers.ntfy_sink.requests')
    def test_critical_is_urgent(self, mock_requests):
        self.sink.handle(make_event(level='CRITICAL'))

        headers = mock_requests.post.call_args[1]['headers']
        self.assertEqual(headers['Priority'], 'urgent')
        self.assertEqual(headers['Tags'], 'sos')

    @patch('services.common.Helpers.ntfy_sink.requests')
    def test_info_without_push_goes_nowhere(self, mock_requests):
        self.sink.handle(make_event(level='INFO', push=False))

        mock_requests.post.assert_not_called()

    @patch('services.common.Helpers.ntfy_sink.requests')
    def test_info_with_push_goes_to_milestone_topic(self, mock_requests):
        self.sink.handle(make_event(level='INFO', push=True))

        self.assertEqual(mock_requests.post.call_args[0][0], 'https://ntfy.example.nl/music-management')

    @patch('services.common.Helpers.ntfy_sink.requests')
    def test_duplicate_within_window_is_suppressed(self, mock_requests):
        self.sink.handle(make_event(level='ERROR', title='zelfde'))
        self.clock.now = 299.0
        self.sink.handle(make_event(level='ERROR', title='zelfde'))

        self.assertEqual(mock_requests.post.call_count, 1)

    @patch('services.common.Helpers.ntfy_sink.requests')
    def test_duplicate_after_window_is_sent_again(self, mock_requests):
        self.sink.handle(make_event(level='ERROR', title='zelfde'))
        self.clock.now = 301.0
        self.sink.handle(make_event(level='ERROR', title='zelfde'))

        self.assertEqual(mock_requests.post.call_count, 2)

    @patch('services.common.Helpers.ntfy_sink.requests')
    def test_different_source_is_not_a_duplicate(self, mock_requests):
        self.sink.handle(make_event(level='ERROR', title='zelfde', source='downloader'))
        self.sink.handle(make_event(level='ERROR', title='zelfde', source='importer'))

        self.assertEqual(mock_requests.post.call_count, 2)

    @patch('services.common.Helpers.ntfy_sink.requests')
    def test_error_is_high_with_a_siren(self, mock_requests):
        self.sink.handle(make_event(level='ERROR'))

        headers = mock_requests.post.call_args[1]['headers']
        self.assertEqual(headers['Priority'], 'high')
        self.assertEqual(headers['Tags'], 'rotating_light')

    @patch('services.common.Helpers.ntfy_sink.requests')
    def test_same_logger_with_a_changing_countdown_pushes_once(self, mock_requests):
        # sweep.py waarschuwt 'nog 240s afkoelen' en even later 'nog 180s'. Dat
        # is dezelfde melding met een andere titel; op de telefoon hoort dat
        # eenmaal aan te komen, niet elke sweep opnieuw.
        self.sink.handle(make_event(level='WARNING', logger='downloader.sweep',
                                    title='soundcloud koelt nog 240s af'))
        self.clock.now = 60.0
        self.sink.handle(make_event(level='WARNING', logger='downloader.sweep',
                                    title='soundcloud koelt nog 180s af'))

        self.assertEqual(mock_requests.post.call_count, 1)

    @patch('services.common.Helpers.ntfy_sink.requests')
    def test_same_title_from_different_loggers_pushes_twice(self, mock_requests):
        self.sink.handle(make_event(level='ERROR', logger='downloader.sweep', title='zelfde'))
        self.sink.handle(make_event(level='ERROR', logger='downloader.queue', title='zelfde'))

        self.assertEqual(mock_requests.post.call_count, 2)

    @patch('services.common.Helpers.ntfy_sink.requests')
    def test_events_without_a_logger_still_dedup_on_title(self, mock_requests):
        self.sink.handle(make_event(level='ERROR', logger=None, title='zelfde'))
        self.clock.now = 60.0
        self.sink.handle(make_event(level='ERROR', logger=None, title='zelfde'))

        self.assertEqual(mock_requests.post.call_count, 1)

    @patch('services.common.Helpers.ntfy_sink.requests')
    def test_missing_configuration_sends_nothing(self, mock_requests):
        sink = NtfySink(config=fake_config({'notify_url': ''}), clock=self.clock)

        sink.handle(make_event(level='ERROR'))

        mock_requests.post.assert_not_called()

    @patch('services.common.Helpers.ntfy_sink.requests')
    def test_post_failure_does_not_propagate(self, mock_requests):
        mock_requests.post.return_value.raise_for_status.side_effect = RuntimeError('503 Service Unavailable')

        # Should not raise; exceptions in POST are swallowed
        self.sink.handle(make_event(level='ERROR'))
