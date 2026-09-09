"""The baseline generator must not throw away the reasons somebody wrote by hand.

The whole file is rebuilt from REASONS on every `SAST_WRITE_BASELINE=1`, and the
reasons are also the first thing a reader sees *in* the file -- so that is where
people edit them, and that is what gets silently overwritten. It has happened
twice: once badly enough that the person who restored the text left a note in the
file warning the next reader, and again on 2026-09-08, which cost 36 lines.

Nothing tested this script at all before, which is how the same accident happened
twice. What is pinned here is narrow: regenerating either reproduces every reason
in the file, or it refuses and says what it would have lost.
"""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'ci' / 'sast_baseline.py'

spec = importlib.util.spec_from_file_location('sast_baseline', SCRIPT)
sast = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sast)

REPO_BASELINE = Path(__file__).resolve().parents[2] / 'security' / 'accepted-sast-findings.txt'


def _report(tmp_path, rule='use-of-md5', path='services/a.py', line='hashlib.md5(x)'):
    report = {
        'results': [
            {
                'check_id': f'python.lang.security.{rule}',
                'path': path,
                'start': {'line': 3},
                'extra': {'lines': line, 'message': 'md5 is weak'},
            }
        ]
    }
    report_path = tmp_path / 'report.json'
    report_path.write_text(json.dumps(report), encoding='utf-8')
    return str(report_path)


def _baseline(tmp_path, text):
    baseline = tmp_path / 'accepted.txt'
    baseline.write_text(text, encoding='utf-8')
    return baseline


def test_a_generated_baseline_regenerates_unchanged(tmp_path):
    # The round trip that has to hold: what the writer produced, the writer
    # accepts. Without this, every guard below could be satisfied by refusing
    # always.
    report = _report(tmp_path)
    baseline = tmp_path / 'accepted.txt'
    assert sast.write_baseline(report, str(baseline)) == 0
    first = baseline.read_text(encoding='utf-8')
    assert sast.write_baseline(report, str(baseline)) == 0
    assert baseline.read_text(encoding='utf-8') == first


def test_a_hand_written_reason_stops_the_rewrite(tmp_path, capsys):
    baseline = _baseline(
        tmp_path,
        sast.HEADER
        + '\n# --- use-of-md5 ---\n# Audited 2026-08-31 by hand: this one is a cache key.\ndeadbeefdeadbeef x1  # use-of-md5 services/a.py\n',
    )
    before = baseline.read_text(encoding='utf-8')

    status = sast.write_baseline(_report(tmp_path), str(baseline))

    assert status == 1
    assert baseline.read_text(encoding='utf-8') == before, 'the file was rewritten anyway'
    printed = capsys.readouterr().out
    assert 'Audited 2026-08-31 by hand' in printed, 'the lost text has to be shown, not just counted'
    assert 'REASONS' in printed


def test_the_reason_that_is_in_reasons_is_not_treated_as_hand_written(tmp_path):
    # Rewrapping must not read as an edit: the writer wraps at 74 columns and a
    # person may have joined the lines differently.
    reason = sast.REASONS['use-of-md5']
    baseline = _baseline(
        tmp_path,
        sast.HEADER + f'\n# --- use-of-md5 ---\n# {reason}\ndeadbeefdeadbeef x1  # use-of-md5 services/a.py\n',
    )
    assert sast.write_baseline(_report(tmp_path), str(baseline)) == 0


def test_an_edited_header_is_protected_too(tmp_path):
    baseline = _baseline(tmp_path, sast.HEADER + '# And a line somebody added to the header.\n')
    assert sast.write_baseline(_report(tmp_path), str(baseline)) == 1


def test_a_not_yet_audited_section_is_free_to_replace(tmp_path):
    # That text is the generator's own placeholder, so overwriting it loses nothing --
    # including the case this exists for: a rule whose reason was just written into
    # REASONS and now replaces the placeholder in the file.
    baseline = _baseline(
        tmp_path,
        sast.HEADER + '\n# --- use-of-md5 ---\n# NOT YET AUDITED.\ndeadbeefdeadbeef x1  # use-of-md5 services/a.py\n',
    )
    assert sast.write_baseline(_report(tmp_path), str(baseline)) == 0
    assert sast.REASONS['use-of-md5'].split()[0] in baseline.read_text(encoding='utf-8')


def test_the_override_exists_and_says_what_it_costs(tmp_path, monkeypatch):
    baseline = _baseline(
        tmp_path,
        sast.HEADER + '\n# --- use-of-md5 ---\n# Hand-written.\ndeadbeefdeadbeef x1  # use-of-md5 services/a.py\n',
    )
    monkeypatch.setenv('SAST_BASELINE_FORCE', '1')
    assert sast.write_baseline(_report(tmp_path), str(baseline)) == 0
    assert 'Hand-written' not in baseline.read_text(encoding='utf-8')


def test_a_missing_baseline_is_written_from_scratch(tmp_path):
    baseline = tmp_path / 'does-not-exist.txt'
    assert sast.write_baseline(_report(tmp_path), str(baseline)) == 0
    assert baseline.exists()


@pytest.mark.skipif(not REPO_BASELINE.exists(), reason='baseline not in this checkout')
def test_this_repositorys_baseline_carries_no_unreproducible_reason():
    # The end state of the repair: every reason in the committed file comes from
    # REASONS, so a regeneration is safe. A new hand-written paragraph fails here
    # rather than in six weeks when somebody accepts a finding.
    lost = sast.unwritable_rationale(str(REPO_BASELINE))
    assert lost == {}, (
        'these sections hold text that regenerating would destroy; move it into '
        f'REASONS in scripts/ci/sast_baseline.py: {sorted(lost)}'
    )
