"""Compare a semgrep JSON report against the accepted-findings baseline.

Semgrep's own fingerprint requires a logged-in account, so identity is built
here instead: the rule, the file, and the text of the flagged line. Line numbers
are deliberately not part of it -- they move whenever anything above them
changes, which would invalidate the whole baseline on an unrelated edit.

Used by scripts/ci/sast.sh; not a test module.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

HEADER = """\
# Static-analysis findings this project has consciously accepted for now.
#
# Read by scripts/ci/sast.sh. Anything listed here is excluded from the scan;
# anything not listed fails the job. An entry is per *finding*, not per rule, so
# a new site that trips an already-accepted rule still fails -- "we already do
# this elsewhere" never silently covers new code.
#
# Format: <key> x<count>  # <rule> <path>
# The key is a hash of the rule, the file and the flagged line's text, and the
# count is how many times it occurs. Line numbers are not part of it -- they
# move whenever anything above them changes -- but the count is, so a second
# identical line in the same file is a new finding and fails. Editing a flagged
# line invalidates its entry on purpose: the code changed, so the reason below
# should be re-read before it is accepted again.
#
# Regenerate after auditing new findings:
#   SAST_WRITE_BASELINE=1 ./scripts/ci/sast.sh
#
# Reasons are per rule, in the section headers below. A rule with no reason has
# not been audited yet and is the next thing to look at.
#
# This whole file is generated, reasons included. Write a reason in REASONS in
# scripts/ci/sast_baseline.py, not here: text typed straight into this file used
# to be destroyed by the next regeneration, twice. The [r:...] beside each
# section stamps what the generator wrote, so an edit made here is now detected
# and the regeneration refuses instead of overwriting it.
"""

REASONS = {
    'sqlalchemy-execute-raw-query': (
        'Table and column names cannot be bound as parameters, and every site '
        'interpolates an internal constant rather than request data. Revisit '
        'any new site that interpolates something reaching it from outside. '
        'SoundcloudArchive.py and the third events.py hit arrived with the '
        'whole-tree ruff format, and are worth explaining because they look like '
        'the reformat introduced them. It did not: both sites are older than the '
        'reformat, which only joined their implicitly-concatenated SQL onto one '
        'line and so made the pattern visible to semgrep. Audited both, '
        '2026-09-01: SoundcloudArchive.py builds a join of %s placeholders and '
        'passes tuple(chunk) as parameters, so only the placeholder *count* is '
        'interpolated; events.py takes its WHERE from _build_filters(), where '
        'every clause is a literal and every value goes into params as %s. '
        'Neither puts request data into the SQL string.'
    ),
    'avoid-sqlalchemy-text': 'Same as sqlalchemy-execute-raw-query.',
    'formatted-sql-query': (
        'Table-name interpolation in the helper layer and in one-off scripts '
        'under tools/ and scripts/, which take their arguments from the person '
        'running them. Values still go through placeholders.'
    ),
    'github-actions-mutable-action-tag': (
        'services/muma-mobile/.github/ is dead weight inherited from Ultrasonic '
        'at the rename commit 054b115df. This is a GitLab repository with no '
        'GitHub remote, so nothing runs these workflows. Deleting the directory '
        'removes all of these; that is a separate change.'
    ),
    'dependabot-missing-cooldown': 'Same dead Ultrasonic directory.',
    'insecure-file-permissions': (
        'The importer setting 0777/0666 on a release it just moved into the '
        'library. That is what the whole tree carries after the 2026-09-05 '
        'permission repair, and it has to: the muma containers write as root, '
        'LMS writes as its own user, and the SMB share maps everyone else to a '
        'third. A release left at the default 0755/0644 is readable by all of '
        'them and writable by none -- 19 directories arrived that way in the '
        'first week of September and the release-date backfill skipped nine of '
        'their files. Narrowing this to a shared group is the better answer, and '
        'it is a change to how every writer is deployed rather than to this '
        'line. Audited 2026-09-08.'
    ),
    'writable-filesystem-service': (
        'Container hardening that is not safe to switch on blind: a service that '
        'writes a temp file falls over in a way that only shows up on deploy, '
        'and prod cannot be tested from here. no-new-privileges, which cannot '
        'break anything, was applied instead. tools went from x3 to x4 with '
        'release-date-backfill, a one-off run that writes only to the mounted '
        'music share and follows the same rule. x4 to x5 with song-work-repair, '
        '2026-09-05: same shape again, a one-off container that runs one script '
        'against the database, no mounts, gone when it exits. read_only would be '
        'a better answer than an accepted finding, but it cannot be tried on '
        'anything but production -- the whole file carries that caveat -- so it '
        'follows its four neighbours rather than being the one service that is '
        'hardened untested. The finding semgrep prints names firefox: it reports '
        'the surplus occurrence, not the one that was added.'
    ),
    'exposing-docker-socket-volume': (
        'The socket is mounted where a container genuinely drives Docker. Each '
        'new mount needs its own justification, which is why this is listed per '
        'site rather than per rule.'
    ),
    'detected-ssh-password': (
        'sshpass reading a shell variable, not a committed credential. The '
        'branch above each one prefers key auth and only falls back to this. '
        'The real weakness is that a password in argv is visible to a local '
        'process listing, which is acceptable on a workstation deploy script.'
    ),
    'detected-generic-api-key': (
        '.gitleaksignore lists commit:path:rule:line references to past '
        'findings, not the secrets themselves.'
    ),
    'detected-jwt-token': 'Test fixtures for the Subsonic API client.',
    'exported_activity': (
        'Android activities that are launched by the system or by another app '
        'on purpose -- the launcher aliases and the media button receiver. '
        'Four aliases since the Capacitor shell: icon x interface, exactly one '
        'enabled at a time. An alias carrying a LAUNCHER intent filter has to '
        'be exported to be launchable at all; CapacitorActivity itself, which '
        'two of them target, is not.'
    ),
    'wildcard-cors': (
        'OPEN HARDENING ITEM, not a false positive. services/music_manager/'
        'main.py:47 serves every origin with every method and header. It is not '
        'an auth bypass on its own -- allow_credentials is off, so a browser '
        'attaches nothing and an attacker would need the x-api-key already -- '
        'but it does let any page read the unauthenticated endpoints from a '
        'victim on this LAN. Narrowing it means naming the frontend and LMS '
        'origins, which is a deployment change and needs its own merge request.'
    ),
    'detected-private-key': (
        'A self-signed certificate fixture under core/subsonic-api integration '
        'tests. It exists to be a key; it protects nothing.'
    ),
    'detected-bcrypt-hash': 'An example hash in installation documentation.',
    'python-logger-credential-disclosure': (
        'Both sites are logger.error(..., e) in the except branch of a Spotify '
        'token fetch. What is logged is the exception, not the token that the '
        'try branch assigns; semgrep flags the token being in scope.'
    ),
    'use-of-md5': (
        'Content and path hashing for cache keys and duplicate detection, never '
        'for authentication or signatures.'
    ),
    'dynamic-proxy-host': (
        'The proxy target is the configured LMS or Subsonic server, read from '
        'this deployment\'s own settings rather than from a request.'
    ),
    'missing-internal': (
        'Android exported components again -- the same set as exported_activity.'
    ),
    'renovate-missing-minimum-release-age': (
        'A three-day cooldown is set on a catch-all packageRules entry, with '
        'yt-dlp exempted because being behind on it is what breaks downloading. '
        'The rule wants the key repeated on every entry; Renovate does not need '
        'that -- a later rule that omits the key does not unset it -- so the '
        'remaining hits are the rule being stricter than the tool.'
    ),
    'request-with-http': (
        'Plain HTTP to a service on this LAN that speaks no TLS, reachable only '
        'inside the tailnet. LmsScanTrigger used to be listed here too. It now '
        'builds its URL through one helper that keeps an explicit scheme when the '
        'configured host carries one, so there is no literal http:// left in the '
        'request and the rule no longer fires.'
    ),
    'dynamic-urllib-use-detected': (
        'The ntfy notify call in the crash-triage listener builds its URL from '
        'NTFY_URL, an operator-set value in a root-owned env file, and the code '
        'pins the scheme to http(s) before opening it -- a mangled value cannot '
        'become a file:// read. Audited 2026-08-31. The nightly prod-check '
        'collector does the same with MUMA_URL from the same env file: its '
        'ProdClient refuses anything but http(s) in its constructor. Audited '
        '2026-09-10. This reason was once restored by hand after a regeneration '
        'replaced it with the placeholder; that is what unwritable_rationale() '
        'below now prevents.'
    ),
    'unsafe-formatstring': (
        'Format strings built from internal constants in one-off tools, not '
        'from anything a request supplies.'
    ),
    'missing-user': (
        'Images that still run as root. Changing that means getting volume '
        'ownership right on a live deployment, so it needs its own change with '
        'someone watching the stack come up.'
    ),
}


def key_for(result: dict) -> str:
    rule = result['check_id']
    path = result['path']
    line = (result['extra'].get('lines') or '').strip()
    digest = hashlib.sha256(f'{rule}\n{path}\n{line}'.encode()).hexdigest()
    return digest[:16]


def short_rule(check_id: str) -> str:
    return check_id.split('.')[-1]


def load_report(path: str) -> list[dict]:
    with open(path) as handle:
        return json.load(handle).get('results', [])


def load_baseline(path: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    try:
        with open(path) as handle:
            for raw in handle:
                line = raw.split('#', 1)[0].strip()
                if not line:
                    continue
                key, _, count = line.partition(' x')
                counts[key] = int(count) if count else 1
    except FileNotFoundError:
        pass
    return counts


#: What a section says before anybody has audited it. Written by this generator,
#: so it is the one comment block that may be replaced without asking.
PLACEHOLDER = 'NOT YET AUDITED.'


def _normalized(lines: list[str]) -> str:
    """Comment text with its wrapping removed, so two rewraps of one paragraph match."""
    return ' '.join(' '.join(line.lstrip('#') for line in lines).split()).strip()


def reason_stamp(text: str) -> str:
    """A short digest of the reason this generator wrote for a section.

    Recorded in the section header, which is what makes "somebody typed here"
    decidable rather than a guess. Comparing the file against REASONS instead
    cannot work: updating a reason is a normal edit, and it would be
    indistinguishable from the accident this guards against.
    """
    return hashlib.sha256(_normalized([text]).encode()).hexdigest()[:8]


def rationale_in_file(baseline_path: str) -> dict[str, tuple[str, str]]:
    """Each section's reason text and the stamp recorded beside it.

    Keyed by rule, with the header under the empty key. Everything between a
    `# --- rule --- [r:stamp]` marker and that section's first key line is the
    reason. A section written before stamps existed has an empty stamp.
    """
    found: dict[str, list[str]] = {'': []}
    stamps: dict[str, str] = {'': ''}
    rule = ''
    try:
        with open(baseline_path) as handle:
            for raw in handle:
                line = raw.rstrip('\n')
                if line.startswith('# --- '):
                    name, _, stamp = line[6:].partition(' --- [r:')
                    rule = name.removesuffix(' ---').strip()
                    stamps[rule] = stamp.rstrip(']').strip()
                    found[rule] = []
                elif line.startswith('#'):
                    found[rule].append(line)
    except FileNotFoundError:
        return {}
    return {name: (_normalized(lines), stamps.get(name, '')) for name, lines in found.items()}


def rationale_to_write(rule: str) -> str:
    return _normalized(_wrap(REASONS[rule])) if REASONS.get(rule) else PLACEHOLDER


def unwritable_rationale(baseline_path: str) -> dict[str, str]:
    """Reason text in the file that regenerating would not put back.

    The whole file is generated from REASONS, so anything typed straight into it
    is lost the next time somebody accepts a finding. That has happened twice:
    36 lines of audit rationale in one go, and once before that -- the file still
    carried a note about the first incident, written by the person who restored
    it by hand. A comment block nobody can reproduce is the one thing this
    generator must not quietly drop.

    The stamp beside each section is what decides it. A section still carrying
    the stamp of the text it holds was written by this generator, so replacing it
    with a newer reason from REASONS loses nothing -- updating a reason has to
    stay an ordinary edit. A section whose text no longer matches its stamp was
    typed by a person, and that is what this refuses to overwrite.

    Returns rule -> the text that would be lost. The header is under ''.
    """
    lost = {}
    for rule, (existing, stamp) in rationale_in_file(baseline_path).items():
        if not existing or existing == PLACEHOLDER:
            # The placeholder is this generator's own text; replacing it is the
            # normal path for a rule whose reason was just written into REASONS.
            continue
        if rule == '':
            if existing != _normalized(HEADER.splitlines()):
                lost[rule] = existing
            continue
        if stamp:
            if stamp != reason_stamp(existing):
                lost[rule] = existing
            continue
        # No stamp: written before this guard existed, so REASONS is the only
        # thing to compare against. One regeneration gives every section a stamp
        # and this branch stops being reachable.
        if existing != rationale_to_write(rule):
            lost[rule] = existing
    return lost


def write_baseline(report_path: str, baseline_path: str) -> int:
    """Regenerate the baseline. Returns an exit status; refuses to lose rationale."""
    lost = unwritable_rationale(baseline_path)
    if lost and os.environ.get('SAST_BASELINE_FORCE') != '1':
        print(f'--- refusing to write {baseline_path}: {len(lost)} section(s) hold '
              f'rationale that is not in REASONS ---')
        for rule, text in sorted(lost.items()):
            print(f'\n{rule or "(header)"}:\n  {text[:400]}')
        print(
            '\nRegenerating rebuilds every comment block from REASONS in '
            'scripts/ci/sast_baseline.py, so the text above would be gone. Move it '
            'into REASONS (that is where a reason belongs -- the file is generated), '
            'then run this again. SAST_BASELINE_FORCE=1 overrides, and throws it away.'
        )
        return 1

    results = load_report(report_path)
    counts: Counter[str] = Counter(key_for(r) for r in results)
    by_rule: dict[str, list[dict]] = defaultdict(list)
    for result in results:
        by_rule[short_rule(result['check_id'])].append(result)

    with open(baseline_path, 'w') as handle:
        handle.write(HEADER)
        for rule in sorted(by_rule):
            reason = REASONS.get(rule)
            written_text = _wrap(reason) if reason else [PLACEHOLDER]
            # The stamp records what this generator wrote, so a later edit by hand
            # is detectable. See unwritable_rationale().
            handle.write(f'\n# --- {rule} --- [r:{reason_stamp(" ".join(written_text))}]\n')
            for chunk in written_text:
                handle.write(f'# {chunk}\n')
            written: set[str] = set()
            for result in sorted(by_rule[rule], key=lambda r: (r['path'], r['start']['line'])):
                key = key_for(result)
                if key in written:
                    continue
                written.add(key)
                handle.write(
                    f"{key} x{counts[key]}  # {rule} {result['path']}\n"
                )
    return 0


def _wrap(text: str, width: int = 74) -> list[str]:
    words, lines, current = text.split(), [], ''
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f'{current} {word}'.strip()
    if current:
        lines.append(current)
    return lines


def check(report_path: str, baseline_path: str) -> int:
    results = load_report(report_path)
    accepted = load_baseline(baseline_path)
    seen: Counter[str] = Counter(key_for(r) for r in results)

    # A finding is new when its key is unknown, or when it now occurs more often
    # than was accepted -- a second identical line is a second site to justify.
    new = []
    budget = dict(accepted)
    for result in results:
        key = key_for(result)
        if budget.get(key, 0) > 0:
            budget[key] -= 1
        else:
            new.append(result)

    stale = {key for key in accepted if key not in seen}

    accepted_total = sum(accepted.values())
    print(f'--- {len(results)} findings, {accepted_total} accepted, {len(new)} new ---')

    if stale:
        print(f'{len(stale)} accepted findings no longer occur. Regenerate the '
              f'baseline with SAST_WRITE_BASELINE=1 ./scripts/ci/sast.sh')

    if not new:
        print('--- No new findings ---')
        return 0

    for result in new:
        location = f"{result['path']}:{result['start']['line']}"
        print(f"\n{short_rule(result['check_id'])}  {location}")
        print(f"  {result['extra'].get('message', '').strip()[:200]}")
        print(f"  {(result['extra'].get('lines') or '').strip()[:160]}")

    print(f'\n{len(new)} new finding(s). Fix them, or audit and accept them with '
          f'SAST_WRITE_BASELINE=1 ./scripts/ci/sast.sh')
    return 1


def main() -> int:
    if len(sys.argv) != 4:
        print('usage: sast_baseline.py <write|check> <report.json> <baseline.txt>')
        return 2
    mode, report_path, baseline_path = sys.argv[1:4]
    if mode == 'write':
        return write_baseline(report_path, baseline_path)
    if mode == 'check':
        return check(report_path, baseline_path)
    print(f'unknown mode: {mode}')
    return 2


if __name__ == '__main__':
    sys.exit(main())
