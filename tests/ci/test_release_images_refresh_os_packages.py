"""The release build has to actually run the OS upgrade its Dockerfiles ask for.

Four Dockerfiles upgrade the base image's packages (`apt-get upgrade` /
`apk upgrade`) so a rebuild reaches the distribution's security pocket. That
only works when the layer is rebuilt. `scripts/ci/build-and-push-images.sh`
builds with the runner's layer cache, and an unchanged Dockerfile hands back
the layer from the first build: the LMS image deployed with 0.82.1 on
2026-09-28 carried an `apk upgrade` layer created on 2026-09-17, and with it
libexpat 2.8.4-r0 (CVE-2026-93990, HIGH) while Alpine already shipped 2.8.5-r0.
`security:dependency-audit` caught it; nothing in the build would have.

The fix is a build argument that changes every day, declared right above each
upgrade step, so exactly that layer and what follows it are rebuilt. These
tests hold both halves together: a Dockerfile that upgrades declares the
argument before the upgrade, and the build script passes it for that file.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "ci" / "build-and-push-images.sh"
UPGRADE = re.compile(r"^RUN\s+(apt-get update && apt-get upgrade|apk upgrade)", re.MULTILINE)


def dockerfiles_the_build_script_builds() -> dict[str, str]:
    """Map each Dockerfile the release build uses to the flags of its `docker build`."""
    script = BUILD_SCRIPT.read_text()
    builds = re.findall(r"docker build \\\n((?:    .*\\\n)*?)    -f (\S+) \.", script)
    assert builds, "no docker build invocations found in the build script"
    return {dockerfile: flags for flags, dockerfile in builds}


def stages(text: str) -> list[str]:
    """Split a Dockerfile into its stages; an ARG only lives inside its own stage."""
    return re.split(r"^FROM\s", text, flags=re.MULTILINE)[1:]


def test_every_upgrade_step_follows_a_security_refresh_argument():
    for dockerfile in dockerfiles_the_build_script_builds():
        for number, stage in enumerate(stages((REPO_ROOT / dockerfile).read_text()), start=1):
            upgrade = UPGRADE.search(stage)
            if not upgrade:
                continue
            argument = re.search(r"^ARG SECURITY_REFRESH\b", stage, re.MULTILINE)
            assert argument and argument.start() < upgrade.start(), (
                f"{dockerfile} stage {number} upgrades OS packages without ARG SECURITY_REFRESH "
                f"above it, so the layer cache can hand back an old upgrade"
            )


def test_the_build_script_passes_a_daily_refresh_to_every_upgrading_dockerfile():
    script = BUILD_SCRIPT.read_text()
    assert re.search(r'^SECURITY_REFRESH="\$\(date -u \+%Y-%m-%d\)"$', script, re.MULTILINE), (
        "SECURITY_REFRESH has to change every day, or the cached upgrade layer is reused"
    )
    for dockerfile, flags in dockerfiles_the_build_script_builds().items():
        if not UPGRADE.search((REPO_ROOT / dockerfile).read_text()):
            continue
        assert '--build-arg SECURITY_REFRESH="${SECURITY_REFRESH}"' in flags, (
            f"{dockerfile} upgrades OS packages but is built without SECURITY_REFRESH"
        )
        assert "--pull" in flags, f"{dockerfile} is built without --pull, so its base tag can be stale"


def test_images_built_on_muma_base_do_not_pull_it():
    """They name the muma-base tag this same run just built; --pull would fetch
    the registry's copy instead (or fail on a tag not pushed in no-push mode)."""
    for dockerfile, flags in dockerfiles_the_build_script_builds().items():
        text = (REPO_ROOT / dockerfile).read_text()
        if re.search(r"^FROM .*muma-base", text, re.MULTILINE):
            assert "--pull" not in flags, f"{dockerfile} pulls muma-base instead of using this run's build"
