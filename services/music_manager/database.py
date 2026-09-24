"""The music-manager's MariaDB connection pool, plus a bounded health probe.

Two properties of DBUtils' PooledDB shape this module:

- It has no wait timeout. With `blocking=True` an exhausted pool makes `connection()`
  wait forever, which is how /health used to hang instead of answering. The pool is
  therefore created with `blocking=False` (exhaustion raises at once) and
  `get_db_connection` retries for at most DB_POOL_WAIT_SECONDS before raising
  `DatabaseBusyError`, which main.py turns into a 503.
- `ping=4` pings a cached connection only when a query runs, never on checkout, so
  "the pool handed out a connection" says nothing about whether MariaDB is up.
  `check_database` answers that question with its own short-lived connection and a
  `SELECT 1` under tight timeouts, independent of the pool's state.

The pool runs with `autocommit=True`, so a `conn.commit()` after several writes commits
nothing extra: each statement was already committed on its own. Code that writes more
than one statement which must land together -- above all a DELETE followed by the
INSERTs that replace it -- wraps them in `transaction(conn)`.
"""

import contextlib
import logging
import os
import time
from collections.abc import Iterator
from typing import Any

import pymysql
from dbutils.pooled_db import PooledDB
from dotenv import load_dotenv

try:
    from dbutils.pooled_db import TooManyConnections as _PoolExhausted

    if not (isinstance(_PoolExhausted, type) and issubclass(_PoolExhausted, BaseException)):
        raise ImportError('dbutils is stubbed')  # the unit tests replace dbutils with a MagicMock
except ImportError:

    class _PoolExhausted(Exception):  # type: ignore[no-redef]
        """Stand-in when dbutils is not the real library; never raised by a stub pool."""


load_dotenv()
_pool = None
logger = logging.getLogger('music-manager.database')

# How long a caller may wait for a free pooled connection before getting a clear error.
POOL_WAIT_SECONDS = float(os.getenv('DB_POOL_WAIT_SECONDS', '5'))
_POOL_RETRY_SECONDS = 0.05
# Per-step socket timeout for the health probe (connect, write, read), in seconds.
HEALTH_TIMEOUT_SECONDS = 1


class DatabaseBusyError(RuntimeError):
    """Every pooled connection stayed in use for longer than POOL_WAIT_SECONDS."""


def _connection_params() -> dict:
    """Host, port, credentials and database from the environment, shared by pool and probe."""
    host = os.getenv('DB_HOST', 'db')
    port = int(os.getenv('DB_PORT', '3306'))

    # Handle host:port format
    if ':' in host and not host.startswith('['):
        host, port_str = host.split(':', 1)
        port = int(port_str)
    return {
        'host': host,
        'port': port,
        'user': os.getenv('DB_USER', 'music-management'),
        'password': os.getenv('DB_PASS', ''),
        'database': os.getenv('DB_DB', 'music-management'),
    }


def get_db_pool():
    """The process-wide pool, created on first use; None when it could not be created."""
    global _pool
    if _pool is None:
        try:
            _pool = PooledDB(
                creator=pymysql,
                maxconnections=20,
                mincached=2,
                maxcached=5,
                maxshared=0,
                # Non-blocking: exhaustion raises at once and get_db_connection bounds the
                # wait itself, because PooledDB's own blocking wait has no timeout.
                blocking=False,
                maxusage=None,
                setsession=[],
                ping=4,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
                **_connection_params(),
            )
        except Exception as e:
            print(f'Failed to create connection pool: {e}')
    return _pool


def get_db_connection(wait_seconds: float | None = None):
    """A pooled connection, or None when the pool itself could not be created.

    Waits at most `wait_seconds` (default POOL_WAIT_SECONDS) for a free connection when
    all of them are in use, then raises DatabaseBusyError. Any other failure to connect
    (MariaDB down, wrong credentials) raises pymysql's own error straight away.
    """
    pool = get_db_pool()
    if not pool:
        return None
    deadline = time.monotonic() + (POOL_WAIT_SECONDS if wait_seconds is None else wait_seconds)
    while True:
        try:
            return pool.connection()
        except _PoolExhausted as exc:
            if time.monotonic() >= deadline:
                raise DatabaseBusyError('No free database connection: the pool is exhausted') from exc
            time.sleep(_POOL_RETRY_SECONDS)


def check_database() -> bool:
    """True when MariaDB answers `SELECT 1` on a fresh connection within the health timeouts.

    Deliberately not a pooled connection: a cached connection can be dead without the pool
    noticing, and an exhausted pool must not make the health check wait. Never raises.
    """
    conn = None
    try:
        conn = pymysql.connect(
            connect_timeout=HEALTH_TIMEOUT_SECONDS,
            read_timeout=HEALTH_TIMEOUT_SECONDS,
            write_timeout=HEALTH_TIMEOUT_SECONDS,
            **_connection_params(),
        )
        with conn.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        return True
    except Exception:  # pylint: disable=broad-except  # any failure means unreachable
        return False
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()


@contextlib.contextmanager
def transaction(conn: Any) -> Iterator[Any]:
    """Run the enclosed writes as one transaction on `conn`: all of them land, or none.

    `conn.begin()` issues an explicit BEGIN, which suspends the pool's autocommit until
    the matching COMMIT or ROLLBACK, after which the connection is back in autocommit
    mode. Commits when the block finishes, rolls back when it raises -- an
    HTTPException for a 404 included -- and re-raises the original exception, even when
    the rollback itself fails. A connection closed mid-transaction is safe as well:
    DBUtils rolls back whatever is still open when the connection returns to the pool.

    Every statement has to run on this same `conn`: a second connection sees none of
    the uncommitted rows and is not part of the transaction.
    """
    conn.begin()
    try:
        yield conn
    except BaseException:
        try:
            conn.rollback()
        except Exception as rollback_error:  # pylint: disable=broad-except  # keep the original error
            logger.warning('Rolling back a transaction failed: %s', rollback_error)
        raise
    conn.commit()
