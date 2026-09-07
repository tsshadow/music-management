"""Which images the nightly refresh has to rebuild.

`muma:refresh-downloader` rebuilds `muma-base` with `--no-cache` every night and
pushes it, so that build picks up whatever Debian-Security published that day.
Every image built FROM that base keeps whatever its own last build inherited --
which is the release build, days or weeks earlier.

That gap is not theoretical. On 2026-09-07 the audit reported
`CVE-2026-33164` (libde265, HIGH, fixed upstream) in `muma-telegram:latest` and
`muma-importer:latest` while `muma-base:latest` and `muma-downloader:latest`,
rebuilt by that night's refresh, were clean. There was no pin to bump and no
Dockerfile to fix: the two images were simply older than the base they claim to
be built on.

So the rule these tests hold is a list nobody has to maintain: whatever is built
FROM muma-base is refreshed with it.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKER_DIR = REPO_ROOT / "docker"
REFRESH_SCRIPT = REPO_ROOT / "scripts" / "ci" / "refresh-downloader-image.sh"

BASE_DOCKERFILE = "Dockerfile.base"


def dockerfiles_built_on_the_base() -> set[str]:
    """Every Dockerfile whose FROM names muma-base, plus the base itself."""
    derived = {BASE_DOCKERFILE}
    for path in DOCKER_DIR.glob("Dockerfile.*"):
        if re.search(r"^FROM .*muma-base", path.read_text(), re.MULTILINE):
            derived.add(path.name)
    return derived


def dockerfiles_the_refresh_builds() -> set[str]:
    return set(re.findall(r"-f docker/(Dockerfile\.\S+)", REFRESH_SCRIPT.read_text()))


def test_every_image_built_on_the_base_is_rebuilt_with_it():
    missing = dockerfiles_built_on_the_base() - dockerfiles_the_refresh_builds()
    assert missing == set(), (
        f"these are built FROM muma-base but not rebuilt when it is refreshed, so they keep "
        f"the OS packages of their last release build: {sorted(missing)}"
    )


def test_the_refresh_builds_nothing_that_is_not_part_of_the_base_family():
    """The inverse: an image with its own FROM does not get a security update
    out of this job, and rebuilding it here would push a `:latest` from master
    that no release produced."""
    extra = dockerfiles_the_refresh_builds() - dockerfiles_built_on_the_base()
    assert extra == set(), f"the refresh builds images that are not part of the muma-base family: {sorted(extra)}"


def test_each_refreshed_image_is_built_without_the_layer_cache():
    """A cached `apt-get upgrade` layer reinstalls nothing: the Dockerfile text
    has not changed, so Docker reuses the layer from the day the package was
    still vulnerable. Without --no-cache this whole job is a no-op that looks
    like it worked."""
    script = REFRESH_SCRIPT.read_text()
    builds = re.findall(r"docker build(.*?)-f docker/(Dockerfile\.\S+)", script, re.DOTALL)
    assert builds, "no docker build invocations found in the refresh script"
    cached = [dockerfile for flags, dockerfile in builds if "--no-cache" not in flags]
    assert cached == [], f"built with the layer cache, so a security update can be silently skipped: {cached}"


def test_each_refreshed_image_pushes_latest_and_a_dated_tag():
    """`:latest` is what production pulls; the dated tag is the only record of
    which refresh produced it. The `:${VERSION}` tag is deliberately not pushed
    -- it names a release and has to keep meaning what that release shipped."""
    script = REFRESH_SCRIPT.read_text()
    pushed = set(re.findall(r"docker push \"\$\{DOCKER_USER\}/\$\{(IMAGE_\w+)\}:(\S+?)\"", script))
    images = {image for image, _ in pushed}
    assert images, "no docker push invocations found in the refresh script"
    for image in sorted(images):
        assert (image, "latest") in pushed, f"{image} is built but its :latest is never pushed"
        assert (image, "${REFRESH_TAG}") in pushed, f"{image} is pushed without the dated refresh tag"
        assert (image, "${VERSION}") not in pushed, f"{image} overwrites a release tag"
