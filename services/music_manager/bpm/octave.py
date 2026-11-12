"""Which octave of a measured tempo is the track's tempo: T/2, T or 2T, weighed on evidence.

docs/designs/bpm-octave/technical.md (bug report 140). The estimator measures a pulse, and a
pulse at 128 is also a pulse at 64 and at 256: it cannot tell a ballad from its double time, nor a
hardstyle kick from its half-time feel. The previous rule (`bands.fold_into_band` on the track's
genres, else on its artist's commonest genre) moved every estimate into a hand-set band, and it
failed two ways on production:

- André Hazes -- "Vaag en Stil" (raw 64) went to 256: the track has no genre of its own, and its
  artist's commonest genre came from hardstyle and uptempo *remixes* of his songs.
- The Silence -- "Nothing" (raw 115, a clear pulse) went to 230: the industrial hardcore band
  starts at 140, so a genuinely slow track had nowhere to stay.

This module replaces the band as the decision. Each candidate `c` in {T/2, T, 2T} (40-500 BPM)
gets a score, the sum of independent terms in natural-log units:

- **estimate**: the raw estimate is the estimator's own choice (`STAY_BONUS`), and when the comb
  scores of the neighbours are known, a neighbour that scores far below the estimate is penalised
  (`audio_term`). On the evaluation set a correct octave neighbour scored at least ~0.64 of the
  estimate, so only a clearly lower score counts against it (The Silence's 230 scored 0.47).
- **label**, **artist**, **genre**: learned priors (`priors.py`) -- a Gaussian in log2(BPM) around
  the centre of the confident measurements on that label, that artist's own (non-remix) tracks, or
  that genre -- weighted by how many samples back them. A genre without a learned prior falls back
  to its hand-set band (`bands.GENRE_BANDS`), read as a Gaussian with the band's edges at 1 sigma.
- **folder**: a Soundcloud or YouTube upload's uploader folder (`/mnt/music/Soundcloud/<uploader>/`),
  learned like the artist's prior and weighted the same, with the track itself left out of its own
  folder's prior (issue #241). An uploader mostly posts one kind of music, and the folder covers 99%
  of those uploads where the credited artist covers 69% (production, 2026-11-12).
- **path**: tracks under a mainstream compilation folder (Hitzone, Spotify, Lidarr, Top 100) are
  pop and dance: a prior around 115 BPM.
- **getsongbpm**: the tempo GetSongBPM lists for the same artist and title (issue #152), a strong
  prior for mainstream tracks that have no label or artist prior. Only looked up and only applied
  for those (`weak_priors`), and only when it lies close to one of the candidates: a listed tempo
  that matches no octave of the measurement is a different recording, not evidence.
- **neutral**: a broad prior around 125 BPM that settles it when nothing else speaks, strongest
  when there is no genre, label or artist evidence at all. It is what folds a genre-less 234 down
  to 117 and a genre-less 64 up to 128, while a strong fast pulse can still keep a genre-less 205.

The candidate with the highest score wins, with two hard rules around `FOLD_UP_LIMIT` (205):

- a doubled estimate above it is only a candidate when the track's own genre, its label or its
  GetSongBPM tempo favours it -- an artist's or folder's prior (or the neutral one) alone never
  folds a track up into hard-dance territory;
- a raw estimate above it is only halved when real evidence favours the half: the track's own
  genre, its label, its artist, its uploader folder, its GetSongBPM tempo or a mainstream folder
  (`_halving_vouched`, issues #153 and #241). The neutral prior alone halved 4,209 genre-less fast tracks on production, 3,482 of
  them Soundcloud/YouTube uploads. Without that evidence the estimate stays and the octave is
  `unsettled`: kept, but with the confidence of a tie and capped at `WEAK_FOLD_CAP`. A fast
  estimate that wins with nothing on its side (no prior, no clearly weaker half pulse) is
  unsettled too.

The confidence of the result is the estimator's pulse
confidence times an octave certainty derived from the margin to the runner-up, and a value that
moved away from the raw estimate is discounted once more (`FOLD_DISCOUNT`): an octave choice made
against the estimator is never as sure as the pulse it came from. A fold that only the general
priors (neutral, path) decided is capped at `WEAK_FOLD_CAP`, below "reliable" -- as is an
unsettled estimate. `weak_value` says which stored outcomes those are; the tag writeback never
writes one.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from services.music_manager.bpm.bands import GENRE_BANDS

#: Bump when the rule changes: rows folded by an older version are folded again (worker.refold).
#: 3: a halving above FOLD_UP_LIMIT needs real evidence (issue #153).
#: 4: the uploader-folder prior (issue #241).
FOLD_VERSION = 4

#: The candidates must lie in this range, the same bounds as the effective BPM (effective.py).
MIN_BPM = 40.0
MAX_BPM = 500.0

#: Score bonus for the estimator's own choice.
STAY_BONUS = 0.35
#: Audio term: a gentle log-ratio slope everywhere, and a steep one below `AUDIO_KNEE`.
AUDIO_SLOPE = 1.5
AUDIO_KNEE = 0.6
AUDIO_KNEE_SLOPE = 10.0

#: The largest penalty one prior can hand out, before its weight: a far-off candidate is unlikely,
#: not impossible -- no single prior may veto on its own.
PENALTY_CAP = 4.5
#: The narrowest spread a prior is read with, in octaves (a label of identical 150s is still not
#: evidence against 151).
MIN_SPREAD = 0.12
#: A learned prior wider than this says nothing about the octave and is ignored.
MAX_SPREAD = 0.45

W_LABEL = 1.5
LABEL_MIN_SAMPLES = 10
LABEL_HALF_WEIGHT = 20
W_ARTIST = 1.5
ARTIST_MIN_SAMPLES = 5
ARTIST_HALF_WEIGHT = 10
#: The uploader folder (issue #241): the same weight and thresholds as the artist.
W_FOLDER = W_ARTIST
FOLDER_MIN_SAMPLES = ARTIST_MIN_SAMPLES
FOLDER_HALF_WEIGHT = ARTIST_HALF_WEIGHT
W_GENRE = 1.5
GENRE_MIN_SAMPLES = 30
GENRE_HALF_WEIGHT = 30
#: Weight of a hand-set band relative to W_GENRE.
BAND_WEIGHT = 0.6

#: Where the library's files live, as music-manager and the analyzer see them.
MUSIC_ROOT = '/mnt/music'
#: Top-level folders whose tracks are mainstream pop and dance compilations, lower-cased.
MAINSTREAM_ROOTS = frozenset({'hitzone', 'spotify', 'lidarr', 'top 100', 'top-100'})
PATH_CENTRE_BPM = 105.0
PATH_SPREAD = 0.4
W_PATH = 1.0
#: The path prior's weight relative to W_PATH when the track has a genre of its own.
PATH_WITH_GENRE = 0.5

#: GetSongBPM (issue #152): its tempo is read as a narrow prior with this weight. It only counts
#: when it lies within `EXTERNAL_MATCH` octaves (about 9%) of one of the candidates.
W_EXTERNAL = 1.5
EXTERNAL_SPREAD = MIN_SPREAD
EXTERNAL_MATCH = 0.12

NEUTRAL_CENTRE_BPM = 135.0
NEUTRAL_SPREAD = 0.5
#: The neutral prior's weight without any genre, label or artist evidence, and with some.
W_NEUTRAL_ALONE = 1.0
W_NEUTRAL_WITH_EVIDENCE = 0.3

#: Above this tempo a doubled estimate needs the track's own genre or its label to favour it: an
#: artist's prior alone never folds a track up into hard-dance territory (bug report 140, the
#: André Hazes case -- a ballad doubled on the strength of its artist's hardstyle remixes).
#: Labels here are genre-pure, so a terror label may still double a genre-less 105 to 210.
FOLD_UP_LIMIT = 205.0

#: Plausibility: without the track's own genre or label favouring it, a tempo above
#: FOLD_UP_LIMIT or below IMPLAUSIBLE_BELOW costs this much -- a strong fast pulse (the audio
#: term) can still pay for it, a neutral prior's nudge cannot.
IMPLAUSIBLE_BELOW = 70.0
IMPLAUSIBLE_PENALTY = 0.8

#: Octave certainty = 1 - 0.5 * exp(-CERTAINTY_RATE * margin): 0.5 at a tie, ~0.85 at 1, ~0.95 at 2.
CERTAINTY_RATE = 1.2
#: Extra factor on the confidence of a value that is not the raw estimate.
FOLD_DISCOUNT = 0.9
#: A fold decided by nothing but the general priors (neutral, path) is a plausible guess, not a
#: finding: its confidence is capped below any sensible "reliable" threshold, so it is never
#: written into a file's tag on its own. The track's genre, label or artist can make it reliable.
WEAK_FOLD_CAP = 0.6
WEAK_EVIDENCE = frozenset({'neutral', 'path'})
#: Below this margin the choice is ambiguous: the worker re-measures it first for its comb scores.
AMBIGUOUS_MARGIN = 1.0

#: Names of the terms, as stored in `library_track_bpm.fold_evidence`.
EVIDENCE_ESTIMATE = 'estimate'
EVIDENCE_LABEL = 'label'
EVIDENCE_ARTIST = 'artist'
EVIDENCE_FOLDER = 'folder'
EVIDENCE_GENRE = 'genre'
EVIDENCE_BAND = 'band'
EVIDENCE_PATH = 'path'
EVIDENCE_NEUTRAL = 'neutral'
EVIDENCE_EXTERNAL = 'getsongbpm'
#: A raw estimate above FOLD_UP_LIMIT that no evidence settles either way (issue #153): kept as
#: measured, with the confidence of a tie.
EVIDENCE_UNSETTLED = 'unsettled'
#: Stored when a person set the tempo (manual override); never produced by `choose_octave`.
EVIDENCE_MANUAL = 'manual'


@dataclass(frozen=True)
class Prior:
    """Where one key's (label, artist, genre) confident tempos sit, in log2(BPM).

    `centre` is the mean log2 tempo, `spread` its standard deviation in octaves, `samples` how
    many measurements back it.
    """

    centre: float
    spread: float
    samples: int

    @classmethod
    def around(cls, bpm: float, spread: float, samples: int = 0) -> Prior:
        """A prior centred on `bpm` (not log2) -- convenient for tests and fixed priors."""
        return cls(math.log2(bpm), spread, samples)


@dataclass(frozen=True)
class Evidence:
    """What is known about a track besides its audio.

    `genres` are the track's own genre names; `root` the top-level folder under the music root
    (`Hitzone`, `Soundcloud`, ...). `label` and `artist` are the learned priors of its label (the
    best-sampled one when it has several) and its primary artist's own tracks; `folder` that of its
    uploader folder, without the track itself (issue #241); `genre_priors` maps a lower-cased
    genre name to its learned prior. `external` is the tempo GetSongBPM lists for the
    track (issue #152), set only for a track with weak priors (`weak_priors`).
    """

    genres: tuple[str, ...] = ()
    root: str | None = None
    label: Prior | None = None
    artist: Prior | None = None
    folder: Prior | None = None
    genre_priors: Mapping[str, Prior] = field(default_factory=dict)
    external: Prior | None = None


@dataclass(frozen=True)
class Scores:
    """The estimator's comb scores: of the raw estimate, and of half and double it (None unknown)."""

    strength: float | None = None
    half: float | None = None
    double: float | None = None


@dataclass(frozen=True)
class Choice:
    """The chosen tempo, how sure the octave is, and which evidence decided it."""

    bpm: float
    factor: float
    confidence: float
    evidence: str
    margin: float
    #: The GetSongBPM tempo the choice weighed, None when that term did not apply.
    external_bpm: float | None = None

    @property
    def octave_corrected(self) -> bool:
        """True when the chosen tempo is not the raw estimate."""
        return self.factor != 1.0

    @property
    def ambiguous(self) -> bool:
        """True when the runner-up octave scored almost as well."""
        return self.margin < AMBIGUOUS_MARGIN


def _distance(bpm: float, prior: Prior) -> float:
    """How far `bpm` lies from `prior`'s centre, in spreads (an uncapped |z| in log2)."""
    return abs(math.log2(bpm) - prior.centre) / max(prior.spread, MIN_SPREAD)


def _penalty(bpm: float, prior: Prior) -> float:
    """How unlikely `bpm` is under `prior`: half the squared z-score in log2, capped."""
    z = _distance(bpm, prior)
    return min(PENALTY_CAP, 0.5 * z * z)


def _learned_weight(prior: Prior | None, weight: float, min_samples: int, half: int) -> float:
    """The weight a learned prior earns: 0 when too thin or too wide, rising with its samples."""
    if prior is None or prior.samples < min_samples or prior.spread > MAX_SPREAD:
        return 0.0
    return weight * prior.samples / (prior.samples + half)


def band_prior(band: tuple[float, float]) -> Prior:
    """A hand-set (low, high) band read as a prior: centred on its geometric middle, edges at 1 sigma."""
    low, high = band
    return Prior(centre=math.log2(math.sqrt(low * high)), spread=math.log2(high / low) / 2, samples=0)


def genre_evidence(genres: Iterable[str], learned: Mapping[str, Prior]) -> tuple[Prior, float, str] | None:
    """(prior, weight, name) of the most specific of the track's genres, or None without any known.

    Most specific = the narrowest prior: a track tagged `Hardcore` and `Uptempo Hardcore` is judged
    by the uptempo one. A learned prior is used when it has enough samples, else the genre's band.
    """
    best: tuple[Prior, float, str] | None = None
    best_spread = math.inf
    for name in sorted({(g or '').strip().lower() for g in genres}):
        if not name:
            continue
        prior = learned.get(name)
        weight = _learned_weight(prior, W_GENRE, GENRE_MIN_SAMPLES, GENRE_HALF_WEIGHT)
        kind = EVIDENCE_GENRE
        if weight == 0.0:
            if name not in GENRE_BANDS:
                continue
            prior, weight, kind = band_prior(GENRE_BANDS[name]), W_GENRE * BAND_WEIGHT, EVIDENCE_BAND
        if prior is not None and prior.spread < best_spread:
            best, best_spread = (prior, weight, kind), prior.spread
    return best


def _vouched(evidence: Evidence, genre: tuple[Prior, float, str] | None, candidate: float, raw: float) -> bool:
    """True when the track's own genre, or its well-sampled label, prefers `candidate` to its octave.

    For a doubled candidate the comparison is with the raw estimate; for the raw estimate itself
    (a fast reading that might be halved) with half of it.
    """
    other = raw if candidate != raw else raw / 2 if candidate > FOLD_UP_LIMIT else raw * 2
    if genre is not None and _distance(candidate, genre[0]) < _distance(other, genre[0]):
        return True
    external = external_prior(evidence, raw)
    if external is not None and _distance(candidate, external) < _distance(other, external):
        return True
    label = evidence.label
    if label is not None and _learned_weight(label, W_LABEL, LABEL_MIN_SAMPLES, LABEL_HALF_WEIGHT):
        return _distance(candidate, label) < _distance(other, label)
    return False


def _real_priors(evidence: Evidence, genre: tuple[Prior, float, str] | None, raw: float) -> list[Prior]:
    """The priors that count as real evidence on the octave of a fast `raw` (issue #153).

    The track's own genre (learned or band), its label, its artist and its uploader folder when
    their weight is not zero, its GetSongBPM tempo when it matches an octave, and the mainstream
    path prior. Measured on production (2026-11-12): on the 411 fast mainstream rows, the artist
    prior sided with the half in 223 of 233 and the genre in 176 of 177, so the path prior is
    evidence, not a guess. Only the neutral prior is left out: it knows nothing about the track.
    """
    found: list[Prior] = []
    if genre is not None:
        found.append(genre[0])
    if evidence.label is not None and _learned_weight(evidence.label, W_LABEL, LABEL_MIN_SAMPLES, LABEL_HALF_WEIGHT):
        found.append(evidence.label)
    if evidence.artist is not None and _learned_weight(
        evidence.artist, W_ARTIST, ARTIST_MIN_SAMPLES, ARTIST_HALF_WEIGHT
    ):
        found.append(evidence.artist)
    if evidence.folder is not None and _learned_weight(
        evidence.folder, W_FOLDER, FOLDER_MIN_SAMPLES, FOLDER_HALF_WEIGHT
    ):
        found.append(evidence.folder)
    external = external_prior(evidence, raw)
    if external is not None:
        found.append(external)
    if (evidence.root or '').strip().lower() in MAINSTREAM_ROOTS:
        found.append(Prior.around(PATH_CENTRE_BPM, PATH_SPREAD))
    return found


def _halving_vouched(evidence: Evidence, genre: tuple[Prior, float, str] | None, raw: float) -> bool:
    """True when a real prior puts a fast `raw` estimate's half closer than the estimate itself."""
    return any(_distance(raw / 2, prior) < _distance(raw, prior) for prior in _real_priors(evidence, genre, raw))


def _estimate_supported(
    evidence: Evidence, genre: tuple[Prior, float, str] | None, raw: float, scores: Scores | None
) -> bool:
    """True when something real backs a fast `raw` estimate against its half.

    A real prior closer to the estimate than to its half, or the audio: a half whose comb score is
    below `AUDIO_KNEE` of the estimate's (a clearly fast pulse).
    """
    if any(_distance(raw, prior) < _distance(raw / 2, prior) for prior in _real_priors(evidence, genre, raw)):
        return True
    if scores is None or not scores.strength or scores.half is None:
        return False
    return scores.half / scores.strength < AUDIO_KNEE


def weak_value(octave_corrected: bool, fold_evidence: str | None) -> bool:
    """True for a stored outcome that general priors or no evidence decided (never written to a tag).

    A fold decided by `WEAK_EVIDENCE` alone, or an unsettled estimate.
    """
    if fold_evidence == EVIDENCE_UNSETTLED:
        return True
    return bool(octave_corrected) and fold_evidence in WEAK_EVIDENCE


def weak_priors(evidence: Evidence) -> bool:
    """True for a mainstream track without a usable label or artist prior (issue #152).

    Only these tracks are looked up on GetSongBPM: everywhere else the collection's own priors
    already settle the octave.
    """
    if (evidence.root or '').strip().lower() not in MAINSTREAM_ROOTS:
        return False
    label = _learned_weight(evidence.label, W_LABEL, LABEL_MIN_SAMPLES, LABEL_HALF_WEIGHT)
    artist = _learned_weight(evidence.artist, W_ARTIST, ARTIST_MIN_SAMPLES, ARTIST_HALF_WEIGHT)
    return not label and not artist


def external_prior(evidence: Evidence, raw: float) -> Prior | None:
    """The track's GetSongBPM prior when it lies close to one octave of `raw`, else None."""
    external = evidence.external
    if external is None or raw <= 0:
        return None
    for factor in (1.0, 0.5, 2.0):
        if abs(math.log2(raw * factor) - external.centre) <= EXTERNAL_MATCH:
            return external
    return None


def audio_term(ratio: float | None) -> float:
    """The audio evidence for a neighbour whose comb score is `ratio` times the estimate's (<= 0)."""
    if ratio is None or not math.isfinite(ratio):
        return 0.0
    ratio = min(1.0, max(ratio, 1e-3))
    return AUDIO_SLOPE * math.log(ratio) + AUDIO_KNEE_SLOPE * min(0.0, math.log(ratio / AUDIO_KNEE))


def _terms(candidate: float, factor: float, raw: float, evidence: Evidence, scores: Scores | None) -> dict[str, float]:
    """Every term of one candidate's score, by evidence name."""
    terms: dict[str, float] = {}
    estimate = STAY_BONUS if factor == 1.0 else 0.0
    if factor != 1.0 and scores is not None and scores.strength:
        neighbour = scores.half if factor < 1.0 else scores.double
        if neighbour is not None:
            estimate += audio_term(neighbour / scores.strength)
    terms[EVIDENCE_ESTIMATE] = estimate

    has_evidence = False
    label_weight = _learned_weight(evidence.label, W_LABEL, LABEL_MIN_SAMPLES, LABEL_HALF_WEIGHT)
    if label_weight and evidence.label is not None:
        terms[EVIDENCE_LABEL] = -label_weight * _penalty(candidate, evidence.label)
        has_evidence = True
    artist_weight = _learned_weight(evidence.artist, W_ARTIST, ARTIST_MIN_SAMPLES, ARTIST_HALF_WEIGHT)
    if artist_weight and evidence.artist is not None:
        terms[EVIDENCE_ARTIST] = -artist_weight * _penalty(candidate, evidence.artist)
        has_evidence = True
    folder_weight = _learned_weight(evidence.folder, W_FOLDER, FOLDER_MIN_SAMPLES, FOLDER_HALF_WEIGHT)
    if folder_weight and evidence.folder is not None:
        terms[EVIDENCE_FOLDER] = -folder_weight * _penalty(candidate, evidence.folder)
        has_evidence = True
    genre = genre_evidence(evidence.genres, evidence.genre_priors)
    if genre is not None:
        prior, weight, kind = genre
        terms[kind] = -weight * _penalty(candidate, prior)
        has_evidence = True
    external = external_prior(evidence, raw)
    if external is not None:
        terms[EVIDENCE_EXTERNAL] = -W_EXTERNAL * _penalty(candidate, external)
        has_evidence = True
    if (evidence.root or '').strip().lower() in MAINSTREAM_ROOTS:
        path_weight = W_PATH * (PATH_WITH_GENRE if genre is not None else 1.0)
        terms[EVIDENCE_PATH] = -path_weight * _penalty(candidate, Prior.around(PATH_CENTRE_BPM, PATH_SPREAD))
    neutral_weight = W_NEUTRAL_WITH_EVIDENCE if has_evidence else W_NEUTRAL_ALONE
    neutral = -neutral_weight * _penalty(candidate, Prior.around(NEUTRAL_CENTRE_BPM, NEUTRAL_SPREAD))
    if (candidate > FOLD_UP_LIMIT or candidate < IMPLAUSIBLE_BELOW) and not _vouched(evidence, genre, candidate, raw):
        neutral -= IMPLAUSIBLE_PENALTY
    terms[EVIDENCE_NEUTRAL] = neutral
    return terms


def choose_octave(
    raw: float,
    raw_confidence: float | None,
    evidence: Evidence | None = None,
    scores: Scores | None = None,
) -> Choice:
    """The octave of `raw` the evidence favours; see the module docstring for the terms."""
    evidence = evidence or Evidence()
    genre = genre_evidence(evidence.genres, evidence.genre_priors)
    fast = raw > FOLD_UP_LIMIT
    halving_vouched = fast and _halving_vouched(evidence, genre, raw)
    scored: list[tuple[float, float, float, dict[str, float]]] = []
    for factor in (1.0, 0.5, 2.0):
        candidate = raw * factor
        if factor != 1.0 and not MIN_BPM <= candidate <= MAX_BPM:
            continue
        if factor > 1.0 and candidate > FOLD_UP_LIMIT and not _vouched(evidence, genre, candidate, raw):
            continue
        terms = _terms(candidate, factor, raw, evidence, scores)
        scored.append((sum(terms.values()), factor, candidate, terms))
    scored.sort(key=lambda item: item[0], reverse=True)
    best_total, factor, candidate, best_terms = scored[0]
    if len(scored) > 1:
        runner_total, _, _, runner_terms = scored[1]
        margin = best_total - runner_total
        diffs = {name: best_terms.get(name, 0.0) - runner_terms.get(name, 0.0) for name in {*best_terms, *runner_terms}}
        decider = max(sorted(diffs), key=lambda name: diffs[name])
    else:
        margin, decider = 10.0, EVIDENCE_ESTIMATE
    if fast and factor < 1.0 and not halving_vouched:
        # Only the neutral prior wanted the half: the estimate stays, the octave is not settled.
        factor, candidate = 1.0, raw
        margin, decider = 0.0, EVIDENCE_UNSETTLED
    elif fast and factor == 1.0 and not _estimate_supported(evidence, genre, raw, scores):
        margin, decider = 0.0, EVIDENCE_UNSETTLED

    certainty = 1.0 - 0.5 * math.exp(-CERTAINTY_RATE * margin)
    confidence = float(raw_confidence or 0.0) * certainty
    if factor != 1.0:
        confidence *= FOLD_DISCOUNT
    if weak_value(factor != 1.0, decider):
        confidence = min(confidence, WEAK_FOLD_CAP)
    external = external_prior(evidence, raw)
    return Choice(
        bpm=round(candidate, 2),
        factor=factor,
        confidence=round(min(1.0, max(0.0, confidence)), 3),
        evidence=decider,
        margin=round(margin, 3),
        external_bpm=None if external is None else round(2**external.centre, 2),
    )


#: Top-level folders whose files sit in a folder per uploader, lower-cased (issue #241).
UPLOADER_ROOTS = frozenset({'soundcloud', 'youtube'})
#: `library_bpm_priors.prior_key` is a VARCHAR(191).
FOLDER_KEY_LENGTH = 191


def folder_key(path: str | None, music_root: str = MUSIC_ROOT) -> str | None:
    """`<Root>/<uploader>`, lower-cased, for a file in an uploader folder; None for any other path.

    The same key `priors.py` computes in SQL: the path's first two folders under `music_root`, cut
    to FOLDER_KEY_LENGTH characters. A file directly under the root has no uploader.
    """
    prefix = music_root.rstrip('/') + '/'
    if not path or not path.startswith(prefix):
        return None
    parts = path[len(prefix) :].split('/')
    if len(parts) < 3 or parts[0].lower() not in UPLOADER_ROOTS or not parts[1]:
        return None
    return f'{parts[0]}/{parts[1]}'[:FOLDER_KEY_LENGTH].lower()


def root_of(path: str | None, music_root: str = MUSIC_ROOT) -> str | None:
    """The top-level folder of a library path under `music_root` (`Hitzone` for .../Hitzone/x.mp3)."""
    if not path:
        return None
    prefix = music_root.rstrip('/') + '/'
    rest = path[len(prefix) :] if path.startswith(prefix) else path.lstrip('/')
    head = rest.split('/', 1)[0]
    return head or None
