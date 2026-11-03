# Image Builds Pulled Unpinned Inputs

# status: fixed

# reported problem
Audit item C18 (2026-09-23). The image builds pulled whatever was newest on the day of the build,
and nothing checked what arrived:

- `docker/Dockerfile.tools` downloaded yt-dlp from `releases/latest/download/yt-dlp`.
- `docker/Dockerfile.downloader` installed `yt-dlp[default,curl-cffi]` with no version and deno from
  `releases/latest/download/`; `requirements.txt` had `yt-dlp>=2026.7.4`, a floor.
- `services/music-management-server/Dockerfile-release` fetched the ffmpeg, Wt, stb and TagLib
  tarballs with `curl -sLO` -- a version in the URL, but no checksum, and without `-f`, so an HTTP
  error page would be saved under the tarball's name.
- The compose files ran `phpmyadmin:latest`, `jlesage/firefox:latest`, a bare
  `willfarrell/autoheal` (i.e. `latest`) and `nginx:alpine`; `docker/Dockerfile-android-ci` was
  `FROM mobiledevops/android-sdk-image:latest` and `Dockerfile-build-alpine` used a bare
  `tonistiigi/xx`.

Two builds of the same commit were therefore not known to contain the same software, a regression
could arrive with no diff in this repository to point at, and a tampered or regenerated tarball
would have been compiled into the LMS image without a word.

# Possible reason
- yt-dlp was floored on purpose: sites break it, and an old yt-dlp is what stops downloads. The
  floor, together with `muma:refresh-downloader` rebuilding the downloader family weekly, was how
  a fresh yt-dlp reached production between releases. Pinning was avoided because nothing bumped
  pins -- Renovate only started running in September 2026.
- The LMS Dockerfile came from upstream, which fetches its dependencies the same way. The rule in
  `renovate.json` that ignores `services/music-management-server/**` also kept these out of view.
- Compose images on `latest` were never noticed because nothing rebuilt them on a schedule; they
  moved whenever the host happened to pull.

# solution
- Every download in a Dockerfile is pinned to a version and checked with
  `echo "<sha256>  <file>" | sha256sum -c -` (`curl -f` as well, so an HTTP error fails loudly):
  ffmpeg 6.1.4, Wt 4.12.5, stb at `f1c79c0`, TagLib v2.2, deno v2.9.7. Each checksum was taken from
  the file downloaded once on 2026-09-25; deno's matches the `.sha256sum` upstream publishes.
- yt-dlp is pinned to `2026.8.19` in `requirements.txt`, `docker/Dockerfile.downloader` and
  `docker/Dockerfile.tools` (the tools image now installs it from PyPI instead of the unversioned
  binary URL). Renovate's `yt-dlp` group bumps the three in one MR, at any time and without the
  three-day cooldown, and automerges it when green; `customManagers:dockerfileVersions` reads the
  `# renovate:` comments above the ARGs. `muma:refresh-downloader` builds master but installs the
  version pinned on develop, so a Renovate bump still reaches production at the next weekly refresh
  instead of waiting for a release.
- Compose and base images name a version and a digest: `phpmyadmin:5.2.3`, `jlesage/firefox:v26.09.1`,
  `nginx:1.31.6-alpine`, `mobiledevops/android-sdk-image:36.1.0`, `tonistiigi/xx:1.9.0`, and
  `willfarrell/autoheal:latest@sha256:...` (no version tag published since 1.2.0 in 2021, so the
  digest is the pin). Renovate moves the digests; a new rule re-enables it for the LMS stack's
  `docker-compose.yml`, which is ours, not upstream's.
- `tests/ci/test_pinned_build_inputs.py` fails on a new unchecked download, a `releases/latest` URL,
  a floating image reference, or yt-dlp pins that disagree.
- the operator's runbook "Pinned build inputs" says who bumps what, and how to bump a checksummed input
  by hand.

Left open, for Teun to decide rather than this fix:

- **autoheal holds the Docker socket.** It is mounted read-only, but read-only on the socket file
  does not restrict the API behind it: any process in that container can start a privileged
  container with the host's root filesystem mounted, which is root on the host. The image is now
  pinned by digest, so a new upstream push no longer reaches the host unreviewed, but the grant
  itself is unchanged. `lms` relies on it (the `autoheal: "true"` label in
  `services/music-management-server/docker-compose.yml`), so it was kept. Alternatives are a
  socket proxy that only allows container restarts, or a healthcheck-driven restart from the host.
- **deno and the LMS tarballs are bumped by hand.** Renovate cannot compute a new checksum, so a
  deno bump MR is red until someone fills it in, and the LMS tarballs are not watched at all. deno
  matters for YouTube: a future yt-dlp-ejs that needs a newer deno would show up as signature
  failures, not as a build error.
