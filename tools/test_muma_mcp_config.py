"""Configuration resolution, tools/muma_mcp/config.py."""

from __future__ import annotations

import pytest

from tools.muma_mcp import config as config_module
from tools.muma_mcp.config import Config, ConfigError, load, parse_env_file

COMPLETE = {
    'MUMA_PROD_URL': 'http://192.0.2.27:8000/',
    'MUMA_PROD_API_KEY': 'key',
    'MUMA_RO_DB_HOST': '192.0.2.27',
    'MUMA_RO_DB_USER': 'muma-readonly',
    'MUMA_RO_DB_PASS': 'pw',
    'MUMA_RO_DB_NAME': 'music-management',
}


@pytest.fixture(autouse=True)
def _no_real_config_file(tmp_path, monkeypatch):
    """Point the loader at an empty directory so no developer's own file leaks in."""
    monkeypatch.setenv('MUMA_MCP_CONFIG_DIR', str(tmp_path))


def test_load_returns_a_config():
    config = load(dict(COMPLETE))
    assert config.db_user == 'muma-readonly'
    assert config.db_port == 3306


def test_trailing_slash_is_stripped_from_the_url():
    """Otherwise every request path becomes a double slash."""
    assert load(dict(COMPLETE)).prod_url == 'http://192.0.2.27:8000'


def test_missing_variables_are_all_named_at_once():
    partial = dict(COMPLETE)
    del partial['MUMA_RO_DB_PASS']
    del partial['MUMA_PROD_API_KEY']

    with pytest.raises(ConfigError) as excinfo:
        load(partial)

    message = str(excinfo.value)
    assert 'MUMA_RO_DB_PASS' in message
    assert 'MUMA_PROD_API_KEY' in message


def test_no_defaults_are_invented():
    """A missing host must be an error, never a guess at which database to read."""
    with pytest.raises(ConfigError):
        load({})


def test_empty_value_counts_as_missing():
    partial = dict(COMPLETE, MUMA_RO_DB_PASS='')
    with pytest.raises(ConfigError, match='MUMA_RO_DB_PASS'):
        load(partial)


def test_non_numeric_port_is_an_error():
    with pytest.raises(ConfigError, match='MUMA_RO_DB_PORT'):
        load(dict(COMPLETE, MUMA_RO_DB_PORT='drieduizend'))


def test_file_supplies_values_and_environment_wins(tmp_path, monkeypatch):
    (tmp_path / 'env').write_text(
        '\n'.join(f'{key}={value}' for key, value in COMPLETE.items()) + '\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('MUMA_MCP_CONFIG_DIR', str(tmp_path))

    from_file = load({})
    assert from_file.db_host == '192.0.2.27'

    overridden = load({'MUMA_RO_DB_HOST': '10.0.0.9'})
    assert overridden.db_host == '10.0.0.9'
    assert overridden.db_user == 'muma-readonly'


def test_config_path_honours_the_override(tmp_path, monkeypatch):
    monkeypatch.setenv('MUMA_MCP_CONFIG_DIR', str(tmp_path))
    assert config_module.config_path() == tmp_path / 'env'


def test_parse_env_file_skips_comments_and_blank_lines():
    parsed = parse_env_file('# note\n\nA=1\n  B = 2 \n')
    assert parsed == {'A': '1', 'B': '2'}


def test_parse_env_file_strips_matching_quotes():
    assert parse_env_file('A="1"\nB=\'2\'\n') == {'A': '1', 'B': '2'}


def test_parse_env_file_ignores_a_line_without_an_equals_sign():
    """A stray note in the file should not stop the server from starting."""
    assert parse_env_file('een losse regel\nA=1\n') == {'A': '1'}


def test_secrets_are_the_values_worth_masking():
    config = load(dict(COMPLETE))
    assert set(config.secrets) == {'key', 'pw'}


def test_secrets_skips_blanks():
    config = Config(
        prod_url='http://x',
        api_key='key',
        db_port=3306,
        db_host='h',
        db_user='u',
        db_pass='',
        db_name='d',
    )
    assert config.secrets == ('key',)
