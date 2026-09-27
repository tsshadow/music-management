- The pre-deploy database backup can no longer be corrupted by a second writer. On 2026-09-27 a
  `DEPLOY_DB=1` deploy refused to continue because its dump did not decompress: Watchtower's hourly
  session had recreated the running `db-backup` container, which started a second dump in the same
  second as the deploy's fallback, into the same file. The backup run now opts out of Watchtower,
  a failed run's container is removed before the fallback starts (or the deploy is refused), a
  running nightly backup refuses the fallback, every writer's temporary file has a name of its own,
  and the nightly prune leaves a partial file alone until it is an hour old (bug report 123).
