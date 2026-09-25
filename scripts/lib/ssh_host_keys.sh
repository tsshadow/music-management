#!/bin/bash
# scripts/lib/ssh_host_keys.sh
#
# Host key checking for the scripts that SSH into production. Meant to be sourced.
#
# Every one of them used to pass `-o StrictHostKeyChecking=no`, and the CI setup
# appended whatever `ssh-keyscan` returned to the shared runner's known_hosts
# first. Together that accepted any key at all: anything answering on the
# production address -- a reinstalled host, or something impersonating it --
# received the root key's signature, every production secret on stdin, and the
# database migrations. See docs/bug-reports/081-compose-logs-grow-without-bound.md.
#
# The production host's keys are pinned in scripts/ssh/known_hosts. A host listed
# there is checked against that file only, with StrictHostKeyChecking=yes: a key
# that differs fails the connection instead of being learned. A host that is not
# listed (a Portainer host, a developer's own target) falls back to accept-new
# against the user's own known_hosts, which learns a key once and refuses it if it
# changes later -- still never "accept anything".
#
# SSH_PINNED_KNOWN_HOSTS overrides the pinned file, e.g. with a file-type CI/CD
# variable after the host was reinstalled and before the repository caught up.

SSH_PINNED_KNOWN_HOSTS="${SSH_PINNED_KNOWN_HOSTS:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../ssh" && pwd)/known_hosts}"
export SSH_PINNED_KNOWN_HOSTS

# ssh_host_key_opts HOST: print the ssh -o options for HOST, one argument per
# line (read them with `mapfile -t`, so a path with spaces stays one argument).
ssh_host_key_opts() {
    local host="$1"
    if [ -f "$SSH_PINNED_KNOWN_HOSTS" ] \
        && ssh-keygen -F "$host" -f "$SSH_PINNED_KNOWN_HOSTS" >/dev/null 2>&1; then
        printf '%s\n' -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$SSH_PINNED_KNOWN_HOSTS"
    else
        printf '%s\n' -o StrictHostKeyChecking=accept-new
    fi
}
export -f ssh_host_key_opts
