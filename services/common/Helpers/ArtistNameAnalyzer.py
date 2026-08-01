"""Turn a raw artist string into a proposal, with the reasoning attached.

The library holds tens of thousands of artist names of which only a fraction are
real. They fail in a handful of recognisable ways: noise wrapped around a real
name (`**FREE DOWNLOAD** DJ KURT`), two names glued together
(`AngerfistHeadhunter`), a misspelling, or a sentence some tagger rule mistook
for an artist (`Als wij samen komen(`).

This module proposes what to do with one such string. It never decides: it
returns a proposal, a confidence and the chain of reasoning that produced it, so
a human can see why. Every threshold lives in `AnalyzerConfig`, because what
counts as "good enough" can only be judged by looking at a report over the real
data, and will change once it has been.

No database, no network — those belong to the callers, so this stays testable
and cheap enough to run over the whole library repeatedly.
"""
import difflib
import re
import unicodedata
from dataclasses import dataclass, field, fields
from typing import Optional

KEEP = 'keep'
REWRITE = 'rewrite'
SPLIT = 'split'
REJECT = 'reject'
UNKNOWN = 'unknown'

DEFAULT_AFFIX_PATTERNS = (
    r'\*+\s*free\s*(download|dl)\s*\*+',
    r'\[\s*free\s*(download|dl)\s*\]',
    r'\(\s*free\s*(download|dl)\s*\)',
    r'\bfree\s*(download|dl)\b',
    r'\bout\s*now\b',
    r'\bpremiere\b',
    r'\bofficial\s*(video|audio|music\s*video)?\b',
    r'\bvevo\b',
    r'-\s*topic$',
    r'^#\s*\d+',
    r'^\d+\s*[.\-)]\s*',
)

DEFAULT_STOPWORDS = (
    'de', 'het', 'een', 'en', 'van', 'wij', 'we', 'je', 'jij', 'ik', 'dat', 'als',
    'niet', 'maar', 'voor', 'met', 'the', 'and', 'of', 'you', 'is', 'are', 'this',
    'that', 'when', 'what', 'my', 'your',
)


@dataclass
class AnalyzerConfig:
    """Every threshold the analyzer uses, in one place.

    Defaults are a starting point, not a recommendation: they are meant to be
    tuned against a report over the real library and then stored in ConfigStore.
    """
    affix_patterns: tuple = DEFAULT_AFFIX_PATTERNS
    stopwords: tuple = DEFAULT_STOPWORDS
    junk_score_threshold: int = 4
    junk_long_name_chars: int = 40
    junk_min_words: int = 4
    # A single wrong character in a name of n characters scores 1 - 1/n, so 0.90
    # would only catch typos in names of 10 characters and up - and most artist
    # names are shorter than that. 0.87 reaches down to 8-character names.
    fuzzy_rewrite_threshold: float = 0.87
    segment_fuzzy_threshold: float = 0.9
    segment_min_length: int = 4
    max_segments: int = 3
    bootstrap_min_tracks: int = 5

    @classmethod
    def from_dict(cls, values: Optional[dict]) -> 'AnalyzerConfig':
        """Build a config from a plain dict, ignoring keys we do not know."""
        if not values:
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in values.items() if k in known})


@dataclass
class Proposal:
    """What to do with one raw artist string, and why.

    `values` is what the tag should end up containing: the name itself for a
    keep, one name for a rewrite, several for a split, and nothing for a reject.
    An `unknown` proposal carries the input unchanged — it means "no mechanical
    answer", which is a queue entry for a human or an external lookup, never a
    decision.
    """
    kind: str
    values: list
    confidence: int
    evidence: list = field(default_factory=list)


def normalize(name: str) -> str:
    """Casing-, accent- and punctuation-insensitive key for an artist name."""
    decomposed = unicodedata.normalize('NFKD', name or '')
    without_accents = ''.join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', without_accents.lower()).strip()


def _squash(name: str) -> str:
    """Normalized key with the separators removed, for concatenation matching."""
    return normalize(name).replace(' ', '')


class ArtistNameAnalyzer:
    """Proposes an interpretation for a raw artist string.

    `known_artists` is the dictionary everything is matched against — the names
    already approved. It is what makes the analyzer improve in passes: every
    approved artist rescues the polluted variants of itself in the next run.
    """

    def __init__(self, known_artists=None, config: Optional[AnalyzerConfig] = None):
        self.config = config or AnalyzerConfig()
        self._known_by_key: dict = {}
        self._known_by_squash: dict = {}
        self.set_known_artists(known_artists or [])
        self._affix_res = [re.compile(p, re.IGNORECASE) for p in self.config.affix_patterns]

    def set_known_artists(self, names) -> None:
        """Replace the approved-artist dictionary."""
        self._known_by_key = {}
        self._known_by_squash = {}
        for name in names:
            key = normalize(name)
            if not key:
                continue
            self._known_by_key.setdefault(key, name)
            self._known_by_squash.setdefault(_squash(name), name)

    def known(self, name: str) -> Optional[str]:
        """The approved spelling of `name`, or None if it is not approved."""
        return self._known_by_key.get(normalize(name))

    def strip_affixes(self, name: str) -> tuple:
        """Remove promo noise from around a name.

        Returns the remainder and what was removed. Applied repeatedly, because
        one name can carry several layers (`**FREE DOWNLOAD** #1 Artist`).
        """
        removed = []
        current = name
        for _ in range(len(self._affix_res) + 1):
            before = current
            for pattern in self._affix_res:
                match = pattern.search(current)
                if match and match.group().strip():
                    removed.append(match.group().strip())
                    current = pattern.sub(' ', current, count=1)
            current = current.strip(' \t-_&,;:|/\\*[](){}"\'')
            current = re.sub(r'\s+', ' ', current).strip()
            if current == before:
                break
        return current, removed

    def junk_score(self, name: str) -> tuple:
        """How sentence-like or malformed a name is, with the reasons.

        A score, not a rule, because the signals are individually weak: four
        words is normal for an artist, and so is a bracket. Together with Dutch
        or English function words they stop being normal.
        """
        score = 0
        reasons = []
        words = [w for w in re.split(r'\s+', name.strip()) if w]
        stopwords = [w for w in words if normalize(w) in self.config.stopwords]
        if stopwords:
            score += 2 * len(stopwords)
            reasons.append(f"contains function words: {', '.join(stopwords)}")
        if len(words) >= self.config.junk_min_words:
            score += 1
            reasons.append(f'{len(words)} words')
        if name.count('(') != name.count(')') or name.count('[') != name.count(']'):
            score += 2
            reasons.append('unbalanced brackets')
        if len(name) > self.config.junk_long_name_chars:
            score += 1
            reasons.append(f'{len(name)} characters')
        if re.search(r'[.,!?]\s', name):
            score += 2
            reasons.append('sentence punctuation')
        return score, reasons

    def segment(self, name: str) -> Optional[list]:
        """Split a name glued together without a separator into approved names.

        Only attempted on names without whitespace: a string with spaces that
        needs splitting is a delimiter problem for the tagger, not a glued name,
        and guessing there would invent artists that were never in the tag.
        Every segment must match an approved artist, so the dictionary — not the
        analyzer — decides where the boundaries are.
        """
        if re.search(r'\s', name.strip()):
            return None
        squashed = _squash(name)
        if not squashed or squashed in self._known_by_squash:
            return None
        result = self._segment(squashed, depth=0)
        if result and len(result) >= 2:
            return result
        return None

    def _segment(self, remainder: str, depth: int) -> Optional[list]:
        if not remainder:
            return []
        if depth >= self.config.max_segments:
            return None
        for candidate_key, candidate_name in self._known_by_squash.items():
            if len(candidate_key) < self.config.segment_min_length:
                continue
            for length in {len(candidate_key) - 1, len(candidate_key), len(candidate_key) + 1}:
                if length < self.config.segment_min_length or length > len(remainder):
                    continue
                prefix = remainder[:length]
                if prefix != candidate_key:
                    ratio = difflib.SequenceMatcher(None, prefix, candidate_key).ratio()
                    if ratio < self.config.segment_fuzzy_threshold:
                        continue
                rest = self._segment(remainder[length:], depth + 1)
                if rest is not None:
                    return [candidate_name] + rest
        return None

    def closest_known(self, name: str) -> tuple:
        """The approved artist most similar to `name`, with its ratio."""
        key = normalize(name)
        if not key:
            return None, 0.0
        best_name = None
        best_ratio = 0.0
        for candidate_key, candidate_name in self._known_by_key.items():
            ratio = difflib.SequenceMatcher(None, key, candidate_key).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_name = candidate_name
        return best_name, best_ratio

    def propose(self, raw_name: str) -> Proposal:
        """Decide what to propose for one raw artist string."""
        name = (raw_name or '').strip()
        if not name:
            return Proposal(REJECT, [], 100, ['empty name'])

        approved = self.known(name)
        if approved:
            if approved == name:
                return Proposal(KEEP, [approved], 100, ['already approved'])
            return Proposal(REWRITE, [approved], 100, [f"approved spelling is '{approved}'"])

        if not re.search(r'[A-Za-z]', name):
            return Proposal(REJECT, [], 95, ['contains no letters'])

        stripped, removed = self.strip_affixes(name)
        evidence = []
        if removed:
            evidence.append(f"removed noise: {', '.join(removed)}")
        if not stripped:
            return Proposal(REJECT, [], 95, evidence + ['nothing left after removing noise'])

        approved = self.known(stripped)
        if approved:
            return Proposal(REWRITE, [approved], 95, evidence + [f"remainder matches approved '{approved}'"])

        score, reasons = self.junk_score(stripped)
        if score >= self.config.junk_score_threshold:
            return Proposal(REJECT, [], min(95, 50 + 10 * score), evidence + reasons)

        segments = self.segment(stripped)
        if segments:
            return Proposal(SPLIT, segments, 85, evidence + [f"glued approved names: {' + '.join(segments)}"])

        closest, ratio = self.closest_known(stripped)
        if closest and ratio >= self.config.fuzzy_rewrite_threshold:
            return Proposal(REWRITE, [closest], int(ratio * 100), evidence + [f"looks like approved '{closest}' ({ratio:.2f})"])

        if removed:
            evidence.append('noise removed but remainder is not approved')
        return Proposal(UNKNOWN, [stripped], 0, evidence or ['no mechanical match'])
