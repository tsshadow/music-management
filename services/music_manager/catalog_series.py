"""How complete a label's catalogue is, read off the release folders it has on disk.

There is no catalogue-number column anywhere. The number lives in the release folder
(`<eps root>/<label>/<CATID rest-of-name>/<file>`), and this module turns a label's file
paths into series -- `DWX`, `DWXCD`, `DWXCVR` -- each with the range the library holds
and the numbers inside that range that are not there.

What it deliberately does not claim: anything before the lowest or after the highest
number held. A label may skip numbers, and nothing here can tell a skipped number from
one that was never bought, so the vocabulary is "absent" and "observed range", never
"missing".
"""

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from services.tagger.Song import LabelPath

#: A series wider than this is reported by count only. One mistyped folder
#: (`DWX2000000`) must not turn the response into two million integers.
EXPANSION_CAP = 20_000

#: The number is the last run of digits. It needs at least three of them, unless a
#: `-` or `_` sets it apart from the prefix -- that is what reads `R909-29` as series
#: `R909` number `29` while leaving `AFT3R001` whole up to its `001`. The suffix may not
#: contain a digit, which is what pins the number to the *last* run.
_CATID = re.compile(r'^(?P<prefix>.*?)(?:(?P<sep>[-_])(?P<sep_number>\d+)|(?P<number>\d{3,}))(?P<suffix>\D*)$')


@dataclass(frozen=True)
class ParsedCatid:
    """One catalogue number taken apart: `DWX0544-` is prefix `DWX`, number 544, digits `0544`, suffix `-`."""

    prefix: str
    number: int
    digits: str
    suffix: str
    separator: str


def parse_catid(catid: str) -> ParsedCatid | None:
    """Splits a catalogue number into prefix, number and suffix, or None when it has no number.

    The prefix comes back upper-cased so `dwx001` and `DWX002` land in one series.
    """
    match = _CATID.match((catid or '').strip())
    if not match:
        return None
    digits = match.group('sep_number') or match.group('number')
    return ParsedCatid(
        prefix=match.group('prefix').upper(),
        number=int(digits),
        digits=digits,
        suffix=match.group('suffix'),
        separator=match.group('sep') or '',
    )


def runs(numbers: Iterable[int]) -> list[list[int]]:
    """Compresses ascending numbers into `[from, to]` runs: `[1, 2, 3, 7]` -> `[[1, 3], [7, 7]]`."""
    result: list[list[int]] = []
    for number in numbers:
        if result and result[-1][1] == number - 1:
            result[-1][1] = number
        else:
            result.append([number, number])
    return result


@dataclass
class _Series:
    """Everything seen for one prefix while the paths are being walked."""

    prefix: str
    numbers: set[int] = field(default_factory=set)
    catids: set[str] = field(default_factory=set)
    widths: Counter = field(default_factory=Counter)
    separators: Counter = field(default_factory=Counter)
    variants: dict[str, tuple[str, str]] = field(default_factory=dict)

    def add(self, parsed: ParsedCatid, key: str, catid: str, release_folder: str) -> None:
        """Records one catid; `key` is its upper-cased form, `catid` how it was first seen."""
        self.numbers.add(parsed.number)
        if key in self.catids:
            return
        self.catids.add(key)
        self.widths[len(parsed.digits)] += 1
        self.separators[parsed.separator] += 1
        if parsed.suffix:
            self.variants[key] = (catid, release_folder)

    def summary(self) -> dict[str, Any]:
        """The range, count and missing numbers of this series, as the API returns them."""
        low, high = min(self.numbers), max(self.numbers)
        span = high - low + 1
        present = len(self.numbers)
        truncated = span > EXPANSION_CAP
        absent = [] if truncated else [n for n in range(low, high + 1) if n not in self.numbers]
        return {
            'prefix': self.prefix,
            'separator': _most_common(self.separators, prefer_larger=False),
            'min': low,
            'max': high,
            # Ties go to the wider form so padding never truncates the newest releases.
            'width': _most_common(self.widths, prefer_larger=True),
            'present': present,
            'releases': len(self.catids),
            'absent_count': span - present,
            'absent': absent,
            'absent_runs': runs(absent),
            'absent_truncated': truncated,
            'coverage': round(present / span, 3),
            'variants': [
                {'catid': catid, 'release_folder': folder} for _key, (catid, folder) in sorted(self.variants.items())
            ],
        }


def _most_common(counter: Counter, prefer_larger: bool) -> Any:
    """The most frequent key; on a tie the larger one when asked, the smaller otherwise."""
    best = max(counter.values())
    candidates = [key for key, count in counter.items() if count == best]
    return max(candidates) if prefer_larger else min(candidates)


def build_catalog(paths: Iterable[str], eps_root: str | None, delimiter: str) -> dict[str, Any]:
    """The catalogue picture for one label, from the paths of every file it has.

    Returns `{'files_considered', 'files_outside_root', 'series', 'other'}`: one entry
    per prefix in `series`, most present numbers first, and the catalogue numbers that
    have no readable number in `other`.

    Only the EPs tree is read. A label's files also live under `Soundcloud/`,
    `Podcasts/` and `Top 100/`, and there the folder above the file is a channel or a
    show, not a release; `LabelPath.split`'s fallback would happily hand those over
    and a channel name ending in digits would become a series. So when `eps_root` is
    set, a path outside it is skipped and counted in `files_outside_root`; the
    fallback is kept only for the case that no root is configured at all. A file that
    sits directly in the label folder has no release folder and is skipped too; both
    still count in `files_considered`.
    """
    series: dict[str, _Series] = {}
    other: dict[str, tuple[str, str]] = {}
    root = str(eps_root or '').rstrip(delimiter)
    files = 0
    outside = 0
    for path in paths:
        files += 1
        if root and not path.startswith(root + delimiter):
            outside += 1
            continue
        _label, release_folder = LabelPath.split(path, eps_root, delimiter)
        catid = LabelPath.catalog_number(release_folder)
        if not catid:
            continue
        key = catid.upper()
        parsed = parse_catid(catid)
        if parsed is None:
            other.setdefault(key, (catid, release_folder))
            continue
        series.setdefault(parsed.prefix, _Series(parsed.prefix)).add(parsed, key, catid, release_folder)
    summaries = [entry.summary() for entry in series.values()]
    summaries.sort(key=lambda entry: (-entry['present'], entry['prefix']))
    return {
        'files_considered': files,
        'files_outside_root': outside,
        'series': summaries,
        'other': [{'catid': catid, 'release_folder': folder} for _key, (catid, folder) in sorted(other.items())],
    }
