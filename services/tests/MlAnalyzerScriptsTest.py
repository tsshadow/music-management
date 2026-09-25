"""Covers the ml-analyzer's maintenance scripts: the schema fixer, the path
migration and the metadata refresh.

See services/tests/MlAnalyzerTest.py for why these modules are loaded by file and
why their third-party dependencies are stubbed.
"""

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('librosa', 'sqlalchemy', 'pandas', 'tqdm', 'dotenv')


from services.tests.MlAnalyzerTest import load_module

fix_db_schema = load_module('fix_db_schema')
migrate_paths = load_module('migrate_paths')
update_metadata = load_module('update_metadata')


def analyzer_returning(engine):
    """Patch TrackAnalyzer in a script module so it hands back a scripted engine."""
    instance = MagicMock()
    instance.engine = engine
    return instance


def readable_sql(module):
    """Make the stubbed sqlalchemy.text() in `module` return the statement itself."""
    return patch.object(module, 'text', side_effect=lambda statement: statement)


class FixSchemaTest(unittest.TestCase):
    def run_fix(self, existing_columns=None, has_table=True, alter_fails=False):
        connection = MagicMock()
        if alter_fails:
            connection.execute.side_effect = Exception('no permission')
        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = connection
        inspector = MagicMock()
        inspector.has_table.return_value = has_table
        inspector.get_columns.return_value = [{'name': name} for name in (existing_columns or [])]

        with (
            patch.object(fix_db_schema, 'TrackAnalyzer', return_value=analyzer_returning(engine)),
            patch.object(fix_db_schema, 'inspect', return_value=inspector),
            readable_sql(fix_db_schema),
        ):
            fix_db_schema.fix_schema()
        return connection

    def test_a_missing_column_is_added(self):
        connection = self.run_fix(existing_columns=[])

        statements = [call.args[0] for call in connection.execute.call_args_list]
        self.assertIn('ALTER TABLE library_track_audio_features ADD COLUMN internal_track_id INT', statements)
        self.assertIn(
            'ALTER TABLE library_track_ml_labels ADD COLUMN approved_for_training BOOLEAN DEFAULT FALSE',
            statements,
        )

    def test_a_column_that_is_already_there_is_left_alone(self):
        columns = [
            'internal_track_id',
            'file_path',
            'artist_name',
            'label_name',
            'release_year',
            'source_platform',
            'bpm_tag',
            'genre_tag',
            'ml_review_status',
            'approved_for_training',
        ]

        connection = self.run_fix(existing_columns=columns)

        connection.execute.assert_not_called()

    def test_a_table_that_does_not_exist_yet_is_skipped(self):
        connection = self.run_fix(existing_columns=[], has_table=False)

        connection.execute.assert_not_called()

    def test_an_alter_that_is_refused_does_not_stop_the_rest(self):
        connection = self.run_fix(existing_columns=[], alter_fails=True)

        self.assertEqual(len(connection.execute.call_args_list), 10)

    def test_nothing_happens_without_a_database(self):
        with (
            patch.object(fix_db_schema, 'TrackAnalyzer', return_value=analyzer_returning(None)),
            patch.object(fix_db_schema, 'inspect') as inspect,
        ):
            fix_db_schema.fix_schema()

        inspect.assert_not_called()


class MigratePathsTest(unittest.TestCase):
    def run_migration(self, failure=None, rowcount=3):
        connection = MagicMock()
        if failure is not None:
            connection.execute.side_effect = failure
        else:
            connection.execute.return_value.rowcount = rowcount
        engine = MagicMock()
        engine.begin.return_value.__enter__.return_value = connection

        with (
            patch.object(migrate_paths, 'TrackAnalyzer', return_value=analyzer_returning(engine)),
            readable_sql(migrate_paths),
        ):
            migrate_paths.migrate_paths()
        return connection

    def test_the_backfill_joins_the_media_files_onto_the_features(self):
        connection = self.run_migration()

        statement = connection.execute.call_args[0][0]
        self.assertIn('UPDATE library_track_audio_features', statement)
        self.assertIn('JOIN library_media_files', statement)
        self.assertIn('WHERE f.file_path IS NULL OR f.internal_track_id IS NULL', statement)

    def test_an_outdated_schema_points_at_the_schema_fixer(self):
        with patch('builtins.print') as printed:
            self.run_migration(failure=Exception("Unknown column 'file_path'"))

        output = ' '.join(str(call.args[0]) for call in printed.call_args_list if call.args)
        self.assertIn('fix_db_schema.py', output)

    def test_any_other_failure_is_reported_as_itself(self):
        with patch('builtins.print') as printed:
            self.run_migration(failure=Exception('deadlock'))

        output = ' '.join(str(call.args[0]) for call in printed.call_args_list if call.args)
        self.assertIn('deadlock', output)
        self.assertNotIn('fix_db_schema.py', output)

    def test_nothing_happens_without_a_database(self):
        analyzer = analyzer_returning(None)

        with patch.object(migrate_paths, 'TrackAnalyzer', return_value=analyzer):
            migrate_paths.migrate_paths()

        analyzer.engine = None


class UpdateMetadataTest(unittest.TestCase):
    def run_update(self, rows, metadata=None, path_exists=True, lookup=None, update_fails=False):
        connection = MagicMock()
        select_result = MagicMock()
        select_result.__iter__.return_value = iter([MagicMock(_mapping=row) for row in rows])
        connection.execute.return_value = select_result
        # Always pinned: an unset fetchone() would hand back a truthy MagicMock, and a
        # row whose path cannot be found would look like a row that has one.
        connection.execute.return_value.fetchone.return_value = lookup

        write_connection = MagicMock()
        if update_fails:
            write_connection.execute.side_effect = Exception('deadlock')

        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection
        engine.begin.return_value.__enter__.return_value = write_connection

        analyzer = analyzer_returning(engine)
        analyzer.extract_metadata.return_value = metadata or {
            'artist_name': 'Angerfist',
            'label_name': 'Roughstate',
            'release_year': 2024,
            'bpm_tag': 174.0,
            'genre_tag': 'Hardcore',
            'source_platform': 'Soundcloud',
        }

        with (
            patch.object(update_metadata, 'TrackAnalyzer', return_value=analyzer),
            patch.object(update_metadata.os.path, 'exists', return_value=path_exists),
            readable_sql(update_metadata),
        ):
            update_metadata.update_metadata()
        return analyzer, write_connection

    def test_the_tags_of_every_track_are_written_back(self):
        rows = [{'track_id': 'hash-1', 'file_path': '/music/a.mp3', 'internal_track_id': 1}]

        analyzer, write_connection = self.run_update(rows)

        analyzer.extract_metadata.assert_called_once_with('/music/a.mp3')
        statement, params = write_connection.execute.call_args[0]
        self.assertIn('UPDATE library_track_audio_features', statement)
        self.assertEqual(params['artist'], 'Angerfist')
        self.assertEqual(params['tid'], 'hash-1')

    def test_a_row_without_a_path_is_looked_up_by_its_hash(self):
        rows = [{'track_id': 'hash-1', 'file_path': None, 'internal_track_id': 1}]

        analyzer, _write_connection = self.run_update(rows, lookup=('/music/found.mp3',))

        analyzer.extract_metadata.assert_called_once_with('/music/found.mp3')

    def test_a_row_whose_path_cannot_be_found_is_skipped(self):
        rows = [{'track_id': 'hash-1', 'file_path': None, 'internal_track_id': 1}]

        analyzer, _write_connection = self.run_update(rows, lookup=None)

        analyzer.extract_metadata.assert_not_called()

    def test_a_file_that_is_no_longer_on_disk_is_skipped(self):
        rows = [{'track_id': 'hash-1', 'file_path': '/music/gone.mp3', 'internal_track_id': 1}]

        analyzer, _write_connection = self.run_update(rows, path_exists=False)

        analyzer.extract_metadata.assert_not_called()

    def test_a_failing_write_does_not_stop_the_run(self):
        rows = [
            {'track_id': 'hash-1', 'file_path': '/music/a.mp3', 'internal_track_id': 1},
            {'track_id': 'hash-2', 'file_path': '/music/b.mp3', 'internal_track_id': 2},
        ]

        analyzer, _write_connection = self.run_update(rows, update_fails=True)

        self.assertEqual(analyzer.extract_metadata.call_count, 2)

    def test_an_empty_table_is_reported_rather_than_iterated(self):
        analyzer, write_connection = self.run_update([])

        analyzer.extract_metadata.assert_not_called()
        write_connection.execute.assert_not_called()

    def test_an_outdated_schema_points_at_the_schema_fixer(self):
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value.execute.side_effect = Exception("Unknown column 'file_path'")
        analyzer = analyzer_returning(engine)

        with (
            patch.object(update_metadata, 'TrackAnalyzer', return_value=analyzer),
            readable_sql(update_metadata),
            patch('builtins.print') as printed,
        ):
            update_metadata.update_metadata()

        output = ' '.join(str(call.args[0]) for call in printed.call_args_list if call.args)
        self.assertIn('fix_db_schema.py', output)

    def test_any_other_database_failure_is_reported(self):
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value.execute.side_effect = Exception('deadlock')
        analyzer = analyzer_returning(engine)

        with (
            patch.object(update_metadata, 'TrackAnalyzer', return_value=analyzer),
            readable_sql(update_metadata),
            patch('builtins.print') as printed,
        ):
            update_metadata.update_metadata()

        output = ' '.join(str(call.args[0]) for call in printed.call_args_list if call.args)
        self.assertIn('deadlock', output)

    def test_nothing_happens_without_a_database(self):
        analyzer = analyzer_returning(None)

        with patch.object(update_metadata, 'TrackAnalyzer', return_value=analyzer):
            update_metadata.update_metadata()

        analyzer.extract_metadata.assert_not_called()


if __name__ == '__main__':
    unittest.main()
