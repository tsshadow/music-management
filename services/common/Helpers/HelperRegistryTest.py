import unittest
from unittest.mock import MagicMock

from services.common.Helpers.HelperRegistry import reload_helpers


class HelperRegistryTest(unittest.TestCase):
    """`Cache.databaseHelpers` is built once at import; this is how it is refreshed.

    The dispatcher lives here rather than in Cache.py because importing Cache
    constructs every helper against a real database, which is also why
    services/tests/mock_base.py replaces that module wholesale.
    """

    def setUp(self):
        self.artist = MagicMock()
        self.subgenre = MagicMock()
        self.helpers = {'artistGenreHelper': self.artist, 'subgenreHelper': self.subgenre}

    def test_reloads_only_the_named_helper(self):
        reloaded = reload_helpers(self.helpers, 'artistGenreHelper')
        self.artist.reload.assert_called_once_with()
        self.subgenre.reload.assert_not_called()
        self.assertEqual(reloaded, ['artistGenreHelper'])

    def test_reloads_every_helper_when_no_key_is_given(self):
        reloaded = reload_helpers(self.helpers)
        self.artist.reload.assert_called_once_with()
        self.subgenre.reload.assert_called_once_with()
        self.assertEqual(sorted(reloaded), ['artistGenreHelper', 'subgenreHelper'])

    def test_an_unknown_key_is_ignored_rather_than_raising(self):
        self.assertEqual(reload_helpers(self.helpers, 'nosuchhelper'), [])

    def test_a_helper_without_reload_is_skipped(self):
        # TableHelper and FilterTableHelper do not preload the same way and have no
        # reload; asking for one must not take the endpoint down with an AttributeError.
        plain = object()
        self.assertEqual(reload_helpers({'plain': plain}, 'plain'), [])

    def test_one_failing_helper_does_not_stop_the_others(self):
        self.artist.reload.side_effect = RuntimeError('database gone')
        reloaded = reload_helpers(self.helpers)
        self.subgenre.reload.assert_called_once_with()
        self.assertEqual(reloaded, ['subgenreHelper'])
