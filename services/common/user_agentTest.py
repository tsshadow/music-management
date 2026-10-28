"""Tests for the shared User-Agent builder and the rule that nothing else builds one."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.common import user_agent

SERVICES_DIR = Path(__file__).resolve().parents[1]


def _store_returning(value):
    """A stand-in module whose ConfigStore().get() answers `value`."""
    module = MagicMock()
    module.ConfigStore.return_value.get.return_value = value
    return patch.dict(sys.modules, {'services.common.config_store': module})


class BuildUserAgentTest(unittest.TestCase):
    """build_user_agent: product, version and the configured project address."""

    def test_carries_the_configured_project_url(self):
        with _store_returning('https://example.org/muma'):
            self.assertEqual(
                user_agent.build_user_agent('muma-importer', '0.1'),
                'muma-importer/0.1 (+https://example.org/muma)',
            )

    def test_without_a_project_url_names_no_address(self):
        with _store_returning(''):
            self.assertEqual(user_agent.build_user_agent('muma-importer', '0.1'), 'muma-importer/0.1')

    def test_whitespace_only_counts_as_empty(self):
        with _store_returning('  '):
            self.assertEqual(user_agent.build_user_agent('x', '1'), 'x/1')

    def test_falls_back_to_the_environment_when_the_store_cannot_open(self):
        module = MagicMock()
        module.ConfigStore.side_effect = OSError('read-only file system')
        with (
            patch.dict(sys.modules, {'services.common.config_store': module}),
            patch.dict('os.environ', {'PROJECT_URL': 'https://example.org/env'}),
        ):
            self.assertEqual(user_agent.build_user_agent('x', '1'), 'x/1 (+https://example.org/env)')


class NoHardCodedUserAgentTest(unittest.TestCase):
    """A module under services/ that writes its own User-Agent text bypasses the setting."""

    LITERAL = re.compile(r"""(User-Agent['"]\s*:\s*f?['"])|(\bUSER_AGENT\s*=\s*f?['"])""")
    #: A browser string the SoundCloud downloader sends on purpose; it is not an identity.
    ALLOWED = {'FIREFOX_USER_AGENT'}

    def test_no_module_builds_a_user_agent_without_the_helper(self):
        offenders = []
        for path in sorted(SERVICES_DIR.rglob('*.py')):
            relative = path.relative_to(SERVICES_DIR)
            parts = relative.parts
            if 'tests' in parts or path.name.endswith('Test.py') or path.name.startswith('test_'):
                continue
            if any(part in {'node_modules', 'music-management-server', 'muma-mobile', 'frontend'} for part in parts):
                continue
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
                if self.LITERAL.search(line) and not any(name in line for name in self.ALLOWED):
                    offenders.append(f'{relative}:{number}: {line.strip()}')
        self.assertEqual(offenders, [], 'build the User-Agent with services.common.user_agent.build_user_agent')


if __name__ == '__main__':
    unittest.main()
