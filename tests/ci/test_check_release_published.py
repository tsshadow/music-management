"""release:publish holds the tag until the release is published (docs/designs/ops-split/).

``scripts/ci/check-release-published.sh`` asks the GitLab API about the release branch pipeline of
the merged commit and the APK package. A fake ``curl`` answers from a dict, so each test names the
one thing that is missing.
"""

import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "check-release-published.sh"
GRADLE = (ROOT / "services" / "muma-mobile" / "app" / "build.gradle").read_text(encoding="utf-8")
NAME = re.search(r'versionName\s+"([^"]+)"', GRADLE).group(1)
CODE = re.search(r"versionCode\s+(\d+)", GRADLE).group(1)
APK = f"muma-mobile-v{NAME}-{CODE}.apk"

# Answers the fake curl gives, by the last path segment of the URL before the query.
GOOD = {
    "pipelines": [{"id": 7, "ref": "release/9.9.9"}],
    "jobs": [
        {"name": "release:build-images", "status": "success"},
        {"name": "mobile:build-release", "status": "success"},
    ],
    "packages": [{"id": 3, "name": "muma-mobile", "version": NAME}],
    "package_files": [{"file_name": APK}],
}

FAKE_CURL = """#!/bin/bash
url="${@: -1}"
key="${url%%\\?*}"; key="${key##*/}"
file="$ANSWERS/$key.json"
[ -f "$file" ] || exit 22
cat "$file"
"""


def _merge_commit() -> str:
    out = subprocess.run(
        ["git", "log", "--merges", "-1", "--format=%H"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    if not out.stdout.strip():
        pytest.skip("needs a merge commit in the history")
    return out.stdout.strip()


def _run(tmp_path: Path, answers: dict, **extra: str) -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(FAKE_CURL, encoding="utf-8")
    curl.chmod(curl.stat().st_mode | stat.S_IEXEC)
    answer_dir = tmp_path / "answers"
    answer_dir.mkdir()
    for key, value in answers.items():
        (answer_dir / f"{key}.json").write_text(json.dumps(value), encoding="utf-8")
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ANSWERS": str(answer_dir),
        "TAG_CREATION_TOKEN": "not-a-secret",
        "CI_API_V4_URL": "https://gitlab.example.org/api/v4",
        "CI_PROJECT_ID": "1",
        "CI_COMMIT_SHA": _merge_commit(),
    }
    env.update(extra)
    return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, check=False)


def test_a_published_release_passes(tmp_path):
    result = _run(tmp_path, GOOD)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"muma-mobile/{NAME}/{APK} exists" in result.stdout


def test_without_a_release_branch_pipeline_it_fails(tmp_path):
    result = _run(tmp_path, {**GOOD, "pipelines": [{"id": 8, "ref": "develop"}]})
    assert result.returncode == 1
    assert "no release or hotfix branch pipeline" in result.stdout


@pytest.mark.parametrize("job", ["release:build-images", "mobile:build-release"])
def test_a_build_job_that_did_not_succeed_fails_it(tmp_path, job):
    jobs = [j if j["name"] != job else {**j, "status": "skipped"} for j in GOOD["jobs"]]
    result = _run(tmp_path, {**GOOD, "jobs": jobs})
    assert result.returncode == 1
    assert f"has no successful {job}" in result.stdout


def test_a_missing_apk_fails_it(tmp_path):
    result = _run(tmp_path, {**GOOD, "package_files": [{"file_name": "muma-mobile-v0.0.1-1.apk"}]})
    assert result.returncode == 1
    assert f"has no {APK}" in result.stdout


def test_a_missing_package_fails_it(tmp_path):
    result = _run(tmp_path, {**GOOD, "packages": []})
    assert result.returncode == 1
    assert f"has no {APK}" in result.stdout


def test_without_the_token_it_stops(tmp_path):
    result = _run(tmp_path, GOOD, TAG_CREATION_TOKEN="")
    assert result.returncode == 1
    assert "TAG_CREATION_TOKEN" in result.stdout
