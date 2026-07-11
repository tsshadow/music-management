import re
from services.tagger.constants import ARTIST_REGEX

def split_artists(artist_str: str) -> list[str]:
    raw = re.sub(ARTIST_REGEX, ';', artist_str)
    return [name.strip() for name in raw.split(';') if name.strip()]

def merge_and_sort_genres(a, b):
    """Merges and sorts two lists of rules_genres, removing duplicates."""
    return sorted(set(list(a) + list(b)))