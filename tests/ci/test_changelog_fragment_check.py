"""The exemptions in scripts/ci/changelog-fragment-check.sh.

Only the paths that exit before touching git are exercised here: those are the ones
that decide whether a merge request is asked for a fragment at all, and they are pure
environment checks. The failing path fetches and diffs against the target branch, which
needs a real remote, so it stays out of this file.

Renovate's own merge requests are exempt for a different reason: it opens and merges
them itself, so the gate has nobody to remind and only parks the automerge queue.

The back-merge case is the reason this file exists. `muma:changelog` failed on every
master->develop merge request, and that failure is not cosmetic: the back-merge stays
open, an open back-merge suppresses master's branch pipeline, and the release after it
loses its tag.
"""

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'ci' / 'changelog-fragment-check.sh'


def run(**env):
    return subprocess.run(
        ['bash', str(SCRIPT)],
        capture_output=True,
        text=True,
        env={'PATH': '/usr/bin:/bin', **env},
        check=False,
    )


def test_the_back_merge_is_not_asked_for_a_fragment():
    result = run(CI_MERGE_REQUEST_SOURCE_BRANCH_NAME='master', CI_MERGE_REQUEST_TARGET_BRANCH_NAME='develop')
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'back-merge' in result.stdout


def test_a_release_branch_is_not_asked_for_a_fragment():
    result = run(CI_MERGE_REQUEST_SOURCE_BRANCH_NAME='release/0.47.0', CI_MERGE_REQUEST_TARGET_BRANCH_NAME='master')
    assert result.returncode == 0
    assert 'release branch' in result.stdout


def test_a_hotfix_branch_is_not_asked_for_a_fragment():
    result = run(CI_MERGE_REQUEST_SOURCE_BRANCH_NAME='hotfix/0.47.1', CI_MERGE_REQUEST_TARGET_BRANCH_NAME='master')
    assert result.returncode == 0
    assert 'release branch' in result.stdout


def test_a_renovate_branch_is_not_asked_for_a_fragment():
    result = run(
        CI_MERGE_REQUEST_SOURCE_BRANCH_NAME='renovate/python-(minorpatch)',
        CI_MERGE_REQUEST_TARGET_BRANCH_NAME='develop',
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'renovate branch' in result.stdout


def test_a_branch_merely_mentioning_renovate_is_an_ordinary_branch():
    """The exemption is the branch prefix Renovate actually uses, not the word."""
    result = run(
        CI_MERGE_REQUEST_SOURCE_BRANCH_NAME='fix/renovate-changelog-gate',
        CI_MERGE_REQUEST_TARGET_BRANCH_NAME='develop',
    )
    assert 'skipping' not in result.stdout


def test_the_label_still_excuses_a_feature_branch():
    result = run(
        CI_MERGE_REQUEST_LABELS='no-changelog',
        CI_MERGE_REQUEST_SOURCE_BRANCH_NAME='fix/whatever',
        CI_MERGE_REQUEST_TARGET_BRANCH_NAME='develop',
    )
    assert result.returncode == 0
    assert 'no-changelog' in result.stdout


def test_a_branch_pipeline_is_not_a_merge_request():
    result = run(CI_MERGE_REQUEST_SOURCE_BRANCH_NAME='develop')
    assert result.returncode == 0
    assert 'not a merge request' in result.stdout


@pytest.mark.parametrize('source', ['master-of-puppets', 'feat/master'])
def test_only_master_itself_is_the_back_merge(source):
    """A branch whose name merely contains 'master' is an ordinary feature branch.

    It reaches the git-diffing part of the script, so all that is asserted here is that
    it was not waved through by one of the exemptions.
    """
    result = run(CI_MERGE_REQUEST_SOURCE_BRANCH_NAME=source, CI_MERGE_REQUEST_TARGET_BRANCH_NAME='develop')
    assert 'skipping' not in result.stdout
