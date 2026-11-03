"""The label and artist a download's channel is linked to, as evidence for its tags.

A curator links a channel (`Soundcloud/Traxtorm`, `Youtube/Hysta Official`) to the label or
artist it is, in Management > Downloaders > Links (docs/designs/channel-links). This rule is
where that link reaches the files: only where a tag is empty or holds something weaker, never over
a value the file or its title actually supplied.

- PUBLISHER: a download's parse() writes the platform (`Soundcloud`), which is not a label, so the
  track had none. A linked label replaces anything `channels.is_label` refuses -- empty, a platform,
  a placeholder -- and never a real label.
- ARTIST: when the title names nobody, the song type writes the channel folder or the uploader as
  the artist (`Song.channel_stand_ins`). Exactly those values, compared by the artist name key, are
  replaced by the linked artist; a name the title supplied is left alone. An empty ARTIST gets the
  linked artist.

It runs straight after InferArtistFromTitleRule (see rule_stack), so the title has had its say,
and before the genre and artist curation rules, so CheckArtistRule's corrections and rejections
still apply to the linked name like to any other.
"""

from __future__ import annotations

from services.common.channels import is_label
from services.common.text_normalize import unicode_name_key
from services.tagger.constants import ARTIST, PUBLISHER
from services.tagger.Song.rules.TagRule import TagRule


class ApplyChannelLinkRule(TagRule):
    """Fill the publisher and a stand-in artist from the channel's confirmed link."""

    def __init__(self, helper=None):
        from services.common.Helpers.Cache import databaseHelpers

        self.helper = helper if helper is not None else databaseHelpers.get('channelLinkHelper')

    def apply(self, song) -> None:
        if self.helper is None:
            return
        link = self.helper.link_for(song.path())
        if link is None:
            return
        if link.label and not is_label(song.publisher()):
            song.tag_collection.set_item(PUBLISHER, link.label)
        if link.artist:
            self._apply_artist(song, link.artist)

    @staticmethod
    def _apply_artist(song, linked: str) -> None:
        current = [name.strip() for name in song.library_artists() if name and name.strip()]
        if not current:
            song.tag_collection.set_item(ARTIST, linked)
            return
        stand_ins = {unicode_name_key(name) for name in song.channel_stand_ins() if name}
        stand_ins.discard('')
        replaced: list[str] = []
        for name in current:
            value = linked if unicode_name_key(name) in stand_ins else name
            if value not in replaced:
                replaced.append(value)
        if replaced != current:
            song.tag_collection.set_item(ARTIST, ';'.join(replaced))
