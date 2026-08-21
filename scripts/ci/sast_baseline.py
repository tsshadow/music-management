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
"""

REASONS = {
    'sqlalchemy-execute-raw-query': (
        'Table and column names cannot be bound as parameters, and every site '
        'interpolates an internal constant rather than request data. Revisit '
        'any new site that interpolates something reaching it from outside.'
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
    'no-new-privileges': (
        'Docker Compose hardening the production stack does not set yet. Worth '
        'doing, and a change to the deployed stack rather than to code.'
    ),
    'writable-filesystem-service': 'Same as no-new-privileges.',
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
        'on purpose -- the launcher alias and the media button receiver.'
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
        'renovate.json has no cooldown, so a freshly published version can be '
        'proposed the day it lands. Worth adding; it is a policy change to the '
        'update bot rather than to this code.'
    ),
    'request-with-http': (
        'Plain HTTP to services on this LAN that speak no TLS -- the LMS server '
        'and apk-hoster. Both are reachable only inside the tailnet.'
    ),
    'unsafe-formatstring': (
        'Format strings built from internal constants in one-off tools, not '
        'from anything a request supplies.'
    ),
    'missing-user': (
        'Compose services that still run as root. Same hardening pass as '
        'no-new-privileges, and the same reason it is not in this change.'
    ),
}


def key_for(result: dict) -> str:
    rule = result['check_id']
    path = result['path']
    line = (result['extra'].get('lines') or '').strip()
    digest = hashlib.sha1(f'{rule}\n{path}\n{line}'.encode()).hexdigest()
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


def write_baseline(report_path: str, baseline_path: str) -> None:
    results = load_report(report_path)
    counts: Counter[str] = Counter(key_for(r) for r in results)
    by_rule: dict[str, list[dict]] = defaultdict(list)
    for result in results:
        by_rule[short_rule(result['check_id'])].append(result)

    with open(baseline_path, 'w') as handle:
        handle.write(HEADER)
        for rule in sorted(by_rule):
            handle.write(f'\n# --- {rule} ---\n')
            reason = REASONS.get(rule)
            if reason:
                for chunk in _wrap(reason):
                    handle.write(f'# {chunk}\n')
            else:
                handle.write('# NOT YET AUDITED.\n')
            written: set[str] = set()
            for result in sorted(by_rule[rule], key=lambda r: (r['path'], r['start']['line'])):
                key = key_for(result)
                if key in written:
                    continue
                written.add(key)
                handle.write(
                    f"{key} x{counts[key]}  # {rule} {result['path']}\n"
                )


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
        write_baseline(report_path, baseline_path)
        return 0
    if mode == 'check':
        return check(report_path, baseline_path)
    print(f'unknown mode: {mode}')
    return 2


if __name__ == '__main__':
    sys.exit(main())
