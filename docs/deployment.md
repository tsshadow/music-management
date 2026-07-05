# MuMa Deployment & Setup Architecture

This document describes the deployment pipeline and setup process for the MuMa (Music Management) ecosystem.

## Overview

The MuMa ecosystem is a collection of microservices and frontend applications managed via Docker. The deployment process is designed to be flexible, supporting local development, remote builds, and production deployment on a NAS/Server.

### Core Components

1.  **`install.sh`**: The main entry point for the installation and deployment process. It orchestrates the following stages:
    *   **Build**: Compiles and builds Docker images locally or remotely.
    *   **Publish**: Pushes the built images to a Docker registry (default: Docker Hub).
    *   **Deploy**: Updates the running stack on the target machine.

2.  **`scripts/affected.sh`**: An optimization tool that detects which modules have changed since the last deployment. It helps avoid redundant builds of unaffected services.

3.  **`build.sh`**: Handles the Docker build process. Supports `--remote` and `--semi-remote` flags to offload builds to a more powerful machine (e.g., a remote LXC container).

4.  **`publish.sh`**: Pushes the built images to the registry. It also handles database backups before the deployment stage to ensure data safety.

5.  **`scripts/deploy.sh`**: The final stage of the pipeline. It:
    *   Connects to the `REMOTE_HOST` via SSH.
    *   Transfers the `docker-compose.yml` and `.env` files (encoded in Base64).
    *   Triggers `docker compose pull` and `docker compose up`.
    *   Executes database migrations (`migrate_v*.sql` files).

## Deployment Modes

*   **Local**: Build and deploy on the current machine.
*   **Remote (`--remote`)**: All builds and publishing happen on a remote Docker context (defined as `remote-lxc`).
*   **Semi-Remote (`--semi-remote`)**: Only heavy images (ML Analyzer, Tools, Main App) are built on the remote context, while lighter services are built locally. This is typically the fastest mode.

## Database Management

### Backups
Backups are automatically created during the `publish` stage for release builds (when `--debug` is not used). They are stored in `/muma/backups` on the target host. The backup is a gzipped SQL dump created using `mysqldump` inside the running MariaDB container.

### Migrations
Database schema updates are handled automatically by `scripts/deploy.sh`. It looks for `migrate_v*.sql` files in the project root and executes them against the production database using `docker exec`.

## Environment Configuration
The system relies on a `.env` file in the project root. Key variables include:
*   `REMOTE_HOST`, `REMOTE_USER`, `REMOTE_PASS`: SSH credentials for the deployment target.
*   `DOCKER_USER`: The Docker Hub username for pushing images.
*   `DB_HOST`, `DB_NAME`, `MYSQL_ROOT_PASSWORD`: Database connection details.
*   `DEPLOY_TARGET_NAME`: The name of the Docker Compose project (default: `muma`).

## Statistics & Verification
The `install.sh` script provides a `--show-stats` flag to view library statistics, and the `tools/` directory contains various scripts for inspecting database health and media integrity.
