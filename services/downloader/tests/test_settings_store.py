import unittest

from services.downloader.settings_store import (
    InMemorySettingsStore,
    load_settings,
    rows_to_settings,
    save_settings,
)


class RowParsingTest(unittest.TestCase):
    def test_rows_become_a_mapping(self):
        self.assertEqual(
            rows_to_settings([('burst_size', '5'), ('max_workers', '1')]), {'burst_size': '5', 'max_workers': '1'}
        )

    def test_no_rows_means_no_overrides(self):
        self.assertEqual(rows_to_settings([]), {})


class LoadAndSaveTest(unittest.TestCase):
    def setUp(self):
        self.store = InMemorySettingsStore()

    def test_nothing_stored_means_no_overrides(self):
        self.assertEqual(load_settings('soundcloud', store=self.store), {})

    def test_a_saved_value_comes_back(self):
        save_settings('soundcloud', {'burst_size': 3}, store=self.store)
        self.assertEqual(load_settings('soundcloud', store=self.store), {'burst_size': 3})

    def test_saving_again_replaces_the_value(self):
        save_settings('soundcloud', {'burst_size': 3}, store=self.store)
        save_settings('soundcloud', {'burst_size': 7}, store=self.store)
        self.assertEqual(load_settings('soundcloud', store=self.store), {'burst_size': 7})

    def test_saving_one_knob_leaves_the_others_alone(self):
        save_settings('soundcloud', {'burst_size': 3}, store=self.store)
        save_settings('soundcloud', {'max_workers': 2}, store=self.store)
        self.assertEqual(load_settings('soundcloud', store=self.store), {'burst_size': 3, 'max_workers': 2})

    def test_sources_keep_their_own_settings(self):
        save_settings('soundcloud', {'burst_size': 3}, store=self.store)
        self.assertEqual(load_settings('youtube', store=self.store), {})

    def test_an_invalid_value_is_refused_before_it_reaches_storage(self):
        with self.assertRaises(ValueError):
            save_settings('soundcloud', {'max_workers': 0}, store=self.store)
        self.assertEqual(load_settings('soundcloud', store=self.store), {})

    def test_an_unknown_knob_is_refused(self):
        with self.assertRaises(ValueError):
            save_settings('soundcloud', {'nonsense_knob': 1}, store=self.store)


class StorageFailureTest(unittest.TestCase):
    class BrokenStore:
        def load(self, source):
            raise RuntimeError('database is down')

        def save(self, source, values):
            raise RuntimeError('database is down')

    def test_a_broken_store_reads_as_no_overrides(self):
        self.assertEqual(load_settings('soundcloud', store=self.BrokenStore()), {})

    def test_a_broken_store_surfaces_the_error_on_save(self):
        with self.assertRaises(RuntimeError):
            save_settings('soundcloud', {'burst_size': 3}, store=self.BrokenStore())


if __name__ == '__main__':
    unittest.main()
