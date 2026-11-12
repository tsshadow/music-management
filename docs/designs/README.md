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
| [`account-scope/`](account-scope/) | Who sees the ListenBrainz import list (admins every account, others their own) and who may delete an account (`users.update` only, no self-delete) -- issue #38, follow-up of bug report 052. Backend, plus the Management users tab. |
| [`downloader/`](downloader/) | Ingesting tracks from SoundCloud, YouTube, and Telegram (`services/downloader`). |
| [`importer/`](importer/) | Processing incoming music from external sources / label promo pools: archive extraction, folder-structure metadata inference, tagging, and moving into the library (`services/importer`). |
| [`tagger/`](tagger/) | Metadata enforcement engine — song-type auto-detection and rule-based tagging, plus its `/api/tagger` REST API (`services/tagger`, `services/music_manager/routers/tagger.py`). |
| [`scanner/`](scanner/) | Filesystem-to-database library sync and the SoundCloud/YouTube redownload service, plus their `/api/scanner` and `/api/library/tracks/{id}/redownload` REST APIs. |
| [`ratings-scrobbling/`](ratings-scrobbling/) | Track ratings and scrobble/listen history, synchronized between `music-manager`, the LMS server, and MuMa Mobile. |
| [`ml-analyzer/`](ml-analyzer/) | Audio analysis (BPM, and the currently-unimplemented musical key/mood) feeding the library's advanced metadata (`services/ml-analyzer`). **Deprecated and disabled since 2026-09-25** -- see `services/ml-analyzer/DEPRECATED.md`. |

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
| [`label-catalog-coverage/`](label-catalog-coverage/) | The Catalogus section on the label edit page: catalogue numbers read off the release folders, grouped into series, with the observed range, what is present and which numbers are not, plus "copy as search terms". Computed on demand by `GET /api/curation/labels/{name}/catalog`. |
| [`universal-ui/`](universal-ui/) | **Proposal.** One Svelte UI for web, phone and PC: the web player in a Capacitor shell over the phone's native playback, offline, Android Auto and voice services (Path A), with restyling the Kotlin app to the web's look worked out as the alternative (Path B). Sets as a first-class mode on every surface. |
| [`logout-confirmation/`](logout-confirmation/) | The "Log out?" dialog in front of the web and app logout (issue #80): what it says, cancel changes nothing, confirm runs the unchanged sign-out of bug report 106. Frontend only. |
| [`perceived-performance/`](perceived-performance/) | The app looking as fast as it is (issue #107): a boot screen from the first frame, entity pages that draw their header from what the tapped link knew, an in-memory stale-while-revalidate cache, prefetch on pointerdown, and sections that load and fail on their own. Includes the start-up and navigation measurements. Frontend only. |
| [`deferred-queue-restore/`](deferred-queue-restore/) | The app mounting before its queue restore (issue #113): the mini player shows the restore, a track started meanwhile cancels it, and nothing reaches `PlaybackService` while it runs. Frontend only (ships in the APK). |
| [`app-start-reachability/`](app-start-reachability/) | The Android app asks the server once before restoring the queue; when it does not answer, the boot screen offers "Opnieuw proberen", "Wachten op server" and "Offline verder". Offline mode keeps only downloaded tracks in the queue, marks the app with a banner, and switches back with the full queue when the server returns. App only. |
| [`claude-readonly-access/`](claude-readonly-access/) | **Proposal.** Read-only agent access to seven hosts (issue #176): a forced-command SSH wrapper `muma-ro` with a strict allowlist parser and per-host verb sets on production, the dev VM, the CI runners, the NAS and the Proxmox node, read-only API tokens for Portainer and GitLab, logging, the MCP tools, and the rollout from production outward. |
| [`playback-error-recovery/`](playback-error-recovery/) | A track that fails to play in the app, the notification or Android Auto gets one retry from a fresh stream with its cache file dropped, then a skip to the next track; the player stops after three failed tracks in a row or at the end of the queue. App only. |

## Where agent tools look

This directory holds the one copy of the design and requirement content. Tools that expect it under a
conventional `.ai/` directory read it from here.
