from services.tagger.Song.rules.TagRule import TagRule
from services.tagger.constants import GENRE

class MergeDrumAndBassGenresRule(TagRule):
    """Merges 'drum' and 'bass' genre tags into a single 'drum 'n bass' tag."""

    def apply(self, song):
        if not song.tag_collection.has_item(GENRE):
            return
        genre_tag = song.tag_collection.get_item(GENRE)
        genres = [g.lower() for g in genre_tag.as_list()]
        has_drum = 'drum' in genres
        has_bass = 'bass' in genres
        has_dnb = "drum 'n bass" in genres or 'drum and bass' in genres or 'dnb' in genres
        new_genres = genres.copy()
        if has_drum and has_bass:
            new_genres = [g for g in new_genres if g not in {'drum', 'bass'}]
            new_genres.append("drum 'n bass")
        elif has_bass and has_dnb:
            new_genres = [g for g in new_genres if g != 'bass']
        new_genres = ["drum 'n bass" if g in {'dnb', 'drum and bass'} else g for g in new_genres]
        genre_tag.set(new_genres)