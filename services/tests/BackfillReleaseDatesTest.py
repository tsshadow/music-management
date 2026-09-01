"""Covers scripts/backfill_release_dates.py.

The backfill writes tags across the whole library in one pass, so what matters is what it plans:
the year guard has to reject a rip date on old music before anything touches a file.
"""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'backfill_release_dates.py'

spec = importlib.util.spec_from_file_location('backfill_release_dates', SCRIPT)
backfill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backfill)


def _helper():
    helper = MagicMock()
    helper.get = MagicMock(return_value=[])
    return helper


def _release(tmp_path, dirname, nfo_text, with_audio=True):
    directory = tmp_path / dirname
    directory.mkdir()
    (directory / '00-release.nfo').write_bytes(nfo_text.encode('latin-1'))
    if with_audio:
        (directory / '01-track.mp3').write_bytes(b'')
    return directory


def test_plans_a_date_for_a_release_with_an_nfo(tmp_path):
    _release(tmp_path, 'X_-_Y-(008R017)-WEB-2026-ZzZz', 'Str.date : 16-01-2026')
    planned = backfill.plan_release_dates(str(tmp_path), _helper())
    assert [date for _directory, date in planned] == ['2026-01-16']


def test_skips_a_release_whose_nfo_year_disagrees(tmp_path):
    """A 1995 vinyl rip carrying a 2024 rip date must not be redated."""
    _release(tmp_path, 'X_-_Y-(MIDLP1)-VINYL-FLAC-1995-OTS', 'Date: 2024-07-28')
    assert backfill.plan_release_dates(str(tmp_path), _helper()) == []


def test_skips_a_directory_with_no_audio(tmp_path):
    _release(tmp_path, 'X_-_Y-(0001)-WEB-2026-ZzZz', 'Str.date : 16-01-2026', with_audio=False)
    assert backfill.plan_release_dates(str(tmp_path), _helper()) == []


def test_consults_the_override_table_for_the_scene_group(tmp_path):
    _release(tmp_path, 'X_-_Y-(DWX1)-WEB-2026-SPiDeR', 'Releasedate : 05.06.2026')
    helper = MagicMock()
    helper.get = MagicMock(return_value=['md'])
    planned = backfill.plan_release_dates(str(tmp_path), helper)
    helper.get.assert_called_once_with('SPiDeR')
    assert [date for _directory, date in planned] == ['2026-05-06']
