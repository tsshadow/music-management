---
sessionId: session-260618-195715-1jzg
isActive: true
---

# Requirements

### Overview & Goals
Rename the **LMS (Lightweight Music Server)** project to **MuMa server**.
This change aligns the music server with the **Music Management (MuMa)** ecosystem, providing a more unique and consistent identity.

### Scope
- **In Scope**:
    - Build system updates (CMake).
    - Source code refactoring (Namespaces, Class names).
    - File and directory renaming.
    - Configuration file renaming and content updates.
    - User Interface branding and translations.
    - Documentation and Docker configuration.
- **Out of Scope**:
    - Functional changes to the server logic.
    - Changes to third-party client applications.

# Technical Design

### Current Implementation
- **Project Name**: `lms`
- **Main Executable**: `lms`
- **Namespaces**: `lms`, `lms::ui`, `lms::db`, etc.
- **Config File**: `lms.conf`
- **Default Paths**: `/var/lms` (working dir), `/usr/share/lms` (resources).
- **Branding**: "LMS - Lightweight Music Server".

### Key Decisions
- **New Name**: `MuMa server`
- **New Executable**: `muma-server`
- **New Namespace**: `muma`
- **Config Filename**: `muma.conf`
- **Resource Path**: `share/muma`
- **Working Dir**: `/var/muma`

### Proposed Changes
- **CMake**: Update `project(muma ...)` and all library prefixes from `lms` to `muma`.
- **Refactoring**:
    - Global search and replace `namespace lms` with `namespace muma`.
    - Global search and replace `Lms` prefix in class names with `Muma`.
    - Rename `src/lms` directory to `src/muma`.
- **Configuration**:
    - Rename `conf/lms.conf` to `conf/muma.conf`.
    - Update default values in code for `working-dir`, `approot`, `docroot`.
- **Docker**:
    - Update service, container_name, and volume names in `docker-compose.yml`.
    - Update image tags and build instructions in `Dockerfile`s.
- **UI**:
    - Update `approot/messages.xml` to replace "LMS" with "MuMa server".
    - Update templates in `approot/*.xml` for any hardcoded strings or CSS classes (e.g., `Lms-player` -> `Muma-player`).

### File Structure Changes
- `todo/MIGRATE_TO_NEW_NAME.md` (New file)
- `src/lms/` -> `src/muma/`
- `conf/lms.conf` -> `conf/muma.conf`
- `conf/pam/lms` -> `conf/pam/muma`
- `docroot/css/lms.css` -> `docroot/css/muma.css`

# Testing

### Validation Approach
Since this is primarily a renaming task, validation will focus on ensuring the project still builds and runs correctly with the new names.

### Key Scenarios
- **Build Verification**: Run CMake and build the `muma-server` target.
- **Configuration Loading**: Ensure `muma-server` correctly loads `muma.conf` by default.
- **UI Check**: Verify that the web interface displays "MuMa server" and that resources (CSS, JS) are loaded from the new paths.
- **Docker Test**: Run `docker-compose up` and verify the container starts with the new service name and volumes.

### Edge Cases
- **Legacy Config**: Verify if the server can still (optionally) fall back to `lms.conf` or if a warning is issued.
- **Data Path**: Ensure that existing users are informed about moving their database from `/var/lms` to `/var/muma`.

# Delivery Steps

###   Step 1: Create todo/MIGRATE_TO_NEW_NAME.md
Create the `todo` directory and document the full migration plan in `todo/MIGRATE_TO_NEW_NAME.md`.
- Create the `todo/` directory in the project root.
- Create `todo/MIGRATE_TO_NEW_NAME.md` and populate it with the detailed migration steps.
- Summarize the rationale for the name change.
- List all technical steps for developers (CMake, namespaces, directory renaming).
- Provide a section for existing users on how to migrate their installation (moving config and data).

###   Step 2: Update CMake and Project Metadata
Renaming the core project and build targets.
- Update `project()` in root `CMakeLists.txt` to `MuMa`.
- Rename `lms` executable target to `muma-server`.
- Rename all library targets (e.g., `lmsaudio` -> `mumaaudio`).
- Update installation rules for `approot`, `docroot`, and config files to use `share/muma`.

###   Step 3: Codebase Refactoring
Renaming namespaces, classes, and directories in the source code.
- Rename `src/lms/` directory to `src/muma/`.
- Global rename of `namespace lms` to `muma`.
- Update class names (e.g., `LmsApplication` -> `MumaApplication`).
- Fix all include paths and header guards to reflect the new directory structure.

###   Step 4: Configuration and UI Branding
Renaming config files and updating UI text.
- Rename `conf/lms.conf` to `conf/muma.conf`.
- Update `approot/messages.xml` and other templates to use "MuMa server" branding.
- Update default internal paths (working directory, etc.) in the code to use `muma` instead of `lms`.

###   Step 5: Documentation and Docker Update
Updating all external-facing materials and container configs.
- Update `README.md`, `INSTALL.md`, and other documentation files.
- Update `docker-compose.yml` and `Dockerfile`s to use the new names and paths.
- Perform a final search for any remaining "lms" strings that should be updated.