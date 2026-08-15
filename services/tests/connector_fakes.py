"""Test doubles for `DatabaseConnector`.

`DatabaseConnector` exposes two entry points: `connect()`, which hands out a raw
pymysql connection the caller must close, and `connection()`, a context manager
that closes it for you. Production code should prefer the latter -- see
`services/tests/DatabaseConnectionLeakTest.py` for why -- so every fake connector
in the suite has to answer to both, or a test starts failing for the shape of the
double rather than for the behaviour it is meant to pin.
"""
from unittest.mock import MagicMock


def wire_connector(connector, connection):
    """Teach a MagicMock connector both entry points, returning `connection`.

    Returns the connector, so it can be used inline in a `patch(..., return_value=...)`.
    """
    connector.connect.return_value = connection
    connector.connection.return_value.__enter__.return_value = connection
    connector.connection.return_value.__exit__.return_value = False
    return connector


def fake_connector(connection=None):
    """A ready-made connector double plus the connection it hands out."""
    connection = connection if connection is not None else MagicMock()
    return wire_connector(MagicMock(), connection), connection
