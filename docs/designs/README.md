# Feature Design Docs

This directory holds the functional/technical design for every non-trivial feature or behavior change in
this repository, as required by rule 4 in [AGENTS.md](../../AGENTS.md#-development-guidelines)
("Design-first for non-trivial features").

## Why two documents per feature

Splitting a design into a **functional** and a **technical** document keeps each one focused on the
audience that actually needs to validate it:

- **`functional.md`** — describes user-observable behavior: what happens, from whose perspective, and why.
  It should be reviewable by a non-technical stakeholder without needing to know table names or endpoint
  paths.
- **`technical.md`** — describes the implementation contract: data models, API endpoints, error cases, edge
  cases, and cross-app impact. It should be precise enough for an engineer (human or AI agent) to implement
  and test against without re-deriving intent from the rest of the codebase.

Both documents end with a numbered, testable "Acceptance Criteria" section — functional criteria describe
observable outcomes, technical criteria describe implementation-level checks (including error responses and
edge cases).

## How to start a new feature design

1. Copy the two templates in [`_template/`](_template/) into a new `docs/designs/<feature>/` directory:
   ```bash
   mkdir -p docs/designs/<feature>
   cp docs/designs/_template/functional.md docs/designs/<feature>/functional.md
   cp docs/designs/_template/technical.md docs/designs/<feature>/technical.md
   ```
2. Fill in `functional.md` first (user stories, functional flows, acceptance criteria, open questions) — get
   this agreed before writing the technical design, since the technical contract should implement an already
   agreed functional behavior, not the other way around.
3. Fill in `technical.md` (data model, API contract, cross-app impact, technical acceptance criteria),
   resolving the functional design's open questions as concrete implementation decisions.
4. Only start implementation once both documents are agreed — trivial fixes (typo, config value, dependency
   bump) don't need this process (see rule 4 in `AGENTS.md`).
5. Keep both documents up to date in the same change whenever the feature's behavior changes afterward (rule
   3 and rule 12 in `AGENTS.md` — a stale design doc is treated as a bug).

## Existing feature designs

The following features have been retroactively documented in this format, covering the current codebase as
it exists today (see each `functional.md`'s "Open Questions / Not Yet Decided" section for gaps and
undecided behavior that were flagged, not silently resolved, during this documentation pass):

| Feature | Covers |
|---|---|
| [`authentication/`](authentication/) | Login/user model — username+password login, all Google Sign-In flows, the access-request approve/link/unapprove/reject lifecycle, and user deletion. Derived from the existing, code-verified [`docs/authentication.md`](../authentication.md), which remains the deepest-detail reference. |
| [`downloader/`](downloader/) | Ingesting tracks from SoundCloud, YouTube, and Telegram (`services/downloader`). |
| [`importer/`](importer/) | Processing incoming music from external sources / label promo pools: archive extraction, folder-structure metadata inference, tagging, and moving into the library (`services/importer`). |
| [`tagger/`](tagger/) | Metadata enforcement engine — song-type auto-detection and rule-based tagging, plus its `/api/tagger` REST API (`services/tagger`, `services/music_manager/routers/tagger.py`). |
| [`scanner/`](scanner/) | Filesystem-to-database library sync and the SoundCloud/YouTube redownload service, plus their `/api/scanner` and `/api/library/tracks/{id}/redownload` REST APIs. |
| [`ratings-scrobbling/`](ratings-scrobbling/) | Track ratings and scrobble/listen history, synchronized between `music-manager`, the LMS server, and Ultrasonic. |
| [`ml-analyzer/`](ml-analyzer/) | Audio analysis (BPM, and the currently-unimplemented musical key/mood) feeding the library's advanced metadata (`services/ml-analyzer`). |

`authentication/` was the first of these, written from an already-existing deep-detail reference; the others
were written directly from the code (there was no equivalent prior document), so treat their "Open Questions"
sections as a starting point for follow-up review, not a fully agreed design.

### New feature designs (written before implementation)

Features designed and agreed through the process in this document, ahead of writing the code (as opposed to
the retroactive documentation above):

| Feature | Covers |
|---|---|
| [`favorite-genres/`](favorite-genres/) | Per-user favorite genres in the web player, persisted to the account instead of only `localStorage` (`services/frontend/src/lib/store.js`), reusing the existing generic `/api/users/{id}/settings/{app_id}` endpoints. |
| [`i18n/`](i18n/) | Web frontend internationalisation: JSON translation files, a `t()` store, and a language setting (English/Dutch) synced to the account through the same `/api/users/{id}/settings/frontend` blob as favorite genres. Mechanism only — converting the existing screens is a follow-up. |
| [`ultrasonic-session-and-loading/`](ultrasonic-session-and-loading/) | Android client: per-section skeleton loading on the home screen, a "Log out" entry, and returning to the login screen when the server rejects the stored password (Subsonic error 40). Client-side only. |

## Relationship to `.ai/docs` and `.ai/requirements`

Some AI-agent tools look for design/requirement content under a conventional `.ai/` directory. This repo
keeps exactly one copy of the actual content, here in `docs/designs/`; [`.ai/docs/README.md`](../../.ai/docs/README.md)
and [`.ai/requirements/README.md`](../../.ai/requirements/README.md) are thin pointer files that simply
redirect here, so no content has to be duplicated or kept in sync between two trees.
