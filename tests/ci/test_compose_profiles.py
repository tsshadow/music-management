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
    """deploy.sh greps `profiles: ["x"]` lines; the compose file must keep that shape."""
    text = PROD.read_text(encoding='utf-8')
    lines = re.findall(r'^ +profiles: *\[.*\]$', text, flags=re.M)
    assert len(lines) == len(EXPECTED)
    assert 'COMPOSE_PROFILES' in DEPLOY_SH.read_text(encoding='utf-8')


def test_prod_env_must_carry_compose_profiles():
    """The release pipeline fails when PROD_ENV_FILE lacks COMPOSE_PROFILES."""
    assert 'require_key "$env_content" "COMPOSE_PROFILES" "PROD_ENV_FILE"' in SECRETS_SH.read_text(encoding='utf-8')


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
    }
    return subprocess.run(['bash', str(SECRETS_SH)], env=base, capture_output=True, text=True, check=False)


def test_secrets_check_behaviour(tmp_path):
    """Missing COMPOSE_PROFILES fails the check; the full set passes it."""
    common = ['GOOGLE_CLIENT_ID=g', 'API_KEY=k', 'FIREFOX_PASSWORD=p']
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
    env_file.write_text('DB_DB=music-management\n', encoding='utf-8')
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
    assert 'no COMPOSE_PROFILES line' in result.stdout
