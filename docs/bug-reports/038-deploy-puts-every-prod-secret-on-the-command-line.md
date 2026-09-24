# The Deploy Put Every Production Secret On A Command Line

# status: fixed — env file and migration password travel on ssh's stdin, remote files are private and removed, nothing runs from /tmp, CI cleans up its token, agent and env files

# reported problem
A read of the deploy scripts found eight separate ways production secrets leaked during or after a
deploy:

1. `scripts/deploy.sh` and `services/music-management-server/scripts/deploy-stack.sh` base64-encoded
   the whole production `.env` into the ssh command (`BASE64_ENV='...'`). For as long as the deploy
   ran, `ps` showed it to every account on the runner, and to every account on the production host
   through the remote shell's argv.
2. On the host the env file was written to `/tmp/.env.<stack>` with the default umask
   (world-readable) and never deleted — it sat there until the next reboot.
3. Migrations ran `mariadb -u root -p"<root password>"`, putting the MariaDB root password on the
   argv of the ssh command, the remote shell, `docker exec` and the client.
4. The remote script preferred `/tmp/docker-compose-v2` when it was executable. `/tmp` is
   world-writable and the deploy runs as root, so any local account on the production host could
   get code run as root at the next deploy by dropping a file there.
5. `scripts/ci/build-and-push-images.sh` and `scripts/ci/refresh-downloader-image.sh` ran
   `docker login` and never logged out, leaving the Docker Hub push token in the runner account's
   `~/.docker/config.json` — on a shell executor shared by every pipeline, merge requests included.
6. `scripts/ci/prod-ssh-setup.sh` started an `ssh-agent` holding the production root key and never
   stopped it.
7. `scripts/ci-deploy.sh` (and both image scripts) wrote the prod `.env` files into the checkout,
   which is the build context of every image; `.dockerignore` had no `.env` entry. The LMS image's
   build stage copies `services/music-management-server/` whole, so its prod `.env` went into a
   build layer on the runner.
8. The `.env` reader in `scripts/deploy.sh` cut every value at the first `#`, so a password with a
   `#` in it broke every migration while compose, reading the same file, saw it whole.

# Possible reason
The scripts grew from a manual, password-over-sshpass deploy on a trusted workstation, where a
single inline ssh command carrying everything was the simplest thing that worked and `/tmp` was as
good a scratch space as any. When CI took over — a shell-executor runner shared between pipelines,
running as root on the host — nobody re-examined what was on a command line, what outlived the
job, or who else could write to `/tmp`. The `#` truncation was a copy of a `sed` one-liner used for
local convenience scripts where values never contained one.

# solution
- **Env over stdin (1).** Both deploy scripts pipe the env file into `ssh`; the remote script reads
  it with `cat`. Only the compose file (tracked, not secret) stays on the command line. `sshpass`
  now gets its password through `SSHPASS` + `-e` instead of `-p`.
- **Private, short-lived remote files (2, and the compose file).** Under `umask 077` the remote
  script writes into `~/.muma-deploy/<stack>/` (`/root/.muma-deploy/<stack>/` for root, mode 0700).
  The env file goes in a per-run `run.XXXXXX/` directory removed by an `EXIT` trap (also on
  HUP/INT/TERM), since compose only reads `--env-file` while parsing; leftovers of a killed run are
  removed by the next one. The compose file is kept there, off `/tmp`.
- **Migration password via `MYSQL_PWD` (3).** stdin carries the password on the first line and the
  SQL after it; the remote shell does `IFS= read -r MYSQL_PWD` and
  `docker exec -i -e MYSQL_PWD ... mariadb`, which copies the value from the environment. No
  temporary SQL file either. Mirrors `tools/db_backup.py`, which already used a
  `--defaults-extra-file`.
- **No compose binary from /tmp (4).** The branch is gone. `deploy-stack.sh` still prefers the
  root-owned `/usr/local/bin/docker-compose-v2`; `deploy.sh` never had that branch and was not given
  one, so the music-management stack keeps the binary it resolves today (production: v1).
- **Throwaway Docker config (5).** New `scripts/ci/docker-hub-session.sh`: `docker_hub_login` points
  `DOCKER_CONFIG` at a fresh `mktemp -d` (with `cli-plugins`, `buildx` and `contexts` symlinked in so
  builds behave the same), `docker_hub_logout` logs out and deletes it; both image scripts call the
  logout from their `EXIT` trap.
- **Agent teardown (6).** `prod-ssh-setup.sh` installs `trap prod_ssh_teardown EXIT` in the shell
  that sources it and adds the key with `ssh-add -t 3600`. All three sourcing scripts
  (`ci-deploy.sh`, `post-deploy-verify.sh`, `verify-prod-version.sh`) run as their own process, so
  the trap fires when the job's script ends; `ci-deploy.sh` chains it into its own cleanup.
- **Env files out of the build context (7).** All three CI scripts materialise the env files in a
  private `mktemp -d` outside the checkout and delete it on exit; `deploy.sh` accepts an absolute
  `LOCAL_ENV_FILE`. `.dockerignore` (root and LMS) excludes `.env` and `**/.env`; no Dockerfile
  copies one.
- **A parser that matches compose (8).** `scripts/lib/dotenv.sh` (`dotenv_parse_line`,
  `dotenv_load`): `#` starts a comment only at line start or after whitespace in an unquoted value;
  quoted values are literal. Used by `scripts/deploy.sh` and
  `services/music-management-server/scripts/deploy.sh`.
- **Tests.** `tests/ci/test_deploy_script_hygiene.py` greps for every forbidden shape and runs the
  real deploy scripts against fake `ssh`/`docker`/`docker-compose` binaries that execute the remote
  half locally, asserting the env file arrives intact with mode 0600, is gone afterwards, and that
  neither it nor the password appears on any recorded argv.

Not verifiable from CI: the remote half on the real host. On the first deploy after this change,
check `/root/.muma-deploy/<stack>/` exists with mode 0700 and contains no `run.*` directory, that
the containers' `com.docker.compose.project.config_files` label points there, and delete the stale
`/tmp/.env.music-management`, `/tmp/.env.lms` and `/tmp/docker-compose.*.yml` by hand. Also
`docker logout` once as the runner account, since the token already stored in its
`~/.docker/config.json` predates this fix.
