import re
from services.tagger.Song.rules.TagRule import TagRule
from services.tagger.Song.SongHelper import split_artists
from services.tagger.constants import TITLE, ARTIST

class InferFeatureFromTitleRule(TagRule):
    """
    Extracts featured artists from the title (e.g., 'Title feat. Artist' or 'Title (ft. Artist)')
    and adds them to the ARTIST tag.
    """

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(TITLE)
        if not title:
            return False
        patterns = ['[\\(\\[]\\s*(?i:feat\\.?|ft\\.?|featuring|features|with|invite|invites|pres\\.?|presents?)\\s+([^\\]\\)]+)\\s*[\\)\\]]', '\\s+\\b(?i:feat\\.?|ft\\.?|featuring|features|with|invite|invites|pres\\.?|presents?)\\s+(.*)$']
        modified = False
        for pattern in patterns:
            match = re.search(pattern, title)
            if match:
                feature_str = match.group(1).strip()
                full_match = match.group(0)
                artists = split_artists(feature_str)
                artist_tag = song.tag_collection.get_item(ARTIST)
                added_any = False
                for a in artists:
                    if a.lower() not in [existing.lower() for existing in artist_tag.to_array()]:
                        artist_tag.add(a)
                        added_any = True
                if added_any:
                    artist_tag.deduplicate()
                title = title.replace(full_match, '').strip()
                title = re.sub('\\s*\\(\\s*\\)\\s*', ' ', title)
                title = re.sub('\\s*\\[\\s*\\]\\s*', ' ', title)
                title = re.sub('\\s+', ' ', title).strip()
                modified = True
        if modified:
            song.tag_collection.set_item(TITLE, title)
            return True
        return False