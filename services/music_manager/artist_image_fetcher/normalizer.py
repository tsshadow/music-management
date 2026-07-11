import re

class ArtistNameNormalizer:

    @staticmethod
    def normalize(name):
        if not name:
            return ''
        normalized = name.lower()
        normalized = normalized.replace('_', ' ').replace('-', ' ')
        normalized = re.sub('\\s+', ' ', normalized).strip()
        suffixes = ['\\s+official$', '\\s+records$', '\\s+music$', '\\s+tv$', '\\s+hq$']
        for suffix in suffixes:
            normalized = re.sub(suffix, '', normalized)
        return normalized

    @staticmethod
    def get_sort_name(name):
        if not name:
            return ''
        if name.lower().startswith('the '):
            return name[4:] + ', The'
        return name