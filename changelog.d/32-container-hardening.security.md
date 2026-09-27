- **Every production container now drops all Linux capabilities and has a PID ceiling; LMS, its
  nginx proxy and autoheal also run on a read-only root filesystem** (issue #32,
  `docs/deployment.md`, "Container hardening"). Until now `no-new-privileges` was the only
  hardening, and the LMS stack did not even have that. Each service gets back only a named set:
  the muma Python images and LMS keep root's four file capabilities (CHOWN, DAC_OVERRIDE, FOWNER,
  FSETID) so their access to the music share and `lms.db` is unchanged, and lose raw sockets,
  MKNOD, SETUID/SETGID and the rest; MariaDB, phpMyAdmin and nginx keep what their root parent
  needs to switch users and bind port 80; autoheal needs nothing. `pids_limit` sits far above the
  PID counts measured on production (29 for music-manager, 40 for LMS, 326 for Firefox). The test
  stack runs the same settings, so core-smoke, the e2e chain and the contract suite exercise
  them. Applies to a container when it is next recreated -- `db` on a `DEPLOY_DB=1` deploy. Not
  done yet, listed in the deployment doc: non-root users and read-only roots for music-manager
  and the workers, and Firefox.
<!-- release notes -->
- Containers run with fewer privileges (capabilities dropped, process limits, read-only
  filesystem for LMS and its proxy).
