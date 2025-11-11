from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from postprocessing.Song.BaseSong import BaseSong

class TagRule(ABC):
    @abstractmethod
    def apply(self, song: "BaseSong") -> None:
        """Pas de regel toe op een BaseSong."""
        pass

    @property
    def name(self) -> str:
        return self.__class__.__name__
