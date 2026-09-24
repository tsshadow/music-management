- **Image builds no longer pull whatever is newest on the day.** yt-dlp is pinned (2026.8.19) in
  `requirements.txt` and both images that install it, and Renovate bumps the three together in one
  MR, automerged when green: a new yt-dlp is now a merge request instead of an implicit rebuild.
  `muma:refresh-downloader` still ships it between releases, by installing the version pinned on
  develop. deno (v2.9.7) and the ffmpeg, Wt, stb and TagLib tarballs in the LMS image are pinned and
  checked against a sha256 after download; phpmyadmin, jlesage/firefox, autoheal, nginx and the
  Android SDK image are pinned to a version and a digest instead of `latest`. A new test fails on any
  unchecked download or floating image. How to bump: `docs/deployment.md`, "Pinned build inputs".
  See bug report 067.

<!-- release notes -->

- **Builds:** every downloaded build input and third-party image is pinned to a version and
  checksum; yt-dlp updates now arrive as their own reviewed change.
