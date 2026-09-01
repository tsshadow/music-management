"""Compare a clang-tidy log against the accepted-findings baseline.

Same shape as scripts/ci/sast_baseline.py, and the same reasoning: identity is
the check, the file and the message text, never the line number -- line numbers
move whenever anything above them changes, which would invalidate the whole
baseline on an unrelated edit.

One deliberate difference from the SAST helper. That one regenerates its
per-rule comment blocks from a dict in the source, so rewriting the baseline
silently replaces any rationale someone typed in the file with "NOT YET
AUDITED" -- which is exactly what happened on 2026-09-01 and cost an audit note.
This one reads the existing file first and carries its comments over.

Used by scripts/test/muma-server-tidy.sh; not a test module.
"""

from __future__ import annotations

import hashlib
import re
import sys
from collections import Counter, defaultdict

HEADER = """\
# clang-tidy findings this project has consciously accepted for now.
#
# Read by scripts/test/muma-server-tidy.sh. Anything listed here is excluded;
# anything not listed fails the job. An entry is per *finding*, not per check,
# so a new site that trips an already-accepted check still fails.
#
# Format: <key> x<count>  # <check> <path>
# The key hashes the check, the file and the message. Line numbers are not part
# of it -- they move on any edit above them -- but the count is, so a second
# identical finding in the same file is new and fails.
#
# Regenerate after auditing new findings:
#   ./scripts/test/muma-server-tidy.sh --write-baseline
#
# Comments you write under a `# --- check ---` header are preserved when the
# file is regenerated. Write down why something is accepted; an unexplained
# entry is indistinguishable from one nobody looked at.
"""

FINDING = re.compile(
    r"^(?P<path>[^:\n]+):(?P<line>\d+):(?P<col>\d+): "
    r"(?:warning|error): (?P<message>.*?) \[(?P<checks>[a-z0-9,.-]+)\]$"
)

# Messages embed identifiers and numbers that differ per site; that is wanted,
# it is what makes two findings distinct. But some carry a value that changes
# without the code meaning anything different, so normalise those away.
NORMALISE = [
    (re.compile(r"\b\d+ is a magic number\b"), "<n> is a magic number"),
]


def normalise(message: str) -> str:
    for pattern, replacement in NORMALISE:
        message = pattern.sub(replacement, message)
    return message


def parse(log_path: str, strip_prefix: str) -> list[dict]:
    """Findings from a clang-tidy log, de-duplicated.

    A header included by many translation units is reported once per unit, so
    the same finding appears dozens of times in one run; the file/line/check
    triple is what makes it one finding.
    """
    seen: set[tuple[str, str, str, str]] = set()
    findings: list[dict] = []
    with open(log_path, encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            match = FINDING.match(raw.rstrip("\n"))
            if not match:
                continue
            path = match.group("path")
            if path.startswith(strip_prefix):
                path = path[len(strip_prefix) :].lstrip("/")
            # Only our own sources: system and dependency headers arrive here
            # too and are nothing this repository can fix.
            if not path.startswith("src/"):
                continue
            check = match.group("checks").split(",")[0]
            identity = (check, path, match.group("line"), match.group("col"))
            if identity in seen:
                continue
            seen.add(identity)
            findings.append({"check": check, "path": path, "message": normalise(match.group("message"))})
    return findings


def key_for(finding: dict) -> str:
    payload = f"{finding['check']}\n{finding['path']}\n{finding['message']}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def load_baseline(path: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                line = raw.split("#", 1)[0].strip()
                if not line:
                    continue
                key, _, count = line.partition(" x")
                counts[key] = int(count) if count else 1
    except FileNotFoundError:
        pass
    return counts


def load_comments(path: str) -> dict[str, list[str]]:
    """Existing prose under each `# --- check ---` header, so regenerating the
    file does not throw away why something was accepted."""
    comments: dict[str, list[str]] = {}
    current: str | None = None
    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                line = raw.rstrip("\n")
                header = re.match(r"^# --- (.+) ---$", line)
                if header:
                    current = header.group(1)
                    comments[current] = []
                    continue
                if current is None:
                    continue
                if line.startswith("#"):
                    body = line[1:].strip()
                    if body and body != "NOT YET AUDITED.":
                        comments[current].append(body)
                elif line.strip():
                    current = None
    except FileNotFoundError:
        pass
    return {check: text for check, text in comments.items() if text}


def write_baseline(findings: list[dict], baseline_path: str) -> None:
    counts = Counter(key_for(f) for f in findings)
    by_check: dict[str, list[dict]] = defaultdict(list)
    for finding in findings:
        by_check[finding["check"]].append(finding)
    comments = load_comments(baseline_path)

    with open(baseline_path, "w", encoding="utf-8") as handle:
        handle.write(HEADER)
        for check in sorted(by_check):
            handle.write(f"\n# --- {check} ---\n")
            for line in comments.get(check, ["NOT YET AUDITED."]):
                handle.write(f"# {line}\n")
            written: set[str] = set()
            for finding in sorted(by_check[check], key=lambda f: f["path"]):
                key = key_for(finding)
                if key in written:
                    continue
                written.add(key)
                handle.write(f"{key} x{counts[key]}  # {check} {finding['path']}\n")


def main() -> int:
    mode, log_path, baseline_path, strip_prefix = sys.argv[1:5]
    findings = parse(log_path, strip_prefix)

    if mode == "write":
        write_baseline(findings, baseline_path)
        print(f"Wrote {baseline_path}: {len(findings)} findings")
        return 0

    accepted = load_baseline(baseline_path)
    counts = Counter(key_for(f) for f in findings)
    new: list[dict] = []
    reported: set[str] = set()
    for finding in findings:
        key = key_for(finding)
        if counts[key] <= accepted.get(key, 0) or key in reported:
            continue
        reported.add(key)
        new.append(finding)

    total, accepted_count = len(findings), len(findings) - len(new)
    print(f"--- {total} findings, {accepted_count} accepted, {len(new)} new ---")
    if not new:
        return 0
    print()
    for finding in sorted(new, key=lambda f: (f["check"], f["path"]))[:40]:
        print(f"{finding['check']}  {finding['path']}")
        print(f"  {finding['message']}")
    if len(new) > 40:
        print(f"... and {len(new) - 40} more")
    print()
    print("Fix them, or audit and accept with:")
    print("  ./scripts/test/muma-server-tidy.sh --write-baseline")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
