"""The GetSongBPM lookup (issue #152): key, parsing, the client's refusals, the cache and a pass.

No test goes over the network: the HTTP client and the database are fakes. The bodies below have
the shape api.getsongbpm.com answers `/search/?type=both` with.
"""

import logging
from datetime import datetime, timedelta

import pytest

from services.music_manager.bpm import getsongbpm, octave
from services.music_manager.bpm.priors import Priors

NOW = datetime(2026, 11, 10, 12, 0, 0)

#: A found song, as `/search/?type=both&lookup=song:... artist:...` returns it.
FOUND = {
    'search': [
        {
            'id': 'x9Kq2',
            'title': 'Vaag en stil',
            'uri': 'https://getsongbpm.com/song/vaag-en-stil/x9Kq2',
            'artist': {'id': 'aB3', 'name': 'André Hazes', 'uri': 'https://getsongbpm.com/artist/andre-hazes/aB3'},
            'tempo': '128',
            'time_sig': '4/4',
            'key_of': 'G',
            'album': {'title': 'Live', 'year': '1990'},
        }
    ]
}
#: Nothing matched.
NO_RESULT = {'search': {'error': 'no result'}}


class FakePace:
    """Records waits instead of sleeping."""

    def __init__(self):
        self.waits = 0

    def wait(self):
        self.waits += 1


class FakeHttp:
    """Answers each GET with the next (status, body), and records the parameters."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, url, params):
        self.calls.append((url, dict(params)))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


# ----------------------------------------------------------------------------- key and parsing


def test_the_key_ignores_case_accents_brackets_and_featuring():
    key = getsongbpm.lookup_key('André Hazes', 'Vaag en Stil')
    assert len(key) == 40
    assert getsongbpm.lookup_key('ANDRE HAZES', 'vaag en stil (Live)') == key
    assert getsongbpm.lookup_key('André Hazes feat. Jan Smit', 'Vaag en Stil [Remastered]') == key
    assert getsongbpm.lookup_key('André Hazes & Jan Smit', 'Vaag en Stil') == key
    assert getsongbpm.lookup_key('André Hazes', 'Zeg maar niets meer') != key


def test_no_key_without_an_artist_or_a_title():
    assert getsongbpm.lookup_key('', 'Title') is None
    assert getsongbpm.lookup_key('Artist', '(Intro)') is None
    assert getsongbpm.lookup_key(None, None) is None


def test_the_search_terms_drop_what_the_listing_does_not_have():
    assert getsongbpm.clean_title('Titanium (feat. Sia) [Radio Edit]') == 'Titanium'
    assert getsongbpm.clean_title('Dancing with Myself') == 'Dancing with Myself'
    assert getsongbpm.clean_artist('Armin van Buuren & Davina Michelle') == 'Armin van Buuren'
    assert getsongbpm.clean_artist('David Guetta ft. Sia') == 'David Guetta'


def test_a_found_song_gives_its_tempo_id_and_page():
    assert getsongbpm.parse_search(FOUND, 'André Hazes', 'Vaag en Stil') == (
        128.0,
        'x9Kq2',
        'https://getsongbpm.com/song/vaag-en-stil/x9Kq2',
    )


@pytest.mark.parametrize(
    'body',
    [
        NO_RESULT,
        {'search': []},
        {'search': None},
        None,
        [],
        {'search': [{'title': 'Vaag en Stil', 'artist': {'name': 'Someone Else'}, 'tempo': '128'}]},
        {'search': [{'title': 'Another Song', 'artist': {'name': 'André Hazes'}, 'tempo': '128'}]},
        {'search': [{'title': 'Vaag en Stil', 'artist': {'name': 'André Hazes'}, 'tempo': ''}]},
        {'search': [{'title': 'Vaag en Stil', 'artist': {'name': 'André Hazes'}, 'tempo': '0'}]},
        {'search': ['not a song', {'title': None}]},
    ],
)
def test_anything_else_is_no_match(body):
    assert getsongbpm.parse_search(body, 'André Hazes', 'Vaag en Stil') is None


def test_the_parser_takes_numbers_a_plain_artist_name_and_skips_to_the_matching_result():
    body = {
        'search': [
            {'title': 'Vaag en Stil', 'artist': {'name': 'Cover Band'}, 'tempo': 90},
            {'title': 'Vaag en Stil (Live)', 'artist': 'Andre Hazes', 'tempo': 127.5},
        ]
    }
    assert getsongbpm.parse_search(body, 'André Hazes', 'Vaag en Stil') == (127.5, None, None)


def test_a_duo_listed_in_full_matches_its_first_artist():
    body = {'search': [{'title': 'Titanium', 'artist': {'name': 'David Guetta & Sia'}, 'tempo': '126'}]}
    assert getsongbpm.parse_search(body, 'David Guetta feat. Sia', 'Titanium (Radio Edit)')[0] == 126.0


# ----------------------------------------------------------------------------- the client


def test_a_lookup_sends_the_key_and_the_cleaned_terms_and_waits_for_its_slot():
    http, pace = FakeHttp((200, FOUND)), FakePace()
    found = getsongbpm.fetch('André Hazes', 'Vaag en Stil (Live)', 'k3y', http, pace)
    assert found == getsongbpm.Lookup(
        getsongbpm.lookup_key('André Hazes', 'Vaag en Stil'),
        'André Hazes',
        'Vaag en Stil',
        getsongbpm.OK,
        128.0,
        'x9Kq2',
        'https://getsongbpm.com/song/vaag-en-stil/x9Kq2',
    )
    url, params = http.calls[0]
    assert url == getsongbpm.API_URL
    assert params == {'api_key': 'k3y', 'type': 'both', 'lookup': 'song:Vaag en Stil artist:André Hazes'}
    assert pace.waits == 1


def test_no_result_is_a_stored_miss():
    found = getsongbpm.fetch('André Hazes', 'Vaag en Stil', 'k3y', FakeHttp((200, NO_RESULT)), FakePace())
    assert (found.status, found.bpm) == (getsongbpm.NOT_FOUND, None)


def test_a_rate_limit_and_a_refused_key_stop_the_pass():
    with pytest.raises(getsongbpm.Throttled):
        getsongbpm.fetch('A', 'B', 'k', FakeHttp((429, None)), FakePace())
    for answer in ((401, None), (200, {'error': 'API key not valid'})):
        with pytest.raises(getsongbpm.KeyRejected):
            getsongbpm.fetch('A', 'B', 'k', FakeHttp(answer), FakePace())


def test_a_transient_failure_is_none_and_never_logs_the_key(caplog):
    caplog.set_level(logging.INFO, logger='music-manager.bpm')
    error = ConnectionError('GET https://api.getsongbpm.com/search/?api_key=s3cret failed')
    assert getsongbpm.fetch('A', 'B', 's3cret', FakeHttp(error), FakePace()) is None
    assert getsongbpm.fetch('A', 'B', 's3cret', FakeHttp((500, None)), FakePace()) is None
    assert 's3cret' not in caplog.text
    assert 'ConnectionError' in caplog.text


def test_nothing_is_asked_without_artist_or_title():
    http = FakeHttp()
    assert getsongbpm.fetch('', 'B', 'k', http, FakePace()) is None
    assert http.calls == []


def test_the_client_names_itself_through_the_shared_builder(monkeypatch):
    monkeypatch.setattr(getsongbpm, '_user_agent', lambda product, version: f'{product}/{version}')
    assert getsongbpm.user_agent() == 'muma-bpm-analyzer/0.1'


# ----------------------------------------------------------------------------- the cache and a pass


class FakeCursor:
    """Answers each SQL by its first words; records every execute."""

    def __init__(self, db):
        self.db = db
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.db.executed.append((sql, tuple(params)))
        if sql == getsongbpm.KNOWN_SQL:
            self.result = self.db.known
        elif sql == getsongbpm.TEMPOS_SQL:
            self.result = [{'lookup_key': key, 'bpm': bpm} for key, bpm in self.db.tempos.items()]
        elif 'FROM library_track_bpm b' in sql:
            self.result = self.db.candidates
        else:
            self.result = []

    def fetchall(self):
        return self.result


class FakeDb:
    """A connection factory over fixed rows."""

    def __init__(self, candidates=(), known=(), tempos=None):
        self.candidates = list(candidates)
        self.known = list(known)
        self.tempos = dict(tempos or {})
        self.executed = []
        self.commits = 0

    def __call__(self):
        return self

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        pass

    def upserts(self):
        return [params for sql, params in self.executed if sql == getsongbpm.UPSERT_SQL]


def candidate(track_id, artist, title, root='Hitzone', artist_id=None, labels=None):
    """One CANDIDATES_SQL row."""
    return {
        'track_id': track_id,
        'artist_name': artist,
        'title': title,
        'primary_artist_id': artist_id,
        'labels': labels,
        'file_path': f'/mnt/music/{root}/Some Album/{title}.mp3',
    }


def test_the_candidates_are_the_mainstream_roots_bound_as_parameters():
    sql, params = getsongbpm.candidates_sql()
    assert sql.count('%s') == len(params) == len(octave.MAINSTREAM_ROOTS)
    assert '/mnt/music/hitzone/%' in params
    assert 'ORDER BY t.id DESC' in sql


def test_found_songs_and_fresh_misses_are_settled_old_misses_are_due():
    rows = [
        {'lookup_key': 'found', 'status': 'ok', 'fetched_at': NOW - timedelta(days=400)},
        {'lookup_key': 'fresh-miss', 'status': 'not_found', 'fetched_at': NOW - timedelta(days=1)},
        {'lookup_key': 'old-miss', 'status': 'not_found', 'fetched_at': NOW - timedelta(days=91)},
    ]
    assert getsongbpm.due_keys(rows, NOW) == {'found', 'fresh-miss'}


def test_load_tempos_reads_the_found_songs():
    assert getsongbpm.load_tempos(FakeDb(tempos={'k': 128.0})) == {'k': 128.0}


def test_a_pass_asks_once_per_song_skips_strong_priors_and_stores_every_answer():
    settled = getsongbpm.lookup_key('Known', 'Song')
    db = FakeDb(
        candidates=[
            candidate(9, 'André Hazes', 'Vaag en Stil'),
            candidate(8, 'André Hazes', 'Vaag en Stil (Live)'),  # the same song: one request
            candidate(7, 'Known', 'Song'),  # already in the cache
            candidate(6, 'Prior Artist', 'Song', artist_id=55),  # has an artist prior
            candidate(5, 'Underground', 'Track', root='Soundcloud'),  # not mainstream
            candidate(4, 'Nobody', 'Unknown Song'),
        ],
        known=[{'lookup_key': settled, 'status': 'ok', 'fetched_at': NOW}],
    )
    loaded = Priors(artist={55: octave.Prior.around(128.0, 0.2, 40)})
    http = FakeHttp((200, FOUND), (200, NO_RESULT))
    result = getsongbpm.lookup_pass(db, loaded, 'k3y', NOW, http_get=http, pace=FakePace())
    assert [params['lookup'] for _, params in http.calls] == [
        'song:Vaag en Stil artist:André Hazes',
        'song:Unknown Song artist:Nobody',
    ]
    assert (result.asked, result.found, result.not_found, result.stopped) == (2, 1, 1, None)
    assert result.track_ids == [9, 8]
    assert result.tempos == {getsongbpm.lookup_key('André Hazes', 'Vaag en Stil'): 128.0}
    stored = db.upserts()
    assert [(row[3], row[4]) for row in stored] == [('ok', 128.0), ('not_found', None)]
    assert stored[0][-1] == NOW
    assert db.commits == 2


def test_a_pass_keeps_to_its_budget_and_stops_on_a_refusal():
    db = FakeDb(candidates=[candidate(i, f'Artist {i}', f'Song {i}') for i in range(10)])
    http = FakeHttp((200, NO_RESULT), (200, NO_RESULT), (200, NO_RESULT))
    result = getsongbpm.lookup_pass(db, Priors(), 'k', NOW, budget=3, http_get=http, pace=FakePace())
    assert result.asked == 3
    http = FakeHttp((200, NO_RESULT), (429, None))
    result = getsongbpm.lookup_pass(db, Priors(), 'k', NOW, http_get=http, pace=FakePace())
    assert (result.asked, result.stopped) == (1, 'Throttled')


def test_a_pass_without_a_key_asks_nothing():
    db = FakeDb(candidates=[candidate(1, 'A', 'B')])
    assert getsongbpm.lookup_pass(db, Priors(), '', NOW, http_get=FakeHttp()).asked == 0
    assert db.executed == []


def test_the_evidence_prior_is_only_read_for_weak_priors():
    key = getsongbpm.lookup_key('André Hazes', 'Vaag en Stil')
    row = {'artist_name': 'André Hazes', 'title': 'Vaag en Stil'}
    weak = octave.Evidence(root='Hitzone')
    assert getsongbpm.evidence_prior(row, weak, {key: 128.0}) == octave.Prior.around(128.0, octave.EXTERNAL_SPREAD)
    assert getsongbpm.evidence_prior(row, weak, {}) is None
    assert getsongbpm.evidence_prior(row, octave.Evidence(root='EPs'), {key: 128.0}) is None
