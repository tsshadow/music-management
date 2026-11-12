"""Channel links reaching the tags and the library, against a real MariaDB (issue #58).

The unit tests mock the cursor, so these prove the two statements they cannot: what the tagger's
ChannelLinkHelper loads (LINKS_SQL, which must drop an artist that is no longer approved), and
that the scanner stores the linked label for a file under a platform folder while still refusing
the platform itself (CHANNEL_LABEL_QUERY via ScannerManager.process_file).
See docs/designs/channel-links/technical.md, "Hand-linking and the tagger".
"""

import pytest

from services.common.Helpers.ChannelLinkHelper import LINKS_SQL, ChannelLinkHelper
from services.common.Helpers.RescanInvalidator import CHANNEL_FILES_SQL
from services.music_manager.routers import scanner as scanner_router
from tests.integration.conftest import run_sql

pytestmark = pytest.mark.integration


class FakeSong:
    """What ReadonlySong would read from a download: a publisher and one artist."""

    def __init__(self, publisher, artist='Angerfist'):
        self._publisher = publisher
        self._artist = artist

    def remixers(self):
        return []

    def library_artists(self):
        return [self._artist]

    def publisher(self):
        return self._publisher

    def title(self):
        return 'Raise Your Fist'

    def length(self):
        return 300

    def original_artist(self):
        return None

    def rules_genres(self):
        return []


def linked_channel(db, label='Traxtorm', artist='D-Sturb', approved=True):
    """A SoundCloud channel `TRAXTORM` linked to a label and an artist; returns the channel id."""
    with db.cursor() as cursor:
        cursor.execute('INSERT INTO library_labels (name) VALUES (%s)', (label,))
        label_id = cursor.lastrowid
        cursor.execute('INSERT INTO library_artists (name) VALUES (%s)', (artist,))
        artist_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO rules_artists (name, state) VALUES (%s, %s)', (artist, 'white' if approved else 'black')
        )
        cursor.execute(
            "INSERT INTO channels (platform, name, normalized_name, label_id, artist_id)"
            " VALUES ('soundcloud', 'TRAXTORM', 'traxtorm', %s, %s)",
            (label_id, artist_id),
        )
        channel_id = cursor.lastrowid
    db.commit()
    return channel_id


def load_links(db) -> ChannelLinkHelper:
    helper = ChannelLinkHelper(preload=False)
    helper.set_links(tuple(row.values()) for row in run_sql(db, LINKS_SQL))
    return helper


class LinksSqlTest:
    def test_the_tagger_loads_the_label_and_the_approved_artist(self, db):
        linked_channel(db)
        link = load_links(db).link_for('/mnt/music/Soundcloud/TRAXTORM/a.mp3')
        assert (link.label, link.artist) == ('Traxtorm', 'D-Sturb')

    def test_an_artist_rejected_after_linking_is_not_written(self, db):
        linked_channel(db, approved=False)
        link = load_links(db).link_for('/mnt/music/Soundcloud/TRAXTORM/a.mp3')
        assert (link.label, link.artist) == ('Traxtorm', None)

    def test_an_unlinked_channel_is_not_loaded(self, db):
        run_sql(db, "INSERT INTO channels (platform, name, normalized_name) VALUES ('youtube', 'Free', 'free')")
        assert not run_sql(db, LINKS_SQL)


@pytest.fixture(name='scan')
def scan_fixture(db, tmp_path, monkeypatch):
    """Run the real scanner over one file under `tmp_path` whose tags say `song`."""
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
        return str(path)

    return _scan


def track_labels(db, path):
    return [
        row['name']
        for row in run_sql(
            db,
            'SELECT l.name FROM library_media_files mf JOIN library_track_labels tl ON tl.track_id = mf.track_id '
            'JOIN library_labels l ON l.id = tl.label_id WHERE mf.file_path = %s',
            (path,),
        )
    ]


class ScannerChannelLabelTest:
    def test_a_download_carrying_its_channels_label_is_filed_under_it(self, db, scan):
        channel_id = linked_channel(db)
        path = scan('Soundcloud/TRAXTORM/a.mp3', FakeSong('TRAXTORM'))
        assert track_labels(db, path) == ['Traxtorm']
        # And it is one of the channel's files, which is what a link change queues for retag.
        assert run_sql(db, CHANNEL_FILES_SQL, (channel_id,)) == [{'file_path': path}]

    def test_the_platform_or_another_label_on_a_download_is_still_refused(self, db, scan):
        linked_channel(db)
        assert track_labels(db, scan('Soundcloud/TRAXTORM/b.mp3', FakeSong('Soundcloud'))) == []
        assert track_labels(db, scan('Soundcloud/TRAXTORM/c.mp3', FakeSong('Dirty Workz', artist='Other'))) == []
        assert not run_sql(db, "SELECT name FROM library_labels WHERE name = 'Dirty Workz'")
