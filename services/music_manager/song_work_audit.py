"""Works that hold more than one song: spotting the false merges of the grouping key.

The key in song_versions.py groups on "artist ::: title". When the tagger reads the wrong
half of an upload's title -- "Synapze - Neon Lights | Q-dance presents NEXT" stored as
title "NEXT" by artist "Q-Dance" -- every upload of that series shares one key, and a
collapsing list shows one of them and hides the rest. Production on 2026-09-26:
`q dance:::next` held 88 tracks, `q dance:::speqtrum` 63, `gearbox:::lockdown` 49 and
`q dance:::qore` 41 (bug report 098).

Nothing in a single track says it was misparsed, so the key cannot refuse it. The work can:
one song comes in a handful of lengths (radio, extended, original, instrumental, a few
edits), while a series of different songs comes in as many lengths as it has songs.

Pure functions, no database; song_version_worker.py owns the SQL.
"""

from __future__ import annotations

# Two durations closer than this are one length -- the MP3 and the M4A of one file differ
# by a second, a re-encode by two.
DURATION_TOLERANCE_SECONDS = 3.0

# The automatic split. Measured on production on 2026-09-26: the most distinct lengths any
# genuine work carries is 9 ("lny tnz:::fired up", 17 files), while every work past 12 is a
# misparsed series -- q dance:::next 61 distinct lengths, speqtrum 48, qore 33, lockdown ~17,
# 101barz:::throwback sessie 30. The empty band from 10 to 12 is the margin. A work needs
# more than 12 members before it can even qualify, so a normal song never reaches the test.
AUTO_SPLIT_LENGTHS = 12

# Below the split, a work is only flagged for a person to look at in the Versies page.
SUSPICIOUS_LENGTHS = 6
SPREAD_RATIO = 1.5
SPREAD_MIN_LENGTHS = 4
MANY_VERSIONS = 12
MANY_YEARS = 3
# Any work with more members than this is put in front of a person (bug report 142): the
# misparsed release series reached 18 to 88 members, while one song is rarely ripped more
# than ten times. Only flags -- the automatic split still needs AUTO_SPLIT_LENGTHS.
MANY_MEMBERS = 10


def distinct_lengths(durations, tolerance: float = DURATION_TOLERANCE_SECONDS) -> int:
    """How many different lengths a set of durations holds, within `tolerance` seconds.

    Neighbours are chained: 184, 185 and 186 are one length. Chaining can only make the
    count smaller, which is the safe direction for a test that splits works.
    """
    values = sorted(value for value in durations if value and value > 0)
    if not values:
        return 0
    count = 1
    for previous, current in zip(values, values[1:], strict=False):
        if current - previous > tolerance:
            count += 1
    return count


def _year(value) -> str | None:
    """The four-digit year of a release date, None when there is none."""
    text = str(value or '')
    return text[:4] if len(text) >= 4 and text[:4].isdigit() else None


def assess_work(members) -> dict | None:
    """Whether a work looks like several songs. None when it looks like one.

    `members` are rows with `duration_secs` and `release_date`. The verdict is `split`
    when the rule is unambiguous (more than AUTO_SPLIT_LENGTHS different lengths) and
    `suspicious` otherwise, with the reasons spelled out for the report.
    """
    members = list(members)
    durations = [row.get('duration_secs') for row in members]
    lengths = distinct_lengths(durations)
    positive = [value for value in durations if value and value > 0]
    ratio = round(max(positive) / min(positive), 2) if positive else 0.0
    years = {year for year in (_year(row.get('release_date')) for row in members) if year}

    reasons = []
    if lengths > SUSPICIOUS_LENGTHS:
        reasons.append(f'{lengths} different lengths')
    if ratio > SPREAD_RATIO and lengths >= SPREAD_MIN_LENGTHS:
        reasons.append(f'longest is {ratio}x the shortest')
    if len(members) > MANY_VERSIONS and len(years) > MANY_YEARS:
        reasons.append(f'{len(members)} versions from {len(years)} different years')
    if len(members) > MANY_MEMBERS:
        reasons.append(f'{len(members)} members')
    if not reasons:
        return None

    return {
        'verdict': 'split' if lengths > AUTO_SPLIT_LENGTHS else 'suspicious',
        'members': len(members),
        'lengths': lengths,
        'ratio': ratio,
        'years': len(years),
        'reasons': reasons,
    }


def suspicious_works(rows) -> list[dict]:
    """Group member rows by work and assess each; the worst (most members) first.

    Rows carry `work_id`, `work_key`, `duration_secs` and `release_date`, as
    song_version_worker.find_suspicious_works reads them.
    """
    by_work: dict[int, list] = {}
    keys: dict[int, str] = {}
    for row in rows:
        by_work.setdefault(row['work_id'], []).append(row)
        keys[row['work_id']] = row.get('work_key') or ''

    found = []
    for work_id, members in by_work.items():
        verdict = assess_work(members)
        if verdict:
            found.append({'work_id': work_id, 'work_key': keys[work_id], **verdict})
    found.sort(key=lambda item: (-item['members'], item['work_id']))
    return found
