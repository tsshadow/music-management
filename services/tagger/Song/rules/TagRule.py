from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.tagger.Song.BaseSong import BaseSong


class TagRule(ABC):
    """One tagging rule, applied to a song in turn with the others."""

    @abstractmethod
    def apply(self, song: 'BaseSong') -> None:
        """Pas de regel toe op een BaseSong."""

    @property
    def name(self) -> str:
        """The name the rule is reported under: its class name."""
        return self.__class__.__name__
