"""Every relative Markdown link in the top-level docs and `docs/` must point at a file that exists.

A link to a deleted or moved document fails silently for a reader, so this test reads the
Markdown, skips code fences, and checks the target path of each inline link, image and
reference definition. `http(s)`, `mailto` and pure anchors are ignored; for `file#anchor` only the
file is checked.
"""

import re
from pathlib import Path
from urllib.parse import unquote

import pytest

from tests.ci.conftest import REPO_ROOT

# Applied migrate_*.sql files are immutable: the deploy re-runs a migration whose sha256 changed,
# and re-running migrate_v7 re-queues the whole Youtube tree for the tagger. Their comments may
# keep references to removed docs, so no link or `superpowers/` expectation covers them.
TOP_LEVEL = ("AGENTS.md", "README.md", "CONTRIBUTING.md", "SECURITY.md")

# Broken links in files that other merge requests rewrite right now. Each entry is
# (source file, link target as written) and is removed by the follow-up named in its comment.
# An entry that no longer matches a broken link fails the test, so stale entries cannot stay.
ALLOWED_BROKEN = {
    # removed by step 7c-2 (docs/release-management.md moves to muma-ops)
    ("docs/release-management.md", "branch-hygiene.md"),
    # removed by step 7c-2 (docs/deployment.md is split into docs/self-hosting.md)
    (
        "docs/deployment.md",
        # Written in two pieces so a grep for the old plans folder stays empty once 7c-2 lands.
        "superpowers" + "/specs/2026-08-02-daily-db-backups-design.md",
    ),
}

_FENCE = re.compile(r"^\s*(```|~~~)")
_INLINE = re.compile(r"!?\[[^\]]*\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
_REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)")


def _doc_files() -> list[Path]:
    """Return the Markdown files whose links are checked."""
    files = [REPO_ROOT / name for name in TOP_LEVEL if (REPO_ROOT / name).exists()]
    files += sorted((REPO_ROOT / "docs").rglob("*.md"))
    return files


def _targets(text: str):
    """Yield the link targets in a Markdown text, leaving out fenced code blocks and code spans."""
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = re.sub(r"`[^`]*`(?!\])", "", line)
        for match in _INLINE.finditer(line):
            yield match.group(1)
        reference = _REFERENCE.match(line)
        if reference:
            yield reference.group(1)


def _is_checked(target: str) -> bool:
    """Tell whether a target is a relative file path."""
    return not (re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#") or target.startswith("//"))


def find_broken_links() -> set[tuple[str, str]]:
    """Return (source file, target as written) for every broken relative link."""
    broken = set()
    for path in _doc_files():
        text = path.read_text(encoding="utf-8")
        for raw in _targets(text):
            target = raw.strip("<>")
            if not _is_checked(target):
                continue
            file_part = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not file_part:
                continue
            base = REPO_ROOT if file_part.startswith("/") else path.parent
            resolved = (base / file_part.lstrip("/")).resolve()
            if not resolved.exists():
                broken.add((path.relative_to(REPO_ROOT).as_posix(), target))
    return broken


def test_no_broken_relative_links():
    """A relative link whose target is gone fails, unless it is on the allowlist."""
    unexpected = sorted(find_broken_links() - ALLOWED_BROKEN)
    assert not unexpected, "Broken relative links:\n" + "\n".join(
        f"  {source}: {target}" for source, target in unexpected
    )


def test_allowlist_has_no_stale_entries():
    """An allowlist entry whose link works again must be deleted."""
    stale = sorted(ALLOWED_BROKEN - find_broken_links())
    assert not stale, f"Remove these from ALLOWED_BROKEN: {stale}"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("[a](x.md)", ["x.md"]),
        ("[a](x.md#frag \"title\")", ["x.md#frag"]),
        ("`[a](x.md)`", []),
        ("```\n[a](x.md)\n```", []),
        ("[a]: ../y.md", ["../y.md"]),
        ("![i](img.png)", ["img.png"]),
    ],
)
def test_target_extraction(text, expected):
    """The extractor finds links and skips code."""
    assert list(_targets(text)) == expected
