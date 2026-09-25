import select
import sys

from services.common.Helpers.FilterTableHelper import FilterTableHelper
from services.common.Helpers.TrustedArtistHelper import TrustedArtistHelper
from services.tagger.constants import ARTIST
from services.tagger.Song.rules.TagRule import TagRule


class AddMissingArtistToDatabaseRule(TagRule):
    """
    Controleert of artiesten van een song aanwezig zijn in de artist-database of ignored-library_artists.
    Voegt ze toe of corrigeert ze afhankelijk van gebruikersinput.

    Logica:
    - Als artiest in 'library_artists' staat -> niks doen
    - Als artiest in 'rules_ignored_artists' staat zonder correctie -> verwijderen
    - Als artiest in 'rules_ignored_artists' staat met correctie -> corrigeren
    - Als artiest nergens staat en ask_for_missing == True -> prompt geven
    """

    def __init__(self, artist_db=None, ignored_db=None, ask_for_missing: bool = False):
        from services.common.Helpers.Cache import databaseHelpers

        self.artist_table = artist_db or databaseHelpers.get('library_artists') or TrustedArtistHelper()
        self.ignored_table = (
            ignored_db
            or databaseHelpers.get('rules_ignored_artists')
            or FilterTableHelper('rules_ignored_artists', 'name', 'corrected_name', follow_chains=True)
        )
        self.ask_for_missing = ask_for_missing

    def get_user_input(self, artist, library_artists, title, path) -> str:
        """Ask on stdin, with a 10 second timeout, whether an unknown artist is real."""
        print('\n\n🔍 Nieuwe artiest gedetecteerd:')
        print(f"'{artist}' in: {', '.join(library_artists)} – {title} ({path})")
        print('Is dit een correcte artiest? Druk binnen 10 sec op:')
        print('[j] = ja  |  [n] = nee  |  of typ correct gespelde naam (bv. HENK of Klaas)')
        i, _, _ = select.select([sys.stdin], [], [], 10)
        if i:
            return sys.stdin.readline().strip()
        return ''

    def apply(self, song) -> None:
        """Check every artist of the song; corrections are made in place, order preserved."""
        # A snapshot: the returned list is the tag's live value, and the handlers below
        # change it. Iterating the live list skipped the value after every removal.
        all_artists = list(song.library_artists())
        if not all_artists:
            return
        for name in all_artists:
            self._process_single_artist(song, name, all_artists)

    def _process_single_artist(self, song, name, all_artists):
        """Route one artist name to the database, ignore-list or prompt handling."""
        name = name.strip()
        if not name:
            return
        if self.artist_table.exists(name):
            return
        if self.ignored_table.exists(name):
            self._handle_ignored_artist(song, name)
            return
        if not self.ask_for_missing:
            return
        user_input = self.get_user_input(name, all_artists, song.title(), song.path()).strip()
        if user_input:
            self._handle_user_input(song, name, user_input)

    def _handle_ignored_artist(self, song, name):
        """Replace an ignored artist by its correction at the same position, or drop it."""
        corrected = self.ignored_table.get_corrected(name)
        if corrected:
            song.tag_collection.get_item(ARTIST).replace(name, corrected)
            print(f"✅ '{name}' vervangen door gecorrigeerde naam '{corrected}'")
        else:
            song.tag_collection.get_item(ARTIST).remove(name)
            print(f"❌ '{name}' verwijderd (staat op ignore-lijst)")

    def _handle_user_input(self, song, name, user_input):
        """Apply the answer to the interactive prompt: confirm, reject or correct the name."""
        if user_input.lower() == 'j':
            self.artist_table.add(name)
            print(f"✅ '{name}' toegevoegd aan artiestendatabase")
        elif user_input.lower() == 'n':
            self.ignored_table.add(name)
            song.tag_collection.get_item(ARTIST).remove(name)
            print(f"❌ '{name}' toegevoegd aan ignore-lijst en verwijderd")
        elif user_input.lower() == name.lower():
            self.artist_table.add(user_input)
            print(f"✅ '{user_input}' toegevoegd aan artiestendatabase (case corrected)")
        else:
            self.ignored_table.add(name, user_input)
            song.tag_collection.get_item(ARTIST).replace(name, user_input)
            print(f"🔁 '{name}' vervangen door '{user_input}', toegevoegd aan ignore-lijst met correctie")
