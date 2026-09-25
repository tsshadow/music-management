"""Turn a raw genre string into a proposal, with the reasoning attached.

The genre curation queue fills with strings that fail in a handful of
recognisable ways: two genres joined by a slash (`Frenchcore/Terror`), glued
together (`Jungleterror`), blended into one word (`Upterror` is the start of
`Uptempo Hardcore` and the whole of `Terror`), a misspelling (`Harddcore`), a
genre with promo noise around it (`Hardstyle 2018`, `Happy Hardcore Classics`),
or something that is not a genre at all -- an artist, a label, a word from a
sentence.

This module proposes what to do with one such string. It never decides: it
returns a proposal, a confidence and the chain of reasoning that produced it, so
a human can see why. The dictionary it matches against is the curator's own past
work -- approved genres, the corrections already made, the tagger's artist and
label links -- so every decision makes the next run find more.

No database, no network: the callers own those, which keeps this testable and
cheap enough to run over the whole queue on every click.
"""

import difflib
import re
from collections import defaultdict
from dataclasses import dataclass, field, fields

from services.common.text_normalize import ascii_name_key

KEEP = 'keep'
REWRITE = 'rewrite'
SPLIT = 'split'
REJECT = 'reject'
UNKNOWN = 'unknown'
KINDS = (KEEP, REWRITE, SPLIT, REJECT, UNKNOWN)

#: Things that sit *between* genres in one tag. A slash is the common one; the
#: backslash is what an escaped slash looks like after some tagger mangled it.
DEFAULT_SEPARATORS = ('/', '\\', ',', '|', ' & ', ' + ', ' and ', ' en ', ' vs ')

#: Words that decorate a genre without being part of it: `Hardstyle 2018`,
#: `Happy Hardcore Classics`, `Add "Uptempo"` (a tagging tool's own prompt).
DEFAULT_NOISE_PATTERNS = (
    r'(?<!\d)(19|20)\d\d\b',
    r'\b\d{2}s\b',
    r'\bmusic\b',
    r'\bclassics?\b',
    r'\banthems?\b',
    r'\bmainstage\b',
    r'\bbest\b',
    r'\bonly\b',
    r'\bfestival\b',
    r'\bremix(es)?\b',
    r'\brmx\b',
    r'\bmix(es)?\b',
    r'\bedition\b',
    r'\bvol(ume)?\s*\d+\b',
    r'\bhits\b',
    r'\btop\s*\d+\b',
    r'^add\b',
    r'^aggiungi\b',
    r'^ajouter\b',
    r'\btoevoegen\b',
    r'\bgym\b',
)

#: A name carrying one of these is a label, not a genre.
DEFAULT_LABEL_WORDS = ('records', 'recordings', 'recs', 'digital', 'label', 'productions', 'entertainment', 'audio')

#: A name carrying one of these came from a publishing pipeline, not a genre field.
DEFAULT_PROMO_WORDS = (
    'free download',
    'premiere',
    'out now',
    'podcast',
    'radio',
    'sample pack',
    'demo',
    'clip',
    'soundcloud',
    'youtube',
    'spotify',
    'weekly',
    'selection',
    'release',
    'mixtape',
    'livestream',
    'episode',
    'promo',
    'exclusive',
    'warez',
    'tracklist',
    'talent pool',
    'contest',
)

#: Suffixes that make a word read as a genre even when nothing approved contains
#: it (`Energycore`, `Piepcore`, `Lemonstyle`). A name without any genre-like
#: part and without any match is proposed for rejection; one with such a part is
#: left to the human, because it may be a genre nobody approved yet.
DEFAULT_GENRE_STEMS = ('core', 'style', 'tempo', 'tek', 'tekk', 'step', 'tronic', 'wave', 'beat', 'bass', 'house')


def normalize(name: str) -> str:
    """Casing-, accent- and punctuation-insensitive key for a genre name.

    The same key the tagger (`GenreRulesHelper.normalize`) and the curation page
    use. It lives in `services.common.text_normalize`, which imports nothing that
    needs a database driver -- the reason this module used to carry a copy.
    """
    return ascii_name_key(name)


@dataclass
class GenreAnalyzerConfig:
    """Every threshold the analyzer uses, in one place."""

    fuzzy_rewrite_threshold: float = 0.88
    token_fuzzy_threshold: float = 0.9
    rejected_fuzzy_threshold: float = 0.9
    #: Shortest piece a glued name (`Jungleterror`) is cut into.
    min_segment_length: int = 3
    #: Shortest prefix or suffix a blend (`Upterror`) may borrow from a genre when
    #: the other side is a whole genre.
    min_blend_length: int = 2
    #: Shortest fragment on *both* sides of a blend when neither is a whole genre
    #: (`Frenchtempo`); shorter fragments blend every word into something.
    min_fragment_length: int = 5
    separators: tuple = DEFAULT_SEPARATORS
    noise_patterns: tuple = DEFAULT_NOISE_PATTERNS
    label_words: tuple = DEFAULT_LABEL_WORDS
    promo_words: tuple = DEFAULT_PROMO_WORDS
    genre_stems: tuple = DEFAULT_GENRE_STEMS

    @classmethod
    def from_dict(cls, values: dict | None) -> 'GenreAnalyzerConfig':
        """Build a config from a plain dict, ignoring keys we do not know."""
        if not values:
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in values.items() if k in known})


@dataclass
class Proposal:
    """What to do with one raw genre string, and why.

    `values` is what the tag should end up containing: the name itself for a
    keep, one approved genre for a rewrite, several for a split, nothing for a
    reject or an unknown. An `unknown` proposal means "no mechanical answer" --
    a queue entry for a human, never a decision.
    """

    kind: str
    values: list
    confidence: int
    evidence: list = field(default_factory=list)


@dataclass
class GenreDictionary:
    """Everything a proposal can be matched against.

    `approved` maps an approved genre's name to its popularity (tracks carrying
    it), used to rank blends. `aliases` maps a decided name to the approved names
    it is rewritten to. `rejected` holds names a human dropped without a
    correction. `artists` and `labels` map a name to the genre the tagger page
    links it to, or `None` when it is merely known to be an artist or label.
    """

    approved: dict = field(default_factory=dict)
    aliases: dict = field(default_factory=dict)
    rejected: set = field(default_factory=set)
    artists: dict = field(default_factory=dict)
    labels: dict = field(default_factory=dict)


def build_dictionary(approved, expansions, rejected=(), artists=(), labels=()) -> GenreDictionary:
    """Assemble the dictionary from what the database holds, resolving aliases.

    @param approved: iterable of `(name, popularity)` for the white genres.
    @param expansions: iterable of `(name, target_name)` in position order, for
        every genre with a correction, white or black.
    @param rejected: names of black genres without a correction.
    @param artists: iterable of `(name, linked_genre_or_None)`.
    @param labels: iterable of `(name, linked_genre_or_None)`.

    An approved genre that itself has a correction (`RAW` is white and expands to
    `Raw Hardstyle`) is an alias, not a target: the tagger never writes it, so
    advice should not point at it either. An alias only counts when its targets
    end up approved: a correction that points at a name later rejected would
    otherwise be advice to make the same mistake again. Two levels of
    indirection are followed, so an alias pointing at an alias still lands on an
    approved name. An approved genre whose own name is a `;`-joined list (a
    legacy of `corrected_genre`) is treated as an alias to its parts rather than
    offered as a target.
    """
    dictionary = GenreDictionary()
    raw_targets: dict = defaultdict(list)
    for name, target in expansions:
        if name and target and target != name and target not in raw_targets[name]:
            raw_targets[name].append(target)
    joined_lists = {}
    for name, popularity in approved:
        if not name or name in raw_targets:
            continue
        if ';' in name:
            joined_lists[name] = [part.strip() for part in name.split(';') if part.strip()]
        else:
            dictionary.approved[name] = int(popularity or 0)

    def resolve(target: str, depth: int) -> list:
        if target in dictionary.approved:
            return [target]
        if depth == 0:
            return []
        pieces = joined_lists.get(target) or raw_targets.get(target, [])
        return [part for piece in pieces for part in resolve(piece, depth - 1)]

    for name, targets in list(raw_targets.items()) + list(joined_lists.items()):
        resolved = []
        for target in targets:
            for part in resolve(target, 2):
                if part not in resolved and part != name:
                    resolved.append(part)
        if resolved:
            dictionary.aliases[name] = resolved
    dictionary.rejected = {name for name in rejected if name and name not in dictionary.aliases}
    dictionary.artists = {name: genre for name, genre in artists if name}
    dictionary.labels = {name: genre for name, genre in labels if name}
    return dictionary


def _squash(key: str) -> str:
    return key.replace(' ', '')


def _has_letters(name: str) -> bool:
    return any(c.isalpha() for c in name or '')


class GenreNameAnalyzer:
    """Proposes an interpretation for a raw genre string against a dictionary."""

    def __init__(self, dictionary: GenreDictionary | None = None, config: GenreAnalyzerConfig | None = None):
        self.config = config or GenreAnalyzerConfig()
        self.dictionary = dictionary or GenreDictionary()
        self._noise_res = [re.compile(p, re.IGNORECASE) for p in self.config.noise_patterns]
        self._index()

    # ------------------------------------------------------------------ indexing

    def _index(self) -> None:
        """Lookup tables keyed by normalized name and by squashed (space-free) name.

        Every entry resolves to the list of approved names it stands for: an
        approved genre to itself, an alias to its targets. The artist and label
        maps are keyed the same way so `dr peacock` finds `Dr Peacock`.
        """
        self._by_key: dict = {}
        self._display: dict = {}
        self._key_by_squash: dict = {}
        for name in self.dictionary.approved:
            self._add(name, [name])
        for name, targets in self.dictionary.aliases.items():
            self._add(name, targets)
        self._rejected_keys = {normalize(name): name for name in self.dictionary.rejected}
        self._artist_keys = {normalize(name): (name, genre) for name, genre in self.dictionary.artists.items()}
        self._label_keys = {normalize(name): (name, genre) for name, genre in self.dictionary.labels.items()}
        # Tokens of every approved genre, so a word can be recognised as genre-like
        # without being a genre on its own (`melodic`, `early`). Alias names do not
        # count: `Vocal Trance` -> `Trance` teaches that `vocal` is a modifier the
        # curator drops, and that lesson is kept as such.
        self._genre_tokens = {
            token for name in self.dictionary.approved for token in normalize(name).split(' ') if len(token) >= 3
        }
        self._modifiers: dict = {}
        for name, targets in self.dictionary.aliases.items():
            target_tokens = {token for target in targets for token in normalize(target).split(' ')}
            for token in normalize(name).split(' '):
                if len(token) >= 3 and token not in target_tokens and token not in self._genre_tokens:
                    self._modifiers.setdefault(token, name)
        self._keys_by_length: dict = defaultdict(list)
        for key in self._by_key:
            self._keys_by_length[len(key)].append(key)

    def _add(self, name: str, targets: list) -> None:
        key = normalize(name)
        if not key or key in self._by_key:
            return
        self._by_key[key] = targets
        self._display[key] = name
        self._key_by_squash.setdefault(_squash(key), key)

    # ------------------------------------------------------------------ lookups

    def _key_for(self, text: str) -> str | None:
        """The dictionary key the text is: exact, or the same without spaces.

        An ampersand is tried as the letter it stands for too, so `D&B` reaches
        a `Dnb` the curator already corrected.
        """
        variants = [text or '']
        if '&' in variants[0]:
            variants.append(variants[0].replace('&', ' n '))
        for variant in variants:
            key = normalize(variant)
            if not key:
                continue
            if key in self._by_key:
                return key
            squashed = self._key_by_squash.get(_squash(key))
            if squashed:
                return squashed
        return None

    def lookup(self, text: str) -> list | None:
        """Approved names the text stands for, or None when it is not known."""
        key = self._key_for(text)
        return list(self._by_key[key]) if key else None

    def closest_known(self, text: str, threshold: float | None = None) -> tuple:
        """The known key most similar to `text` with its ratio, or `(None, ratio)`.

        Candidates are limited to lengths that could still reach the threshold,
        which keeps the whole queue affordable against a few hundred names.
        """
        key = normalize(text)
        if not key:
            return None, 0.0
        threshold = self.config.fuzzy_rewrite_threshold if threshold is None else threshold
        matcher = difflib.SequenceMatcher(None)
        matcher.set_seq2(key)
        best_key, best_ratio = None, 0.0
        shortest = int(len(key) * threshold)
        longest = int(len(key) / threshold) + 1
        for length in range(max(1, shortest), longest + 1):
            for candidate in self._keys_by_length.get(length, ()):
                matcher.set_seq1(candidate)
                if matcher.real_quick_ratio() <= best_ratio or matcher.quick_ratio() <= best_ratio:
                    continue
                ratio = matcher.ratio()
                if ratio > best_ratio:
                    best_key, best_ratio = candidate, ratio
        if best_key is None or best_ratio < threshold:
            return None, best_ratio
        return best_key, best_ratio

    def _resolve_part(self, text: str) -> tuple:
        """Targets for one piece of a composite and the reasoning; `(None, why)` when nothing fits."""
        targets = self.lookup(text)
        if targets:
            return targets, None
        key, ratio = self.closest_known(text)
        if key:
            return list(self._by_key[key]), f"'{text.strip()}' looks like '{self._display[key]}' ({ratio:.2f})"
        return None, f"no match for '{text.strip()}'"

    def _looks_like_genre(self, key: str) -> bool:
        """Whether a name that matched nothing still reads as a genre.

        A word of a known genre inside it (`hard` in `Hardpsy`, `melodic` on its
        own) or a genre-like ending (`Energycore`) is enough. `Tafelpoot` has
        neither.
        """
        for token in key.split(' '):
            if token in self._genre_tokens:
                return True
            if any(known in token for known in self._genre_tokens if len(known) >= 4):
                return True
            if any(token.endswith(stem) and len(token) > len(stem) for stem in self.config.genre_stems):
                return True
        return False

    @staticmethod
    def _merge(*lists) -> list:
        merged: list = []
        for targets in lists:
            for target in targets or []:
                if target not in merged:
                    merged.append(target)
        return merged

    @staticmethod
    def _kind_for(targets: list) -> str:
        return SPLIT if len(targets) > 1 else REWRITE

    # ------------------------------------------------------------------ passes

    def _split_on_separators(self, name: str) -> Proposal | None:
        pattern = '|'.join(re.escape(sep) for sep in self.config.separators)
        parts = [part.strip() for part in re.split(pattern, name, flags=re.IGNORECASE)]
        parts = [part for part in parts if part]
        if not parts:
            return None
        if len(parts) == 1:
            if parts[0] == name.strip():
                return None
            # A stray separator ('Hardcore/'): the one part is the whole answer.
            targets, why = self._resolve_part(parts[0])
            if not targets:
                return None
            stray = [f"'{parts[0]}' with the stray separator removed"] + ([why] if why else [])
            return Proposal(self._kind_for(targets), targets, 90, stray)
        resolved: list = []
        evidence: list = []
        missing: list = []
        for part in parts:
            targets, why = self._resolve_part(part)
            if why:
                evidence.append(why)
            if targets:
                resolved = self._merge(resolved, targets)
            else:
                missing.append(part)
        if not resolved or len(missing) > len(parts) - len(missing):
            return None
        head = f"{len(parts)} genres joined by a separator: {' + '.join(parts)}"
        genre_like = [part for part in missing if self._looks_like_genre(normalize(part))]
        if genre_like:
            return Proposal(UNKNOWN, [], 0, [head] + evidence + [f"'{', '.join(genre_like)}' reads as a genre too"])
        if missing:
            return Proposal(SPLIT, resolved, 60, [head] + evidence + [f"dropped: {', '.join(missing)}"])
        return Proposal(SPLIT, resolved, 90, [head] + evidence)

    def _strip_noise(self, name: str) -> Proposal | None:
        stripped, removed = name, []
        for pattern in self._noise_res:
            match = pattern.search(stripped)
            if match:
                removed.append(match.group(0).strip())
                stripped = pattern.sub(' ', stripped)
        if not removed:
            return None
        stripped = re.sub(r'["\'«»]', ' ', stripped)
        stripped = re.sub(r'\s+', ' ', stripped).strip(' -:.')
        if not stripped:
            return None
        targets, why = self._resolve_part(stripped)
        if not targets:
            return None
        evidence = [f"'{', '.join(removed)}' is not part of the genre"] + ([why] if why else [])
        return Proposal(self._kind_for(targets), targets, 85, evidence)

    @staticmethod
    def _matches_word(key: str, words) -> str | None:
        for word in words:
            if re.search(rf'\b{re.escape(word)}\b', key):
                return word
        return None

    def _segment_tokens(self, key: str) -> Proposal | None:
        """Split `hardcore early terror` into known phrases covering the tokens.

        Fewest phrases wins, so `Hard Techno` stays one genre rather than `Hard`
        plus `Techno`. A token nothing covers is dropped when it is a mere
        modifier (`gym`, `vocal`) and blocks the proposal when it reads as a
        genre itself, because then the human has to say what it is.
        """
        tokens = key.split(' ')
        if len(tokens) < 2:
            return None
        n = len(tokens)
        best: list = [None] * (n + 1)
        best[0] = []
        for end in range(1, n + 1):
            candidates = []
            for start in range(end):
                if best[start] is None:
                    continue
                phrase = ' '.join(tokens[start:end])
                targets, why = self._phrase(phrase)
                if targets is not None:
                    candidates.append(best[start] + [(phrase, targets, why)])
                elif end - start == 1:
                    candidates.append(best[start] + [(phrase, None, None)])
            if candidates:
                best[end] = min(candidates, key=lambda segs: (sum(1 for s in segs if s[1] is None), len(segs)))
        segments = best[n]
        if not segments:
            return None
        covered = [seg for seg in segments if seg[1] is not None]
        dropped = [seg[0] for seg in segments if seg[1] is None]
        if not covered or len(covered) < len(dropped):
            return None
        resolved = self._merge(*[seg[1] for seg in covered])
        evidence = [seg[2] for seg in covered if seg[2]]
        known = ' + '.join(seg[0] for seg in covered)
        genre_like = [word for word in dropped if self._looks_like_genre(word)]
        if genre_like:
            return Proposal(UNKNOWN, [], 0, [f"'{known}' is known, but '{', '.join(genre_like)}' reads as a genre too"])
        head = f'known genres in the name: {known}'
        if dropped:
            learned = [word for word in dropped if word in self._modifiers]
            for word in learned:
                evidence.append(
                    f"'{word}' was dropped before ('{self._modifiers[word]}' -> {' + '.join(self.dictionary.aliases[self._modifiers[word]])})"
                )
            confidence = 70 if len(learned) == len(dropped) else 60
            return Proposal(
                self._kind_for(resolved), resolved, confidence, [head] + evidence + [f"dropped: {', '.join(dropped)}"]
            )
        return Proposal(self._kind_for(resolved), resolved, 85, [head] + evidence)

    def _phrase(self, phrase: str) -> tuple:
        """A token run as a known genre: exact, or spelled slightly wrong.

        The fuzzy match has to keep the word count, so a run of two words is
        only ever a two-word genre with a typo, never a one-word genre plus a
        stray word -- that case is the dropped-modifier path.
        """
        targets = self.lookup(phrase)
        if targets:
            return targets, None
        if len(phrase) >= 5:
            key, ratio = self.closest_known(phrase, self.config.token_fuzzy_threshold)
            if key and key.count(' ') == phrase.count(' '):
                return list(self._by_key[key]), f"'{phrase}' looks like '{self._display[key]}' ({ratio:.2f})"
        return None, None

    def _segment_glued(self, squashed: str) -> Proposal | None:
        """Cut `jungleterror` into known names with nothing left over."""
        if len(squashed) < 2 * self.config.min_segment_length:
            return None
        pieces = self._segment(squashed, 0)
        if not pieces or len(pieces) < 2:
            return None
        keys = [self._key_by_squash[piece] for piece in pieces]
        resolved = self._merge(*[self._by_key[key] for key in keys])
        shown = ' + '.join(self._display[key] for key in keys)
        return Proposal(self._kind_for(resolved), resolved, 80, [f'glued genres: {shown}'])

    def _segment(self, remainder: str, depth: int) -> list | None:
        if not remainder:
            return []
        if depth >= 4:
            return None
        # Longest piece first, so `hardcore` is not cut into `hard` + `core`.
        for length in range(len(remainder), self.config.min_segment_length - 1, -1):
            if remainder[:length] in self._key_by_squash:
                rest = self._segment(remainder[length:], depth + 1)
                if rest is not None:
                    return [remainder[:length]] + rest
        return None

    def _blend(self, squashed: str) -> Proposal | None:
        """`upterror`: a prefix of one genre fused with the end of another.

        Preferably one side is a whole genre; two fragments only count when both
        are long enough to mean something (`french` + `tempo`). Candidates rank
        by how much of the name is a whole genre and then by popularity, so `Up`
        prefers `Uptempo Hardcore` over a rarer genre that also starts with `up`;
        the runners-up stay in the evidence for the human to overrule.
        """
        minimum = self.config.min_blend_length
        candidates = []
        for cut in range(minimum, len(squashed) - minimum + 1):
            head, tail = squashed[:cut], squashed[cut:]
            head_key = self._key_by_squash.get(head)
            tail_key = self._key_by_squash.get(tail)
            if head_key and tail_key:
                continue  # a glued name, handled before this
            if tail_key:
                for key in self._keys_by_prefix(head):
                    candidates.append((len(tail), key, tail_key, head, tail))
            elif head_key:
                for key in self._keys_by_suffix(tail):
                    candidates.append((len(head), head_key, key, head, tail))
            elif min(len(head), len(tail)) >= self.config.min_fragment_length:
                for first in self._keys_by_prefix(head):
                    for second in self._keys_by_suffix(tail):
                        candidates.append((0, first, second, head, tail))
        if not candidates:
            return None
        # Whole-genre side first, then popularity, then a genre over an alias to
        # it, so the evidence names `Uptempo Hardcore` rather than a misspelling
        # someone corrected to it.
        candidates.sort(
            key=lambda c: (
                -c[0],
                -(self._popularity(c[1]) + self._popularity(c[2])),
                self._display[c[1]] not in self.dictionary.approved,
                self._display[c[2]] not in self.dictionary.approved,
            )
        )
        whole, first, second, head, tail = candidates[0]
        resolved = self._merge(self._by_key[first], self._by_key[second])
        if len(resolved) < 2:
            return None
        pair = f'{self._display[first]} + {self._display[second]}'
        evidence = [f"blend: '{head}' begins {self._display[first]}, '{tail}' ends {self._display[second]}"]
        others = []
        for candidate in candidates[1:]:
            alt = f'{self._display[candidate[1]]} + {self._display[candidate[2]]}'
            if alt != pair and alt not in others:
                others.append(alt)
            if len(others) == 3:
                break
        if others:
            evidence.append(f"also possible: {'; '.join(others)}")
        return Proposal(SPLIT, resolved, 65 if whole else 55, evidence)

    def _keys_by_prefix(self, prefix: str) -> list:
        return [key for squash, key in self._key_by_squash.items() if squash != prefix and squash.startswith(prefix)]

    def _keys_by_suffix(self, suffix: str) -> list:
        return [key for squash, key in self._key_by_squash.items() if squash != suffix and squash.endswith(suffix)]

    def _popularity(self, key: str) -> int:
        return sum(self.dictionary.approved.get(target, 0) for target in self._by_key.get(key, ()))

    def _closest_rejected(self, key: str) -> tuple:
        threshold = self.config.rejected_fuzzy_threshold
        best_key, best_ratio = None, 0.0
        matcher = difflib.SequenceMatcher(None)
        matcher.set_seq2(key)
        for candidate in self._rejected_keys:
            if abs(len(candidate) - len(key)) > len(key) * (1 - threshold) + 1:
                continue
            matcher.set_seq1(candidate)
            if matcher.quick_ratio() <= best_ratio:
                continue
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_key, best_ratio = candidate, ratio
        if best_key is None or best_ratio < threshold:
            return None, best_ratio
        return best_key, best_ratio

    # ------------------------------------------------------------------ propose

    def propose(self, raw_name: str) -> Proposal:
        """Decide what to propose for one raw genre string."""
        name = (raw_name or '').strip()
        key = normalize(name)
        if not key:
            return Proposal(REJECT, [], 100, ['empty name'])
        if not _has_letters(name):
            return Proposal(REJECT, [], 95, ['contains no letters'])
        proposal, hint = self._propose(name, key)
        if hint and proposal.kind in (REJECT, UNKNOWN):
            proposal.evidence.append(hint)
        return proposal

    def _propose(self, name: str, key: str) -> tuple:
        """The proposal and, when the name is also an artist or label, a hint saying so.

        The artist and label lists are polluted enough (`Melodic`, `Future`) that a
        collision only decides anything when the name does not read as a genre;
        otherwise it is a footnote on whatever the other passes conclude.
        """
        hint = None

        known_key = self._key_for(name)
        if known_key:
            targets = list(self._by_key[known_key])
            if known_key == key and targets == [self._display[known_key]]:
                return Proposal(KEEP, targets, 100, ['already approved']), None
            if known_key == key:
                reason = f"'{self._display[known_key]}' was already decided as {' + '.join(targets)}"
            else:
                reason = f"same name as '{self._display[known_key]}' without spaces or punctuation"
            return Proposal(self._kind_for(targets), targets, 95, [reason]), None

        for role, index in (('an artist', self._artist_keys), ('a label', self._label_keys)):
            known = index.get(key)
            if not known:
                continue
            found, genre = known
            linked = self.lookup(genre) if genre else None
            if linked:
                targets = linked
                return Proposal(
                    self._kind_for(targets), targets, 90, [f"'{found}' is {role} linked to {genre} on the tagger page"]
                ), None
            if not self._looks_like_genre(key):
                return Proposal(
                    REJECT,
                    [],
                    85,
                    [f"'{found}' is {role}, not a genre (link it to a genre on the tagger page instead)"],
                ), None
            hint = f"'{found}' is also {role}"
            break

        proposal = self._split_on_separators(name) or self._strip_noise(name)
        if proposal:
            return proposal, hint

        word = self._matches_word(key, self.config.label_words)
        if word:
            return Proposal(REJECT, [], 80, [f"'{word}' makes this read as a label name"]), hint
        word = self._matches_word(key, self.config.promo_words)
        if word:
            return Proposal(REJECT, [], 80, [f"'{word}' makes this read as promo or publishing noise"]), hint

        closest, ratio = self.closest_known(name)
        if closest:
            targets = list(self._by_key[closest])
            # One changed letter in a short word is a different word as often as a
            # typo (`Mental` / `Metal`), so a short match is worth less.
            confidence = int(ratio * 100) - (10 if len(key) < 8 else 0)
            return Proposal(
                self._kind_for(targets), targets, confidence, [f"looks like '{self._display[closest]}' ({ratio:.2f})"]
            ), hint

        proposal = self._segment_tokens(key)
        if proposal:
            return proposal, hint

        squashed = _squash(key)
        if ' ' not in key:
            proposal = self._segment_glued(squashed) or self._blend(squashed)
            if proposal:
                return proposal, hint

        rejected_key, ratio = self._closest_rejected(key)
        if rejected_key:
            return Proposal(
                REJECT, [], 75, [f"looks like '{self._rejected_keys[rejected_key]}', which was rejected ({ratio:.2f})"]
            ), hint

        if len(squashed) <= 2:
            return Proposal(REJECT, [], 70, ['too short to be a genre']), hint
        if not self._looks_like_genre(key):
            return Proposal(REJECT, [], 50, ['resembles no known genre and has no genre-like part']), hint
        return Proposal(UNKNOWN, [], 0, ['reads as a genre, but matches nothing approved']), hint
