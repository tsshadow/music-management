"""The artist curation queue, wired to the tagger, against a real MariaDB.

What is proved here is the SQL the unit tests mock away: which names the tagger's
trusted-artist helper loads (TRUSTED_ARTISTS_SQL), that a name the scanner records is
pending rather than trusted, and that the auto-approve run still sees a pending name as a candidate.
See docs/designs/artist-curation/technical.md, "Wiring the queue".
"""

import pytest

from services.common.Helpers.TrustedArtistHelper import TRUSTED_ARTISTS_SQL
from services.music_manager.routers import scanner as scanner_router
from tests.integration.conftest import run_sql
from tools.artist_auto_approve import SNAPSHOT_SQL

pytestmark = pytest.mark.integration


class FakeSong:
    """What ReadonlySong would read from a file: only the fields process_file asks for."""

    def __init__(self, artists, title='Raise Your Fist'):
        self._artists = list(artists)
        self._title = title

    def remixers(self):
        return []

    def library_artists(self):
        return self._artists

    def publisher(self):
        return None

    def title(self):
        return self._title

    def length(self):
        return 300

    def original_artist(self):
        return None

    def rules_genres(self):
        return []


def trusted(db) -> set[str]:
    """What the tagger's TrustedArtistHelper would load right now."""
    return {row['name'] for row in run_sql(db, TRUSTED_ARTISTS_SQL)}


def add_artists(db, *names):
    with db.cursor() as cursor:
        cursor.executemany('INSERT IGNORE INTO library_artists (name) VALUES (%s)', [(n,) for n in names])


@pytest.fixture(name='scan')
def scan_fixture(db, tmp_path, monkeypatch):
    """Run the real scanner over one file whose tags say `song`."""
    tags = {}
    monkeypatch.setattr(scanner_router, 'ReadonlySong', lambda path: tags[str(path)])
    manager = scanner_router.ScannerManager()
    manager.music_path = str(tmp_path)

    def _scan(relative, song):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'not really audio')
        tags[str(path)] = song
        assert manager.process_file(db, str(path), force=True)

    return _scan


class TrustedArtistsTest:
    def test_trust_is_approval_or_grandfathering_and_never_a_bare_library_row(self, db):
        add_artists(db, 'Legacy Name', 'Legacy Rejected', 'Approved Later', 'Brand New')
        with db.cursor() as cursor:
            cursor.executemany(
                'INSERT INTO rules_artist_legacy_trust (name) VALUES (%s)', [('Legacy Name',), ('Legacy Rejected',)]
            )
            cursor.executemany(
                'INSERT INTO rules_artists (name, state, decided_by) VALUES (%s, %s, %s)',
                [
                    ('Legacy Rejected', 'black', 'user'),
                    ('Approved Later', 'white', 'auto-external'),
                    # Approved but no longer carried by any file: still an artist.
                    ('Off The Library', 'white', 'user'),
                ],
            )
        assert trusted(db) == {'Legacy Name', 'Approved Later', 'Off The Library'}

    def test_an_approved_spelling_wins_over_a_legacy_casing_variant(self, db):
        add_artists(db, 'ANGERFIST')
        run_sql(db, "INSERT INTO rules_artist_legacy_trust (name) VALUES ('ANGERFIST')")
        run_sql(db, "INSERT INTO rules_artists (name, state) VALUES ('Angerfist', 'white')")
        rows = [row['name'] for row in run_sql(db, TRUSTED_ARTISTS_SQL)]
        # general_ci collation: the white row *is* the library row, so the legacy branch
        # drops it and the approved spelling is the only one left.
        assert rows == ['Angerfist']


class ScannerPathTest:
    def test_a_name_the_scanner_records_is_pending_not_trusted(self, db, scan, api, headers):
        add_artists(db, 'Angerfist')
        run_sql(db, "INSERT INTO rules_artist_legacy_trust (name) VALUES ('Angerfist')")
        scan('Soundcloud/a.mp3', FakeSong(['Angerfist', 'Tagger Guess']))

        # The file's tag is recorded as it is: the track links to both names.
        links = run_sql(
            db,
            'SELECT a.name FROM library_track_artists la JOIN library_artists a ON a.id = la.artist_id '
            'ORDER BY la.position',
        )
        assert [row['name'] for row in links] == ['Angerfist', 'Tagger Guess']
        # Nothing was decided or grandfathered on the scanner's say-so.
        assert not run_sql(db, 'SELECT name FROM rules_artists')
        assert trusted(db) == {'Angerfist'}

        pending = api.get('/api/rules/artists?state=pending', headers=headers).json()
        assert [(row['name'], row['pending'], row['track_count']) for row in pending['rows']] == [
            ('Tagger Guess', True, 1)
        ]
        queue = api.get('/api/rules/artists?state=unknown', headers=headers).json()
        assert {row['name']: row['pending'] for row in queue['rows']} == {'Angerfist': False, 'Tagger Guess': True}
        summary = api.get('/api/rules/artists/summary', headers=headers).json()
        assert (summary['unknown'], summary['pending']) == (2, 1)

    def test_a_second_file_with_the_same_guess_does_not_make_it_trusted(self, db, scan):
        scan('Soundcloud/a.mp3', FakeSong(['Tagger Guess'], title='One'))
        scan('Soundcloud/b.mp3', FakeSong(['Tagger Guess'], title='Two'))
        assert 'Tagger Guess' not in trusted(db)


class DecisionPathTest:
    def test_approving_a_pending_name_makes_it_trusted_and_undo_makes_it_pending_again(self, db, api, headers):
        add_artists(db, 'Tagger Guess')
        response = api.post(
            '/api/rules/artists/decide',
            headers=headers,
            json={'names': ['Tagger Guess'], 'state': 'white', 'decided_by': 'auto-external'},
        )
        assert response.status_code == 200, response.text
        assert 'Tagger Guess' in trusted(db)
        rows = run_sql(db, "SELECT decided_by FROM rules_artists WHERE name = 'Tagger Guess'")
        assert [row['decided_by'] for row in rows] == ['auto-external']
        api.delete('/api/rules/artists/Tagger Guess', headers=headers)
        assert 'Tagger Guess' not in trusted(db)
        pending = api.get('/api/rules/artists?state=pending', headers=headers).json()
        assert [row['name'] for row in pending['rows']] == ['Tagger Guess']


class AutoApprovePathTest:
    def test_the_auto_approve_snapshot_offers_a_pending_name(self, db, scan):
        """!874's evidence run reads the undecided names; a pending one is one of them."""
        scan('Soundcloud/a.mp3', FakeSong(['Tagger Guess'], title='Feel The Electricity'))
        with db.cursor() as cursor:
            cursor.execute(SNAPSHOT_SQL)
            rows = cursor.fetchall()
        assert [(row['name'], row['title']) for row in rows] == [('Tagger Guess', 'Feel The Electricity')]
