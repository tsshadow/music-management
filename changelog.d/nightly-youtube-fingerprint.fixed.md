- **One night of YouTube refusing yt-dlp made the nightly production report unusable.** The
  fingerprint normalisation in `scripts/nightly-prod-check/collect.py` folded a SoundCloud item id
  away but not a YouTube video id: that only ever happened through the catch-all `\S*_\S*` rule,
  and a video id is eleven characters of `[A-Za-z0-9_-]`, so roughly one in three. On 2026-09-25
  that turned 22,170 downloader errors with nineteen causes into 7,638 attention items -- one per
  video, against a budget of two fix MRs -- and wrote 7,634 dead rows into the ledger. `[youtube]`
  and `[youtube:tab]` now get the same explicit rule `[soundcloud]` has; the same night folds back
  to 19 fingerprints. The replacement is `<name>` rather than `<item>:` on purpose, so every
  fingerprint the catch-all already folded -- and the verdict the ledger holds against it -- keeps
  its key.

<!-- release notes -->

- **The nightly production check summarises YouTube download failures by cause again** instead of
  by video.
