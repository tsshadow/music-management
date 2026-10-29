#!/usr/bin/env python3
"""Decide which Docker images the production host may delete after a deploy.

Every release and hotfix deploy pulls a fresh set of images and nothing ever
removed the previous ones: on 2026-09-26 the host held 377 images, 67 GB of
which 61 GB was reclaimable, and its root disk was 95% full (bug report 094).
scripts/ci/prune-prod-images.sh does the I/O -- it lists the host's images and
containers over ssh and runs `docker rmi` on what this module returns. The
decision itself is a pure function over that listing, so what is allowed to
disappear from production is testable without a Docker daemon.

Input (stdin), one record per line, tab-separated:

    container<TAB><image id>          every container, running or stopped
    image<TAB><image id><TAB><created>  every image, build time in RFC 3339
    tag<TAB><image id><TAB><repository:tag>
    digest<TAB><image id><TAB><repository@sha256:...>

prune-prod-images.sh produces the last three with one `docker image inspect`
template rather than from `docker image ls`, whose REPOSITORY column for an
image that lost its tag depends on the Docker version and image store.

Output (stdout): one reference per line to pass to `docker rmi` without -f --
`repository:tag` for each tag of a tagged image, the image id for an untagged
one. What is kept, and why, goes to stderr.

Production pulls `:latest`, so a previous release is usually not a version tag
on the host but an image whose tag moved on: it keeps its repository only in its
RepoDigests (`<user>/music-manager@sha256:...`). That is
why the rollback set is chosen by build time, not by tag. An image is kept when
any of these holds:

* a container uses it -- running or stopped. A stopped one-shot
  (soundcloud-fetcher, genre-processor) must still be restartable, and
  `docker rmi` without -f refuses anyway;
* it is one of the ``keep`` most recently built images of its repository that
  no container uses: the previous releases, which the IMAGE_TAG rollback lever
  (docs/deployment.md#rollback) redeploys. Pulling a tag whose digest is still
  on the host downloads nothing, so a rollback stays fast and works while
  Docker Hub does not;
* it carries a moving tag (``latest``, ``stable``, ``rc``): the db-backup
  service of the backup compose file runs ``muma-tools:latest`` with
  ``run --rm`` once a night, so no container holds that image between runs.

Everything else goes: older releases, dangling layers without a repository,
images of services that no longer exist.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime

MOVING_TAGS = frozenset({"latest", "stable", "rc"})
NONE = "<none>"
# `docker image inspect` renders .Created as RFC 3339 with nanoseconds,
# "2026-09-25T10:22:33.123456789Z"; the fraction is dropped, it orders nothing.
CREATED = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$")


@dataclass
class Image:
    """One image id on the host and every repository:tag that points at it."""

    image_id: str
    created: datetime | None = None
    refs: list[tuple[str, str]] = field(default_factory=list)

    @property
    def repositories(self) -> set[str]:
        """The repositories this image belongs to (from a tag or from a digest)."""
        return {repo for repo, _ in self.refs if repo != NONE}

    @property
    def tagged_refs(self) -> list[str]:
        """The `repository:tag` references, without docker's `<none>` placeholders."""
        return [f"{repo}:{tag}" for repo, tag in self.refs if repo != NONE and tag != NONE]

    def name(self) -> str:
        """A readable name for the log: its tags, else its repository, else its short id."""
        if self.tagged_refs:
            return ", ".join(self.tagged_refs)
        short = self.image_id.removeprefix("sha256:")[:12]
        repos = sorted(self.repositories)
        return f"{repos[0]}@{short}" if repos else short


def parse_created(text: str) -> datetime | None:
    """Parse an image's RFC 3339 build time, or None when it is not in that format."""
    match = CREATED.match(text.strip())
    if not match:
        return None
    zone = "+00:00" if match.group(2) == "Z" else match.group(2)
    return datetime.fromisoformat(match.group(1) + zone)


def split_tag(ref: str) -> tuple[str, str] | None:
    """Split `repository:tag` (the repository may carry a registry port), or None."""
    repo, sep, tag = ref.rpartition(":")
    if not sep or not repo or "/" in tag:
        return None
    return repo, tag


def parse(lines: list[str]) -> tuple[dict[str, Image], set[str]]:
    """Read the listing into images by id and the set of image ids containers use."""
    images: dict[str, Image] = {}
    in_use: set[str] = set()
    for raw in lines:
        parts = raw.rstrip("\n").split("\t")
        if len(parts) < 2 or not parts[1]:
            continue
        kind, image_id, value = parts[0], parts[1], parts[2] if len(parts) > 2 else ""
        if kind == "container":
            in_use.add(image_id)
            continue
        if kind not in {"image", "tag", "digest"}:
            continue
        image = images.setdefault(image_id, Image(image_id))
        if kind == "image":
            image.created = parse_created(value)
        elif kind == "tag" and (pair := split_tag(value)):
            image.refs.append(pair)
        elif kind == "digest" and "@" in value:
            image.refs.append((value.split("@", 1)[0], NONE))
    return images, in_use


def rollback_set(images: dict[str, Image], in_use: set[str], keep: int) -> set[str]:
    """Ids of the KEEP most recently built unused images of every repository.

    An image without a parseable build time sorts as the oldest: when in doubt
    it is the one given up, never a newer one.
    """
    by_repo: dict[str, list[Image]] = {}
    for image in images.values():
        if image.image_id in in_use:
            continue
        for repo in image.repositories:
            by_repo.setdefault(repo, []).append(image)
    kept: set[str] = set()
    for candidates in by_repo.values():
        candidates.sort(key=lambda i: (i.created is not None, i.created or datetime.min), reverse=True)
        kept.update(image.image_id for image in candidates[:keep])
    return kept


def plan(lines: list[str], keep: int) -> tuple[list[str], list[str]]:
    """Return (references to remove, human-readable lines about what is kept)."""
    images, in_use = parse(lines)
    rollback = rollback_set(images, in_use, keep)
    removals: list[str] = []
    kept: list[str] = []
    for image_id in sorted(images):
        image = images[image_id]
        if image_id in in_use:
            kept.append(f"{image.name()} (used by a container)")
        elif image_id in rollback:
            kept.append(f"{image.name()} (rollback: one of the {keep} newest unused of its repository)")
        elif any(tag in MOVING_TAGS for _, tag in image.refs):
            kept.append(f"{image.name()} (moving tag)")
        else:
            removals.extend(image.tagged_refs or [image_id])
    return removals, kept


def main(argv: list[str] | None = None) -> int:
    """Read the listing on stdin, print the references to remove on stdout."""
    parser = argparse.ArgumentParser(description="Plan which production images to delete.")
    parser.add_argument(
        "--keep", type=int, default=3, help="previous images to keep per repository for a rollback (default 3)"
    )
    args = parser.parse_args(argv)
    if args.keep < 1:
        parser.error("--keep must be at least 1: IMAGE_TAG needs a previous release to roll back to")
    removals, kept = plan(sys.stdin.readlines(), args.keep)
    for line in kept:
        print(f"keep    {line}", file=sys.stderr)
    for ref in removals:
        print(ref)
    print(f"{len(kept)} image(s) kept, {len(removals)} reference(s) to remove", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
