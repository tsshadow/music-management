"""Unit tests that must run outside services/.

services/conftest.py installs the mock_base stubs (mutagen, yt-dlp, pymysql, ...)
for everything collected under it, for the whole session. A test that needs the
real library therefore lives here, in tests/unit/, which
scripts/test/music-management-unit.sh collects alongside services/, tools/ and
tests/ci/. Such a test runs its real-library work in a child interpreter, because
by the time it runs the stubs are already in sys.modules.

Nothing is configured here; the file exists so the directory is collected (and
covered by backend:unit's `changes:` rule) before the first test lands in it.
"""
