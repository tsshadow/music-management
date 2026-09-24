- **`trigger_fetch` in the artist-images router is gone.** Since the image endpoint stopped
  scheduling a lookup on a miss, nothing but its own tests called it; the per-artist fetch that
  remains is `trigger_fetch_by_id` behind `/fetch-image`. `coverage-muma-server.xml` is no longer
  tracked either: `scripts/test/muma-server-unit.sh` writes it on every run and `server:unit`
  uploads it from there.

<!-- release notes -->

- Internal clean-up only; nothing changes for users.
