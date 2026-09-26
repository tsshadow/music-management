"""The unit suite's event log stays in memory (bug report 099)."""

import logging
import threading
import time
from unittest.mock import patch

from services.common.Helpers.EventService import EventService, event_service
from services.common.Helpers.logging_setup import EventLogHandler
from services.tests import in_memory_events_plugin as plugin
from services.tests.stop_after import StopAfter


def _wait_for(predicate, timeout=2.0):
    """Poll `predicate` until it holds or `timeout` passes; the writer is a thread."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        threading.Event().wait(0.01)
    return False


def test_the_process_wide_service_never_connects_to_a_database(recorded_events):
    with patch(
        'services.common.Helpers.EventService.DatabaseConnector', side_effect=AssertionError('connected')
    ) as connector:
        event_service.emit('ERROR', 'probe-099', 'm', 'music-manager')
        assert _wait_for(lambda: any(e.title == 'probe-099' for e in recorded_events))
    connector.assert_not_called()


def test_the_service_behind_a_root_handler_is_switched_too():
    """A handler installed from another mock_base world holds a service of its own copy."""
    other = EventService(sinks=[])
    handler = EventLogHandler(source='music-manager', service=other)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        assert other in plugin._reachable_services()
        for service in plugin._reachable_services():
            plugin.keep_in_memory(service)
    finally:
        root.removeHandler(handler)
    assert other._write is plugin._record


def test_a_service_built_by_a_test_keeps_its_real_writer():
    assert EventService(sinks=[])._write.__func__ is EventService._write


def test_stop_after_ends_the_loop_after_exactly_that_many_waits():
    stop = StopAfter(3)
    assert [stop.wait(5), stop.wait(6), stop.wait(7)] == [False, False, True]
    assert stop.wait(8) is True
    assert stop.delays == [5, 6, 7]
