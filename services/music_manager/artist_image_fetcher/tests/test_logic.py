import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from services.music_manager.artist_image_fetcher.normalizer import ArtistNameNormalizer
from services.music_manager.artist_image_fetcher.matcher import ArtistMatcher

def test_normalizer():
    norm = ArtistNameNormalizer()
    assert norm.normalize("A-Lusion") == "a lusion"
    assert norm.normalize("The Artist - Official") == "the artist"
    assert norm.normalize("Label_Records") == "label"
    print("Normalizer tests passed!")

def test_matcher():
    matcher = ArtistMatcher()
    target = {'id': 1, 'name': 'A-Lusion', 'mbid': 'abc'}

    # Exact match
    cand1 = {'name': 'A-Lusion', 'mbid': 'abc', 'source': 'spotify'}
    score1 = matcher.calculate_confidence(target, cand1)
    assert score1 >= 100 # 50 (name) + 100 (mbid)

    # Name match only
    cand2 = {'name': 'a lusion', 'source': 'lastfm'}
    score2 = matcher.calculate_confidence(target, cand2)
    assert score2 == 50

    # Mismatch
    cand3 = {'name': 'Different Artist', 'source': 'spotify'}
    score3 = matcher.calculate_confidence(target, cand3)
    assert score3 == 0 # 0 - 40 -> max(0, -40) = 0

    print("Matcher tests passed!")

if __name__ == '__main__':
    test_normalizer()
    test_matcher()
