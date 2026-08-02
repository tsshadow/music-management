"""A consistent view of a live Firefox cookie profile.

yt-dlp reads Firefox cookies by copying ``cookies.sqlite`` on its own
(``yt_dlp.cookies._open_database_copy``) and opening the copy. It takes the
database file and nothing else. Firefox keeps that database in write-ahead-log
mode, so a cookie written minutes ago may still live only in
``cookies.sqlite-wal`` until SQLite gets round to a checkpoint -- and the
rotating anti-bot cookie SoundCloud hands out is exactly the kind that is always
the most recent write.

Copying the database together with its log and checkpointing the copy leaves a
single self-contained file, so the copy yt-dlp then makes is complete. The live
profile is mounted read-only in the worker and is never written to.
"""
from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import tempfile

_DATABASE = 'cookies.sqlite'
_SIDECARS = ('-wal', '-shm')


def snapshot_cookie_profile(profile_dir: str) -> str | None:
    """Materialize ``profile_dir`` into a temporary directory yt-dlp can read.

    Returns the directory, which the caller owns and should remove, or None when
    there is no cookie database to snapshot -- in which case the caller should
    simply carry on with the live profile.
    """
    source = os.path.join(profile_dir, _DATABASE)
    if not os.path.isfile(source):
        logging.warning('No cookie database at %s; using the profile as it is.', source)
        return None

    target_dir = tempfile.mkdtemp(prefix='muma-cookies-')
    target = os.path.join(target_dir, _DATABASE)
    try:
        shutil.copy(source, target)
        for suffix in _SIDECARS:
            sidecar = source + suffix
            if os.path.exists(sidecar):
                shutil.copy(sidecar, target + suffix)
        _checkpoint(target)
        return target_dir
    except Exception as exc:
        logging.warning('Could not snapshot the cookie profile at %s: %s', profile_dir, exc)
        shutil.rmtree(target_dir, ignore_errors=True)
        return None


def _checkpoint(database: str) -> None:
    """Fold the write-ahead log into the database file itself."""
    connection = sqlite3.connect(database)
    try:
        connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        connection.commit()
    finally:
        connection.close()
    for suffix in _SIDECARS:
        try:
            os.remove(database + suffix)
        except OSError:
            pass
