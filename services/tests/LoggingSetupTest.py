import contextlib
import io
import logging
import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest

from services.common.Helpers.logging_setup import (
    EventLogHandler,
    is_captured,
    level_name,
    setup_logging,
)

pytestmark = pytest.mark.mock_base('pymysql', 'dbutils')


def make_record(name='music-manager.radio', levelno=logging.INFO, msg='iets gebeurde', exc_info=None):
    return logging.LogRecord(name=name, level=levelno, pathname=__file__, lineno=1, msg=msg, args=(), exc_info=exc_info)


class IsCapturedTest(unittest.TestCase):
    def test_own_logger_captured_from_info(self):
        self.assertTrue(is_captured('music-manager.radio', logging.INFO))
        self.assertTrue(is_captured('downloader', logging.INFO))
        self.assertTrue(is_captured('importer.mover', logging.INFO))

    def test_root_logger_captured_from_info(self):
        # downloader, importer en tagger loggen via de module-API, dus hun
        # records heten 'root'. Zonder deze regel viel al hun INFO weg.
        self.assertTrue(is_captured('root', logging.INFO))

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

    def test_a_failing_service_complains_on_stderr(self):
        # Stil falen maakte deze handler een zwart gat: precies daarom bleven
        # de allowlist- en dedup-fouten onzichtbaar.
        self.service.emit.side_effect = RuntimeError('queue stuk')
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            self.handler.emit(make_record())

        self.assertIn('queue stuk', stderr.getvalue())


class SetupLoggingTest(unittest.TestCase):
    def setUp(self):
        # Save current root logger handlers so we can restore them
        self.saved_handlers = logging.getLogger().handlers[:]
        # Reset the _sink_registered flag for each test
        import services.common.Helpers.logging_setup as logging_setup_module

        logging_setup_module._sink_registered = False

    def tearDown(self):
        # Restore root logger handlers to their original state
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        for handler in self.saved_handlers:
            root.addHandler(handler)
        # Reset the flag again
        import services.common.Helpers.logging_setup as logging_setup_module

        logging_setup_module._sink_registered = False

    @patch('services.common.Helpers.logging_setup.NtfySink')
    @patch('services.common.Helpers.logging_setup.event_service')
    def test_calling_setup_logging_twice_registers_sink_only_once(self, mock_event_service, mock_ntfy_sink):
        setup_logging('music-manager')
        setup_logging('music-manager')

        self.assertEqual(mock_event_service.add_sink.call_count, 1)

    @patch('services.common.Helpers.logging_setup.NtfySink')
    @patch('services.common.Helpers.logging_setup.event_service')
    def test_setup_logging_leaves_one_event_handler_and_stream_handler(self, mock_event_service, mock_ntfy_sink):
        setup_logging('music-manager')

        root = logging.getLogger()
        event_handlers = [h for h in root.handlers if isinstance(h, EventLogHandler)]
        stream_handlers = [
            h for h in root.handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, EventLogHandler)
        ]

        self.assertEqual(len(event_handlers), 1)
        self.assertEqual(len(stream_handlers), 1)

    @patch('services.common.Helpers.logging_setup.NtfySink')
    @patch('services.common.Helpers.logging_setup.event_service')
    def test_calling_setup_logging_twice_leaves_one_event_handler(self, mock_event_service, mock_ntfy_sink):
        setup_logging('music-manager')
        setup_logging('music-manager')

        root = logging.getLogger()
        event_handlers = [h for h in root.handlers if isinstance(h, EventLogHandler)]

        self.assertEqual(len(event_handlers), 1)
