- **A label page lists the channels linked to it** (issue #122, `docs/designs/channel-links/`).
  Under the label's heading a **Kanalen** section shows every SoundCloud, YouTube or Telegram channel a
  curator linked to that label, busiest first, with its platform and number of tracks; tapping one
  opens the channel's tracks (the `Soundcloud (<channel>)` / `Youtube (<channel>)` album), or the
  account's page on the platform when the library has no such album. A curator also gets
  **Koppelingen beheren**, which opens Beheer -> Downloaders on the Koppelingen tab, and sees the
  section (with its placeholders) on every label; a listener only on a label that has channels, so the
  track list does not jump on the many that have none. On production (2026-09-27) no channel is
  linked yet -- 898 proposals await review -- so the section fills as they are confirmed. New:
  `GET /api/channel-links/by-label?name=` (read-only, index lookups only, no schema change).
<!-- release notes -->
- A label page now shows the SoundCloud, YouTube and Telegram channels linked to that label.
