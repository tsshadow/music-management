import select
import sys
from time import sleep

from postprocessing.Song.Helpers.FilterTableHelper import FilterTableHelper
from postprocessing.Song.Helpers.TableHelper import TableHelper
from postprocessing.Song.rules.TagRule import TagRule


class AddMissingArtistToDatabaseRule(TagRule):
    """
    Controleert of artiesten van een song aanwezig zijn in de artist-database of ignored-artists.
    Voegt ze toe of corrigeert ze afhankelijk van gebruikersinput.

    Logica:
    - Als artiest in 'artists' staat -> niks doen
    - Als artiest in 'ignored_artists' staat zonder correctie -> verwijderen
    - Als artiest in 'ignored_artists' staat met correctie -> corrigeren
    - Als artiest nergens staat en ask_for_missing == True -> prompt geven
    """
    def __init__(self, artist_db=None, ignored_db=None, ask_for_missing: bool = False):
        self.artist_table = artist_db or TableHelper("artists", "name")
        self.ignored_table = ignored_db or FilterTableHelper("ignored_artists", "name", "corrected_name")
        self.ask_for_missing = ask_for_missing

    def get_user_input(self, artist, artists, title, path) -> str:
        print("\n\n🔍 Nieuwe artiest gedetecteerd:")
        print(f"'{artist}' in: {', '.join(artists)} – {title} ({path})")
        print("Is dit een correcte artiest? Druk binnen 10 sec op:")
        print("[j] = ja  |  [n] = nee  |  of typ correct gespelde naam (bv. HENK of Klaas)")
        i, _, _ = select.select([sys.stdin], [], [], 10)
        if i:
            return sys.stdin.readline().strip()
        return ""



    def apply(self, song) -> None:
        all_artists = song.artists()
        if not all_artists:
            return

        for name in all_artists:
            name = name.strip()
            if not name:
                continue

            # Staat al in artist database
            if self.artist_table.exists(name):
                continue

            # Staat in ignored, met of zonder correctie
            if self.ignored_table.exists(name):
                corrected = self.ignored_table.get_corrected(name)
                if corrected:
                    # Corrigeer naam in tags
                    song.tag_collection.get_item("ARTIST").replace(name, corrected)
                    print(f"✅ '{name}' vervangen door gecorrigeerde naam '{corrected}'")
                else:
                    # Gewoon verwijderen
                    song.tag_collection.get_item("ARTIST").remove(name)
                    print(f"❌ '{name}' verwijderd (staat op ignore-lijst)")
                continue

            # Niet gevonden → vraag het na indien nodig
            if not self.ask_for_missing:
                continue

            user_input = self.get_user_input(name, all_artists, song.title(), song.path()).strip()

            if not user_input:
                # niks ingevuld, sla over
                continue

            if user_input.lower() == "j":
                self.artist_table.add(name)
                print(f"✅ '{name}' toegevoegd aan artiestendatabase")
            elif user_input.lower() == "n":
                self.ignored_table.add(name)
                song.tag_collection.get_item("ARTIST").remove(name)
                print(f"❌ '{name}' toegevoegd aan ignore-lijst en verwijderd")
            elif user_input.lower() == name.lower():
                # Alleen hoofdlettercorrectie → toevoegen aan artist db
                self.artist_table.add(user_input)
                print(f"✅ '{user_input}' toegevoegd aan artiestendatabase (case corrected)")
            else:
                # Corrigeer spelling → voeg aan ignore-lijst toe met correctie
                self.ignored_table.add(name, user_input)
                song.tag_collection.get_item("ARTIST").replace(name, user_input)
                print(f"🔁 '{name}' vervangen door '{user_input}', toegevoegd aan ignore-lijst met correctie")