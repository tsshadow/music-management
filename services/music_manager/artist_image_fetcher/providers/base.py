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


class ProviderRateLimited(ProviderUnavailable):
    """The provider refused to answer because the run asked too often (HTTP 429).

    `retry_after` is how many seconds the provider asked us to wait, already bounded to
    something sane. Unlike any other ProviderUnavailable this one is about the whole
    run, not about one artist: the next artist would get the same 429. The fetcher
    pauses for `retry_after` instead of walking on and collecting a 429 per artist --
    on 2026-09-24 that walk produced 3.278 warnings, and a push every five minutes.
    """

    def __init__(self, message, retry_after):
        super().__init__(message)
        self.retry_after = retry_after


def parse_retry_after(response: object, default: float, maximum: float) -> float:
    """Seconds to wait according to a response's `Retry-After` header, bounded.

    Only the delta-seconds form is read. A missing, unreadable or HTTP-date value falls
    back to `default`; the result lies between 1 s and `maximum`, so a hostile or broken
    header cannot park a run for a day.
    """
    headers = getattr(response, 'headers', None) or {}
    try:
        value = headers.get('Retry-After')
    except AttributeError:
        value = None
    seconds = float(default)
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        try:
            seconds = float(value)
        except ValueError:
            seconds = float(default)
    return min(max(seconds, 1.0), float(maximum))


def has_retry_after(response: object) -> bool:
    """Whether a response carries a `Retry-After` header at all."""
    headers = getattr(response, 'headers', None) or {}
    try:
        return headers.get('Retry-After') is not None
    except AttributeError:
        return False


class ArtistImageProvider(ABC):
    """A source of artist images, such as Spotify or MusicBrainz."""

    @property
    @abstractmethod
    def name(self):
        """The name this provider is recorded under in the source column."""
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


__all__ = [
    'ArtistImageProvider',
    'ProviderRateLimited',
    'ProviderUnavailable',
    'credential',
    'has_retry_after',
    'parse_retry_after',
]
