from .normalizer import ArtistNameNormalizer

class ArtistMatcher:

    def __init__(self, db_conn=None):
        self.db_conn = db_conn
        self.normalizer = ArtistNameNormalizer()

    def calculate_confidence(self, target_artist, candidate_artist):
        """
        target_artist: dict with 'name', 'mbid', 'id'
        candidate_artist: dict with 'name', 'mbid', 'source', 'source_id', etc.
        """
        score = 0
        target_name_norm = self.normalizer.normalize(target_artist.get('name', ''))
        candidate_name_norm = self.normalizer.normalize(candidate_artist.get('name', ''))
        target_name_slug = ''.join(filter(str.isalnum, target_name_norm))
        candidate_name_slug = ''.join(filter(str.isalnum, candidate_name_norm))
        import difflib
        ratio = difflib.SequenceMatcher(None, target_name_norm, candidate_name_norm).ratio()
        if target_name_norm == candidate_name_norm:
            score += 60
        elif target_name_slug == candidate_name_slug:
            score += 55
        elif ratio > 0.9:
            score += 45
        elif ratio > 0.8:
            score += 35
        elif ratio > 0.7:
            score += 25
        elif ratio < 0.5:
            score -= 40
        if target_artist.get('mbid') and candidate_artist.get('mbid'):
            if target_artist['mbid'] == candidate_artist['mbid']:
                score += 100
        if candidate_artist.get('is_known_match'):
            score += 100
        label_keywords = ['records', 'label', 'channel', 'collective', 'tv']
        if any((kw in candidate_artist.get('name', '').lower() for kw in label_keywords)):
            score -= 30
        if candidate_artist.get('source') == 'spotify' and candidate_artist.get('popularity', 0) > 50:
            score += 10
        if candidate_artist.get('source') == 'soundcloud' and candidate_artist.get('linked_artist_id') == target_artist.get('id'):
            score += 40
        return max(0, min(100, score))

    def should_auto_accept(self, confidence):
        return confidence >= 80

    def is_candidate(self, confidence):
        return confidence >= 50