import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql'):
    sys.modules.setdefault(_mod_name, MagicMock())

# Ensure real requests is available (ArtistFixerTest creates a stub that we need to override)
if 'requests' in sys.modules and not hasattr(sys.modules['requests'], 'post'):
    del sys.modules['requests']
import requests

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


def make_event(level='INFO', title='t', push=False, source='downloader'):
    return Event(level=level, title=title, message='bericht', source=source, push=push)


class NtfySinkTest(unittest.TestCase):

    def setUp(self):
        self.clock = FakeClock()
        self.sink = NtfySink(config=fake_config(), clock=self.clock)

    @patch('services.common.Helpers.ntfy_sink.requests.post')
    def test_warning_goes_to_alerts_topic(self, mock_post):
        self.sink.handle(make_event(level='WARNING'))

        url = mock_post.call_args[0][0]
        headers = mock_post.call_args[1]['headers']
        self.assertEqual(url, 'https://ntfy.example.nl/music-management-alerts')
        self.assertEqual(headers['Priority'], 'high')
        self.assertEqual(headers['Tags'], 'warning')

    @patch('services.common.Helpers.ntfy_sink.requests.post')
    def test_critical_is_urgent(self, mock_post):
        self.sink.handle(make_event(level='CRITICAL'))

        headers = mock_post.call_args[1]['headers']
        self.assertEqual(headers['Priority'], 'urgent')
        self.assertEqual(headers['Tags'], 'sos')

    @patch('services.common.Helpers.ntfy_sink.requests.post')
    def test_info_without_push_goes_nowhere(self, mock_post):
        self.sink.handle(make_event(level='INFO', push=False))

        mock_post.assert_not_called()

    @patch('services.common.Helpers.ntfy_sink.requests.post')
    def test_info_with_push_goes_to_milestone_topic(self, mock_post):
        self.sink.handle(make_event(level='INFO', push=True))

        self.assertEqual(mock_post.call_args[0][0], 'https://ntfy.example.nl/music-management')

    @patch('services.common.Helpers.ntfy_sink.requests.post')
    def test_duplicate_within_window_is_suppressed(self, mock_post):
        self.sink.handle(make_event(level='ERROR', title='zelfde'))
        self.clock.now = 299.0
        self.sink.handle(make_event(level='ERROR', title='zelfde'))

        self.assertEqual(mock_post.call_count, 1)

    @patch('services.common.Helpers.ntfy_sink.requests.post')
    def test_duplicate_after_window_is_sent_again(self, mock_post):
        self.sink.handle(make_event(level='ERROR', title='zelfde'))
        self.clock.now = 301.0
        self.sink.handle(make_event(level='ERROR', title='zelfde'))

        self.assertEqual(mock_post.call_count, 2)

    @patch('services.common.Helpers.ntfy_sink.requests.post')
    def test_different_source_is_not_a_duplicate(self, mock_post):
        self.sink.handle(make_event(level='ERROR', title='zelfde', source='downloader'))
        self.sink.handle(make_event(level='ERROR', title='zelfde', source='importer'))

        self.assertEqual(mock_post.call_count, 2)

    @patch('services.common.Helpers.ntfy_sink.requests.post')
    def test_missing_configuration_sends_nothing(self, mock_post):
        sink = NtfySink(config=fake_config({'notify_url': ''}), clock=self.clock)

        sink.handle(make_event(level='ERROR'))

        mock_post.assert_not_called()
