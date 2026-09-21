from abc import ABC, abstractmethod

from services.common.config_store import credential


class ProviderUnavailable(Exception):
    """The provider could not answer -- which says nothing about the artist.

    Raised for a missing or rejected credential, a rate limit, a 5xx or a transport
    error. The fetcher treats it as "ask again later", never as "no image exists":
    between 2026-08-22 and 2026-09-21 every provider ran without credentials and
    45.000 artists -- Sefa, Partyraiser, Dr. Peacock among them -- were recorded as
    `failed` on the strength of an empty answer nobody had actually given.
    """


class ArtistImageProvider(ABC):
    @property
    @abstractmethod
    def name(self):
        pass

    @property
    def configured(self) -> bool:
        """Whether this provider has what it needs to answer at all.

        A provider that is not configured is left out of the run, and a run with no
        configured provider records nothing: it cannot tell an unfindable artist from
        its own blindness.
        """
        return True

    @abstractmethod
    def get_artist_images(self, artist_name, mbid=None, external_ids=None):
        """
        Returns a list of candidate images.
        Each candidate is a dict with:
        - source: provider name
        - source_id: id from the source
        - url: original image url
        - width: width (if known)
        - height: height (if known)
        - confidence: provider-specific confidence hint
        - metadata: dict with extra info (e.g. artist name on source)

        Raises ProviderUnavailable when the provider could not answer. An empty list
        is a real answer: the provider looked and found nothing.
        """


__all__ = ['ArtistImageProvider', 'ProviderUnavailable', 'credential']
