import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import pytest

from services.common.Helpers.EventService import Event, EventQueue, EventService
from services.common.Helpers.ntfy_sink import NtfySink

pytestmark = pytest.mark.mock_base('pymysql', 'dbutils')


def make_event(level='INFO', title='t', source='downloader'):
    return Event(level=level, title=title, message='m', source=source, logger=None, context=None, push=False)


class EventQueueTest(unittest.TestCase):
    def test_put_and_get_round_trip(self):
        q = EventQueue(maxsize=2)
        event = make_event()
        self.assertTrue(q.put(event))
        self.assertIs(q.get(timeout=0.01), event)

    def test_get_returns_none_when_empty(self):
        self.assertIsNone(EventQueue(maxsize=2).get(timeout=0.01))

    def test_overflow_drops_oldest_info(self):
        q = EventQueue(maxsize=2)
        old_info = make_event(title='old-info')
        warning = make_event(level='WARNING', title='warn')
        q.put(old_info)
        q.put(warning)

        newcomer = make_event(title='new-info')
        self.assertTrue(q.put(newcomer))

        remaining = [q.get(timeout=0.01), q.get(timeout=0.01)]
        self.assertEqual([e.title for e in remaining], ['warn', 'new-info'])

    def test_overflow_rejects_when_only_warnings_queued(self):
        q = EventQueue(maxsize=2)
        q.put(make_event(level='ERROR', title='a'))
        q.put(make_event(level='CRITICAL', title='b'))

        self.assertFalse(q.put(make_event(level='ERROR', title='c')))
        self.assertEqual(len(q), 2)


class EventServiceWriteTest(unittest.TestCase):
    def setUp(self):
        self.service = EventService(sinks=[])

    @patch('services.common.Helpers.EventService.DatabaseConnector')
    def test_write_inserts_row(self, mock_connector):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connector.return_value.connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        event = Event(
            level='ERROR',
            title='kapot',
            message='details',
            source='importer',
            logger='importer.mover',
            context={'track': 'x'},
            push=False,
        )
        self.assertTrue(self.service._write(event))

        sql, params = mock_cursor.execute.call_args[0]
        self.assertIn('INSERT INTO events', sql)
        self.assertEqual(params[0], 'ERROR')
        self.assertEqual(params[1], 'importer')
        self.assertEqual(params[2], 'importer.mover')
        self.assertEqual(params[3], 'kapot')
        self.assertEqual(params[5], '{"track": "x"}')
        mock_conn.commit.assert_called_once()

    @patch('services.common.Helpers.EventService.DatabaseConnector')
    def test_write_retries_then_gives_up(self, mock_connector):
        mock_connector.return_value.connect.side_effect = RuntimeError('db weg')

        with patch.object(self.service._retry_pause, 'wait', return_value=False) as mock_pause:
            self.assertFalse(self.service._write(make_event()))

        self.assertEqual(mock_connector.return_value.connect.call_count, 4)
        self.assertEqual([c[0][0] for c in mock_pause.call_args_list], [1, 4, 16])

    @patch('services.common.Helpers.EventService.DatabaseConnector')
    def test_a_retry_never_calls_the_process_wide_sleep(self, mock_connector):
        """Bug report 099: loop tests patch `time.sleep` with a finite side_effect list.

        The writer thread used to pause between retries with that same function, so a retry
        landing inside such a test consumed its items and the test died on StopIteration.
        """
        mock_connector.return_value.connect.side_effect = RuntimeError('db weg')

        with (
            patch.object(self.service._retry_pause, 'wait', return_value=False),
            patch('time.sleep', side_effect=AssertionError('the writer used time.sleep')) as mock_sleep,
        ):
            self.assertFalse(self.service._write(make_event()))

        mock_sleep.assert_not_called()

    def test_dispatch_survives_a_failing_sink(self):
        angry = MagicMock()
        angry.handle.side_effect = RuntimeError('ntfy plat')
        calm = MagicMock()
        service = EventService(sinks=[angry, calm])

        service._dispatch(make_event())

        calm.handle.assert_called_once()

    @patch('services.common.Helpers.EventService.DatabaseConnector')
    def test_record_now_writes_the_row_before_it_returns_and_skips_the_sinks(self, mock_connector):
        """A one-shot command exits right after; a daemon thread would die with its row."""
        sink = MagicMock()
        service = EventService(sinks=[sink])
        mock_cursor = MagicMock()
        mock_connector.return_value.connect.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        self.assertTrue(service.record_now(make_event(level='WARNING', source='music-mirror')))

        params = mock_cursor.execute.call_args[0][1]
        self.assertEqual(params[:2], ('WARNING', 'music-mirror'))
        sink.handle.assert_not_called()
        self.assertFalse(service.is_alive())

    def test_record_now_rejects_unknown_level(self):
        with self.assertRaises(ValueError):
            self.service.record_now(make_event(level='TRACE'))

    def test_emit_rejects_unknown_level(self):
        with self.assertRaises(ValueError):
            self.service.emit('TRACE', 'titel', 'bericht', 'downloader')


class PushDoesNotWaitOnTheDatabaseTest(unittest.TestCase):
    """During a MariaDB outage the rows are late, the pushes are not.

    Before the split one worker wrote each event (with 1 + 4 + 16 s of retries) before
    handing it to the sinks, so a CRITICAL queued behind N events reached the phone
    N x 21 s late.
    """

    def setUp(self):
        # Every database write blocks on this until the test ends: an outage that never heals.
        self.outage = threading.Event()
        self.addCleanup(self.outage.set)
        connector = patch('services.common.Helpers.EventService.DatabaseConnector')
        self.mock_connector = connector.start()
        self.addCleanup(connector.stop)

        def connect():
            self.outage.wait(5)
            raise RuntimeError('db weg')

        self.mock_connector.return_value.connect.side_effect = connect

    def _wait_for(self, predicate, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            threading.Event().wait(0.01)
        return False

    def test_a_critical_reaches_the_sink_while_the_database_write_is_failing(self):
        sink = MagicMock()
        service = EventService(sinks=[sink])

        for index in range(5):
            service.emit('WARNING', f'db flapping {index}', 'm', 'music-manager', logger='music-manager.db')
        service.emit('CRITICAL', 'library gone', 'm', 'music-manager')

        self.assertTrue(
            self._wait_for(lambda: any(c.args[0].level == 'CRITICAL' for c in sink.handle.call_args_list)),
            'the CRITICAL push waited on the failing database write',
        )
        self.assertTrue(service.is_alive())
        # The writer is still stuck on the very first row, so nothing was written yet.
        self.assertEqual(self.mock_connector.return_value.connect.call_count, 1)

    @patch('services.common.Helpers.ntfy_sink.requests')
    def test_the_dedupe_brake_still_holds_back_a_repeat_push(self, mock_requests):
        config = MagicMock()
        values = {
            'notify_url': 'https://ntfy.example.nl',
            'notify_topic': 'music-management',
            'notify_topic_alerts': 'music-management-alerts',
        }
        config.get.side_effect = values.get
        service = EventService(sinks=[NtfySink(config=config)])

        service.emit('CRITICAL', 'still cooling down for 240s', 'm', 'music-manager', logger='music-manager.db')
        service.emit('CRITICAL', 'still cooling down for 230s', 'm', 'music-manager', logger='music-manager.db')
        service.emit('ERROR', 'marker', 'm', 'music-manager', logger='music-manager.other')

        self.assertTrue(self._wait_for(lambda: mock_requests.post.call_count >= 2))
        threading.Event().wait(0.05)
        titles = [c.kwargs['headers']['Title'] for c in mock_requests.post.call_args_list]
        self.assertEqual(titles, ['still cooling down for 240s', 'marker'])

    def test_every_event_is_still_handed_to_the_writer(self):
        service = EventService(sinks=[])
        with patch.object(service, '_dispatch'):
            for index in range(3):
                service._handle(make_event(title=f'e{index}'))
        self.assertEqual(len(service._write_queue), 3)

    def test_is_alive_needs_both_threads(self):
        service = EventService(sinks=[])
        self.assertFalse(service.is_alive())
        service.emit('INFO', 't', 'm', 'downloader')
        self.assertTrue(service.is_alive())


if __name__ == '__main__':
    unittest.main()
