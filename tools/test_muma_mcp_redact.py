"""Secret masking for container logs, tools/muma_mcp/redact.py."""

from __future__ import annotations

from tools.muma_mcp.redact import MASK, redact

SECRET = 'sup3rsecretvalue'


def test_known_secret_is_masked_by_exact_match():
    """The one part of this that cannot produce a false negative."""
    assert redact(f'connecting with {SECRET} now', [SECRET]) == f'connecting with {MASK} now'


def test_short_values_are_not_treated_as_secrets():
    """Masking a three-character value would shred ordinary log lines."""
    assert redact('the id is abc everywhere', ['abc']) == 'the id is abc everywhere'


def test_longest_secret_first_leaves_no_tail():
    text = f'{SECRET}extra'
    assert redact(text, [SECRET, f'{SECRET}extra']) == MASK


def test_assignment_patterns_are_masked():
    line = 'DB_PASS=hunter2 api_key: abc123def token=zzzzzz'
    result = redact(line)
    assert 'hunter2' not in result
    assert 'abc123def' not in result
    assert 'zzzzzz' not in result


def test_assignment_masking_keeps_the_key_readable():
    assert redact('password=hunter2') == f'password={MASK}'


def test_bearer_token_is_masked():
    assert redact('Bearer abcdefghijklmnop') == f'Bearer {MASK}'


def test_header_line_is_masked():
    assert redact('X-API-Key: abcdefghijklmnop') == f'X-API-Key: {MASK}'


def test_url_credentials_are_masked():
    result = redact('mysql://muma:hunter2@192.0.2.27/music-management')
    assert 'hunter2' not in result
    assert '192.0.2.27' in result


def test_ordinary_log_lines_are_untouched():
    line = 'INFO scanner: Found 1423 files in /mnt/music, 12 new'
    assert redact(line, [SECRET]) == line


def test_empty_input_is_returned_as_is():
    assert redact('') == ''


def test_empty_secret_is_ignored():
    """A blank configured value must not turn into a mask on every character."""
    assert redact('unchanged', ['']) == 'unchanged'


def test_underscore_prefixed_names_are_masked():
    """DB_PASS and MUMA_API_KEY are the names that actually appear in these logs."""
    result = redact('DB_PASS=hunter2 MUMA_API_KEY=abcdefghij')
    assert 'hunter2' not in result
    assert 'abcdefghij' not in result
