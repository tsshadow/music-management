"""Assembles changelog.d fragments into CHANGELOG.md and RELEASE_NOTES.md.

Runs as part of the stabilize commit on a release branch. Everything this script does used to be
done by hand on the feature branch, which is why entries kept landing under the wrong version
heading: appending to a shared `## [Unreleased]` block merges cleanly against a two-line heading
insertion, and git then files your lines under a release that shipped without them. A fragment is
a file nobody else touches, so there is nothing to merge and nothing to misfile.

Dry run by default: it prints what it would write and touches nothing until `--apply`.
"""

import argparse
import datetime
import os
import sys

# Keep a Changelog's set, in the order the sections are emitted.
SECTIONS = ('added', 'changed', 'deprecated', 'removed', 'fixed', 'security')

# A fragment may hold two wordings: the changelog entry, then this marker, then the shorter
# release-notes version. RELEASE_NOTES.md addresses the person reading what changed in the app,
# CHANGELOG.md the person who will have to work on it -- the same change, different detail.
RELEASE_NOTES_MARKER = '<!-- release notes -->'

# CHANGELOG.md brackets the heading, the root RELEASE_NOTES.md does not, and muma-mobile's copies
# bracket it in both files. Accepting either is what the anchor is for; insisting on one spelling
# emptied services/muma-mobile/RELEASE_NOTES.md on the first release that carried a mobile
# fragment, because the file was already open for writing when the lookup failed.
UNRELEASED_ANCHORS = ('## [Unreleased]', '## Unreleased')

SCOPES = {
    'root': {
        'fragments': 'changelog.d',
        'changelog': 'CHANGELOG.md',
        'release_notes': ['RELEASE_NOTES.md'],
    },
    'mobile': {
        'fragments': os.path.join('changelog.d', 'mobile'),
        'changelog': os.path.join('services', 'muma-mobile', 'CHANGELOG.md'),
        # The two copies under app/src/main/assets are what the in-app "what's new" screen reads;
        # they are generated from these, and release:version-check fails when they drift.
        'release_notes': [
            os.path.join('services', 'muma-mobile', 'RELEASE_NOTES.md'),
            os.path.join('services', 'muma-mobile', 'app', 'src', 'main', 'assets', 'RELEASE_NOTES.md'),
        ],
    },
}


def fragment_files(directory):
    """`[(section, path)]` for every fragment in `directory`, sorted by name within a section.

    Subdirectories are skipped: `changelog.d/mobile` is its own scope, not part of the root one.
    """
    found = []
    if not os.path.isdir(directory):
        return found
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if not os.path.isfile(path) or not name.endswith('.md') or name == 'README.md':
            continue
        parts = name[: -len('.md')].rsplit('.', 1)
        if len(parts) != 2 or parts[1].lower() not in SECTIONS:
            raise ValueError(f'{path}: name must be <slug>.<section>.md with section in {sorted(SECTIONS)}')
        found.append((parts[1].lower(), path))
    return found


def split_fragment(text):
    """`(changelog_text, release_notes_text)`; both are the same when no marker is present."""
    if RELEASE_NOTES_MARKER in text:
        changelog, _marker, notes = text.partition(RELEASE_NOTES_MARKER)
        return changelog.strip(), notes.strip()
    stripped = text.strip()
    return stripped, stripped


def collect(directory):
    """`({section: [changelog_text]}, [release_notes_text], [path])` for one scope."""
    by_section = {}
    notes = []
    used = []
    for section, path in fragment_files(directory):
        with open(path, encoding='utf-8') as handle:
            changelog_text, notes_text = split_fragment(handle.read())
        if not changelog_text:
            raise ValueError(f'{path}: fragment is empty')
        by_section.setdefault(section, []).append(changelog_text)
        notes.append(notes_text)
        used.append(path)
    return by_section, notes, used


def render_changelog_section(by_section, version, date):
    """The `## [x.y.z] - date` block, sections in Keep a Changelog order."""
    lines = [f'## [{version}] - {date}', '']
    for section in SECTIONS:
        if section not in by_section:
            continue
        lines.append(f'### {section.capitalize()}')
        for entry in by_section[section]:
            lines.append(entry)
            lines.append('')
    return '\n'.join(lines).rstrip('\n') + '\n'


def render_release_notes_section(notes, version, date):
    body = '\n'.join(f'{note}\n' for note in notes)
    return f'## Global Version {version} ({date})\n\n{body}'


def insert_after(text, block, path):
    """Inserts `block` directly below the Unreleased heading, keeping one blank line either side."""
    anchor = next((candidate for candidate in UNRELEASED_ANCHORS if candidate in text), None)
    if anchor is None:
        raise ValueError(f'{path}: no "{UNRELEASED_ANCHORS[0]}" heading to insert below')
    head, _marker, tail = text.partition(anchor)
    return f'{head}{anchor}\n\n{block.rstrip(chr(10))}\n{tail.lstrip(chr(10))}'


def assemble(scope, version, date, apply_changes, root='.'):
    """Writes one scope. Returns the fragment paths it consumed."""
    config = SCOPES[scope]
    by_section, notes, used = collect(os.path.join(root, config['fragments']))
    if not used:
        print(f'{scope}: no fragments, nothing to assemble')
        return []

    changelog_block = render_changelog_section(by_section, version, date)
    notes_block = render_release_notes_section(notes, version, date)
    print(f'{scope}: {len(used)} fragment(s) -> {config["changelog"]}')
    print(changelog_block)

    if not apply_changes:
        return used

    # Every file is rendered before any of them is opened for writing. A scope that fails halfway
    # used to leave one file assembled and the next one truncated to nothing, on a release branch
    # where the damage looks like a merge artefact rather than a script that gave up.
    targets = [(os.path.join(root, config['changelog']), changelog_block)]
    targets.extend((os.path.join(root, relative), notes_block) for relative in config['release_notes'])

    pending = []
    for path, block in targets:
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as handle:
            pending.append((path, insert_after(handle.read(), block, path)))

    for path, assembled in pending:
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(assembled)

    for path in used:
        os.remove(path)
    return used


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True, help='the version being released, e.g. 0.45.0')
    # muma-mobile's versionName deliberately does not track the root VERSION -- it has drifted a
    # minor ahead -- so a mobile fragment filed under the root version would be filed under a
    # version the app never had. Read the next one from services/muma-mobile/app/build.gradle.
    parser.add_argument('--mobile-version', help='version for the muma-mobile scope, e.g. 6.28.4')
    parser.add_argument('--date', default=datetime.date.today().isoformat())
    parser.add_argument('--scope', choices=sorted(SCOPES), action='append', help='default: every scope')
    parser.add_argument('--apply', action='store_true', help='write the files; default is a dry run')
    args = parser.parse_args(argv)

    consumed = []
    for scope in args.scope or sorted(SCOPES):
        version = args.mobile_version if scope == 'mobile' else args.version
        if version is None and fragment_files(SCOPES[scope]['fragments']):
            parser.error('--mobile-version is required: there are fragments in changelog.d/mobile')
        consumed.extend(assemble(scope, version, args.date, args.apply))
    if not args.apply:
        print('dry run, nothing written; pass --apply to write the changelog')
    elif consumed:
        print(f'removed {len(consumed)} fragment(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
