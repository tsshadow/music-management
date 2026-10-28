"""External recording evidence for an artist name: the judgement behind artist auto-approval.

Moved here from `tools/artist_auto_approve.py` so the scheduled evidence run inside
music-manager (`services/music_manager/artist_auto_approve_worker.py`) and the manual tool
apply *one* set of rules: the normalisation, the three approval rules, the brand guards and
the three keyless lookups (Deezer, iTunes Search, MusicBrainz). Nothing here opens a
database or a sqlite file; the lookups take any fetcher with `get(source, url) -> dict | None`
and a `failed` counter, so the caller decides how requests are cached and rate-limited.

See docs/designs/artist-curation/technical.md ("Scheduled evidence run") for how the
rules are applied on a schedule, and the tool's docstring for the rules in words.
"""

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Protocol

from services.common.user_agent import build_user_agent

#: Bump when a threshold or a normalisation rule changes: verdicts stored under an older
#: policy are recomputed from the cached responses, nothing is fetched again.
POLICY = 'v1'
DECIDED_BY = 'auto-external'
USER_AGENT = build_user_agent('muma-artist-auto-approve', '0.1')

DEEZER = 'deezer'
MUSICBRAINZ = 'musicbrainz'
ITUNES = 'itunes'
#: Asked in this order, cheapest first; a name stops at its first approval.
SOURCES = (DEEZER, ITUNES, MUSICBRAINZ)
#: Deezer and iTunes are fed by the same distributors, so an approval on one title needs
#: MusicBrainz -- separately curated -- plus one of these.
COMMERCIAL = {DEEZER, ITUNES}

APPROVE = 'approve'
UNRESOLVED = 'unresolved'
SKIPPED = 'skipped'
#: A source did not answer (quota, 503, network) so the evidence is partial; the next
#: run asks again instead of treating silence as "not found".
INCOMPLETE = 'incomplete'

#: Rules 1 and 2: this many different local titles found outside.
MIN_TITLES = 2
#: Rules 2 and 3 lean on one title, so it has to be a distinctive one -- `Free` on a
#: same-named artist is a coincidence waiting to happen, `Feel The Electricity` is not.
DISTINCTIVE_WORDS = 2
DISTINCTIVE_LETTERS = 10
#: A title shorter than this never counts at all; `180` matches too much.
MIN_TITLE_LETTERS = 4
#: MusicBrainz artist types that are an act. `Other` covers labels and event brands.
MUSICBRAINZ_ACT_TYPES = {'Person', 'Group', 'Orchestra', 'Choir', 'Character'}
#: How many exact-name candidates per source get their tracklist fetched. A short name
#: has many namesakes; the real one is rarely past the third.
MAX_CANDIDATES = 3

#: Names that are catalogued as artists by the stores but are labels, channels, event
#: brands or shows in this library. They have real recording credits (a compilation
#: series, a podcast), so evidence would approve them; keep them in the queue.
BRAND_BLOCKLIST = {
    'q-dance',
    'dj mag',
    'sick events',
    'the boom room',
    'various artists',
    'various',
    'monstercat',
    'defqon.1',
    'thunderdome',
    'masters of hardcore',
    'dominator',
    'hardtunes',
    'scantraxx',
    'art of dance',
    'b2s',
    'bkjn',
    'mixmash',
}

#: A name shaped like a brand rather than an act. The stores credit a festival with its
#: anthems and a label with its compilations, so evidence would approve `DediKted
#: Festival` (it did); such a name stays in the queue for a human.
BRAND_SHAPE = re.compile(
    r"\b(?:festival|events?|records|recordings|recordz|music|tv|radio|podcast|exclusives?|premieres?|presents|"
    r"sessions?|mag|magazine|official|channel|network|label|agency|bookings|promotions?|store|shop)\b|"
    r"\b(?:19|20)\d\d\b",
    re.IGNORECASE,
)

#: Per-source minimum interval between requests, seconds. MusicBrainz says one per
#: second and answers 503 above it; iTunes documents ~20 per minute; Deezer is
#: undocumented and answers `Quota limit exceeded` (HTTP 200) when pushed.
MIN_INTERVAL = {DEEZER: 0.25, MUSICBRAINZ: 1.1, ITUNES: 3.2}
TIMEOUT = 20
RETRIES = 5

DECIDE_BATCH = 100

# ----------------------------------------------------------------------------- normalisation

#: A bracket that ends in a mix-type word: `(Extended Mix)`, `(Hard Remix)`, `(Official
#: BKJN vs Partyraiser 2026 Anthem)`, `(Album Intro Edit)`. Ending, not containing: `(Free
#: Your Mind)` and `(Music Is Everything)` are the song.
_MIX_BRACKET = re.compile(
    r"\s*[\(\[]\s*[^()\[\]]*?\b(?:remix|rmx|mix|edit|bootleg|mashup|mash-up|rework|remake|refix|flip|vip|"
    r"version|instrumental|acapella|dub|cut|anthem|theme|extended|original|radio|reprise|explicit|clean)\s*[\)\]]",
    re.IGNORECASE,
)
#: A bracket that is packaging, wherever the word sits: `[OUT NOW ON OWSLA!]`, `(jeuj...
#: free download)`, `(Official Videoclip)`, `(HQ Preview)`.
_PROMO_BRACKET = re.compile(
    r"\s*[\(\[]\s*[^()\[\]]*\b(?:free\s*(?:\w+\s*)?(?:dl|download)|out now|official\s*(?:video|audio|videoclip|music video)?|"
    r"videoclip|preview|snippet|premiere|hq|hd|lyrics?|visualizer)\b[^()\[\]]*[\)\]]",
    re.IGNORECASE,
)
#: A catalogue id (`[TX023]`, `[ FR002 ]`, `(DEM050)`), a label (`[Silk Music]`, `(Napalm
#: Records)`) or a feature (`(feat. Layna)`).
_TAG_BRACKET = re.compile(
    r"\s*[\(\[]\s*(?:(?-i:[A-Z]{1,8}[\- ]?\d{1,4}[A-Z]{0,2})|[^()\[\]]*\b(?:records?|recordings|music)|"
    r"(?:feat\.?|ft\.?|featuring)\b[^()\[\]]*)\s*[\)\]]",
    re.IGNORECASE,
)
#: Packaging at the very end of the title, after brackets are gone: `... FREE DOWNLOAD`,
#: `... - Napalm Records`, `...hardtunes only`. Anchored, so `Dream Premiere Night` keeps
#: its name.
_TRAILING_NOISE = re.compile(
    r"\s*(?:[-|–]\s*)?(?:free\s*(?:dl|download)|out now|official\s*(?:video|audio|music video)|hq|hd|preview|"
    r"snippet|premiere|hardtunes only|[^-|–]*\brecords)\W*(?:[\(\[][^()\[\]]*[\)\]]\W*)*$",
    re.IGNORECASE,
)
_FEAT = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s+.*$", re.IGNORECASE)
#: What a label or an event is credited with on the stores: sets, compilations, mixes.
#: Checked on the raw title, before `(Album Mix)` and `(Continuous Mix)` are stripped.
_COMPILATION_MARKERS = re.compile(
    r"\bbest of\b|\bvol(?:ume)?\.?\s*\d|\bchapter\s*\d|\bmegamix\b|\b(?:album|continuous|full|dj|live|yearmix|year)\s*mix\b|"
    r"\bmix\s*$",
    re.IGNORECASE,
)
#: What a set or a show is called, judged after the packaging is gone so that a year
#: in `(Official ... 2026 Anthem)` does not condemn the song.
_SET_MARKERS = re.compile(
    r"\|| @ |\blive (?:from|at|set)\b|\bdj[- ]?set\b|\bpodcast\b|\bepisode\b|\bwarm-?up\b|"
    r"\b(?:19|20)\d\d\b|\bpresents\b|\bpres\.",
    re.IGNORECASE,
)


def fold(value: str) -> str:
    """Case, accents, typographic quotes and punctuation folded away; words separated by one space."""
    value = unicodedata.normalize('NFKD', value or '')
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace('&', ' and ')
    return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def normalise_artist(name: str) -> str:
    """The key two spellings of one artist name share: `fold` of the name."""
    return fold(name)


def strip_packaging(title: str) -> str:
    """The song under the packaging: no mix suffix, catalogue id, label, promo tail or feature."""
    value = title or ''
    previous = None
    while previous != value:
        previous = value
        for pattern in (_MIX_BRACKET, _PROMO_BRACKET, _TAG_BRACKET, _TRAILING_NOISE):
            value = pattern.sub('', value)
    return _FEAT.sub('', value).strip()


def normalise_title(title: str) -> str:
    """The key a local and an external title are compared on: packaging stripped, then folded."""
    return fold(strip_packaging(title))


def looks_like_a_set(title: str) -> bool:
    """`Defqon.1 | ORANGE | Friday`, `Uncaged Vol. 8 (Album Mix)`: not a song, never matched.

    Sets, compilations and mixes are what a *label* is credited with on the stores, so
    they count on neither side -- Monstercat was approved on two of them.
    """
    return bool(_COMPILATION_MARKERS.search(title or '')) or bool(_SET_MARKERS.search(strip_packaging(title)))


def letters(value: str) -> int:
    """How many alphanumeric characters `value` holds."""
    return sum(ch.isalnum() for ch in value)


def is_distinctive(normalised_title: str) -> bool:
    """Whether one matching title is enough to lean on: at least two words and ten letters."""
    return len(normalised_title.split()) >= DISTINCTIVE_WORDS and letters(normalised_title) >= DISTINCTIVE_LETTERS


def usable_titles(titles: list[str]) -> dict[str, str]:
    """Normalised title -> one raw example, for the titles worth asking about."""
    out: dict[str, str] = {}
    for raw in titles:
        if looks_like_a_set(raw):
            continue
        key = normalise_title(raw)
        if letters(key) < MIN_TITLE_LETTERS:
            continue
        out.setdefault(key, raw)
    return out


# ----------------------------------------------------------------------------- scoring


@dataclass
class ExternalArtist:
    source: str
    external_id: str
    name: str
    kind: str | None = None  # MusicBrainz type; None elsewhere
    titles: list[str] = field(default_factory=list)  # raw external recording titles
    detail: dict = field(default_factory=dict)  # fans, url -- evidence only


@dataclass
class Verdict:
    verdict: str
    rule: str | None
    evidence: dict


def match_titles(local: dict[str, str], external: ExternalArtist) -> dict[str, str]:
    """Local normalised titles found in the external tracklist, with the external raw title."""
    seen = {}
    for raw in external.titles:
        if looks_like_a_set(raw):
            continue
        key = normalise_title(raw)
        if key in local and key not in seen:
            seen[key] = raw
    return seen


def score_artist(name: str, titles: list[str], candidates: list[ExternalArtist]) -> Verdict:
    """The decision, from the local titles and whatever the sources said about the name.

    Candidates must already be exact-name matches; this does not re-check the name.
    """
    if normalise_artist(name) in {fold(brand) for brand in BRAND_BLOCKLIST}:
        return Verdict(SKIPPED, 'brand', {'reason': 'on the label/channel blocklist'})
    if BRAND_SHAPE.search(name):
        return Verdict(SKIPPED, 'brand-shape', {'reason': 'named like a label, channel or event'})
    local = usable_titles(titles)
    if not local:
        return Verdict(SKIPPED, 'no-titles', {'reason': 'no title survives normalisation'})

    per_candidate = []
    for candidate in candidates:
        matched = match_titles(local, candidate)
        if not matched:
            continue
        per_candidate.append(
            {
                'source': candidate.source,
                'id': candidate.external_id,
                'name': candidate.name,
                'type': candidate.kind,
                'matched': {key: {'local': local[key], 'external': raw} for key, raw in matched.items()},
                **candidate.detail,
            }
        )
    evidence = {'titles_queried': len(local), 'matches': per_candidate}
    if not per_candidate:
        return Verdict(UNRESOLVED, None, evidence)

    acts = [hit for hit in per_candidate if hit['source'] != MUSICBRAINZ or hit['type'] in MUSICBRAINZ_ACT_TYPES]

    # Rule 1: two titles on one external act.
    if any(len(hit['matched']) >= MIN_TITLES for hit in acts):
        return Verdict(APPROVE, 'two-titles-one-act', evidence)

    # Rule 2: two titles from two sources, one of them distinctive. Two namesakes on
    # one store with a title each are not two sources.
    by_source: dict[str, set[str]] = defaultdict(set)
    for hit in acts:
        by_source[hit['source']].update(hit['matched'])
    matched_keys = set().union(*by_source.values()) if by_source else set()
    if (
        len(by_source) >= 2
        and len(matched_keys) >= MIN_TITLES
        and any(len(matched_keys - keys) >= 1 for keys in by_source.values())
        and any(is_distinctive(key) for key in matched_keys)
    ):
        return Verdict(APPROVE, 'two-titles-two-sources', evidence)

    # Rule 3: one distinctive title on MusicBrainz (an act) and on a store.
    mb_ok = any(hit['source'] == MUSICBRAINZ and any(is_distinctive(key) for key in hit['matched']) for hit in acts)
    store_ok = any(hit['source'] in COMMERCIAL and any(is_distinctive(key) for key in hit['matched']) for hit in acts)
    if mb_ok and store_ok:
        return Verdict(APPROVE, 'distinctive-title-two-sources', evidence)
    return Verdict(UNRESOLVED, None, evidence)


class EvidenceFetcher(Protocol):
    """What the lookups need from a fetcher: a GET that returns parsed JSON or None, and a failure count."""

    failed: int

    def get(self, source: str, url: str) -> dict | None:
        """The parsed body of `url` on `source`, or None when the source did not answer."""


def _deezer_error(body: str) -> bool:
    """Deezer reports its quota (and most other refusals) as a 200 with an error object."""
    try:
        return isinstance(json.loads(body), dict) and 'error' in json.loads(body)
    except ValueError:
        return True


def _q(value: str) -> str:
    """`value` percent-encoded for a URL path or query, slashes included."""
    from urllib.parse import quote

    return quote(value, safe='')


def _lucene(value: str) -> str:
    """`value` with Lucene query syntax escaped, for the MusicBrainz search."""
    return re.sub(r'([+\-!(){}\[\]^"~*?:\\/&|])', r'\\\1', value)


def deezer_candidates(fetcher: EvidenceFetcher, name: str) -> list[ExternalArtist]:
    """Deezer artists named exactly `name`, each with its top tracks and search hits as titles."""
    key = normalise_artist(name)
    found = fetcher.get(DEEZER, f'https://api.deezer.com/search/artist?q={_q(name)}&limit=10') or {}
    out = []
    for artist in (found.get('data') or [])[: MAX_CANDIDATES * 2]:
        if normalise_artist(artist.get('name', '')) != key:
            continue
        candidate = ExternalArtist(DEEZER, str(artist['id']), artist['name'], detail={'fans': artist.get('nb_fan')})
        top = fetcher.get(DEEZER, f"https://api.deezer.com/artist/{artist['id']}/top?limit=50") or {}
        candidate.titles = [track.get('title', '') for track in top.get('data') or []]
        out.append(candidate)
        if len(out) >= MAX_CANDIDATES:
            break
    # The top list is short for a small act; the plain search reaches the long tail and
    # tracks the name is only credited on, filtered back to the exact ids found above.
    if out:
        ids = {c.external_id: c for c in out}
        search = fetcher.get(DEEZER, f'https://api.deezer.com/search?q={_q(name)}&limit=100') or {}
        for track in search.get('data') or []:
            owner = ids.get(str((track.get('artist') or {}).get('id')))
            if owner is not None:
                owner.titles.append(track.get('title', ''))
    return out


def musicbrainz_candidates(fetcher: EvidenceFetcher, name: str) -> list[ExternalArtist]:
    """MusicBrainz artists named (or aliased) exactly `name`, each with up to 100 recording titles."""
    key = normalise_artist(name)
    query = _q(f'artist:"{_lucene(name)}"')
    found = fetcher.get(MUSICBRAINZ, f'https://musicbrainz.org/ws/2/artist?query={query}&fmt=json&limit=10') or {}
    out = []
    for artist in found.get('artists') or []:
        names = [artist.get('name', '')] + [alias.get('name', '') for alias in artist.get('aliases') or []]
        if key not in {normalise_artist(n) for n in names}:
            continue
        candidate = ExternalArtist(MUSICBRAINZ, artist['id'], artist['name'], kind=artist.get('type'))
        recordings = (
            fetcher.get(MUSICBRAINZ, f"https://musicbrainz.org/ws/2/recording?artist={artist['id']}&fmt=json&limit=100")
            or {}
        )
        candidate.titles = [r.get('title', '') for r in recordings.get('recordings') or []]
        out.append(candidate)
        if len(out) >= MAX_CANDIDATES:
            break
    return out


def itunes_candidates(fetcher: EvidenceFetcher, name: str) -> list[ExternalArtist]:
    """iTunes artists named exactly `name`, grouped from one song search, with their song titles."""
    key = normalise_artist(name)
    found = (
        fetcher.get(ITUNES, f'https://itunes.apple.com/search?term={_q(name)}&entity=song&limit=200&country=NL') or {}
    )
    by_id: dict[str, ExternalArtist] = {}
    for track in found.get('results') or []:
        if normalise_artist(track.get('artistName', '')) != key:
            continue
        artist_id = str(track.get('artistId'))
        candidate = by_id.setdefault(artist_id, ExternalArtist(ITUNES, artist_id, track['artistName']))
        candidate.titles.append(track.get('trackName', ''))
    return list(by_id.values())[:MAX_CANDIDATES]


LOOKUPS = {DEEZER: deezer_candidates, MUSICBRAINZ: musicbrainz_candidates, ITUNES: itunes_candidates}


def resolve(fetcher: EvidenceFetcher, name: str, titles: list[str], sources: tuple[str, ...]) -> Verdict:
    """Cheapest source first; stop as soon as the evidence is enough."""
    candidates: list[ExternalArtist] = []
    verdict = score_artist(name, titles, candidates)
    if verdict.verdict == SKIPPED:
        return verdict
    failed_before = fetcher.failed
    for source in sources:
        candidates.extend(LOOKUPS[source](fetcher, name))
        verdict = score_artist(name, titles, candidates)
        if verdict.verdict == APPROVE:
            break
    if verdict.verdict != APPROVE and fetcher.failed > failed_before:
        verdict = Verdict(INCOMPLETE, None, dict(verdict.evidence, failed_requests=fetcher.failed - failed_before))
    verdict.evidence['sources'] = list(sources)
    return verdict


def titles_hash(titles: list[str]) -> str:
    """Changes when the library's titles for a name change, which makes a verdict stale."""
    return hashlib.sha256(json.dumps(sorted(set(titles))).encode()).hexdigest()[:16]
