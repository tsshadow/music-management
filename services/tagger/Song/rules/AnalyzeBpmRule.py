import logging
import sys
import types
from typing import Any

from services.common.config_store import ConfigStore as Settings
from services.tagger.constants import BPM
from services.tagger.Song.rules.TagRule import TagRule

try:
    import librosa
except Exception:
    _librosa_stub: Any = types.ModuleType('librosa')
    _librosa_stub.load = lambda *a, **k: ([], 0)
    beat_mod: Any = types.ModuleType('librosa.beat')
    beat_mod.beat_track = lambda *a, **k: (0, None)
    _librosa_stub.beat = beat_mod
    librosa = _librosa_stub
    sys.modules['librosa'] = librosa
    sys.modules['librosa.beat'] = beat_mod
sys.modules.setdefault(__name__ + '.librosa', librosa)
if getattr(librosa, 'beat', None):
    sys.modules.setdefault(__name__ + '.librosa.beat', librosa.beat)


class AnalyzeBpmRule(TagRule):
    """Uses librosa to estimate BPM and stores it."""

    def apply(self, song):
        # BPM does not change once it is known, and decoding the audio is by far the
        # most expensive thing the tagger does. A retag triggered by a rule change must
        # not turn into a full re-analysis of the library.
        if song.tag_collection.get_item_as_string(BPM).strip():
            return
        try:
            y, sr = librosa.load(song.path())
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            song.tag_collection.set_item(BPM, str(round(self._as_float(tempo))))
        except Exception as e:
            if Settings().debug:
                logging.info(f'Failed to parse bpm for {song.path()}: {str(e)}')

    @staticmethod
    def _as_float(tempo) -> float:
        """librosa 0.10.1+ hands back a one-element ndarray instead of a float.

        round() on an ndarray raises TypeError, which the except above swallows, so
        without this the rule would quietly store no BPM at all.
        """
        item = getattr(tempo, 'item', None)
        return float(item()) if callable(item) else float(tempo)
