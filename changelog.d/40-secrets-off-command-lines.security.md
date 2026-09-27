- **No password, token or key goes on a command line any more, outside the deploy as well**
  (issue #40, bug report 125). The release jobs sent the GitLab tag/merge token as a curl header,
  Renovate and the mobile release build passed their tokens and the signing passwords as
  `docker run -e NAME=value`, the nightly check and crash triage put the production system API key
  in a curl header, and three prod scripts put the MariaDB root password on the argv of
  `docker exec` or the client -- all readable through `ps` by every account on the shared runner or
  the production host. They now use `MYSQL_PWD` via `-e NAME` without a value, curl headers through
  a process substitution, ssh's stdin, `sshpass -e` and `keytool -storepass:env`;
  `scripts/migrate_lms_history.py` reads its key from `MUMA_API_KEY`. The nine scripts that still
  read `.env` with the loop that cut `ab#cd` to `ab` use `scripts/lib/dotenv.sh`, as the deploy
  does. A new CI test (`tests/ci/test_no_secrets_on_command_lines.py`) fails on any new
  occurrence.
<!-- release notes -->
- Scripts and CI jobs no longer show passwords or tokens in the process list.
