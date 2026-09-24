# 🏷️ Tagger Service

The Tagger Service is the "brain" of the library organization. It applies a series of intelligent rules to audio files to ensure metadata is clean, consistent, and complete.

## ⚙️ Core Concept: Rule-Based Tagging

The tagger doesn't just write tags; it **infers** them. It uses a pipeline of rules to:
- Guess library_artists/titles from filenames if tags are missing.
- Normalize rules_genres (e.g., mapping "Hardcore Techno" to "Hardcore").
- Identify remixers and move them to the artist field.
- Detect BPM using audio analysis.
- Look up missing info in a local database of known library_artists/library_labels.

## 📂 Architecture

- `tagger_service.py`: Background worker that processes library_tracks in the library that are marked for re-tagging or are newly imported.
- `tagger.py`: The core logic that orchestrates rule application.
- `Song/`: Object models for different types of sources (Generic, YouTube, SoundCloud, Telegram).
- `Song/rules/`: The individual logic units (rules) applied to every song.

## 🔁 Deep run

Every round skips the files it has already seen: `tagger_processed_files` holds the mtime the
tagger last read, and an unchanged file is passed over. That keeps the five-minute round cheap,
but it also means a rule added today never reaches a file tagged yesterday — which is how the
library ends up with festivals, labels and genres that the rules do know but the files do not.

`deep_run.py` closes that gap. Before every round it hands the oldest slice of the table back to
the tagger, so the whole library passes the current rules roughly once every
`tagger_deep_run_days` (default 30; `0` switches it off). `tagger_deep_run_batch` (default 200)
bounds one slice, so the deep run costs seconds per round instead of hours once a month.

Re-reading a file is cheap: a rule that produces the same value writes nothing, so a slice that
finds no news touches no files and gives LMS nothing to re-index.

## ⏸ Files that keep failing

A file that raises in the tagger is not retried every round. Its queue row counts the failures
(`attempts`, `last_attempt`); the next try waits `2^attempts × 5 minutes`, and the fifth failure in
a row (`TAGGER_PARK_AFTER`) parks the file with reason `failed` until it changes on disk or a retag
is requested. The first failure logs a `WARNING` with the traceback, parking one more `WARNING`, retries only
`INFO`; none of them is an `ERROR`. The
tagger page in Beheer shows how many files are parked. See
[docs/designs/tagger/technical.md](../../docs/designs/tagger/technical.md#retag-queue-backoff-and-parking).

## 📜 Rules

Detailed information about the available tagging rules can be found in the [Rules README](Song/rules/README.MD).

## 🚀 Key Features

- **Smart Remixer Detection**: Automatically extracts remixers from titles.
- **BPM Analysis**: Real-time tempo detection for untagged files.
- **Genre Normalization**: Ensures your library isn't cluttered with 50 different variations of the same genre.
- **Multi-Source Support**: Handles specific metadata quirks from YouTube, SoundCloud, and Telegram.
