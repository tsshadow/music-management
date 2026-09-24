"""Every input an image build pulls from the network is pinned.

Audit item C18 (2026-09-23) found the builds pulling whatever was newest on the
day: yt-dlp from `releases/latest`, deno from `releases/latest`, ffmpeg, Wt, stb
and TagLib tarballs without a checksum, and `phpmyadmin:latest`,
`jlesage/firefox:latest` and a bare `willfarrell/autoheal` in the compose files.
Two builds of the same commit were not known to contain the same software, and a
tampered or regenerated tarball would have been compiled in without a word. See
docs/bug-reports/067-image-builds-pull-unpinned-inputs.md.

These tests hold the line from here on: a download in a Dockerfile checks a
sha256, an image reference names a version (or, for an image without version
tags, a digest), and the three yt-dlp pins agree so Renovate can move them as one.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DOCKERFILES = sorted(
    [*REPO_ROOT.glob("docker/Dockerfile*"), *REPO_ROOT.glob("services/**/Dockerfile*")],
)
COMPOSE_FILES = sorted(
    [*REPO_ROOT.glob("docker/*compose*.yml"), *REPO_ROOT.glob("services/*/docker-compose*.yml")],
)
REFRESH_SCRIPT = REPO_ROOT / "scripts" / "ci" / "refresh-downloader-image.sh"


def _no_node_modules(paths: list[Path]) -> list[Path]:
    """Drop vendored files: a package's own Dockerfile is not ours to pin."""
    return [p for p in paths if "node_modules" not in p.parts]


def instructions(dockerfile: Path) -> list[str]:
    """The Dockerfile's instructions, continuation lines joined, comments dropped."""
    joined: list[str] = []
    current = ""
    for raw in dockerfile.read_text().splitlines():
        line = raw.strip()
        if line.startswith("#") or not line:
            continue
        if line.endswith("\\"):
            current += line[:-1] + " "
            continue
        joined.append(current + line)
        current = ""
    if current:
        joined.append(current)
    return joined


def test_the_globs_find_the_files_this_audit_was_about():
    """A test that silently checks nothing passes forever."""
    names = {p.name for p in DOCKERFILES}
    assert {"Dockerfile.downloader", "Dockerfile.tools", "Dockerfile-release"} <= names
    assert any(p.name == "docker-compose.yml" and p.parent.name == "music-management-server" for p in COMPOSE_FILES)


def test_every_download_in_a_dockerfile_is_checked_against_a_sha256():
    """A curl, wget or ADD of a URL is followed by `sha256sum -c` in the same RUN."""
    unchecked = []
    for dockerfile in _no_node_modules(DOCKERFILES):
        for instruction in instructions(dockerfile):
            if not instruction.startswith(("RUN", "ADD")):
                continue
            if not re.search(r"\b(curl|wget)\b[^&;|]*https?://|^ADD\s+https?://", instruction):
                continue
            if "sha256sum -c" not in instruction and "--checksum=sha256:" not in instruction:
                unchecked.append(f"{dockerfile.relative_to(REPO_ROOT)}: {instruction[:120]}")
    assert not unchecked, "downloads without a sha256 check:\n" + "\n".join(unchecked)


def test_no_download_url_points_at_a_moving_latest():
    """`releases/latest` resolves to a different file after every upstream release."""
    moving = []
    for dockerfile in _no_node_modules(DOCKERFILES):
        for instruction in instructions(dockerfile):
            if "/releases/latest" in instruction:
                moving.append(f"{dockerfile.relative_to(REPO_ROOT)}: {instruction[:120]}")
    assert not moving, "downloads from a releases/latest URL:\n" + "\n".join(moving)


def _is_pinned(image: str) -> bool:
    """A reference built from our own variables is pinned by the release; anything
    else needs a tag that is not `latest`, or a digest."""
    if "${" in image:
        return True
    if "@sha256:" in image:
        return True
    name = image.rsplit("/", 1)[-1]
    if ":" not in name:
        return False
    tag = name.split(":", 1)[1]
    return tag not in {"latest", "alpine", "stable", "mainline"}


def test_every_base_image_names_a_version():
    """A FROM on `latest` or a bare tag changes under a rebuild of the same commit."""
    floating = []
    for dockerfile in _no_node_modules(DOCKERFILES):
        stages = set()
        for instruction in instructions(dockerfile):
            match = re.match(r"FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", instruction, re.IGNORECASE)
            if not match:
                continue
            image, stage = match.group(1), match.group(2)
            if image not in stages and not _is_pinned(image):
                floating.append(f"{dockerfile.relative_to(REPO_ROOT)}: {image}")
            if stage:
                stages.add(stage)
    assert not floating, "FROM without a version:\n" + "\n".join(floating)


def test_every_compose_image_names_a_version():
    """Same for the images the compose files run."""
    floating = []
    for compose in _no_node_modules(COMPOSE_FILES):
        for line in compose.read_text().splitlines():
            match = re.match(r"\s*image:\s*[\"']?([^\"'\s#]+)", line)
            if match and not _is_pinned(match.group(1)):
                floating.append(f"{compose.relative_to(REPO_ROOT)}: {match.group(1)}")
    assert not floating, "compose images without a version:\n" + "\n".join(floating)


def _yt_dlp_pins() -> dict[str, str]:
    """The yt-dlp version in each of the three places it is pinned, "" where missing."""
    pins = {}
    requirement = re.search(r"^yt-dlp==(\S+)", (REPO_ROOT / "requirements.txt").read_text(), re.MULTILINE)
    pins["requirements.txt"] = requirement.group(1) if requirement else ""
    for name in ("Dockerfile.downloader", "Dockerfile.tools"):
        text = (REPO_ROOT / "docker" / name).read_text()
        arg = re.search(r"^# renovate: datasource=pypi depName=yt-dlp\nARG YT_DLP_VERSION=(\S+)$", text, re.MULTILINE)
        pins[name] = arg.group(1) if arg else ""
    return pins


def test_yt_dlp_is_pinned_to_one_version_everywhere():
    """Renovate's yt-dlp group moves all three at once; a hand edit that moves one
    would leave the downloader and the tools image on different extractors."""
    pins = _yt_dlp_pins()
    assert all(pins.values()), f"a yt-dlp pin (or its `# renovate:` marker) is missing: {pins}"
    assert len(set(pins.values())) == 1, f"yt-dlp pins disagree: {pins}"


def test_the_images_install_the_pinned_yt_dlp():
    """The ARG is only a pin if the pip install actually uses it."""
    for name in ("Dockerfile.downloader", "Dockerfile.tools"):
        text = (REPO_ROOT / "docker" / name).read_text()
        assert re.search(r'pip install [^\n]*"yt-dlp(\[[^\]]*\])?==\$\{YT_DLP_VERSION\}"', text), name


def test_the_weekly_refresh_builds_the_pin_from_develop():
    """Pinning yt-dlp must not undo what muma:refresh-downloader is for: the job
    builds master, so it has to be told the version Renovate landed on develop."""
    script = REFRESH_SCRIPT.read_text()
    assert "git show FETCH_HEAD:requirements.txt" in script
    build = re.search(r"docker build(.*?)-f docker/Dockerfile\.downloader", script, re.DOTALL)
    assert build, "the refresh no longer builds the downloader"
    assert '--build-arg YT_DLP_VERSION="${YT_DLP_VERSION}"' in build.group(1)
