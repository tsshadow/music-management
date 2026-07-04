# Release Notes - Music Management

## Version 2.1.2 (2026-07-04)
### 🛠️ Database Normalization & Fixes
- **MariaDB Compatibility**: Resolved syntax issues in migration scripts to ensure smooth database updates on all platforms.
- **Unified Rule Schema**: Streamlined the way artist and label genre rules are stored, making the database more efficient while maintaining full compatibility with existing tools.

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
