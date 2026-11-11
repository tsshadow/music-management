"""nginx takes a client address only from proxies it is told to trust (issue #234).

reverse-proxy.conf trusts loopback and the Docker networks (172.16.0.0/12) for /muma/api/, and
includes a file the reverse-proxy container's entrypoint writes from NGINX_TRUSTED_PROXY. nginx
publishes port 80 on every interface, so a LAN range in that list would let any LAN host give
MuMa's login rate limit an address of its own choosing.

The entrypoint script is taken from the compose file itself and run with /bin/sh, with compose's
`$$` unescaped the way compose does it, so these tests pin what the container really runs.
"""

import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
LMS = ROOT / 'services' / 'music-management-server' / 'docker-compose.yml'
CONF = ROOT / 'services' / 'music-management-server' / 'nginx' / 'reverse-proxy.conf'
INCLUDE = '/etc/nginx/muma/trusted-proxies.conf'
IMAGE_ENTRYPOINT = '/docker-entrypoint.sh'


def _proxy():
    """The reverse-proxy service of the LMS stack."""
    return yaml.safe_load(LMS.read_text(encoding='utf-8'))['services']['reverse-proxy']


def _muma_api_location():
    """The text of the `location /muma/api/ { ... }` block in reverse-proxy.conf."""
    text = CONF.read_text(encoding='utf-8')
    match = re.search(r'location /muma/api/ \{(.*?)\n    \}', text, re.S)
    assert match, 'no location /muma/api/ block in reverse-proxy.conf'
    return match.group(1)


def _render(tmp_path, value):
    """Run the entrypoint script with NGINX_TRUSTED_PROXY=value; return (result, include text)."""
    entrypoint = _proxy()['entrypoint']
    assert entrypoint[:2] == ['/bin/sh', '-c']
    script = entrypoint[2].replace('$$', '$')
    assert INCLUDE in script and f'exec {IMAGE_ENTRYPOINT}' in script
    out = tmp_path / 'trusted-proxies.conf'
    script = script.replace(INCLUDE, str(out)).replace(f'exec {IMAGE_ENTRYPOINT}', 'exit 0 #')
    env = {'PATH': '/usr/bin:/bin'}
    if value is not None:
        env['NGINX_TRUSTED_PROXY'] = value
    result = subprocess.run(
        ['/bin/sh', '-c', script, 'sh', 'nginx'], env=env, capture_output=True, text=True, check=False
    )
    return result, out.read_text(encoding='utf-8') if out.exists() else None


def test_the_conf_trusts_no_lan_range():
    trusted = re.findall(r'set_real_ip_from\s+([^;]+);', _muma_api_location())
    assert trusted == ['127.0.0.1', '::1', '172.16.0.0/12']
    assert '192.168.' not in CONF.read_text(encoding='utf-8').split('location /muma/api/')[1]


def test_the_conf_includes_the_rendered_file_by_pattern():
    # A pattern: nginx starts without the file, e.g. in scripts/test/reverse-proxy-routing.sh.
    assert 'include /etc/nginx/muma/trusted-proxies*.conf;' in _muma_api_location()


def test_the_variable_is_empty_by_default():
    assert _proxy()['environment']['NGINX_TRUSTED_PROXY'] == '${NGINX_TRUSTED_PROXY:-}'


def test_the_include_directory_is_a_bounded_tmpfs():
    # The root filesystem is read-only; the entrypoint can write only to a tmpfs.
    assert '/etc/nginx/muma:size=64k' in _proxy()['tmpfs']


def test_the_image_command_is_kept():
    # Setting `entrypoint` clears the image's CMD, so the compose file has to name it again.
    assert _proxy()['command'] == ['nginx', '-g', 'daemon off;']


@pytest.mark.parametrize('value', [None, '', ' , '])
def test_unset_renders_no_trust(tmp_path, value):
    result, include = _render(tmp_path, value)
    assert result.returncode == 0, result.stderr
    assert include == ''


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('192.0.2.30', ['192.0.2.30']),
        ('192.0.2.30,192.0.2.31', ['192.0.2.30', '192.0.2.31']),
        ('192.0.2.30, 198.51.100.0/24  2001:db8::1', ['192.0.2.30', '198.51.100.0/24', '2001:db8::1']),
    ],
)
def test_one_directive_per_entry(tmp_path, value, expected):
    result, include = _render(tmp_path, value)
    assert result.returncode == 0, result.stderr
    assert include.splitlines() == [f'set_real_ip_from {entry};' for entry in expected]


@pytest.mark.parametrize('value', ['192.0.2.30;include /x', 'npm.lan', '192.0.2.0/24/8', '*', '192.0.2.30/'])
def test_anything_else_stops_the_container(tmp_path, value):
    result, _ = _render(tmp_path, value)
    assert result.returncode != 0
    assert 'NGINX_TRUSTED_PROXY' in result.stderr
