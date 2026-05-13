# 🏷️ Tagger Service

The Tagger Service is the "brain" of the library organization. It applies a series of intelligent rules to audio files to ensure metadata is clean, consistent, and complete.

## ⚙️ Core Concept: Rule-Based Tagging

The tagger doesn't just write tags; it **infers** them. It uses a pipeline of rules to:
- Guess artists/titles from filenames if tags are missing.
- Normalize genres (e.g., mapping "Hardcore Techno" to "Hardcore").
- Identify remixers and move them to the artist field.
- Detect BPM using audio analysis.
- Look up missing info in a local database of known artists/labels.

## 📂 Architecture

- `tagger_service.py`: Background worker that processes tracks in the library that are marked for re-tagging or are newly imported.
- `tagger.py`: The core logic that orchestrates rule application.
- `Song/`: Object models for different types of sources (Generic, YouTube, SoundCloud, Telegram).
- `Song/rules/`: The individual logic units (rules) applied to every song.

## 📜 Rules

Detailed information about the available tagging rules can be found in the [Rules README](Song/rules/README.MD).

## 🚀 Key Features

- **Smart Remixer Detection**: Automatically extracts remixers from titles.
- **BPM Analysis**: Real-time tempo detection for untagged files.
- **Genre Normalization**: Ensures your library isn't cluttered with 50 different variations of the same genre.
- **Multi-Source Support**: Handles specific metadata quirks from YouTube, SoundCloud, and Telegram.
