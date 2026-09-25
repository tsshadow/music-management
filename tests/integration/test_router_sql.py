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
from datetime import date, timedelta
from unittest.mock import patch

import pymysql
import pytest

from tests.integration.conftest import run_sql

pytestmark = pytest.mark.integration

# (method, path) for every endpoint that reads from the database and needs no
# request body. Against an empty-but-valid schema each must answer 2xx or a
# deliberate 4xx -- never a 500, which is what invalid SQL produces.
READ_ENDPOINTS = [
    ('/api/users', 200),
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
    ('/api/library/tracks', 200),
    ('/api/library/advanced', 200),
    # Paging is validated before any SQL runs: page 0 was a negative OFFSET (a 500).
    ('/api/library/tracks?page=0', 422),
    ('/api/library/tracks?limit=501', 422),
    ('/api/library/advanced?page=0', 422),
    ('/api/library/genres', 200),
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
    ('/api/artists?q=anger', 200),
    ('/api/labels?q=scan', 200),
    ('/api/system/activity', 200),
    ('/api/soundcloud', 200),
    ('/api/youtube', 200),
    # Four statements each over the downloader tables, including the archive
    # timestamp the YouTube table only has since migrate_v31.
    ('/api/downloaders/coverage/soundcloud', 200),
    ('/api/downloaders/coverage/youtube', 200),
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

    def test_the_last_admin_is_protected(self, api, headers, db):
        setup = api.post('/api/auth/setup', json={'username': 'root', 'password': 'hunter2'})
        admin_id = setup.json()['id']
        refused = api.delete(f'/api/users/{admin_id}', headers=headers)
        assert refused.status_code == 409
        assert 'beheerder' in refused.json()['detail']

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
        assert api.get('/api/soundcloud', headers=headers).json() == [{'name': 'artist', 'soundcloud_id': '7'}]
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
        import time
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
        from tests.integration.conftest import _connect

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
        from tests.integration.conftest import _connect

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
