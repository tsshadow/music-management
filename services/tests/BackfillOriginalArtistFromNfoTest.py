"""Covers scripts/backfill_original_artist_from_nfo.py.

The backfill writes a tag onto files across the whole EPs tree, so what matters is what it plans:
it has to restore wording for a track the NFO demonstrably describes, and refuse every case where
the line and the file disagree -- a wrong write here invents an artist credit that was never there.
"""

import importlib.util
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'backfill_original_artist_from_nfo.py'

spec = importlib.util.spec_from_file_location('backfill_original_artist_from_nfo', SCRIPT)
backfill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backfill)

NFO = """
   01. Eternate & Prosphere - Waiting For You [03:39]
   02. Oxya - The Desert [04:12]
"""

SINGLE_NFO = '   RLS NAME : Arzadous & Equalizer - Nothing Inside\n'


def _plan(nfo_text, files, artist_state):
    """Plan one release directory without touching a filesystem."""
    with (
        patch.object(backfill, 'read_nfo', return_value=nfo_text),
        patch.object(backfill, 'audio_files', return_value=files),
        patch.object(backfill, 'read_artist_state', side_effect=lambda path: artist_state[path]),
    ):
        return backfill.plan_release('/mnt/music/EPs/Label/Release')


class FileNumberTest:
    def test_reads_the_leading_number(self):
        assert backfill.file_number('01_artist_-_title.mp3') == 1
        assert backfill.file_number('03-artist-title.mp3') == 3

    def test_keeps_the_disc_digit_of_a_multi_disc_rip(self):
        assert backfill.file_number('116-rob_gee_-_gabber.mp3') == 116

    def test_a_file_without_a_number_has_none(self):
        assert backfill.file_number('rob_gee_-_gabber.mp3') is None


class PlanReleaseTest:
    def test_restores_wording_the_nfo_and_the_tag_agree_on(self):
        planned, counts = _plan(
            NFO,
            {1: '/a/01.mp3'},
            {'/a/01.mp3': (['Eternate', 'Prosphere'], None)},
        )
        assert planned == [('/a/01.mp3', 'Eternate & Prosphere')]
        assert counts['to_write'] == 1

    def test_refuses_a_line_naming_different_artists(self):
        planned, counts = _plan(
            NFO,
            {1: '/a/01.mp3'},
            {'/a/01.mp3': (['Hellfish', 'Akira'], None)},
        )
        assert planned == []
        assert counts['nothing_to_restore'] == 1

    def test_leaves_a_file_that_already_has_an_original_alone(self):
        planned, counts = _plan(
            NFO,
            {1: '/a/01.mp3'},
            {'/a/01.mp3': (['Eternate', 'Prosphere'], 'Eternate & Prosphere')},
        )
        assert planned == []
        assert counts['already_has_original'] == 1

    def test_a_single_artist_track_yields_nothing_to_restore(self):
        planned, _counts = _plan(NFO, {2: '/a/02.mp3'}, {'/a/02.mp3': (['Oxya'], None)})
        assert planned == []

    def test_a_line_without_a_matching_file_is_counted_not_guessed(self):
        planned, counts = _plan(NFO, {7: '/a/07.mp3'}, {'/a/07.mp3': (['Whoever'], None)})
        assert planned == []
        assert counts['no_file_for_line'] == 2

    def test_a_release_header_speaks_for_a_single_track_directory(self):
        planned, _counts = _plan(
            SINGLE_NFO,
            {1: '/a/01.mp3'},
            {'/a/01.mp3': (['Arzadous', 'Equalizer'], None)},
        )
        assert planned == [('/a/01.mp3', 'Arzadous & Equalizer')]

    def test_a_release_header_is_not_applied_to_a_multi_track_directory(self):
        planned, _counts = _plan(
            SINGLE_NFO,
            {1: '/a/01.mp3', 2: '/a/02.mp3'},
            {'/a/01.mp3': (['Arzadous', 'Equalizer'], None), '/a/02.mp3': (['Arzadous'], None)},
        )
        assert planned == []

    def test_a_directory_without_an_nfo_is_skipped(self):
        planned, counts = _plan(None, {1: '/a/01.mp3'}, {})
        assert planned == []
        assert counts['no_nfo'] == 1

    def test_an_unreadable_file_does_not_stop_the_release(self):
        def state(path):
            if path == '/a/01.mp3':
                raise OSError('refused')
            return (['Oxya'], None)

        with (
            patch.object(backfill, 'read_nfo', return_value=NFO),
            patch.object(backfill, 'audio_files', return_value={1: '/a/01.mp3', 2: '/a/02.mp3'}),
            patch.object(backfill, 'read_artist_state', side_effect=state),
            patch.object(backfill, 'with_retries', side_effect=lambda work, path: work()),
        ):
            planned, counts = backfill.plan_release('/mnt/music/EPs/Label/Release')
        assert planned == []
        assert counts['unreadable'] == 1


class AudioFilesTest:
    def test_a_number_claimed_by_two_files_is_dropped(self, tmp_path):
        for name in ('01_a.mp3', '01_b.mp3', '02_c.mp3'):
            (tmp_path / name).write_bytes(b'')
        found = backfill.audio_files(str(tmp_path))
        assert set(found) == {2}

    def test_files_without_a_number_are_ignored(self, tmp_path):
        (tmp_path / 'cover.jpg').write_bytes(b'')
        (tmp_path / 'sleeve.mp3').write_bytes(b'')
        assert backfill.audio_files(str(tmp_path)) == {}


def _apply(rows, artist_state, failed_path=None, writes=None):
    """Apply a plan without touching a filesystem, recording what it would write."""
    written = writes if writes is not None else []

    with (
        patch.object(backfill, 'read_artist_state', side_effect=lambda path: artist_state[path]),
        patch.object(backfill, 'with_retries', side_effect=lambda work, path: work()),
        patch.object(
            backfill,
            'write_original_artist',
            side_effect=lambda path, value: written.append((path, value)),
        ),
    ):
        return backfill.apply_plan(rows, failed_path)


class ApplyPlanTest:
    """The plan is hours old by the time it is written, so the guard is asked again per file."""

    def test_writes_a_row_whose_guard_still_holds(self):
        writes = []
        counts, failed = _apply(
            [('/a/01.mp3', 'Eternate & Prosphere')],
            {'/a/01.mp3': (['Eternate', 'Prosphere'], None)},
            writes=writes,
        )
        assert writes == [('/a/01.mp3', 'Eternate & Prosphere')]
        assert counts['written'] == 1
        assert failed == []

    def test_leaves_a_credit_the_file_gained_since_the_plan(self):
        writes = []
        counts, _failed = _apply(
            [('/a/01.mp3', 'Eternate & Prosphere')],
            {'/a/01.mp3': (['Eternate', 'Prosphere'], 'Eternate feat. Prosphere')},
            writes=writes,
        )
        assert writes == []
        assert counts['skipped_gained_original'] == 1
        assert counts['written'] == 0

    def test_refuses_a_wording_the_artists_no_longer_match(self):
        writes = []
        counts, _failed = _apply(
            [('/a/01.mp3', 'Eternate & Prosphere')],
            {'/a/01.mp3': (['Oxya'], None)},
            writes=writes,
        )
        assert writes == []
        assert counts['skipped_artists_changed'] == 1

    def test_a_refused_file_is_recorded_so_it_can_be_replayed(self, tmp_path):
        failed_file = tmp_path / 'plan.txt.failed'

        def refuse(path, value):
            raise PermissionError(13, 'Permission denied')

        with (
            patch.object(
                backfill,
                'read_artist_state',
                side_effect=lambda path: (['Eternate', 'Prosphere'], None),
            ),
            patch.object(backfill, 'with_retries', side_effect=lambda work, path: work()),
            patch.object(backfill, 'write_original_artist', side_effect=refuse),
        ):
            counts, failed = backfill.apply_plan([('/a/01.mp3', 'Eternate & Prosphere')], str(failed_file))

        assert counts['refused'] == 1
        assert failed == [('/a/01.mp3', 'Eternate & Prosphere')]
        assert backfill.load_plan(str(failed_file)) == [('/a/01.mp3', 'Eternate & Prosphere')]
