"""Covers scripts/release/assemble_changelog.py.

What matters is where the assembled block lands: under `## [Unreleased]` and above the newest
version heading, with the previously shipped section untouched. Getting that wrong is the exact
failure the fragments exist to prevent, and no other test in the repository reads a changelog.
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'release' / 'assemble_changelog.py'

spec = importlib.util.spec_from_file_location('assemble_changelog', SCRIPT)
assemble_changelog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assemble_changelog)

CHANGELOG = """# Changelog

## [Unreleased]

## [0.44.4] - 2026-09-04

### Fixed
- **Iets ouds.** Dat al uitgebracht is.
"""

RELEASE_NOTES = """# Release Notes

## Unreleased

## Global Version 0.44.4 (2026-09-04)

- **Iets ouds.**
"""

# muma-mobile's release notes head their pending block differently from the root file:
# `## [Unreleased]`, with the brackets. This fixture used to hand the mobile scope the
# root spelling, which is why the mobile path passed here while failing on the real
# repository -- and failing destructively, since the write truncated first.
MOBILE_RELEASE_NOTES = RELEASE_NOTES.replace('## Unreleased', '## [Unreleased]')


def _repo(tmp_path, fragments, mobile_fragments=None):
    (tmp_path / 'CHANGELOG.md').write_text(CHANGELOG)
    (tmp_path / 'RELEASE_NOTES.md').write_text(RELEASE_NOTES)
    directory = tmp_path / 'changelog.d'
    directory.mkdir()
    (directory / 'README.md').write_text('how to write a fragment')
    for name, body in fragments.items():
        (directory / name).write_text(body)
    if mobile_fragments is not None:
        mobile = tmp_path / 'services' / 'muma-mobile'
        (mobile / 'app' / 'src' / 'main' / 'assets').mkdir(parents=True)
        (mobile / 'CHANGELOG.md').write_text(CHANGELOG)
        (mobile / 'RELEASE_NOTES.md').write_text(MOBILE_RELEASE_NOTES)
        (mobile / 'app' / 'src' / 'main' / 'assets' / 'RELEASE_NOTES.md').write_text(MOBILE_RELEASE_NOTES)
        (directory / 'mobile').mkdir()
        for name, body in mobile_fragments.items():
            (directory / 'mobile' / name).write_text(body)
    return tmp_path


def test_the_new_section_lands_above_the_previous_release(tmp_path):
    _repo(tmp_path, {'619.fixed.md': '- **Een fix.** Met uitleg.'})
    assemble_changelog.assemble('root', '0.45.0', '2026-09-05', apply_changes=True, root=str(tmp_path))
    headings = [line for line in (tmp_path / 'CHANGELOG.md').read_text().splitlines() if line.startswith('## ')]
    assert headings == ['## [Unreleased]', '## [0.45.0] - 2026-09-05', '## [0.44.4] - 2026-09-04']


def test_the_shipped_section_is_left_exactly_as_it_was(tmp_path):
    """The misfiling this replaces edited a released section. Nothing may touch it."""
    _repo(tmp_path, {'619.fixed.md': '- **Een fix.** Met uitleg.'})
    assemble_changelog.assemble('root', '0.45.0', '2026-09-05', apply_changes=True, root=str(tmp_path))
    text = (tmp_path / 'CHANGELOG.md').read_text()
    shipped = text[text.index('## [0.44.4]') :]
    assert shipped == '## [0.44.4] - 2026-09-04\n\n### Fixed\n- **Iets ouds.** Dat al uitgebracht is.\n'


def test_sections_come_out_in_keep_a_changelog_order(tmp_path):
    _repo(
        tmp_path,
        {
            '2.fixed.md': '- **Een fix.**',
            '1.added.md': '- **Iets nieuws.**',
            '3.changed.md': '- **Iets anders.**',
        },
    )
    assemble_changelog.assemble('root', '0.45.0', '2026-09-05', apply_changes=True, root=str(tmp_path))
    text = (tmp_path / 'CHANGELOG.md').read_text()
    assert [line for line in text.splitlines() if line.startswith('### ')] == [
        '### Added',
        '### Changed',
        '### Fixed',
        '### Fixed',
    ]


def test_two_fragments_in_one_section_share_its_heading(tmp_path):
    _repo(tmp_path, {'1.fixed.md': '- **Eerste.**', '2.fixed.md': '- **Tweede.**'})
    assemble_changelog.assemble('root', '0.45.0', '2026-09-05', apply_changes=True, root=str(tmp_path))
    new = (tmp_path / 'CHANGELOG.md').read_text().split('## [0.44.4]')[0]
    assert new.count('### Fixed') == 1
    assert '- **Eerste.**' in new and '- **Tweede.**' in new


def test_the_release_notes_use_the_shorter_wording_when_there_is_one(tmp_path):
    _repo(
        tmp_path,
        {'619.fixed.md': '- **Lang, met code.** `patoolib`\n\n<!-- release notes -->\n\n- **Kort.**'},
    )
    assemble_changelog.assemble('root', '0.45.0', '2026-09-05', apply_changes=True, root=str(tmp_path))
    notes = (tmp_path / 'RELEASE_NOTES.md').read_text()
    assert '- **Kort.**' in notes
    assert 'patoolib' not in notes
    assert 'patoolib' in (tmp_path / 'CHANGELOG.md').read_text()


def test_a_fragment_without_a_marker_says_the_same_in_both_files(tmp_path):
    _repo(tmp_path, {'619.fixed.md': '- **Eén wording.**'})
    assemble_changelog.assemble('root', '0.45.0', '2026-09-05', apply_changes=True, root=str(tmp_path))
    assert '- **Eén wording.**' in (tmp_path / 'RELEASE_NOTES.md').read_text()
    assert '- **Eén wording.**' in (tmp_path / 'CHANGELOG.md').read_text()


def test_the_fragments_are_removed_once_they_are_in(tmp_path):
    _repo(tmp_path, {'619.fixed.md': '- **Een fix.**'})
    assemble_changelog.assemble('root', '0.45.0', '2026-09-05', apply_changes=True, root=str(tmp_path))
    assert not (tmp_path / 'changelog.d' / '619.fixed.md').exists()
    assert (tmp_path / 'changelog.d' / 'README.md').exists()


def test_a_dry_run_writes_nothing_and_keeps_the_fragments(tmp_path):
    _repo(tmp_path, {'619.fixed.md': '- **Een fix.**'})
    assemble_changelog.assemble('root', '0.45.0', '2026-09-05', apply_changes=False, root=str(tmp_path))
    assert (tmp_path / 'CHANGELOG.md').read_text() == CHANGELOG
    assert (tmp_path / 'changelog.d' / '619.fixed.md').exists()


def test_a_release_with_no_fragments_changes_nothing(tmp_path):
    _repo(tmp_path, {})
    assert assemble_changelog.assemble('root', '0.45.0', '2026-09-05', apply_changes=True, root=str(tmp_path)) == []
    assert (tmp_path / 'CHANGELOG.md').read_text() == CHANGELOG


def test_an_unknown_section_in_the_filename_is_refused(tmp_path):
    """Silently dropping a fragment is worse than a red pipeline: the entry is gone."""
    _repo(tmp_path, {'619.improved.md': '- **Een fix.**'})
    with pytest.raises(ValueError, match='619.improved.md'):
        assemble_changelog.assemble('root', '0.45.0', '2026-09-05', apply_changes=True, root=str(tmp_path))


def test_an_empty_fragment_is_refused(tmp_path):
    _repo(tmp_path, {'619.fixed.md': '\n\n'})
    with pytest.raises(ValueError, match='empty'):
        assemble_changelog.assemble('root', '0.45.0', '2026-09-05', apply_changes=True, root=str(tmp_path))


def test_the_mobile_fragments_are_not_part_of_the_root_scope(tmp_path):
    _repo(tmp_path, {'1.fixed.md': '- **Server.**'}, mobile_fragments={'2.fixed.md': '- **App.**'})
    assemble_changelog.assemble('root', '0.45.0', '2026-09-05', apply_changes=True, root=str(tmp_path))
    assert '- **App.**' not in (tmp_path / 'CHANGELOG.md').read_text()
    assert (tmp_path / 'changelog.d' / 'mobile' / '2.fixed.md').exists()


def test_the_mobile_scope_writes_both_copies_of_the_release_notes(tmp_path):
    """The copy under app/src/main/assets is what the in-app screen reads; drift fails the release."""
    _repo(tmp_path, {}, mobile_fragments={'2.fixed.md': '- **App.**'})
    assemble_changelog.assemble('mobile', '0.46.0', '2026-09-05', apply_changes=True, root=str(tmp_path))
    mobile = tmp_path / 'services' / 'muma-mobile'
    assert '- **App.**' in (mobile / 'CHANGELOG.md').read_text()
    assert '- **App.**' in (mobile / 'RELEASE_NOTES.md').read_text()
    assert '- **App.**' in (mobile / 'app' / 'src' / 'main' / 'assets' / 'RELEASE_NOTES.md').read_text()


def test_a_changelog_without_an_unreleased_heading_is_refused(tmp_path):
    _repo(tmp_path, {'619.fixed.md': '- **Een fix.**'})
    (tmp_path / 'CHANGELOG.md').write_text('# Changelog\n\n## [0.44.4] - 2026-09-04\n')
    with pytest.raises(ValueError, match='Unreleased'):
        assemble_changelog.assemble('root', '0.45.0', '2026-09-05', apply_changes=True, root=str(tmp_path))


def test_release_notes_may_bracket_the_unreleased_heading(tmp_path):
    """muma-mobile's RELEASE_NOTES.md brackets it; the root one does not."""
    _repo(tmp_path, {}, mobile_fragments={'2.changed.md': '- **App.**'})
    mobile = tmp_path / 'services' / 'muma-mobile'
    (mobile / 'RELEASE_NOTES.md').write_text(RELEASE_NOTES.replace('## Unreleased', '## [Unreleased]'))
    assemble_changelog.assemble('mobile', '6.28.4', '2026-09-06', apply_changes=True, root=str(tmp_path))
    assert '- **App.**' in (mobile / 'RELEASE_NOTES.md').read_text()


def test_a_scope_that_cannot_be_assembled_leaves_every_file_alone(tmp_path):
    """It used to open each file for writing before knowing it could write it, so the first
    unusable heading truncated a 47 KB file to nothing on the release branch."""
    _repo(tmp_path, {}, mobile_fragments={'2.changed.md': '- **App.**'})
    mobile = tmp_path / 'services' / 'muma-mobile'
    (mobile / 'RELEASE_NOTES.md').write_text('# Release Notes\n\nno heading here\n')
    with pytest.raises(ValueError, match='Unreleased'):
        assemble_changelog.assemble('mobile', '6.28.4', '2026-09-06', apply_changes=True, root=str(tmp_path))
    assert (mobile / 'RELEASE_NOTES.md').read_text() == '# Release Notes\n\nno heading here\n'
    assert (mobile / 'CHANGELOG.md').read_text() == CHANGELOG
    assert (tmp_path / 'changelog.d' / 'mobile' / '2.changed.md').exists()


def test_the_mobile_scope_needs_its_own_version(tmp_path, monkeypatch):
    """The app's versionName runs a minor ahead of the root VERSION, so sharing one is wrong."""
    _repo(tmp_path, {'1.fixed.md': '- **Server.**'}, mobile_fragments={'2.changed.md': '- **App.**'})
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        assemble_changelog.main(['--version', '0.46.1', '--apply'])
    assert (tmp_path / 'changelog.d' / 'mobile' / '2.changed.md').exists()


def test_a_root_only_release_does_not_ask_for_a_mobile_version(tmp_path, monkeypatch):
    _repo(tmp_path, {'1.fixed.md': '- **Server.**'}, mobile_fragments={})
    monkeypatch.chdir(tmp_path)
    assert assemble_changelog.main(['--version', '0.46.1', '--apply']) == 0
    assert '- **Server.**' in (tmp_path / 'CHANGELOG.md').read_text()


def test_a_refused_release_notes_file_is_left_exactly_as_it_was(tmp_path):
    """The refusal used to destroy the file it refused.

    `open(path, 'w')` truncates when it is called, and the anchor was checked inside
    that block, so a release notes file without the heading came out empty -- 762 lines
    of muma-mobile history, on the release that found this.
    """
    _repo(tmp_path, {'619.fixed.md': '- **Een fix.**'})
    before = '# Release Notes\n\n## Global Version 0.44.4 (2026-09-04)\n\n- **Iets ouds.**\n'
    (tmp_path / 'RELEASE_NOTES.md').write_text(before)

    with pytest.raises(ValueError, match='Unreleased'):
        assemble_changelog.assemble('root', '0.45.0', '2026-09-05', apply_changes=True, root=str(tmp_path))

    assert (tmp_path / 'RELEASE_NOTES.md').read_text() == before
    # And the changelog it would have written first stays untouched too, so the release
    # can simply be re-run once the file is fixed.
    assert '0.45.0' not in (tmp_path / 'CHANGELOG.md').read_text()
    assert (tmp_path / 'changelog.d' / '619.fixed.md').exists()


def test_a_blank_line_separates_the_new_section_from_the_previous_release(tmp_path):
    """0.76.0 and 0.77.1 shipped muma-mobile's changelog with `## [7.5.x]` glued to the last bullet."""
    _repo(tmp_path, {'619.fixed.md': '- **Een fix.** Met uitleg.'})
    assemble_changelog.assemble('root', '0.45.0', '2026-09-05', apply_changes=True, root=str(tmp_path))
    lines = (tmp_path / 'CHANGELOG.md').read_text().splitlines()
    assert lines[lines.index('## [0.44.4] - 2026-09-04') - 1] == ''
    notes = (tmp_path / 'RELEASE_NOTES.md').read_text().splitlines()
    assert notes[notes.index('## Global Version 0.44.4 (2026-09-04)') - 1] == ''
