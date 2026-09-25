import re


class ArtistNameNormalizer:
    """Normalizes artist names for comparison and sorting."""

    @staticmethod
    def normalize(name):
        """Lowercase `name` and strip separators and suffixes such as "official" or "records".

        Deliberately lighter than the `services.common.text_normalize` keys: it compares a
        library artist with a channel or provider name, where the difference is platform
        noise (`_`, `-`, "Official", "Records"), and accents and punctuation are part of
        the name the provider is searched with.
        """
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
        """The name to sort `name` under: a leading "The " moves to the end."""
        if not name:
            return ''
        if name.lower().startswith('the '):
            return name[4:] + ', The'
        return name
