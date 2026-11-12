- **`/health/backup` answered with the player page from the LAN.** Since music-manager listens on
  the host's loopback only (#218), the LAN reaches it through the player stack's nginx, and that
  sent only the exact path `/health` to music-manager. The nightly check read the LMS web page
  instead of the backup age. nginx now sends `/health/backup` to music-manager too (issue #236).
<!-- release notes -->
- **The backup check works from the LAN again.** `/health/backup` on the player's address now gives
  the age of the newest database backup.
