# 🛠️ Common Service & Utilities

This module contains shared logic, database helpers, and the main internal API that bridges the different workers and the frontend.

## 📂 Structure

- **`api/`**: The FastAPI-based server.
    - `server.py`: Main API entry point.
    - `job_manager.py`: Handles background tasks and worker status.
- **`Helpers/`**: Reusable utility classes.
    - `DatabaseConnector.py`: Centralized DB access.
    - `TableHelper.py`: Abstraction for database table operations.
    - `Cache.py`: Simple file-based or memory-based caching.
    - `FestivalHelper.py`: Logic for festival detection.

## 🌐 API

The API provides endpoints for:
- Monitoring the status of importer/tagger workers.
- Manually triggering re-scans or re-tagging jobs.
- Accessing library metadata.
- Configuration management.

## 🛠 Usage in other services

Other services (importer, tagger, etc.) import from `services.common` to ensure consistency in database access and shared settings.
