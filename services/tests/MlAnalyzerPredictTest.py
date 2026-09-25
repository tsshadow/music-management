"""Covers services/ml-analyzer/predict.py.

Only the parts that are the predictor's own logic: loading (or failing to load) a
model, the guards before a prediction is attempted, and the write-back of a
result. The feature assembly in between is pandas and scikit-learn calls, and
those libraries are stubbed here (see services/tests/MlAnalyzerTest.py), so
asserting on it would prove nothing.
"""

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('librosa', 'sqlalchemy', 'pandas', 'tqdm', 'dotenv')


from services.tests.MlAnalyzerTest import load_module

predict = load_module('predict')


def readable_sql():
    return patch.object(predict, 'text', side_effect=lambda statement: statement)


def predictor_with(model=None, encoders=None, engine=None):
    """A GenrePredictor whose __init__ is bypassed, so nothing is loaded from disk."""
    instance = predict.GenrePredictor.__new__(predict.GenrePredictor)
    instance.analyzer = MagicMock()
    instance.analyzer.engine = engine
    instance.model_path = 'models/genre_classifier.joblib'
    instance.encoder_path = 'models/label_encoders.joblib'
    instance.model = model
    instance.encoders = encoders
    return instance


class LoadingTest(unittest.TestCase):
    def build(self, model_exists):
        with (
            patch.object(predict, 'TrackAnalyzer'),
            patch.object(predict.os.path, 'exists', return_value=model_exists),
            patch.object(predict, 'joblib') as joblib,
            patch('builtins.print'),
        ):
            instance = predict.GenrePredictor()
        return instance, joblib

    def test_a_saved_model_is_loaded_with_its_encoders(self):
        instance, joblib = self.build(model_exists=True)

        self.assertEqual(joblib.load.call_count, 2)
        self.assertIsNotNone(instance.model)

    def test_without_a_saved_model_nothing_is_loaded(self):
        instance, joblib = self.build(model_exists=False)

        joblib.load.assert_not_called()
        self.assertIsNone(instance.model)


class PredictTest(unittest.TestCase):
    def test_without_a_model_there_is_no_prediction(self):
        self.assertIsNone(predictor_with().predict('/music/a.mp3'))

    def test_a_track_that_cannot_be_analyzed_yields_no_prediction(self):
        instance = predictor_with(model=MagicMock(), encoders={})
        instance.analyzer.analyze_track.return_value = None

        with patch('builtins.print'):
            self.assertIsNone(instance.predict('/music/a.mp3'))

    def test_the_track_is_analyzed_without_being_saved(self):
        instance = predictor_with(model=MagicMock(), encoders={})
        instance.analyzer.analyze_track.return_value = None

        with patch('builtins.print'):
            instance.predict('/music/a.mp3')

        instance.analyzer.analyze_track.assert_called_once_with('/music/a.mp3', save=False)


class SavePredictionTest(unittest.TestCase):
    def save(self, engine, track_info=('hash-1', 42), failure=None):
        instance = predictor_with(engine=engine)
        instance.analyzer.get_track_info.return_value = track_info
        connection = MagicMock()
        if failure is not None:
            connection.execute.side_effect = failure
        if engine is not None:
            engine.begin.return_value.__enter__.return_value = connection

        with patch('builtins.print') as printed, readable_sql():
            instance.save_prediction('/music/a.mp3', 'Hardcore', 0.9)
        return connection, printed

    def test_a_prediction_is_upserted_for_the_internal_track_id(self):
        connection, _printed = self.save(MagicMock())

        statement, params = connection.execute.call_args[0]
        self.assertIn('INSERT INTO library_track_ml_predictions', statement)
        self.assertIn('ON DUPLICATE KEY UPDATE', statement)
        self.assertEqual(params, {'tid': '42', 'ver': 'v1.0-rf', 'genre': 'Hardcore', 'conf': 0.9})

    def test_without_an_internal_id_the_path_hash_identifies_the_track(self):
        connection, _printed = self.save(MagicMock(), track_info=('hash-1', None))

        self.assertEqual(connection.execute.call_args[0][1]['tid'], 'hash-1')

    def test_nothing_is_written_without_a_database(self):
        connection, _printed = self.save(None)

        connection.execute.assert_not_called()

    def test_a_failing_write_is_reported_rather_than_raised(self):
        _connection, printed = self.save(MagicMock(), failure=Exception('deadlock'))

        output = ' '.join(str(call.args[0]) for call in printed.call_args_list if call.args)
        self.assertIn('deadlock', output)


if __name__ == '__main__':
    unittest.main()
