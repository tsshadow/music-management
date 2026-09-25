"""Guard: a test run can never reach the real ntfy server (bug report 082)."""

import os


def test_notify_url_is_blank_under_pytest():
    """The root conftest blanks NOTIFY_URL before config_store's load_dotenv can fill it.

    load_dotenv never overrides a variable that is already set, so with this blank the
    default NtfySink finds no URL and posts nothing, whatever a developer's .env says.
    """
    assert os.environ.get('NOTIFY_URL') == ''
