# 🎼 Tagging Rules – MusicManagement

This folder contains all **tagging rules** used in the `BaseSong` subclasses of the MusicManagement project. Each rule implements the `TagRule` interface and applies automatic metadata corrections, cleanup, or enrichment based on audio file tags.

## 📦 Contents

### 🔊 BPM Analysis

- **`AnalyzeBpmRule.py`**  
  Calculates the tempo (BPM) of an audio file using `librosa` and stores it in the `BPM` tag.

---

### 🧹 Cleaning & Normalization

- **`CleanAndFilterGenreRule.py`**  
  Removes invalid or irrelevant genres and filters out duplicates or inconsistent entries.

- **`CleanArtistFieldsRule.py`**  
  Trims whitespace, reformats artist names, and applies regex-based cleanup on the `ARTIST` tag.

- **`NormalizeFlacTagsRule.py`**  
  Normalizes tag keys and values specifically for FLAC files (e.g., capitalization or uncommon tag formats).

---

### 🎭 Genre Inference

- **`InferGenreFromAlbumArtistRule.py`**  
  Infers genre from the `ALBUM_ARTIST` tag using database lookups.

- **`InferGenreFromArtistRule.py`**  
  Infers genre based on the primary `ARTIST`, using known mappings from a lookup table.

- **`InferGenreFromLabelRule.py`**  
  Infers genre based on the `PUBLISHER`, typically for label releases.

- **`InferGenreFromSubgenreRule.py`**  
  Maps a given `SUBGENRE` tag to a standardized `GENRE`.

---

### 🎉 Extra Metadata Detection

- **`InferFestivalFromTitleRule.py`**  
  Extracts a festival or event name from the `TITLE` tag and assigns it to the `FESTIVAL` tag if recognized.

- **`InferRemixerFromTitleRule.py`**  
  Detects remixers or editors from parenthetical phrases in the title (e.g., "(XYZ Remix)") and adds them to both the `ARTIST` and optionally `REMIXERS` tags. Prompts the user if an unknown remixer is found.

---

## 📐 Usage

Rules are applied from within a `BaseSong` subclass using `self.rules.append(...)` and executed via `run_all_rules()`:

```python
for rule in self.rules:
    rule.apply(self)
