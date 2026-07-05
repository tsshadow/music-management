# Contributing to LMS

Thank you for your interest in contributing to LMS! We welcome contributions of all kinds, including bug reports, feature requests, documentation improvements, and code changes.

## Table of Contents
- [How to Contribute](#how-to-contribute)
- [Development Environment Setup](#development-environment-setup)
  - [Backend (C++)](#backend-c)
  - [Frontend (Svelte)](#frontend-svelte)
- [Code Quality & Style](#code-quality--style)
- [Testing](#testing)

## How to Contribute

### Reporting Bugs
- Use the **Bug Report** template when opening a new issue.
- Provide as much detail as possible, including logs and steps to reproduce.

### Suggesting Enhancements
- Use the **Feature Request** template.
- Explain why the enhancement would be useful and how it should work.

### Pull Requests
- Fork the repository and create your branch from `master`.
- Ensure your code follows the project's style and quality guidelines.
- Add or update tests for your changes.
- Provide a clear description of the changes in your PR.

## Development Environment Setup

### Backend (C++)

#### Prerequisites
You will need a C++20 compiler and the following dependencies:
- CMake (3.12+)
- Boost (program_options, iostreams)
- Wt4 (with Dbo, Sqlite3, HTTP)
- FFmpeg (4+)
- Taglib
- Pugixml
- OpenSSL
- SQLite3
- Libarchive
- xxHash

On Debian/Ubuntu:
```sh
sudo apt-get install build-essential cmake libboost-program-options-dev libboost-system-dev libavutil-dev libavformat-dev libswresample-dev ffmpeg libconfig++-dev libstb-dev libtag-dev libpugixml-dev libgtest-dev libarchive-dev libxxhash-dev libssl-dev
```
Note: Wt4 may need to be compiled from source if not available in your distribution's repositories.

#### Building
```sh
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Debug -DENABLE_TESTS=ON
make -j$(nproc)
```

### Frontend (Svelte)
The modern MuMa Spotify is built with Svelte and Vite.

#### Prerequisites
- Node.js (v18+)
- npm

#### Development
```sh
cd src/lms/ui/spotify-ui
npm install
npm run dev
```
By default, the dev server will attempt to proxy API requests to `http://localhost:5082`. Ensure your backend is running.

## Code Quality & Style

LMS follows strict code quality guidelines. Please refer to [CODE_QUALITY.md](CODE_QUALITY.md) for more details.

- **Formatting**: Use `clang-format`. A `.clang-format` file is provided in the root.
- **Static Analysis**: We use `clang-tidy` and `cppcheck`.
- **Naming Conventions**:
  - Classes: `PascalCase`
  - Methods/Functions: `camelCase`
  - Member variables: `_camelCase` (with underscore prefix)
  - Files: `PascalCase.cpp/hpp`

## Testing
We use **GoogleTest** for unit testing.

To run tests:
```sh
cd build
make test
# Or for more detail:
ctest -V
```
Always ensure tests pass before submitting a PR.
