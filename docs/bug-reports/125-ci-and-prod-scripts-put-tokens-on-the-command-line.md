# CI And Prod Scripts Still Put Tokens And Passwords On A Command Line

# status: fixed — every script moved to MYSQL_PWD, `-e NAME`, curl header/body via process substitution or stdin, `sshpass -e`, ssh stdin; `tests/ci/test_no_secrets_on_command_lines.py` guards it

# reported problem
Bug report 038 took secrets off the deploy's command lines. GitLab #40 noted that
`scripts/prod/create-readonly-db-user.sh` still had the same shape, and that about ten scripts
still read `.env` with a loop that cuts values at `#`. A sweep of every shell script, compose file,
Gradle file and the CI definition for the rest found considerably more than that one script. Each
of these put a live secret on an argv, which `ps` and `/proc/<pid>/cmdline` show to every account
on the machine -- and a process inside a container is just as visible from the host:

On the shared shell-executor runner (every pipeline, merge requests included, runs as the same
account; the runner LXC also hosts other accounts such as `briefing`):
1. `scripts/ci/back-merge-develop.sh`, `create-release-tags.sh`, `delete-merged-release-branch.sh`:
   `curl --header "PRIVATE-TOKEN: ${TAG_CREATION_TOKEN}"` -- a token that can create tags, open and
   merge MRs, and delete branches.
2. `scripts/ci/renovate.sh`: `docker run -e "RENOVATE_TOKEN=..."` and
   `-e "GITHUB_COM_TOKEN=..."`, for the whole length of a Renovate run.
3. `scripts/ci/muma-mobile-build-upload.sh`: `docker run -e SIGNING_STORE_PASSWORD=...`,
   `-e SIGNING_KEY_PASSWORD=...`, `-e APK_HOSTER_PASSWORD=...` -- the release signing key's
   passwords for the length of a Gradle release build; inside that container
   `services/muma-mobile/scripts/deploy.sh` then sent the upload password as
   `curl -H "X-Upload-Password: ..."`.
4. `scripts/nightly-prod-check/prod-get.sh` and `scripts/crash-triage/crash-status.sh`:
   `curl -H "X-API-Key: $MUMA_SYSTEM_API_KEY"` -- the production system API key.

On the production host (as root, visible to every local account and every container user):
5. `scripts/prod/create-readonly-db-user.sh`: the new account's password in the ssh remote command,
   the MariaDB root password in `docker exec -e MYSQL_PWD=<value>` (the variable name does not
   help when the value is on docker's argv).
6. `scripts/prod/clear-spurious-artist-retag-marks.sh`, `scripts/prod/repair-username-case.sh`:
   `sh -c 'exec mariadb -uroot -p"$MYSQL_ROOT_PASSWORD"'` inside the db container, so the
   expanded root password is the client's argv.
7. `scripts/prod-restructure-music.sh`: `docker exec -e MYSQL_PWD="$DB_PASS"`.

On the workstation:
8. `scripts/prod/person/get-muma-admin-key.sh`: the admin's login password on `python3`'s argv and
   in curl's `--data-binary`; `scripts/prod/install-muma-mcp.sh`: the prod API key in a curl header.
9. `publish.sh` and `services/muma-mobile/scripts/deploy.sh`: `sshpass -p <password>`;
   `services/muma-mobile/build.gradle` `generateKeystore`: `keytool -storepass <pw> -keypass <pw>`.
10. `scripts/migrate_lms_history.py` *required* `--api-key <key>`, so every run put the system
    key in shell history.

And the `.env` reader in `build.sh`, `publish.sh`, `scripts/lint.sh`, `scripts/run_local.sh`,
`scripts/set_user_password.sh`, `scripts/test/music-management-unit.sh`, `tools/backup_db.sh` and
the LMS `build.sh`/`publish.sh` still cut `ab#cd` to `ab` (and kept quotes as part of a value),
while docker-compose reading the same file saw `ab#cd`.

# Possible reason
Bug report 038 fixed the one path that carried *every* secret, and its hygiene test only reads the
deploy scripts. Nothing looked at the rest, and each of these scripts was written the obvious way:
`-H "Header: $value"`, `-e NAME="$value"`, `-p"$pw"` are what every example shows. The variable
name `MYSQL_PWD` in `-e MYSQL_PWD=<value>` reads as if it were the safe pattern, which is how two
scripts that meant to avoid `-p` ended up exposing the same value anyway.

# solution
- **MariaDB:** `MYSQL_PWD` in the environment, handed to `docker exec` as `-e MYSQL_PWD` without a
  value (docker copies it from its own environment), or set inside the container's `sh -c` before
  `exec mariadb`.
- **docker run:** export, then `-e NAME` without `=value` (renovate, the mobile release build).
- **curl:** the header through a process substitution, `-H @<(printf 'X-API-Key: %s\n' "$KEY")`
  -- the printf is a bash builtin in a forked subshell, so the value is in no process's argv and
  curl's argv holds only `/dev/fd/63`; a JSON body with a password through `--data-binary @-`.
- **ssh:** the new password as the first line of ssh's stdin, read with `IFS= read -r` before
  `bash -s` reads the script that follows.
- **sshpass:** `SSHPASS=... sshpass -e`. **keytool:** `-storepass:env` / `-keypass:env`.
- **Python CLIs:** `--api-key` defaults to `MUMA_API_KEY` from the environment.
- **.env reader:** all nine scripts source `scripts/lib/dotenv.sh` and call `dotenv_load`
  (`--keep-existing` where the old loop skipped variables already set).
- **Guard:** `tests/ci/test_no_secrets_on_command_lines.py` scans every tracked shell script,
  YAML file, Dockerfile and Gradle file for the shapes above and fails on a new one; throwaway
  test-container credentials are allowlisted with a reason, and a stale allowlist entry fails too.
  It also fails on the `#`-cutting `.env` loop.

Not verifiable from CI: the prod-side scripts only run by hand against production. The tokens
listed under 1-4 were visible on the runner for as long as each command ran; nothing shows they were
read, but the runner is shared, so rotating `TAG_CREATION_TOKEN`, `RENOVATE_TOKEN` and the
`APK_HOSTER_PASSWORD` is a reasonable precaution and is left to the owner.
