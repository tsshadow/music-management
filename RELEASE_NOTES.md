# Release Notes - Music Management Suite

This project is now modularized. Detailed release notes for each module can be found in their respective directories:

- [Scanner Module](services/scanner/RELEASE_NOTES.md)
- [Tagger Module](services/tagger/RELEASE_NOTES.md)
- [Downloader Module](services/downloader/RELEASE_NOTES.md)
- [Importer Module](services/importer/RELEASE_NOTES.md)
- [Music Manager](services/music_manager/RELEASE_NOTES.md)
- [ML Analyzer](services/ml-analyzer/RELEASE_NOTES.md)

## Global Version 2.1.31 (2026-07-05)
### 🛡️ Health & Activity Dashboard
- **System Monitoring**: The Control Center now has a dedicated "Health & Activity" tab for a complete overview of the system.
- **Container Health**: Real-time status overview of all Docker containers (Running/Stopped).
- **In-App Logs**: View the last 200 lines of logs from each container directly without using SSH.
- **Activity Stream**: Instantly see which tracks have recently been added by the downloaders or processed by the tagger.

## Global Version 2.1.30 (2026-07-05)
### 🔑 LMS Subsonic API Key Integration
- **Configurable Subsonic Key**: LMS now supports the `LMS_SUBSONIC_API_KEY` environment variable. This allows the Subsonic API key to be set directly without manual database changes, ensuring a seamless connection with apps like Ultrasonic.

## Global Version 2.1.29 (2026-07-05)
### 🔐 Centralized Auth & Network Hardening
- **User Service Identity Provider**: Repurposed the User Service to act as a central auth authority. It now exposes an `/auth/verify` endpoint that validates tokens for other services.
- **Enhanced Verification**: Services can now offload API key verification to the User Service, which supports both global and user-specific keys from the database.
- **Port Minimization**: Removed public port exposures for internal microservices (`Rating`, `Scrobble`, `User`). They are now only accessible within the secure Docker network.
- **Internal DNS Integration**: Optimized service communication by utilizing Docker's internal networking, improving both security and performance.

## Global Version 2.1.28 (2026-07-04)
### 🛠 Infrastructure Fix
- **Configuration Persistence**: Ensured that the newly introduced `LMS_SUBSONIC_API_KEY` is correctly propagated through the main Docker Compose configuration, finalizing the fix for LMS user synchronization.

## Global Version 2.1.27 (2026-07-04)
### 🔒 Security & Multi-Service Authentication
- **LMS API Key Separation**: Resolved a key mismatch where LMS required an older UUID token while muma services were updated to a new key. Introduced `LMS_SUBSONIC_API_KEY` to handle this.
- **Improved Diagnostics**: The User Service now provides detailed feedback on Subsonic API responses, helping to identify "Unknown API method" errors on older LMS versions.

## Global Version 2.1.26 (2026-07-04)
### 🐛 Bugfixes & LMS Connectivity
- **Subsonic API Auth**: Fixed an authentication failure when syncing users with LMS. The system now correctly passes the `apiKey` as a query parameter, satisfying LMS security requirements.

## Global Version 2.1.25 (2026-07-04)
### 🔒 Security & LMS Integration
- **API Key Alignment**: Fixed a configuration issue where microservices were receiving inconsistent API keys. Now, `user-service`, `rating-system`, and `scrobble-service` correctly use their dedicated keys.
- **Verified LMS Sync**: Confirmed that the User Service properly includes the `X-API-Key` header when communicating with LMS/Subsonic endpoints.

## Global Version 2.1.24 (2026-07-04)
### 📺 YouTube & Cookie Integration
- **YouTube Control**: A new dedicated "YouTube Accounts" tab in the Control Center allows for easy management of channels to be scanned.
- **Shared Firefox Cookies**: Integrated support for using cookies from a running Firefox container. This enables the downloaders to access restricted content and reduces the likelihood of being flagged as a bot.
- **Improved UI**: Streamlined the downloader management interfaces, adding delete functionality for both SoundCloud and YouTube accounts.

## Global Version 2.1.23 (2026-07-04)
### 🛠 User Service & Sync Fixes
- **LMS Sync Reliability**: Fixed critical bugs in the LMS user synchronization task, including incorrect variable usage and indentation errors.
- **Multi-Host LMS Support**: Introduced the `LMS_HOSTS` environment variable, allowing the User Service to synchronize from multiple LMS instances simultaneously.
- **Environment Cleanup**: Corrected network configuration typos in the `.env` file to ensure stable connectivity.

## Global Version 2.1.22 (2026-07-04)
### 🔐 System-wide API Security
- **Unified API Authentication**: Implemented a mandatory `X-API-Key` validation across all backend services (`Management API`, `User Service`, `Scrobble Service`, and `Rating System`). This ensures that only authorized interactions from the Control Center are accepted.
- **Improved Token Handling**: The Control Center now includes a dedicated "API Security" section, allowing you to securely set and store your API key in the browser.
- **Service Alignment**: Synchronized the `API_KEY` configuration across all modular components to ensure seamless internal communication and proxying.
- **Infrastructure Hardening**: Integrated the `User Service` into the consolidated `full` Docker Compose configuration for better out-of-the-box deployment.

## Global Version 2.1.20 (2026-07-04)
### 🌐 Production Connectivity Fixes
- **LMS Host Alignment**: Updated default SlimServer/LMS host to `lms.teunschriks.nl` to match the actual production environment.
- **CORS Policy Update**: Expanded trusted origins to include the correct production IP and new LMS domains, ensuring seamless UI interaction across all endpoints.

## Global Version 2.1.19 (2026-07-04)
### 🔐 Unified Password Management
- **LMS Password Sync**: You can now set user passwords directly from the Muma Control Center. These passwords are automatically hashed and synchronized with your Logitech Media Server instance.
- **Enhanced Security**: Switched to industry-standard Bcrypt hashing for all user accounts, ensuring consistent security across the modular ecosystem.
- **Improved User UI**: The Users dashboard now features a dedicated security section for quick account management.

## Global Version 2.1.18 (2026-07-04)
### 🔄 Advanced LMS Integration
- **Direct Database Sync**: Added the ability to sync users directly from the LMS `lms.db` SQLite database, providing more complete account information than the API.
- **ListenBrainz Token Migration**: Automatically migrates ListenBrainz tokens found in LMS accounts to the Muma User Service.
- **Volume Mounting**: Updated infrastructure to support direct access to LMS data files for seamless background synchronization.
- **Enhanced UI**: Added new synchronization triggers to the Users dashboard to easily maintain parity with LMS.

## Global Version 2.1.17 (2026-07-04)
### 👥 Centralized User Management
- **User Service**: Introduced a dedicated service to manage Muma users and their external account credentials.
- **ListenBrainz Integration**: Users can now securely store their ListenBrainz API tokens.
- **LMS Synchronization**: One-click synchronization of players/users from Logitech Media Server.
- **Enhanced Dashboard**: New dedicated Users tab in the Control Center for streamlined administration.

## Global Version 2.1.16 (2026-07-04)
### 🐛 Scrobble Service Fixes
- **Import Stability**: Fixed a critical crash in the ListenBrainz import background task.
- **API Compliance**: Added proper User-Agent headers to external API calls.
- **Data Integrity**: Ensured ListenBrainz raw data is correctly serialized as JSON before storage.

## Global Version 2.1.15 (2026-07-04)
### 📊 Enhanced Scrobble Monitoring
- **Import Dashboard**: Added a new dedicated tab in the Control Center for the Scrobble Service.
- **Progress Tracking**: You can now monitor ListenBrainz imports in real-time with progress bars and status updates.
- **Import History**: View a log of recent imports, including total tracks found and processed.
- **API Improvements**: Enhanced the Scrobble Service with task tracking and background processing status endpoints.

## Global Version 2.1.14 (2026-07-04)
### 🎧 Introducing Scrobble Service
- **Listening History**: You can now track your listens directly in MuMa.
- **ListenBrainz Import**: Sync your existing history from ListenBrainz with a single click.
- **Unmatched Listens**: If a song isn't in your library yet, it's stored separately so you can match it later once it's imported.
- **Smart Matching**: Automated matching using MusicBrainz IDs with a robust artist/title fallback.

## Global Version 2.1.13 (2026-07-04)
### 🍏 UI Polish & Database Consistency
- **Rating System**: Renamed internal table to `rating_tracks` to align with the module's naming convention.
- **Goodbye Blue**: Fixed remaining browser default focus rings that were still showing up as blue. Everything now glows in Spotify Green.
- **Theme Consistency**: Reinforced the dark theme across all interactive components.

## Global Version 2.1.12 (2026-07-04)
### 🎨 UI Refinement & Debugging
- **Spotify Theme Finalized**: The design system is now formalized in `styleguide.md`, ensuring a consistent Spotify-inspired look across the entire Control Center.
- **Enhanced Debugging**: Added a new `--debug` flag to the build and publish scripts for easier troubleshooting of the deployment pipeline.
- **Visual Polish**: Improved color consistency and interactive states (focus/selection) for a smoother user experience.

## Global Version 2.1.11 (2026-07-04)
### 🚀 System-wide Release Notes
- **Unified Documentation**: You can now view release notes for all sub-programs directly from the Control Center home page.
- **Service Integration**: The Rating System now fully supports the versioning and monitoring API.

## Global Version 2.1.10 (2026-07-04)
### 🛠️ Final Infrastructure Hardening
- **ML Analyzer Fully Resolved**: Integrated `pymysql` and other missing core libraries into the ML Analyzer's specialized environment.
- **Cleaner Logs**: Silenced redundant database warnings in worker services, ensuring clearer and more relevant logs.

---

## Global Version 2.1.9 (2026-07-04)
### 🚀 Final Polish & Service Stability
- **ML Analyzer Active**: Fixed the ML Analyzer configuration to ensure it runs as a persistent service, enabling its version tracking and API features.
- **Telegram Reliability**: Implemented advanced asyncio loop handling for the Telegram worker, resolving persistent "Event loop is closed" errors.
- **Optimized Startup**: Removed unnecessary `yt-dlp` update checks from service startup to ensure containers boot faster.

---

## Global Version 2.1.8 (2026-07-04)
### ⚡ Performance & Reliability
- **Telegram Worker Fix**: Resolved a critical "Event loop is closed" error that caused the Telegram worker to crash repeatedly. It now uses a much more stable asynchronous initialization process.

---

## Global Version 2.1.7 (2026-07-04)
### 🛠️ Final Polishing
- **YouTube Fix**: Resolved a configuration mismatch that caused the YouTube worker to crash on startup.
- **Rating System Integration**: Officially included the new Rating System service in the build and deployment pipeline.

---

## Global Version 2.1.6 (2026-07-04)
### 🔄 Massive Dependency Fix
- **Unified Base Image**: To prevent further "ModuleNotFound" errors, all worker service code is now bundled into the base image. This ensures that any cross-service imports (like the Downloader using the Tagger's logic) work seamlessly in all containers.
- **Dependency Consolidation**: All common Python libraries are now pre-installed in the base image, reducing the chance of runtime failures in specialized workers.

---

## Global Version 2.1.5 (2026-07-04)
### 🐛 Bug Fixes
- **API Stability**: Fixed a crash in worker APIs by ensuring all necessary dependencies like `markdown` and `pydantic` are available in the base image.
- **Improved Logging**: Fixed an error masking bug that made it difficult to diagnose startup failures.
- **Service Integration**: Ensured core music management classes are correctly discoverable by all worker services.

---

## Global Version 2.1.4 (2026-07-04)
### 🛠️ Bug Fixes & Stability
- **Dependency Resolution**: Fixed a critical issue where specialized worker containers were missing core music management logic.
- **Base Image Enhancement**: Moved shared `Song` classes and `mutagen` to the base image for better consistency across workers.
- **Management API Fixes**: Resolved a crash in the Control Center caused by missing `requests` library and properly integrated it into the base image ecosystem.

---

## Global Version 2.1.3 (2026-07-04)
### 🚀 Deployment Optimization
- **Consolidated Deployment**: Merged all deployment logic into a single, unified `scripts/deploy.sh` script.
- **Improved Automation**: Streamlined the `install.sh` workflow to ensure all modular applications are processed correctly in one go.

---

## Global Version 2.1.2 (2026-07-04)
### 🏗️ Modular Architecture
- **Specialized Containers**: Each service now runs in its own lightweight, optimized Docker container.
- **Improved Performance**: Reduced image sizes by excluding unnecessary dependencies and frontend builds from background workers.
- **Module-Specific Documentation**: Introduced separate release notes and changelogs for each module to improve clarity.

---

## Version 2.1.1 (2026-07-04)
### 🏗️ Infrastructure Update
- Unified Docker deployment configuration with the new `scanner_service` name.
- Added a consolidated `docker-compose.full.yml` for easier Portainer integration.

## Version 2.1.0 (2026-07-04)

### 🎨 Artist-Genre Editor
We've introduced a powerful new editor in the Control Center! You can now easily map your favorite artists and labels to specific genres using a modern, Spotify-inspired interface. Search through your library, find the right genre, and set the rules for future imports.

### 🔍 Library Scanner
The new Library Scanner automatically indexes your music collection into the database. It finds your tracks, extracts metadata, and organizes your artists and labels without ever touching your original files.

### 🛠️ Backend Enhancements
- Expanded the Management API with dedicated endpoints for library and rule management.
- Improved database indexing for faster library lookups.

---

## Version 2.0.0 (2026-07-04)

This major release introduces a redesigned database core and significantly enhanced machine learning analysis capabilities.

### Features
- **Advanced Audio Analysis**: The ML analyzer now extracts deeper audio features including MFCC, Zero Crossing Rate, Spectral Rolloff, and Chroma features. This enables more accurate similarity matching and automated tagging.
- **Database Schema v2**: A fully refactored database engine providing significantly improved performance and data consistency for large music collections.

### Improvements
- **Analysis Stability**: Enhanced robustness for high-load analysis jobs, ensuring reliable background processing of large libraries.
- **Metadata Handling**: Improved accuracy in path mapping and configuration storage across the system.
