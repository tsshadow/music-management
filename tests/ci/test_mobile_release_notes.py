"""services/muma-mobile/scripts/release-notes.sh: the notes publish.sh puts next to the APK (issue #205).

The release assembler writes `## Global Version <v> (<date>)`; publish.sh only read `## [<v>]`, so
every APK since the changelog fragments reached the hoster without notes.
"""

import subprocess

from tests.ci.conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "services" / "muma-mobile" / "scripts" / "release-notes.sh"

NOTES = """## [Unreleased]

## Global Version 7.20.1 (2026-11-07)

- Radio ends when you pick a track.

## Global Version 7.20.0 (2026-11-07)

- **Radio has 67 stations.**

### Fixed

- Pause works.

## Global Version 7.2.0 (2026-01-01)

- Old one.

## [7.1.0]

- Hand-written section.

"""


def _notes(tmp_path, version):
    path = tmp_path / "RELEASE_NOTES.md"
    path.write_text(NOTES, encoding="utf-8")
    result = subprocess.run(["bash", str(SCRIPT), version, str(path)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_an_assembled_section_is_found_without_its_heading(tmp_path):
    assert _notes(tmp_path, "7.20.1") == "- Radio ends when you pick a track.\n"


def test_a_section_keeps_its_subheadings_and_stops_at_the_next_version(tmp_path):
    assert _notes(tmp_path, "7.20.0") == "- **Radio has 67 stations.**\n\n### Fixed\n\n- Pause works.\n"


def test_the_old_bracket_heading_is_still_read(tmp_path):
    assert _notes(tmp_path, "7.1.0") == "- Hand-written section.\n"


def test_a_version_prefix_does_not_match_a_longer_version(tmp_path):
    assert _notes(tmp_path, "7.2") == ""
    assert _notes(tmp_path, "7.20") == ""


def test_a_debug_query_with_its_version_code_finds_nothing(tmp_path):
    assert _notes(tmp_path, "7.20.1-371") == ""


def test_publish_sh_reads_the_notes_through_this_script():
    text = (REPO_ROOT / "services" / "muma-mobile" / "scripts" / "publish.sh").read_text(encoding="utf-8")
    assert 'scripts/release-notes.sh "$VER_QUERY"' in text
    assert "awk" not in text.split("--- Extracting release notes")[1].split("APK_PATH=")[0]
