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
assert _spec is not None and _spec.loader is not None
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
        self.config_path.write_text(json.dumps({'lastfm_api_key': 'hunter2', 'spotify_client_id': 'client-id'}))

    def test_the_stored_secret_is_still_readable_inside_the_process(self):
        # The Last.fm provider reads this; only the API boundary masks it.
        self.assertEqual(self.store.get('lastfm_api_key'), 'hunter2')

    def test_describe_reports_a_secret_as_the_sentinel(self):
        entry = next(row for row in self.store.describe() if row['key'] == 'lastfm_api_key')
        self.assertEqual(entry['value'], config_store.SECRET_SENTINEL)
        self.assertTrue(entry['secret'])

    def test_describe_leaves_an_ordinary_field_alone(self):
        entry = next(row for row in self.store.describe() if row['key'] == 'spotify_client_id')
        self.assertEqual(entry['value'], 'client-id')
        self.assertFalse(entry['secret'])

    def test_all_configs_masks_secrets_too(self):
        # This is the dict GET /api/config hands out.
        self.assertEqual(self.store.all_configs()['lastfm_api_key'], config_store.SECRET_SENTINEL)
        self.assertEqual(self.store.all_configs()['spotify_client_id'], 'client-id')

    def test_an_unset_secret_reads_as_empty_rather_than_masked(self):
        # Masking an empty value would claim a credential exists where none does.
        entry = next(row for row in self.store.describe() if row['key'] == 'discogs_token')
        self.assertEqual(entry['value'], '')

    def test_writing_the_sentinel_back_leaves_the_secret_untouched(self):
        self.store.update({'lastfm_api_key': config_store.SECRET_SENTINEL})
        self.assertEqual(self.store.get('lastfm_api_key'), 'hunter2')

    def test_a_real_new_value_does_replace_the_secret(self):
        self.store.update({'lastfm_api_key': 'correct horse'})
        self.assertEqual(self.store.get('lastfm_api_key'), 'correct horse')

    def test_a_secret_can_be_cleared_with_an_empty_string(self):
        self.store.update({'lastfm_api_key': ''})
        self.assertEqual(self.store.get('lastfm_api_key'), '')

    def test_saving_a_whole_page_back_does_not_wipe_the_secrets(self):
        # Exactly what the config page does: read everything, change one field, post
        # it all back. Every secret in that payload is the sentinel.
        payload = self.store.all_configs()
        payload['spotify_client_id'] = 'other'
        self.store.update(payload)
        self.assertEqual(self.store.get('lastfm_api_key'), 'hunter2')
        self.assertEqual(self.store.get('spotify_client_id'), 'other')

    def test_the_sentinel_is_never_written_to_disk(self):
        self.store.update({'lastfm_api_key': config_store.SECRET_SENTINEL, 'spotify_client_id': 'other'})
        on_disk = json.loads(self.config_path.read_text())
        self.assertNotEqual(on_disk.get('lastfm_api_key'), config_store.SECRET_SENTINEL)


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


class ConfigStoreProjectUrlTest(ConfigStoreTestCase):
    def test_project_url_is_empty_by_default_and_belongs_to_about(self):
        self.assertEqual(self.store.get('project_url'), '')
        entry = next(item for item in self.store.describe() if item['key'] == 'project_url')
        self.assertEqual(entry['group'], 'About')


class ConfigStoreProjectUrlEnvironmentTest(ConfigStoreTestCase):
    env = {'PROJECT_URL': 'https://example.org/muma'}

    def test_project_url_comes_from_the_environment(self):
        self.assertEqual(self.store.get('project_url'), 'https://example.org/muma')


class ConfigStoreUppercaseEnvironmentTest(ConfigStoreTestCase):
    env = {'DEBUG': 'yes'}

    def test_a_lowercase_env_name_also_matches_its_uppercase_form(self):
        self.assertIs(self.store.get('debug'), True)


class ConfigStoreDiskTest(ConfigStoreTestCase):
    def write_config_file(self):
        self.config_path.write_text(
            json.dumps(
                {
                    'notify_topic': 'from-disk',
                    'telegram_max_concurrent': '8',
                    'unknown_key': 'ignored',
                    'debug': 'nonsense',
                }
            ),
            encoding='utf-8',
        )

    def test_values_are_read_back_from_disk(self):
        self.assertEqual(self.store.get('notify_topic'), 'from-disk')
        self.assertEqual(self.store.get('telegram_max_concurrent'), 8)

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


def on_disk(path):
    """The persisted config.json as a dict."""
    return json.loads(path.read_text(encoding='utf-8'))


class ConfigStoreOverridesOnlyTest(ConfigStoreTestCase):
    """Only what the API changed is written; the environment is never copied to disk."""

    env = {'notify_topic': 'from-env', 'LASTFM_API_KEY': 'env-secret', 'DB_PASS': 'db-secret'}

    def test_a_save_writes_the_changed_key_and_nothing_from_the_environment(self):
        self.store.update({'debug': True})
        data = on_disk(self.config_path)
        self.assertEqual(data['debug'], True)
        self.assertNotIn('notify_topic', data)
        self.assertNotIn('lastfm_api_key', data)
        self.assertNotIn('db_pass', data)
        self.assertNotIn('env-secret', self.config_path.read_text(encoding='utf-8'))

    def test_a_value_equal_to_its_environment_value_is_not_written(self):
        self.store.update({'debug': True})
        self.store.update({'notify_topic': 'from-env'})
        self.assertNotIn('notify_topic', on_disk(self.config_path))

    def test_setting_a_key_back_to_its_environment_value_removes_the_override(self):
        self.store.update({'notify_topic': 'from-page'})
        self.assertEqual(on_disk(self.config_path)['notify_topic'], 'from-page')
        self.store.update({'notify_topic': 'from-env'})
        self.assertNotIn('notify_topic', on_disk(self.config_path))
        self.assertFalse(self.store.is_overridden('notify_topic'))

    def test_an_override_wins_over_the_environment(self):
        self.store.update({'notify_topic': 'from-page'})
        self.assertEqual(self.store.get('notify_topic'), 'from-page')
        self.assertTrue(self.store.is_overridden('notify_topic'))

    def test_a_secret_typed_on_the_page_is_persisted(self):
        # The way to hand the fetcher a Spotify secret the environment lacks (bug 034).
        self.store.update({'spotify_client_secret': 'typed'})
        self.assertEqual(on_disk(self.config_path)['spotify_client_secret'], 'typed')

    def test_the_file_is_readable_by_its_owner_only(self):
        self.store.update({'debug': True})
        self.assertEqual(self.config_path.stat().st_mode & 0o777, 0o600)

    def test_the_file_carries_the_format_marker(self):
        self.store.update({'debug': True})
        self.assertEqual(on_disk(self.config_path)[config_store.FILE_FORMAT_KEY], config_store.FILE_FORMAT)

    def test_update_returns_masked_values_not_the_secret(self):
        result = self.store.update({'lastfm_api_key': 'brand-new', 'notify_topic': 'x'})
        self.assertEqual(result, {'lastfm_api_key': config_store.SECRET_SENTINEL, 'notify_topic': 'x'})
        self.assertEqual(self.store.get('lastfm_api_key'), 'brand-new')


class ConfigStoreReadOnlyTest(ConfigStoreTestCase):
    """The db_* fields are read by nobody through the store; the page may only show them."""

    env = {'DB_HOST': 'mariadb', 'DB_PASS': 'db-secret'}

    def test_database_fields_are_marked_read_only_and_show_the_environment(self):
        fields = {row['key']: row for row in self.store.describe()}
        for key in ('db_host', 'db_port', 'db_user', 'db_pass', 'db_name', 'db_connect_timeout'):
            self.assertTrue(fields[key]['read_only'], key)
        self.assertEqual(fields['db_host']['value'], 'mariadb')
        self.assertEqual(fields['db_pass']['value'], config_store.SECRET_SENTINEL)
        self.assertFalse(fields['notify_topic']['read_only'])

    def test_changing_a_read_only_field_is_refused_and_nothing_is_applied(self):
        with self.assertRaises(ValueError):
            self.store.update({'notify_topic': 'x', 'db_host': 'elsewhere'})
        self.assertEqual(self.store.get('db_host'), 'mariadb')
        self.assertEqual(self.store.get('notify_topic'), 'music-management')
        self.assertFalse(self.config_path.exists())

    def test_posting_the_page_back_with_read_only_fields_unchanged_is_fine(self):
        page = self.store.all_configs()
        page['notify_topic'] = 'x'
        self.store.update(page)
        self.assertEqual(self.store.get('notify_topic'), 'x')
        self.assertNotIn('db_host', on_disk(self.config_path))


class ConfigStoreLegacyFileTest(ConfigStoreTestCase):
    """A config.json from before 0.73 is a snapshot of every value, secrets included."""

    env = {
        'notify_topic': 'from-env',
        'LMS_SUBSONIC_API_KEY': 'rotated-key',
        'DB_PASS': 'db-secret',
    }

    def write_config_file(self):
        self.config_path.write_text(
            json.dumps(
                {
                    'notify_topic': 'from-env',
                    'crash_hook_url': 'https://hook.test/x',
                    'lms_subsonic_api_key': 'stale-key',
                    'spotify_client_secret': 'typed-on-the-page',
                    'db_pass': 'old-db-secret',
                    'debug': False,
                }
            ),
            encoding='utf-8',
        )
        self.config_path.chmod(0o644)

    def test_a_value_that_differs_from_env_and_default_still_loads(self):
        self.assertEqual(self.store.get('crash_hook_url'), 'https://hook.test/x')
        self.assertEqual(self.store.get('spotify_client_secret'), 'typed-on-the-page')

    def test_a_secret_the_environment_sets_is_left_to_the_environment(self):
        # The recurring stale-LMS-key failure: a snapshot of an old key beat every deploy.
        self.assertEqual(self.store.get('lms_subsonic_api_key'), 'rotated-key')

    def test_read_only_fields_are_not_taken_from_the_file(self):
        self.assertEqual(self.store.get('db_pass'), 'db-secret')

    def test_the_file_is_rewritten_with_the_overrides_only(self):
        data = on_disk(self.config_path)
        self.assertEqual(data[config_store.FILE_FORMAT_KEY], config_store.FILE_FORMAT)
        self.assertEqual(
            {k: v for k, v in data.items() if k != config_store.FILE_FORMAT_KEY},
            {'crash_hook_url': 'https://hook.test/x', 'spotify_client_secret': 'typed-on-the-page'},
        )
        self.assertEqual(self.config_path.stat().st_mode & 0o777, 0o600)


class ConfigStoreCurrentFileTest(ConfigStoreTestCase):
    """In the current format every entry is an override the API set, and it wins."""

    env = {'LMS_SUBSONIC_API_KEY': 'env-key'}

    def write_config_file(self):
        self.config_path.write_text(
            json.dumps({config_store.FILE_FORMAT_KEY: config_store.FILE_FORMAT, 'lms_subsonic_api_key': 'page-key'}),
            encoding='utf-8',
        )
        self.config_path.chmod(0o644)

    def test_an_override_from_the_file_wins_over_the_environment(self):
        self.assertEqual(self.store.get('lms_subsonic_api_key'), 'page-key')

    def test_loading_tightens_the_file_permissions(self):
        self.assertEqual(self.config_path.stat().st_mode & 0o777, 0o600)
