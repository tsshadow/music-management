import logging
import sys
import unittest
from unittest.mock import MagicMock

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql'):
    sys.modules.setdefault(_mod_name, MagicMock())

from services.common.Helpers.logging_setup import (
    EventLogHandler, is_captured, level_name,
)


def make_record(name='music-manager.radio', levelno=logging.INFO, msg='iets gebeurde',
                exc_info=None):
    return logging.LogRecord(name=name, level=levelno, pathname=__file__, lineno=1,
                             msg=msg, args=(), exc_info=exc_info)


class IsCapturedTest(unittest.TestCase):

    def test_own_logger_captured_from_info(self):
        self.assertTrue(is_captured('music-manager.radio', logging.INFO))
        self.assertTrue(is_captured('downloader', logging.INFO))
        self.assertTrue(is_captured('importer.mover', logging.INFO))

    def test_own_logger_not_captured_below_info(self):
        self.assertFalse(is_captured('music-manager.radio', logging.DEBUG))

    def test_prefix_match_is_on_a_boundary(self):
        self.assertFalse(is_captured('scannerly', logging.INFO))

    def test_third_party_not_captured_at_info(self):
        self.assertFalse(is_captured('uvicorn.access', logging.INFO))
        self.assertFalse(is_captured('urllib3.connectionpool', logging.INFO))

    def test_third_party_captured_from_warning(self):
        self.assertTrue(is_captured('uvicorn.access', logging.ERROR))


class LevelNameTest(unittest.TestCase):

    def test_maps_python_levels_to_event_levels(self):
        self.assertEqual(level_name(logging.INFO), 'INFO')
        self.assertEqual(level_name(logging.WARNING), 'WARNING')
        self.assertEqual(level_name(logging.ERROR), 'ERROR')
        self.assertEqual(level_name(logging.CRITICAL), 'CRITICAL')

    def test_unknown_level_falls_back_to_nearest_below(self):
        self.assertEqual(level_name(logging.ERROR + 1), 'ERROR')


class EventLogHandlerTest(unittest.TestCase):

    def setUp(self):
        self.service = MagicMock()
        self.handler = EventLogHandler(source='music-manager', service=self.service)

    def test_captured_record_becomes_an_event(self):
        self.handler.emit(make_record(msg='radio kanaal bijgevuld'))

        kwargs = self.service.emit.call_args[1]
        self.assertEqual(kwargs['level'], 'INFO')
        self.assertEqual(kwargs['source'], 'music-manager')
        self.assertEqual(kwargs['logger'], 'music-manager.radio')
        self.assertIn('radio kanaal bijgevuld', kwargs['title'])
        self.assertFalse(kwargs['push'])

    def test_filtered_record_is_ignored(self):
        self.handler.emit(make_record(name='uvicorn.access'))

        self.service.emit.assert_not_called()

    def test_title_is_first_line_only_and_message_keeps_the_rest(self):
        self.handler.emit(make_record(msg='eerste regel\ntweede regel'))

        kwargs = self.service.emit.call_args[1]
        self.assertNotIn('tweede regel', kwargs['title'])
        self.assertIn('tweede regel', kwargs['message'])

    def test_exception_lands_in_the_message(self):
        try:
            raise ValueError('stuk')
        except ValueError:
            record = make_record(levelno=logging.ERROR, msg='mislukt', exc_info=sys.exc_info())

        self.handler.emit(record)

        self.assertIn('ValueError: stuk', self.service.emit.call_args[1]['message'])

    def test_reentrancy_guard_blocks_a_loop(self):
        def emit_again(**_kwargs):
            self.handler.emit(make_record(msg='van binnenuit'))

        self.service.emit.side_effect = emit_again

        self.handler.emit(make_record(msg='van buitenaf'))

        self.assertEqual(self.service.emit.call_count, 1)

    def test_a_failing_service_does_not_raise(self):
        self.service.emit.side_effect = RuntimeError('queue stuk')

        self.handler.emit(make_record())  # mag niet opgooien
