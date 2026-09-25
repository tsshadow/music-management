"""Which label or artist a channel is, where the names leave no doubt.

Every channel (see `services.common.channels`) starts out pointing at neither a label nor an
artist. This proposes those links on strong name equality only, for a curator to confirm or
reject; see docs/designs/channel-links/.

"Strong" means: the channel's name and the candidate's name have the same
`unicode_name_key`, or the candidate is reached through an explicit alias or a curator's
redirect. The Unicode key rather than the ASCII one because it is the artist key already, and
because channel names are full of letters outside ASCII (`Ｖａｚｅ`, `ĦȺŦɆɌS`) that the ASCII
key would drop -- two different names collapsing to the same shorter key is precisely the false
"strong" match this must not produce. Resemblance (a substring, an `Official` suffix) is never
proposed.

Pure over its inputs; `ChannelLinkStore` in the router module does the queries.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from services.common.channels import is_label
from services.common.text_normalize import unicode_name_key

LABEL = 'label'
ARTIST = 'artist'
KINDS = (LABEL, ARTIST)

NAME = 'name'
ALIAS = 'alias'
REDIRECT = 'redirect'

#: Platforms whose channels are considered. Telegram is left out: one channel, and a
#: Telegram channel is a chat, not an artist's or a label's own account.
PLATFORMS = ('soundcloud', 'youtube')


@dataclass(frozen=True)
class Channel:
    """A channel as the search needs it: its name and the links it already has."""

    id: int
    platform: str
    name: str
    label_id: int | None = None
    artist_id: int | None = None

    def linked(self, kind: str) -> bool:
        """Whether the channel already has a link of this kind."""
        return (self.label_id if kind == LABEL else self.artist_id) is not None


@dataclass(frozen=True)
class Target:
    """A label or artist a channel may be linked to, reached through `via` (a name or an alias)."""

    id: int
    name: str
    via: str


@dataclass(frozen=True)
class Proposal:
    """One proposed link."""

    channel_id: int
    kind: str
    target_id: int
    target_name: str
    source: str

    @property
    def key(self) -> tuple[int, str, int]:
        """The triple the proposals table is unique on."""
        return (self.channel_id, self.kind, self.target_id)


@dataclass
class ProposalRun:
    """What one search produced: the proposals, and how many (channel, kind) pairs were too ambiguous."""

    proposals: list[Proposal]
    ambiguous: int = 0


def name_key(name: str | None) -> str:
    """The key two names are compared on. See the module docstring for why this variant."""
    return unicode_name_key(name)


def _index(targets: Iterable[Target]) -> dict[str, list[Target]]:
    """Targets grouped by the key of the name they are reached through; empty keys dropped."""
    index: dict[str, list[Target]] = {}
    for target in targets:
        key = name_key(target.via)
        if key:
            index.setdefault(key, []).append(target)
    return index


class CandidateIndex:
    """The tiers of candidates for one kind, each indexed by name key, in the order they are consulted."""

    def __init__(self, kind: str, tiers: Sequence[tuple[str, Iterable[Target]]]):
        self.kind = kind
        self.tiers = [(source, _index(targets)) for source, targets in tiers]


def _pick(channel_name: str, candidates: list[Target]) -> Target | None:
    """The one target a tier proposes, or None when it cannot choose.

    Several rows can reach the same target (a name and its alias); they count once. Among
    several distinct targets, the one spelled exactly like the channel, capitals aside, wins
    -- `Dr. Peacock` over `Dr Peacock` and `Dr.Peacock` for the channel `Dr. Peacock`.
    """
    distinct: dict[int, Target] = {}
    for target in candidates:
        distinct.setdefault(target.id, target)
    if len(distinct) == 1:
        return next(iter(distinct.values()))
    wanted = channel_name.strip().casefold()
    exact = {t.id: t for t in candidates if t.via.strip().casefold() == wanted}
    if len(exact) == 1:
        return next(iter(exact.values()))
    return None


def propose_for_channel(channel: Channel, index: CandidateIndex) -> tuple[Proposal | None, bool]:
    """The proposal of one kind for one channel, and whether the channel was ambiguous for it.

    The first tier with any candidate decides; later tiers are not consulted, also not when
    that first tier cannot choose. Falling through to an alias after an ambiguous name would
    let a weaker signal settle what a stronger one could not.
    """
    if channel.linked(index.kind):
        return None, False
    key = name_key(channel.name)
    if not key:
        return None, False
    for source, tier in index.tiers:
        candidates = tier.get(key)
        if not candidates:
            continue
        target = _pick(channel.name, candidates)
        if target is None:
            return None, True
        # The name as the target is called, not the spelling it was reached through: an
        # alias or redirect row names the channel's spelling, the proposal names the artist.
        return Proposal(channel.id, index.kind, target.id, target.name, source), False
    return None, False


def label_index(labels: Iterable[tuple[int, str]]) -> CandidateIndex:
    """Label candidates: every library label that is actually a label (not a platform or placeholder)."""
    return CandidateIndex(LABEL, [(NAME, [Target(i, n, n) for i, n in labels if is_label(n)])])


def artist_index(
    approved: Iterable[tuple[int, str]],
    aliases: Iterable[tuple[int, str, str]] = (),
    redirects: Iterable[tuple[int, str, str]] = (),
) -> CandidateIndex:
    """Artist candidates in three tiers.

    `approved`: (library id, name) of white artists. `aliases`: (library id, artist name,
    alias) from `library_artist_aliases`. `redirects`: (library id, canonical name, spelling)
    for black spellings the curator rewrote to a white artist.
    """
    return CandidateIndex(
        ARTIST,
        [
            (NAME, [Target(i, n, n) for i, n in approved]),
            (ALIAS, [Target(i, n, alias) for i, n, alias in aliases]),
            (REDIRECT, [Target(i, n, spelling) for i, n, spelling in redirects]),
        ],
    )


def propose_links(channels: Iterable[Channel], indexes: Sequence[CandidateIndex]) -> ProposalRun:
    """Every strong proposal for every considered channel, one per (channel, kind) at most."""
    kinds = list(indexes)
    run = ProposalRun([])
    for channel in channels:
        if channel.platform not in PLATFORMS:
            continue
        for index in kinds:
            proposal, ambiguous = propose_for_channel(channel, index)
            if proposal:
                run.proposals.append(proposal)
            elif ambiguous:
                run.ambiguous += 1
    return run
