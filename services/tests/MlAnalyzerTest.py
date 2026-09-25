"""Covers services/ml-analyzer/analyzer.py.

The ml-analyzer lives in a hyphenated directory and imports its siblings flatly
(``from analyzer import TrackAnalyzer``), so it is not importable as a package.
These tests put its directory on sys.path and load the module by file, the way
the service itself is run.

Its third-party dependencies (SQLAlchemy, numpy, pandas, scikit-learn, joblib,
tqdm) are stubbed by services/tests/mock_base.py: they are not in the root
requirements and CI installs nothing before running this suite. What is asserted
here is therefore the analyzer's own branching and the SQL it issues, never
SQLAlchemy's behaviour.
"""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('librosa', 'sqlalchemy', 'pandas', 'tqdm', 'dotenv')


ML_ANALYZER_DIR = Path(__file__).resolve().parents[1] / 'ml-analyzer'


def load_module(name):
    """Load one ml-analyzer module by path, with its directory importable."""
    if str(ML_ANALYZER_DIR) not in sys.path:
        sys.path.insert(0, str(ML_ANALYZER_DIR))
    spec = importlib.util.spec_from_file_location(name, ML_ANALYZER_DIR / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


analyzer_module = load_module('analyzer')
TrackAnalyzer = analyzer_module.TrackAnalyzer


def analyzer_with(engine=None):
    """A TrackAnalyzer whose __init__ is bypassed, so no engine is built."""
    instance = TrackAnalyzer.__new__(TrackAnalyzer)
    instance._config = MagicMock()
    instance.engine = engine
    instance.max_workers = 1
    instance.verbose = False
    return instance


def sql_is_readable():
    """Make the stubbed sqlalchemy.text() hand back the statement itself.

    Without this every assertion on the SQL would be comparing MagicMock repr.
    """
    return patch.object(analyzer_module, 'text', side_effect=lambda statement: statement)


def connection_yielding(rows):
    """An engine whose connect() hands out a connection scripted with `rows`."""
    connection = MagicMock()
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    result = MagicMock()
    result.fetchone.side_effect = list(rows)
    connection.execute.return_value = result
    return engine, connection, result


class DatabaseEngineTest(unittest.TestCase):
    def build(self, env):
        instance = analyzer_with()
        with patch.dict(os.environ, env, clear=True), patch.object(analyzer_module, 'create_engine') as create_engine:
            engine = instance._get_db_engine()
        return engine, create_engine

    def test_without_a_password_there_is_no_engine_at_all(self):
        engine, create_engine = self.build({})

        self.assertIsNone(engine)
        create_engine.assert_not_called()

    def test_the_connection_url_is_built_from_the_environment(self):
        _engine, create_engine = self.build(
            {
                'DB_HOST': 'db.example',
                'DB_PORT': '3307',
                'DB_USER': 'muma',
                'DB_PASS': 'secret',
                'DB_DB': 'music',
            }
        )

        create_engine.assert_called_once_with('mysql+mysqlconnector://muma:secret@db.example:3307/music')

    def test_a_host_with_a_port_in_it_is_split(self):
        _engine, create_engine = self.build({'DB_HOST': 'db.example:3999', 'DB_PASS': 'secret'})

        self.assertIn('@db.example:3999/', create_engine.call_args[0][0])

    def test_the_defaults_fill_in_what_the_environment_leaves_out(self):
        _engine, create_engine = self.build({'DB_PASS': 'secret'})

        self.assertEqual(
            create_engine.call_args[0][0],
            'mysql+mysqlconnector://music-management:secret@db:3306/music-management',
        )


class LoadAudioTest(unittest.TestCase):
    def test_a_readable_file_yields_its_samples(self):
        instance = analyzer_with()

        with patch.object(analyzer_module.librosa, 'load', return_value=([1, 2], 44100)):
            self.assertEqual(instance.load_audio('/music/a.mp3'), ([1, 2], 44100))

    def test_an_unreadable_file_yields_nothing(self):
        instance = analyzer_with()

        with patch.object(analyzer_module.librosa, 'load', side_effect=Exception('corrupt')):
            self.assertEqual(instance.load_audio('/music/a.mp3'), (None, None))

    def test_there_are_no_features_without_audio(self):
        self.assertIsNone(analyzer_with().extract_audio_features(None, 44100))


class ExtractMetadataTest(unittest.TestCase):
    def setUp(self):
        self.instance = analyzer_with()

    def test_the_source_platform_comes_from_the_path(self):
        metadata = self.instance.extract_metadata('/music/Soundcloud/Angerfist/a.wav')

        self.assertEqual(metadata['source_platform'], 'Soundcloud')

    def test_a_path_without_a_known_platform_leaves_it_unset(self):
        metadata = self.instance.extract_metadata('/music/Albums/Angerfist/a.wav')

        self.assertIsNone(metadata['source_platform'])

    def test_the_label_comes_from_the_folder_below_eps(self):
        metadata = self.instance.extract_metadata('/music/EPs/Roughstate/Angerfist/a.wav')

        self.assertEqual(metadata['label_name'], 'Roughstate')

    def test_an_eps_folder_with_nothing_under_it_yields_no_label(self):
        metadata = self.instance.extract_metadata('/music/EPs')

        self.assertIsNone(metadata['label_name'])

    def test_an_unsupported_extension_reads_no_tags(self):
        metadata = self.instance.extract_metadata('/music/a.wav')

        self.assertEqual(metadata['artist_name'], None)

    def test_an_mp3_is_read_with_the_id3_reader(self):
        with patch.object(self.instance, '_extract_mp3_metadata') as reader:
            self.instance.extract_metadata('/music/a.mp3')

        reader.assert_called_once()

    def test_a_flac_is_read_with_the_flac_reader(self):
        with patch.object(self.instance, '_extract_flac_metadata') as reader:
            self.instance.extract_metadata('/music/a.flac')

        reader.assert_called_once()

    def test_an_m4a_is_read_with_the_mp4_reader(self):
        with patch.object(self.instance, '_extract_m4a_metadata') as reader:
            self.instance.extract_metadata('/music/a.m4a')

        reader.assert_called_once()

    def test_an_unreadable_tag_block_does_not_break_the_analysis(self):
        with patch.object(self.instance, '_extract_mp3_metadata', side_effect=Exception('bad tags')):
            metadata = self.instance.extract_metadata('/music/a.mp3')

        self.assertEqual(metadata['artist_name'], None)


class Mp3MetadataTest(unittest.TestCase):
    def read(self, tags):
        instance = analyzer_with()
        metadata = {'label_name': None}
        with patch('mutagen.easyid3.EasyID3', return_value=tags):
            instance._extract_mp3_metadata('/music/a.mp3', metadata)
        return metadata

    def test_the_common_tags_are_taken_over(self):
        metadata = self.read(
            {
                'artist': ['Angerfist'],
                'genre': ['Hardcore'],
                'publisher': ['Roughstate'],
                'date': ['2024-03-01'],
                'bpm': ['174.5'],
            }
        )

        self.assertEqual(metadata['artist_name'], 'Angerfist')
        self.assertEqual(metadata['genre_tag'], 'Hardcore')
        self.assertEqual(metadata['label_name'], 'Roughstate')
        self.assertEqual(metadata['release_year'], 2024)
        self.assertEqual(metadata['bpm_tag'], 174.5)

    def test_a_label_from_the_path_wins_over_the_publisher_tag(self):
        instance = analyzer_with()
        metadata = {'label_name': 'Roughstate'}
        with patch('mutagen.easyid3.EasyID3', return_value={'publisher': ['Other']}):
            instance._extract_mp3_metadata('/music/a.mp3', metadata)

        self.assertEqual(metadata['label_name'], 'Roughstate')

    def test_an_unparsable_year_is_skipped(self):
        self.assertNotIn('release_year', self.read({'date': ['abcd']}))

    def test_a_short_date_is_ignored(self):
        self.assertNotIn('release_year', self.read({'date': ['24']}))

    def test_an_unparsable_bpm_is_skipped(self):
        self.assertNotIn('bpm_tag', self.read({'bpm': ['fast']}))

    def test_missing_tags_leave_everything_empty(self):
        metadata = self.read({})

        self.assertIsNone(metadata['artist_name'])
        self.assertIsNone(metadata['label_name'])


class FlacAndM4aMetadataTest(unittest.TestCase):
    def test_a_flac_yields_artist_genre_label_and_year(self):
        instance = analyzer_with()
        metadata = {'label_name': None}
        tags = {'artist': ['Angerfist'], 'genre': ['Hardcore'], 'publisher': ['Roughstate'], 'date': ['2024']}

        with patch('mutagen.flac.FLAC', return_value=tags):
            instance._extract_flac_metadata('/music/a.flac', metadata)

        self.assertEqual(metadata['artist_name'], 'Angerfist')
        self.assertEqual(metadata['genre_tag'], 'Hardcore')
        self.assertEqual(metadata['label_name'], 'Roughstate')
        self.assertEqual(metadata['release_year'], 2024)

    def test_an_unparsable_flac_year_is_skipped(self):
        instance = analyzer_with()
        metadata = {'label_name': None}

        with patch('mutagen.flac.FLAC', return_value={'date': ['abcd']}):
            instance._extract_flac_metadata('/music/a.flac', metadata)

        self.assertNotIn('release_year', metadata)

    def test_an_m4a_reads_the_apple_atoms(self):
        instance = analyzer_with()
        metadata = {'label_name': None}
        tags = {
            '©ART': ['Angerfist'],
            '©gen': ['Hardcore'],
            '©day': ['2024-03-01'],
            '----:com.apple.iTunes:PUBLISHER': ['Roughstate'],
        }

        with patch('mutagen.mp4.MP4', return_value=tags):
            instance._extract_m4a_metadata('/music/a.m4a', metadata)

        self.assertEqual(metadata['artist_name'], 'Angerfist')
        self.assertEqual(metadata['genre_tag'], 'Hardcore')
        self.assertEqual(metadata['label_name'], 'Roughstate')
        self.assertEqual(metadata['release_year'], 2024)


class IsAlreadyAnalyzedTest(unittest.TestCase):
    def test_without_a_database_nothing_counts_as_analyzed(self):
        self.assertFalse(analyzer_with().is_already_analyzed('track-1'))

    def test_a_row_means_the_track_was_analyzed(self):
        engine, _connection, _result = connection_yielding([(1,)])

        self.assertTrue(analyzer_with(engine).is_already_analyzed('track-1'))

    def test_no_row_means_it_was_not(self):
        engine, _connection, _result = connection_yielding([None])

        self.assertFalse(analyzer_with(engine).is_already_analyzed('track-1'))

    def test_a_database_failure_reads_as_not_analyzed(self):
        engine = MagicMock()
        engine.connect.side_effect = Exception('DB down')

        self.assertFalse(analyzer_with(engine).is_already_analyzed('track-1'))


class GetTrackInfoTest(unittest.TestCase):
    PATH = '/music/Angerfist/raise-your-fist.mp3'

    def expected_hash(self):
        import hashlib

        return hashlib.sha256(self.PATH.encode()).hexdigest()

    def test_without_a_database_only_the_path_hash_comes_back(self):
        self.assertEqual(analyzer_with().get_track_info(self.PATH), (self.expected_hash(), None))

    def test_a_known_media_file_yields_its_internal_track_id(self):
        engine, _connection, _result = connection_yielding([(42, 7)])

        self.assertEqual(analyzer_with(engine).get_track_info(self.PATH), (self.expected_hash(), 42))

    def test_a_media_file_without_a_track_gets_one_created(self):
        engine, connection, result = connection_yielding([(None, 7)])
        connection.execute.return_value.scalar.return_value = 99

        with sql_is_readable():
            track_hash, internal_id = analyzer_with(engine).get_track_info(self.PATH)

        self.assertEqual((track_hash, internal_id), (self.expected_hash(), 99))
        statements = [call.args[0] for call in connection.execute.call_args_list]
        self.assertTrue(any('INSERT INTO library_tracks' in s for s in statements))
        self.assertTrue(any('UPDATE library_media_files' in s for s in statements))
        connection.commit.assert_called_once()

    def test_an_unknown_file_is_registered_as_a_new_track_and_media_file(self):
        engine, connection, _result = connection_yielding([None])
        connection.execute.return_value.scalar.return_value = 99

        with (
            sql_is_readable(),
            patch.object(analyzer_module.os.path, 'exists', return_value=True),
            patch.object(analyzer_module.os.path, 'getsize', return_value=1234),
            patch.object(analyzer_module.os.path, 'getmtime', return_value=99.0),
        ):
            track_hash, internal_id = analyzer_with(engine).get_track_info(self.PATH)

        self.assertEqual((track_hash, internal_id), (self.expected_hash(), 99))
        statements = [call.args[0] for call in connection.execute.call_args_list]
        self.assertTrue(any('INSERT INTO library_media_files' in s for s in statements))

    def test_a_missing_file_is_registered_with_a_zero_size(self):
        engine, connection, _result = connection_yielding([None])
        connection.execute.return_value.scalar.return_value = 99

        with sql_is_readable(), patch.object(analyzer_module.os.path, 'exists', return_value=False):
            analyzer_with(engine).get_track_info(self.PATH)

        insert = next(
            call for call in connection.execute.call_args_list if 'INSERT INTO library_media_files' in call.args[0]
        )
        self.assertEqual(insert.args[1]['size'], 0)
        self.assertEqual(insert.args[1]['mtime'], 0)

    def test_a_database_failure_still_yields_the_path_hash(self):
        engine = MagicMock()
        engine.connect.side_effect = Exception('DB down')

        self.assertEqual(analyzer_with(engine).get_track_info(self.PATH), (self.expected_hash(), None))


class AnalyzeTrackTest(unittest.TestCase):
    def setUp(self):
        self.instance = analyzer_with()
        self.instance.get_track_info = MagicMock(return_value=('hash-1', 42))
        self.instance.extract_metadata = MagicMock(return_value={'artist_name': 'Angerfist'})
        self.instance.load_audio = MagicMock(return_value=([1], 44100))
        self.instance.extract_audio_features = MagicMock(return_value={'tempo': 174.0})
        self.instance.is_already_analyzed = MagicMock(return_value=False)
        self.instance.save_features = MagicMock()

    def test_the_result_merges_the_features_and_the_tags(self):
        result = self.instance.analyze_track('/music/a.mp3')

        self.assertEqual(result, {'tempo': 174.0, 'artist_name': 'Angerfist'})

    def test_a_tags_only_run_never_touches_the_audio(self):
        result = self.instance.analyze_track('/music/a.mp3', tags_only=True)

        self.instance.load_audio.assert_not_called()
        self.assertEqual(result, {'artist_name': 'Angerfist'})

    def test_an_already_analyzed_track_is_skipped(self):
        self.instance.is_already_analyzed.return_value = True

        self.assertIsNone(self.instance.analyze_track('/music/a.mp3', skip_existing=True))

    def test_a_tags_only_run_is_never_skipped(self):
        self.instance.is_already_analyzed.return_value = True

        self.assertIsNotNone(self.instance.analyze_track('/music/a.mp3', skip_existing=True, tags_only=True))

    def test_the_internal_id_is_what_gets_checked_for_existing_analysis(self):
        self.instance.analyze_track('/music/a.mp3', skip_existing=True)

        self.instance.is_already_analyzed.assert_called_once_with('42')

    def test_without_an_internal_id_the_path_hash_is_checked_instead(self):
        self.instance.get_track_info.return_value = ('hash-1', None)

        self.instance.analyze_track('/music/a.mp3', skip_existing=True)

        self.instance.is_already_analyzed.assert_called_once_with('hash-1')

    def test_unreadable_audio_still_yields_the_tags(self):
        self.instance.load_audio.return_value = (None, None)

        result = self.instance.analyze_track('/music/a.mp3')

        self.instance.extract_audio_features.assert_not_called()
        self.assertEqual(result, {'artist_name': 'Angerfist'})

    def test_saving_hands_everything_to_save_features(self):
        self.instance.analyze_track('/music/a.mp3', save=True)

        self.instance.save_features.assert_called_once_with(
            'hash-1',
            {'tempo': 174.0},
            internal_track_id=42,
            metadata={'artist_name': 'Angerfist'},
            file_path='/music/a.mp3',
        )

    def test_nothing_is_written_unless_saving_was_asked_for(self):
        self.instance.analyze_track('/music/a.mp3')

        self.instance.save_features.assert_not_called()


class ReleaseDatePrecisionTest(unittest.TestCase):
    """The analyzer used to reduce every date to a year; the full value now travels beside it."""

    def test_a_full_date_is_kept_whole(self):
        self.assertEqual(TrackAnalyzer._partial_date('2026-01-16'), '2026-01-16')

    def test_a_compact_date_is_normalised(self):
        self.assertEqual(TrackAnalyzer._partial_date('20260116'), '2026-01-16')

    def test_a_month_precision_value_is_kept_as_a_month(self):
        self.assertEqual(TrackAnalyzer._partial_date('2026-01'), '2026-01')

    def test_a_year_stays_a_year(self):
        self.assertEqual(TrackAnalyzer._partial_date('2026'), '2026')

    def test_a_timestamp_is_trimmed_to_the_date(self):
        """Slicing to ten characters first stops a timestamp's time digits reading as a longer date."""
        self.assertEqual(TrackAnalyzer._partial_date('2026-01-16T00:00:00Z'), '2026-01-16')

    def test_junk_yields_nothing(self):
        self.assertIsNone(TrackAnalyzer._partial_date('sometime'))
        self.assertIsNone(TrackAnalyzer._partial_date(''))
        self.assertIsNone(TrackAnalyzer._partial_date(None))


if __name__ == '__main__':
    unittest.main()
