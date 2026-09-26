"""The calling user's own Subsonic API token, read from -- or issued into -- LMS's `lms.db`.

LMS accepts two ways of signing a `/rest` request with a secret that never travels in the clear:
`t=md5(token + salt)&s=salt`, and the OpenSubsonic `apiKey`. Both are checked against the user's
*Subsonic API token* (`auth_token` rows in the `subsonic` domain), never against the login
password, which LMS does not hold in any form it could salt. A client that only knows the login
password therefore has to send it as `p=`, which puts it in every URL and every access log on the
way (bug report 054, item 2; bug report 103).

`GET /api/auth/subsonic-token` closes that gap: an authenticated user asks for their own token and
signs every later request with it. The token lives in LMS's own database, which music-manager
already opens directly for the hourly user and playlist sync (`routers.users.lms_db_targets`), so
this reads the same files the same way, and only ever inserts a row -- it never alters or deletes
anything the server holds.

Which LMS user is "the caller" is decided by `user.muma_id` -- the id LMS's user synchroniser
stored for this MuMa account -- and only when no row carries that id by the login name, the exact
spelling first. The login name is compared case-insensitively as a last resort only because LMS
used to create a second user for a case variant (bug report 074); the exact match wins that tie.

A user who has no token yet gets one: 32 random bytes, URL-safe, which is well above the 16
characters `/updateUser` and `/muma/api/admin/subsonic-token` insist on. An administrator-issued
token is returned as it is, never replaced, so external clients configured with it keep working.
When music-manager sees more than one server database, the token of the first one that has it is
written into every other one that lacks it, so the app can sign against whichever server answers.
"""

from __future__ import annotations

import contextlib
import logging
import secrets
import sqlite3
from dataclasses import dataclass

logger = logging.getLogger('music-manager.subsonic-token')

#: The auth-token domain LMS checks `t`/`s` and `apiKey` against (`SubsonicResource::authenticateUser`).
SUBSONIC_DOMAIN = 'subsonic'

#: LMS refuses a Subsonic token shorter than this (`userSettings::minSubsonicTokenLength`).
MIN_TOKEN_LENGTH = 16

#: How long a write waits for LMS to release its lock. LMS itself dies on a locked database rather
#: than waiting (see `routers.users.sync_single_server_db`), so the write is kept short instead.
SQLITE_TIMEOUT_SECONDS = 5


class NoServerDatabase(Exception):
    """music-manager cannot see any LMS database, so there is nowhere to read a token from."""


class NotOnServer(Exception):
    """None of the LMS databases knows this account yet (it has not been synced there)."""


@dataclass(frozen=True)
class SubsonicToken:
    """What a client needs to sign its Subsonic requests: the LMS login name and the token."""

    username: str
    token: str
    issued: bool


def new_token() -> str:
    """A fresh token: 32 random bytes, URL-safe base64 (43 characters)."""
    return secrets.token_urlsafe(32)


def find_lms_user(server: sqlite3.Connection, muma_user_id: int | None, username: str) -> tuple[int, str] | None:
    """The LMS user id and login name for this MuMa account, or None when LMS does not know it.

    `muma_id` decides when it is set; the login name only when no row carries the id. Among login
    names the exact spelling wins over a case variant (bug report 074).
    """
    if muma_user_id is not None:
        row = server.execute(
            'SELECT id, login_name FROM user WHERE muma_id = ? ORDER BY id LIMIT 1', (muma_user_id,)
        ).fetchone()
        if row:
            return int(row[0]), str(row[1])
    if not username:
        return None
    row = server.execute(
        'SELECT id, login_name FROM user WHERE login_name = ? COLLATE NOCASE '
        'ORDER BY (login_name = ?) DESC, id LIMIT 1',
        (username, username),
    ).fetchone()
    if row:
        return int(row[0]), str(row[1])
    return None


def existing_token(server: sqlite3.Connection, lms_user_id: int) -> str | None:
    """The user's oldest usable Subsonic token in this database, or None.

    A token shorter than LMS's floor is skipped: it predates the floor and a client should not be
    handed something the admin route would refuse to issue today.
    """
    rows = server.execute(
        'SELECT value FROM auth_token WHERE domain = ? AND user_id = ? ORDER BY id',
        (SUBSONIC_DOMAIN, lms_user_id),
    ).fetchall()
    for (value,) in rows:
        if value and len(value) >= MIN_TOKEN_LENGTH:
            return str(value)
    return None


def insert_token(server: sqlite3.Connection, lms_user_id: int, token: str) -> None:
    """Adds `token` as a Subsonic token of `lms_user_id`, in the shape LMS's own `createAuthToken`
    writes: no expiry, no use limit. Any token the user already has stays valid."""
    server.execute(
        'INSERT INTO auth_token (version, domain, value, expiry, use_count, last_used, max_use_count, user_id) '
        'VALUES (0, ?, ?, NULL, 0, NULL, NULL, ?)',
        (SUBSONIC_DOMAIN, token, lms_user_id),
    )
    server.commit()


def _open(path: str) -> sqlite3.Connection:
    """A connection to one server database, with a short lock timeout."""
    return sqlite3.connect(path, timeout=SQLITE_TIMEOUT_SECONDS)


def own_subsonic_token(targets: list[tuple[str, str]], muma_user_id: int | None, username: str) -> SubsonicToken:
    """The caller's Subsonic token, issued first when no server database holds one.

    `targets` is `routers.users.lms_db_targets()`: (path, source) pairs, the first one preferred.
    Raises NoServerDatabase when there is no target at all and NotOnServer when no target knows
    the account. A target that cannot be opened or read is skipped with a warning -- another
    server may still answer -- but when it was the only one, the sqlite3 error propagates.
    """
    if not targets:
        raise NoServerDatabase()

    found: list[tuple[str, str, int, str, str | None]] = []  # path, source, lms id, login, token
    last_error: sqlite3.Error | None = None
    for path, source in targets:
        server = None
        try:
            server = _open(path)
            user = find_lms_user(server, muma_user_id, username)
            if user is None:
                continue
            found.append((path, source, user[0], user[1], existing_token(server, user[0])))
        except sqlite3.Error as exc:
            last_error = exc
            logger.warning('Could not read Subsonic tokens from %s (%s): %s', path, source, exc)
        finally:
            if server is not None:
                with contextlib.suppress(sqlite3.Error):
                    server.close()

    if not found:
        if last_error is not None:
            raise last_error
        raise NotOnServer()

    token = next((entry[4] for entry in found if entry[4]), None)
    issued = token is None
    if token is None:
        token = new_token()

    for path, source, lms_user_id, _login, current in found:
        if current == token:
            continue
        # A server that holds a different token for the user gets ours next to it rather than in
        # its place: LMS accepts any of a user's tokens, so whatever holds the other keeps working.
        server = None
        try:
            server = _open(path)
            insert_token(server, lms_user_id, token)
            logger.info('%s a Subsonic token for %s on %s', 'Issued' if issued else 'Copied', username, source)
        except sqlite3.Error as exc:
            logger.warning('Could not store a Subsonic token for %s in %s (%s): %s', username, path, source, exc)
            if len(found) == 1:
                raise
        finally:
            if server is not None:
                with contextlib.suppress(sqlite3.Error):
                    server.close()

    return SubsonicToken(username=found[0][3], token=token, issued=issued)
