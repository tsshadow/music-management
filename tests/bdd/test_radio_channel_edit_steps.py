"""Steps for features/radio_channel_edit.feature.

The feature file is the description; this is only what the steps do.

Started by scripts/test/core-e2e.sh, which brings the stack up. Without it these
skip.
"""

from __future__ import annotations

import pytest
import requests
from pytest_bdd import scenarios, then, when

pytestmark = pytest.mark.e2e

scenarios('features/radio_channel_edit.feature')

TIMEOUT = 10

# Its own slug, so nothing here touches the seeded `main` channel the radio
# scheduler is filling.
SLUG = 'e2e-proxy-verbs'
NAME = 'Proxy verbs'
RENAMED = 'Proxy verbs, renamed'


def _channels_url(lms: str) -> str:
    # Through LMS, not to music-manager directly: the proxy is the thing under
    # test, and a call straight to the manager would pass with the proxy broken.
    return f'{lms}/muma/api/radio/channels'


def _list_channels(lms: str, api_key: str) -> list[dict]:
    response = requests.get(_channels_url(lms), headers={'X-API-Key': api_key}, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    return response.json().get('channels', [])


def _channel(lms: str, api_key: str) -> dict | None:
    return next((c for c in _list_channels(lms, api_key) if c.get('slug') == SLUG), None)


@when('a radio channel is created through the LMS proxy')
def _create(lms, api_key, context):
    context['response'] = requests.post(
        _channels_url(lms),
        headers={'X-API-Key': api_key},
        json={'slug': SLUG, 'name': NAME},
        timeout=TIMEOUT,
    )


@then('the proxy answers that the channel was created')
def _created(context):
    response = context['response']
    assert response.status_code == 201, f'{response.status_code}: {response.text}'
    assert response.json().get('slug') == SLUG, response.text


@when('the channel is renamed through the LMS proxy')
def _rename(lms, api_key, context):
    context['response'] = requests.put(
        f'{_channels_url(lms)}/{SLUG}',
        headers={'X-API-Key': api_key},
        json={'name': RENAMED},
        timeout=TIMEOUT,
    )


@then('the proxy answers with the renamed channel')
def _renamed(context):
    response = context['response']
    # 405 is the failure this scenario exists for: the route takes PUT, and a
    # proxy that turns it into a POST gets "method not allowed" from FastAPI.
    assert response.status_code != 405, f'the proxy forwarded the PUT as something else: {response.text}'
    assert response.status_code == 200, f'{response.status_code}: {response.text}'
    assert response.json().get('name') == RENAMED, response.text


@then('the channel reads back under its new name')
def _reads_back_renamed(lms, api_key):
    channel = _channel(lms, api_key)
    assert channel is not None, 'the channel is missing from the line-up'
    assert channel.get('name') == RENAMED, f'the rename did not land: {channel!r}'


@when('the channel is removed through the LMS proxy')
def _remove(lms, api_key, context):
    context['response'] = requests.delete(
        f'{_channels_url(lms)}/{SLUG}',
        headers={'X-API-Key': api_key},
        timeout=TIMEOUT,
    )


@then('the proxy answers that the channel is gone')
def _removed(context):
    response = context['response']
    assert response.status_code != 405, f'the proxy forwarded the DELETE as something else: {response.text}'
    assert response.status_code == 200, f'{response.status_code}: {response.text}'
    assert response.json().get('deleted') == SLUG, response.text


@then('the channel no longer reads back')
def _no_longer_reads_back(lms, api_key):
    assert _channel(lms, api_key) is None, 'the channel is still in the line-up after its DELETE'
