#!/usr/bin/env python3
"""Decide which Docker image tags a runner may delete to reclaim disk.

Split out of disk-janitor.sh so the part that decides what to destroy is a
pure function over a listing, testable without a Docker daemon and without a
full disk. The shell script does the I/O: read the listing, run `docker rmi`
on what comes back here.

Reads `docker images --format '{{.Repository}}:{{.Tag}}\\t{{.CreatedAt}}\\t{{.ID}}'`
on stdin and writes one image reference per line to stdout, oldest first.

The rules encode what three separate outages taught us (see the
gitlab-runner-disk-fills-up notes):

* Release images (`<DOCKER_USER>/*`, named by DOCKER_USER, no default) are the big win: every release build keeps its
  version tag forever, and they are all recoverable from Docker Hub.
* `muma-ci/*` is the same story for the merge-request image builds. Those now
  build under a per-job `muma-ci-<job-id>/*` namespace instead, which
  build-and-push-images.sh removes itself on exit -- so what is left under one
  is a job that died without running its trap, and the whole namespace goes on
  age, `:latest` included. The old shared prefix stays here for images still on
  a runner from before that change.
* `music-management/android-ci:<dockerfile-hash>` gains a new tag whenever the
  Dockerfile changes, and each one is >5GB.
* `muma-test-<job-id>-*` should be cleaned up by `--rmi local` in the compose
  teardown, but a killed job leaves them behind.

Everything else is left alone on purpose. Third-party base images (mariadb,
phpmyadmin, aquasec/trivy, ...) cost a re-pull and free little, and an image
this script has never heard of is exactly the one nobody wants it guessing
about.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# `docker images` renders "2026-08-31 10:22:33 +0200 CEST"; the trailing zone
# abbreviation is not parseable and not needed, the numeric offset is.
CREATED_AT = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})")

# Repositories whose per-version tags are disposable, and how many of the
# newest to keep. Moving tags (:latest, :stable, and :rc -- the newest release
# build, which release:build-images pushes instead of :latest) are never
# candidates.
#: Prefix of the old shared merge-request build images; the release prefix comes from DOCKER_USER.
SHARED_CI_PREFIX = "muma-ci/"
MOVING_TAGS = frozenset({"latest", "stable", "rc"})
ANDROID_CI_REPO = "music-management/android-ci"
TEST_STACK_PREFIX = "muma-test-"
# Per-job merge-request build images (`muma-ci-<job-id>/muma-base`, ...). Their
# own build script deletes them; anything still here outlives the job that made
# it, so age decides and no tag is spared.
THROWAWAY_BUILD_PREFIX = "muma-ci-"


@dataclass(frozen=True)
class Image:
    ref: str
    repository: str
    tag: str
    created: datetime
    image_id: str


def parse_listing(lines: list[str]) -> list[Image]:
    """Turn `docker images` output into Images, skipping what we cannot read.

    Dangling images (`<none>:<none>`) are dropped here rather than handled:
    `docker image prune` removes those, and it is a safer tool for it than a
    name-based rule.
    """
    images: list[Image] = []
    for line in lines:
        line = line.rstrip("\n")
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        ref, created_raw = parts[0], parts[1]
        image_id = parts[2] if len(parts) > 2 else ""
        if "<none>" in ref:
            continue
        repository, _, tag = ref.rpartition(":")
        if not repository:
            continue
        match = CREATED_AT.match(created_raw.strip())
        if not match:
            continue
        created = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S %z")
        images.append(Image(ref, repository, tag, created, image_id))
    return images


def _newest_first(images: list[Image]) -> list[Image]:
    return sorted(images, key=lambda i: i.created, reverse=True)


def select_removals(
    images: list[Image],
    *,
    now: datetime,
    keep_versions: int,
    keep_android: int,
    test_stack_min_age_hours: int,
    docker_user: str,
) -> list[Image]:
    """The images that may be removed, oldest first.

    Oldest first matters: the script stops caring once it is back under the
    threshold, and the oldest tag is both the least likely to be wanted and
    the most likely to hold layers nothing else shares.

    `docker_user` is the registry user the release images are pushed under; its repositories
    are the ones whose old version tags may go. Empty means none are selected.
    """
    # An empty docker_user leaves the release images alone: only the shared CI prefix is versioned.
    versioned_prefixes = (f"{docker_user}/", SHARED_CI_PREFIX) if docker_user else (SHARED_CI_PREFIX,)
    doomed: list[Image] = []
    by_repository: dict[str, list[Image]] = {}
    for image in images:
        by_repository.setdefault(image.repository, []).append(image)

    for repository, group in by_repository.items():
        if repository.startswith((TEST_STACK_PREFIX, THROWAWAY_BUILD_PREFIX)):
            # A per-job image, from a test stack or a merge-request build.
            # Age, not count: no job reuses another job's namespace, so a
            # per-repository count would keep every one of them forever. A
            # running pipeline's images are minutes old, and `docker rmi`
            # would refuse them anyway because their containers exist -- but
            # not asking is better than being refused.
            cutoff = now - timedelta(hours=test_stack_min_age_hours)
            doomed.extend(image for image in group if image.created < cutoff)
            continue

        if repository == ANDROID_CI_REPO:
            doomed.extend(_newest_first(group)[keep_android:])
            continue

        if repository.startswith(versioned_prefixes):
            versioned = [image for image in group if image.tag not in MOVING_TAGS]
            doomed.extend(_newest_first(versioned)[keep_versions:])
            continue

        # Anything else: not ours to delete.

    return sorted(doomed, key=lambda i: i.created)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-versions", type=int, default=3)
    parser.add_argument("--keep-android", type=int, default=2)
    parser.add_argument("--test-stack-min-age-hours", type=int, default=2)
    parser.add_argument(
        "--docker-user",
        default=os.environ.get("DOCKER_USER", ""),
        help="Registry user of the release images (default: $DOCKER_USER). Without it the release images are left alone.",
    )
    parser.add_argument(
        "--now",
        default=None,
        help="ISO timestamp to treat as the current time (tests only).",
    )
    args = parser.parse_args()
    if not args.docker_user:
        print("WARNING: DOCKER_USER is not set; release image tags are not selected.", file=sys.stderr)

    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    images = parse_listing(sys.stdin.readlines())
    for image in select_removals(
        images,
        now=now,
        keep_versions=args.keep_versions,
        keep_android=args.keep_android,
        test_stack_min_age_hours=args.test_stack_min_age_hours,
        docker_user=args.docker_user,
    ):
        print(image.ref)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
