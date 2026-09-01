"""The system API key must be configured, never baked into the source.

The key that used to sit in the source as a fallback is spelled out here on
purpose: these tests assert it is *rejected*, so if it (or any other literal)
ever comes back as a default, they fail.
"""

import os
import unittest
from unittest.mock import patch

from services.music_manager.api_key import is_system_api_key, resolve_system_api_key

LEAKED_LITERAL = '00000000-0000-4000-8000-000000000000'


class ApiKeyResolutionTest(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_no_key_configured_resolves_to_none(self):
        self.assertIsNone(resolve_system_api_key())

    @patch.dict(os.environ, {'API_KEY': '', 'MUMA_API_KEY': ''}, clear=True)
    def test_empty_values_count_as_unconfigured(self):
        self.assertIsNone(resolve_system_api_key())

    @patch.dict(os.environ, {'API_KEY': 'from-api-key', 'MUMA_API_KEY': 'from-muma'}, clear=True)
    def test_api_key_wins_over_muma_api_key(self):
        self.assertEqual(resolve_system_api_key(), 'from-api-key')

    @patch.dict(os.environ, {'MUMA_API_KEY': 'from-muma'}, clear=True)
    def test_muma_api_key_is_the_fallback(self):
        self.assertEqual(resolve_system_api_key(), 'from-muma')


class IsSystemApiKeyTest(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_nothing_is_the_system_key_when_none_is_configured(self):
        """The whole point: no configuration means no system access, not default access."""
        self.assertFalse(is_system_api_key(LEAKED_LITERAL))
        self.assertFalse(is_system_api_key('anything'))
        self.assertFalse(is_system_api_key(''))
        self.assertFalse(is_system_api_key(None))

    @patch.dict(os.environ, {'API_KEY': 'the-configured-key'}, clear=True)
    def test_only_the_configured_key_matches(self):
        self.assertTrue(is_system_api_key('the-configured-key'))
        self.assertFalse(is_system_api_key(LEAKED_LITERAL))
        self.assertFalse(is_system_api_key('the-configured-ke'))
        self.assertFalse(is_system_api_key(None))

    @patch.dict(os.environ, {'API_KEY': 'the-configured-key'}, clear=True)
    def test_env_is_read_per_call_not_captured_at_import(self):
        self.assertTrue(is_system_api_key('the-configured-key'))
        os.environ['API_KEY'] = 'rotated-key'
        self.assertFalse(is_system_api_key('the-configured-key'))
        self.assertTrue(is_system_api_key('rotated-key'))


class NoLiteralKeyInSourceTest(unittest.TestCase):
    def test_the_leaked_key_is_gone_from_the_python_sources(self):
        """A grep guard: the literal must not reappear in any shipped module."""
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        offenders = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in {'node_modules', 'build', '__pycache__', '.git', '.venv'}]
            for filename in filenames:
                if not filename.endswith('.py'):
                    continue
                path = os.path.join(dirpath, filename)
                if os.path.abspath(path) == os.path.abspath(__file__):
                    continue  # this module names it deliberately
                with open(path, encoding='utf-8', errors='ignore') as handle:
                    if LEAKED_LITERAL in handle.read():
                        offenders.append(os.path.relpath(path, root))
        self.assertEqual(offenders, [], f'leaked API key literal found in: {offenders}')


if __name__ == '__main__':
    unittest.main()
