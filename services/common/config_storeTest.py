import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

# services/tests/mock_base.py replaces services.common.config_store with a MagicMock
# for the whole test session, so a plain import would hand these tests a mock instead
# of the store. Load the real file under its own name; coverage still attributes the
# executed lines to services/common/config_store.py. The sys.modules entry has to be
# in place before the module body runs, because @dataclass looks its class up there.
_MODULE_NAME = 'services.common.config_store_under_test'
_spec = importlib.util.spec_from_file_location(_MODULE_NAME, Path(__file__).with_name('config_store.py'))
config_store = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = config_store
_spec.loader.exec_module(config_store)
ConfigField = config_store.ConfigField
ConfigStore = config_store.ConfigStore
credential = config_store.credential


class ConfigStoreTestCase(unittest.TestCase):
    """ConfigStore is a process-wide singleton: every test builds a fresh one
    against a throwaway config file and puts the shared instance back afterwards,
    so the store other modules already hold on to is left untouched."""

    env: dict[str, str] = {}

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.config_path = Path(self._tmp.name) / 'config.json'
        self.write_config_file()

        previous_instance = ConfigStore._instance
        previous_initialized = ConfigStore._initialized
        self.addCleanup(self._restore, previous_instance, previous_initialized)

        env = {'CONFIG_PATH': str(self.config_path), **self.env}
        with patch.dict('os.environ', env, clear=True):
            ConfigStore._instance = None
            ConfigStore._initialized = False
            self.store = ConfigStore()

    @staticmethod
    def _restore(instance, initialized):
        ConfigStore._instance = instance
        ConfigStore._initialized = initialized

    def write_config_file(self):
        """Override to seed the on-disk config before the store is built."""


class ConfigStoreDefaultsTest(ConfigStoreTestCase):
    def test_unset_keys_fall_back_to_their_declared_default(self):
        self.assertFalse(self.store.get('debug'))
        self.assertEqual(self.store.get('telegram_max_concurrent'), 4)
        self.assertEqual(self.store.get('db_connect_timeout'), 5)

    def test_attribute_access_mirrors_get(self):
        self.assertEqual(self.store.notify_topic, 'music-management')

    def test_an_unknown_key_reads_the_environment_instead(self):
        with patch.dict('os.environ', {'SOMETHING_ELSE': 'from-env'}):
            self.assertEqual(self.store.get('SOMETHING_ELSE'), 'from-env')
            self.assertEqual(self.store.SOMETHING_ELSE, 'from-env')

    def test_an_unknown_key_returns_the_supplied_default(self):
        self.assertEqual(self.store.get('SOMETHING_ELSE', 'fallback'), 'fallback')

    def test_private_attributes_are_not_resolved_as_config(self):
        self.assertRaises(AttributeError, getattr, self.store, '_missing_attribute')

    def test_describe_exposes_the_schema_with_current_values(self):
        entry = next(item for item in self.store.describe() if item['key'] == 'notify_topic')

        self.assertEqual(entry['type'], 'string')
        self.assertEqual(entry['group'], 'Notifications')
        self.assertEqual(entry['default'], 'music-management')
        self.assertEqual(entry['value'], 'music-management')

    def test_fields_is_an_alias_for_describe(self):
        self.assertEqual(self.store.fields(), self.store.describe())

    def test_groups_lists_every_configuration_group(self):
        self.assertIn('Database', self.store.groups())
        self.assertIn('SoundCloud', self.store.groups())

    def test_the_lms_fields_are_available(self):
        # LmsScanTrigger reads these two out of the store; without a declared field they
        # were unreachable from the config page and the trigger stayed silent.
        keys = {field['key'] for field in self.store.describe()}
        self.assertIn('lms_hosts', keys)
        self.assertIn('lms_subsonic_api_key', keys)
        self.assertIn('LMS', self.store.groups())

    def test_bpm_analysis_is_a_declared_setting_and_off_by_default(self):
        self.assertFalse(self.store.get('analyze_bpm'))
        self.assertIn('analyze_bpm', {field['key'] for field in self.store.describe()})

    def test_all_configs_returns_a_copy(self):
        snapshot = self.store.all_configs()
        snapshot['debug'] = 'tampered'

        self.assertFalse(self.store.get('debug'))

    def test_get_many_reads_several_keys_at_once(self):
        self.assertEqual(
            self.store.get_many(['debug', 'notify_topic']),
            {'debug': False, 'notify_topic': 'music-management'},
        )

    def test_config_path_is_exposed(self):
        self.assertEqual(self.store.config_path, self.config_path)

    def test_legacy_initialize_is_a_no_op(self):
        self.assertIsNone(self.store._initialize())

    def test_the_store_is_a_singleton(self):
        self.assertIs(ConfigStore(), self.store)


class ConfigStoreSecretTest(ConfigStoreTestCase):
    """Credentials must not leave the process just because someone opened a page.

    Every value used to come back verbatim from `describe` and `all_configs`, which
    is what `GET /api/config` returns. A field marked secret is reported as a fixed
    sentinel instead, and writing that sentinel back is a no-op -- without which,
    loading the config page and pressing save would overwrite every secret with the
    mask.
    """

    def write_config_file(self):
        self.config_path.write_text(json.dumps({'db_pass': 'hunter2', 'db_user': 'muma'}))

    def test_the_stored_secret_is_still_readable_inside_the_process(self):
        # The database connector reads this; only the API boundary masks it.
        self.assertEqual(self.store.get('db_pass'), 'hunter2')

    def test_describe_reports_a_secret_as_the_sentinel(self):
        entry = next(row for row in self.store.describe() if row['key'] == 'db_pass')
        self.assertEqual(entry['value'], config_store.SECRET_SENTINEL)
        self.assertTrue(entry['secret'])

    def test_describe_leaves_an_ordinary_field_alone(self):
        entry = next(row for row in self.store.describe() if row['key'] == 'db_user')
        self.assertEqual(entry['value'], 'muma')
        self.assertFalse(entry['secret'])

    def test_all_configs_masks_secrets_too(self):
        # This is the dict GET /api/config hands out.
        self.assertEqual(self.store.all_configs()['db_pass'], config_store.SECRET_SENTINEL)
        self.assertEqual(self.store.all_configs()['db_user'], 'muma')

    def test_an_unset_secret_reads_as_empty_rather_than_masked(self):
        # Masking an empty value would claim a credential exists where none does.
        entry = next(row for row in self.store.describe() if row['key'] == 'discogs_token')
        self.assertEqual(entry['value'], '')

    def test_writing_the_sentinel_back_leaves_the_secret_untouched(self):
        self.store.update({'db_pass': config_store.SECRET_SENTINEL})
        self.assertEqual(self.store.get('db_pass'), 'hunter2')

    def test_a_real_new_value_does_replace_the_secret(self):
        self.store.update({'db_pass': 'correct horse'})
        self.assertEqual(self.store.get('db_pass'), 'correct horse')

    def test_a_secret_can_be_cleared_with_an_empty_string(self):
        self.store.update({'db_pass': ''})
        self.assertEqual(self.store.get('db_pass'), '')

    def test_saving_a_whole_page_back_does_not_wipe_the_secrets(self):
        # Exactly what the config page does: read everything, change one field, post
        # it all back. Every secret in that payload is the sentinel.
        payload = self.store.all_configs()
        payload['db_user'] = 'other'
        self.store.update(payload)
        self.assertEqual(self.store.get('db_pass'), 'hunter2')
        self.assertEqual(self.store.get('db_user'), 'other')

    def test_the_sentinel_is_never_written_to_disk(self):
        self.store.update({'db_pass': config_store.SECRET_SENTINEL, 'db_user': 'other'})
        on_disk = json.loads(self.config_path.read_text())
        self.assertNotEqual(on_disk.get('db_pass'), config_store.SECRET_SENTINEL)


class ConfigStoreRetagLimitTest(ConfigStoreTestCase):
    """The retag ceiling the curation pages enforce is a configured value."""

    def test_max_retag_files_is_a_tagger_field_defaulting_to_the_old_constant(self):
        entry = next(row for row in self.store.describe() if row['key'] == 'max_retag_files')
        self.assertEqual(entry['default'], 2000)
        self.assertEqual(entry['group'], 'Tagger')
        self.assertEqual(entry['type'], 'integer')


class ConfigStoreEnvironmentTest(ConfigStoreTestCase):
    env = {
        'debug': 'true',
        'DB_PORT': '3307',
        'notify_topic': 'from-env',
        'telegram_max_concurrent': 'not-a-number',
    }

    def test_environment_values_are_coerced_to_the_field_type(self):
        self.assertIs(self.store.get('debug'), True)
        self.assertEqual(self.store.get('db_port'), 3307)
        self.assertEqual(self.store.get('notify_topic'), 'from-env')

    def test_an_unparsable_environment_value_leaves_the_default_in_place(self):
        self.assertEqual(self.store.get('telegram_max_concurrent'), 4)


class ConfigStoreUppercaseEnvironmentTest(ConfigStoreTestCase):
    env = {'DEBUG': 'yes'}

    def test_a_lowercase_env_name_also_matches_its_uppercase_form(self):
        self.assertIs(self.store.get('debug'), True)


class ConfigStoreDiskTest(ConfigStoreTestCase):
    def write_config_file(self):
        self.config_path.write_text(
            json.dumps({'notify_topic': 'from-disk', 'db_port': '3308', 'unknown_key': 'ignored', 'debug': 'nonsense'}),
            encoding='utf-8',
        )

    def test_values_are_read_back_from_disk(self):
        self.assertEqual(self.store.get('notify_topic'), 'from-disk')
        self.assertEqual(self.store.get('db_port'), 3308)

    def test_unknown_and_unparsable_entries_are_skipped(self):
        self.assertNotIn('unknown_key', self.store.all_configs())
        self.assertFalse(self.store.get('debug'))


class ConfigStoreBrokenDiskTest(ConfigStoreTestCase):
    def write_config_file(self):
        self.config_path.write_text('{ this is not json', encoding='utf-8')

    def test_a_corrupt_config_file_falls_back_to_the_defaults(self):
        self.assertEqual(self.store.get('notify_topic'), 'music-management')


class ConfigStoreNonMappingDiskTest(ConfigStoreTestCase):
    def write_config_file(self):
        self.config_path.write_text('["not", "a", "mapping"]', encoding='utf-8')

    def test_a_non_mapping_config_file_falls_back_to_the_defaults(self):
        self.assertEqual(self.store.get('notify_topic'), 'music-management')


class ConfigStoreUpdateTest(ConfigStoreTestCase):
    def test_update_stores_and_persists_the_new_values(self):
        result = self.store.update({'notify_topic': 'muma', 'debug': 'on'})

        self.assertEqual(result, {'notify_topic': 'muma', 'debug': True})
        self.assertEqual(json.loads(self.config_path.read_text(encoding='utf-8'))['notify_topic'], 'muma')

    def test_an_empty_update_touches_nothing(self):
        self.assertEqual(self.store.update({}), {})
        self.assertFalse(self.config_path.exists())

    def test_writing_an_unchanged_value_does_not_persist(self):
        self.store.update({'notify_topic': 'music-management'})

        self.assertFalse(self.config_path.exists())

    def test_an_unknown_key_is_rejected(self):
        with self.assertRaises(KeyError):
            self.store.update({'nope': 1})

    def test_listeners_are_notified_of_a_change(self):
        seen = []
        self.store.subscribe('notify_topic', seen.append)

        self.store.update({'notify_topic': 'muma'})

        self.assertEqual(seen, ['muma'])

    def test_listeners_are_not_notified_when_nothing_changed(self):
        seen = []
        self.store.subscribe('notify_topic', seen.append)

        self.store.update({'notify_topic': 'music-management'})

        self.assertEqual(seen, [])

    def test_a_failing_listener_does_not_stop_the_others(self):
        seen = []

        def boom(_value):
            raise RuntimeError('listener exploded')

        self.store.subscribe('notify_topic', boom)
        self.store.subscribe('notify_topic', seen.append)

        self.store.update({'notify_topic': 'muma'})

        self.assertEqual(seen, ['muma'])

    def test_subscribe_immediate_delivers_the_current_value(self):
        seen = []

        self.store.subscribe('notify_topic', seen.append, immediate=True)

        self.assertEqual(seen, ['music-management'])

    def test_unsubscribing_stops_further_notifications(self):
        seen = []
        unsubscribe = self.store.subscribe('notify_topic', seen.append)

        unsubscribe()
        self.store.update({'notify_topic': 'muma'})

        self.assertEqual(seen, [])

    def test_unsubscribing_twice_is_harmless(self):
        unsubscribe = self.store.subscribe('notify_topic', lambda _value: None)

        unsubscribe()
        unsubscribe()

    def test_subscribing_to_an_unknown_key_is_rejected(self):
        with self.assertRaises(KeyError):
            self.store.subscribe('nope', lambda _value: None)


class ConfigStoreCoercionTest(ConfigStoreTestCase):
    def coerce(self, value, type_='string', nullable=True):
        return self.store._coerce(ConfigField(key='sample', type=type_, nullable=nullable), value)

    def test_none_is_allowed_for_a_nullable_field(self):
        self.assertIsNone(self.coerce(None))

    def test_none_is_rejected_for_a_non_nullable_field(self):
        with self.assertRaises(ValueError):
            self.coerce(None, nullable=False)

    def test_an_unsupported_field_type_is_rejected(self):
        with self.assertRaises(ValueError):
            self.coerce('x', type_='colour')

    def test_boolean_accepts_the_usual_spellings(self):
        for value in (True, '1', 'true', 'YES', ' on '):
            self.assertIs(self.coerce(value, 'boolean'), True, value)
        for value in (False, '0', 'false', 'No', 'off'):
            self.assertIs(self.coerce(value, 'boolean'), False, value)

    def test_boolean_accepts_numbers(self):
        self.assertIs(self.coerce(1, 'boolean'), True)
        self.assertIs(self.coerce(0.0, 'boolean'), False)

    def test_boolean_rejects_nonsense(self):
        with self.assertRaises(ValueError):
            self.coerce('maybe', 'boolean')
        with self.assertRaises(ValueError):
            self.coerce([], 'boolean')

    def test_integer_accepts_integers_and_numeric_strings(self):
        self.assertEqual(self.coerce(7, 'integer'), 7)
        self.assertEqual(self.coerce(' 7 ', 'integer'), 7)
        self.assertEqual(self.coerce(7.0, 'integer'), 7)

    def test_an_empty_integer_string_clears_a_nullable_field(self):
        self.assertIsNone(self.coerce('', 'integer'))

    def test_an_empty_integer_string_becomes_zero_when_not_nullable(self):
        self.assertEqual(self.coerce('', 'integer', nullable=False), 0)

    def test_integer_rejects_booleans_fractions_and_nonsense(self):
        with self.assertRaises(ValueError):
            self.coerce(True, 'integer')
        with self.assertRaises(ValueError):
            self.coerce(7.5, 'integer')
        with self.assertRaises(ValueError):
            self.coerce('seven', 'integer')
        with self.assertRaises(ValueError):
            self.coerce([], 'integer')

    def test_string_accepts_scalars(self):
        self.assertEqual(self.coerce('text'), 'text')
        self.assertEqual(self.coerce(7), '7')
        self.assertEqual(self.coerce(True), 'True')

    def test_string_rejects_containers(self):
        with self.assertRaises(ValueError):
            self.coerce(['text'])


if __name__ == '__main__':
    unittest.main()


class CredentialTest(ConfigStoreTestCase):
    """`credential()` is what every Spotify/Last.fm/Discogs consumer reads: the config page's
    value first, the environment second, None when neither has it."""

    def test_a_value_stored_through_the_config_page_wins(self):
        self.store.update({'spotify_client_id': 'from-page'})
        with patch.dict('os.environ', {'SPOTIFY_CLIENT_ID': 'from-env'}):
            self.assertEqual(credential('spotify_client_id', 'SPOTIFY_CLIENT_ID'), 'from-page')

    def test_the_environment_is_read_when_the_store_has_nothing(self):
        with patch.dict('os.environ', {'SPOTIFY_CLIENT_ID': 'from-env'}):
            self.assertEqual(credential('spotify_client_id', 'SPOTIFY_CLIENT_ID'), 'from-env')

    def test_nothing_anywhere_is_none_not_an_empty_string(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertIsNone(credential('spotify_client_id', 'SPOTIFY_CLIENT_ID'))
