"""Unit tests that must run outside services/.

Until bug report 085, services/conftest.py installed the mock_base stubs (mutagen,
yt-dlp, pymysql, ...) for the whole session, so a test that needed the real library
had to live here, in tests/unit/, and run its real-library work in a child
interpreter. The stubs are opt-in per module now (`pytest.mark.mock_base`), so a new
test that needs a real library can live anywhere; the tests here keep their child
interpreters, which also keep their real-library work away from module state the rest
of the session shares.

Nothing is configured here; the file exists so the directory is collected (and
covered by backend:unit's `changes:` rule) before the first test lands in it.
"""
