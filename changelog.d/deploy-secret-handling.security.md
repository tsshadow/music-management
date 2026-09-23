- **A deploy showed the whole production `.env` to anyone who ran `ps`.** `deploy.sh` and
  `deploy-stack.sh` put the env file, base64-encoded, on the ssh command line, and migrations put
  the MariaDB root password in `mariadb -p...` — visible on the runner and on the production host
  for as long as the deploy ran. The env file now travels on ssh's stdin and the password reaches
  the client as `MYSQL_PWD` through `docker exec -e`. On the host the env file is written under
  `umask 077` to `/root/.muma-deploy/<stack>/` and deleted when the deploy ends, instead of staying
  world-readable in `/tmp/.env.<stack>` until the next reboot; the compose file moved there too,
  and a `/tmp/docker-compose-v2` is no longer run as root. In CI the Docker Hub login uses a
  throwaway `DOCKER_CONFIG`, the ssh-agent holding the prod key is killed when its job ends, and
  the prod env files are written outside the checkout (and `.dockerignore` excludes `.env`), so
  none of them outlives the job on the shared runner or lands in a build context. A password
  containing `#` no longer breaks the migration step. See bug report 038.

<!-- release notes -->

- **A deploy no longer exposes production secrets on the runner or the server.** The env file and
  the database password are no longer visible in the process list, no copy stays behind in `/tmp`,
  and the Docker Hub token and deploy key no longer outlive their CI job.
