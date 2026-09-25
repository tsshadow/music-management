"""Covers services/ml-analyzer/approve.py: the interactive tool that marks tracks
as usable training data.

See services/tests/MlAnalyzerTest.py for why the module is loaded by file and why
its third-party dependencies are stubbed.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('librosa', 'sqlalchemy', 'pandas', 'tqdm', 'dotenv')


from services.tests.MlAnalyzerTest import load_module

approve = load_module('approve')


def readable_sql():
    return patch.object(approve, 'text', side_effect=lambda statement: statement)


def track_row(
    track_id=1,
    artist='Angerfist',
    label='Roughstate',
    genre_tag='Hardcore',
    ml_genre='Uptempo',
    review_status='unreviewed',
    approved=0,
):
    """One row in the exact column order approve_tracks() selects."""
    row = [
        track_id,
        '/music/a.mp3',
        artist,
        label,
        genre_tag,
        ml_genre,
        174.0,
        0.5,
        0.1,
        2024,
        2000.0,
        100.0,
        1500.0,
        90.0,
        4000.0,
        200.0,
        20.0,
        3.0,
    ]
    row.extend(float(i) for i in range(1, 14))  # mfcc_1..13
    row.extend(float(i) for i in range(14, 27))  # std_mfcc_1..13
    row.extend([0.05, 0.01, 0.4, 0.02, 'Soundcloud', 300.0, review_status, approved])
    return row


class DatabaseUrlTest(unittest.TestCase):
    def url_for(self, env):
        with patch.dict(os.environ, env, clear=True):
            return approve._get_db_url()

    def test_an_explicit_database_url_is_used_as_is(self):
        self.assertEqual(self.url_for({'DATABASE_URL': 'mysql://elsewhere'}), 'mysql://elsewhere')

    def test_the_url_is_built_from_the_separate_settings(self):
        url = self.url_for(
            {'DB_HOST': 'db.example', 'DB_PORT': '3307', 'DB_USER': 'muma', 'DB_PASS': 'secret', 'DB_DB': 'music'}
        )

        self.assertEqual(url, 'mysql+mysqlconnector://muma:secret@db.example:3307/music')

    def test_a_host_with_a_port_in_it_is_split(self):
        url = self.url_for({'DB_HOST': 'db.example:3999', 'DB_PASS': 'secret'})

        self.assertIn('@db.example:3999/', url)

    def test_without_a_password_there_is_no_url(self):
        self.assertIsNone(self.url_for({'DB_HOST': 'db.example'}))


class GetPredictionTest(unittest.TestCase):
    def test_without_a_model_there_is_no_prediction(self):
        self.assertEqual(approve.get_prediction(None, {}, MagicMock(), {}), (None, 0))

    def test_without_encoders_there_is_no_prediction(self):
        self.assertEqual(approve.get_prediction(MagicMock(), None, MagicMock(), {}), (None, 0))

    def test_without_a_scaler_there_is_no_prediction(self):
        self.assertEqual(approve.get_prediction(MagicMock(), {}, None, {}), (None, 0))

    def test_a_failing_model_yields_no_prediction_rather_than_raising(self):
        model = MagicMock()
        model.predict.side_effect = Exception('shape mismatch')

        self.assertEqual(approve.get_prediction(model, {'artist_name': MagicMock()}, MagicMock(), {}), (None, 0))


class ProcessSingleTrackTest(unittest.TestCase):
    def process(self, answers, row=None, prediction=('Uptempo', 0.9)):
        connection = MagicMock()
        with (
            patch.object(approve, 'get_prediction', return_value=prediction),
            patch('builtins.input', side_effect=answers),
            patch('builtins.print'),
            readable_sql(),
        ):
            choice = approve._process_single_track(connection, row or track_row(), (MagicMock(),) * 3)
        return choice, connection

    def statements(self, connection):
        return [call.args[0] for call in connection.execute.call_args_list]

    def test_approving_marks_the_track_as_human_verified(self):
        choice, connection = self.process(['y'])

        self.assertEqual(choice, 'y')
        self.assertIn('approved_for_training = 1', self.statements(connection)[0])
        self.assertIn("ml_review_status = 'human_verified'", self.statements(connection)[0])
        connection.commit.assert_called_once()

    def test_rejecting_with_a_correction_stores_the_new_genre(self):
        choice, connection = self.process(['n', 'Frenchcore'])

        self.assertEqual(choice, 'n')
        statement, params = connection.execute.call_args[0]
        self.assertIn('SET ml_genre = :genre', statement)
        self.assertEqual(params['genre'], 'Frenchcore')

    def test_rejecting_without_a_correction_marks_it_do_not_train(self):
        _choice, connection = self.process(['n', ''])

        self.assertIn("ml_review_status = 'do_not_train'", self.statements(connection)[0])
        self.assertIn('approved_for_training = 0', self.statements(connection)[0])

    def test_skipping_writes_nothing(self):
        choice, connection = self.process(['s'])

        self.assertEqual(choice, 's')
        connection.execute.assert_not_called()

    def test_quitting_writes_nothing(self):
        choice, connection = self.process(['q'])

        self.assertEqual(choice, 'q')
        connection.execute.assert_not_called()

    def test_a_track_without_a_prediction_is_still_offered(self):
        choice, _connection = self.process(['s'], prediction=(None, 0))

        self.assertEqual(choice, 's')


class ApproveTracksTest(unittest.TestCase):
    def run_approve(self, tracks, argv=None, choices=None, models_exist=False, failure=None):
        connection = MagicMock()
        if failure is not None:
            connection.execute.side_effect = failure
        else:
            connection.execute.return_value.fetchall.return_value = tracks
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection

        arguments = ['approve.py', *(argv or [])]
        with (
            patch.object(approve, 'create_engine', return_value=engine),
            patch.object(approve.os.path, 'exists', return_value=models_exist),
            patch.object(approve, 'joblib') as joblib,
            patch.object(approve, '_process_single_track', side_effect=choices or []) as process,
            patch.dict(os.environ, {'DB_HOST': 'db', 'DB_PASS': 'secret'}, clear=True),
            patch('sys.argv', arguments),
            patch('builtins.print') as printed,
            readable_sql(),
        ):
            approve.approve_tracks()
        return connection, process, joblib, printed

    def test_every_pending_track_is_offered_for_review(self):
        _connection, process, _joblib, _printed = self.run_approve([track_row(1), track_row(2)], choices=['y', 'y'])

        self.assertEqual(process.call_count, 2)

    def test_quitting_stops_the_run(self):
        _connection, process, _joblib, _printed = self.run_approve([track_row(1), track_row(2)], choices=['q', 'y'])

        self.assertEqual(process.call_count, 1)

    def test_by_default_only_unreviewed_tracks_are_selected(self):
        connection, _process, _joblib, _printed = self.run_approve([], choices=[])

        statement = connection.execute.call_args[0][0]
        self.assertIn("WHERE l.approved_for_training = 0 AND l.ml_review_status = 'unreviewed'", statement)

    def test_redo_offers_every_track_again(self):
        connection, _process, _joblib, _printed = self.run_approve([], argv=['--redo'], choices=[])

        self.assertNotIn('WHERE l.approved_for_training', connection.execute.call_args[0][0])

    def test_the_limit_is_passed_to_the_query(self):
        connection, _process, _joblib, _printed = self.run_approve([], argv=['--limit', '5'], choices=[])

        self.assertEqual(connection.execute.call_args[0][1], {'limit': 5})

    def test_a_saved_model_is_loaded_for_the_previews(self):
        _connection, _process, joblib, _printed = self.run_approve([], choices=[], models_exist=True)

        self.assertEqual(joblib.load.call_count, 3)

    def test_an_unloadable_model_does_not_stop_the_review(self):
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = []
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection

        with (
            patch.object(approve, 'create_engine', return_value=engine),
            patch.object(approve.os.path, 'exists', return_value=True),
            patch.object(approve, 'joblib') as joblib,
            patch.dict(os.environ, {'DB_HOST': 'db', 'DB_PASS': 'secret'}, clear=True),
            patch('sys.argv', ['approve.py']),
            patch('builtins.print'),
            readable_sql(),
        ):
            joblib.load.side_effect = Exception('corrupt model')
            approve.approve_tracks()

    def test_without_a_database_configuration_nothing_runs(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(approve, 'create_engine') as create_engine,
            patch('sys.argv', ['approve.py']),
            patch('builtins.print'),
        ):
            approve.approve_tracks()

        create_engine.assert_not_called()

    def test_a_database_failure_is_reported_rather_than_raised(self):
        _connection, _process, _joblib, printed = self.run_approve([], choices=[], failure=Exception('deadlock'))

        output = ' '.join(str(call.args[0]) for call in printed.call_args_list if call.args)
        self.assertIn('deadlock', output)


if __name__ == '__main__':
    unittest.main()
