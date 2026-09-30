"""Fixtures for the tests that talk to a real MariaDB.

These deliberately live outside `services/`, for two reasons:

* `scripts/test/music-management-unit.sh` collects `services/` and `tools/`, so
  putting them here keeps a suite that needs a database out of the unit run;
* the real pymysql is used here -- which is the entire point of this suite.
  The mock_base stubs (pymysql, mutagen, ...) are opt-in per test module since
  bug report 085 (`pytestmark = pytest.mark.mock_base(...)`), and nothing under
  tests/integration/ asks for them.

Start the database with ./scripts/test/db-integration.sh, which also sets the
DB_* environment variables these fixtures read.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Belt and braces with scripts/test/db-integration.sh: the background loops write
# to the database on their own schedule, and the radio scheduler's rows collide
# with the per-test truncate below. Set before main.py is imported anywhere.
os.environ.setdefault('MUMA_DISABLE_BACKGROUND_WORKERS', '1')

# Likewise set before main.py: the system API key has no literal fallback any more
# (services/music_manager/api_key.py), and this suite runs the app in-process, so the
# same value serves the client and the server. It matches the key
# docker/compose.test.yml uses, so no suite disagrees with another about it.
os.environ.setdefault('API_KEY', 'test-api-key')


def _unavailable(reason: str):
    """Give up on the suite: a hard failure in CI, a loud skip anywhere else.

    A skip is green. backend:integration used to gate only on the container
    reporting healthy, so a database the tests could not reach -- or an
    environment without pymysql -- skipped every test in the session and the job
    still passed, having proved nothing. GitLab sets CI on every job; locally a
    missing database stays a skip, since running the unit tests without Docker is
    normal there.
    """
    if os.getenv('CI'):
        pytest.fail(f'integration suite cannot run in CI: {reason}', pytrace=False)
    pytest.skip(f'INTEGRATION SUITE NOT RUN -- {reason}')


try:
    import pymysql
except ImportError:  # pragma: no cover - depends on the environment
    if os.getenv('CI'):
        raise
    pytest.skip('INTEGRATION SUITE NOT RUN -- the real pymysql is not installed', allow_module_level=True)


def _connection_settings():
    host = os.getenv('DB_HOST', '127.0.0.1')
    port = int(os.getenv('DB_PORT', '13306'))
    if ':' in host and not host.startswith('['):
        host, port_str = host.split(':', 1)
        port = int(port_str)
    return {
        'host': host,
        'port': port,
        'user': os.getenv('DB_USER', 'muma_test'),
        'password': os.getenv('DB_PASS', 'muma_test'),
        'database': os.getenv('DB_DB', 'muma_test'),
    }


def _connect(**overrides):
    settings = _connection_settings() | overrides
    return pymysql.connect(cursorclass=pymysql.cursors.DictCursor, autocommit=True, **settings)


@pytest.fixture(scope='session')
def database():
    """A connection to the test database, with the production schema applied.

    The schema comes from the same code paths a real deployment uses -- the
    shared ensure_tables_exist(), then every router's own init_db(), then the
    migrate_*.sql files scripts/deploy.sh applies. If any of those drift from
    the SQL the endpoints run, this suite is where it shows up.
    """
    try:
        connection = _connect()
    except Exception as exc:  # pragma: no cover - only hit when no database is up
        _unavailable(f'no test database reachable ({exc}); run ./scripts/test/db-integration.sh')

    _apply_schema(connection)
    yield connection
    connection.close()


def _apply_schema(connection):
    from services.common import db_init
    from services.music_manager import rbac
    from services.music_manager.routers import artist_images, events, news, scrobbler, users

    db_init.ensure_tables_exist()
    with connection.cursor() as cursor:
        # Order matters: rbac.init_db creates `roles`, which users.init_db's
        # foreign keys and the user_requests table depend on.
        for init in (
            users.init_db,
            rbac.init_db,
            scrobbler.init_db,
            artist_images.init_db,
            events.init_db,
            news.init_db,
        ):
            init(cursor)
    _apply_migrations(connection)


def _apply_migrations(connection):
    """Run every migrate_*.sql, exactly as scripts/deploy.sh does on each deploy."""
    for migration in sorted(ROOT.glob('migrate_*.sql')):
        statements = _split_statements(migration.read_text(encoding='utf-8'))
        with connection.cursor() as cursor:
            for statement in statements:
                try:
                    cursor.execute(statement)
                except pymysql.err.MySQLError as exc:
                    # Migrations are written to be re-runnable on a deployed
                    # database, so "already exists"/"duplicate" is expected on a
                    # schema ensure_tables_exist() already brought up to date.
                    if exc.args[0] not in _IDEMPOTENT_ERRORS:
                        raise AssertionError(f'{migration.name}: {statement[:120]}... -> {exc}') from exc


# Duplicate column/key/table, unknown column on DROP, cannot drop what is not there.
_IDEMPOTENT_ERRORS = {1050, 1060, 1061, 1091, 1826, 1146, 1054}


def _split_statements(sql: str) -> list[str]:
    """Split on `;` at statement level, dropping comments and empty fragments."""
    cleaned = '\n'.join(line for line in sql.splitlines() if not line.strip().startswith('--') and line.strip() != '')
    return [statement.strip() for statement in cleaned.split(';') if statement.strip()]


@pytest.fixture
def db(database):
    """Per-test database: schema stays, every row is removed first."""
    _truncate_all(database)
    return database


def _truncate_all(connection):
    """Empty every base table.

    DELETE rather than TRUNCATE: TRUNCATE implicitly commits and takes a
    metadata lock on the table, which on a loaded CI runner collided with the
    connections the endpoints under test had just opened and closed and failed
    with "Lock wait timeout exceeded". These tables never hold more than a
    handful of rows, so the cost of DELETE is irrelevant.

    The AUTO_INCREMENT reset keeps ids predictable per test, the way TRUNCATE
    used to leave them, but only for the tables a test actually wrote to.
    Resetting all forty of them on every one of the forty-odd tests meant ~1700
    ALTER TABLE statements per run, which took the server down with "Lost
    connection to MySQL server during query" and turned every later test into a
    cascade of InterfaceError.

    Reconnects first: if a previous test did lose the connection, one dead
    socket should not fail the rest of the suite.
    """
    connection.ping(reconnect=True)
    with connection.cursor() as cursor:
        cursor.execute('SET FOREIGN_KEY_CHECKS = 0')
        cursor.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
        tables = [next(iter(row.values())) for row in cursor.fetchall()]
        emptied = []
        for table in tables:
            if cursor.execute(f'DELETE FROM `{table}`'):
                emptied.append(table)
        for table in emptied:
            cursor.execute(f'ALTER TABLE `{table}` AUTO_INCREMENT = 1')
        cursor.execute('SET FOREIGN_KEY_CHECKS = 1')


@pytest.fixture
def api(db, monkeypatch):
    """A FastAPI TestClient wired to the real database instead of a mock."""
    from fastapi.testclient import TestClient

    from services.music_manager import database as database_module
    from services.music_manager.main import app

    def real_connection():
        return _connect()

    # Every router imported get_db_connection by value, so each module that uses
    # it needs its own patch; patching the source module alone would miss them.
    monkeypatch.setattr(database_module, 'get_db_connection', real_connection)
    for module_name in (
        'services.music_manager.routers.users',
        'services.music_manager.routers.library',
        'services.music_manager.routers.management',
        'services.music_manager.routers.channel_links',
        'services.music_manager.routers.artist_curation',
        'services.music_manager.routers.genre_curation',
        'services.music_manager.routers.festivals',
        'services.music_manager.routers.lineups',
        'services.music_manager.routers.artist_images',
        'services.music_manager.routers.scrobbler',
        'services.music_manager.routers.events',
        'services.music_manager.routers.stats',
        'services.music_manager.routers.rating',
        'services.music_manager.routers.analytics',
        'services.music_manager.routers.listening',
        'services.music_manager.routers.radio',
        'services.music_manager.routers.user_requests',
        'services.music_manager.routers.diagnostics',
        'services.music_manager.routers.news',
        'services.music_manager.routers.scanner',
        'services.music_manager.routers.curation',
        'services.music_manager.routers.downloaders',
        'services.music_manager.routers.feeds',
        'services.music_manager.routers.songs',
        'services.music_manager.routers.reconcile',
    ):
        module = __import__(module_name, fromlist=['get_db_connection'])
        if hasattr(module, 'get_db_connection'):
            monkeypatch.setattr(module, 'get_db_connection', real_connection)

    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def _reset_auth_rate_limiter():
    """Same reason as in services/conftest.py: the auth endpoints are rate
    limited per client address and the TestClient always presents the same one."""
    try:
        from services.music_manager.rate_limit import reset_limiters
    except Exception:
        yield
        return
    reset_limiters()
    yield
    reset_limiters()


@pytest.fixture(autouse=True)
def _reset_feed_sample_memo():
    """Same reason as in services/conftest.py: every test truncates and reseeds the
    library under the same user and day, so a memoised split-mix sample must not
    survive into the next one."""
    try:
        from services.music_manager.feeds.build import clear_sample_memo
    except Exception:
        yield
        return
    clear_sample_memo()
    yield
    clear_sample_memo()


@pytest.fixture
def api_key():
    # The resolver is what the app actually checks X-API-Key against, so asking it
    # keeps the fixture correct no matter which variable the compose file sets.
    from services.music_manager.api_key import resolve_system_api_key

    return resolve_system_api_key()


@pytest.fixture
def headers(api_key):
    return {'x-api-key': api_key}


def run_sql(connection, statement, params=None):
    """Helper for arranging fixtures: execute and return the rows, if any."""
    with connection.cursor() as cursor:
        cursor.execute(statement, params)
        try:
            return cursor.fetchall()
        except pymysql.err.ProgrammingError:
            return []


def mariadb_available() -> bool:
    """Used by scripts/test/db-integration.sh to fail fast with a clear message."""
    try:
        _connect().close()
        return True
    except Exception:
        return False


if __name__ == '__main__':  # pragma: no cover - CLI helper for the shell script
    sys.exit(0 if mariadb_available() else 1)


__all__ = ['database', 'db', 'api', 'api_key', 'headers', 'run_sql', 'mariadb_available']


def pytest_configure(config):
    config.addinivalue_line('markers', 'integration: needs a live MariaDB')


@pytest.fixture(scope='session')
def built_schemas(database):
    """The schema built twice from nothing, once per path, as snapshots.

    ``code`` is what a fresh stack creates (db_init, every init_db main.py's startup
    runs, the tagger's own table); ``migrated`` is what the deploy produces (db_init,
    then every migrate_*.sql twice). Each is built in a database of its own, so the
    shared session database -- and every test that relies on its rows -- is left
    alone. db-integration.sh grants the test user the muma_test_* databases this
    needs.
    """
    from tests.integration import schema_sources

    names = {'code': 'muma_test_schema_code', 'migrated': 'muma_test_schema_migrated'}
    snapshots = {}
    for kind, name in names.items():
        try:
            with database.cursor() as cursor:
                cursor.execute(f'DROP DATABASE IF EXISTS `{name}`')
                cursor.execute(f'CREATE DATABASE `{name}`')
        except pymysql.err.MySQLError as exc:
            _unavailable(f'cannot create the scratch database {name} ({exc}); see scripts/test/db-integration.sh')
        connection = _connect(database=name)
        try:
            if kind == 'code':
                schema_sources.build_from_code(connection, name)
            else:
                schema_sources.build_from_migrations(connection, name, _apply_migrations)
            snapshots[kind] = schema_sources.snapshot(connection, name)
        finally:
            connection.close()
    yield snapshots
    with database.cursor() as cursor:
        for name in names.values():
            cursor.execute(f'DROP DATABASE IF EXISTS `{name}`')
