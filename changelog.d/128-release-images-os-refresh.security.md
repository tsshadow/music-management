- **Release images pick up the day's OS security updates again.** The Dockerfiles' `apt-get
  upgrade` / `apk upgrade` steps came out of the CI runner's layer cache, so the LMS image shipped
  with 0.82.1 still carried an upgrade from 2026-09-17 and a libexpat with a fixed HIGH CVE
  (CVE-2026-93990). A build argument that changes daily now forces that layer to rebuild, and the
  public base images are pulled fresh (bug report 128).

<!-- release notes -->

- **Server images include the latest operating-system security fixes** at every release.
