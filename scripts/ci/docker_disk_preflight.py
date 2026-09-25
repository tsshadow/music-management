#!/usr/bin/env python3
"""Fail a job early, and legibly, when the Docker data root is too full for it.

The emulator in mobile:smoke creates a ~7.4GB userdata partition inside its
container, i.e. on the Docker data root. On 2026-09-25 the workstation runner
had 3.7GB left there and the job died on

    FATAL | Not enough space to create userdata partition.

six minutes in, which reads like an emulator problem and skipped the release
deploy behind it (docs/bug-reports/073). This check costs one statvfs call and
names the actual fix instead.

Usage:
    docker_disk_preflight.py --path /var/lib/docker --min-free-gb 12 --job mobile:smoke

Exit codes: 0 enough space (or the path cannot be inspected from here),
1 not enough space.
"""

import argparse
import shutil
import sys
from pathlib import Path

GIB = 1024**3

# The fixes, most targeted first. The janitor carries its own safety rules
# (age-filtered cache prune, keeps the newest release tags); the bare prune is
# what freed 62GB by hand in the incident and is age-filtered for the same
# reason: an unfiltered prune empties the ccache server:unit depends on.
FIX_HINT = (
    "Fix on that runner: ./scripts/ci/disk-janitor.sh --force "
    "(or, by hand: docker builder prune -f --filter until=72h). "
    "Never an unfiltered prune -- see scripts/ci/systemd/README.md."
)


def evaluate(free_bytes: int, total_bytes: int, min_free_bytes: int, path: str, job: str) -> tuple[bool, str]:
    """Decide whether `free_bytes` on `path` is enough for `job`.

    Pure so the decision and its wording can be tested without a disk.
    Returns (ok, message); the message is meant to be printed either way.
    """
    free_gb = free_bytes / GIB
    need_gb = min_free_bytes / GIB
    used_pct = 100 * (total_bytes - free_bytes) / total_bytes if total_bytes else 0.0
    if free_bytes >= min_free_bytes:
        return True, (f"Disk pre-flight OK for {job}: {free_gb:.1f}GB free on {path} (need {need_gb:.1f}GB).")
    return False, (
        f"Disk pre-flight FAILED for {job}: only {free_gb:.1f}GB free on {path} "
        f"({used_pct:.0f}% used), this job needs at least {need_gb:.1f}GB. "
        f"Failing now instead of letting the job die on a cryptic out-of-space error. {FIX_HINT}"
    )


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, measure the path and print the verdict."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", required=True, help="Docker data root (docker info .DockerRootDir)")
    parser.add_argument("--min-free-gb", type=float, required=True)
    parser.add_argument("--job", default="this job")
    args = parser.parse_args(argv)

    path = Path(args.path)
    try:
        usage = shutil.disk_usage(path)
    except OSError as exc:
        # A remote daemon or a data root this user cannot stat: no answer is
        # better than a false failure. The job still runs and fails on its own.
        print(f"Disk pre-flight skipped for {args.job}: cannot inspect {path} ({exc}).")
        return 0

    ok, message = evaluate(usage.free, usage.total, int(args.min_free_gb * GIB), str(path), args.job)
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
