# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.77.0] - 2026-07-04
### Added
- Modular build system: split `build_and_publish.sh` into `build.sh`, `publish.sh`, and `deploy.sh`.
- Portainer Webhook support for automated deployments.
- Automatic Docker group permission handling using `sg docker` re-execution.
- Standardized `.env` configuration file for deployment settings.
- `bup` shortcut for the full build and publish pipeline.
- Registry authentication pre-check in `publish.sh`.

### Changed
- Updated `install.sh` to handle `.env` creation and dependency checks automatically.
- Unified deployment environment variables (`REMOTE_STACK_PATH`, `DEPLOY_TARGET_NAME`) for multi-repo consistency.

### Fixed
- Fixed Docker Hub push denial issues by adding proactive login checks.
- Improved SSH deployment reliability by verifying remote Docker Compose paths.

## [3.76.1] - 2026-06-25
### Changed
- Bumped version for initial stack support and improved deployment scripts.
