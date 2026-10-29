- **The dependency audit accepts one more finding in pip's own vendored msgpack.** CVE-2026-114613
  (memory leak, high) is in the msgpack 1.1.2 that pip 26.2.2, the newest release, bundles in every
  Python image. pip only runs while an image is built; the msgpack the services import is 1.2.3.
  It sits in `security/trivyignore` next to the earlier advisory for the same copy, and goes when a
  pip release bundles msgpack 1.2.3 or later.
<!-- release notes -->
- The security audit no longer fails on a build-tool library that the services do not use.
