"""Source workers sit behind compose profiles, and production enables them all.

The importer and the three downloaders are opt-in for a self-hoster
(docs/designs/public-edition/technical.md, "Source workers as profiles"). The
owner's production stack keeps running every one of them, which depends on three
things this test pins:

- which service is behind which profile, in the file production deploys
  (docker/docker-compose.yml) and in docker/docker-compose.full.yml;
- the production env check (scripts/ci/check-required-secrets.sh) requires
  COMPOSE_PROFILES, and scripts/deploy.sh refuses a compose file with profiles
  when the env file has none;
- the test stack starts the same services as before, none behind a profile.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PROD = ROOT / 'docker' / 'docker-compose.yml'
FULL = ROOT / 'docker' / 'docker-compose.full.yml'
TEST = ROOT / 'docker' / 'compose.test.yml'
DEPLOY_SH = ROOT / 'scripts' / 'deploy.sh'
VERIFY_SH = ROOT / 'scripts' / 'ci' / 'post-deploy-verify.sh'
SECRETS_SH = ROOT / 'scripts' / 'ci' / 'check-required-secrets.sh'
DEV_SH = ROOT / 'scripts' / 'dev.sh'

EXPECTED = {
    'importer_worker': ['importer'],
    'youtube_worker': ['youtube'],
    'soundcloud_worker': ['soundcloud'],
    'telegram_worker': ['telegram'],
    'firefox': ['youtube', 'soundcloud'],
    'soundcloud-fetcher': ['soundcloud'],
}
ALL_PROFILES = {'importer', 'youtube', 'soundcloud', 'telegram'}


def _services(path):
    """Return the services mapping of a compose file."""
    return yaml.safe_load(path.read_text(encoding='utf-8'))['services']


@pytest.mark.parametrize('path', [PROD, FULL], ids=['prod', 'full'])
def test_services_sit_behind_their_profile(path):
    """Each source service has exactly its profile; every other service has none."""
    found = {name: svc.get('profiles') for name, svc in _services(path).items() if svc.get('profiles')}
    assert found == EXPECTED


def test_compose_file_format_supports_profiles():
    """Profiles need compose file format 3.9 (docker-compose v1.28+, production's v1.29)."""
    for path in (PROD, FULL):
        assert yaml.safe_load(path.read_text(encoding='utf-8'))['version'] == '3.9'


def test_test_stack_has_no_profiles():
    """core-smoke and the e2e jobs start every service of compose.test.yml, as before."""
    assert not [n for n, s in _services(TEST).items() if s.get('profiles')]


def test_overlays_do_not_add_profiles():
    """Only the base file decides; an overlay with its own profile would diverge."""
    for name in ('docker-compose.workers.yml', 'docker-compose.tools.yml', 'docker-compose.dev.yml'):
        for svc, body in _services(ROOT / 'docker' / name).items():
            assert not (body or {}).get('profiles'), f'{name}: {svc}'


def test_declared_profiles_are_the_four_sources():
    """The set the deploy guard derives from the compose file is the documented one."""
    declared = {p for svc in _services(PROD).values() for p in svc.get('profiles', [])}
    assert declared == ALL_PROFILES


def test_deploy_guard_reads_flow_style_profiles():
    """The shared parser reads `profiles: ["x"]` lines; the compose file must keep that shape."""
    text = PROD.read_text(encoding='utf-8')
    lines = re.findall(r'^ +profiles: *\[.*\]$', text, flags=re.M)
    assert len(lines) == len(EXPECTED)
    assert 'COMPOSE_PROFILES' in DEPLOY_SH.read_text(encoding='utf-8')


def test_prod_env_must_carry_compose_profiles():
    """The release pipeline fails when PROD_ENV_FILE lacks COMPOSE_PROFILES."""
    assert 'compose_profiles_value "$env_content"' in SECRETS_SH.read_text(encoding='utf-8')


def _run_secrets_check(tmp_path, env_lines):
    """Run check-required-secrets.sh with a PROD_ENV_FILE holding env_lines."""
    env = tmp_path / 'prod.env'
    env.write_text('\n'.join(env_lines) + '\n', encoding='utf-8')
    lms = tmp_path / 'lms.env'
    lms.write_text('VITE_GOOGLE_CLIENT_ID=x\n', encoding='utf-8')
    base = {
        'PATH': '/usr/bin:/bin',
        'DOCKERHUB_USERNAME': 'u',
        'DOCKERHUB_TOKEN': 't',
        'APK_HOSTER_URL': 'h',
        'SIGNING_STORE_FILE': 'f',
        'PROD_ENV_FILE': str(env),
        'PROD_ENV_FILE_LMS': str(lms),
        'PROD_REMOTE_HOST': 'prod.example.org',
        'PROD_SSH_ACCEPT_NEW_HOST_KEY': 'true',
    }
    return subprocess.run(['bash', str(SECRETS_SH)], env=base, capture_output=True, text=True, check=False)


def test_secrets_check_behaviour(tmp_path):
    """Missing COMPOSE_PROFILES fails the check; the full set passes it."""
    common = ['GOOGLE_CLIENT_ID=g', 'API_KEY=k', 'FIREFOX_PASSWORD=p', 'DOCKER_USER=u']
    bad = _run_secrets_check(tmp_path, common)
    assert bad.returncode == 1
    assert "'COMPOSE_PROFILES'" in bad.stdout
    good = _run_secrets_check(tmp_path, [*common, 'COMPOSE_PROFILES=soundcloud,youtube,telegram,importer'])
    assert good.returncode == 0, good.stdout


def test_verify_script_worker_map_matches_compose():
    """post-deploy-verify.sh maps each profile to the container name the compose file sets."""
    text = VERIFY_SH.read_text(encoding='utf-8')
    mapping = dict(entry.split(':') for entry in re.search(r'PROFILE_WORKERS="([^"]+)"', text).group(1).split())
    services = _services(PROD)
    expected = {
        profile: services[svc]['container_name']
        for svc, profiles in EXPECTED.items()
        if svc.endswith('_worker')
        for profile in profiles
    }
    assert mapping == expected


def test_dev_stack_enables_all_profiles():
    """scripts/dev.sh runs the source workers locally, so it exports the profiles."""
    text = DEV_SH.read_text(encoding='utf-8')
    assert 'COMPOSE_PROFILES' in text
    assert set(re.search(r'COMPOSE_PROFILES:-([a-z,]+)', text).group(1).split(',')) == ALL_PROFILES


def test_deploy_refuses_an_env_file_without_compose_profiles(tmp_path):
    """deploy.sh stops before touching the host when the env file has no COMPOSE_PROFILES."""
    env_file = tmp_path / 'prod.env'
    env_file.write_text('DB_DB=music-management\nDOCKER_USER=tester\n', encoding='utf-8')
    env = {
        **os.environ,
        'LOCAL_ENV_FILE': str(env_file),
        'REMOTE_HOST': '203.0.113.9',
        'REMOTE_USER': 'root',
        'DEPLOY_TARGET_NAME': 'music-management',
        'PREDEPLOY_BACKUP': '0',
    }
    result = subprocess.run(
        ['bash', str(DEPLOY_SH)], env=env, capture_output=True, text=True, cwd=tmp_path, check=False, timeout=60
    )
    assert result.returncode == 1
    assert 'no non-empty COMPOSE_PROFILES line' in result.stdout


LIB = ROOT / 'scripts' / 'lib' / 'compose_profiles.sh'
ALL = 'soundcloud,youtube,telegram,importer'


def _bash(snippet, *args):
    """Run a snippet with compose_profiles.sh sourced; return the completed process."""
    return subprocess.run(
        ['bash', '-c', f'. {LIB}; {snippet}', '_', *args], capture_output=True, text=True, check=False, timeout=60
    )


@pytest.mark.parametrize(
    'content, expected',
    [
        (f'COMPOSE_PROFILES={ALL}\n', ALL),
        (f'COMPOSE_PROFILES={ALL}\r\n', ALL),
        (f'export COMPOSE_PROFILES={ALL}\n', ALL),
        (f'   COMPOSE_PROFILES={ALL}\n', ALL),
        (f'COMPOSE_PROFILES="{ALL}"\n', ALL),
        (f"COMPOSE_PROFILES='{ALL}'\n", ALL),
        (f'COMPOSE_PROFILES={ALL} # all four\n', ALL),
        (f'COMPOSE_PROFILES=youtube\nCOMPOSE_PROFILES={ALL}\n', ALL),
        ('COMPOSE_PROFILES=\n', None),
        ('COMPOSE_PROFILES=""\n', None),
        ('COMPOSE_PROFILES= # nothing\n', None),
        ('# COMPOSE_PROFILES=youtube\n', None),
        ('OTHER=1\n', None),
        (f'COMPOSE_PROFILES={ALL}\nCOMPOSE_PROFILES=\n', None),
    ],
)
def test_shared_parser(content, expected):
    """compose_profiles_value accepts the .env spellings compose accepts and rejects empty values."""
    result = _bash('compose_profiles_value "$1"', content)
    if expected is None:
        assert result.returncode == 1
    else:
        assert (result.returncode, result.stdout) == (0, expected)


def test_disabled_services_follow_the_profile_list():
    """A service is disabled when none of its profiles is enabled; services without profiles never are."""
    text = PROD.read_text(encoding='utf-8')
    off = _bash('compose_disabled_services "$1" "$2"', text, 'importer,youtube').stdout.split()
    assert sorted(off) == ['soundcloud-fetcher', 'soundcloud_worker', 'telegram_worker']
    assert _bash('compose_disabled_services "$1" "$2"', text, ALL).stdout == ''
    assert sorted(_bash('compose_disabled_services "$1" "$2"', text, 'other').stdout.split()) == sorted(EXPECTED)


def test_deploy_skips_services_of_disabled_profiles():
    """The update loop skips the services the shared parser reports for the disabled profiles."""
    text = DEPLOY_SH.read_text(encoding='utf-8')
    assert 'case \\" $SKIP_SERVICES $PROFILE_SKIPPED_SERVICES \\" in' in text
    assert 'compose_disabled_services "$COMPOSE_CONTENT"' in text


def _run_verify_check(env_extra, sample):
    """Source post-deploy-verify.sh's check function in isolation."""
    text = VERIFY_SH.read_text(encoding='utf-8')
    start = text.index('PROFILE_WORKERS=')
    end = text.index('# restarts_increased')
    snippet = text[start:end]
    return subprocess.run(
        ['bash', '-c', f'. {LIB}; {snippet}\ncheck_profile_workers "$SAMPLE"'],
        env={'PATH': os.environ['PATH'], 'SAMPLE': sample, **env_extra},
        capture_output=True,
        text=True,
        check=False,
    )


RUNNING = ''.join(
    f'music-management|/{c}|unless-stopped|running|none|0\n'
    for c in ('muma-soundcloud-worker', 'muma-youtube-worker', 'muma-telegram-worker', 'muma-importer-worker')
)


def test_verify_check_skips_loudly_outside_the_deploy_jobs():
    """No PROD_ENV_FILE or no COMPOSE_PROFILES: SKIPPED, exit 0 locally, exit 1 in deploy:production."""
    local = _run_verify_check({}, RUNNING)
    assert local.returncode == 0 and 'SKIPPED' in local.stdout
    for job in ('deploy:production',):
        failing = _run_verify_check({'CI_JOB_NAME': job}, RUNNING)
        assert failing.returncode == 1 and 'SKIPPED' in failing.stdout
        no_key = _run_verify_check({'CI_JOB_NAME': job, 'PROD_ENV_FILE': 'OTHER=1\n'}, RUNNING)
        assert no_key.returncode == 1 and 'COMPOSE_PROFILES' in no_key.stdout


def test_verify_check_flags_a_worker_that_is_not_running():
    """A worker of an enabled profile that is exited or missing fails the check."""
    env = {'PROD_ENV_FILE': f'COMPOSE_PROFILES={ALL}\r\n'}
    assert _run_verify_check(env, RUNNING).returncode == 0
    exited = RUNNING.replace(
        '/muma-telegram-worker|unless-stopped|running', '/muma-telegram-worker|unless-stopped|exited'
    )
    result = _run_verify_check(env, exited)
    assert result.returncode == 1 and 'telegram' in result.stdout
    assert _run_verify_check({'PROD_ENV_FILE': 'COMPOSE_PROFILES=youtube\n'}, exited).returncode == 0


def test_one_off_commands_on_profiled_services_pass_the_profile():
    """run/logs/up of a profiled service names its profile, or compose says the service does not exist."""
    telegram = (ROOT / 'run_telegram_auth.sh').read_text(encoding='utf-8')
    assert '--profile telegram run --rm' in telegram
    assert '--profile telegram up -d telegram_worker' in telegram
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert '--profile importer logs -f importer_worker' in readme
    for profile in ALL_PROFILES:
        assert f'--profile {profile}' in readme
    assert '--profile soundcloud run --rm soundcloud-fetcher' in (ROOT / 'docs' / 'self-hosting.md').read_text(
        encoding='utf-8'
    )


@pytest.mark.parametrize(
    'path', [PROD, FULL, ROOT / 'docker' / 'docker-compose.tools.yml'], ids=['prod', 'full', 'tools']
)
def test_firefox_port_is_loopback_by_default(path):
    """The browser's noVNC port listens on 127.0.0.1 unless FIREFOX_BIND_ADDRESS says otherwise."""
    ports = _services(path)['firefox']['ports']
    assert ports == ['${FIREFOX_BIND_ADDRESS:-127.0.0.1}:7003:5800']
