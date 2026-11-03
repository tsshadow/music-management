#!/usr/bin/env python3
"""Personal-data guard for the public repository (issue #208).

Two modes, both exit 1 on a finding and never print the matched text (only a short commit id or a
file path and the kind of finding), because the matched text is the personal value.

    public_guard.py tree      Tracked files: no word whose sha256 is in public-banned-tokens.txt.
    public_guard.py history   Commits and tags: identity allowlist, regex patterns and banned words.

History scope:
    --range A..B   the commits of that range only (merge request pipelines: origin/develop..HEAD).
    --full         every commit of develop and master (origin/ copy when it exists) and every tag,
                   plus the tagger and the message of every annotated tag.

Identity policy, for the author and the committer of every commit and the tagger of every tag:
the e-mail must be one of the owner's public addresses, match `*@users.noreply.example.com`, or have
its sha256 in public-upstream-identities.txt (the upstream authors and old bots in the history before
the rewrite of 2026-10-29). Everything else, such as a private mailbox or the bot of the private
GitLab host, is a finding. The name part of an identity is only checked by the patterns and the
banned words, never by the allowlist.
"""

import argparse
import bisect
import fnmatch
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI_DIR = ROOT / "scripts" / "ci"
WORD = re.compile(r"[a-z0-9]+")
ALLOWED_EMAIL_GLOBS = ("github@teunschriks.nl", "ci@example.com", "*@users.noreply.example.com")
SEP = "\x1f"
RECORD = "\x00"


def _env_path(name: str, default: str) -> Path:
    """Return the path in environment variable `name`, else the default file in scripts/ci."""
    return Path(os.environ.get(name) or CI_DIR / default)


def load_digests(path: Path) -> set[str]:
    """Read a digest file: the first token of every line that is not a comment or blank."""
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(line.split()[0].lower())
    return out


def digest(text: str) -> str:
    """Return the sha256 hex digest of `text`."""
    return hashlib.sha256(text.encode()).hexdigest()


def banned_words(text: str, banned: set[str]) -> bool:
    """Return True when a lower-case [a-z0-9]+ word of `text` has a digest in `banned`."""
    return any(digest(w) in banned for w in set(WORD.findall(text.lower())))


def git(*args: str, check: bool = True) -> str:
    """Run git in the repository root and return stdout."""
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=check)
    return proc.stdout.decode("utf-8", "replace")


def identity_ok(email: str, upstream: set[str]) -> bool:
    """Return True when `email` is allowed by the identity policy."""
    mail = email.strip().strip("<>").lower()
    if any(fnmatch.fnmatchcase(mail, g) for g in ALLOWED_EMAIL_GLOBS):
        return True
    return digest(mail) in upstream


def pattern_hit_lines(text: str, patterns: Path) -> set[int]:
    """Return the 1-based line numbers of `text` matched by the PCRE lines of `patterns` (grep -P -i)."""
    clean = [
        ln for ln in patterns.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.lstrip().startswith("#")
    ]
    if not clean:
        raise SystemExit("ERROR: no patterns, so the history check proves nothing.")
    # grep -P takes one pattern: join the lines into one alternation, each in its own group so that
    # an inline flag such as (?-i) stays inside its own line.
    combined = "|".join(f"(?:{ln})" for ln in clean)
    proc = subprocess.run(
        ["grep", "-P", "-i", "-n", "-a", "-e", combined],
        input=text.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if proc.returncode not in (0, 1):
        raise SystemExit(f"ERROR: grep failed with exit code {proc.returncode}: {proc.stderr.decode()[:200]}")
    return {int(line.split(b":", 1)[0]) for line in proc.stdout.splitlines() if line}


def tree_check() -> int:
    """Fail on a tracked text file that holds a banned word. Return the exit code."""
    banned = load_digests(_env_path("PUBLIC_CHECK_TOKENS", "public-banned-tokens.txt"))
    hits = []
    for rel in [p for p in git("ls-files", "-z").split("\0") if p]:
        path = ROOT / rel
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:4096]:
            continue
        if banned_words(data.decode("utf-8", "ignore"), banned):
            hits.append(rel)
    for rel in hits:
        print(f"banned word in {rel}")
    if hits:
        print(f"ERROR: {len(hits)} tracked file(s) hold a banned word (digest list).", file=sys.stderr)
        return 1
    print("--- banned words: clean ---")
    return 0


def collect(range_spec: str | None) -> list[dict]:
    """Return one record per commit (and per tag in full mode) with its identities and text."""
    records = []
    if range_spec:
        revs = [range_spec]
    else:
        revs = []
        for name in ("develop", "master"):
            for cand in (f"origin/{name}", name):
                if git("rev-parse", "--verify", "--quiet", cand, check=False).strip():
                    revs.append(cand)
                    break
        revs.append("--tags")
    fmt = "%x00" + "%x1f".join(["%H", "%an", "%ae", "%cn", "%ce", "%B"])
    log = git("log", *revs, f"--format={fmt}")
    for chunk in log.split(RECORD)[1:]:
        sha, an, ae, cn, ce, body = chunk.split(SEP, 5)
        records.append(
            {"id": sha[:8], "kind": "commit", "emails": [ae, ce], "text": f"{an} <{ae}>\n{cn} <{ce}>\n{body}"}
        )
    if not range_spec:
        tag_fmt = "%00" + "%1f".join(
            ["%(refname:short)", "%(objecttype)", "%(taggername)", "%(taggeremail)", "%(contents)"]
        )
        for chunk in git("for-each-ref", "refs/tags", f"--format={tag_fmt}").split(RECORD)[1:]:
            name, otype, tn, te, contents = chunk.split(SEP, 4)
            if otype != "tag":
                continue
            records.append({"id": f"tag {name}", "kind": "tag", "emails": [te], "text": f"{tn} {te}\n{contents}"})
    return records


def history_check(range_spec: str | None) -> int:
    """Check commits and tags against identity allowlist, patterns and banned words. Return the exit code."""
    patterns = _env_path("PUBLIC_CHECK_PATTERNS", "public-patterns.txt")
    banned = load_digests(_env_path("PUBLIC_CHECK_TOKENS", "public-banned-tokens.txt"))
    upstream = load_digests(_env_path("PUBLIC_CHECK_UPSTREAM", "public-upstream-identities.txt"))
    records = collect(range_spec)

    starts, blob, line = [], [], 1
    for rec in records:
        starts.append(line)
        text = rec["text"].rstrip("\n") + "\n"
        blob.append(text)
        line += text.count("\n")
    hit_lines = pattern_hit_lines("".join(blob), patterns)
    pattern_ids = {bisect.bisect_right(starts, n) - 1 for n in hit_lines}

    counts = {"identity": 0, "pattern": 0, "banned word": 0}
    flagged = set()
    for idx, rec in enumerate(records):
        kinds = []
        if any(not identity_ok(e, upstream) for e in rec["emails"]):
            kinds.append("identity")
        if idx in pattern_ids:
            kinds.append("pattern")
        if banned_words(rec["text"], banned):
            kinds.append("banned word")
        for k in kinds:
            counts[k] += 1
        if kinds:
            flagged.add(idx)
            print(f"{rec['id']}: {', '.join(kinds)}")
    scope = range_spec or "develop, master and all tags"
    print(
        f"--- history ({scope}): {len(records)} checked, {len(flagged)} flagged "
        f"(identity {counts['identity']}, pattern {counts['pattern']}, banned word {counts['banned word']}) ---"
    )
    if flagged:
        print("ERROR: personal data in commit or tag metadata (ids above, values not printed).", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    """Parse the command line and run the chosen mode."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("tree")
    hist = sub.add_parser("history")
    group = hist.add_mutually_exclusive_group(required=True)
    group.add_argument("--range")
    group.add_argument("--full", action="store_true")
    args = parser.parse_args()
    if args.mode == "tree":
        return tree_check()
    return history_check(None if args.full else args.range)


if __name__ == "__main__":
    sys.exit(main())
