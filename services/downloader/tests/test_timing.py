import unittest

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader.timing import (
    SOURCES,
    TIMING_FIELDS,
    DownloaderTiming,
    field_map,
    load_timing,
    validate_settings,
)


class TimingFieldsTest(unittest.TestCase):

    def test_every_source_has_fields(self):
        for source in SOURCES:
            self.assertTrue(TIMING_FIELDS[source], f'no fields for {source}')

    def test_defaults_are_within_their_own_bounds(self):
        for source in SOURCES:
            for field in TIMING_FIELDS[source]:
                self.assertGreaterEqual(field.default, field.minimum, f'{source}.{field.key}')
                self.assertLessEqual(field.default, field.maximum, f'{source}.{field.key}')

    def test_soundcloud_sweeps_less_often_than_the_old_five_minute_loop(self):
        self.assertGreater(field_map('soundcloud')['sweep_interval'].default, 300)

    def test_telegram_has_max_concurrent_but_no_burst_size(self):
        keys = field_map('telegram')
        self.assertIn('max_concurrent', keys)
        self.assertNotIn('burst_size', keys)


class LoadTimingTest(unittest.TestCase):

    def test_uses_default_when_no_override_stored(self):
        timing = load_timing('soundcloud', overrides={})
        self.assertEqual(timing.sweep_interval, field_map('soundcloud')['sweep_interval'].default)

    def test_stored_override_replaces_default(self):
        timing = load_timing('soundcloud', overrides={'sweep_interval': 4200})
        self.assertEqual(timing.sweep_interval, 4200)

    def test_unknown_stored_key_is_ignored(self):
        timing = load_timing('soundcloud', overrides={'nonsense_knob': 5})
        self.assertNotIn('nonsense_knob', timing.values)

    def test_out_of_range_stored_value_falls_back_to_default(self):
        timing = load_timing('soundcloud', overrides={'max_workers': 9999})
        self.assertEqual(timing.max_workers, field_map('soundcloud')['max_workers'].default)


class MultiplierTest(unittest.TestCase):

    def test_multiplier_stretches_wait_times(self):
        timing = load_timing('soundcloud', overrides={'sweep_interval': 900}, multiplier=4)
        self.assertEqual(timing.sweep_interval, 3600)

    def test_multiplier_stretches_account_cooldown(self):
        timing = load_timing('soundcloud', overrides={'account_cooldown': 3600}, multiplier=2)
        self.assertEqual(timing.account_cooldown, 7200)

    def test_multiplier_leaves_counts_alone(self):
        timing = load_timing('soundcloud', overrides={'burst_size': 5}, multiplier=8)
        self.assertEqual(timing.burst_size, 5)

    def test_raw_returns_the_unscaled_value(self):
        timing = load_timing('soundcloud', overrides={'sweep_interval': 900}, multiplier=4)
        self.assertEqual(timing.raw('sweep_interval'), 900)


class YdlOptsTest(unittest.TestCase):

    def test_ratelimit_is_converted_from_kilobytes_to_bytes(self):
        timing = load_timing('soundcloud', overrides={'ratelimit_kbps': 512})
        self.assertEqual(timing.to_ydl_opts()['ratelimit'], 512 * 1024)

    def test_sleep_options_carry_the_multiplier(self):
        timing = load_timing('soundcloud', overrides={'sleep_interval': 15, 'max_sleep_interval': 90}, multiplier=2)
        opts = timing.to_ydl_opts()
        self.assertEqual(opts['sleep_interval'], 30)
        self.assertEqual(opts['max_sleep_interval'], 180)

    def test_sleep_requests_is_a_count_and_does_not_scale(self):
        timing = load_timing('soundcloud', overrides={'sleep_requests': 2}, multiplier=4)
        self.assertEqual(timing.to_ydl_opts()['sleep_requests'], 2)


class ValidateSettingsTest(unittest.TestCase):

    def test_accepts_a_value_inside_the_range(self):
        self.assertEqual(validate_settings('soundcloud', {'burst_size': 3}), {'burst_size': 3})

    def test_coerces_numeric_strings_from_the_api(self):
        self.assertEqual(validate_settings('soundcloud', {'burst_size': '3'}), {'burst_size': 3})

    def test_rejects_a_value_below_the_minimum(self):
        with self.assertRaises(ValueError):
            validate_settings('soundcloud', {'max_workers': 0})

    def test_rejects_a_value_above_the_maximum(self):
        with self.assertRaises(ValueError):
            validate_settings('soundcloud', {'burst_size': 10 ** 6})

    def test_rejects_an_unknown_key(self):
        with self.assertRaises(ValueError):
            validate_settings('soundcloud', {'nonsense_knob': 1})

    def test_rejects_a_key_that_belongs_to_another_source(self):
        with self.assertRaises(ValueError):
            validate_settings('telegram', {'burst_size': 5})

    def test_rejects_an_unknown_source(self):
        with self.assertRaises(ValueError):
            validate_settings('bandcamp', {'burst_size': 5})

    def test_rejects_a_non_numeric_value(self):
        with self.assertRaises(ValueError):
            validate_settings('soundcloud', {'burst_size': 'soon'})


class MinMaxPauseTest(unittest.TestCase):

    def test_max_pause_is_lifted_to_min_pause_when_stored_lower(self):
        timing = load_timing('soundcloud', overrides={'min_pause': 60, 'max_pause': 10})
        self.assertGreaterEqual(timing.max_pause, timing.min_pause)

    def test_max_sleep_interval_is_lifted_to_sleep_interval_when_stored_lower(self):
        timing = load_timing('soundcloud', overrides={'sleep_interval': 40, 'max_sleep_interval': 10})
        opts = timing.to_ydl_opts()
        self.assertGreaterEqual(opts['max_sleep_interval'], opts['sleep_interval'])


class TimingIsUsableWithoutADatabaseTest(unittest.TestCase):

    def test_constructing_directly_needs_no_store(self):
        timing = DownloaderTiming(source='youtube', values={'sweep_interval': 60})
        self.assertEqual(timing.sweep_interval, 60)


if __name__ == '__main__':
    unittest.main()
