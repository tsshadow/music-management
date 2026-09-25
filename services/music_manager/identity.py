"""One identity per account, whatever case its name is typed in.

The rule (docs/authentication.md, "Account names are case-insensitive"): an account name
is compared case-insensitively everywhere, and whatever stores or compares a username uses
the one spelling in `users.username`. MariaDB already compares `users.username` that way
(utf8mb4_general_ci), so the login accepted "Teun" for the account "user" -- but LMS
(SQLite, BINARY) and every Python-side comparison did not, and the typed spelling forked
the account in two. See docs/bug-reports/074-login-case-forks-user-identity.md.

The lookups use `LOWER()` on both sides rather than relying on the column's collation, so
they mean the same thing on a database created under a different default collation.
"""

from typing import Any


def same_username(first: str | None, second: str | None) -> bool:
    """Whether two spellings name the same account. Blank never matches anything."""
    if not first or not second:
        return False
    return first.casefold() == second.casefold()


def canonical_username(cursor: Any, name: str | None) -> str | None:
    """The account's own spelling of `name`, from `users.username`.

    A name no account carries comes back unchanged: LMS may relay a listen for a local
    user music-manager does not know, and that listen is still worth keeping. Blank in,
    blank out.
    """
    if not name:
        return name
    cursor.execute('SELECT username FROM users WHERE LOWER(username) = LOWER(%s) ORDER BY id LIMIT 1', (name,))
    row = cursor.fetchone()
    found = row.get('username') if isinstance(row, dict) else None
    return found if isinstance(found, str) and found else name


def username_taken(cursor: Any, name: str, exclude_user_id: int | None = None) -> bool:
    """Whether an account other than `exclude_user_id` already carries `name` in any case."""
    if exclude_user_id is None:
        cursor.execute('SELECT id FROM users WHERE LOWER(username) = LOWER(%s) LIMIT 1', (name,))
    else:
        cursor.execute(
            'SELECT id FROM users WHERE LOWER(username) = LOWER(%s) AND id <> %s LIMIT 1', (name, exclude_user_id)
        )
    return cursor.fetchone() is not None


def account_spellings(cursor: Any) -> dict[str, str]:
    """Every account name, keyed by its casefolded form: for mapping many names at once.

    The oldest account wins a spelling clash -- which the unique key on `users.username`
    rules out under its case-insensitive collation anyway.
    """
    cursor.execute('SELECT username FROM users ORDER BY id')
    rows = cursor.fetchall() or []
    spellings: dict[str, str] = {}
    for row in rows:
        name = row.get('username') if isinstance(row, dict) else None
        if name:
            spellings.setdefault(name.casefold(), name)
    return spellings


def spelled(spellings: dict[str, str], name: str) -> str:
    """`name` in the account's own spelling from `account_spellings`, or unchanged."""
    return spellings.get(name.casefold(), name) if name else name
