import librosa

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
