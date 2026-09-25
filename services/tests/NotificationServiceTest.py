import unittest
from unittest.mock import patch

import pytest

from services.common.Helpers.NotificationService import NotificationService

pytestmark = pytest.mark.mock_base('pymysql', 'dbutils')


class NotificationServiceTest(unittest.TestCase):
    @patch('services.common.Helpers.NotificationService.event_service')
    def test_notify_emits_a_pushed_info_event(self, mock_service):
        mock_service.emit.return_value = True

        result = NotificationService(source='downloader').notify('nummer klaar', title='SoundCloud')

        self.assertTrue(result)
        kwargs = mock_service.emit.call_args[1]
        self.assertEqual(kwargs['level'], 'INFO')
        self.assertEqual(kwargs['title'], 'SoundCloud')
        self.assertEqual(kwargs['message'], 'nummer klaar')
        self.assertEqual(kwargs['source'], 'downloader')
        self.assertTrue(kwargs['push'])

    @patch('services.common.Helpers.NotificationService.event_service')
    def test_default_title_is_kept(self, mock_service):
        NotificationService().notify('zonder titel')

        self.assertEqual(mock_service.emit.call_args[1]['title'], 'Music Management')
