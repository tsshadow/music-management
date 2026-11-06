"""Every endpoint's SQL is run against a real MariaDB.

The unit suite mocks the cursor, so it proves the right SQL string is handed
over with the right parameters -- not that MariaDB accepts it. A typo in a
column name, a table that the schema bootstrap never creates, or a query that
outgrew its migration all pass the unit tests and fail in production. This is
where they fail instead.

The list below is deliberately exhaustive for GET endpoints: adding a new read
endpoint without adding it here is the only way to reintroduce that gap.
"""

import hashlib
import json
import threading
import time
from datetime import date, timedelta
from unittest.mock import patch

import pymysql
import pytest

from tests.integration.conftest import _connect, run_sql

pytestmark = pytest.mark.integration

# (method, path) for every endpoint that reads from the database and needs no
# request body. Against an empty-but-valid schema each must answer 2xx or a
# deliberate 4xx -- never a 500, which is what invalid SQL produces.
READ_ENDPOINTS = [
    ('/api/radio/stations', 200),
    ('/api/radio/stations?include_disabled=true', 200),
    ('/api/users', 200),
    ('/api/import-conflicts', 200),
    # The LMS listen reconcile's status is process state; its dry run needs an lms.db and is
    # exercised by ScrobbleReconcileSqlTest below and tests/integration/test_scrobble_reconcile.py.
    ('/api/scrobble/reconcile/lms/status', 200),
    ('/api/users/roles', 200),
    ('/api/users/permissions', 200),
    ('/api/users/1/dynamic-playlists', 200),
    ('/api/users/1/identities', 200),
    ('/api/users/1/listenbrainz', 200),
    ('/api/users/1/settings/ultrasonic', 200),
    ('/api/auth/setup-status', 200),
    ('/api/auth/verify', 200),
    # The system key is nobody, so it has no Subsonic token of its own (bug report 103).
    ('/api/auth/subsonic-token', 403),
    ('/api/library/tracks', 200),
    ('/api/library/advanced', 200),
    # Paging is validated before any SQL runs: page 0 was a negative OFFSET (a 500).
    ('/api/library/tracks?page=0', 422),
    ('/api/library/tracks?limit=501', 422),
    ('/api/library/advanced?page=0', 422),
    # Form and the effective year (docs/designs/track-form/): both reach the SQL, and a form
    # outside the closed set is refused before any runs.
    ('/api/library/advanced?form=liveset&form=set&year_min=2012&year_max=2012', 200),
    ('/api/library/advanced?form=mixtape', 422),
    ('/api/analytics/summary?form=podcast&year_min=2010', 200),
    ('/api/analytics/year-histogram?form=liveset', 200),
    ('/api/library/genres', 200),
    # Browse by BPM (docs/designs/bpm-browse/): the index query and the page details.
    # BpmBrowseSqlTest below seeds every BPM source.
    ('/api/library/bpm/histogram', 200),
    ('/api/library/bpm/tracks?bpm=150', 200),
    ('/api/library/bpm/tracks?bpm_from=140&bpm_to=160&min_confidence=medium&genre=Hardstyle', 200),
    ('/api/library/bpm/tracks', 400),
    # A file MuMa never scanned is a deliberate 404, never a 500.
    ('/api/library/tracks/by-path?path=nope.mp3', 404),
    ('/api/rules', 200),
    ('/api/rules/genres', 200),
    ('/api/rules/genres/summary', 200),
    ('/api/rules/artists', 200),
    ('/api/rules/artists?state=white', 200),
    ('/api/rules/artists?state=all&q=a&proposal=reject&sort=name', 200),
    ('/api/rules/artists/summary', 200),
    ('/api/rules/artists/redirects/issues', 200),
    # The scheduled evidence run's review list and ledger (artist_auto_approve_worker).
    ('/api/rules/artists?state=white&decided_by=auto-external&sort=decided', 200),
    ('/api/rules/artists/auto-approve/runs', 200),
    ('/api/rules/festivals', 200),
    ('/api/curation/labels', 200),
    ('/api/curation/labels?q=a', 200),
    ('/api/rules/lineups', 200),
    ('/api/rules/artist-genres', 200),
    ('/api/curation/genres', 200),
    ('/api/curation/genres?q=hard', 200),
    ('/api/rules/label-genres', 200),
    ('/api/rules/artist-redirects', 200),
    ('/api/tagger/retag/pending', 200),
    # The `__TODO` label repair's dry run pages tagger_processed_files by primary key.
    ('/api/tagger/todo-label-repair', 200),
    ('/api/artists?q=anger', 200),
    ('/api/labels?q=scan', 200),
    ('/api/system/activity', 200),
    ('/api/soundcloud', 200),
    ('/api/youtube', 200),
    # Four statements each over the downloader tables, including the archive
    # timestamp the YouTube table only has since migrate_v31.
    ('/api/downloaders/coverage/soundcloud', 200),
    ('/api/downloaders/coverage/youtube', 200),
    # Deprecated; reads downloads_account_checks through the downloader's own connector.
    ('/api/downloaders/schedule/soundcloud', 200),
    ('/api/channel-links/proposals', 200),
    ('/api/channel-links/proposals?status=rejected&kind=artist', 200),
    ('/api/channel-links/proposals?status=maybe', 400),
    ('/api/channel-links/channels?q=x', 200),
    ('/api/channel-links/targets?kind=label&q=x', 200),
    ('/api/channel-links/targets?kind=artist&q=x', 200),
    ('/api/channel-links/targets?kind=genre&q=x', 400),
    ('/api/channel-links/by-label?name=x', 200),
    ('/api/artists/search', 200),
    ('/api/artists/search-all', 200),
    ('/api/artists/images/stats', 200),
    ('/api/artists/manage/search', 200),
    ('/api/artists/1/images', 404),
    ('/api/scrobble/import/latest', 200),
    ('/api/events', 200),
    ('/api/events?level=ERROR&source=importer&since=-1h&q=test', 200),
    ('/api/stats/', 200),
    ('/api/analytics/summary', 200),
    ('/api/analytics/genre-distribution', 200),
    ('/api/analytics/bpm-histogram', 200),
    ('/api/analytics/year-histogram', 200),
    ('/api/analytics/top-artists', 200),
    ('/api/analytics/top-labels', 200),
    ('/api/analytics/artist-search?q=anger', 200),
    ('/api/listening/summary', 200),
    ('/api/listening/summary?from=2024-01-01&to=2026-12-31&tz=Europe/Amsterdam', 200),
    ('/api/listening/timeline?bucket=day', 200),
    ('/api/listening/timeline?bucket=week', 200),
    ('/api/listening/timeline?bucket=month', 200),
    ('/api/listening/clock', 200),
    ('/api/listening/sources', 200),
    ('/api/listening/top-tracks', 200),
    ('/api/listening/top-artists', 200),
    ('/api/listening/top-labels', 200),
    ('/api/listening/top-genres', 200),
    ('/api/listening/top-genres?limit=500&genre=Hardstyle', 200),
    ('/api/listening/years', 200),
    ('/api/listening/years?year=unknown&year=2015&year_from=2018&year_to=2020', 200),
    ('/api/listening/summary?genre=Hardstyle&genre=Uptempo+Hardcore&year_from=2015&year_to=2019', 200),
    ('/api/listening/timeline?bucket=week&genre=Hardstyle&year=unknown', 200),
    ('/api/listening/clock?year_from=2015', 200),
    ('/api/listening/sources?year_to=2019&genre=Hardstyle', 200),
    ('/api/listening/top-tracks?genre=Hardstyle&year=2019', 200),
    ('/api/listening/top-artists?genre=Hardstyle&year_from=2015&year_to=2019', 200),
    ('/api/listening/top-labels?genre=Hardstyle&year=unknown', 200),
    ('/api/listening/summary?year=abc', 400),
    ('/api/user-requests', 200),
    # News bulletins. Nothing recorded yet is a deliberate 404 for the latest and
    # for a stream, never a 500.
    ('/api/news/sources', 200),
    ('/api/news/bulletins', 200),
    ('/api/news/bulletins?source=nos&limit=5', 200),
    ('/api/news/bulletins/latest', 404),
    ('/api/news/bulletins/1/stream', 404),
    # The curation edit pages. An artist or label the library has never seen reads
    # back as a row of nulls rather than a 404: the rule tables are free text, so a
    # rule may legitimately be written before the first matching file arrives.
    ('/api/curation/artists/Angerfist', 200),
    ('/api/curation/labels/Scantraxx', 200),
    # The catalogue is read off files, so a label with none is a 404 rather than a
    # row of nulls; the seeded label below proves the join.
    ('/api/curation/labels/Scantraxx/catalog', 404),
    ('/api/curation/genres/Hardcore', 404),
    ('/api/curation/genre-hierarchy/cycles', 200),
    # The feeds surface. `headers` authenticates as the system key, which
    # `_resolve_username` in routers/feeds.py refuses without an explicit
    # `username` -- so the bare paths are a deliberate 400, not a miss. With a
    # username, `GET /api/feeds/{slug}` still answers 200 against an empty
    # schema: build_feed's cold-start gate reports `not_enough_data` before it
    # ever runs the candidate query, so this alone proves only that the
    # profile queries parse. FeedsPipelineTest below is what exercises the
    # candidate query, the dominant-genre queries and the rating join.
    ('/api/feeds', 200),
    ('/api/feeds/profile', 400),
    ('/api/feeds/profile?username=root', 200),
    ('/api/feeds/release-radar', 400),
    ('/api/feeds/release-radar?username=root', 200),
    ('/api/feeds/daily-mix', 400),
    ('/api/feeds/daily-mix?username=root', 200),
    # A spectrum mix and the listing for a named listener also run params_key's
    # genre-hardness digest (CRC32 over rules_genres) before the snapshot read.
    ('/api/feeds?username=root', 200),
    ('/api/feeds/daily-mix-hard?username=root', 200),
    # "Oude hitjes" (docs/designs/old-hits-feed/): its own builder and queries, not the ranker's.
    # OldHitsPipelineTest below seeds enough to run every one of them.
    ('/api/feeds/old-hits', 400),
    ('/api/feeds/old-hits?username=root', 200),
    # The Versions page in Beheer (docs/designs/song-versions/): the list, its sorts and
    # filter, the ranking status, and a song that does not exist.
    ('/api/songs/curation', 200),
    ('/api/songs/curation?q=fist&sort=changed&changed_only=true&page=2&page_size=10', 200),
    ('/api/songs/curation?sort=title', 200),
    ('/api/songs/ranking', 200),
    ('/api/songs/999999', 404),
]


@pytest.mark.parametrize(('path', 'expected'), READ_ENDPOINTS)
def test_a_read_endpoint_runs_its_sql_against_a_real_schema(api, headers, path, expected):
    response = api.get(path, headers=headers)
    assert response.status_code != 500, f'{path} -> 500: {response.text[:400]}'
    assert response.status_code == expected, f'{path} -> {response.status_code}: {response.text[:200]}'


class CurationEditPagesTest:
    """The artist, label and genre edit pages, against the real schema.

    Every write here goes through SQL the unit suite only ever saw as a string.
    `created_by`, `library_labels.mbid` and `label_external_ids` all arrived in
    migrate_v13, so these also prove that migration reached the running schema.
    """

    def _white_genre(self, db, name='Hardcore'):
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO rules_genres (name, normalized_name, state) VALUES (%s, %s, 'white')", (name, name.lower())
            )
            return cursor.lastrowid

    def test_an_artist_rule_is_written_read_back_and_removed(self, api, headers, db):
        genre_id = self._white_genre(db)
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_artists (name, normalized_name) VALUES ('Angerfist', 'angerfist')")

        added = api.post('/api/curation/artists/Angerfist/genres', headers=headers, json={'genre_id': genre_id})
        assert added.status_code == 200, added.text

        page = api.get('/api/curation/artists/Angerfist', headers=headers).json()
        assert [rule['name'] for rule in page['genre_rules']] == ['Hardcore']
        assert page['genre_rules'][0]['created_by'] == 'system'

        removed = api.delete(f'/api/curation/artists/Angerfist/genres/{genre_id}', headers=headers)
        assert removed.status_code == 200, removed.text
        assert api.get('/api/curation/artists/Angerfist', headers=headers).json()['genre_rules'] == []

    def test_a_rule_cannot_point_at_a_genre_curation_rejected(self, api, headers, db):
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO rules_genres (name, normalized_name, state) VALUES ('Arts', 'arts', 'black')")
            rejected = cursor.lastrowid
        refused = api.post('/api/curation/artists/Angerfist/genres', headers=headers, json={'genre_id': rejected})
        assert refused.status_code == 400, refused.text

    def test_an_mbid_lands_in_both_places_it_is_stored(self, api, headers, db):
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_artists (name, normalized_name) VALUES ('Angerfist', 'angerfist')")
        mbid = '5b11f4ce-a62d-471e-81fc-a69a8278c7da'

        saved = api.put('/api/curation/artists/Angerfist/mbid', headers=headers, json={'mbid': mbid})
        assert saved.status_code == 200, saved.text

        page = api.get('/api/curation/artists/Angerfist', headers=headers).json()
        assert page['mbid'] == mbid
        assert [row['source'] for row in page['external_ids']] == ['musicbrainz']

        cleared = api.put('/api/curation/artists/Angerfist/mbid', headers=headers, json={'mbid': None})
        assert cleared.status_code == 200, cleared.text
        page = api.get('/api/curation/artists/Angerfist', headers=headers).json()
        assert page['mbid'] is None
        assert page['external_ids'] == []

    def test_a_label_carries_an_mbid_a_parent_and_a_catalogue_prefix(self, api, headers, db):
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_labels (name) VALUES ('Roughstate')")
            parent_id = cursor.lastrowid
            cursor.execute("INSERT INTO library_labels (name) VALUES ('Minus Is More')")

        assert (
            api.put(
                '/api/curation/labels/Minus Is More/parent', headers=headers, json={'parent_label_id': parent_id}
            ).status_code
            == 200
        )
        assert (
            api.post('/api/curation/labels/Minus Is More/catids', headers=headers, json={'catid': 'mim'}).status_code
            == 200
        )

        page = api.get('/api/curation/labels/Minus Is More', headers=headers).json()
        assert page['parent_label_name'] == 'Roughstate'
        assert page['catids'] == ['MIM']

    def test_a_label_catalogue_is_read_off_the_files_that_carry_it(self, api, headers, db):
        # The join in GET /labels/{name}/catalog is the only SQL the unit suite never
        # ran for real: label -> track labels -> media files.
        # Number 5 has no label link -- the scanner has not linked half the EPs tree
        # -- so it must come in through the path query.
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_labels (name) VALUES ('Dirty Workz')")
            label_id = cursor.lastrowid
            for number, linked in ((1, True), (2, True), (4, True), (5, False)):
                cursor.execute("INSERT INTO library_tracks (title) VALUES (%s)", (f'Track {number}',))
                track_id = cursor.lastrowid
                if linked:
                    cursor.execute(
                        'INSERT INTO library_track_labels (track_id, label_id) VALUES (%s, %s)', (track_id, label_id)
                    )
                cursor.execute(
                    'INSERT INTO library_media_files (file_path, file_path_hash, track_id) VALUES (%s, %s, %s)',
                    (f'/mnt/music/EPs/Dirty Workz/DWX{number:04d} Release/01.mp3', f'dwx-{number}', track_id),
                )

        # Imported here, not at module level: the router module builds the tagger on
        # import, which wants a database before the fixtures have provided one.
        from services.music_manager.routers import curation as curation_router

        with patch.object(curation_router, 'Settings') as settings:
            settings.return_value.eps_folder_path = '/mnt/music/EPs'
            settings.return_value.delimiter = '/'
            page = api.get('/api/curation/labels/Dirty Workz/catalog', headers=headers)
        assert page.status_code == 200, page.text
        body = page.json()
        assert body['files_considered'] == 4
        assert [(s['prefix'], s['min'], s['max'], s['absent']) for s in body['series']] == [('DWX', 1, 5, [3])]

    def test_a_label_cannot_be_its_own_parent(self, api, headers, db):
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_labels (name) VALUES ('Scantraxx')")
            label_id = cursor.lastrowid
        refused = api.put('/api/curation/labels/Scantraxx/parent', headers=headers, json={'parent_label_id': label_id})
        assert refused.status_code == 400, refused.text

    def test_a_genre_hierarchy_is_replaced_not_merged(self, api, headers, db):
        self._white_genre(db, 'Hardcore')
        self._white_genre(db, 'Terror')
        self._white_genre(db, 'Industrial Hardcore')

        first = api.put(
            '/api/curation/genres/Industrial Hardcore/parents',
            headers=headers,
            json={'parents': ['Hardcore', 'Terror']},
        )
        assert first.status_code == 200, first.text
        assert sorted(api.get('/api/curation/genres/Industrial Hardcore', headers=headers).json()['parents']) == [
            'Hardcore',
            'Terror',
        ]

        second = api.put(
            '/api/curation/genres/Industrial Hardcore/parents', headers=headers, json={'parents': ['Hardcore']}
        )
        assert second.status_code == 200, second.text
        page = api.get('/api/curation/genres/Industrial Hardcore', headers=headers).json()
        assert page['parents'] == ['Hardcore']
        assert api.get('/api/curation/genres/Hardcore', headers=headers).json()['children'] == ['Industrial Hardcore']

    def test_a_genre_hierarchy_refuses_a_cycle(self, api, headers, db):
        self._white_genre(db, 'Hardcore')
        self._white_genre(db, 'Uptempo')
        self._white_genre(db, 'Upterror')
        assert (
            api.put('/api/curation/genres/Uptempo/parents', headers=headers, json={'parents': ['Hardcore']}).status_code
            == 200
        )
        assert (
            api.put('/api/curation/genres/Upterror/parents', headers=headers, json={'parents': ['Uptempo']}).status_code
            == 200
        )

        refused = api.put('/api/curation/genres/Hardcore/parents', headers=headers, json={'parents': ['Upterror']})
        assert refused.status_code == 409, refused.text
        assert refused.json()['detail'] == 'Hardcore is already an ancestor of Upterror'
        assert api.get('/api/curation/genres/Hardcore', headers=headers).json()['descendants'] == [
            'Uptempo',
            'Upterror',
        ]
        assert api.get('/api/curation/genre-hierarchy/cycles', headers=headers).json() == {'count': 0, 'cycles': []}

    def test_the_cycle_check_reports_a_stored_cycle(self, api, headers, db):
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO rules_subgenre_hierarchy (subgenre, genre) VALUES ('Uptempo', 'Terror'), ('Terror', 'Uptempo')"
            )
        report = api.get('/api/curation/genre-hierarchy/cycles', headers=headers).json()
        assert report == {'count': 1, 'cycles': [['Terror', 'Uptempo']]}

    def test_a_rejected_genre_has_no_hierarchy_to_edit(self, api, headers, db):
        self._white_genre(db, 'Hardcore')
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO rules_genres (name, normalized_name, state) VALUES ('Arts', 'arts', 'black')")
        refused = api.put('/api/curation/genres/Arts/parents', headers=headers, json={'parents': ['Hardcore']})
        assert refused.status_code == 403, refused.text


class UserLifecycleTest:
    """Create, log in, change, delete -- the whole flow against real tables."""

    def test_the_first_admin_can_be_created_and_then_log_in(self, api, db):
        setup = api.post('/api/auth/setup', json={'username': 'root', 'display_name': 'Root', 'password': 'hunter2'})
        assert setup.status_code == 200, setup.text
        assert setup.json()['is_admin'] is True

        assert api.get('/api/auth/setup-status').json()['setup_required'] is False

        login = api.post('/api/auth/login', json={'username': 'root', 'password': 'hunter2'})
        assert login.status_code == 200, login.text
        body = login.json()
        assert body['user']['username'] == 'root'
        assert body['user']['is_admin'] is True
        assert body['api_key'] and body['refresh_token']

    def test_a_case_variant_login_answers_with_the_accounts_own_spelling(self, api, db):
        """Bug report 074: the LOWER() lookup against the real table, and the name that goes back."""
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        login = api.post('/api/auth/login', json={'username': 'ROOT', 'password': 'hunter2'})
        assert login.status_code == 200, login.text
        assert login.json()['user']['username'] == 'root'

    def test_a_case_variant_of_an_existing_account_cannot_be_created(self, api, headers, db):
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        created = api.post('/api/users', headers=headers, json={'username': 'Root'})
        assert created.status_code == 409, created.text

    def test_a_relayed_scrobble_is_stored_under_the_accounts_own_spelling(self, api, headers, db):
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        sent = api.post(
            '/api/scrobble/event',
            headers=headers,
            json={'artist_name': 'Nobody', 'track_title': 'Nothing', 'username': 'Root', 'listened_at': 1758780000},
        )
        assert sent.status_code == 200, sent.text
        rows = run_sql(db, 'SELECT username FROM scrobble_unmatched_listens')
        assert [row['username'] for row in rows] == ['root']

    def test_a_refresh_token_issued_at_login_is_accepted(self, api, db):
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        refresh_token = api.post('/api/auth/login', json={'username': 'root', 'password': 'hunter2'}).json()[
            'refresh_token'
        ]
        refreshed = api.post('/api/auth/refresh', json={'refresh_token': refresh_token})
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()['user']['username'] == 'root'

    def test_a_users_own_api_key_authenticates_it(self, api, db):
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        api_key = api.post('/api/auth/login', json={'username': 'root', 'password': 'hunter2'}).json()['api_key']
        verify = api.get('/api/auth/verify', headers={'x-api-key': api_key})
        assert verify.status_code == 200, verify.text
        assert verify.json()['user']['role_name'] == 'admin'

    def test_a_second_user_can_be_created_and_deleted(self, api, headers, db):
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        created = api.post('/api/users', headers=headers, json={'username': 'user'})
        assert created.status_code == 200, created.text
        user_id = created.json()['id']

        listed = api.get('/api/users', headers=headers).json()
        assert {row['username'] for row in listed} == {'root', 'user'}

        deleted = api.delete(f'/api/users/{user_id}', headers=headers)
        assert deleted.status_code == 200, deleted.text
        assert {row['username'] for row in api.get('/api/users', headers=headers).json()} == {'root'}

    def test_approving_a_google_request_whose_email_is_taken_is_a_409(self, api, headers, db):
        """The e-mail becomes the username; an account already carrying it, in any case,
        used to hit the unique index and answer a 500 (bug report 079)."""
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        assert api.post('/api/users', headers=headers, json={'username': 'User@Example.com'}).status_code == 200
        run_sql(
            db,
            "INSERT INTO user_requests (google_subject, email, display_name, status) "
            "VALUES ('google-sub-1', 'user@example.com', 'Teun', 'pending')",
        )
        request_id = run_sql(db, "SELECT id FROM user_requests WHERE google_subject = 'google-sub-1'")[0]['id']

        approved = api.post(f'/api/user-requests/{request_id}/approve', headers=headers, json={})

        assert approved.status_code == 409, approved.text
        pending = run_sql(db, 'SELECT status FROM user_requests WHERE id = %s', (request_id,))
        assert pending[0]['status'] == 'pending'

    def test_the_last_admin_is_protected(self, api, headers, db):
        setup = api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        admin_id = setup.json()['id']
        refused = api.delete(f'/api/users/{admin_id}', headers=headers)
        assert refused.status_code == 409
        assert 'beheerder' in refused.json()['detail']

    def _plain_account_key(self, api, headers):
        """Sets up `root` (admin) and `user` (plain user) and returns user's own API key."""
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        created = api.post('/api/users', headers=headers, json={'username': 'user', 'password': 'hunter2-user'})
        assert created.status_code == 200, created.text
        login = api.post('/api/auth/login', json={'username': 'user', 'password': 'hunter2-user'})
        assert login.status_code == 200, login.text
        return created.json()['id'], login.json()['api_key']

    def test_a_plain_account_cannot_delete_itself(self, api, headers, db):
        """Issue #38: deleting an account takes `users.update`, also for one's own."""
        user_id, key = self._plain_account_key(api, headers)
        refused = api.delete(f'/api/users/{user_id}', headers={'x-api-key': key})
        assert refused.status_code == 403, refused.text
        assert run_sql(db, 'SELECT id FROM users WHERE id = %s', (user_id,))

    def test_a_plain_account_lists_only_its_own_imports(self, api, headers, db):
        """Issue #38: the scoped query runs on MariaDB, and an admin key still sees every row."""
        _, key = self._plain_account_key(api, headers)
        run_sql(
            db,
            'INSERT INTO scrobble_imports (username, lb_username, status) VALUES '
            "('user', 'user-lb', 'completed'), ('root', 'root-lb', 'failed')",
        )
        own = api.get('/api/scrobble/import/latest', headers={'x-api-key': key})
        assert own.status_code == 200, own.text
        assert [row['username'] for row in own.json()] == ['user']
        everyone = api.get('/api/scrobble/import/latest', headers=headers)
        assert {row['username'] for row in everyone.json()} == {'user', 'root'}

    def test_the_last_enabled_admin_cannot_be_demoted_or_disabled(self, api, headers, db):
        admin_id = api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'}).json()['id']
        demoted = api.put(f'/api/users/{admin_id}/role', headers=headers, json={'role': 'user'})
        assert demoted.status_code == 409, demoted.text
        disabled = api.post(f'/api/users/{admin_id}/disable', headers=headers)
        assert disabled.status_code == 409, disabled.text

        # A second, enabled admin lifts the guard: the SQL counts the others, enabled only.
        second = api.post('/api/users', headers=headers, json={'username': 'user'}).json()['id']
        api.put(f'/api/users/{second}/role', headers=headers, json={'role': 'admin'})
        assert api.post(f'/api/users/{admin_id}/disable', headers=headers).status_code == 200
        # ...and now `user` is the last enabled one, root being disabled.
        assert api.put(f'/api/users/{second}/role', headers=headers, json={'role': 'user'}).status_code == 409

    def test_setup_runs_once_and_its_guarded_insert_is_accepted(self, api, db):
        assert api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'}).status_code == 200
        again = api.post('/api/auth/setup', json={'username': 'other', 'password': 'hunter2'})
        assert again.status_code == 409, again.text
        assert run_sql(db, 'SELECT COUNT(*) AS n FROM users')[0]['n'] == 1

    def test_logins_keep_only_the_newest_refresh_tokens(self, api, db):
        from services.music_manager import rbac

        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        tokens = [
            api.post('/api/auth/login', json={'username': 'root', 'password': 'hunter2'}).json()['refresh_token']
            for _ in range(rbac.REFRESH_TOKENS_PER_USER + 3)
        ]
        stored = [row['token'] for row in run_sql(db, 'SELECT token FROM user_refresh_tokens ORDER BY id')]
        assert stored == tokens[-rbac.REFRESH_TOKENS_PER_USER :]

    def test_the_daily_purge_caps_every_account_and_drops_old_revoked_rows(self, api, db):
        from services.music_manager import rbac

        root_id = api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'}).json()['id']
        for n in range(rbac.REFRESH_TOKENS_PER_USER + 5):
            run_sql(db, 'INSERT INTO user_refresh_tokens (user_id, token) VALUES (%s, %s)', (root_id, f'bulk-{n}'))
        run_sql(
            db,
            'UPDATE user_refresh_tokens SET revoked_at = NOW() - INTERVAL 40 DAY WHERE token = %s',
            (f'bulk-{rbac.REFRESH_TOKENS_PER_USER + 4}',),
        )
        rbac.purge_refresh_tokens(db)
        stored = [row['token'] for row in run_sql(db, 'SELECT token FROM user_refresh_tokens ORDER BY id')]
        assert stored == [f'bulk-{n}' for n in range(5, rbac.REFRESH_TOKENS_PER_USER + 4)]

    def test_a_role_can_be_assigned_and_is_reflected_in_the_permissions(self, api, headers, db):
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        user_id = api.post('/api/users', headers=headers, json={'username': 'user'}).json()['id']

        assigned = api.put(f'/api/users/{user_id}/role', headers=headers, json={'role': 'admin'})
        assert assigned.status_code == 200, assigned.text

        api.post(f'/api/users/{user_id}/password', headers=headers, json={'password': 'pw'})
        login = api.post('/api/auth/login', json={'username': 'user', 'password': 'pw'})
        assert login.json()['user']['role_name'] == 'admin'
        assert 'users.assign-role' in login.json()['user']['permissions']

    def test_app_settings_round_trip(self, api, headers, db):
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        stored = api.post('/api/users/1/settings/ultrasonic', headers=headers, json={'settings': '{"theme":"dark"}'})
        assert stored.status_code == 200, stored.text
        assert api.get('/api/users/1/settings/ultrasonic', headers=headers).json()['settings'] == '{"theme":"dark"}'

    def test_a_settings_patch_changes_only_the_named_keys(self, api, headers, db):
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        api.post('/api/users/1/settings/frontend', headers=headers, json={'settings': '{"language":"nl","a":1}'})

        patched = api.patch(
            '/api/users/1/settings/frontend', headers=headers, json={'set': {'b': [1, 2]}, 'remove': ['a']}
        )

        assert patched.status_code == 200, patched.text
        assert json.loads(patched.json()['settings']) == {'language': 'nl', 'b': [1, 2]}
        stored = api.get('/api/users/1/settings/frontend', headers=headers).json()['settings']
        assert json.loads(stored) == {'language': 'nl', 'b': [1, 2]}

    def test_a_settings_patch_creates_a_missing_blob(self, api, headers, db):
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        patched = api.patch('/api/users/1/settings/frontend', headers=headers, json={'set': {'language': 'en'}})
        assert patched.status_code == 200, patched.text
        assert patched.json()['updated_at']
        stored = api.get('/api/users/1/settings/frontend', headers=headers).json()['settings']
        assert json.loads(stored) == {'language': 'en'}

    def test_a_settings_patch_for_an_unknown_user_is_a_not_found(self, api, headers, db):
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        assert api.patch('/api/users/999/settings/frontend', headers=headers, json={'set': {'a': 1}}).status_code == 404

    def test_two_concurrent_partial_writes_both_survive(self, api, headers, db):
        """The lost update of issue #39, provoked on purpose.

        A third connection holds the row lock -- and changes the row -- while two PATCHes of
        different keys start, so both are guaranteed to be in flight at once and to find the row
        changed under them. Were the endpoint to read the blob without FOR UPDATE, both would read
        the same `{"base":0}` straight away (a consistent read does not wait for the lock), and the
        later UPDATE would write back a blob without the other's key. Were it to open a read view
        before taking the row lock (any plain SELECT first -- the first version checked the user
        that way), MariaDB's snapshot isolation would refuse the locked read with error 1020.
        """
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        api.post('/api/users/1/settings/frontend', headers=headers, json={'settings': '{"base":0}'})

        holder = _connect()
        try:
            holder.begin()
            with holder.cursor() as cursor:
                cursor.execute(
                    "SELECT settings_json FROM user_app_settings WHERE user_id = 1 AND app_id = 'frontend' FOR UPDATE"
                )
                cursor.execute(
                    "UPDATE user_app_settings SET settings_json = '{\"base\":0,\"tablet\":1}' "
                    "WHERE user_id = 1 AND app_id = 'frontend'"
                )
            results = {}

            def patch(key):
                results[key] = api.patch('/api/users/1/settings/frontend', headers=headers, json={'set': {key: key}})

            threads = [threading.Thread(target=patch, args=(key,)) for key in ('phone', 'web')]
            for thread in threads:
                thread.start()
            time.sleep(1.0)  # both requests are now parked on the lock (or would have read by now)
            holder.commit()
            for thread in threads:
                thread.join(timeout=30)
        finally:
            holder.close()

        assert {key: r.status_code for key, r in results.items()} == {'phone': 200, 'web': 200}
        stored = api.get('/api/users/1/settings/frontend', headers=headers).json()['settings']
        assert json.loads(stored) == {'base': 0, 'tablet': 1, 'phone': 'phone', 'web': 'web'}

    def test_many_concurrent_first_writes_all_survive(self, api, headers, db):
        """No blob yet: concurrent first writes race on the INSERT, and the losers retry."""
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        keys = [f'k{n}' for n in range(6)]
        statuses = {}

        def patch(key):
            statuses[key] = api.patch(
                '/api/users/1/settings/frontend', headers=headers, json={'set': {key: True}}
            ).status_code

        threads = [threading.Thread(target=patch, args=(key,)) for key in keys]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        assert statuses == dict.fromkeys(keys, 200)
        stored = api.get('/api/users/1/settings/frontend', headers=headers).json()['settings']
        assert json.loads(stored) == dict.fromkeys(keys, True)

    def test_a_listenbrainz_account_round_trip(self, api, headers, db):
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        api.post('/api/users/1/listenbrainz', headers=headers, json={'lb_username': 'user', 'lb_token': 'tok'})
        assert api.get('/api/users/1/listenbrainz', headers=headers).json()['lb_username'] == 'user'

    def test_revoking_sessions_invalidates_the_api_key(self, api, headers, db):
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        api_key = api.post('/api/auth/login', json={'username': 'root', 'password': 'hunter2'}).json()['api_key']
        assert api.get('/api/auth/verify', headers={'x-api-key': api_key}).status_code == 200
        api.post('/api/users/1/sessions/revoke', headers=headers)
        assert api.get('/api/auth/verify', headers={'x-api-key': api_key}).status_code == 403


class DynamicPlaylistsTest:
    @pytest.fixture(autouse=True)
    def _a_user_exists(self, api, db):
        api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})

    def test_a_playlist_can_be_created_read_updated_and_deleted(self, api, headers):
        created = api.post(
            '/api/users/1/dynamic-playlists', headers=headers, json={'name': 'Hardstyle', 'params': '{}'}
        )
        assert created.status_code == 200, created.text
        playlist_id = created.json()['id']

        assert api.get(f'/api/users/1/dynamic-playlists/{playlist_id}', headers=headers).json()['name'] == 'Hardstyle'

        api.put(f'/api/users/1/dynamic-playlists/{playlist_id}', headers=headers, json={'name': 'Hardcore'})
        assert api.get(f'/api/users/1/dynamic-playlists/{playlist_id}', headers=headers).json()['name'] == 'Hardcore'

        api.delete(f'/api/users/1/dynamic-playlists/{playlist_id}', headers=headers)
        assert api.get('/api/users/1/dynamic-playlists', headers=headers).json() == []

    def test_the_default_playlists_can_be_seeded(self, api, headers):
        seeded = api.post('/api/users/1/dynamic-playlists/seed-defaults', headers=headers)
        assert seeded.status_code == 200, seeded.text
        names = {row['name'] for row in api.get('/api/users/1/dynamic-playlists', headers=headers).json()}
        assert names == {'Hardstyle', 'Hardcore', 'Techno', 'Recently Added'}

    def test_the_track_query_of_a_playlist_runs(self, api, headers, db):
        """The largest generated query in the codebase; only a real database
        can say whether it parses."""
        playlist_id = api.post(
            '/api/users/1/dynamic-playlists',
            headers=headers,
            json={
                'name': 'Mixed',
                'params': '{"genres": ["Hardcore"], "rating_range": [0, 100], "size": 10,'
                ' "sort_method": "highest_rated", "song_type": "track",'
                ' "rules": [{"column": "genre", "value": "Uptempo"}]}',
            },
        ).json()['id']
        response = api.get(f'/api/users/1/dynamic-playlists/{playlist_id}/tracks', headers=headers)
        assert response.status_code == 200, response.text
        assert response.json() == []

    @pytest.mark.parametrize('sort_method', ['newest', 'oldest', 'random', 'highest_rated'])
    def test_every_sort_method_produces_valid_sql(self, api, headers, sort_method):
        playlist_id = api.post(
            '/api/users/1/dynamic-playlists',
            headers=headers,
            json={'name': sort_method, 'params': f'{{"sort_method": "{sort_method}"}}'},
        ).json()['id']
        response = api.get(f'/api/users/1/dynamic-playlists/{playlist_id}/tracks', headers=headers)
        assert response.status_code == 200, response.text


class GenreCurationTest:
    def test_a_genre_can_be_decided_and_shows_its_targets(self, api, headers, db):
        with db.cursor() as cursor:
            cursor.executemany(
                'INSERT INTO rules_genres (name, normalized_name, state) VALUES (%s, %s, %s)',
                [
                    ('Upterror', 'upterror', 'unknown'),
                    ('Uptempo Hardcore', 'uptempo hardcore', 'white'),
                    ('Terror', 'terror', 'white'),
                ],
            )
            cursor.execute("SELECT id, name FROM rules_genres ORDER BY id")
            ids = {row['name']: row['id'] for row in cursor.fetchall()}

        decided = api.post(
            f"/api/rules/genres/{ids['Upterror']}/decide",
            headers=headers,
            json={'state': 'black', 'canonical_ids': [ids['Uptempo Hardcore'], ids['Terror']]},
        )
        assert decided.status_code == 200, decided.text

        queue = api.get('/api/rules/genres', headers=headers).json()
        upterror = next(row for row in queue if row['name'] == 'Upterror')
        assert upterror['state'] == 'black'
        assert upterror['decided_by'] == 'system'
        assert [target['name'] for target in upterror['canonical_targets']] == ['Uptempo Hardcore', 'Terror']

    def test_an_analysis_run_writes_advice_the_queue_carries(self, api, headers, db):
        """Every query behind the advice, against the real schema: the dictionary
        loads (approved genres with track counts, expansions, rejected names,
        artists with their tagger links, labels), the proposals land with ids, and
        the queue endpoint joins and filters on them."""
        with db.cursor() as cursor:
            cursor.executemany(
                'INSERT INTO rules_genres (name, normalized_name, state) VALUES (%s, %s, %s)',
                [
                    ('Uptempo Hardcore', 'uptempo hardcore', 'white'),
                    ('Terror', 'terror', 'white'),
                    ('Frenchcore', 'frenchcore', 'white'),
                    ('uptempo', 'uptempo', 'black'),
                    ('HEARTBREAK', 'heartbreak', 'black'),
                    ('Upterror', 'upterror', 'unknown'),
                    ('Frenchcore/Terror', 'frenchcore terror', 'unknown'),
                    ('dr peacock', 'dr peacock', 'unknown'),
                    ('Tafelpoot', 'tafelpoot', 'unknown'),
                ],
            )
            cursor.execute('SELECT id, name FROM rules_genres')
            ids = {row['name']: row['id'] for row in cursor.fetchall()}
            cursor.execute(
                'INSERT INTO rules_genre_expansions (genre_id, target_id, position) VALUES (%s, %s, 0)',
                (ids['uptempo'], ids['Uptempo Hardcore']),
            )
            cursor.execute("INSERT INTO library_artists (name) VALUES ('Dr Peacock')")
            cursor.execute(
                "INSERT INTO rules_artist_genres (artist_name, genre_id) VALUES ('Dr Peacock', %s)",
                (ids['Frenchcore'],),
            )

        started = api.post('/api/rules/genres/analyze', headers=headers)
        assert started.status_code == 202, started.text
        status = api.get(f"/api/rules/genres/analyze/{started.json()['job_id']}", headers=headers).json()
        assert status['status'] == 'finished', status
        assert status['summary'] == {'keep': 0, 'rewrite': 1, 'split': 2, 'reject': 1, 'unknown': 0}

        queue = {row['name']: row for row in api.get('/api/rules/genres?state=unknown', headers=headers).json()}
        assert [t['name'] for t in queue['Upterror']['proposal']['targets']] == ['Uptempo Hardcore', 'Terror']
        assert queue['Upterror']['proposal']['targets'][0]['id'] == ids['Uptempo Hardcore']
        assert queue['dr peacock']['proposal']['kind'] == 'rewrite'
        assert queue['dr peacock']['proposal']['targets'][0]['name'] == 'Frenchcore'
        assert queue['Tafelpoot']['proposal']['kind'] == 'reject'
        rejects = api.get('/api/rules/genres?state=unknown&proposal=reject', headers=headers).json()
        assert [row['name'] for row in rejects] == ['Tafelpoot']

        summary = api.get('/api/rules/genres/summary', headers=headers).json()
        assert summary['unknown'] == 4
        assert summary['proposals'] == {'rewrite': 1, 'split': 2, 'reject': 1}
        assert summary['analyzed_at']

        # A decision on an advised genre leaves the others' advice in place and the
        # tagger page's list approved-only.
        decided = api.post(
            f"/api/rules/genres/{ids['Upterror']}/decide",
            headers=headers,
            json={'state': 'black', 'canonical_ids': [t['id'] for t in queue['Upterror']['proposal']['targets']]},
        )
        assert decided.status_code == 200, decided.text
        assert {g['name'] for g in api.get('/api/rules', headers=headers).json()['genres']} == {
            'Uptempo Hardcore',
            'Terror',
            'Frenchcore',
        }

    def test_the_curation_queue_can_be_filtered_by_state(self, api, headers, db):
        with db.cursor() as cursor:
            cursor.executemany(
                'INSERT INTO rules_genres (name, normalized_name, state) VALUES (%s, %s, %s)',
                [('New Thing', 'new thing', 'unknown'), ('Hardcore', 'hardcore', 'white')],
            )
        queue = api.get('/api/rules/genres?state=unknown', headers=headers).json()
        assert [row['name'] for row in queue] == ['New Thing']

    def test_an_artist_genre_rule_round_trip(self, api, headers, db):
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO rules_genres (name, normalized_name) VALUES ('Hardcore', 'hardcore')")
            genre_id = cursor.lastrowid
        api.post('/api/rules/artist-genres', headers=headers, json={'artist_name': 'Angerfist', 'genre_id': genre_id})
        rules = api.get('/api/rules/artist-genres', headers=headers).json()
        assert rules[0]['artist_name'] == 'Angerfist'
        assert rules[0]['genre_name'] == 'Hardcore'
        api.delete(f"/api/rules/artist-genres/{rules[0]['id']}", headers=headers)
        assert api.get('/api/rules/artist-genres', headers=headers).json() == []

    def test_a_label_genre_rule_round_trip(self, api, headers, db):
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO rules_genres (name, normalized_name) VALUES ('Hardstyle', 'hardstyle')")
            genre_id = cursor.lastrowid
        api.post('/api/rules/label-genres', headers=headers, json={'label_name': 'Scantraxx', 'genre_id': genre_id})
        rules = api.get('/api/rules/label-genres', headers=headers).json()
        assert rules[0]['label_name'] == 'Scantraxx'
        api.delete(f"/api/rules/label-genres/{rules[0]['id']}", headers=headers)
        assert api.get('/api/rules/label-genres', headers=headers).json() == []


class LibraryReadsTest:
    @pytest.fixture
    def a_track(self, db):
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_artists (name) VALUES ('Angerfist')")
            artist_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id)'
                " VALUES ('uid-1', 'Raise Your Fist', 320, %s)",
                (artist_id,),
            )
            track_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO library_media_files (file_path, file_path_hash, track_id, file_mtime, file_size)'
                " VALUES ('/mnt/music/a.mp3', 'hash-1', %s, 1.0, 10)",
                (track_id,),
            )
            cursor.execute(
                "INSERT INTO rules_genres (name, normalized_name, state) VALUES ('Hardcore', 'hardcore', 'white')"
            )
            genre_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO library_track_genres (track_id, genre_id) VALUES (%s, %s)', (track_id, genre_id)
            )
        return track_id

    def test_a_track_shows_up_in_the_track_list(self, api, headers, a_track):
        body = api.get('/api/library/tracks', headers=headers).json()
        assert body['total'] == 1
        assert body['tracks'][0]['title'] == 'Raise Your Fist'
        assert body['tracks'][0]['artist'] == 'Angerfist'

    def test_the_display_artist_is_null_when_never_captured(self, api, headers, a_track):
        body = api.get('/api/library/tracks', headers=headers).json()
        assert body['tracks'][0]['display_artist'] is None

    def test_the_display_artist_is_returned_when_captured(self, api, headers, db):
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_artists (name) VALUES ('Henk')")
            artist_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id, display_artist)'
                " VALUES ('uid-2', 'Big Room Anthem', 320, %s, 'Henk feat Kees')",
                (artist_id,),
            )
        tracks = api.get('/api/library/tracks', headers=headers).json()['tracks']
        advanced = api.get('/api/library/advanced', headers=headers).json()['tracks']
        assert next(t for t in tracks if t['title'] == 'Big Room Anthem')['display_artist'] == 'Henk feat Kees'
        assert next(t for t in advanced if t['title'] == 'Big Room Anthem')['display_artist'] == 'Henk feat Kees'

    def test_the_search_term_filters_the_track_list(self, api, headers, a_track):
        assert api.get('/api/library/tracks?q=anger', headers=headers).json()['total'] == 1
        assert api.get('/api/library/tracks?q=nothing', headers=headers).json()['total'] == 0

    def test_the_advanced_view_returns_the_genres_as_a_list(self, api, headers, a_track):
        body = api.get('/api/library/advanced', headers=headers).json()
        assert body['total'] == 1
        assert body['tracks'][0]['genres'] == ['Hardcore']

    def test_the_genre_sidebar_counts_tracks(self, api, headers, a_track):
        genres = api.get('/api/library/genres', headers=headers).json()
        assert genres == [{'genre': 'Hardcore', 'state': 'white', 'count': 1, 'tint': '#e5002b'}]

    def _insert_set(self, db, uid, title, path, **columns):
        names = ['track_uid', 'title', 'duration_secs', *columns]
        values = [uid, title, 3600, *columns.values()]
        with db.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO library_tracks ({', '.join(names)}) VALUES ({', '.join(['%s'] * len(names))})", values
            )
            track_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO library_media_files (file_path, file_path_hash, track_id, file_mtime, file_size)'
                ' VALUES (%s, %s, %s, 1.0, 10)',
                (path, hashlib.sha256(path.encode()).hexdigest(), track_id),
            )
        return track_id

    def test_a_live_set_files_under_the_year_it_was_played(self, api, headers, db, a_track):
        """product-goal.md: a live set filters on its performance date, everything else on its
        release date -- and the form filter leaves the plain track out."""
        self._insert_set(
            db,
            'uid-live',
            'Defqon 2012 set',
            '/mnt/music/Livesets/a.mp3',
            form='liveset',
            performance_date='2012-06-23',
            release_date='2016-01-01',
        )
        self._insert_set(
            db, 'uid-mix', 'Yearmix', '/mnt/music/Soundcloud/x/b.mp3', form='set', release_date='2012-12-31'
        )

        def titles(query):
            return sorted(
                t['title'] for t in api.get(f'/api/library/advanced?{query}', headers=headers).json()['tracks']
            )

        assert titles('year_min=2012&year_max=2012') == ['Defqon 2012 set', 'Yearmix']
        assert titles('year_min=2016&year_max=2016') == []
        assert titles('form=liveset') == ['Defqon 2012 set']
        assert titles('form=liveset&form=set') == ['Defqon 2012 set', 'Yearmix']

    def test_the_form_pass_classifies_the_library_against_mariadb(self, db, a_track):
        """track_form_sync's window query and UPDATE run on MariaDB, and a second pass writes nothing."""

        from services.common.Helpers.FestivalHelper import Festival, FestivalHelper
        from services.common.Helpers.PodcastHelper import PodcastHelper
        from services.music_manager import track_form_sync

        live = self._insert_set(db, 'uid-live', 'Headhunterz @ Defqon.1 2012', '/mnt/music/Youtube/q/c.mp3')
        festivals = FestivalHelper(preload=False)
        festivals.set_festivals([Festival(name='Defqon.1', aliases=['Defqon.1'], editions={2012: date(2012, 6, 23)})])
        podcasts = PodcastHelper(preload=False)

        first = track_form_sync.classify_library(db, '/mnt/music', festivals, podcasts)
        second = track_form_sync.classify_library(db, '/mnt/music', festivals, podcasts)

        assert first == {'considered': 2, 'written': 2, 'unclassified_no_file': 0, 'unclassified_no_length': 0}
        assert second == {'considered': 2, 'written': 0, 'unclassified_no_file': 0, 'unclassified_no_length': 0}
        with db.cursor() as cursor:
            cursor.execute('SELECT id, form, performance_date FROM library_tracks ORDER BY id')
            rows = {row['id']: (row['form'], row['performance_date']) for row in cursor.fetchall()}
        assert rows == {a_track: ('track', None), live: ('liveset', '2012-06-23')}

    def test_the_form_push_converges_when_two_media_rows_name_one_file(self, db):
        """Bug report 093: a stale media row (hash no longer its path's) on a length-less stub
        must not overwrite the form the scanner's own row pushes -- run twice, write once."""
        import sqlite3

        from services.music_manager import track_form_sync

        path = '/mnt/music/EPs/Label/CAT1/01.mp3'
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO library_tracks (track_uid, title, duration_secs, form) VALUES ('uid-real', 'Real', 200, 'track')"
            )
            real = cursor.lastrowid
            cursor.execute("INSERT INTO library_tracks (track_uid, title) VALUES ('uid-stub', '01')")
            stub = cursor.lastrowid
            # The stale row is inserted last, so it has the higher id: only the hash says who wins.
            cursor.execute(
                'INSERT INTO library_media_files (file_path, file_path_hash, track_id) VALUES (%s, %s, %s)',
                (path, hashlib.sha256(path.encode()).hexdigest(), real),
            )
            cursor.execute(
                "INSERT INTO library_media_files (file_path, file_path_hash, track_id) VALUES (%s, 'stale', %s)",
                (path, stub),
            )
        server = sqlite3.connect(':memory:')
        server.execute(
            "CREATE TABLE track (id INTEGER PRIMARY KEY, absolute_file_path TEXT,"
            " form TEXT NOT NULL DEFAULT '', performance_date TEXT NOT NULL DEFAULT '')"
        )
        server.execute("INSERT INTO track (absolute_file_path) VALUES ('/music/EPs/Label/CAT1/01.mp3')")
        server.commit()

        first = track_form_sync.push_forms_to_server(db, server, 'test')
        second = track_form_sync.push_forms_to_server(db, server, 'test')

        assert (first['matched'], first['duplicates_skipped']) == (1, 1)
        assert (second['matched'], second['duplicates_skipped']) == (0, 1)
        assert server.execute('SELECT form FROM track').fetchone() == ('track',)
        server.close()

    def test_the_version_push_marks_one_canonical_row_per_work(self, db, tmp_path):
        """Bug report 097, against MariaDB and an lms.db file: a canonical track with two files
        gets one canonical row, a canonical the server lacks falls back to the best version it
        has, a stale media row is ignored, and a second run writes nothing."""
        import sqlite3

        from services.music_manager import song_version_sync

        def media(cursor, path, track_id, size, own=True):
            digest = hashlib.sha256(path.encode()).hexdigest() if own else 'stale-' + path[-20:]
            cursor.execute(
                'INSERT INTO library_media_files (file_path, file_path_hash, track_id, file_size, duration_secs)'
                ' VALUES (%s, %s, %s, %s, 300)',
                (path, digest, track_id, size),
            )

        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_works (work_key) VALUES ('angerfist|raise your fist')")
            song = cursor.lastrowid
            cursor.execute("INSERT INTO library_works (work_key) VALUES ('miss k8|gone')")
            gone = cursor.lastrowid
            tracks = {}
            for uid, work_id, score in (
                ('uid-official', song, 900),
                ('uid-rip', song, 100),
                ('uid-gone-official', gone, 900),
                ('uid-gone-rip', gone, 100),
                ('uid-gone-ext', gone, 300),
            ):
                cursor.execute(
                    'INSERT INTO library_tracks (track_uid, title, duration_secs, work_id, version_score)'
                    ' VALUES (%s, %s, 300, %s, %s)',
                    (uid, uid, work_id, score),
                )
                tracks[uid] = cursor.lastrowid
            cursor.execute(
                'UPDATE library_works SET canonical_track_id = %s WHERE id = %s', (tracks['uid-official'], song)
            )
            cursor.execute(
                'UPDATE library_works SET canonical_track_id = %s WHERE id = %s', (tracks['uid-gone-official'], gone)
            )
            cursor.execute("INSERT INTO library_tracks (track_uid, title) VALUES ('uid-stub', '01')")
            stub = cursor.lastrowid
            media(cursor, '/mnt/music/EPs/MOH/01.flac', tracks['uid-official'], 40_000_000)
            media(cursor, '/mnt/music/EPs/MOH/01.mp3', tracks['uid-official'], 12_000_000)
            media(cursor, '/mnt/music/EPs/MOH/01.mp3', stub, 12_000_000, own=False)
            media(cursor, '/mnt/music/Soundcloud/rip.mp3', tracks['uid-rip'], 7_000_000)
            media(cursor, '/mnt/music/EPs/K8/gone.flac', tracks['uid-gone-official'], 40_000_000)
            media(cursor, '/mnt/music/Soundcloud/gone-rip.mp3', tracks['uid-gone-rip'], 7_000_000)
            media(cursor, '/mnt/music/Youtube/k8/gone-ext.mp3', tracks['uid-gone-ext'], 7_000_000)

        lms_db = tmp_path / 'lms.db'
        server = sqlite3.connect(lms_db)
        server.execute(
            'CREATE TABLE track (id INTEGER PRIMARY KEY, absolute_file_path TEXT, work_id INTEGER,'
            " is_canonical INTEGER NOT NULL DEFAULT 1, version_kind TEXT NOT NULL DEFAULT '',"
            ' version_score INTEGER NOT NULL DEFAULT 0)'
        )
        # Every file but the gone work's canonical: that one is missing from the server.
        for path in (
            '/music/EPs/MOH/01.flac',
            '/music/EPs/MOH/01.mp3',
            '/music/Soundcloud/rip.mp3',
            '/music/Soundcloud/gone-rip.mp3',
            '/music/Youtube/k8/gone-ext.mp3',
        ):
            server.execute('INSERT INTO track (absolute_file_path) VALUES (?)', (path,))
        server.commit()

        first = song_version_sync.sync_song_versions_to_server(db, server, 'test')
        second = song_version_sync.sync_song_versions_to_server(db, server, 'test')

        rows = dict(server.execute('SELECT absolute_file_path, is_canonical FROM track'))
        assert rows == {
            '/music/EPs/MOH/01.flac': 1,
            '/music/EPs/MOH/01.mp3': 0,
            '/music/Soundcloud/rip.mp3': 0,
            '/music/Soundcloud/gone-rip.mp3': 0,
            '/music/Youtube/k8/gone-ext.mp3': 1,
        }
        assert (first['duplicates_skipped'], first['canonical_fallbacks'], first['works']) == (1, 1, 2)
        assert first['matched'] == 5
        assert second['matched'] == 0
        server.close()

    def test_rerunning_a_parse_for_an_unknown_track_is_a_not_found(self, api, headers, db):
        assert api.post('/api/library/tracks/999/rerun-parse', headers=headers).status_code == 404

    def test_the_details_by_path_join_channel_ingestion_features_and_archive(self, api, headers, db):
        """Five tables behind one answer for the player's details sheet, keyed on the
        LMS-relative spelling of the path while every row stores the /mnt/music one."""
        path = '/mnt/music/Soundcloud/Complex/b.mp3'
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_artists (name) VALUES ('Complex')")
            artist_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id)'
                " VALUES ('uid-b', 'Rammeroni Style', 201, %s)",
                (artist_id,),
            )
            track_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO library_media_files (file_path, file_path_hash, track_id, file_mtime, file_size)'
                ' VALUES (%s, %s, %s, 1.0, 10)',
                (path, hashlib.sha256(path.encode()).hexdigest(), track_id),
            )
            cursor.execute(
                "INSERT INTO channels (platform, name, normalized_name, artist_id)"
                " VALUES ('soundcloud', 'Complex', 'complex', %s)",
                (artist_id,),
            )
            channel_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO library_track_channels (track_id, channel_id) VALUES (%s, %s)', (track_id, channel_id)
            )
            cursor.execute(
                'INSERT INTO library_ingestion_records (file_path, file_path_hash, source, tags_json)'
                " VALUES (%s, %s, 'LABEL', '{\"catalognumber\": [\"Q404PRO\"], \"isrc\": [\"NL1\"]}')",
                (path, hashlib.sha256(path.encode()).hexdigest()),
            )
            cursor.execute(
                'INSERT INTO library_track_audio_features (track_id, internal_track_id, tempo) VALUES (%s, %s, 103.4)',
                ('uid-b', track_id),
            )
            cursor.execute(
                "INSERT INTO downloads_soundcloud_archive (account, video_id, filename, url, title)"
                " VALUES ('complex', 'v1', %s, 'https://soundcloud.com/complex/b', 'b')",
                (path,),
            )
        response = api.get('/api/library/tracks/by-path?path=Soundcloud/Complex/b.mp3', headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['track_id'] == track_id
        assert body['channels'] == [{'platform': 'soundcloud', 'name': 'Complex', 'label': None, 'artist': 'Complex'}]
        assert body['source'] == 'LABEL'
        assert body['tags'] == {'catalognumber': ['Q404PRO'], 'isrc': ['NL1']}
        assert body['bpm'] == pytest.approx(103.4)
        assert body['source_url'] == 'https://soundcloud.com/complex/b'
        assert body['source_platform'] == 'soundcloud'
        assert body['added_at']


class ChannelLinksTest:
    """docs/designs/channel-links: the search, a decision, and the link on the coverage page."""

    def _library(self, db):
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_labels (name) VALUES ('Traxtorm')")
            label_id = cursor.lastrowid
            cursor.execute("INSERT INTO library_artists (name) VALUES ('D-Sturb')")
            artist_id = cursor.lastrowid
            cursor.execute("INSERT INTO rules_artists (name, state) VALUES ('D-Sturb', 'white')")
            cursor.execute(
                "INSERT INTO rules_artists (name, state, canonical_name) VALUES ('D Sturb', 'black', 'D-Sturb')"
            )
            cursor.execute(
                "INSERT INTO library_artist_aliases (artist_id, alias) VALUES (%s, 'DSturb Official')", (artist_id,)
            )
            cursor.execute(
                "INSERT INTO channels (platform, name, normalized_name) VALUES "
                "('soundcloud', 'TRAXTORM', 'traxtorm'), ('youtube', 'D-Sturb', 'd-sturb')"
            )
            cursor.execute("SELECT id, name FROM channels")
            channels = {row['name']: row['id'] for row in cursor.fetchall()}
        db.commit()
        return label_id, artist_id, channels

    def test_the_search_runs_twice_and_a_confirm_links_the_channel(self, api, headers, db):
        label_id, _, channels = self._library(db)
        first = api.post('/api/channel-links/proposals/refresh', headers=headers)
        assert first.status_code == 200, first.text
        assert first.json() == {'created': 2, 'open': 2, 'withdrawn': 0, 'ambiguous': 0}
        again = api.post('/api/channel-links/proposals/refresh', headers=headers).json()
        assert again == {'created': 0, 'open': 2, 'withdrawn': 0, 'ambiguous': 0}

        listed = api.get('/api/channel-links/proposals?kind=label', headers=headers).json()
        assert [(row['channel_name'], row['target_name'], row['source']) for row in listed] == [
            ('TRAXTORM', 'Traxtorm', 'name')
        ]
        confirmed = api.post(f"/api/channel-links/proposals/{listed[0]['id']}/confirm", headers=headers)
        assert confirmed.json()['status'] == 'confirmed', confirmed.text
        assert run_sql(db, 'SELECT label_id FROM channels WHERE id = %s', (channels['TRAXTORM'],)) == [
            {'label_id': label_id}
        ]

        unlinked = api.delete(f"/api/channel-links/channels/{channels['TRAXTORM']}/label", headers=headers)
        assert unlinked.json()['status'] == 'unlinked'
        api.post('/api/channel-links/proposals/refresh', headers=headers)
        statuses = run_sql(db, "SELECT status FROM channel_link_proposals WHERE kind = 'label'")
        assert statuses == [{'status': 'rejected'}]

    def test_the_coverage_page_shows_the_link_through_the_archive(self, api, headers, db):
        label_id, _, channels = self._library(db)
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO downloads_soundcloud_accounts (name, soundcloud_id) VALUES ('traxtorm', '42')")
            cursor.execute(
                "INSERT INTO downloads_soundcloud_archive (account, video_id, filename, url, title, added_at)"
                " VALUES ('42', 'v1', '/mnt/music/Soundcloud/TRAXTORM/a.mp3', 'u', 'a', NOW())"
            )
            cursor.execute('UPDATE channels SET label_id = %s WHERE id = %s', (label_id, channels['TRAXTORM']))
        db.commit()
        body = api.get('/api/downloaders/coverage/soundcloud', headers=headers).json()
        row = body['accounts'][0]
        assert row['last_download_at'] is not None
        assert row['channel']['label'] == {'id': label_id, 'name': 'Traxtorm'}

    def test_a_hand_link_is_a_manual_confirmed_row_and_unlinks_like_a_proposal(self, api, headers, db):
        """Issue #58: migrate_v48's `manual` source, the upsert, and the rival proposal withdrawn."""
        _, artist_id, channels = self._library(db)
        api.post('/api/channel-links/proposals/refresh', headers=headers)
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_artists (name) VALUES ('D-Sturb Alt')")
            other_id = cursor.lastrowid
            cursor.execute("INSERT INTO rules_artists (name, state) VALUES ('D-Sturb Alt', 'white')")
        db.commit()
        channel = channels['D-Sturb']
        linked = api.put(f'/api/channel-links/channels/{channel}/artist', headers=headers, json={'target_id': other_id})
        assert linked.status_code == 200, linked.text
        assert linked.json()['target_name'] == 'D-Sturb Alt'
        rows = run_sql(
            db,
            'SELECT target_id, source, status FROM channel_link_proposals WHERE channel_id = %s ORDER BY id',
            (channel,),
        )
        assert rows == [
            {'target_id': artist_id, 'source': 'name', 'status': 'stale'},
            {'target_id': other_id, 'source': 'manual', 'status': 'confirmed'},
        ]
        assert run_sql(db, 'SELECT artist_id FROM channels WHERE id = %s', (channel,)) == [{'artist_id': other_id}]
        # Another artist is refused until the link is removed; unlinking rejects the manual row.
        again = api.put(f'/api/channel-links/channels/{channel}/artist', headers=headers, json={'target_id': artist_id})
        assert again.status_code == 409
        api.delete(f'/api/channel-links/channels/{channel}/artist', headers=headers)
        assert run_sql(db, "SELECT status FROM channel_link_proposals WHERE source = 'manual'") == [
            {'status': 'rejected'}
        ]

    def test_the_pickers_search_channels_labels_and_approved_artists_literally(self, api, headers, db):
        self._library(db)
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_labels (name) VALUES ('Soundcloud'), ('100% Hard')")
            cursor.execute("INSERT INTO library_artists (name) VALUES ('D-Sturbia')")
            cursor.execute(
                "INSERT INTO channels (platform, name, normalized_name) VALUES ('soundcloud', '100% Raw', '100% raw')"
            )
        db.commit()
        found = api.get('/api/channel-links/channels?q=traxtorm', headers=headers).json()
        assert [(c['name'], c['track_count'], c['label'], c['open_proposals']) for c in found] == [
            ('TRAXTORM', 0, None, 0)
        ]
        # `%` in the query is a character, not a wildcard.
        assert [c['name'] for c in api.get('/api/channel-links/channels?q=100%25', headers=headers).json()] == [
            '100% Raw'
        ]
        labels = api.get('/api/channel-links/targets?kind=label&q=d', headers=headers).json()
        assert [row['name'] for row in labels] == ['100% Hard']  # Soundcloud matches, but is no label
        # D-Sturbia is in the library but was never approved.
        artists = api.get('/api/channel-links/targets?kind=artist&q=d-sturb', headers=headers).json()
        assert [row['name'] for row in artists] == ['D-Sturb']

    def test_a_label_page_lists_its_linked_channels_busiest_first(self, api, headers, db):
        """Issue #122: the label by name, its channels with counts, the source link by account."""
        label_id, artist_id, channels = self._library(db)
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO channels (platform, name, normalized_name, label_id, artist_id) VALUES "
                "('youtube', 'Traxtorm Records', 'traxtorm records', %s, %s)",
                (label_id, artist_id),
            )
            busy = cursor.lastrowid
            cursor.execute('UPDATE channels SET label_id = %s WHERE id = %s', (label_id, channels['TRAXTORM']))
            for n in range(2):
                cursor.execute("INSERT INTO library_tracks (track_uid, title) VALUES (%s, 't')", (f'uid-l{n}',))
                cursor.execute(
                    'INSERT INTO library_track_channels (track_id, channel_id) VALUES (%s, %s)',
                    (cursor.lastrowid, busy),
                )
            cursor.execute("INSERT INTO downloads_soundcloud_accounts (name, soundcloud_id) VALUES ('traxtorm', '42')")
            cursor.execute("INSERT INTO downloads_youtube_accounts (name) VALUES ('@traxtormrecords')")
        db.commit()
        response = api.get('/api/channel-links/by-label', params={'name': 'traxtorm'}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json() == [
            {
                'id': busy,
                'platform': 'youtube',
                'name': 'Traxtorm Records',
                'track_count': 2,
                'artist': {'id': artist_id, 'name': 'D-Sturb'},
                'album': 'Youtube (Traxtorm Records)',
                'source_url': 'https://www.youtube.com/@traxtormrecords',
            },
            {
                'id': channels['TRAXTORM'],
                'platform': 'soundcloud',
                'name': 'TRAXTORM',
                'track_count': 0,
                'artist': None,
                'album': 'Soundcloud (TRAXTORM)',
                'source_url': 'https://soundcloud.com/traxtorm',
            },
        ]
        assert api.get('/api/channel-links/by-label?name=Nobody', headers=headers).json() == []

    def test_a_link_change_queues_the_channels_files_for_the_tagger(self, api, headers, db):
        from services.common import db_init

        label_id, _, channels = self._library(db)
        # tagger_processed_files' later columns land on a second pass, as on every deploy.
        db_init.ensure_tables_exist()
        path = '/mnt/music/Soundcloud/TRAXTORM/a.mp3'
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_tracks (track_uid, title) VALUES ('uid-t', 'a')")
            track_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO library_media_files (file_path, file_path_hash, track_id) VALUES (%s, %s, %s)',
                (path, 'h-t', track_id),
            )
            cursor.execute(
                'INSERT INTO library_track_channels (track_id, channel_id) VALUES (%s, %s)',
                (track_id, channels['TRAXTORM']),
            )
            cursor.execute(
                'INSERT INTO tagger_processed_files (filepath, mtime, needs_rescan) VALUES (%s, 1.0, FALSE)', (path,)
            )
        db.commit()
        linked = api.put(
            f"/api/channel-links/channels/{channels['TRAXTORM']}/label", headers=headers, json={'target_id': label_id}
        )
        assert linked.json()['queued'] == 1, linked.text
        rows = run_sql(
            db, 'SELECT needs_rescan, rescan_reason FROM tagger_processed_files WHERE filepath = %s', (path,)
        )
        assert [(bool(r['needs_rescan']), r['rescan_reason']) for r in rows] == [(True, 'channel_link')]


class DownloaderScheduleTest:
    """The deprecated schedule read, against a checks table that holds a row."""

    def test_the_deprecated_schedule_reports_a_checked_account(self, api, headers, db):
        # An empty table hid a 500 here: each row came back as an AccountCheck (#171).
        run_sql(
            db,
            "INSERT INTO downloads_account_checks (source, account, last_checked_at)"
            " VALUES ('soundcloud', 'traxtorm', '2026-07-30 12:00:00')",
        )
        db.commit()
        response = api.get('/api/downloaders/schedule/soundcloud', headers=headers)
        assert response.status_code == 200
        assert response.json()['accounts'] == [{'account': 'traxtorm', 'last_checked_at': '2026-07-30T12:00:00'}]


class ScrobblingTest:
    def test_a_listen_for_a_known_track_is_matched(self, api, headers, db):
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_artists (name) VALUES ('Angerfist')")
            artist_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO library_tracks (track_uid, title, primary_artist_id)"
                " VALUES ('uid-1', 'Raise Your Fist', %s)",
                (artist_id,),
            )
        response = api.post(
            '/api/scrobble/event',
            headers=headers,
            json={'artist_name': 'Angerfist', 'track_title': 'Raise Your Fist', 'username': 'root'},
        )
        assert response.status_code == 200, response.text
        assert response.json()['matched'] is True
        with db.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) AS n FROM scrobble_listens')
            assert cursor.fetchone()['n'] == 1

    def test_a_listen_for_an_unknown_track_is_parked(self, api, headers, db):
        response = api.post(
            '/api/scrobble/event',
            headers=headers,
            json={'artist_name': 'Nobody', 'track_title': 'Nothing', 'username': 'root'},
        )
        assert response.json()['matched'] is False
        with db.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) AS n FROM scrobble_unmatched_listens')
            assert cursor.fetchone()['n'] == 1

    def test_the_same_listen_twice_is_stored_once(self, api, headers, db):
        payload = {'artist_name': 'Nobody', 'track_title': 'Nothing', 'username': 'root', 'listened_at': 1700000000}
        api.post('/api/scrobble/event', headers=headers, json=payload)
        api.post('/api/scrobble/event', headers=headers, json=payload)
        with db.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) AS n FROM scrobble_unmatched_listens')
            assert cursor.fetchone()['n'] == 1

    def test_a_retried_matched_listen_is_stored_once(self, api, headers, db):
        # Bug report 071: the app retries a send it could not confirm, with the play's start time
        # as listened_at both times. The unique key on (username, listened_at, track_id) has to
        # turn the second request into the same row, not a second listen.
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_artists (name) VALUES ('Angerfist')")
            artist_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO library_tracks (track_uid, title, primary_artist_id)"
                " VALUES ('uid-retry', 'Raise Your Fist', %s)",
                (artist_id,),
            )
        payload = {
            'artist_name': 'Angerfist',
            'track_title': 'Raise Your Fist',
            'username': 'root',
            'listened_at': 1758778000,
            'played_secs': 600,
            'source': 'mobile',
        }
        assert api.post('/api/scrobble/event', headers=headers, json=payload).status_code == 200
        assert api.post('/api/scrobble/event', headers=headers, json=payload).status_code == 200
        with db.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) AS n, MAX(played_secs) AS secs FROM scrobble_listens')
            row = cursor.fetchone()
            assert row['n'] == 1
            assert row['secs'] == 600


class DownloadAccountsTest:
    def test_a_soundcloud_account_round_trip(self, api, headers, db):
        api.post('/api/soundcloud', headers=headers, json={'name': 'artist', 'soundcloud_id': '7'})
        # soundcloud_id is a BIGINT, as on production, so it comes back as a number.
        assert api.get('/api/soundcloud', headers=headers).json() == [{'name': 'artist', 'soundcloud_id': 7}]
        api.delete('/api/soundcloud/artist', headers=headers)
        assert api.get('/api/soundcloud', headers=headers).json() == []

    def test_a_youtube_account_round_trip(self, api, headers, db):
        api.post('/api/youtube', headers=headers, json={'name': 'channel'})
        assert [row['name'] for row in api.get('/api/youtube', headers=headers).json()] == ['channel']
        api.delete('/api/youtube/channel', headers=headers)
        assert api.get('/api/youtube', headers=headers).json() == []


class ArtistRedirectsTest:
    """Bug 080: rejecting or undoing a name must not leave redirects pointing at it."""

    @staticmethod
    def _redirects(db):
        with db.cursor() as cursor:
            cursor.execute('SELECT name, corrected_name FROM rules_ignored_artists ORDER BY name')
            tagger = {row['name']: row['corrected_name'] for row in cursor.fetchall()}
            cursor.execute('SELECT name, state, canonical_name FROM rules_artists ORDER BY name')
            decisions = {row['name']: (row['state'], row['canonical_name']) for row in cursor.fetchall()}
        return tagger, decisions

    def _correct(self, api, headers, name, target):
        response = api.post(
            '/api/rules/artists/decide',
            headers=headers,
            json={'names': [name], 'state': 'black', 'canonical_name': target},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_rejecting_a_target_with_a_correction_repoints_its_redirects(self, api, headers, db):
        self._correct(api, headers, 'Angerfst', 'Angerfist')
        with db.cursor() as cursor:
            # A redirect typed on the Tagger tab, never a curation decision.
            cursor.execute(
                "INSERT INTO rules_ignored_artists (name, corrected_name) VALUES ('ANGERFIST!', 'angerfist')"
            )
        body = self._correct(api, headers, 'Angerfist', 'Angerfist (NL)')
        assert body['repointed'] == ['ANGERFIST!', 'Angerfst']
        tagger, decisions = self._redirects(db)
        assert tagger == {'ANGERFIST!': 'Angerfist (NL)', 'Angerfist': 'Angerfist (NL)', 'Angerfst': 'Angerfist (NL)'}
        assert decisions['Angerfst'] == ('black', 'Angerfist (NL)')
        assert api.get('/api/rules/artists/redirects/issues', headers=headers).json()['count'] == 0

    def test_rejecting_a_target_outright_returns_its_redirects_to_the_queue(self, api, headers, db):
        self._correct(api, headers, 'Angerfst', 'Angerfist')
        response = api.post(
            '/api/rules/artists/decide', headers=headers, json={'names': ['Angerfist'], 'state': 'black'}
        )
        assert response.json()['returned_to_queue'] == ['Angerfst']
        tagger, decisions = self._redirects(db)
        assert tagger == {'Angerfist': None}
        assert 'Angerfst' not in decisions

    def test_undoing_a_target_returns_its_redirects_to_the_queue(self, api, headers, db):
        self._correct(api, headers, 'Angerfst', 'Angerfist')
        response = api.delete('/api/rules/artists/Angerfist', headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()['returned_to_queue'] == ['Angerfst']
        tagger, decisions = self._redirects(db)
        assert tagger == {}
        assert decisions == {}

    def test_the_check_reports_dangling_redirects_and_loops_stored_before_the_fix(self, api, headers, db):
        with db.cursor() as cursor:
            cursor.executemany(
                'INSERT INTO rules_ignored_artists (name, corrected_name) VALUES (%s, %s)',
                [('Y', 'Premiere'), ('Premiere', None), ('Loop A', 'Loop B'), ('Loop B', 'Loop A')],
            )
            cursor.execute(
                "INSERT INTO rules_artists (name, state, canonical_name, decided_by) VALUES "
                "('Premiere', 'black', NULL, 'legacy-redirect')"
            )
        report = api.get('/api/rules/artists/redirects/issues', headers=headers).json()
        assert [(row['name'], row['target']) for row in report['dangling']] == [('Y', 'Premiere')]
        assert report['cycles'] == [['Loop A', 'Loop B']]
        assert report['count'] == 2

    def test_the_tagger_tab_refuses_a_rejected_target(self, api, headers, db):
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO rules_artists (name, state) VALUES ('Premiere', 'black')")
        refused = api.post(
            '/api/rules/artist-redirects', headers=headers, json={'name': 'Y', 'corrected_name': 'Premiere'}
        )
        assert refused.status_code == 400, refused.text


class ArtistImagesTest:
    def test_the_stats_count_artists_with_and_without_an_image(self, api, headers, db):
        with db.cursor() as cursor:
            cursor.executemany(
                'INSERT INTO library_artists (name) VALUES (%s)', [('Angerfist',), ('Radical Redemption',)]
            )
            cursor.execute('SELECT id FROM library_artists ORDER BY id LIMIT 1')
            artist_id = cursor.fetchone()['id']
            cursor.execute(
                "INSERT INTO library_artist_images (artist_id, source, cached_path)"
                " VALUES (%s, 'manual', '/mnt/a.jpg')",
                (artist_id,),
            )
            image_id = cursor.lastrowid
            cursor.execute('UPDATE library_artists SET primary_image_id = %s WHERE id = %s', (image_id, artist_id))
        stats = api.get('/api/artists/images/stats', headers=headers).json()
        assert stats == {'total_artists': 2, 'artists_with_images': 1, 'artists_without_images': 1}

    def test_the_manager_search_reports_which_artists_have_an_image(self, api, headers, db):
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_artists (name) VALUES ('Angerfist')")
        body = api.get('/api/artists/manage/search?only=without', headers=headers).json()
        assert body['total'] == 1
        assert body['items'][0]['has_image'] is False

    def test_a_cleared_portrait_is_left_out_of_the_bulk_run(self, api, headers, db):
        """Clearing used to set `none`, which the start-up run read as "never asked"."""
        import sys
        from unittest.mock import MagicMock

        from services.music_manager.routers import artist_images

        with db.cursor() as cursor:
            cursor.executemany('INSERT INTO library_artists (name) VALUES (%s)', [('Cleared',), ('Never Asked',)])
            cursor.execute("SELECT id FROM library_artists WHERE name = 'Cleared'")
            cleared_id = cursor.fetchone()['id']
        assert api.post(f'/api/artists/{cleared_id}/image/clear', headers=headers).status_code == 200
        with db.cursor() as cursor:
            cursor.execute('SELECT image_status FROM library_artists WHERE id = %s', (cleared_id,))
            assert cursor.fetchone()['image_status'] == 'cleared'

        fetcher_module = MagicMock()
        fetcher = fetcher_module.ArtistImageFetcher.return_value
        fetcher.blind = False
        fetcher.fetch_for_artist.return_value = False
        with patch.dict(sys.modules, {'services.music_manager.artist_image_fetcher.fetcher': fetcher_module}):
            artist_images.run_fetch_missing()
        asked = [call.args[1] for call in fetcher.fetch_for_artist.call_args_list]
        assert asked == ['Never Asked']

    def test_a_cleared_portrait_is_taken_back_from_the_server(self, api, headers, db):
        """Bug 080: the server kept the artwork it had been given, so the player kept it too."""
        import sqlite3

        from services.music_manager.routers import artist_images

        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_artists (name) VALUES ('Angerfist')")
            artist_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO library_artist_images (artist_id, source, cached_path) VALUES (%s, 'spotify', '/mnt/a.jpg')",
                (artist_id,),
            )
        assert api.post(f'/api/artists/{artist_id}/image/clear', headers=headers).status_code == 200
        server = sqlite3.connect(':memory:')
        server.executescript(
            """
            CREATE TABLE image (id INTEGER PRIMARY KEY, absolute_file_path TEXT);
            CREATE TABLE artwork (id INTEGER PRIMARY KEY, image_id INTEGER);
            CREATE TABLE artist (id INTEGER PRIMARY KEY, name TEXT, preferred_artwork_id INTEGER);
            INSERT INTO image VALUES (1, '/mnt/a.jpg');
            INSERT INTO artwork VALUES (10, 1);
            INSERT INTO artist VALUES (100, 'Angerfist', 10);
            """
        )
        try:
            assert artist_images._unset_cleared_artwork_on_server(db, server) == 1
            assert server.execute('SELECT preferred_artwork_id FROM artist').fetchone()[0] is None
        finally:
            server.close()

    def test_the_portrait_sync_writes_the_path_the_server_sees(self, db):
        """Bug 138: rows under muma's /mnt/music were removed by every LMS library scan.

        The server already indexed the portrait file itself under /music (the artists folder is
        inside its library root), and still holds a row an older sync wrote under /mnt/music.
        After the sync the artist points at the server's own row and nothing new is written
        under muma's mount.
        """
        import sqlite3

        from services.music_manager.routers import artist_images

        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_artists (name) VALUES ('Angerfist')")
            artist_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO library_artist_images (artist_id, source, cached_path, width, height, mime_type, file_size) "
                "VALUES (%s, 'spotify', '/mnt/music/artists/9/spotify-abc.jpg', 640, 640, 'image/jpeg', 1000)",
                (artist_id,),
            )
            cursor.execute(
                'UPDATE library_artists SET primary_image_id = %s WHERE id = %s', (cursor.lastrowid, artist_id)
            )
        db.commit()
        server = sqlite3.connect(':memory:')
        server.executescript(
            """
            CREATE TABLE image (id INTEGER PRIMARY KEY, version INTEGER, absolute_file_path TEXT, stem TEXT,
                                file_size INTEGER, width INTEGER, height INTEGER, mime_type TEXT);
            CREATE TABLE artwork (id INTEGER PRIMARY KEY, version INTEGER, image_id INTEGER);
            CREATE TABLE artist (id INTEGER PRIMARY KEY, name TEXT, preferred_artwork_id INTEGER);
            INSERT INTO image (id, absolute_file_path) VALUES (1, '/mnt/music/artists/9/spotify-abc.jpg'),
                                                              (2, '/music/artists/9/spotify-abc.jpg');
            INSERT INTO artwork (id, image_id) VALUES (10, 1), (20, 2);
            INSERT INTO artist VALUES (100, 'Angerfist', 10);
            """
        )
        try:
            with patch('builtins.print'):
                artist_images.sync_artist_images_to_server(db, server)
            assert server.execute('SELECT preferred_artwork_id FROM artist').fetchone()[0] == 20
            assert server.execute('SELECT count(*) FROM image').fetchone()[0] == 2
            with patch('builtins.print'):
                artist_images.sync_artist_images_to_server(db, server)
            assert server.execute('SELECT count(*) FROM image').fetchone()[0] == 2, 'a second sync writes nothing new'
        finally:
            server.close()


class FeedsPipelineTest:
    """The candidate query, its grouped audio-features subquery, the two
    bounded dominant-genre queries and the rating join -- the heavy SQL in
    feeds/build.py that READ_ENDPOINTS above never reaches.

    Against an empty schema `build_feed` reports `state='not_enough_data'`
    before it runs any of that: `resolve_profile`'s cold-start gate sees no
    listening history at all, so the candidate query, the bucketing queries
    and the ranking never execute. A 200 there proves only that the profile
    queries -- the hierarchy, the exclusions, the listens query -- parse.

    These tests seed just enough to clear every gate `build_feed` applies, in
    the order it applies them: one listen so `resolve_profile`'s profile scope
    is not `'empty'`, then a candidate carrying a media file, a positive
    duration under the policy's song ceiling, and a day-precision
    `release_date` inside the release window -- exactly what `candidates_query`
    filters on. A 500 here is what invalid SQL produces against a real
    MariaDB; a `state` other than `'ok'` with candidates surviving in the
    funnel is the naive, worthless version of this test.
    """

    def _track(self, db, title, artist='Angerfist', release_date=None, duration=320):
        with db.cursor() as cursor:
            # IGNORE: two tracks by the same artist in one test share the row
            # rather than colliding on library_artists' UNIQUE name.
            cursor.execute('INSERT IGNORE INTO library_artists (name) VALUES (%s)', (artist,))
            cursor.execute('SELECT id FROM library_artists WHERE name = %s', (artist,))
            artist_id = cursor.fetchone()['id']
            cursor.execute(
                'INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id)'
                ' VALUES (%s, %s, %s, %s)',
                (f'uid-{title}', title, duration, artist_id),
            )
            track_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO library_media_files (file_path, file_path_hash, track_id, file_mtime, file_size)'
                ' VALUES (%s, %s, %s, 1.0, 10)',
                (f'/mnt/music/{title}.mp3', f'hash-{title}', track_id),
            )
            if release_date:
                cursor.execute(
                    'INSERT INTO library_track_audio_features (track_id, internal_track_id, release_date)'
                    ' VALUES (%s, %s, %s)',
                    (f'af-{track_id}', track_id, release_date),
                )
        return track_id

    def _listen(self, db, track_id, username='root'):
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO scrobble_listens (track_id, listened_at, username, match_method)"
                " VALUES (%s, NOW(), %s, 'exact')",
                (track_id, username),
            )

    def test_release_radar_runs_its_candidate_query_against_a_real_schema(self, api, headers, db):
        today = date.today().isoformat()
        track_id = self._track(db, 'New Single', release_date=today)
        # Clears resolve_profile's cold-start gate: without at least one listen
        # in the profile window, profile.scope stays 'empty' and build_feed
        # returns before candidates_query is ever run.
        self._listen(db, track_id)

        response = api.get('/api/feeds/release-radar?username=root', headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['state'] == 'ok', body
        assert body['funnel']['candidates'] >= 1, body['funnel']
        assert body['funnel']['emitted'] >= 1, body['funnel']
        assert [track['title'] for track in body['tracks']] == ['New Single']

    def test_release_radar_window_is_a_sql_filter_not_a_python_one(self, api, headers, db):
        """Proves the release_date bounds in candidates_query's WHERE clause
        actually run, rather than merely parsing: a release well outside the
        7-day window must not come back, and only a real database can reject
        it -- the unit suite's mocked cursor returns whatever it is told to."""
        in_window = self._track(db, 'New Single', release_date=date.today().isoformat())
        self._listen(db, in_window)
        out_of_window = self._track(db, 'Old Single', release_date=(date.today() - timedelta(days=30)).isoformat())

        body = api.get('/api/feeds/release-radar?username=root', headers=headers).json()
        assert body['state'] == 'ok', body
        assert [track['title'] for track in body['tracks']] == ['New Single']
        assert out_of_window not in [track['id'] for track in body['tracks']]

    def test_release_radar_leaves_an_interview_out(self, api, headers, db):
        """docs/designs/non-music-forms/: the form condition runs on MariaDB, drops the
        interview and keeps a track the form pass has not classified yet (form NULL)."""
        today = date.today().isoformat()
        song = self._track(db, 'New Single', release_date=today)
        self._listen(db, song)
        self._track(db, 'Unclassified Single', artist='Radical Redemption', release_date=today)
        interview = self._track(db, 'QAPITAL 2019 Interview', artist='Rejecta', release_date=today)
        with db.cursor() as cursor:
            cursor.execute("UPDATE library_tracks SET form = 'track' WHERE id = %s", (song,))
            cursor.execute("UPDATE library_tracks SET form = 'interview' WHERE id = %s", (interview,))

        body = api.get('/api/feeds/release-radar?username=root', headers=headers).json()
        assert body['state'] == 'ok', body
        assert sorted(track['title'] for track in body['tracks']) == ['New Single', 'Unclassified Single']

    def test_daily_mix_runs_its_unheard_pool_clause_against_a_real_schema(self, api, headers, db):
        """daily-mix's policy differs from release-radar's in exactly the ways
        that matter for SQL coverage: a 90-day window, the 'unheard' pool's
        NOT EXISTS clause in candidates_query, and the daily_sample order --
        so this exercises the query text release-radar's tests never reach."""
        heard_id = self._track(db, 'Old Favourite', release_date=date.today().isoformat())
        self._listen(db, heard_id)
        self._track(db, 'Unheard Gem', release_date=date.today().isoformat())

        response = api.get('/api/feeds/daily-mix?username=root', headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['state'] == 'ok', body
        assert body['funnel']['candidates'] >= 1, body['funnel']
        assert body['funnel']['emitted'] >= 1, body['funnel']
        # 'Old Favourite' fails both halves of the 'unheard'-or-'loved' pool: it
        # has been listened to, and nothing here carries a rating_tracks row --
        # so only the never-heard candidate should come back.
        assert [track['title'] for track in body['tracks']] == ['Unheard Gem']

    def test_daily_mix_samples_older_songs_that_match_the_profile(self, api, headers, db):
        """Bug report 131: older_candidates_query and last_listened_query parse on MariaDB,
        and the older half is profile-matched and drops songs rated 1-2 while keeping
        unrated ones -- heard or not -- that a 90-day window used to hide."""
        heard = [self._track(db, f'Angerfist heard {i}', release_date='2014-02-02') for i in range(2)]
        for track_id in heard:
            self._listen(db, track_id)
        # Another artist, so the per-artist cap on the four Angerfist songs cannot drop it.
        self._track(db, 'New Gem', artist='Fresh Face', release_date=date.today().isoformat())
        self._track(db, 'Old Gem', release_date='2015-06-01')
        self._track(db, 'Undated Gem')
        self._track(db, 'Old Dud', release_date='2015-06-01')
        self._track(db, 'Stranger Gem', artist='Somebody Else', release_date='2015-06-01')
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO rating_tracks (entity_type, entity_id, username, rating) VALUES "
                "('track', 'uid-Old Dud', 'root', 2), ('track', 'uid-Old Gem', 'root', 3)"
            )

        response = api.get('/api/feeds/daily-mix?username=root', headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['state'] == 'ok', body
        titles = {track['title'] for track in body['tracks']}
        # Three per artist: the cap trims the four Angerfist songs, so ask what may and may not appear.
        # 'Undated Gem' has no agreed release date: not provably older, so not in the older half.
        assert titles <= {'New Gem', 'Old Gem', 'Angerfist heard 0', 'Angerfist heard 1'}, titles
        assert 'New Gem' in titles, titles
        assert 'Old Dud' not in titles and 'Stranger Gem' not in titles, titles
        assert body['pool_counts']['recent'] == 1, body['pool_counts']
        assert body['pool_counts']['older'] >= 1, body['pool_counts']

    def _artist_with_history(self, db, artist, playable):
        """Two heard tracks (enough for the profile to know `artist`) plus `playable`
        unheard ones with no release date -- only reachable with no window at all."""
        for index in range(2):
            self._listen(db, self._track(db, f'{artist} heard {index}', artist=artist))
        for index in range(playable):
            self._track(db, f'{artist} unheard {index}', artist=artist)

    def test_artist_mix_counts_its_top_ten_and_widens_the_window(self, api, headers, db):
        """Bug report 110: rotation_counts_query parses on MariaDB, counts what the
        candidate query then returns, and the mix is built at the widened window."""
        self._artist_with_history(db, 'Angerfist', playable=15)

        response = api.get('/api/feeds/daily-mix-artist?username=root', headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['state'] == 'ok', body
        assert body['title'] == 'angerfist'
        assert body['relaxed_to'] == 'none'
        assert body['funnel']['candidates'] == 15, body['funnel']
        # Not cut to max_per_artist: every track of an artist mix has one artist.
        assert body['funnel']['emitted'] == 15, body['funnel']

    def test_artist_mix_below_the_minimum_is_empty_not_near_empty(self, api, headers, db):
        self._artist_with_history(db, 'Angerfist', playable=14)

        body = api.get('/api/feeds/daily-mix-artist?username=root', headers=headers).json()
        assert body['state'] == 'no_matches', body
        assert body['tracks'] == []
        assert body['title'] == 'Artiestmix'

    def test_a_continuation_is_stored_back_into_the_snapshot(self, api, headers, db, monkeypatch):
        """docs/designs/feed-length/: a page past the stored list runs a second, bigger
        build and writes the row back through the same INSERT ... ON DUPLICATE KEY
        UPDATE; once nothing new comes it is marked exhausted, and the next read of
        the head -- served from the row -- no longer offers a next page.

        Twelve tracks by one artist at a length of 10: the quota hands out all ten places,
        the per-artist cap keeps three, so the head is short without having run out -- the
        one shape a continuation build is attempted for. Release Radar, because a split
        daily mix continues from its stored reserve instead (the test below)."""
        from services.music_manager.routers import feeds as feeds_router

        real_get = feeds_router.settings.get
        monkeypatch.setattr(
            feeds_router.settings, 'get', lambda key, *rest: 10 if key == 'feeds_size' else real_get(key, *rest)
        )
        heard_id = self._track(db, 'Old Favourite', release_date=date.today().isoformat())
        self._listen(db, heard_id)
        for index in range(12):
            self._track(db, f'Unheard {index}', release_date=date.today().isoformat())

        head = api.get('/api/feeds/release-radar?username=root', headers=headers).json()
        assert head['state'] == 'ok', head
        assert (len(head['tracks']), head['next_offset']) == (3, 3), head['funnel']
        assert 'work_id' in head['tracks'][0]

        response = api.get('/api/feeds/release-radar?username=root&offset=3', headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers['X-MuMa-Feed-Source'] == 'extended'
        past = response.json()
        assert (past['tracks'], past['next_offset']) == ([], None)

        again = api.get('/api/feeds/release-radar?username=root', headers=headers)
        assert again.headers['X-MuMa-Feed-Source'] == 'snapshot'
        assert (len(again.json()['tracks']), again.json()['next_offset']) == (3, None)

    def test_a_split_daily_mix_continues_from_its_stored_reserve(self, api, headers, db, monkeypatch):
        """Issue #137: the head build stores the rest of a MAX_FEED_LENGTH ranking in the
        row, and the next page comes off it through the same write-back -- no build."""
        from services.music_manager.routers import feeds as feeds_router

        real_get = feeds_router.settings.get
        monkeypatch.setattr(
            feeds_router.settings, 'get', lambda key, *rest: 10 if key == 'feeds_size' else real_get(key, *rest)
        )
        heard_id = self._track(db, 'Old Favourite', release_date=date.today().isoformat())
        self._listen(db, heard_id)
        for index in range(25):
            self._track(db, f'Unheard {index}', artist=f'Artist {index}', release_date=date.today().isoformat())

        head = api.get('/api/feeds/daily-mix?username=root', headers=headers).json()
        assert head['state'] == 'ok', head
        assert (len(head['tracks']), head['next_offset']) == (10, 10), head['funnel']
        assert 'reserve' not in head

        monkeypatch.setattr(feeds_router, 'build_feed', lambda *a, **k: pytest.fail('a continuation built a feed'))
        response = api.get('/api/feeds/daily-mix?username=root&offset=10', headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers['X-MuMa-Feed-Source'] == 'extended'
        page = response.json()
        assert len(page['tracks']) == 10, page
        assert not {t['id'] for t in page['tracks']} & {t['id'] for t in head['tracks']}

        rest = api.get('/api/feeds/daily-mix?username=root&offset=20', headers=headers).json()
        assert (len(rest['tracks']), rest['next_offset']) == (5, None), rest


class FeedsProfileAndExclusionsTest:
    """`GET /api/feeds/profile` and `PUT /api/feeds/profile/exclusions`
    against the real `feeds_profile_exclusions` table -- created by
    `feeds.init_db`, which only runs as part of the app's own startup event,
    not `tests/integration/conftest.py`'s `_apply_schema` (see that module's
    `_apply_schema` docstring). If that table were ever missing from a real
    deploy, this is where it would show up as a 500."""

    def test_an_exclusion_is_written_read_back_and_removed(self, api, headers, db):
        excluded = api.put(
            '/api/feeds/profile/exclusions?username=root',
            headers=headers,
            json={'entity_type': 'artist', 'entity_name': 'Angerfist', 'excluded': True},
        )
        assert excluded.status_code == 200, excluded.text

        profile = api.get('/api/feeds/profile?username=root', headers=headers).json()
        assert profile['excluded'] == [{'entity_type': 'artist', 'entity_name': 'angerfist'}]

        removed = api.put(
            '/api/feeds/profile/exclusions?username=root',
            headers=headers,
            json={'entity_type': 'artist', 'entity_name': 'Angerfist', 'excluded': False},
        )
        assert removed.status_code == 200, removed.text
        assert api.get('/api/feeds/profile?username=root', headers=headers).json()['excluded'] == []


class NewsSqlTest:
    """The news source and bulletin SQL against the real schema, which news.init_db creates."""

    def _source(self, db, slug='bnr'):
        with db.cursor() as cursor:
            cursor.execute(
                'INSERT INTO news_sources (slug, name, stream_url) VALUES (%s, %s, %s)',
                (slug, slug.upper(), f'http://stream.test/{slug}'),
            )
            return cursor.lastrowid

    def _bulletin(self, db, source_id, started_at, filename):
        with db.cursor() as cursor:
            cursor.execute(
                'INSERT INTO news_bulletins (source_id, started_at, duration_ms, size_bytes, filename)'
                ' VALUES (%s, %s, %s, %s, %s)',
                (source_id, started_at, 612000, 10, filename),
            )

    def test_bulletins_are_listed_newest_first_and_the_latest_is_found(self, api, headers, db):
        source_id = self._source(db)
        self._bulletin(db, source_id, 1787248800.0, 'bnr-2026-08-20T18-00-00.mp3')
        self._bulletin(db, source_id, 1787252400.0, 'bnr-2026-08-20T19-00-00.mp3')

        listed = api.get('/api/news/bulletins?source=bnr', headers=headers).json()['bulletins']
        assert [b['started_at'] for b in listed] == [1787252400.0, 1787248800.0]
        latest = api.get('/api/news/bulletins/latest?source=bnr', headers=headers).json()
        assert latest['started_at'] == 1787252400.0

    def test_a_source_is_listed_with_its_settings(self, api, headers, db):
        self._source(db)
        sources = api.get('/api/news/sources', headers=headers).json()['sources']
        bnr = next(s for s in sources if s['slug'] == 'bnr')
        assert bnr['retention_count'] == 12
        assert bnr['enabled'] is True

    def test_prune_keeps_the_newest_retention_count(self, db, tmp_path, monkeypatch):
        from services.music_manager.routers import news

        monkeypatch.setenv('NEWS_DATA_DIR', str(tmp_path))
        source_id = self._source(db)
        for hour in range(3):
            self._bulletin(db, source_id, 1787248800.0 + hour * 3600, f'bnr-{hour}.mp3')
            (tmp_path / f'bnr-{hour}.mp3').write_bytes(b'x')

        removed = news.prune_bulletins(db, {'id': source_id, 'retention_count': 1})

        assert removed == 2
        assert sorted(p.name for p in tmp_path.iterdir()) == ['bnr-2.mp3']

    def test_deleting_a_source_removes_its_rows_and_files(self, api, headers, db, tmp_path, monkeypatch):
        monkeypatch.setenv('NEWS_DATA_DIR', str(tmp_path))
        source_id = self._source(db)
        self._bulletin(db, source_id, 1787248800.0, 'bnr-a.mp3')
        (tmp_path / 'bnr-a.mp3').write_bytes(b'x')

        response = api.delete('/api/news/sources/bnr', headers=headers)

        assert response.status_code == 200, response.text
        assert list(tmp_path.iterdir()) == []
        with db.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) AS n FROM news_bulletins WHERE source_id = %s', (source_id,))
            assert cursor.fetchone()['n'] == 0

    def test_a_failing_source_delete_keeps_the_bulletin_rows(self, api, headers, db, tmp_path, monkeypatch):
        """Bug report 113: the bulletin DELETE is rolled back on the real server, and no file goes."""
        monkeypatch.setenv('NEWS_DATA_DIR', str(tmp_path))
        source_id = self._source(db)
        self._bulletin(db, source_id, 1787248800.0, 'bnr-a.mp3')
        (tmp_path / 'bnr-a.mp3').write_bytes(b'x')
        fail_on_statement(monkeypatch, 'DELETE FROM news_sources')

        with pytest.raises(RuntimeError):
            api.delete('/api/news/sources/bnr', headers=headers)

        assert [p.name for p in tmp_path.iterdir()] == ['bnr-a.mp3']
        with db.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) AS n FROM news_bulletins WHERE source_id = %s', (source_id,))
            assert cursor.fetchone()['n'] == 1
            cursor.execute('SELECT COUNT(*) AS n FROM news_sources WHERE id = %s', (source_id,))
            assert cursor.fetchone()['n'] == 1


def fail_on_statement(monkeypatch, prefix):
    """Make every pymysql statement starting with `prefix` raise, the way a lost connection would.

    Patched on the cursor class, so it reaches the app's pooled connections too.
    """
    original = pymysql.cursors.Cursor.execute

    def execute(self, query, args=None):
        if ' '.join(str(query).split()).startswith(prefix):
            raise RuntimeError(f'simulated failure on: {prefix}')
        return original(self, query, args)

    monkeypatch.setattr(pymysql.cursors.Cursor, 'execute', execute)


class ParentChildDeleteSqlTest:
    """The parent-then-children deletes of bug report 113 against the real server."""

    @staticmethod
    def _channel(db):
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO radio_channels (slug, name) VALUES ('qdance', 'Q-dance')")
            channel_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO radio_timeline (channel_id, track_id, duration_ms, started_at, ends_at)'
                " VALUES (%s, 'tr-1', 200000, 1787248800.0, 1787249000.0)",
                (channel_id,),
            )
        return channel_id

    @staticmethod
    def _count(db, sql, params):
        with db.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()['n']

    def test_deleting_a_channel_takes_its_timeline(self, api, headers, db):
        channel_id = self._channel(db)
        response = api.delete('/api/radio/channels/qdance', headers=headers)
        assert response.status_code == 200, response.text
        assert self._count(db, 'SELECT COUNT(*) AS n FROM radio_timeline WHERE channel_id = %s', (channel_id,)) == 0
        assert self._count(db, 'SELECT COUNT(*) AS n FROM radio_channels WHERE id = %s', (channel_id,)) == 0

    def test_a_failing_channel_delete_keeps_the_timeline(self, api, headers, db, monkeypatch):
        channel_id = self._channel(db)
        fail_on_statement(monkeypatch, 'DELETE FROM radio_channels')
        with pytest.raises(RuntimeError):
            api.delete('/api/radio/channels/qdance', headers=headers)
        assert self._count(db, 'SELECT COUNT(*) AS n FROM radio_timeline WHERE channel_id = %s', (channel_id,)) == 1

    @staticmethod
    def _shows(db):
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO rules_podcasts (name, normalized_name) VALUES ('DJ Isaac Sessions', 'dj isaac sessions')"
            )
            source = cursor.lastrowid
            cursor.execute(
                "INSERT INTO rules_podcasts (name, normalized_name) VALUES ('Hardstyle Sessions', 'hardstyle sessions')"
            )
            target = cursor.lastrowid
            cursor.execute(
                'INSERT INTO rules_podcast_aliases (podcast_id, alias, normalized_alias)'
                " VALUES (%s, 'DJ ISAAC - SESSIONS', 'dj isaac sessions alias')",
                (source,),
            )
        return source, target

    def test_a_podcast_merge_moves_the_spellings_and_drops_the_row(self, api, headers, db):
        source, target = self._shows(db)
        response = api.post(
            f'/api/rules/podcasts/{source}/decide',
            headers=headers,
            json={'state': 'white', 'merge_into_podcast_id': target},
        )
        assert response.status_code == 200, response.text
        assert self._count(db, 'SELECT COUNT(*) AS n FROM rules_podcasts WHERE id = %s', (source,)) == 0
        assert self._count(db, 'SELECT COUNT(*) AS n FROM rules_podcast_aliases WHERE podcast_id = %s', (target,)) == 2

    def test_a_failing_podcast_merge_leaves_the_spellings_with_the_show(self, api, headers, db, monkeypatch):
        source, target = self._shows(db)
        fail_on_statement(monkeypatch, 'DELETE FROM rules_podcasts')
        with pytest.raises(RuntimeError):
            api.post(
                f'/api/rules/podcasts/{source}/decide',
                headers=headers,
                json={'state': 'white', 'merge_into_podcast_id': target},
            )
        assert self._count(db, 'SELECT COUNT(*) AS n FROM rules_podcast_aliases WHERE podcast_id = %s', (source,)) == 1
        assert self._count(db, 'SELECT COUNT(*) AS n FROM rules_podcast_aliases WHERE podcast_id = %s', (target,)) == 0


class MultiStatementWriteSqlTest:
    """The multi-statement writes of bug report 115 against the real server.

    Each test makes the last statement of a write raise inside pymysql and checks that the
    earlier ones did not land either.
    """

    @staticmethod
    def _one(db, sql, params=()):
        with db.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def test_a_failing_label_verdict_leaves_no_rule_behind(self, api, headers, db, monkeypatch):
        run_sql(db, "INSERT INTO rules_label_proposals (folder, catid) VALUES ('BKRP104 - Darwin', 'BKRP')")
        proposal_id = self._one(db, 'SELECT id FROM rules_label_proposals')['id']
        url = f'/api/label-proposals/{proposal_id}/confirm'
        with monkeypatch.context() as patcher:
            fail_on_statement(patcher, "UPDATE rules_label_proposals SET status = 'confirmed'")
            with pytest.raises(RuntimeError):
                api.post(url, headers=headers, json={'label': 'Brutal Kuts'})
        assert self._one(db, 'SELECT COUNT(*) AS n FROM rules_catid_label')['n'] == 0
        assert self._one(db, 'SELECT status FROM rules_label_proposals')['status'] == 'new'

        # And the retry lands both.
        confirmed = api.post(url, headers=headers, json={'label': 'Brutal Kuts'})
        assert confirmed.status_code == 200, confirmed.text
        assert (
            self._one(db, 'SELECT label FROM rules_catid_label WHERE catid = %s', ('BKRP',))['label'] == 'Brutal Kuts'
        )
        assert self._one(db, 'SELECT status FROM rules_label_proposals')['status'] == 'confirmed'

    def test_a_two_option_proposal_lists_both_and_its_confirmation_records_the_choice(self, api, headers, db):
        run_sql(
            db,
            "INSERT INTO rules_label_name_choices (nfo_label_key, nfo_label, name_folder, history_folder) "
            "VALUES ('cloud9', 'Cloud 9 Music', 'Cloud 9 Music', 'Cloud 9 Dance') "
            'ON DUPLICATE KEY UPDATE chosen_folder = NULL',
        )
        run_sql(
            db,
            "INSERT INTO rules_label_proposals (folder, catid, proposed_label, source, alternative_label, "
            "label_choice_key) VALUES ('CLDM2025001 - VA', 'CLDM2025001', 'Cloud 9 Music', 'nfo-vs-history', "
            "'Cloud 9 Dance', 'cloud9')",
        )
        listed = api.get('/api/label-proposals', headers=headers)
        assert listed.status_code == 200, listed.text
        row = next(r for r in listed.json() if r['folder'] == 'CLDM2025001 - VA')
        assert (row['alternative_label'], row['label_choice_key']) == ('Cloud 9 Dance', 'cloud9')
        confirmed = api.post(
            f"/api/label-proposals/{row['id']}/confirm", headers=headers, json={'label': 'Cloud 9 Dance'}
        )
        assert confirmed.status_code == 200, confirmed.text
        chosen = self._one(db, "SELECT chosen_folder FROM rules_label_name_choices WHERE nfo_label_key = 'cloud9'")
        assert chosen['chosen_folder'] == 'Cloud 9 Dance'

    def test_a_failing_alias_insert_keeps_the_old_show_name(self, api, headers, db, monkeypatch):
        run_sql(
            db,
            "INSERT INTO rules_podcasts (name, normalized_name) VALUES ('KELTEK Presents Pure Hardstyle', 'keltek presents pure hardstyle')",
        )
        podcast_id = self._one(db, 'SELECT id FROM rules_podcasts')['id']
        fail_on_statement(monkeypatch, 'INSERT IGNORE INTO rules_podcast_aliases')
        with pytest.raises(RuntimeError):
            api.post(f'/api/rules/podcasts/{podcast_id}/rename', headers=headers, json={'name': 'Pure Hardstyle'})
        assert self._one(db, 'SELECT name FROM rules_podcasts')['name'] == 'KELTEK Presents Pure Hardstyle'

    @staticmethod
    def _artist_with_two_images(db):
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO library_artists (name) VALUES ('Angerfist')")
            artist_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO library_artist_images (artist_id, source, cached_path, is_primary)"
                " VALUES (%s, 'spotify', '/mnt/old.jpg', 1)",
                (artist_id,),
            )
            old = cursor.lastrowid
            cursor.execute(
                "INSERT INTO library_artist_images (artist_id, source, cached_path, is_primary)"
                " VALUES (%s, 'lastfm', '/mnt/new.jpg', 0)",
                (artist_id,),
            )
            new = cursor.lastrowid
            cursor.execute(
                "UPDATE library_artists SET primary_image_id = %s, image_status = 'active' WHERE id = %s",
                (old, artist_id),
            )
        return artist_id, old, new

    def _primary_flags(self, db, artist_id):
        with db.cursor() as cursor:
            cursor.execute(
                'SELECT id FROM library_artist_images WHERE artist_id = %s AND is_primary = 1 ORDER BY id', (artist_id,)
            )
            return [row['id'] for row in cursor.fetchall()]

    def test_a_failing_pointer_update_keeps_the_old_primary_image(self, api, headers, db, monkeypatch):
        artist_id, old, new = self._artist_with_two_images(db)
        fail_on_statement(monkeypatch, 'UPDATE library_artists SET primary_image_id')
        with pytest.raises(RuntimeError):
            api.post(f'/api/artists/{artist_id}/image/select/{new}', headers=headers)
        assert self._primary_flags(db, artist_id) == [old]
        pointer = self._one(db, 'SELECT primary_image_id FROM library_artists WHERE id = %s', (artist_id,))
        assert pointer['primary_image_id'] == old

    def test_a_failing_pointer_clear_keeps_the_primary_flag(self, api, headers, db, monkeypatch):
        artist_id, old, _new = self._artist_with_two_images(db)
        fail_on_statement(monkeypatch, 'UPDATE library_artists SET primary_image_id')
        with pytest.raises(RuntimeError):
            api.post(f'/api/artists/{artist_id}/image/clear', headers=headers)
        assert self._primary_flags(db, artist_id) == [old]

    def test_the_fetcher_rolls_its_primary_flags_back_on_its_own_connection(self, db, monkeypatch):
        """The CLI's connection is not the pool's: a plain pymysql connection, autocommit off."""
        from services.music_manager.artist_image_fetcher.fetcher import ArtistImageFetcher

        artist_id, old, new = self._artist_with_two_images(db)
        connection = _connect()
        connection.autocommit(False)
        try:
            fetcher = ArtistImageFetcher.__new__(ArtistImageFetcher)
            fetcher.db_conn = connection
            fail_on_statement(monkeypatch, 'UPDATE library_artists SET primary_image_id')
            with pytest.raises(RuntimeError):
                fetcher._set_primary_image(artist_id, new)
            # What the next artist's commit used to publish: the half-done flags.
            connection.commit()
        finally:
            connection.close()
        assert self._primary_flags(db, artist_id) == [old]

    def test_a_failing_audit_row_keeps_the_sessions(self, api, headers, db, monkeypatch):
        user_id = api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'}).json()['id']
        run_sql(db, "UPDATE users SET api_key = 'still-valid' WHERE id = %s", (user_id,))
        run_sql(db, "INSERT INTO user_refresh_tokens (user_id, token) VALUES (%s, 'refresh-1')", (user_id,))
        fail_on_statement(monkeypatch, 'INSERT INTO audit_events')
        with pytest.raises(RuntimeError):
            api.post(f'/api/users/{user_id}/sessions/revoke', headers=headers)
        assert self._one(db, 'SELECT api_key FROM users WHERE id = %s', (user_id,))['api_key'] == 'still-valid'
        assert self._one(db, 'SELECT revoked_at FROM user_refresh_tokens')['revoked_at'] is None


class ScrobbleReconcileSqlTest:
    """GET /api/scrobble/reconcile/lms runs every muma-side query against the real schema.

    An empty SQLite with LMS's `user`, `track` and `listen` columns stands in for `lms.db`; the
    seeded listen makes the path lookup against `library_media_files` run too.
    """

    def test_the_dry_run_sql_runs(self, api, headers, db, tmp_path, monkeypatch):
        import sqlite3

        path = tmp_path / 'lms.db'
        lms = sqlite3.connect(path)
        lms.execute('CREATE TABLE user (id INTEGER PRIMARY KEY, login_name TEXT)')
        lms.execute('CREATE TABLE track (id INTEGER PRIMARY KEY, absolute_file_path TEXT)')
        lms.execute(
            'CREATE TABLE listen (id INTEGER PRIMARY KEY, date_time TEXT, backend INTEGER, '
            'sync_state INTEGER, user_id INTEGER, track_id INTEGER)'
        )
        lms.execute("INSERT INTO user (login_name) VALUES ('root')")
        lms.execute("INSERT INTO track (absolute_file_path) VALUES ('/music/a.mp3')")
        lms.execute(
            "INSERT INTO listen (date_time, backend, sync_state, user_id, track_id) VALUES ('2026-08-21T19:02:05.000', 0, 1, 1, 1)"
        )
        lms.commit()
        lms.close()
        monkeypatch.setenv('MUMA_SERVER_DB_PATH', str(path))
        monkeypatch.setenv('MUMA_SERVER_DB_ROOT', str(tmp_path / 'none'))

        for query in ('', '?username=root'):
            response = api.get(f'/api/scrobble/reconcile/lms{query}', headers=headers)
            assert response.status_code == 200, response.text
            assert response.json()['totals']['lms_unmapped'] == 1

        # The `lms-listen-backfill` loop's windowed reads (bug report 075): LMS's `julianday`
        # bound, and muma's listened_at-or-created_at bound on both listen tables.
        from datetime import UTC, datetime

        from services.music_manager import lms_listen_backfill

        now = int(datetime(2026, 8, 22, tzinfo=UTC).timestamp())
        # Like apply(), the backfill refuses to write unless process and database share a zone;
        # the test database runs in UTC, as the music-manager image does.
        monkeypatch.setenv('TZ', 'UTC')
        time.tzset()
        try:
            result = lms_listen_backfill.run_once(now, 48 * 3600)
        finally:
            monkeypatch.undo()
            time.tzset()
        assert result['found']['lms_unmapped'] == 1
        assert result['written'] == {'lms_only_inserted': 0, 'collisions': 0}


class SubsonicTokenSqlTest:
    """GET /api/auth/subsonic-token with a real user key: MariaDB resolves the account, an lms.db
    file with LMS's `user` and `auth_token` columns receives the token (bug report 103)."""

    def test_a_user_key_gets_a_token_written_into_lms_db(self, api, db, tmp_path, monkeypatch):
        import sqlite3

        with db.cursor() as cursor:
            cursor.execute("INSERT INTO users (username, api_key, enabled) VALUES ('listener', 'listener-key', TRUE)")
            cursor.execute("SELECT id FROM users WHERE username = 'listener'")
            muma_id = cursor.fetchone()['id']
        db.commit()

        path = tmp_path / 'lms.db'
        lms = sqlite3.connect(path)
        lms.execute('CREATE TABLE user (id INTEGER PRIMARY KEY, login_name TEXT, muma_id INTEGER)')
        lms.execute('CREATE TABLE track (id INTEGER PRIMARY KEY, absolute_file_path TEXT)')
        lms.execute('CREATE TABLE listen (id INTEGER PRIMARY KEY, user_id INTEGER, track_id INTEGER)')
        lms.execute(
            'CREATE TABLE auth_token (id INTEGER PRIMARY KEY AUTOINCREMENT, version INTEGER NOT NULL DEFAULT 0, '
            "domain TEXT NOT NULL DEFAULT '', value TEXT NOT NULL DEFAULT '', expiry DATETIME, "
            'use_count INTEGER NOT NULL DEFAULT 0, last_used TEXT, max_use_count INTEGER, user_id INTEGER)'
        )
        lms.execute('INSERT INTO user (login_name, muma_id) VALUES (?, ?)', ('listener', muma_id))
        lms.commit()
        lms.close()
        monkeypatch.setenv('MUMA_SERVER_DB_PATH', str(path))
        monkeypatch.setenv('MUMA_SERVER_DB_ROOT', str(tmp_path / 'none'))

        response = api.get('/api/auth/subsonic-token', headers={'x-api-key': 'listener-key'})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body['username'] == 'listener'
        lms = sqlite3.connect(path)
        stored = lms.execute("SELECT value FROM auth_token WHERE domain = 'subsonic'").fetchall()
        lms.close()
        assert stored == [(body['token'],)]


class TransactionTest:
    """`database.transaction` against the real server: a rolled-back DELETE leaves its rows.

    The pool runs autocommit, so these prove the two things the unit tests cannot: that
    `begin()` really suspends autocommit on MariaDB, and that a connection DBUtils hands
    back after a rollback -- or after being closed mid-transaction -- is clean again.
    """

    SEED = (('Industrial Hardcore', 'Hardcore'), ('Industrial Hardcore', 'Terror'))

    def _seed(self, db):
        with db.cursor() as cursor:
            cursor.executemany('INSERT INTO rules_subgenre_hierarchy (subgenre, genre) VALUES (%s, %s)', self.SEED)

    @staticmethod
    def _parents(db):
        """What a separate connection sees: only committed rows."""
        with db.cursor() as cursor:
            cursor.execute("SELECT genre FROM rules_subgenre_hierarchy WHERE subgenre = 'Industrial Hardcore'")
            return sorted(row['genre'] for row in cursor.fetchall())

    @staticmethod
    def _pool():
        from dbutils.pooled_db import PooledDB

        from tests.integration.conftest import _connection_settings

        return PooledDB(
            creator=pymysql,
            maxconnections=1,
            mincached=0,
            maxcached=1,
            maxshared=0,
            blocking=False,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            **_connection_settings(),
        )

    def test_a_failure_after_the_delete_leaves_every_row_in_place(self, db):
        from services.music_manager.database import transaction

        self._seed(db)
        conn = _connect()
        try:
            with pytest.raises(RuntimeError), transaction(conn), conn.cursor() as cursor:
                cursor.execute("DELETE FROM rules_subgenre_hierarchy WHERE subgenre = 'Industrial Hardcore'")
                # Mid-transaction another connection still sees the old rows; under plain
                # autocommit they would already be gone.
                assert self._parents(db) == ['Hardcore', 'Terror']
                raise RuntimeError('crash between the DELETE and the INSERTs')
        finally:
            conn.close()
        assert self._parents(db) == ['Hardcore', 'Terror']

    def test_a_completed_block_replaces_the_rows_for_everyone(self, db):
        from services.music_manager.database import transaction

        self._seed(db)
        conn = _connect()
        try:
            with transaction(conn), conn.cursor() as cursor:
                cursor.execute("DELETE FROM rules_subgenre_hierarchy WHERE subgenre = 'Industrial Hardcore'")
                cursor.execute(
                    "INSERT INTO rules_subgenre_hierarchy (subgenre, genre) VALUES ('Industrial Hardcore', 'Hardcore')"
                )
        finally:
            conn.close()
        assert self._parents(db) == ['Hardcore']

    def test_a_pooled_connection_is_clean_after_a_rollback(self, db):
        from services.music_manager.database import transaction

        self._seed(db)
        pool = self._pool()
        conn = pool.connection()
        with pytest.raises(RuntimeError), transaction(conn), conn.cursor() as cursor:
            cursor.execute("DELETE FROM rules_subgenre_hierarchy WHERE subgenre = 'Industrial Hardcore'")
            raise RuntimeError('crash')
        conn.close()

        again = pool.connection()  # maxconnections=1: the very same connection
        try:
            with again.cursor() as cursor:
                cursor.execute('SELECT @@autocommit AS autocommit, @@in_transaction AS in_transaction')
                state = cursor.fetchone()
                assert (int(state['autocommit']), int(state['in_transaction'])) == (1, 0)
                # Autocommit really is back: a single statement is visible at once.
                cursor.execute("DELETE FROM rules_subgenre_hierarchy WHERE genre = 'Terror'")
            assert self._parents(db) == ['Hardcore']
        finally:
            again.close()
            pool.close()

    def test_a_connection_closed_mid_transaction_is_rolled_back_by_the_pool(self, db):
        self._seed(db)
        pool = self._pool()
        conn = pool.connection()
        conn.begin()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM rules_subgenre_hierarchy WHERE subgenre = 'Industrial Hardcore'")
        conn.close()  # back to the pool without commit or rollback
        try:
            assert self._parents(db) == ['Hardcore', 'Terror']
        finally:
            pool.close()

    def test_a_festival_update_that_fails_half_way_keeps_its_aliases(self, api, headers, db):
        """End to end: the alias INSERT fails after the DELETE ran (strict mode refuses
        an alias longer than the column), and the old alias and name survive."""
        created = api.post('/api/rules/festivals', headers=headers, json={'name': 'Defqon.1', 'aliases': ['Defqon']})
        assert created.status_code == 201, created.text
        festival_id = created.json()['id']

        with pytest.raises(pymysql.err.MySQLError):
            api.put(
                f'/api/rules/festivals/{festival_id}',
                headers=headers,
                json={'name': 'Renamed', 'aliases': ['x' * 300]},
            )

        festival = next(
            row for row in api.get('/api/rules/festivals', headers=headers).json() if row['id'] == festival_id
        )
        assert festival['name'] == 'Defqon.1'
        assert festival['aliases'] == ['Defqon']


class EventsRetentionSqlTest:
    """The retention pass against a real events table: per-level windows, primary-key batches, size cap."""

    def _event(self, db, level, days_old):
        run_sql(
            db,
            'INSERT INTO events (created_at, level, source, logger, title) '
            "VALUES (NOW(3) - INTERVAL %s DAY, %s, 'music-manager', 'test', 'retention')",
            (days_old, level),
        )

    def _levels(self, db):
        return [row['level'] for row in run_sql(db, 'SELECT level FROM events ORDER BY level, created_at')]

    def test_each_level_keeps_its_own_window_in_batches(self, db):
        from services.music_manager import events_retention

        days = {'DEBUG': 3, 'INFO': 14, 'WARNING': 30, 'ERROR': 90, 'CRITICAL': 365}
        for level, window in days.items():
            self._event(db, level, window - 1)
            for _ in range(3):
                self._event(db, level, window + 1)

        with patch.object(events_retention, 'BATCH_SIZE', 2):
            result = events_retention.purge_once(db, days, 0, sleep=lambda _s: None)

        assert result.complete
        assert result.by_age == dict.fromkeys(days, 3)
        assert self._levels(db) == ['CRITICAL', 'DEBUG', 'ERROR', 'INFO', 'WARNING']

    def test_the_size_cap_counts_and_removes_the_oldest_noise(self, db):
        from services.music_manager import events_retention

        days = {'DEBUG': 3, 'INFO': 14, 'WARNING': 30, 'ERROR': 90, 'CRITICAL': 365}
        for age in (1, 2, 3):
            self._event(db, 'INFO', age)
            self._event(db, 'CRITICAL', age)

        # The cap reads InnoDB's row estimate first; make it current for a table this small.
        run_sql(db, 'ANALYZE TABLE events')
        result = events_retention.purge_once(db, days, 4, sleep=lambda _s: None)

        # The app's own event logging may add a row of its own while this runs, so the
        # assertions are on what must be gone and what must stay, not on exact counts.
        assert result.by_size.get('INFO', 0) >= 2
        older_info = run_sql(
            db, "SELECT id FROM events WHERE level = 'INFO' AND created_at < NOW(3) - INTERVAL 36 HOUR"
        )
        assert not older_info
        assert self._levels(db).count('CRITICAL') == 3


class OldHitsPipelineTest:
    """The "Oude hitjes" feed's SQL (feeds/old_hits_queries.py) and the popular-tracks store
    (popular_tracks/worker.py) against a real schema: ratings, listens, the stored top-list
    matches joined on track_uid, the version and date aggregates, and the display rows."""

    def _track(self, db, title, artist, release_date=None, work_id=None, duration=300):
        with db.cursor() as cursor:
            cursor.execute(
                'INSERT IGNORE INTO library_artists (name, normalized_name) VALUES (%s, %s)',
                (artist, artist.lower()),
            )
            cursor.execute('SELECT id FROM library_artists WHERE name = %s', (artist,))
            artist_id = cursor.fetchone()['id']
            cursor.execute(
                'INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id, release_date,'
                " work_id, form) VALUES (%s, %s, %s, %s, %s, %s, 'track')",
                (f'uid-{title}', title, duration, artist_id, release_date, work_id),
            )
            track_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO library_media_files (file_path, file_path_hash, track_id, file_mtime, file_size)'
                ' VALUES (%s, %s, %s, 1.0, 10)',
                (f'/mnt/music/{title}.mp3', f'hash-{title}', track_id),
            )
        return track_id

    def test_every_tier_runs_against_a_real_schema(self, api, headers, db):
        favourite = self._track(db, 'Scrap Attack', 'Headhunterz', release_date='2009-06-27')
        worn = self._track(db, 'Pennywise', 'Angerfist', release_date='2008-01-01')
        hit = self._track(db, 'World Of Madness', 'Headhunterz', release_date='2012-06-01')
        run_sql(
            db,
            "INSERT INTO rating_tracks (entity_type, entity_id, username, rating) VALUES ('track', %s, 'root', 5)",
            ('uid-Scrap Attack',),
        )
        for days in (400, 390, 380, 370):
            run_sql(
                db,
                'INSERT INTO scrobble_listens (track_id, listened_at, username, match_method)'
                " VALUES (%s, NOW() - INTERVAL %s DAY, 'root', 'exact')",
                (worn, days),
            )
        run_sql(
            db,
            'INSERT INTO artist_popular_tracks (artist_key, source, external_track_id, title, normalized_title,'
            " popularity, position, matched_track_uid, fetched_at) VALUES ('headhunterz', 'deezer', '1',"
            " 'World Of Madness', 'world of madness', 398309, 1, 'uid-World Of Madness', NOW())",
        )

        response = api.get('/api/feeds/old-hits?username=root', headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['state'] == 'ok', body
        reasons = {track['id']: track['reason'] for track in body['tracks']}
        assert reasons == {favourite: 'favourite:5', worn: 'worn:4', hit: 'hit:deezer:1'}, reasons
        assert body['title'] == 'Oude hitjes'

    def test_the_popular_tracks_store_runs_against_a_real_schema(self, db):
        from datetime import datetime

        from services.music_manager.popular_tracks.clients import ArtistTopTracks, TopTrack
        from services.music_manager.popular_tracks.matcher import ArtistIndex
        from services.music_manager.popular_tracks.worker import PopularTracksStore

        track = self._track(db, 'Pennywise', 'Angerfist', release_date='2008-01-01')
        run_sql(
            db,
            "INSERT INTO rating_tracks (entity_type, entity_id, username, rating) VALUES ('track', %s, 'root', 4)",
            ('uid-Pennywise',),
        )
        store = PopularTracksStore(connect=_connect)
        config = {'min_listens': 5, 'refresh_days': 7, 'max_artists': 10}
        now = datetime.now().replace(microsecond=0)
        assert store.due_artists('deezer', config, now) == [('angerfist', 'Angerfist')]

        index = ArtistIndex(store.artist_tracks('angerfist'))
        result = ArtistTopTracks('deezer', '42', [TopTrack('9', 'Pennywise (Radio Edit)', 1, 100)])
        assert store.save('angerfist', 'Angerfist', result, index, now) == (1, 1)
        rows = run_sql(db, 'SELECT matched_track_uid FROM artist_popular_tracks')
        assert rows == [{'matched_track_uid': 'uid-Pennywise'}]
        # Fresh now: not due again until the refresh window has passed.
        assert store.due_artists('deezer', config, now) == []

        store.record_failure('angerfist', 'Angerfist', 'deezer', now)
        fetch = run_sql(db, 'SELECT status, track_count FROM artist_popularity_fetches')
        assert fetch == [{'status': 'error', 'track_count': 1}]
        assert track


class ListeningBreakdownTest:
    """/api/listening under a genre and a release-year filter, against real rows.

    READ_ENDPOINTS above proves the filtered SQL parses on an empty schema. These seed a small
    history -- two genres on one track, a dated and an undated track, an analyzer-only date, an
    unmatched listen -- and check the numbers: that the genre column overlaps, that the years add
    up, that a filter excludes the unmatched listen and says how many it excluded, and that a
    genre which does not exist is an empty answer rather than a 500.
    """

    def _genre(self, db, name, state='white'):
        with db.cursor() as cursor:
            cursor.execute(
                'INSERT INTO rules_genres (name, normalized_name, state) VALUES (%s, %s, %s)',
                (name, name.lower(), state),
            )
            return cursor.lastrowid

    def _track(self, db, title, genres=(), release_date=None, analyzer_date=None):
        with db.cursor() as cursor:
            cursor.execute('INSERT IGNORE INTO library_artists (name) VALUES (%s)', ('Angerfist',))
            cursor.execute('SELECT id FROM library_artists WHERE name = %s', ('Angerfist',))
            artist_id = cursor.fetchone()['id']
            cursor.execute(
                'INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id, release_date)'
                ' VALUES (%s, %s, 300, %s, %s)',
                (f'uid-{title}', title, artist_id, release_date),
            )
            track_id = cursor.lastrowid
            for genre_id in genres:
                cursor.execute(
                    'INSERT INTO library_track_genres (track_id, genre_id) VALUES (%s, %s)', (track_id, genre_id)
                )
            if analyzer_date:
                cursor.execute(
                    'INSERT INTO library_track_audio_features (track_id, internal_track_id, release_date)'
                    ' VALUES (%s, %s, %s)',
                    (f'af-{track_id}', track_id, analyzer_date),
                )
        return track_id

    def _listens(self, db, track_id, count):
        with db.cursor() as cursor:
            for i in range(count):
                cursor.execute(
                    'INSERT INTO scrobble_listens (track_id, listened_at, username, match_method)'
                    " VALUES (%s, NOW() - INTERVAL %s MINUTE, 'root', 'exact')",
                    (track_id, i + 1 + track_id * 100),
                )

    def _seed(self, db):
        hardcore = self._genre(db, 'Hardcore')
        uptempo = self._genre(db, 'Uptempo Hardcore')
        rejected = self._genre(db, 'Hardcore Music', state='black')
        both = self._track(db, 'Both', genres=(hardcore, uptempo, rejected), release_date='2019-05-01')
        undated = self._track(db, 'Undated', genres=(hardcore,), release_date='')
        analyzed = self._track(db, 'Analyzed', release_date=None, analyzer_date='2015-02-02')
        self._listens(db, both, 3)
        self._listens(db, undated, 2)
        self._listens(db, analyzed, 1)
        with db.cursor() as cursor:
            cursor.execute(
                'INSERT INTO scrobble_unmatched_listens (artist_name, track_title, listened_at, username)'
                " VALUES ('Nobody', 'Nothing', NOW() - INTERVAL 1 MINUTE, 'root')"
            )

    def test_genres_overlap_and_the_rejected_one_is_left_out(self, api, headers, db):
        self._seed(db)
        body = api.get('/api/listening/top-genres?username=root', headers=headers).json()
        assert {g['genre']: g['listens'] for g in body['genres']} == {'Hardcore': 5, 'Uptempo Hardcore': 3}
        assert body['matched'] == 6
        assert body['untagged'] == 1
        assert body['unmatched'] == 1
        assert body['excluded_unmatched'] == 0

    def test_years_use_the_feeds_release_date_and_add_up(self, api, headers, db):
        self._seed(db)
        body = api.get('/api/listening/years?username=root', headers=headers).json()
        assert {y['year']: y['listens'] for y in body['years']} == {2015: 1, 2019: 3}
        assert body['unknown'] == {'listens': 2, 'tracks': 1}
        assert body['matched'] == 6

    def test_a_genre_filter_excludes_the_unmatched_listen_and_counts_it(self, api, headers, db):
        self._seed(db)
        body = api.get('/api/listening/summary?username=root&genre=Uptempo+Hardcore', headers=headers).json()
        assert body['listens'] == 3
        assert body['unmatched'] == 0
        assert body['excluded_unmatched'] == 1
        assert body['filtered'] is True

    def test_genres_are_alternatives_and_years_narrow_them(self, api, headers, db):
        self._seed(db)
        query = 'username=root&genre=Hardcore&genre=Uptempo+Hardcore'
        tracks = api.get(f'/api/listening/top-tracks?{query}', headers=headers).json()['tracks']
        # 'Both' carries two selected genres and still counts its three listens once.
        assert {t['title']: t['listens'] for t in tracks} == {'Both': 3, 'Undated': 2}
        narrowed = api.get(f'/api/listening/top-tracks?{query}&year=unknown', headers=headers).json()['tracks']
        assert [t['title'] for t in narrowed] == ['Undated']
        ranged = api.get('/api/listening/top-tracks?username=root&year_from=2010&year_to=2016', headers=headers)
        assert [t['title'] for t in ranged.json()['tracks']] == ['Analyzed']

    def test_the_filter_reaches_the_hourly_rollup(self, api, headers, db):
        self._seed(db)
        body = api.get('/api/listening/clock?username=root&year=2019', headers=headers).json()
        assert sum(body['hours']) == 3
        sources = api.get('/api/listening/sources?username=root&year=2019', headers=headers).json()
        assert sum(row['listens'] for row in sources['sources']) == 3

    def test_an_unknown_genre_is_an_empty_answer_not_an_error(self, api, headers, db):
        self._seed(db)
        response = api.get('/api/listening/top-artists?username=root&genre=Polka', headers=headers)
        assert response.status_code == 200
        assert response.json()['artists'] == []
        assert response.json()['excluded_unmatched'] == 1


class BpmBrowseSqlTest:
    """The BPM browse's index query (bpm/index.py INDEX_SQL) and page details (routers/bpm.py)
    against a real schema: a measurement joined on track_uid, a tag, an analyzer tempo folded
    into its genre's band, and a set that must stay out."""

    def _track(self, db, title, genre=None, form='track', tag=None, tempo=None):
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO library_tracks (track_uid, title, duration_secs, form) VALUES (%s, %s, 240, %s)",
                (f'uid-bpm-{title}', title, form),
            )
            track_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO library_media_files (file_path, file_path_hash, track_id, file_mtime, file_size)'
                ' VALUES (%s, %s, %s, 1.0, 10)',
                (f'/mnt/music/EPs/{title}.mp3', f'hash-bpm-{title}', track_id),
            )
            if tag is not None or tempo is not None:
                cursor.execute(
                    'INSERT INTO library_track_audio_features (track_id, internal_track_id, bpm_tag, tempo)'
                    ' VALUES (%s, %s, %s, %s)',
                    (f'af-bpm-{title}', track_id, tag, tempo),
                )
            if genre:
                # The migrations may already have seeded the genre; either way it is looked up by name.
                cursor.execute(
                    "INSERT IGNORE INTO rules_genres (name, normalized_name, state) VALUES (%s, %s, 'white')",
                    (genre, genre.lower()),
                )
                cursor.execute('SELECT id FROM rules_genres WHERE name = %s ORDER BY id LIMIT 1', (genre,))
                genre_id = cursor.fetchone()['id']
                cursor.execute(
                    'INSERT INTO library_track_genres (track_id, genre_id) VALUES (%s, %s)', (track_id, genre_id)
                )
        return track_id

    def test_every_source_reaches_the_browse(self, api, headers, db):
        from services.music_manager.routers import bpm as bpm_router

        measured = self._track(db, 'Measured', genre='Hardstyle', tag=152.0, tempo=152.0)
        run_sql(
            db,
            "INSERT INTO library_track_bpm (track_uid, status, bpm, raw_bpm, confidence, method, analyzed_at)"
            " VALUES ('uid-bpm-Measured', 'ok', 150.02, 75.01, 0.910, 'acf-comb-v1', NOW())",
        )
        tagged = self._track(db, 'Tagged', genre='Raw Hardstyle', tag=152.0, tempo=151.999)
        folded = self._track(db, 'Folded', genre='Uptempo Hardcore', tempo=105.469)
        self._track(db, 'A Set', form='set', tag=150.0)
        failed = self._track(db, 'Failed', tag=149.0)
        run_sql(
            db,
            "INSERT INTO library_track_bpm (track_uid, status, method, error, analyzed_at)"
            " VALUES ('uid-bpm-Failed', 'failed', 'acf-comb-v1', 'decode error', NOW())",
        )
        bpm_router.index_cache.invalidate()
        try:
            response = api.get('/api/library/bpm/tracks?bpm=150', headers=headers)
            assert response.status_code == 200, response.text
            tracks = {t['id']: t for t in response.json()['tracks']}
            assert set(tracks) == {measured, tagged, failed}, tracks
            assert (tracks[measured]['bpm'], tracks[measured]['bpm_source']) == (150.02, 'measured')
            assert tracks[measured]['bpm_confidence'] == 'high'
            assert (tracks[tagged]['bpm_source'], tracks[tagged]['bpm_confidence']) == ('tag', 'medium')
            assert tracks[tagged]['library_path'] == 'EPs/Tagged.mp3'
            assert tracks[failed]['bpm_source'] == 'tag'  # a failed measurement falls back

            uptempo = api.get('/api/library/bpm/tracks?bpm=211&genre=uptempo%20hardcore', headers=headers).json()
            assert [(t['id'], t['bpm'], t['bpm_folded']) for t in uptempo['tracks']] == [(folded, 210.94, True)]

            histogram = api.get('/api/library/bpm/histogram', headers=headers).json()
            assert histogram['summary']['tracks'] == 4
        finally:
            bpm_router.index_cache.invalidate()

    def test_the_analysis_workers_queue_and_upsert_run_against_a_real_schema(self, db):
        """bpm/worker.py's DUE_SQL, REMAINING_SQL, evidence lookup and UPSERT_SQL: newest first,
        sets skipped, a current measurement not queued again, a changed file queued again, a
        failure counted and retried only once due."""
        from datetime import datetime

        from services.music_manager.bpm import estimator, octave, worker

        older = self._track(db, 'Queue Older', genre='Hardstyle')
        newer = self._track(db, 'Queue Newer')
        self._track(db, 'Queue Set', form='set')
        run_sql(db, 'UPDATE library_tracks SET primary_artist_id = 987654 WHERE id IN (%s, %s)', (older, newer))
        store = worker.BpmStore(connect=_connect)
        config = worker.read_settings(env={})
        now = datetime.now().replace(microsecond=0)

        due = [row['track_id'] for row in store.due_tracks(config, now, limit=1000)]
        assert due.index(newer) < due.index(older)
        assert 'uid-bpm-Queue Set' not in {row['track_uid'] for row in store.due_tracks(config, now, limit=1000)}
        before = store.remaining(config, now)
        assert before >= 2

        found = store.evidence_for([older, newer])
        assert found[older]['genres'] == 'Hardstyle'
        assert found[newer]['genres'] is None  # bug report 140: no stand-in from the artist's other tracks

        jobs = {row['track_id']: row for row in store.due_tracks(config, now, limit=1000)}
        measured = {
            'ok': True,
            'raw': 75.0,
            'confidence': 0.9,
            'strength': 0.5,
            'half_score': None,
            'double_score': 0.45,
        }
        store.save(
            [
                worker.to_row(jobs[older], measured, octave.Evidence(genres=('Hardstyle',)), now),
                worker.to_row(jobs[newer], {'ok': False, 'error': 'DecodeError: x'}, None, now),
            ]
        )
        rows = {
            r['track_uid']: r
            for r in run_sql(db, 'SELECT * FROM library_track_bpm WHERE track_uid LIKE %s', ('uid-bpm-Queue%',))
        }
        assert float(rows['uid-bpm-Queue Older']['bpm']) == 150.0
        assert rows['uid-bpm-Queue Older']['method'] == estimator.METHOD
        assert float(rows['uid-bpm-Queue Older']['raw_confidence']) == 0.9
        assert rows['uid-bpm-Queue Older']['fold_version'] == octave.FOLD_VERSION
        assert rows['uid-bpm-Queue Older']['fold_evidence'] == octave.EVIDENCE_BAND
        assert rows['uid-bpm-Queue Newer']['status'] == 'failed'
        assert store.remaining(config, now) == before - 2

        # A second failure counts up; a retry is due only after RETRY_FAILED_AFTER.
        store.save([worker.to_row(jobs[newer], {'ok': False, 'error': 'again'}, None, now)])
        attempts = run_sql(db, "SELECT attempts FROM library_track_bpm WHERE track_uid = 'uid-bpm-Queue Newer'")[0][
            'attempts'
        ]
        assert attempts == 2
        later = now + worker.RETRY_FAILED_AFTER + timedelta(minutes=1)
        assert newer in {row['track_id'] for row in store.due_tracks(config, later, limit=1000)}

        # A replaced file is measured again.
        run_sql(db, 'UPDATE library_media_files SET file_size = 11 WHERE track_id = %s', (older,))
        assert older in {row['track_id'] for row in store.due_tracks(config, now, limit=1000)}
        run_sql(db, 'UPDATE library_media_files SET file_size = 10 WHERE track_id = %s', (older,))

        # Bug report 140: a measurement from before the comb scores were kept is measured again --
        # after the new tracks, and the doubtful ones (above 200, folded, ...) first.
        doubtful = self._track(db, 'Queue Doubtful')
        plain = self._track(db, 'Queue Plain')
        for uid, bpm, corrected in (('uid-bpm-Queue Doubtful', 256.0, 1), ('uid-bpm-Queue Plain', 150.0, 0)):
            run_sql(
                db,
                "INSERT INTO library_track_bpm (track_uid, status, bpm, raw_bpm, confidence, method, octave_corrected,"
                " file_mtime, file_size, analyzed_at) VALUES (%s, 'ok', %s, 64, 0.5, %s, %s, 1.0, 10, NOW())",
                (uid, bpm, estimator.METHOD, corrected),
            )
        order = [row['track_id'] for row in store.due_tracks(config, later, limit=1000)]
        assert order.index(doubtful) < order.index(plain)
        assert order.index(newer) < order.index(doubtful)  # the failure due for a retry is first-tier
        assert older not in order  # measured with comb scores: current

    def _measured(self, db, title, path, bpm=150.02, confidence=0.9, form='track', mtime=1.0, size=10):
        """A track with one file at `path` and a current measurement of it, folded by the current rule."""
        from services.music_manager.bpm.octave import FOLD_VERSION

        with db.cursor() as cursor:
            cursor.execute(
                'INSERT INTO library_tracks (track_uid, title, duration_secs, form) VALUES (%s, %s, 240, %s)',
                (f'uid-tag-{title}', title, form),
            )
            track_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO library_media_files (file_path, file_path_hash, track_id, file_mtime, file_size)'
                ' VALUES (%s, %s, %s, %s, %s)',
                (path, f'hash-tag-{title}', track_id, mtime, size),
            )
            cursor.execute(
                'INSERT INTO library_track_bpm (track_uid, status, bpm, raw_bpm, confidence, method,'
                ' file_mtime, file_size, analyzed_at, fold_version, strength)'
                " VALUES (%s, 'ok', %s, %s, %s, 'acf-comb-v1', %s, %s, NOW(), %s, 0.5)",
                (f'uid-tag-{title}', bpm, bpm, confidence, mtime, size, FOLD_VERSION),
            )
        return track_id

    def test_the_tag_writeback_queue_and_bookkeeping_run_against_a_real_schema(self, db):
        """Issue #139, bpm/tag_writeback.py: confident, current, in-scope measurements newest first;
        an outcome takes a file off the queue until its measurement changes; a write moves the
        analyzer's, the scanner's and an up-to-date tagger row to the new stat, and nothing
        requeues the file -- not this step, not the analyzer, not the tagger."""
        from datetime import datetime
        from types import SimpleNamespace

        from services.music_manager.bpm import tag_writeback, worker

        eps = '/mnt/music/EPs'
        older = self._measured(db, 'Older', f'{eps}/Label/REL1/older.mp3')
        newer = self._measured(db, 'Newer', f'{eps}/Label/REL1/newer.mp3')
        self._measured(db, 'Unsure', f'{eps}/Label/REL1/unsure.mp3', confidence=0.5)
        self._measured(db, 'A Set', f'{eps}/Label/REL1/set.mp3', form='set')
        self._measured(db, 'Todo', f'{eps}/__TODO/REL2/todo.mp3')
        self._measured(db, 'Quarantined', f'{eps}/Label/.quarantine/q.mp3')
        self._measured(db, 'Recycled', f'{eps}/#recycle/r.mp3')
        self._measured(db, 'Lidarr', '/mnt/music/Lidarr/Artist/l.mp3')
        self._measured(db, 'Wildcard', '/mnt/music/EPsX/w.mp3')  # '_' or a prefix is no root
        stale = self._measured(db, 'Stale', f'{eps}/Label/REL1/stale.mp3')
        run_sql(db, 'UPDATE library_media_files SET file_size = 11 WHERE track_id = %s', (stale,))

        store = tag_writeback.BpmTagStore(connect=_connect)
        config = tag_writeback.read_settings({}.get)
        due = store.due(config, [eps], 100)
        assert [row['track_id'] for row in due] == [newer, older]
        assert store.remaining(config, [eps]) == 2
        assert [row['track_id'] for row in store.due(config, [eps], 1)] == [newer]
        low = tag_writeback.read_settings({'bpm_tag_writeback_min_confidence': 40}.get)
        assert len(store.due(low, [eps], 100)) == 3

        now = datetime(2026, 9, 30, 12, 0)
        rows = {row['track_id']: row for row in due}
        store.record(rows[older], 'matches', now)
        assert [row['track_id'] for row in store.due(config, [eps], 100)] == [newer]
        # A new measurement with another value queues the file again.
        run_sql(db, "UPDATE library_track_bpm SET bpm = 151.40 WHERE track_uid = 'uid-tag-Older'")
        assert older in {row['track_id'] for row in store.due(config, [eps], 100)}

        path = rows[newer]['file_path']
        run_sql(
            db,
            'INSERT INTO tagger_processed_files (filepath, mtime, needs_rescan, last_processed)'
            " VALUES (%s, 1.0, FALSE, '2026-01-01 00:00:00')",
            (path,),
        )
        store.record_written(
            rows[newer], SimpleNamespace(st_mtime=1.0, st_size=10), SimpleNamespace(st_mtime=2.5, st_size=12), now
        )
        bpm_row = run_sql(db, "SELECT * FROM library_track_bpm WHERE track_uid = 'uid-tag-Newer'")[0]
        assert (float(bpm_row['tag_bpm']), bpm_row['tag_action']) == (150.02, 'written')
        assert (bpm_row['file_mtime'], bpm_row['file_size']) == (2.5, 12)
        media = run_sql(db, 'SELECT file_mtime, file_size FROM library_media_files WHERE track_id = %s', (newer,))[0]
        assert (media['file_mtime'], media['file_size']) == (2.5, 12)
        processed = run_sql(db, 'SELECT * FROM tagger_processed_files WHERE filepath = %s', (path,))[0]
        assert processed['mtime'] == 2.5
        assert str(processed['last_processed']) == '2026-01-01 00:00:00'  # the deep run's clock untouched
        assert not processed['needs_rescan']

        assert newer not in {row['track_id'] for row in store.due(config, [eps], 100)}
        analysis = worker.read_settings(env={})
        assert newer not in {
            row['track_id'] for row in worker.BpmStore(connect=_connect).due_tracks(analysis, now, 1000)
        }

    def test_the_tag_writeback_follows_the_octave_rule_and_the_manual_tempo(self, db):
        """Bug report 140: a measurement is only written once the current rule chose its octave; a
        file this step wrote is queued again when the rule changes its mind, even without
        confidence; a tempo set by hand is written, whatever the measurement says."""
        from datetime import datetime

        from services.music_manager.bpm import tag_writeback

        eps = '/mnt/music/EPs'
        old_rule = self._measured(db, 'Old Rule', f'{eps}/Label/REL3/old.mp3')
        run_sql(db, "UPDATE library_track_bpm SET fold_version = NULL WHERE track_uid = 'uid-tag-Old Rule'")
        rewritten = self._measured(db, 'Rewritten', f'{eps}/Label/REL3/rewritten.mp3', bpm=256.0)
        run_sql(
            db,
            "UPDATE library_track_bpm SET tag_bpm = 256.0, tag_action = 'written', bpm = 128.0, confidence = 0.4"
            " WHERE track_uid = 'uid-tag-Rewritten'",
        )
        manual = self._measured(db, 'Manual', f'{eps}/Label/REL3/manual.mp3', bpm=230.0, confidence=0.2)
        run_sql(
            db,
            "INSERT INTO library_track_bpm_manual (track_uid, bpm, set_by, set_at) VALUES ('uid-tag-Manual', 115, 1, NOW())",
        )
        store = tag_writeback.BpmTagStore(connect=_connect)
        config = tag_writeback.read_settings({}.get)
        due = {row['track_id']: row for row in store.due(config, [eps], 100)}
        assert old_rule not in due
        assert float(due[rewritten]['bpm']) == 128.0
        assert (float(due[manual]['bpm']), float(due[manual]['manual_bpm'])) == (115.0, 115.0)

        store.record(due[manual], 'written', datetime(2026, 9, 30))
        assert (
            float(run_sql(db, "SELECT tag_bpm FROM library_track_bpm WHERE track_uid = 'uid-tag-Manual'")[0]['tag_bpm'])
            == 115.0
        )
        assert manual not in {row['track_id'] for row in store.due(config, [eps], 100)}
        # Clearing the manual tempo queues the measurement's value -- unconfident, but written before.
        run_sql(db, "DELETE FROM library_track_bpm_manual WHERE track_uid = 'uid-tag-Manual'")
        assert manual in {row['track_id'] for row in store.due(config, [eps], 100)}

    def test_the_tag_writeback_leaves_a_queued_tagger_row_queued(self, db):
        from datetime import datetime
        from types import SimpleNamespace

        from services.music_manager.bpm import tag_writeback

        path = '/mnt/music/EPs/Label/REL1/flagged.mp3'
        self._measured(db, 'Flagged', path)
        run_sql(
            db,
            "INSERT INTO tagger_processed_files (filepath, mtime, needs_rescan, rescan_reason)"
            " VALUES (%s, 1.0, TRUE, 'genre_decision')",
            (path,),
        )
        store = tag_writeback.BpmTagStore(connect=_connect)
        row = store.due(tag_writeback.read_settings({}.get), ['/mnt/music/EPs'], 10)[0]
        store.record_written(
            row, SimpleNamespace(st_mtime=1.0, st_size=10), SimpleNamespace(st_mtime=3.0, st_size=12), datetime.now()
        )
        processed = run_sql(db, 'SELECT * FROM tagger_processed_files WHERE filepath = %s', (path,))[0]
        assert (processed['mtime'], bool(processed['needs_rescan']), processed['rescan_reason']) == (
            1.0,
            True,
            'genre_decision',
        )

    def test_the_effective_bpm_table_feeds_every_sql_reader(self, api, headers, db):
        """Issue #141: bpm/effective_table.py materialises what effective.py resolves, and the
        library table (column, sort, filter, search term), /tracks, the analytics and the details
        sheet all show that one tempo -- a measurement over the analyzer, a tag folded into its
        genre's band, tracks without any BPM last in both sort directions."""
        from services.music_manager.bpm import effective_table

        measured = self._track(db, 'Eff Measured', genre='Hardstyle', tag=152.0, tempo=161.5)
        run_sql(
            db,
            "INSERT INTO library_track_bpm (track_uid, status, bpm, raw_bpm, confidence, method, analyzed_at)"
            " VALUES ('uid-bpm-Eff Measured', 'ok', 150.00, 150.00, 0.910, 'acf-comb-v1', NOW())",
        )
        halftime = self._track(db, 'Eff Halftime', genre='Hardstyle', tag=76.0)
        a_set = self._track(db, 'Eff Set', form='set', tag=140.0)
        silent = self._track(db, 'Eff Silent')

        first = effective_table.sync(_connect)
        assert (first.resolved, first.upserted, first.deleted) == (3, 3, 0)
        rows = {r['track_id']: r for r in run_sql(db, 'SELECT * FROM library_track_effective_bpm')}
        assert set(rows) == {measured, halftime, a_set}
        assert (float(rows[measured]['bpm']), rows[measured]['source'], rows[measured]['approximate']) == (
            150.0,
            'measured',
            0,
        )
        assert (float(rows[halftime]['bpm']), rows[halftime]['folded'], rows[halftime]['approximate']) == (152.0, 1, 1)
        assert effective_table.sync(_connect).upserted == 0  # nothing changed, nothing written

        def advanced(query):
            response = api.get(f'/api/library/advanced?{query}', headers=headers)
            assert response.status_code == 200, response.text
            return response.json()

        desc = advanced('sort=bpm&direction=desc')['tracks']
        assert [t['id'] for t in desc] == [halftime, measured, a_set, silent]
        assert [t['id'] for t in advanced('sort=bpm&direction=asc')['tracks']] == [a_set, measured, halftime, silent]
        by_id = {t['id']: t for t in desc}
        assert (by_id[measured]['bpm'], by_id[measured]['bpm_approximate']) == (150.0, 0)
        assert (by_id[halftime]['bpm'], by_id[halftime]['bpm_approximate']) == (152.0, 1)
        assert by_id[silent]['bpm'] is None
        assert by_id[measured]['file_path'] == '/mnt/music/EPs/Eff Measured.mp3'  # the outer subqueries ran
        assert by_id[measured]['genres'] == ['Hardstyle']
        # Paging over the sorted list neither repeats nor skips a track.
        paged = [t['id'] for p in (1, 2) for t in advanced(f'sort=bpm&direction=desc&limit=2&page={p}')['tracks']]
        assert paged == [halftime, measured, a_set, silent]

        assert {t['id'] for t in advanced('bpm_min=149&bpm_max=151')['tracks']} == {measured}
        found = advanced('q=153')
        assert (found['total'], found['tracks'][0]['id']) == (1, halftime)
        assert advanced('q=161')['total'] == 0  # the analyzer's 161.5 lost to the measurement

        simple = {t['id']: t for t in api.get('/api/library/tracks?q=Eff', headers=headers).json()['tracks']}
        assert (simple[measured]['bpm'], simple[measured]['bpm_approximate']) == (150.0, 0)

        histogram = api.get('/api/analytics/bpm-histogram?bucket=5', headers=headers).json()
        assert {(b['bucket_start'], b['count']) for b in histogram} == {(140, 1), (150, 2)}
        summary = api.get('/api/analytics/summary', headers=headers).json()
        assert summary['coverage']['bpm'] == pytest.approx(0.75)

        halftime_path = '/mnt/music/EPs/Eff Halftime.mp3'
        run_sql(
            db,
            'UPDATE library_media_files SET file_path_hash = %s WHERE track_id = %s',
            (hashlib.sha256(halftime_path.encode()).hexdigest(), halftime),
        )
        details = api.get(
            '/api/library/tracks/by-path', params={'path': 'EPs/Eff Halftime.mp3'}, headers=headers
        ).json()
        assert (details['bpm'], details['bpm_source'], details['bpm_approximate']) == (152.0, 'tag', True)

        # A track that loses its only source loses its row; a partial sync touches only its ids.
        run_sql(db, 'DELETE FROM library_track_audio_features WHERE internal_track_id = %s', (a_set,))
        partial = effective_table.sync(_connect, track_ids=[a_set])
        assert (partial.resolved, partial.upserted, partial.deleted) == (0, 0, 1)
        assert {r['track_id'] for r in run_sql(db, 'SELECT track_id FROM library_track_effective_bpm')} == {
            measured,
            halftime,
        }

    def test_priors_refold_and_the_manual_override_run_against_a_real_schema(self, api, headers, db):
        """Bug report 140 end to end: the priors leave an artist's remixes out, the refold turns
        André Hazes's 256 back into 128 from the database alone, and a tempo set by hand wins,
        is audited, reaches library_track_effective_bpm at once, and can be taken back."""
        from datetime import datetime

        from services.music_manager.bpm import effective_table, octave, priors, refold

        artist = 5551401
        label_name = 'Priors Test Label'
        run_sql(db, 'INSERT INTO library_labels (name) VALUES (%s)', (label_name,))
        label_id = run_sql(db, 'SELECT id FROM library_labels WHERE name = %s', (label_name,))[0]['id']

        def measured(title, raw, bpm, path, genre=None, confidence=0.9, labelled=False, by_artist=True):
            track_id = self._track(db, title, genre=genre)
            if by_artist:
                run_sql(db, 'UPDATE library_tracks SET primary_artist_id = %s WHERE id = %s', (artist, track_id))
            run_sql(db, 'UPDATE library_media_files SET file_path = %s WHERE track_id = %s', (path, track_id))
            if labelled:
                run_sql(
                    db, 'INSERT INTO library_track_labels (track_id, label_id) VALUES (%s, %s)', (track_id, label_id)
                )
            run_sql(
                db,
                'INSERT INTO library_track_bpm (track_uid, status, bpm, raw_bpm, confidence, method, octave_corrected,'
                " analyzed_at) VALUES (%s, 'ok', %s, %s, %s, 'acf-comb-v1', %s, NOW())",
                (f'uid-bpm-{title}', bpm, raw, confidence, int(bpm != raw)),
            )
            return track_id

        for n in range(6):
            measured(
                f'Rode Licht {n} (Rectonize Remix)',
                160.0,
                160.0,
                f'/mnt/music/EPs/L/r{n}.mp3',
                'Hardstyle',
                labelled=True,
            )
        for n in range(6):
            measured(f'Label Own {n}', 150.0, 150.0, f'/mnt/music/EPs/L/o{n}.mp3', labelled=True, by_artist=False)
        hazes = measured(
            'Vaag en Stil', 64.0, 256.0, '/mnt/music/Hitzone/Hitzone 33/CD/21 - Vaag en Stil.mp3', confidence=0.5
        )

        stored = priors.recompute(_connect, datetime.now())
        # The artist's six remixes are left out and the ballad is below the window: no artist prior.
        assert stored.for_artist(artist) is None
        assert stored.label[label_id].samples == 12
        assert 'hardstyle' in stored.genre
        assert priors.load(_connect).label[label_id].samples == 12
        assert priors.last_update(_connect) is not None

        result = refold.refold(_connect, stored, track_ids=[hazes])
        assert (result.rows, result.written) == (1, 1)
        row = run_sql(db, "SELECT * FROM library_track_bpm WHERE track_uid = 'uid-bpm-Vaag en Stil'")[0]
        assert (float(row['bpm']), row['octave_corrected'], row['fold_version']) == (128.0, 1, octave.FOLD_VERSION)
        assert float(row['raw_confidence']) == 0.5 and float(row['confidence']) <= 0.5
        assert refold.refold(_connect, stored, track_ids=[hazes]).written == 0  # settled

        effective_table.sync(_connect, track_ids=[hazes])
        url = f'/api/library/bpm/tracks/{hazes}/manual'
        response = api.put(url, json={'factor': 2}, headers=headers)
        assert response.status_code == 200, response.text
        assert (response.json()['bpm'], response.json()['bpm_source']) == (256.0, 'manual')
        eff = run_sql(
            db, 'SELECT bpm, source, confidence FROM library_track_effective_bpm WHERE track_id = %s', (hazes,)
        )[0]
        assert (float(eff['bpm']), eff['source'], eff['confidence']) == (256.0, 'manual', 'high')
        audit = run_sql(
            db, "SELECT details FROM audit_events WHERE event_type = 'bpm.manual_set' ORDER BY id DESC LIMIT 1"
        )
        assert json.loads(audit[0]['details'])['track_id'] == hazes
        # The analyzer's refold never touches the manual tempo.
        refold.refold(_connect, stored, track_ids=[hazes])
        assert (
            float(
                run_sql(db, "SELECT bpm FROM library_track_bpm_manual WHERE track_uid = 'uid-bpm-Vaag en Stil'")[0][
                    'bpm'
                ]
            )
            == 256.0
        )

        response = api.delete(url, headers=headers)
        assert (response.json()['bpm'], response.json()['bpm_source']) == (128.0, 'measured')
        assert not run_sql(db, "SELECT * FROM library_track_bpm_manual WHERE track_uid = 'uid-bpm-Vaag en Stil'")
        assert (
            api.put('/api/library/bpm/tracks/999999999/manual', json={'bpm': 120}, headers=headers).status_code == 404
        )


class RadioStationsSqlTest:
    """The live-station queries against the real server (issue #213)."""

    STATION = {'slug': 'slam', 'name': 'SLAM', 'stream_url': 'https://example.com/slam.mp3', 'sort_order': 20}

    def test_create_list_update_and_delete(self, api, headers):
        assert api.post('/api/radio/stations', headers=headers, json=self.STATION).status_code == 201
        second = {**self.STATION, 'slug': 'first', 'name': 'First', 'sort_order': 10}
        assert api.post('/api/radio/stations', headers=headers, json=second).status_code == 201
        assert api.post('/api/radio/stations', headers=headers, json=self.STATION).status_code == 409

        listed = api.get('/api/radio/stations', headers=headers).json()['stations']
        assert [station['slug'] for station in listed] == ['first', 'slam']

        response = api.put('/api/radio/stations/slam', headers=headers, json={'enabled': False, 'name': 'Slam!'})
        assert response.status_code == 200, response.text
        assert response.json()['name'] == 'Slam!'

        listed = api.get('/api/radio/stations', headers=headers).json()['stations']
        assert [station['slug'] for station in listed] == ['first']
        listed = api.get('/api/radio/stations?include_disabled=true', headers=headers).json()['stations']
        assert [(station['slug'], station['enabled']) for station in listed] == [('first', True), ('slam', False)]

        assert api.delete('/api/radio/stations/slam', headers=headers).status_code == 200
        assert api.delete('/api/radio/stations/slam', headers=headers).status_code == 404
