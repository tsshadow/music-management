"""Eén plek waar elke service zijn logging opzet.

Naast de bestaande StreamHandler naar stdout hangt hier een handler die
records doorzet naar de events-stroom. Zonder allowlist stroomt uvicorn's
access-log de tabel in en is het logboek binnen een dag onleesbaar.
"""

from __future__ import annotations

import logging
import sys
import threading

from services.common.Helpers.EventService import event_service
from services.common.Helpers.ntfy_sink import NtfySink

# Namespaces captured from INFO upward; everything else only from WARNING.
# 'root' is here because the worker services (downloader, importer, tagger) log through the
# module API -- logging.info(...) rather than a named logger -- so their records carry
# record.name == 'root'; without it every INFO from those processes was dropped. Which
# service it was stays visible: setup_logging sets the source field per process.
# 'services.music_manager' is here because modules that name their logger after themselves
# (logging.getLogger(__name__): song_version_sync, track_form_sync, release_date_sync, the
# feeds) log as 'services.music_manager.<module>'; their hourly INFO summaries existed only
# in `docker logs` and were lost at every redeploy (bug report 105).
ALLOWED_PREFIXES = ('music-manager', 'downloader', 'importer', 'tagger', 'scanner', 'root', 'services.music_manager')
# Inside an allowed namespace, but chatty per item: kept at the default threshold (WARNING).
# The artist image fetcher logs several INFO lines per artist it looks up.
QUIET_PREFIXES = ('services.music_manager.artist_image_fetcher',)
DEFAULT_THRESHOLD = logging.WARNING
LOG_FORMAT = '%(asctime)s  %(filename)s:%(lineno)s [%(levelname)s] %(message)s'
TITLE_MAX_LENGTH = 255

_LEVEL_NAMES = (
    (logging.CRITICAL, 'CRITICAL'),
    (logging.ERROR, 'ERROR'),
    (logging.WARNING, 'WARNING'),
    (logging.INFO, 'INFO'),
)

_state = threading.local()
_sink_registered = False


def _under(logger_name: str, prefix: str) -> bool:
    """Whether `logger_name` is `prefix` itself or one of its children."""
    return logger_name == prefix or logger_name.startswith(prefix + '.')


def is_captured(logger_name: str, levelno: int) -> bool:
    """Whether a record reaches the event stream: INFO for the allowed namespaces, else WARNING."""
    if any(_under(logger_name, prefix) for prefix in QUIET_PREFIXES):
        return levelno >= DEFAULT_THRESHOLD
    for prefix in ALLOWED_PREFIXES:
        if logger_name == prefix or logger_name.startswith(prefix + '.'):
            return levelno >= logging.INFO
    return levelno >= DEFAULT_THRESHOLD


def level_name(levelno: int) -> str:
    for threshold, name in _LEVEL_NAMES:
        if levelno >= threshold:
            return name
    return 'INFO'


class EventLogHandler(logging.Handler):
    def __init__(self, source: str, service=None) -> None:
        super().__init__(level=logging.NOTSET)
        self._source = source
        self._service = service if service is not None else event_service

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(_state, 'active', False):
            return
        if not is_captured(record.name, record.levelno):
            return
        _state.active = True
        try:
            message = record.getMessage()
            if record.exc_info:
                message = f'{message}\n{logging.Formatter().formatException(record.exc_info)}'
            first_line = message.splitlines()[0] if message else ''
            self._service.emit(
                level=level_name(record.levelno),
                title=f'{record.name}: {first_line}'[:TITLE_MAX_LENGTH],
                message=message,
                source=self._source,
                logger=record.name,
                push=False,
            )
        except Exception as exc:
            # logging mag nooit de aanroeper laten sneuvelen, maar stil falen
            # maakt van deze handler een zwart gat. stderr, niet logging: een
            # logregel hier komt via deze handler meteen weer binnen.
            print(f'EventLogHandler: event uit {record.name} mislukt: {exc}', file=sys.stderr)
        finally:
            _state.active = False


def setup_logging(source: str, level: int = logging.INFO) -> None:
    """Zet stdout-logging op zoals voorheen, en hang de events-stroom eronder.

    Dit is ook de plek waar de ntfy-sink wordt geregistreerd: elke service die
    zijn logging opzet krijgt daarmee automatisch de push-kant erbij, zonder
    dat elk entrypoint dat apart moet regelen.

    De sink-registratie wordt maar één keer uitgevoerd per process: basicConfig
    met force=True verwijdert alle bestaande handlers, dus een check op de handler-
    lijst zou altijd waar zijn. We gebruiken een module-flag i.p.v. een handler-check
    zodat de sink maar eenmaal geregistreerd wordt.
    """
    global _sink_registered
    logging.basicConfig(level=level, format=LOG_FORMAT, force=True)
    if not _sink_registered:
        event_service.add_sink(NtfySink())
        _sink_registered = True
    logging.getLogger().addHandler(EventLogHandler(source=source))
