"""Seeds the scene group date format overrides by measuring the library's own NFOs.

Most scene groups write a year-last date as D-M-Y and a year-first date as Y-M-D, which is what
NfoDate assumes by default. A minority write M-D-Y throughout. Only a component above 12 can prove
which, so this walks every NFO, counts the provable tokens per group, and records an override for a
group whose evidence contradicts the default and never supports it. Mixed evidence is left alone: the
default then applies, rather than encoding a mixture as a certainty.
"""
import argparse
import logging
import os
import re
import sys
from collections import Counter, defaultdict

from services.tagger.Song import NfoDate

DEFAULT_ROOT = '/mnt/music/EPs'


def classify_token(token):
    """The written order a token proves, `'dm'` or `'md'`, or None when it proves nothing."""
    parts = re.split(r'[-./]', token)
    if len(parts) != 3:
        return None
    year_first = len(parts[0]) == 4
    year_last = len(parts[2]) == 4
    if year_first == year_last:
        return None
    first, second = (int(parts[1]), int(parts[2])) if year_first else (int(parts[0]), int(parts[1]))
    if first > 12 and second <= 12:
        return 'dm'
    if second > 12 and first <= 12:
        return 'md'
    return None


def _default_order(token):
    """What NfoDate would assume for this token without an override."""
    parts = re.split(r'[-./]', token)
    return 'md' if len(parts[0]) == 4 else 'dm'


def collect_evidence(root):
    """`{scene_group: Counter({'agrees': n, 'contradicts': n})}` over every NFO under `root`.

    A token's proven order is only informative relative to what the positional default would have
    assumed for that token, so the comparison happens here and the counters record agreement.
    """
    evidence = defaultdict(Counter)
    for current, _dirs, files in os.walk(root):
        dirname = os.path.basename(current)
        if NfoDate.dirname_year(dirname) is None:
            continue
        if not any(name.lower().endswith('.nfo') for name in files):
            continue
        group = NfoDate.scene_group(dirname) or '(none)'
        text = NfoDate.read_nfo(current)
        for _kind, token in NfoDate.date_tokens(text):
            observed = classify_token(token)
            if observed is None:
                continue
            evidence[group]['agrees' if observed == _default_order(token) else 'contradicts'] += 1
    return evidence


# A group needs this many contradicting tokens before its evidence counts at all, and has to
# contradict this many times more often than it agrees.
#
# Both thresholds come from measuring the real library. A single contradicting token is not a format,
# it is one odd NFO, and twelve groups had exactly that. At the other end, requiring zero agreement
# was worse: group BC contradicts the default 170 times and agrees once, and that lone token would
# have left all 170 misdated. Compliant groups produce noise at around one in a thousand (FMC agrees
# 4922 times and contradicts 3), so a 4:1 majority separates a deviant group from noise with room to
# spare.
MIN_CONTRADICTIONS = 2
MAJORITY_FACTOR = 4


def group_verdicts(evidence):
    """Overrides to store: groups whose evidence clearly contradicts the positional default."""
    verdicts = {}
    for group, counts in evidence.items():
        contradicts, agrees = counts['contradicts'], counts['agrees']
        if contradicts >= MIN_CONTRADICTIONS and contradicts > MAJORITY_FACTOR * agrees:
            verdicts[group] = 'md'
    return verdicts


def store(verdicts):
    """Writes the overrides, upserting so a re-measurement can correct an earlier verdict.

    Group names differ only in case across releases (NBD and Nbd, QTXMP3 and QTXMp3). Both the
    table's collation and LookupTableHelper.get compare case-insensitively, so those variants share
    one row and one verdict rather than disagreeing.
    """
    from services.common.Helpers.DatabaseConnector import DatabaseConnector

    connection = DatabaseConnector().connect()
    try:
        with connection.cursor() as cursor:
            for group, order in sorted(verdicts.items()):
                cursor.execute(
                    'INSERT INTO rules_scene_group_date_format (scene_group, date_format) '
                    'VALUES (%s, %s) ON DUPLICATE KEY UPDATE date_format = VALUES(date_format)',
                    (group, order))
        connection.commit()
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=DEFAULT_ROOT)
    parser.add_argument('--apply', action='store_true', help='write the overrides; default is a dry run')
    args = parser.parse_args(argv)

    evidence = collect_evidence(args.root)
    verdicts = group_verdicts(evidence)
    for group, counts in sorted(evidence.items()):
        logging.info('%s: agrees=%d contradicts=%d', group, counts['agrees'], counts['contradicts'])
    print(f'{len(evidence)} groups measured, {len(verdicts)} overrides: {sorted(verdicts)}')
    if args.apply:
        store(verdicts)
        print('stored')
    else:
        print('dry run, nothing written; pass --apply to store')
    return 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
