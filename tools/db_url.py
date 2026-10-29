"""One place for the ad-hoc tools to build a database URL from the environment.

Seven scripts in this directory each carried the same block:

    host = os.getenv("DB_HOST", "<the production address>")
    user = "root"
    password = "<the production root password, in plain text>"

That is the production root credential, committed, with the production address
next to it as a default -- so running any of these from a checkout aimed itself
at production as root without asking. The literal is gone from the working tree,
but it is in git history and therefore still published until the value itself is
rotated.

Nothing here defaults: a missing variable raises rather than quietly picking a
host, because "which database did that script just rewrite" should never be a
question.
"""

from __future__ import annotations

import os

REQUIRED = ('DB_HOST', 'DB_USER', 'DB_PASS', 'DB_DB')


def database_url() -> str:
    """A SQLAlchemy URL from DB_HOST/DB_PORT/DB_USER/DB_PASS/DB_DB.

    Raises SystemExit naming everything that is missing, rather than one variable
    at a time.
    """
    values = {name: os.getenv(name) for name in REQUIRED}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise SystemExit(
            f"ontbrekende omgevingsvariabelen: {', '.join(missing)}. "
            'Deze tools praten met de database waar de omgeving naar wijst en '
            'kennen geen standaardwaarden.'
        )
    port = os.getenv('DB_PORT', '3306')
    return (
        f"mysql+mysqlconnector://{values['DB_USER']}:{values['DB_PASS']}@{values['DB_HOST']}:{port}/{values['DB_DB']}"
    )
