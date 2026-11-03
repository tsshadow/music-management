# 🛠️ Common Service & Utilities

This module contains the shared logic and database helpers the workers (downloader, importer)
and `music-manager` import. It runs nothing on its own: the HTTP API lives in
`services/music_manager`.

## 📂 Structure

- `config_store.py`: the settings store behind Management > Configuration (`ConfigStore`).
- `db_init.py`: the `CREATE TABLE` statements for the shared schema.
- `step.py`: `Step`, one stage of the importer pipeline.
- `channels.py`, `version_helper.py`: small shared helpers.
- **`Helpers/`**: Reusable utility classes.
    - `DatabaseConnector.py`: Centralized DB access.
    - `TableHelper.py`: Abstraction for database table operations.
    - `Cache.py`: Simple file-based or memory-based caching.
    - `FestivalHelper.py`: Logic for festival detection.
    - `PodcastHelper.py`: Logic for radio show and podcast series detection.

## 🛠 Usage in other services

Other services (importer, tagger, etc.) import from `services.common` to ensure consistency in database access and shared settings.
