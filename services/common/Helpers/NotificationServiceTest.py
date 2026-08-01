import importlib.util
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# mock_base replaces this module with a MagicMock so no test can fire off a real ntfy
# request. Load the real source under a throwaway name instead.
_SOURCE = Path(__file__).resolve().parent / 'NotificationService.py'


def load_module(config):
    spec = importlib.util.spec_from_file_location('_real_notification_service', _SOURCE)
    module = importlib.util.module_from_spec(spec)
    with patch('services.common.config_store.ConfigStore', return_value=config):
        spec.loader.exec_module(module)
    return module


def make_config(values):
    config = MagicMock()
    config.get.side_effect = lambda key: values[key]
    return config


class ConfigurationTest(unittest.TestCase):

    def test_the_url_and_topic_are_read_from_the_config_store(self):
        module = load_module(make_config({'notify_url': 'https://ntfy.test/', 'notify_topic': 'music'}))
        service = module.NotificationService()
        self.assertEqual(service.notify_url, 'https://ntfy.test/')
        self.assertEqual(service.notify_topic, 'music')

    def test_the_service_follows_later_config_changes(self):
        config = make_config({'notify_url': 'https://ntfy.test', 'notify_topic': 'music'})
        module = load_module(config)
        service = module.NotificationService()
        subscribed = {call.args[0]: call.args[1] for call in config.subscribe.call_args_list}
        subscribed['notify_topic']('other-topic')
        self.assertEqual(service.notify_topic, 'other-topic')

    def test_missing_configuration_disables_notifications_instead_of_crashing(self):
        config = MagicMock()
        config.get.side_effect = KeyError('notify_url')
        module = load_module(config)
        service = module.NotificationService()
        self.assertIsNone(service.notify_url)
        self.assertIsNone(service.notify_topic)


class NotifyTest(unittest.TestCase):

    def setUp(self):
        self.module = load_module(make_config({'notify_url': 'https://ntfy.test/', 'notify_topic': 'music'}))
        self.service = self.module.NotificationService()

    def test_a_notification_is_posted_to_the_configured_topic(self):
        with patch.object(self.module, 'requests') as http:
            self.assertTrue(self.service.notify('hello', title='Import Complete'))
        self.assertEqual(http.post.call_args.args[0], 'https://ntfy.test/music')
        self.assertEqual(http.post.call_args.kwargs['data'], b'hello')
        self.assertEqual(http.post.call_args.kwargs['headers'], {'Title': 'Import Complete'})

    def test_the_default_title_is_used_when_none_is_given(self):
        with patch.object(self.module, 'requests') as http:
            self.service.notify('hello')
        self.assertEqual(http.post.call_args.kwargs['headers'], {'Title': 'Music Management'})

    def test_an_unconfigured_service_reports_failure_without_calling_out(self):
        self.service.notify_topic = None
        with patch.object(self.module, 'requests') as http:
            self.assertFalse(self.service.notify('hello'))
        http.post.assert_not_called()

    def test_an_error_response_is_reported_as_a_failure(self):
        with patch.object(self.module, 'requests') as http:
            http.post.return_value.raise_for_status.side_effect = RuntimeError('503')
            self.assertFalse(self.service.notify('hello'))

    def test_a_transport_error_is_reported_as_a_failure(self):
        with patch.object(self.module, 'requests') as http:
            http.post.side_effect = RuntimeError('network down')
            self.assertFalse(self.service.notify('hello'))


if __name__ == '__main__':
    unittest.main()
