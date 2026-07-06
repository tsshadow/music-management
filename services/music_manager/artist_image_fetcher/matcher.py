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
        
        # Name matching
        import difflib
        ratio = difflib.SequenceMatcher(None, target_name_norm, candidate_name_norm).ratio()
        
        if target_name_norm == candidate_name_norm:
            score += 50
        elif ratio > 0.9:
            score += 40
        elif ratio > 0.8:
            score += 30
        elif ratio > 0.7:
            score += 20
        elif ratio < 0.5:
            score -= 40
            
        # MBID match
        if target_artist.get('mbid') and candidate_artist.get('mbid'):
            if target_artist['mbid'] == candidate_artist['mbid']:
                score += 100
                
        # Existing external ID match (if we have it in candidate_artist metadata)
        if candidate_artist.get('is_known_match'):
            score += 100
            
        # Label/records/channel detected in candidate name
        label_keywords = ['records', 'label', 'channel', 'collective', 'tv']
        if any(kw in candidate_artist.get('name', '').lower() for kw in label_keywords):
            score -= 30
            
        # Spotify popularity hint (optional)
        if candidate_artist.get('source') == 'spotify' and candidate_artist.get('popularity', 0) > 50:
            score += 10
            
        # SoundCloud hint
        if candidate_artist.get('source') == 'soundcloud' and candidate_artist.get('linked_artist_id') == target_artist.get('id'):
            score += 40

        # Bound score between 0 and 100
        return max(0, min(100, score))

    def should_auto_accept(self, confidence):
        return confidence >= 80

    def is_candidate(self, confidence):
        return confidence >= 50
