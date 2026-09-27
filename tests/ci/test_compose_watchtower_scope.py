"""Watchtower may update only the downloader images (issue #68, bug report 050).

The production Watchtower (a Portainer stack outside this repository) ran with
WATCHTOWER_LABEL_ENABLE=false, so it updated every container with a newer image each night at
04:30 -- music-manager and LMS included -- bypassing the deploy and its migrations. An explicit
`enable: "false"` is honoured even when label filtering is off, and `enable: "true"` on the
downloader images keeps them updating once LABEL_ENABLE is switched to true.
"""

from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[2] / 'docker' / 'docker-compose.yml'
LABEL = 'com.centurylinklabs.watchtower.enable'
UPDATED_BY_WATCHTOWER = {'importer_worker', 'youtube_worker', 'soundcloud_worker', 'telegram_worker'}


def _services():
    return yaml.safe_load(COMPOSE.read_text(encoding='utf-8'))['services']


def test_only_the_downloader_images_opt_in():
    opted_in = {name for name, svc in _services().items() if (svc.get('labels') or {}).get(LABEL) == 'true'}
    assert opted_in == UPDATED_BY_WATCHTOWER


def test_every_other_service_opts_out_explicitly():
    missing = [
        name
        for name, svc in _services().items()
        if name not in UPDATED_BY_WATCHTOWER and (svc.get('labels') or {}).get(LABEL) != 'false'
    ]
    assert missing == [], f'services without an explicit Watchtower opt-out: {missing}'


LMS_COMPOSE = Path(__file__).resolve().parents[2] / 'services' / 'music-management-server' / 'docker-compose.yml'


def test_the_lms_stack_opts_out_entirely():
    services = yaml.safe_load(LMS_COMPOSE.read_text(encoding='utf-8'))['services']
    missing = [name for name, svc in services.items() if (svc.get('labels') or {}).get(LABEL) != 'false']
    assert missing == [], f'LMS stack services without a Watchtower opt-out: {missing}'
