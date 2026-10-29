- **Operations and agent material moved to the private ops repository.** The production
  scripts (`scripts/prod/`), the crash-triage and nightly-check services, the Claude skills and agent
  plans (`.claude/`, `.ai/`, `.junie/`, the agent plans under `docs/`), `scripts/vw.sh`, `scripts/ssh/known_hosts`
  and the LMS `remote-build.sh` are no longer tracked here, and their tests moved with them. The
  production host key now comes from the file-type CI/CD variable `PROD_SSH_KNOWN_HOSTS`; a pipeline
  without it stops in `prod-ssh-setup.sh` instead of falling back to accept-new. Refs #189.
