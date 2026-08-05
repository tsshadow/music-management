import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from services.common.version_helper import get_changelog, get_release_notes, get_version


def render(text, extensions=None):
    """Stand-in for markdown.markdown: the real module is mocked out globally by
    services/tests/mock_base.py, so the tests assert on what got handed to it."""
    return f'<rendered extensions={extensions}>{text}</rendered>'


class VersionHelperTest(unittest.TestCase):
    """The helper resolves its files relative to the working directory, so every
    test runs inside a throwaway directory rather than the real project root."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        previous = os.getcwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(self.root)
        patcher = patch('services.common.version_helper.markdown.markdown', side_effect=render)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_get_version_reads_the_version_file(self):
        (self.root / 'VERSION').write_text('0.0.57\n', encoding='utf-8')

        self.assertEqual(get_version(), '0.0.57')

    def test_get_version_finds_the_file_one_directory_up(self):
        (self.root / 'VERSION').write_text('0.0.57', encoding='utf-8')
        nested = self.root / 'services'
        nested.mkdir()
        os.chdir(nested)

        self.assertEqual(get_version(), '0.0.57')

    def test_get_version_is_unknown_without_a_version_file(self):
        self.assertEqual(get_version(), 'unknown')

    def test_get_release_notes_renders_markdown(self):
        (self.root / 'RELEASE_NOTES.md').write_text('# 0.0.57\n\nFixed the tagger.\n', encoding='utf-8')

        html = get_release_notes()

        self.assertIn('Fixed the tagger.', html)
        self.assertIn("extensions=['extra', 'toc']", html)

    def test_get_release_notes_prefers_the_service_specific_file(self):
        service_dir = self.root / 'services' / 'downloader'
        service_dir.mkdir(parents=True)
        (service_dir / 'RELEASE_NOTES.md').write_text('Downloader notes', encoding='utf-8')
        (self.root / 'RELEASE_NOTES.md').write_text('Root notes', encoding='utf-8')

        self.assertIn('Downloader notes', get_release_notes('downloader'))

    def test_get_release_notes_falls_back_to_the_root_file(self):
        (self.root / 'RELEASE_NOTES.md').write_text('Root notes', encoding='utf-8')

        self.assertIn('Root notes', get_release_notes('downloader'))

    def test_get_release_notes_reports_when_there_is_nothing_to_show(self):
        self.assertEqual(get_release_notes(), '<p>No release notes found.</p>')

    def test_get_changelog_renders_markdown(self):
        (self.root / 'CHANGELOG.md').write_text('## Changed\n\n- Something\n', encoding='utf-8')

        html = get_changelog()

        self.assertIn('Something', html)
        self.assertIn("extensions=['extra', 'toc']", html)

    def test_get_changelog_reports_when_there_is_nothing_to_show(self):
        self.assertEqual(get_changelog(), '<p>No changelog found.</p>')


if __name__ == '__main__':
    unittest.main()
