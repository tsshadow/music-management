# 📥 Music Importer Service

This service is responsible for discovering, extracting, and organizing music files into the media library.

## ⚙️ How it works

The Importer works as a background worker that monitors a specific `__TODO` folder. When new files (archives or loose audio files) are detected, it performs the following steps:

1. **Extraction**: Unpacks `.zip` and `.rar` files.
2. **Flattening**: Removes unnecessary nested folders.
3. **Renaming**: Normalizes file names to a consistent format.
4. **Metadata Extraction**: Reads existing tags and identifies track information.
5. **Archiving**: Moves the original source (e.g., the ZIP file) to an archive folder.
6. **Library Integration**: Moves the processed audio files to the library structure (e.g., sorted by Genre/Artist).

## 📂 Components

- `importer_service.py`: The main entry point for the worker.
- `extractor.py`: Handles ZIP and RAR extraction.
- `mover.py`: Logic for moving files to their final destination.
- `renamer.py`: Sanitizes file and folder names.

## 🚀 Downloaders

The importer often works in tandem with the **Downloader Service**, which fetches music from various sources:

- **YouTube**: Tracks channels or playlists and downloads new uploads using `yt-dlp`.
- **SoundCloud**: Downloads tracks from followed artists or specific URLs.
- **Telegram**: Monitors specific channels/chats for shared audio files.

Each downloader maintains an archive database to prevent re-downloading the same tracks.

## 🛠 Configuration

Configuration is handled via environment variables (see the root `.env.example`):

- `IMPORT_FOLDER_PATH`: The "watch" folder for new files.
- `MUSIC_FOLDER_PATH`: The destination library path.
- `DB_*`: Database credentials for archive tracking.
