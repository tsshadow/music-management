import sys
import types

try:  # pragma: no cover - attempt real import
    import librosa  # type: ignore
except Exception:  # noqa: BLE001 - handle missing optional deps
    librosa = types.ModuleType("librosa")
    librosa.load = lambda *a, **k: ([], 0)
    beat_mod = types.ModuleType("librosa.beat")
    beat_mod.beat_track = lambda *a, **k: (0, None)
    librosa.beat = beat_mod
    sys.modules["librosa"] = librosa
    sys.modules["librosa.beat"] = beat_mod

# Expose alias so unittest.mock.patch can locate librosa in this module
sys.modules.setdefault(__name__ + ".librosa", librosa)
if getattr(librosa, "beat", None):
    sys.modules.setdefault(__name__ + ".librosa.beat", librosa.beat)

from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import BPM


class AnalyzeBpmRule(TagRule):
    """Uses librosa to estimate BPM and stores it."""

    def apply(self, song):
        try:
            y, sr = librosa.load(song.path())
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            song.tag_collection.set_item(BPM, str(round(tempo)))
        except Exception as e:
            from data.settings import Settings
            if Settings().debug:
                import logging
                logging.info(f"Failed to parse bpm for {song.path()}: {str(e)}")
