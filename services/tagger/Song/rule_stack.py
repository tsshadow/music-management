"""The rules each song type runs, built once per tagging round instead of once per file.

Every Song subclass used to construct its whole rule list inside `parse()`, so every file
paid for it. Most rules are a few attributes, but InferArtistFromTitleRule turns the
~37k-name artist table into a set twice (once for itself, once for its "presents"
sub-rule) and asks the database for the full ignore list and the full genre list -- two
fresh connections -- on every SoundCloud, Telegram and YouTube file.

The rules hold no per-file state (everything a rule learns about a file lives on the
song), so one list can serve every file and every worker thread of a round. Inside a
round (`services.common.Helpers.RoundScope`) `rules_for` builds a kind's list the first
time it is asked and hands out the same rule objects after that; outside one -- a single
file tagged from the API, the downloader, the importer -- it builds a fresh list, which
is what every caller got before.

What a round-scoped list reads once is read at the same moment everything else a round
depends on is refreshed: `Tagger.run` reloads the rule caches before the first file. The
artist names are the exception that needs care, because the library_artists helper
republishes its snapshot mid-round (every minute, and whenever an artist is added);
InferArtistFromTitleRule follows that snapshot itself.

The order of each list is the order the song class used to append in; it is behaviour,
not style (see the comments at the entries).
"""

from __future__ import annotations

from collections.abc import Callable

from services.common.Helpers import RoundScope
from services.common.Helpers.Cache import databaseHelpers
from services.tagger.Song.rules.AddMissingArtistToDatabaseRule import AddMissingArtistToDatabaseRule
from services.tagger.Song.rules.CaptureDisplayArtistRule import CaptureDisplayArtistRule
from services.tagger.Song.rules.CheckArtistRule import CheckArtistRule
from services.tagger.Song.rules.CleanTagsRule import CleanTagsRule
from services.tagger.Song.rules.CleanTitleRule import CleanTitleRule
from services.tagger.Song.rules.InferArtistFromTitleRule import InferArtistFromTitleRule
from services.tagger.Song.rules.InferFeatureFromTitleRule import InferFeatureFromTitleRule
from services.tagger.Song.rules.InferFestivalFromTitleRule import InferFestivalFromTitleRule
from services.tagger.Song.rules.InferGenreFromAlbumArtistRule import InferGenreFromAlbumArtistRule
from services.tagger.Song.rules.InferGenreFromArtistRule import InferGenreFromArtistRule
from services.tagger.Song.rules.InferGenreFromLabelRule import InferGenreFromLabelRule
from services.tagger.Song.rules.InferGenreFromSubgenreRule import InferGenreFromSubgenreRule
from services.tagger.Song.rules.InferPodcastFromTitleRule import InferPodcastFromTitleRule
from services.tagger.Song.rules.InferReleaseDateFromNfoRule import InferReleaseDateFromNfoRule
from services.tagger.Song.rules.InferRemixerFromTitleRule import InferRemixerFromTitleRule
from services.tagger.Song.rules.ReplaceInvalidUnicodeRule import ReplaceInvalidUnicodeRule
from services.tagger.Song.rules.ResolveGenreRule import ResolveGenreRule
from services.tagger.Song.rules.TagRule import TagRule

SOUNDCLOUD = 'soundcloud'
YOUTUBE = 'youtube'
LABEL = 'label'
GENERIC = 'generic'


def _remixer_rule() -> InferRemixerFromTitleRule:
    return InferRemixerFromTitleRule(
        artist_db=databaseHelpers['library_artists'], ignored_db=databaseHelpers['rules_ignored_artists']
    )


def _add_missing_artist_rule() -> AddMissingArtistToDatabaseRule:
    return AddMissingArtistToDatabaseRule(
        artist_db=databaseHelpers['library_artists'], ignored_db=databaseHelpers['rules_ignored_artists']
    )


def _check_artist_rule() -> CheckArtistRule:
    return CheckArtistRule(
        artist_db=databaseHelpers['library_artists'], ignored_db=databaseHelpers['rules_ignored_artists']
    )


def _infer_artist_rule() -> InferArtistFromTitleRule:
    return InferArtistFromTitleRule(
        artist_db=databaseHelpers['library_artists'],
        ignored_db=databaseHelpers['rules_ignored_artists'],
        genre_db=databaseHelpers['rules_genres'],
    )


def build_soundcloud_rules() -> list[TagRule]:
    """SoundcloudSong's rules (and TelegramSong's, which inherits them)."""
    return [
        CleanTitleRule(),
        _infer_artist_rule(),
        _remixer_rule(),
        InferFeatureFromTitleRule(),
        # SoundCloud is where the warm-up mixes and podcast-length sets land.
        InferFestivalFromTitleRule(helper=databaseHelpers['festivalHelper']),
        InferPodcastFromTitleRule(helper=databaseHelpers['podcastHelper']),
        CleanTagsRule(),
        InferGenreFromArtistRule(helper=databaseHelpers['artistGenreHelper']),
        InferGenreFromSubgenreRule(databaseHelpers['subgenreHelper']),
        CleanTagsRule(),
        _add_missing_artist_rule(),
        ResolveGenreRule(databaseHelpers['genre_rules']),
        CleanTagsRule(),
        _check_artist_rule(),
        # Last of the artist rules on purpose: it writes the credit the title stated
        # only if that credit still names the artists the file ended up with.
        CaptureDisplayArtistRule(),
        ReplaceInvalidUnicodeRule(),
    ]


def build_youtube_rules() -> list[TagRule]:
    """YoutubeSong's rules: SoundCloud's, plus the channel-to-genre lookup."""
    return [
        CleanTitleRule(),
        _infer_artist_rule(),
        _remixer_rule(),
        InferFeatureFromTitleRule(),
        InferFestivalFromTitleRule(helper=databaseHelpers['festivalHelper']),
        InferPodcastFromTitleRule(helper=databaseHelpers['podcastHelper']),
        CleanTagsRule(),
        InferGenreFromArtistRule(helper=databaseHelpers['artistGenreHelper']),
        InferGenreFromAlbumArtistRule(),
        InferGenreFromSubgenreRule(databaseHelpers['subgenreHelper']),
        CleanTagsRule(),
        _add_missing_artist_rule(),
        ResolveGenreRule(databaseHelpers['genre_rules']),
        CleanTagsRule(),
        _check_artist_rule(),
        # Last of the artist rules on purpose, as for SoundCloud.
        CaptureDisplayArtistRule(),
        ReplaceInvalidUnicodeRule(),
    ]


def build_label_rules() -> list[TagRule]:
    """LabelSong's rules."""
    return [
        _remixer_rule(),
        CleanTagsRule(),
        InferGenreFromArtistRule(helper=databaseHelpers['artistGenreHelper']),
        # The publisher LabelSong just wrote from the path, read back as a genre signal.
        # This rule was in no song type's list before, so `rules_label_genre` was only ever
        # consulted through InferGenreFromAlbumArtistRule -- which reads the same table
        # keyed on a YouTube channel. Nothing read it keyed on a publisher, so an actual
        # label release came out with no genre at all whenever its artists carried no rule
        # of their own, and its 49 curated rows did nothing for the EPs tree.
        # Placed before the subgenre rule so a label's genre is broadened too. Its position
        # relative to the artist rule decides nothing: merge_and_sort_genres returns
        # sorted(set(...)), so neither signal takes precedence over the other.
        InferGenreFromLabelRule(helper=databaseHelpers['labelGenreHelper']),
        InferGenreFromSubgenreRule(databaseHelpers['subgenreHelper']),
        CleanTagsRule(),
        _add_missing_artist_rule(),
        ResolveGenreRule(databaseHelpers['genre_rules']),
        CleanTagsRule(),
        InferReleaseDateFromNfoRule(format_helper=databaseHelpers['sceneGroupDateFormatHelper']),
        _check_artist_rule(),
        ReplaceInvalidUnicodeRule(),
    ]


def build_generic_rules() -> list[TagRule]:
    """GenericSong's rules: Livesets, Podcasts, Top 100, Warm Up Mixes and the import queue."""
    return [
        _remixer_rule(),
        # The Livesets, Podcasts and Warm Up Mixes folders all arrive here, so this is
        # where most of the actual festival recordings pass through, and the Podcasts
        # folder is the whole reason the show rule has to run here too.
        InferFestivalFromTitleRule(helper=databaseHelpers['festivalHelper']),
        InferPodcastFromTitleRule(helper=databaseHelpers['podcastHelper']),
        CleanTagsRule(),
        InferGenreFromArtistRule(helper=databaseHelpers['artistGenreHelper']),
        InferGenreFromSubgenreRule(databaseHelpers['subgenreHelper']),
        CleanTagsRule(),
        _add_missing_artist_rule(),
        ResolveGenreRule(databaseHelpers['genre_rules']),
        _check_artist_rule(),
        ReplaceInvalidUnicodeRule(),
    ]


BUILDERS: dict[str, Callable[[], list[TagRule]]] = {
    SOUNDCLOUD: build_soundcloud_rules,
    YOUTUBE: build_youtube_rules,
    LABEL: build_label_rules,
    GENERIC: build_generic_rules,
}


def rules_for(kind: str) -> list[TagRule]:
    """The rules for one song type: the round's shared ones inside a round, fresh ones outside.

    Always a new list, so a song appending to its own `rules` never changes the round's.
    """
    build = BUILDERS[kind]
    scope = RoundScope.current()
    if scope is None:
        return build()
    return list(scope.memo(('rule_stack', kind), build))
