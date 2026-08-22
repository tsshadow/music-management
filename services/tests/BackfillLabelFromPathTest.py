"""Covers scripts/backfill_label_from_path.py.

The backfill rewrites the publisher of tracks across the whole library, so what matters is what it
plans: it has to repair a release folder that was stored as a label, and leave every other
disagreement between a track and its folder alone.
"""
import importlib.util
import os
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'backfill_label_from_path.py'

spec = importlib.util.spec_from_file_location('backfill_label_from_path', SCRIPT)
backfill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backfill)

RELEASE = 'Hartshorn_-_LOSE_CTRL-(ABSLT065)-SINGLE-WEB-2026-SRG'
ROOT = '/mnt/music/EPs'
NESTED = os.path.join(ROOT, 'ABSLT Records', f'ABSLT065 - {RELEASE}', RELEASE, '01-lose_ctrl.mp3')
FLAT = os.path.join(ROOT, 'ABSLT Records', f'ABSLT065 - {RELEASE}', '01-lose_ctrl.mp3')


def _tags(publisher, catalognumber='', copyright_tag='', date='2026'):
    return {
        'publisher': publisher,
        'catalognumber': catalognumber,
        'copyright': copyright_tag,
        'date': date,
    }


def test_repairs_a_release_folder_stored_as_the_label():
    changes = backfill.plan_fix(NESTED, ROOT, _tags(RELEASE, catalognumber=RELEASE))
    assert changes['publisher'] == 'ABSLT Records'
    assert changes['catalognumber'] == 'ABSLT065'


def test_repairs_a_release_that_was_flattened_after_it_was_tagged():
    """The inner folder is gone from the path, so only the tag still shows the mistake."""
    changes = backfill.plan_fix(FLAT, ROOT, _tags(RELEASE))
    assert changes['publisher'] == 'ABSLT Records'


def test_rewrites_a_copyright_built_from_the_wrong_publisher():
    changes = backfill.plan_fix(NESTED, ROOT, _tags(RELEASE, copyright_tag=f'{RELEASE} (2026)'))
    assert changes['copyright'] == 'ABSLT Records (2026)'


def test_repairs_the_copyright_of_a_release_whose_label_was_already_corrected():
    """The tagger only writes a copyright when there is none, so a wrong one outlives the fix."""
    tags = _tags('ABSLT Records', copyright_tag=f'ABSLT065 - {RELEASE} (2026)')
    changes = backfill.plan_fix(FLAT, ROOT, tags)
    assert changes == {'copyright': 'ABSLT Records (2026)'}


def test_keeps_a_copyright_that_was_not_derived_from_the_publisher():
    changes = backfill.plan_fix(NESTED, ROOT, _tags(RELEASE, copyright_tag='Absolute Records BV'))
    assert 'copyright' not in changes


def test_leaves_a_track_whose_label_already_matches_its_folder():
    assert backfill.plan_fix(FLAT, ROOT, _tags('ABSLT Records')) is None


def test_leaves_a_publisher_that_is_not_the_release_folder():
    """A hand corrected label must survive: a folder name alone is not evidence the tag is wrong."""
    assert backfill.plan_fix(FLAT, ROOT, _tags('Absolute Records')) is None


def test_leaves_a_track_without_a_publisher():
    """Never tagged is a different problem, and the tagger is what fills it in."""
    assert backfill.plan_fix(FLAT, ROOT, _tags('')) is None


def test_resumes_after_the_last_label_that_was_reported(tmp_path):
    """A pass that ran for hours has to pick up where it stopped, not start over."""
    for folder in ['A Label', 'B Label', 'C Label', '_Livesets']:
        (tmp_path / folder).mkdir()
    assert backfill.label_folders(str(tmp_path)) == ['A Label', 'B Label', 'C Label']
    assert backfill.label_folders(str(tmp_path), after='B Label') == ['C Label']


def test_reads_a_plan_written_as_lines_or_as_one_array(tmp_path):
    """The plan is appended per label, but a plan written in one go still has to load."""
    lines = tmp_path / 'lines.json'
    lines.write_text(
        '{"path": "/a.mp3", "changes": {"publisher": "X"}}\n'
        '{"path": "/b.mp3", "changes": {"publisher": "Y"}}\n'
    )
    array = tmp_path / 'array.json'
    array.write_text('[["/a.mp3", {"publisher": "X"}], ["/b.mp3", {"publisher": "Y"}]]')
    expected = [('/a.mp3', {'publisher': 'X'}), ('/b.mp3', {'publisher': 'Y'})]
    assert backfill.load_plan(str(lines)) == expected
    assert backfill.load_plan(str(array)) == expected


def test_skips_underscore_folders_and_eadir(tmp_path):
    """`_` label folders are parsed as generic songs and never carry a path derived publisher."""
    for folder in ['ABSLT Records/ABSLT065 - X', '_Livesets/Set', 'ABSLT Records/@eaDir']:
        (tmp_path / folder).mkdir(parents=True)
        (tmp_path / folder / '01-track.mp3').write_bytes(b'')
    found = [os.path.relpath(p, tmp_path) for p in backfill.audio_files(str(tmp_path))]
    assert found == [os.path.join('ABSLT Records', 'ABSLT065 - X', '01-track.mp3')]
