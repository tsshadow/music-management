"""What a dynamic playlist may store, and how the track query reads what is stored (issue #221)."""

import json
import unittest

from services.music_manager.dynamic_playlist_params import DEFAULT_SIZE, MAX_SIZE, read_params, validate_params


class ValidateParamsTest(unittest.TestCase):
    """validate_params refuses what the track query cannot run and passes everything else through."""

    def test_both_client_spellings_pass_unchanged(self):
        for params in (
            {'genres': ['Hardstyle'], 'rating_range': [0, 100], 'size': 500, 'sort_method': 'newest'},
            {'genre': ['Uptempo'], 'sortMethod': 'Random', 'ratingMin': 3, 'size': 100},
            {},
        ):
            text = json.dumps(params)
            self.assertEqual(validate_params(text), text)

    def test_an_empty_or_null_size_means_the_default(self):
        validate_params('{"size": ""}')
        validate_params('{"size": null}')

    def test_not_json_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'not valid JSON'):
            validate_params('size=500&genres=x')

    def test_json_that_is_not_an_object_is_refused(self):
        for text in ('[]', '"x"', '12', 'null'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'JSON object'):
                validate_params(text)

    def test_a_size_that_is_not_a_whole_number_is_refused(self):
        for size in ('lots', 2.5, True, [500]):
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, 'whole number'):
                validate_params(json.dumps({'size': size}))

    def test_a_size_outside_the_cap_is_refused(self):
        for size in (0, -1, MAX_SIZE + 1, 10**9):
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, f'from 1 to {MAX_SIZE}'):
                validate_params(json.dumps({'size': size}))

    def test_the_cap_itself_and_a_numeric_string_pass(self):
        validate_params(json.dumps({'size': MAX_SIZE}))
        validate_params(json.dumps({'size': '250'}))

    def test_misshapen_query_keys_are_refused(self):
        for params, message in (
            ({'genres': 'Hardstyle'}, 'genres'),
            ({'genres': [1]}, 'genres'),
            ({'rating_range': [0]}, 'rating_range'),
            ({'rating_range': ['a', 'b']}, 'rating_range'),
            ({'rules': {'column': 'genre'}}, 'rules'),
            ({'rules': ['genre']}, 'rules'),
        ):
            with self.subTest(params=params), self.assertRaisesRegex(ValueError, message):
                validate_params(json.dumps(params))


class ReadParamsTest(unittest.TestCase):
    """read_params never fails on a stored row; every bad value falls back to its default."""

    def test_a_good_definition_is_read_as_written(self):
        params = read_params(
            json.dumps(
                {
                    'genres': ['Hardcore'],
                    'rating_range': [40, 100],
                    'size': 50,
                    'sort_method': 'random',
                    'song_type': 'set',
                    'rules': [{'column': 'genre', 'value': 'Uptempo'}],
                }
            )
        )
        self.assertEqual(
            params,
            {
                'genres': ['Hardcore'],
                'rating_range': [40, 100],
                'size': 50,
                'sort_method': 'random',
                'song_type': 'set',
                'rules': [{'column': 'genre', 'value': 'Uptempo'}],
            },
        )

    def test_a_stored_size_above_the_cap_is_clamped(self):
        self.assertEqual(read_params('{"size": 1000000}')['size'], MAX_SIZE)

    def test_a_non_numeric_size_is_the_default(self):
        self.assertEqual(read_params('{"size": "lots"}')['size'], DEFAULT_SIZE)

    def test_a_json_value_that_is_not_an_object_gives_the_defaults(self):
        for text in ('[1, 2]', '"x"', None, ''):
            with self.subTest(text=text):
                self.assertEqual(read_params(text)['size'], DEFAULT_SIZE)
                self.assertEqual(read_params(text)['genres'], [])

    def test_the_old_key_value_form_is_still_read(self):
        self.assertEqual(read_params('size=25&sort_method=oldest')['size'], 25)
        self.assertEqual(read_params('size=25&sort_method=oldest')['sort_method'], 'oldest')

    def test_misshapen_lists_are_cleaned(self):
        params = read_params(json.dumps({'genres': ['A', 3], 'rules': ['x', {'column': 'genre'}], 'rating_range': 5}))
        self.assertEqual(params['genres'], ['A'])
        self.assertEqual(params['rules'], [{'column': 'genre'}])
        self.assertEqual(params['rating_range'], [0, 100])


if __name__ == '__main__':
    unittest.main()
