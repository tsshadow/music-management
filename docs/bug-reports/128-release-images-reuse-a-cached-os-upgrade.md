# Release Images Reuse A Cached OS Upgrade Layer

# status: fixed

# reported problem
`security:dependency-audit` on develop (pipeline 4103, job 41439, 2026-09-29) failed on one
finding in the production images:

```
muma/lms:latest (alpine 3.23.6)
libexpat │ CVE-2026-93990 │ HIGH │ fixed │ 2.8.4-r0 │ 2.8.5-r0
```

The LMS release Dockerfile already runs `apk upgrade` before installing its runtime packages,
precisely so a rebuild picks up fixes like this one. The image was rebuilt for 0.82.1 the day
before, so the upgrade should have reached 2.8.5-r0.

# Possible reason
The upgrade step never ran. `docker history` of the image production runs showed:

```
2026-09-17T23:33:45Z | RUN ... apk upgrade --no-cache --update && apk add ...
2026-09-17T20:37:33Z | ADD alpine-minirootfs-3.23.6-x86_64.tar.gz /
```

`scripts/ci/build-and-push-images.sh` builds with the runner's layer cache and without
`--pull`. The Dockerfile text above the upgrade had not changed since 2026-09-17, and neither had
the locally cached `alpine:3.23`, so every release since handed back the same cached layer —
upgrade included. The same holds for the `apt-get upgrade` steps in `Dockerfile.base`,
`Dockerfile.music-manager` (both stages) and `Dockerfile.tools`. The nightly
`muma:refresh-downloader` job builds its images with `--no-cache` and was not affected; the release
build was.

`--no-cache` for the release build was ruled out: the LMS build stage is a full C++ compile that
the cache exists to skip.

# solution
Each Dockerfile declares `ARG SECURITY_REFRESH` directly above its upgrade step. The build script
sets it to the UTC date and passes it, together with `--pull`, to every build whose FROM is a public
image. A changed argument value invalidates the upgrade layer and what follows it, not the stages
or layers before it, so the C++ build stage stays cached. The images built FROM `muma-base` get
neither: they use the base this same run just built.

`tests/ci/test_release_images_refresh_os_packages.py` holds both halves: an upgrading stage
declares the argument before the upgrade, and the build script passes it for that Dockerfile.

The next release rebuilds the LMS image and clears the audit finding.
