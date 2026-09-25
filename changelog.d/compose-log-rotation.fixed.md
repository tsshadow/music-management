- **Every container's log is capped, not only the main stack's.** Docker keeps container logs
  without a size limit by default, and a full disk on the production host has already looked like
  a 502. Bug report 050 capped the services in `docker/docker-compose.yml`. The `lms` stack, the
  backup jobs, the CI test stack and the other compose files now get the same json-file rotation
  (10 MB x 3). LMS and its nginx front get 20 MB x 5, because they log every request. A CI test
  fails when a service in any compose file has no cap. The cap applies once a container is
  recreated, so `db` needs a `DEPLOY_DB=1` deploy to pick it up. Bug report 081.
- **Deploys check production's SSH host key.** Every deploy and verify script connected with
  `StrictHostKeyChecking=no`, after adding whatever `ssh-keyscan` returned to the runner's
  `known_hosts`. Together that accepted any key. The host's keys are now pinned in
  `scripts/ssh/known_hosts`, and a changed key fails the job with ssh's own message.
  `docs/deployment.md` explains how to update the pin after a reinstall.
- **The secondary compose files no longer publish MariaDB and phpMyAdmin on every interface or
  default the noVNC password to `admin`.** This is the same as `docker/docker-compose.yml` since
  bug report 050.

<!-- release notes -->

- **Server logs can no longer fill the disk.** Every service keeps at most a few tens of megabytes
  of log.
