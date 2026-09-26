"""Pytest plugin: the process-wide event service never writes to a database in unit tests.

`services.common.Helpers.EventService.event_service` is a singleton with a writer thread.
Anything a test logs at INFO or higher under a captured logger -- once some test has run
`setup_logging`, or code under test calls `NotificationService` -- is queued for that thread,
which then connects with the real `DatabaseConnector`. In CI that raises "Database connection
parameters are not fully configured" and the writer retries for 21 seconds, pausing while
later tests run; on a developer machine with a `.env` it would write test events into a
real database. Bug report 099 traced three flaky loop tests to exactly that writer.

Before every test, every event service the process can reach is switched to an in-memory
writer: the singleton of the `EventService` module currently in `sys.modules`, and the
service behind each `EventLogHandler` on the root logger. The latter matters because of
the mock_base worlds (bug report 085): a module declaring stubs imports its own copy of the
project modules, so the handler `setup_logging` installed may belong to a different copy
than the one importable right now. The switch is per instance and permanent -- a queued
event written after its test ended must not reach the database either -- and a test that
builds its own `EventService()` (EventServiceTest) keeps the real `_write` it is testing.

Written events land in `RECORDED_EVENTS`, emptied before each test and exposed through the
`recorded_events` fixture. They are recorded by the writer thread, so a test that asserts
on them has to wait for the thread to catch up.
"""

from __future__ import annotations

import importlib
import logging
import threading

import pytest

EVENT_SERVICE_MODULE = 'services.common.Helpers.EventService'

RECORDED_EVENTS: list = []
_recorded_lock = threading.Lock()


def _record(event) -> bool:
    """The in-memory stand-in for EventService._write: keep the event, report success."""
    with _recorded_lock:
        RECORDED_EVENTS.append(event)
    return True


def _reachable_services() -> list:
    """Every event service a log line or a direct emit in this test could end up in."""
    services = []
    try:
        module = importlib.import_module(EVENT_SERVICE_MODULE)
    except Exception:  # pylint: disable=broad-except  # a world whose stubs cannot import it has none
        module = None
    if module is not None and hasattr(module, 'event_service'):
        services.append(module.event_service)
    for handler in logging.getLogger().handlers:
        service = getattr(handler, '_service', None)
        if service is not None and hasattr(service, '_write'):
            services.append(service)
    return services


def keep_in_memory(service) -> None:
    """Replace `service`'s database writer with the in-memory recorder, once."""
    if getattr(service, '_in_memory_events', False):
        return
    service._write = _record  # pylint: disable=protected-access
    service._in_memory_events = True  # pylint: disable=protected-access


@pytest.fixture(autouse=True)
def _event_log_stays_in_memory():
    """Autouse: no event written during a unit test reaches a database."""
    for service in _reachable_services():
        keep_in_memory(service)
    with _recorded_lock:
        RECORDED_EVENTS.clear()
    yield


@pytest.fixture
def recorded_events() -> list:
    """The events the process-wide event service has written so far in this test."""
    return RECORDED_EVENTS
