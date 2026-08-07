import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql'):
    sys.modules.setdefault(_mod_name, MagicMock())

from services.common.Helpers.EventService import Event, EventQueue, EventService


def make_event(level='INFO', title='t', source='downloader'):
    return Event(level=level, title=title, message='m', source=source,
                 logger=None, context=None, push=False)


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

        event = Event(level='ERROR', title='kapot', message='details',
                      source='importer', logger='importer.mover',
                      context={'track': 'x'}, push=False)
        self.assertTrue(self.service._write(event))

        sql, params = mock_cursor.execute.call_args[0]
        self.assertIn('INSERT INTO events', sql)
        self.assertEqual(params[0], 'ERROR')
        self.assertEqual(params[1], 'importer')
        self.assertEqual(params[2], 'importer.mover')
        self.assertEqual(params[3], 'kapot')
        self.assertEqual(params[5], '{"track": "x"}')
        mock_conn.commit.assert_called_once()

    @patch('services.common.Helpers.EventService.time.sleep')
    @patch('services.common.Helpers.EventService.DatabaseConnector')
    def test_write_retries_then_gives_up(self, mock_connector, mock_sleep):
        mock_connector.return_value.connect.side_effect = RuntimeError('db weg')

        self.assertFalse(self.service._write(make_event()))

        self.assertEqual(mock_connector.return_value.connect.call_count, 4)
        self.assertEqual([c[0][0] for c in mock_sleep.call_args_list], [1, 4, 16])

    def test_dispatch_survives_a_failing_sink(self):
        angry = MagicMock()
        angry.handle.side_effect = RuntimeError('ntfy plat')
        calm = MagicMock()
        service = EventService(sinks=[angry, calm])

        service._dispatch(make_event())

        calm.handle.assert_called_once()

    def test_emit_rejects_unknown_level(self):
        with self.assertRaises(ValueError):
            self.service.emit('TRACE', 'titel', 'bericht', 'downloader')
