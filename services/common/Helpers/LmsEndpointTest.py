import unittest
from unittest.mock import MagicMock, patch

from services.common.Helpers.LmsEndpoint import redact_url, resolve_lms_api_key

_KEY_ENV = {'MUMA_SERVER_SUBSONIC_API_KEY': '', 'LMS_SUBSONIC_API_KEY': ''}


class RedactUrlTest(unittest.TestCase):
    """Subsonic authenticates in the query string, and requests puts the URL in its errors."""

    def test_the_query_string_of_an_http_error_is_removed(self):
        message = '401 Client Error: Unauthorized for url: http://lms:5082/rest/ping.view?apiKey=s3cret&v=1.16.1'
        redacted = redact_url(message)
        self.assertNotIn('s3cret', redacted)
        self.assertEqual(redacted, '401 Client Error: Unauthorized for url: http://lms:5082/rest/ping.view?<redacted>')

    def test_a_connection_error_with_a_quoted_url_is_redacted(self):
        message = "HTTPConnectionPool(host='lms', port=5082): Max retries exceeded with url: /rest/x (Caused by 'http://lms:5082/rest/x?apiKey=s3cret')"
        self.assertNotIn('s3cret', redact_url(message))

    def test_the_bare_path_of_a_urllib3_connection_error_is_redacted(self):
        message = (
            "HTTPConnectionPool(host='lms', port=5082): Max retries exceeded with url: "
            '/rest/getSongsByFilter.view?apiKey=s3cret&v=1.16.1 (Caused by NewConnectionError(...))'
        )
        redacted = redact_url(message)
        self.assertNotIn('s3cret', redacted)
        self.assertIn('with url: /rest/getSongsByFilter.view?<redacted> (Caused by', redacted)

    def test_every_url_in_the_text_is_redacted(self):
        redacted = redact_url('a https://one.test/p?k=1 and http://two.test/q?k=2 end')
        self.assertEqual(redacted, 'a https://one.test/p?<redacted> and http://two.test/q?<redacted> end')

    def test_text_without_a_query_string_is_left_alone(self):
        self.assertEqual(redact_url('LMS down at http://lms:5082/rest/x'), 'LMS down at http://lms:5082/rest/x')

    def test_a_non_string_is_turned_into_text_first(self):
        self.assertEqual(redact_url(RuntimeError('boom')), 'boom')


class ResolveLmsApiKeyTest(unittest.TestCase):
    """One resolver for the radio scheduler and the scan trigger."""

    def _store(self, value):
        store = MagicMock()
        store.get.side_effect = lambda key: value if key == 'lms_subsonic_api_key' else None
        return store

    def test_the_config_store_value_wins(self):
        with patch.dict('os.environ', {**_KEY_ENV, 'MUMA_SERVER_SUBSONIC_API_KEY': 'env-key'}):
            self.assertEqual(resolve_lms_api_key(self._store('page-key')), 'page-key')

    def test_the_environment_is_the_fallback(self):
        with patch.dict('os.environ', {**_KEY_ENV, 'MUMA_SERVER_SUBSONIC_API_KEY': 'env-key'}):
            self.assertEqual(resolve_lms_api_key(self._store('')), 'env-key')

    def test_a_mocked_store_does_not_count_as_a_key(self):
        store = MagicMock()
        with patch.dict('os.environ', {**_KEY_ENV, 'LMS_SUBSONIC_API_KEY': 'env-key'}):
            self.assertEqual(resolve_lms_api_key(store), 'env-key')

    def test_a_store_that_raises_falls_back_to_the_environment(self):
        store = MagicMock()
        store.get.side_effect = RuntimeError('broken')
        with patch.dict('os.environ', {**_KEY_ENV, 'LMS_SUBSONIC_API_KEY': 'env-key'}):
            self.assertEqual(resolve_lms_api_key(store), 'env-key')

    def test_nothing_anywhere_is_an_empty_string(self):
        with patch.dict('os.environ', _KEY_ENV):
            self.assertEqual(resolve_lms_api_key(self._store(None)), '')

    def test_without_a_store_the_shared_config_store_is_asked(self):
        with (
            patch('services.common.config_store.ConfigStore') as store_cls,
            patch.dict('os.environ', _KEY_ENV),
        ):
            store_cls.return_value = self._store('shared-key')
            self.assertEqual(resolve_lms_api_key(), 'shared-key')


if __name__ == '__main__':
    unittest.main()
