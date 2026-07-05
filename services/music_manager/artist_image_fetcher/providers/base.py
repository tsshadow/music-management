from abc import ABC, abstractmethod

class ArtistImageProvider(ABC):
    @property
    @abstractmethod
    def name(self):
        pass

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
        """
        pass
