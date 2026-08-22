"""Steps for features/access_control.feature.

The feature file is the description; this is only what the steps do.

Started by scripts/test/core-e2e.sh, which brings the stack up. Without it these
skip.
"""
from __future__ import annotations

import pytest
import requests
from pytest_bdd import parsers, scenarios, then, when

pytestmark = pytest.mark.e2e

scenarios('features/access_control.feature')

TIMEOUT = 10

# Header for each spelling in the feature's Examples table. None means the header
# is not sent at all, which requests distinguishes from sending it empty -- and
# so does the handler: one is "no key", the other is a key that is the empty
# string, and both have to be refused.
CREDENTIALS = {
    'with no API key at all': None,
    'with an invalid key': 'not-the-key-4d6f6a6f',
    'with an empty key': '',
}


def _ask_for_tracks(manager: str, key: str | None) -> requests.Response:
    headers = {} if key is None else {'x-api-key': key}
    return requests.get(
        f'{manager}/api/library/tracks',
        headers=headers,
        params={'limit': 1},
        timeout=TIMEOUT,
    )


@when(parsers.parse('the library is asked for its tracks {credentials}'))
def _ask_with(manager, api_key, credentials, context):
    # The control row names the real key rather than carrying it in the table:
    # a feature file is documentation, and a credential in it is a credential in
    # the repository.
    key = api_key if credentials == 'with the system API key' else CREDENTIALS[credentials]
    context['response'] = _ask_for_tracks(manager, key)


@then('the request is refused as unauthenticated')
def _refused(context):
    # 401 specifically, not "an error". A 500 from a database that never came up
    # would also keep the data in, and would also be a broken stack rather than a
    # working lock.
    response = context['response']
    assert response.status_code == 401, (
        f'expected 401, got {response.status_code}: {response.text[:200]}'
    )


@then('no track data comes back')
def _no_data(context):
    # The status code is not the whole story: a handler that refuses and then
    # serialises the rows anyway is a leak with a 401 on it.
    body = context['response'].text
    assert 'file_path' not in body and 'ci-test-track' not in body, (
        f'a refused request still returned track data: {body[:300]}'
    )


@then('the tracks come back')
def _tracks_come_back(context):
    response = context['response']
    assert response.status_code == 200, (
        f'the key the rest of the suite authenticates with was refused: '
        f'{response.status_code} {response.text[:200]}'
    )
    body = response.json()
    assert isinstance(body, (list, dict)), body
