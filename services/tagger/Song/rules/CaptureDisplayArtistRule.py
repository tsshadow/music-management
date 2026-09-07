from services.tagger.constants import ARTIST, ORIGINAL_ARTIST
from services.tagger.Song.rules.InferArtistFromTitleRule import names_in
from services.tagger.Song.rules.TagRule import TagRule


class CaptureDisplayArtistRule(TagRule):
    """Write the credit a download's title stated, once the artist list has settled.

    `InferArtistFromTitleRule` is the only rule that knows how a download's artists were
    written -- it is what split them out of the title -- so it is where the candidate
    comes from (`remember_display_artist`). But it is not where the decision belongs:
    `InferFeatureFromTitleRule` and `InferRemixerFromTitleRule` run after it and add
    artists of their own, and `CheckArtistRule` can still rename or drop one.

    Writing at extraction time therefore produced a *partial* credit. For
    `Angerfist & Miss K8 - Track (feat. Albino)` the artist tag ends up holding three
    names while the credit names two, and the web player prefers the display artist over
    the artist list -- so a track would show fewer artists than it has. A missing display
    artist is harmless (every consumer falls back to the artist list); a credit that
    contradicts the list is not.

    So the candidate is only written when it still describes the artists the file ends up
    with. Compared as a set: `CheckArtistRule` replaces a name by appending the canonical
    spelling and removing the old one, which reorders the tag without changing who is on
    it.
    """

    def apply(self, song) -> None:
        candidate = getattr(song, 'display_artist_candidate', None)
        if not candidate:
            return
        if song.tag_collection.has_item(ORIGINAL_ARTIST):
            # Either the file already carried one, or CleanTagsRule captured it from the
            # file's own artist tag. Both saw the file earlier than this did.
            return
        artists = {name.strip().lower() for name in song.tag_collection.get_item_as_array(ARTIST) if name.strip()}
        if not artists or set(names_in(candidate)) != artists:
            return
        song.tag_collection.set_item(ORIGINAL_ARTIST, candidate.strip())
