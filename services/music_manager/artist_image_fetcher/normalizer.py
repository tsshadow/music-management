import re

class ArtistNameNormalizer:
    @staticmethod
    def normalize(name):
        if not name:
            return ""
        
        # Lowercase
        normalized = name.lower()
        
        # Replace underscores and dashes with spaces
        normalized = normalized.replace('_', ' ').replace('-', ' ')
        
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # Remove common suffixes for matching (official, records, etc.)
        suffixes = [
            r'\s+official$',
            r'\s+records$',
            r'\s+music$',
            r'\s+tv$',
            r'\s+hq$',
        ]
        
        for suffix in suffixes:
            normalized = re.sub(suffix, '', normalized)
            
        return normalized

    @staticmethod
    def get_sort_name(name):
        if not name:
            return ""
        
        # Simple sort name: "The Artist" -> "Artist, The"
        if name.lower().startswith("the "):
            return name[4:] + ", The"
        
        return name
