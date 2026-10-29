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

TOP_LEVEL = ("AGENTS.md", "README.md", "CONTRIBUTING.md", "SECURITY.md")

# migrate_*.sql are not Markdown and are not read here. Applied migrations must not change: the
# deploy re-runs a migration whose sha256 changed, so they keep their old comments.

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

_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)")

# Trees that are not ours or are build output; their Markdown is not checked.
EXCLUDED_PREFIXES = (
    # Upstream LMS fork: its docs link into the upstream repository layout (see FORK.md).
    "services/music-management-server/",
    # Dependencies and build output, generated and full of upstream links.
    "node_modules/",
)
EXCLUDED_PARTS = ("node_modules", "build", "dist", ".gradle")


def _doc_files() -> list[Path]:
    """Return the Markdown files whose links are checked."""
    files = [REPO_ROOT / name for name in TOP_LEVEL if (REPO_ROOT / name).exists()]
    candidates = sorted((REPO_ROOT / "docs").rglob("*.md"))
    candidates += sorted((REPO_ROOT / "services").rglob("*.md"))
    candidates += sorted((REPO_ROOT / "scripts").rglob("*.md"))
    for path in candidates:
        rel = path.relative_to(REPO_ROOT)
        if rel.as_posix().startswith(EXCLUDED_PREFIXES):
            continue
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        files.append(path)
    return files


def _inline_targets(line: str):
    """Yield the targets of inline links and images in one line, nested ones included."""
    i = 0
    while True:
        i = line.find("](", i)
        if i < 0:
            return
        j = i + 2
        while j < len(line) and line[j] == " ":
            j += 1
        if j < len(line) and line[j] == "<":
            end = line.find(">", j)
            if end < 0:
                i += 2
                continue
            yield line[j + 1 : end]
            i = end
            continue
        depth = 0
        k = j
        while k < len(line):
            c = line[k]
            if c == "(":
                depth += 1
            elif c == ")":
                if depth == 0:
                    break
                depth -= 1
            elif c in " \t" and depth == 0:
                break
            k += 1
        yield line[j:k]
        i = k


def _targets(text: str):
    """Yield the link targets in a Markdown text, leaving out fenced code blocks and code spans."""
    fence = None
    for line in text.splitlines():
        marker = _FENCE.match(line)
        if fence is None and marker:
            fence = marker.group(1)
            continue
        if fence is not None:
            if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = None
            continue
        line = re.sub(r"`[^`]*`(?!\])", "", line)
        yield from _inline_targets(line)
        reference = _REFERENCE.match(line)
        if reference:
            yield reference.group(1).strip("<>")


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
        ("[a](dir/f(1).md)", ["dir/f(1).md"]),
        ("[![x](a.png)](b.md)", ["a.png", "b.md"]),
        ("[a](<my file.md>)", ["my file.md"]),
        ("[a](my%20file.md)", ["my%20file.md"]),
        ('[id]: path.md "title"', ["path.md"]),
        ("[id]: <my path.md> 'title'", ["my path.md"]),
        ("~~~\n```\n[a](x.md)\n~~~\n[b](y.md)", ["y.md"]),
        ("```\n~~~\n[a](x.md)\n```\n[b](y.md)", ["y.md"]),
        ("`[a](x.md)`", []),
        ("```\n[a](x.md)\n```", []),
        ("[a]: ../y.md", ["../y.md"]),
        ("![i](img.png)", ["img.png"]),
    ],
)
def test_target_extraction(text, expected):
    """The extractor finds links and skips code."""
    assert list(_targets(text)) == expected
